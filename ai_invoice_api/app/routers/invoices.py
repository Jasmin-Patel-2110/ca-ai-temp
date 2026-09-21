import os
import threading
import uuid
import tempfile
import logging
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from typing import List

from app.dependencies import get_current_user
from app.services.s3_service import upload_to_s3
from app.services.vllm_service import ensure_model_available, is_vllm_running
from app.services.extraction_service import extract_from_file, extract_from_pdf_all_pages
from app.services import classifier_service
from app.services.rag_service import index_invoice, search_invoices
from app.models.invoice import (
    create_invoice, get_invoices_by_user, get_invoice_by_id,
    get_all_invoices, update_invoice, get_dashboard_stats, get_recent_invoices,
    search_invoice_by_keyword, delete_invoice, build_document_response,
    SplitInvoiceGroupError,
)
from app.models.document import create_document
from app.schemas.invoice import (
    InvoiceUploadResponse, InvoiceListResponse, InvoiceData, InvoiceListItem,
    UpdateInvoiceRequest, UpdateInvoiceResponse, INDUSTRY_VALUES,
    CATEGORY_TAXONOMY,
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}

# Number of files to process in parallel — matches EXTRACTION_WORKERS in extraction.py
UPLOAD_WORKERS = int(os.getenv("EXTRACTION_WORKERS", "3"))


# ── Per-file processor (runs in thread pool) ──────────────────────────────────

def _process_single_file(
    file_bytes: bytes,
    filename: str,
    ext: str,
    user_id: str,
    email: str,
    known_client_name_hint: str | None = None,
) -> list[dict]:
    """
    Process one uploaded file end-to-end:
      S3 upload → temp file → extraction → DB save → RAG index

    Returns list of saved invoice dicts (PDF can have multiple pages).
    Runs inside a ThreadPoolExecutor — must be thread-safe.
    """
    # 1. Upload to S3
    try:
        s3_key, s3_url = upload_to_s3(
            BytesIO(file_bytes), filename,
            user_id=user_id,
            email=email,
        )
    except Exception as e:
        raise RuntimeError(f"S3 upload failed for '{filename}': {e}")

    # 2. Write temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    # 3. Create document record
    shared_doc_id = str(uuid.uuid4())
    doc           = create_document(shared_doc_id, filename or "doc", s3_key, s3_url)
    doc_response  = build_document_response(doc)
    saved_list: list = []

    try:
        if ext == ".pdf":
            # Multi-page PDF — one invoice per page
            try:
                extracted_list = extract_from_pdf_all_pages(
                    tmp_path,
                    known_client_name_hint=known_client_name_hint,
                )
            except (RuntimeError, ValueError) as e:
                raise RuntimeError(f"PDF extraction failed for '{filename}': {e}")

            for extracted in extracted_list:
                if not isinstance(extracted, dict):
                    extracted = {}
                extracted["user_id"] = user_id
                extracted["doc_id"]  = shared_doc_id
                extracted["status"]  = "pending_verification"
                # PDF pages are NOT line-item splits — is_line_item_split stays 0

                try:
                    saved = create_invoice(extracted)
                    saved_rows = saved if isinstance(saved, list) else [saved]
                    for sr in saved_rows:
                        sr["document"] = doc_response

                        # ── ML Prediction (after split) ───────────────────────
                        if sr.get("status") != "error":
                            try:
                                prediction = classifier_service.predict(sr)

                                category_pred     = prediction.get("category", "None")
                                sub_category_pred = prediction.get("sub_category", "None")
                                logging.info(
                                    "[upload] ML prediction line_item=%r category=%r sub_category=%r",
                                    sr.get("product_name", "Unknown"),
                                    category_pred,
                                    sub_category_pred,
                                )

                                updates = {}
                                if prediction.get("category"):
                                    sr["category"] = prediction["category"]
                                    updates["category"] = prediction["category"]
                                if prediction.get("sub_category"):
                                    sr["sub_category"] = prediction["sub_category"]
                                    updates["sub_category"] = prediction["sub_category"]

                                if updates:
                                    update_invoice(sr["id"], updates)
                            except Exception as _e:
                                logging.warning("[upload] Classifier predict failed (non-fatal): %s", _e)
                        # ─────────────────────────────────────────────────────

                        saved_list.append(sr)
                        if sr.get("status") != "error":
                            index_invoice(sr["id"], sr)
                except Exception as e:
                    raise RuntimeError(f"DB save failed: {e}")

        else:
            # Single image file
            extraction_error = None
            try:
                extracted = extract_from_file(
                    tmp_path,
                    known_client_name_hint=known_client_name_hint,
                )
            except (RuntimeError, ValueError) as e:
                extraction_error = str(e)
                logging.warning(f"[upload] Extraction failed for {filename}: {extraction_error}")
                extracted = {}

            if not isinstance(extracted, dict):
                extracted = {}

            extracted["user_id"] = user_id
            extracted["doc_id"]  = shared_doc_id
            extracted["status"]  = "error" if extraction_error else "pending_verification"

            if extraction_error:
                ad = extracted.get("additional_detail") or extracted.get("additional_details") or {}
                ad = ad if isinstance(ad, dict) else {}
                extracted["additional_detail"] = {**ad, "extraction_error": extraction_error}

            try:
                saved = create_invoice(extracted)
                saved_rows = saved if isinstance(saved, list) else [saved]
                for sr in saved_rows:
                    sr["document"] = doc_response

                    # ── ML Prediction (after split) ───────────────────────────
                    if sr.get("status") != "error":
                        try:
                            prediction = classifier_service.predict(sr)
                            logging.info(
                                "[upload] ML prediction line_item=%r category=%r sub_category=%r",
                                sr.get("product_name", "Unknown"),
                                prediction.get("category", "None"),
                                prediction.get("sub_category", "None"),
                            )
                            updates = {}
                            if prediction.get("category"):
                                sr["category"] = prediction["category"]
                                updates["category"] = prediction["category"]
                            if prediction.get("sub_category"):
                                sr["sub_category"] = prediction["sub_category"]
                                updates["sub_category"] = prediction["sub_category"]

                            if updates:
                                update_invoice(sr["id"], updates)
                        except Exception as _e:
                            logging.warning("[upload] Classifier predict failed (non-fatal): %s", _e)
                    # ─────────────────────────────────────────────────────────

                    saved_list.append(sr)
                    if sr.get("status") != "error":
                        index_invoice(sr["id"], sr)
            except Exception as e:
                raise RuntimeError(f"DB save failed: {e}")

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return saved_list


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/industries")
def list_industries():
    return {"status": 200, "message": "Industries fetched", "industries": INDUSTRY_VALUES}


@router.get("/categories")
def list_categories():
    return {
        "status": 200,
        "message": "Categories fetched",
        "categories": CATEGORY_TAXONOMY,
    }


@router.post("/upload", response_model=InvoiceUploadResponse)
def upload_invoice(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
    known_client_name: str | None = Form(None),
):
    """
    Upload one or more invoice files (PDF/image).
    Files are processed in PARALLEL using ThreadPoolExecutor.
    """
    print(f"[known_client_name] Received {known_client_name}")

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    print(f"[upload] Received {len(files)} file(s): {[f.filename for f in files]}")
    for i, f in enumerate(files):
        logging.info(f"[upload] [{i+1}] filename={f.filename!r} content_type={f.content_type!r}")

    # Check vLLM once before processing (runs separately, e.g. port 8002)
    if not is_vllm_running():
        raise HTTPException(
            status_code=503,
            detail="vLLM is not reachable. Start it on the configured VLLM_BASE_URL (default http://127.0.0.1:8002).",
        )
    try:
        ensure_model_available()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    user_id = str(current_user.get("sub", ""))
    email   = current_user.get("email") or ""

    # ── Validate ALL files before processing any ──────────────────────────────
    validated = []
    for file in files:
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}' in '{file.filename}'. "
                       f"Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            )
        file_bytes = file.file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail=f"File '{file.filename}' is empty")
        validated.append((file_bytes, file.filename, ext))

    # ── Process all files in PARALLEL ─────────────────────────────────────────
    all_saved: list = []
    errors:    list = []

    with ThreadPoolExecutor(max_workers=UPLOAD_WORKERS) as pool:
        future_to_filename = {
            pool.submit(
                _process_single_file,
                file_bytes, filename, ext, user_id, email,
                known_client_name,
            ): filename
            for file_bytes, filename, ext in validated
        }

        for future in as_completed(future_to_filename):
            filename = future_to_filename[future]
            print(f"[upload] Processing {filename}")
            try:
                saved_list = future.result()
                all_saved.extend(saved_list)
            except HTTPException:
                raise
            except Exception as e:
                logging.error(f"[upload] Failed to process '{filename}': {e}")
                errors.append({"filename": filename, "error": str(e)})

    if errors and not all_saved:
        raise HTTPException(
            status_code=422,
            detail=f"All files failed to process: {errors}",
        )

    n = len(all_saved)
    msg = f"{n} invoice(s) processed successfully"
    if errors:
        msg += f" ({len(errors)} file(s) failed)"

    known_client_name_clean = (known_client_name or "").strip() or None
    print(f"[upload] known_client_name={known_client_name_clean}")

    return InvoiceUploadResponse(
        status=200,
        message=msg,
        known_client_name=known_client_name_clean,
        invoices=[InvoiceListItem(**s) for s in all_saved] if all_saved else None,
    )


@router.get("", response_model=InvoiceListResponse)
def list_invoices(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user.get("sub", ""))
    rows = get_invoices_by_user(user_id)
    return InvoiceListResponse(
        status=200,
        message="Invoices fetched",
        invoices=[InvoiceListItem(**r) for r in rows],
    )


@router.get("/dashboard")
def dashboard(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user.get("sub", ""))
    stats = get_dashboard_stats(user_id)
    stats["recent_invoices"] = get_recent_invoices(user_id)
    return {"status": 200, "message": "Dashboard stats fetched", "data": stats}


@router.get("/all", response_model=InvoiceListResponse)
def list_all_invoices(
    user_id: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    if user_id:
        rows = get_invoices_by_user(str(user_id))
        message = f"Invoices fetched for user {user_id}"
    else:
        rows = get_all_invoices()
        message = "All invoices fetched"
    return InvoiceListResponse(
        status=200,
        message=message,
        invoices=[InvoiceListItem(**r) for r in rows],
    )


@router.get("/search")
def search_invoice(
    q: str,
    current_user: dict = Depends(get_current_user),
):
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")
    user_id = str(current_user.get("sub", ""))
    try:
        hits = search_invoice_by_keyword(user_id=user_id, keyword=q.strip())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "status": 200,
        "message": f"{len(hits)} result(s) found",
        "query": q.strip(),
        "results": [InvoiceListItem(**r).model_dump() for r in hits],
    }


@router.patch("/{invoice_id}", response_model=UpdateInvoiceResponse)
def patch_invoice(
    invoice_id: int,
    body: UpdateInvoiceRequest,
    current_user: dict = Depends(get_current_user),
):
    row = get_invoice_by_id(invoice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if str(row["user_id"]) != str(current_user.get("sub", "")):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        updated = update_invoice(invoice_id, body.model_dump(exclude_unset=True))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {e}")

    # ── Incremental training trigger ───────────────────────────────────────────
    if body.model_dump(exclude_unset=True).get("status") == "verified":
        if updated.get("category") or updated.get("sub_category"):
            print(f"🔄 [ML Trigger] Background training started for Invoice {invoice_id} / Verified!")
            threading.Thread(
                target=classifier_service.train_one,
                args=(updated,),
                daemon=True,
            ).start()
    # ──────────────────────────────────────────────────────────────────────────

    return UpdateInvoiceResponse(
        status=200,
        message="Invoice updated successfully",
        invoice=InvoiceData(**updated),
    )


@router.post("/classifier/reset")
def reset_classifier(current_user: dict = Depends(get_current_user)):
    """
    Reset the invoice classifier and re-train it from the base synthetic dataset.
    Any incremental learning from verified invoices is discarded.
    """
    try:
        count = classifier_service.reset()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classifier reset failed: {e}")
    return {
        "status": 200,
        "message": f"Classifier reset and retrained on base dataset. {count} samples learned.",
    }


@router.delete("/{invoice_id}")
def delete_invoice_route(
    invoice_id: int,
    current_user: dict = Depends(get_current_user),
):
    row = get_invoice_by_id(invoice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if str(row["user_id"]) != str(current_user.get("sub", "")):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        deleted = delete_invoice(invoice_id)
    except SplitInvoiceGroupError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"status": 200, "message": f"Invoice INV-{invoice_id:03d} deleted successfully"}


@router.get("/{invoice_id}", response_model=UpdateInvoiceResponse)
def get_invoice(
    invoice_id: int,
    current_user: dict = Depends(get_current_user),
):
    row = get_invoice_by_id(invoice_id)
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if str(row["user_id"]) != str(current_user.get("sub", "")):
        raise HTTPException(status_code=403, detail="Access denied")
    return UpdateInvoiceResponse(
        status=200,
        message="Invoice fetched",
        invoice=InvoiceData(**row),
    )