from app.database import get_connection

_PROFILE_COLS = "id, name, company_name, email, gst_number, address, mobile_number, created_at"


def find_user_by_email(email: str) -> dict | None:
    """Return user row as dict if email exists, else None."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, company_name, email, hashed_password, created_at, "
                "gst_number, address, mobile_number "
                "FROM users WHERE email = %s LIMIT 1",
                (email,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def get_all_users() -> list[dict]:
    """Return all user profiles ordered by id."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_PROFILE_COLS} FROM users ORDER BY id ASC")
            return cur.fetchall()
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    """Return full profile row for a given user ID, or None."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_PROFILE_COLS} FROM users WHERE id = %s LIMIT 1",
                (user_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def create_user(name: str, company_name: str, email: str, hashed_password: str) -> dict:
    """Insert a new user row and return the inserted record."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (name, company_name, email, hashed_password) "
                "VALUES (%s, %s, %s, %s)",
                (name, company_name, email, hashed_password),
            )
            conn.commit()
            new_id = cur.lastrowid
            cur.execute(
                "SELECT id, name, company_name, email, created_at "
                "FROM users WHERE id = %s",
                (new_id,),
            )
            return cur.fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_user(user_id: int, fields: dict) -> dict | None:
    """Update only the provided fields for the given user and return the updated row.

    `fields` is a dict of column_name -> new_value (only updatable profile fields).
    Returns None if user not found.
    """
    if not fields:
        return get_user_by_id(user_id)

    allowed = {"name", "email", "company_name", "gst_number", "address", "mobile_number"}
    safe_fields = {k: v for k, v in fields.items() if k in allowed}
    if not safe_fields:
        return get_user_by_id(user_id)

    set_clause = ", ".join(f"{col} = %s" for col in safe_fields)
    values = list(safe_fields.values()) + [user_id]

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE users SET {set_clause} WHERE id = %s",
                values,
            )
            conn.commit()
            cur.execute(
                f"SELECT {_PROFILE_COLS} FROM users WHERE id = %s LIMIT 1",
                (user_id,),
            )
            return cur.fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
