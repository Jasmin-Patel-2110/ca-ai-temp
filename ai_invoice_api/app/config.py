import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", "3306"))
DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME     = os.getenv("DB_NAME", "invoice_api")
SECRET_KEY  = os.getenv("SECRET_KEY", "development-only-change-me")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
DOCUMENT_STORAGE_DIR = os.path.abspath(
    os.getenv(
        "DOCUMENT_STORAGE_DIR",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "documents"),
    )
)

if os.getenv("ENVIRONMENT") == "production" and SECRET_KEY == "development-only-change-me":
    raise RuntimeError("SECRET_KEY must be set when ENVIRONMENT=production")

# AWS S3
AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION            = os.getenv("AWS_REGION", "ap-south-1")
S3_BUCKET_NAME        = os.getenv("S3_BUCKET_NAME", "")
