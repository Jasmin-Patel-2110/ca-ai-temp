import logging
import os
import re
import shutil
import uuid
from pathlib import Path
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError

from app.config import (
    AWS_ACCESS_KEY_ID,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY,
    DOCUMENT_STORAGE_DIR,
    S3_BUCKET_NAME,
)

logger = logging.getLogger(__name__)


def _client():
    """Return an S3 client, allowing IAM credentials when explicit keys are absent."""
    kwargs = {"region_name": AWS_REGION}
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        kwargs.update(
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        )
    return boto3.client("s3", **kwargs)


def _safe_folder_part(email: str) -> str:
    """Sanitize email for use in an object key."""
    if not email or not isinstance(email, str):
        return "unknown"
    return re.sub(r"[^a-z0-9._-]", "_", email.strip().lower())[:100]


def _safe_filename(filename: str) -> str:
    name = os.path.basename(filename or "invoice")
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or "invoice"


def _local_path(key: str) -> Path:
    root = Path(DOCUMENT_STORAGE_DIR).resolve()
    path = (root / key).resolve()
    if root != path and root not in path.parents:
        raise ValueError("Invalid document key")
    return path


def _local_url(key: str) -> str:
    return f"/documents/{quote(key)}"


def upload_to_s3(file_obj, filename: str, user_id: str = "", email: str = "") -> tuple[str, str]:
    """Store a document in S3, or on local persistent storage when S3 is unset."""
    folder = _safe_folder_part(email) if email else "unknown"
    prefix = f"invoices/{user_id}_{folder}" if user_id else "invoices"
    key = f"{prefix}/{uuid.uuid4()}_{_safe_filename(filename)}"

    if S3_BUCKET_NAME:
        _client().upload_fileobj(
            file_obj,
            S3_BUCKET_NAME,
            key,
            ExtraArgs={"ServerSideEncryption": "AES256"},
        )
        url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"
        return key, url

    path = _local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(file_obj, "seek"):
        file_obj.seek(0)
    with path.open("wb") as destination:
        shutil.copyfileobj(file_obj, destination)
    return key, _local_url(key)


def download_from_s3(s3_key: str) -> bytes:
    """Download file contents from configured document storage."""
    if not s3_key or not s3_key.strip():
        raise ValueError("download_from_s3: empty s3_key")
    if not S3_BUCKET_NAME:
        return _local_path(s3_key).read_bytes()
    response = _client().get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
    return response["Body"].read()


def delete_from_s3(s3_key: str) -> bool:
    """Delete a document from configured storage."""
    if not s3_key or not s3_key.strip():
        logger.warning("delete_from_s3: empty s3_key, skipping")
        return False
    if not S3_BUCKET_NAME:
        try:
            _local_path(s3_key).unlink(missing_ok=True)
            return True
        except OSError as exc:
            logger.error("Local document delete failed: key=%s error=%s", s3_key, exc)
            return False
    try:
        _client().delete_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        logger.info("delete_from_s3: deleted key=%s", s3_key)
        return True
    except ClientError as exc:
        logger.error(
            "delete_from_s3 failed: key=%s bucket=%s error=%s",
            s3_key,
            S3_BUCKET_NAME,
            exc.response.get("Error", {}).get("Code", str(exc)),
        )
        return False


def generate_presigned_url(s3_key: str, expiry_seconds: int = 3600) -> str:
    """Generate a document URL for configured storage."""
    if not S3_BUCKET_NAME:
        return _local_url(s3_key)
    try:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET_NAME, "Key": s3_key},
            ExpiresIn=expiry_seconds,
        )
    except ClientError as exc:
        raise RuntimeError(f"Could not generate pre-signed URL: {exc}") from exc
