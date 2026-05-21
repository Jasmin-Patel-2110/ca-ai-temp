from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.database import init_db
from app.routers import auth
from app.routers import users
from app.routers import invoices

app = FastAPI(
    title="Invoice API",
    description="FastAPI backend with XAMPP MySQL",
    version="1.0.0",
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return 'message' instead of FastAPI's default 'detail' key."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": exc.status_code, "message": exc.detail},
    )

# CORS: allow LedgerAI frontend (ngrok + local dev)
_CORS_ORIGINS = [
    "https://ca-ai.kriit.com",
    "https://ca-ai-api.kriit.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Create DB + tables, apply migrations, and reindex invoices into ChromaDB."""
    init_db()

    # Load / pre-train the invoice classifier
    try:
        from app.services import classifier_service
        classifier_service.load()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Classifier load on startup failed (non-fatal): %s", exc
        )

    # Background-reindex all existing invoices so search works without re-uploading
    try:
        from app.models.invoice import get_all_invoices
        from app.services.rag_service import reindex_all
        existing = get_all_invoices()
        if existing:
            count = reindex_all(existing)
            import logging
            logging.getLogger(__name__).info(
                "RAG: reindexed %d existing invoice(s) on startup.", count
            )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "RAG reindex on startup failed (non-fatal): %s", exc
        )


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(invoices.router)


@app.get("/")
def health_check():
    return {"status": 200, "message": "Invoice API is running"}
