"""Document model — 1 row per uploaded file (linked via doc_id; invoices share doc_id)."""
from app.database import get_connection


def create_document(doc_id: str, doc_name: str, s3_key: str, s3_url: str) -> dict | None:
    """Insert a document row (1 per file). Returns existing if doc_id already exists."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT IGNORE INTO documents (doc_id, doc_name, s3_key, s3_url)
                   VALUES (%s, %s, %s, %s)""",
                (doc_id, doc_name, s3_key, s3_url),
            )
            conn.commit()
            if cur.rowcount > 0:
                new_id = cur.lastrowid
                cur.execute(
                    "SELECT id, doc_id, doc_name, s3_key, s3_url, created_at FROM documents WHERE id = %s",
                    (new_id,),
                )
                return cur.fetchone()
            cur.execute(
                "SELECT id, doc_id, doc_name, s3_key, s3_url, created_at FROM documents WHERE doc_id = %s",
                (doc_id,),
            )
            return cur.fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_document_by_doc_id(doc_id: str) -> dict | None:
    """Return the document for a doc_id (1 row per uploaded file)."""
    if not doc_id:
        return None
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, doc_id, doc_name, s3_key, s3_url, created_at FROM documents WHERE doc_id = %s LIMIT 1",
                (doc_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def get_documents_by_doc_ids(doc_ids: list[str]) -> dict[str, dict]:
    """Return documents for given doc_ids. Maps doc_id -> document."""
    if not doc_ids:
        return {}
    seen = set()
    unique_ids = [x for x in doc_ids if x and x not in seen and not seen.add(x)]
    if not unique_ids:
        return {}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(unique_ids))
            cur.execute(
                f"""SELECT id, doc_id, doc_name, s3_key, s3_url, created_at
                    FROM documents WHERE doc_id IN ({placeholders})""",
                unique_ids,
            )
            return {r["doc_id"]: r for r in cur.fetchall()}
    finally:
        conn.close()


def get_document_for_invoice_deletion(invoice_doc_id: str) -> dict | None:
    """Get document by doc_id (for delete flow)."""
    return get_document_by_doc_id(invoice_doc_id)


def count_invoices_with_doc_id(doc_id: str) -> int:
    """Count how many invoices reference this doc_id (for S3 delete decision)."""
    if not doc_id:
        return 0
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM invoices WHERE doc_id = %s", (doc_id,))
            row = cur.fetchone()
            return int(row["cnt"] or 0)
    finally:
        conn.close()


def delete_document_by_doc_id(doc_id: str) -> bool:
    """Delete document row by doc_id. Returns True if deleted."""
    if not doc_id:
        return False
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))
            conn.commit()
            return cur.rowcount > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
