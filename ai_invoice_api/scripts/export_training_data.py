#!/usr/bin/env python3
"""
Export ALL labeled invoices for LLaMA-Factory fine-tuning (category/subcategory).

Exports every invoice with category OR subcategory populated.
Run from invoice_api dir: python scripts/export_training_data.py [--output-dir training_data]

Output:
- training_data/images/*.jpg  (resized to max 1024px)
- training_data/invoice_category_train.json  (Alpaca format)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

from PIL import Image

_MAX_IMG_PX = 1024


def _resize_image(img: Image.Image, max_size: int = _MAX_IMG_PX) -> Image.Image:
    w, h = img.size
    if max(w, h) <= max_size:
        return img
    scale = max_size / max(w, h)
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def _pdf_to_page_images(file_path: str) -> list[Image.Image]:
    try:
        import fitz
    except ImportError:
        raise RuntimeError("PyMuPDF required: pip install pymupdf")
    doc = fitz.open(file_path)
    images = []
    for page in doc:
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images


def main() -> None:
    parser = argparse.ArgumentParser(description="Export all labeled invoices for category/subcategory training")
    parser.add_argument("--output-dir", default="training_data", help="Output directory")
    parser.add_argument("--limit", type=int, default=0, help="Max invoices to export (0 = all)")
    parser.add_argument("--local-dir", default="", help="Use local files instead of S3")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    from app.database import get_connection
    from app.models.document import get_documents_by_doc_ids

    conn = get_connection()
    labeled = []
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT i.id, i.doc_id, i.category, i.sub_category
                FROM invoices i
                WHERE i.category IS NOT NULL AND i.category != ''
                   OR i.sub_category IS NOT NULL AND i.sub_category != ''
                ORDER BY i.doc_id, i.id
            """
            if args.limit:
                sql += f" LIMIT {args.limit}"
            cur.execute(sql)
            labeled = cur.fetchall()
    finally:
        conn.close()

    if not labeled:
        print("No labeled invoices found. Label via PATCH /invoices/{id} with category/subcategory.")
        sys.exit(1)

    doc_ids = list({r["doc_id"] for r in labeled if r.get("doc_id")})
    docs = get_documents_by_doc_ids(doc_ids)
    doc_id_to_invoices: dict[str, list[dict]] = {}
    for row in labeled:
        did = row.get("doc_id") or ""
        doc_id_to_invoices.setdefault(did, []).append(row)

    use_s3 = not args.local_dir and os.getenv("S3_BUCKET_NAME")
    if not use_s3 and not args.local_dir:
        print("Warning: S3_BUCKET_NAME not set. Use --local-dir for local files.")

    records = []
    seen_ids = set()

    for doc_id, inv_list in doc_id_to_invoices.items():
        if not doc_id:
            continue
        doc = docs.get(doc_id)
        if not doc and use_s3:
            continue

        s3_key = doc.get("s3_key") if doc else None
        doc_name = (doc.get("doc_name") or "doc").lower() if doc else ""

        if use_s3 and s3_key:
            from app.services.s3_service import download_from_s3
            try:
                file_bytes = download_from_s3(s3_key)
            except Exception as e:
                print(f"Skip doc_id={doc_id}: {e}")
                continue
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(doc_name).suffix or ".pdf") as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            try:
                _process_file(tmp_path, inv_list, images_dir, records, seen_ids)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        elif args.local_dir:
            local_path = Path(args.local_dir) / doc_id / doc_name
            if not local_path.exists():
                local_path = Path(args.local_dir) / doc_name
            if local_path.exists():
                _process_file(str(local_path), inv_list, images_dir, records, seen_ids)

    out_json = output_dir / "invoice_category_train.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print(f"Exported {len(records)} samples to {out_json}")
    print(f"Images in {images_dir}")


def _process_file(
    file_path: str,
    inv_list: list[dict],
    images_dir: Path,
    records: list[dict],
    seen_ids: set[int],
) -> None:
    ext = Path(file_path).suffix.lower()
    inv_list_sorted = sorted(inv_list, key=lambda x: x.get("id", 0))

    if ext == ".pdf":
        pages = _pdf_to_page_images(file_path)
        for idx, inv in enumerate(inv_list_sorted):
            if idx >= len(pages):
                break
            if inv.get("id") in seen_ids:
                continue
            seen_ids.add(inv["id"])
            cat = (inv.get("category") or "").strip()
            sub = (inv.get("sub_category") or "").strip()
            if not cat and not sub:
                continue
            img = _resize_image(pages[idx])
            img_name = f"inv_{inv['id']}_page{idx}.jpg"
            img_path = images_dir / img_name
            img.convert("RGB").save(img_path, "JPEG", quality=90)
            records.append({
                "instruction": "Classify the category and sub_category of this invoice. Return JSON only.",
                "input": "<image>",
                "output": json.dumps({"category": cat or None, "sub_category": sub or None}),
                "images": [f"images/{img_name}"],
            })
    else:
        if not inv_list_sorted:
            return
        inv = inv_list_sorted[0]
        if inv.get("id") in seen_ids:
            return
        seen_ids.add(inv["id"])
        cat = (inv.get("category") or "").strip()
        sub = (inv.get("sub_category") or "").strip()
        if not cat and not sub:
            return
        img = Image.open(file_path).convert("RGB")
        img = _resize_image(img)
        img_name = f"inv_{inv['id']}.jpg"
        img_path = images_dir / img_name
        img.save(img_path, "JPEG", quality=90)
        records.append({
            "instruction": "Classify the category and sub_category of this invoice. Return JSON only.",
            "input": "<image>",
            "output": json.dumps({"category": cat or None, "sub_category": sub or None}),
            "images": [f"images/{img_name}"],
        })


if __name__ == "__main__":
    main()
