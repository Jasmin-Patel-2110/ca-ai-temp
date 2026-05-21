from typing import Optional
from fastapi import Header, HTTPException
from app.utils.security import decode_access_token
from app.models.token import is_token_blacklisted


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """FastAPI dependency — validates Bearer JWT, checks blacklist, returns decoded payload.

    Usage in a route:
        @router.get("/protected")
        def protected(current_user: dict = Depends(get_current_user)):
            ...
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header is missing")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format. Use: Bearer <token>")

    token = authorization.split(" ", 1)[1]

    # Reject tokens that have been explicitly revoked via /auth/logout
    if is_token_blacklisted(token):
        raise HTTPException(status_code=401, detail="Token has been revoked. Please log in again.")

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload  # {"sub": "1", "email": "...", "name": "..."}
