import uuid
import logging
import boto3
from botocore.exceptions import ClientError
from app.config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, S3_BUCKET_NAME

logger = logging.getLogger(__name__)


def _client():
    """Return a configured boto3 S3 client."""
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def _safe_folder_part(email: str) -> str:
    """Sanitize email for use in S3 key (no @ or spaces)."""
    if not email or not isinstance(email, str):
        return "unknown"
    return email.strip().lower().replace("@", "_").replace(" ", "_")[:100]


def upload_to_s3(file_obj, filename: str, user_id: str = "", email: str = "") -> tuple[str, str]:
    """Upload a file-like object to S3 under path invoices/{user_id}_{email}/.

    Returns:
        (s3_key, public_url)
    """
    folder = _safe_folder_part(email) if email else "unknown"
    if user_id:
        prefix = f"invoices/{user_id}_{folder}"
    else:
        prefix = "invoices"
    key = f"{prefix}/{uuid.uuid4()}_{filename}"
    _client().upload_fileobj(
        file_obj,
        S3_BUCKET_NAME,
        key,
        ExtraArgs={"ServerSideEncryption": "AES256"},
    )
    url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"
    return key, url


def download_from_s3(s3_key: str) -> bytes:
    """Download file contents from S3. Returns raw bytes."""
    if not s3_key or not s3_key.strip():
        raise ValueError("download_from_s3: empty s3_key")
    resp = _client().get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
    return resp["Body"].read()


def delete_from_s3(s3_key: str) -> bool:
    """Delete an object from S3. Returns True if deleted, False if failed."""
    if not s3_key or not s3_key.strip():
        logger.warning("delete_from_s3: empty s3_key, skipping")
        return False
    if not S3_BUCKET_NAME:
        logger.error("delete_from_s3: S3_BUCKET_NAME not configured")
        return False
    try:
        _client().delete_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        logger.info("delete_from_s3: deleted key=%s", s3_key)
        return True
    except ClientError as e:
        logger.error(
            "delete_from_s3 failed: key=%s bucket=%s error=%s",
            s3_key,
            S3_BUCKET_NAME,
            e.response.get("Error", {}).get("Code", str(e)),
        )
        return False


def generate_presigned_url(s3_key: str, expiry_seconds: int = 3600) -> str:
    """Generate a temporary pre-signed download URL for an S3 object."""
    try:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET_NAME, "Key": s3_key},
            ExpiresIn=expiry_seconds,
        )
    except ClientError as e:
        raise RuntimeError(f"Could not generate pre-signed URL: {e}")
