"""
RAG (Retrieval-Augmented Generation) search service for invoices.

Uses:
  - sentence-transformers  → local embeddings (all-MiniLM-L6-v2, ~80 MB download once)
  - chromadb               → in-process vector store, persisted to ./chroma_db on disk

Workflow:
  1. After each successful invoice save  → index_invoice(invoice_id, invoice_dict)
  2. Search endpoint calls               → search_invoices(query, user_id, top_k)

No external API keys required — everything runs locally.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Persist ChromaDB data alongside the app
_CHROMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "chroma_db",
)

_client = None
_collection = None
_embedder = None


def _get_embedder():
    """Lazy-load the sentence-transformer model (downloads once on first call)."""
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model all-MiniLM-L6-v2 …")
            _embedder = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Embedding model ready.")
        except ImportError:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers"
            )
    return _embedder


def _get_collection():
    """Lazy-initialise ChromaDB client and collection."""
    global _client, _collection
    if _collection is None:
        try:
            import chromadb

            os.makedirs(_CHROMA_DIR, exist_ok=True)
            _client = chromadb.PersistentClient(path=_CHROMA_DIR)
            _collection = _client.get_or_create_collection(
                name="invoices",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB collection 'invoices' ready at %s", _CHROMA_DIR)
        except ImportError:
            raise RuntimeError(
                "chromadb is not installed. Run: pip install chromadb"
            )
    return _collection


def _invoice_to_text(invoice: dict) -> str:
    """
    Convert an invoice dict into a single plain-text string for embedding.
    The richer the text, the better the semantic search.
    """
    parts = []

    def add(label: str, value):
        if value and str(value).strip() not in ("", "null", "None"):
            parts.append(f"{label}: {value}")

    add("Buyer", invoice.get("buyer_party_name") or invoice.get("client_name"))
    add("Seller", invoice.get("seller_party_name"))
    add("Industry", invoice.get("industry"))
    add("Transaction type", invoice.get("transaction_type"))
    add("Buyer Location", invoice.get("buyer_location"))
    add("Seller Location", invoice.get("seller_location"))
    add("Total", invoice.get("total"))
    add("Buyer GST", invoice.get("buyer_gst_number"))
    add("Seller GST", invoice.get("seller_gst_number"))
    add("GST", invoice.get("gst"))
    add("Payment mode", invoice.get("payment_mode"))
    add("Buyer PAN", invoice.get("buyer_pan_number"))
    add("Seller PAN", invoice.get("seller_pan_number"))

    # Flatten additional_details (stored as dict or JSON string)
    ad = invoice.get("additional_detail") or invoice.get("additional_details")
    if isinstance(ad, str):
        try:
            ad = json.loads(ad)
        except Exception:
            ad = None
    if isinstance(ad, dict):
        for k, v in ad.items():
            add(k.replace("_", " ").title(), v)

    return " | ".join(parts) if parts else "invoice"


def index_invoice(invoice_id: int, invoice: dict) -> None:
    """
    Embed and store one invoice in ChromaDB.
    Safe to call multiple times — upserts on the same ID.
    """
    try:
        collection = _get_collection()
        embedder = _get_embedder()
        text = _invoice_to_text(invoice)
        embedding = embedder.encode(text).tolist()
        collection.upsert(
            ids=[str(invoice_id)],
            embeddings=[embedding],
            documents=[text],
            metadatas=[
                {
                    "invoice_id": invoice_id,
                    "user_id": str(invoice.get("user_id", "")),
                    "client_name": str(invoice.get("client_name") or ""),
                    "total": str(invoice.get("total") or ""),
                    "industry": str(invoice.get("industry") or ""),
                    "status": str(invoice.get("status") or ""),
                }
            ],
        )
        logger.debug("Indexed invoice %s: %s", invoice_id, text[:80])
    except Exception as exc:
        # Never crash the upload flow because of RAG indexing
        logger.warning("RAG indexing failed for invoice %s: %s", invoice_id, exc)


def search_invoices(
    query: str,
    user_id: Optional[str] = None,
    top_k: int = 10,
) -> list[dict]:
    """
    Semantic search over indexed invoices.

    Args:
        query:   Natural-language query, e.g. "hospital electronics purchase last month"
        user_id: If provided, filter results to this user's invoices only.
        top_k:   Maximum number of results to return.

    Returns:
        List of dicts with keys: invoice_id, score, client_name, industry,
        total, status, snippet (the indexed text).
    """
    collection = _get_collection()
    embedder = _get_embedder()

    query_embedding = embedder.encode(query).tolist()

    where_clause: Optional[dict] = None
    if user_id:
        where_clause = {"user_id": str(user_id)}

    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, max(collection.count(), 1)),
            where=where_clause,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.error("ChromaDB query failed: %s", exc)
        return []

    hits = []
    ids_list      = results.get("ids", [[]])[0]
    docs_list     = results.get("documents", [[]])[0]
    metas_list    = results.get("metadatas", [[]])[0]
    distances     = results.get("distances", [[]])[0]

    for doc_id, doc_text, meta, dist in zip(ids_list, docs_list, metas_list, distances):
        # cosine distance → similarity score (1 = identical)
        score = round(1.0 - dist, 4)
        hits.append(
            {
                "invoice_id":  int(doc_id),
                "score":       score,
                "client_name": meta.get("client_name"),
                "industry":    meta.get("industry"),
                "total":       meta.get("total"),
                "status":      meta.get("status"),
                "snippet":     doc_text[:200],
            }
        )

    # Sort highest score first
    hits.sort(key=lambda x: x["score"], reverse=True)
    return hits


def reindex_all(invoices: list[dict]) -> int:
    """
    Bulk-index a list of invoices (useful for bootstrapping existing DB data).
    Returns the count of successfully indexed invoices.
    """
    count = 0
    for inv in invoices:
        inv_id = inv.get("id")
        if inv_id is not None:
            index_invoice(inv_id, inv)
            count += 1
    return count
