from datetime import datetime, timezone
from app.database import get_connection


def blacklist_token(token: str, expired_at: datetime) -> None:
    """Add a token to the blacklist so it cannot be used again."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO token_blacklist (token, expired_at) VALUES (%s, %s)",
                (token, expired_at.replace(tzinfo=None)),  # store as naive datetime
            )
        conn.commit()
    finally:
        conn.close()


def is_token_blacklisted(token: str) -> bool:
    """Return True if the token has been revoked (exists in blacklist)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM token_blacklist WHERE token = %s LIMIT 1",
                (token,),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def purge_expired_tokens() -> None:
    """Delete tokens whose expiry has already passed — keeps the table small."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM token_blacklist WHERE expired_at < %s",
                (datetime.utcnow(),),
            )
        conn.commit()
    finally:
        conn.close()
