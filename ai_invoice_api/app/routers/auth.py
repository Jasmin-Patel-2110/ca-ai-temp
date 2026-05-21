from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Header
from app.schemas.user import (
    RegisterRequest, RegisterResponse, UserDetails,
    LoginRequest, LoginResponse,
    LogoutResponse,
)
from app.models.user import find_user_by_email, create_user
from app.models.token import blacklist_token, purge_expired_tokens
from app.utils.security import (
    hash_password, verify_password,
    create_access_token, decode_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=RegisterResponse)
def register(payload: RegisterRequest):
    if find_user_by_email(payload.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = create_user(
        name=payload.name,
        company_name=payload.company_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )

    return RegisterResponse(
        status=200,
        message="Registered Success",
        userdetails=UserDetails(
            name=new_user["name"],
            company_name=new_user["company_name"],
            email=new_user["email"],
        ),
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    user = find_user_by_email(payload.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({
        "sub":            str(user["id"]),
        "email":          user["email"],
        "name":           user["name"],
        "company_name":   user.get("company_name", ""),
        "gst_number":     user.get("gst_number", ""),
        "address":        user.get("address", ""),
        "mobile_number":  user.get("mobile_number", ""),
    })

    return LoginResponse(
        status=200,
        message="Successful Login",
        token=token,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(authorization: str = Header(...)):
    """Revoke the current JWT token. Token will be invalid immediately."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format. Use: Bearer <token>")

    token = authorization.split(" ", 1)[1]

    # Decode to validate and get expiry time
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Store token in blacklist until its natural expiry
    exp_ts = payload.get("exp")
    if exp_ts:
        expired_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
    else:
        expired_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    blacklist_token(token, expired_at)

    # Remove already-expired tokens to keep the table clean
    purge_expired_tokens()

    return LogoutResponse(status=200, message="Logged out successfully")
