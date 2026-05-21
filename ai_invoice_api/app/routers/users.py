from fastapi import APIRouter, HTTPException, Depends
from app.schemas.user import UpdateProfileRequest, ProfileResponse, UserProfile, AllUsersResponse
from app.models.user import get_all_users, get_user_by_id, update_user
from app.dependencies import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])


def _to_profile(row: dict) -> UserProfile:
    return UserProfile(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        company_name=row["company_name"],
        gst_number=row.get("gst_number"),
        address=row.get("address"),
        mobile_number=row.get("mobile_number"),
    )


@router.get("", response_model=AllUsersResponse)
def list_users(current_user: dict = Depends(get_current_user)):
    """Return all registered users. JWT token required."""
    rows = get_all_users()
    return AllUsersResponse(
        status=200,
        message="Users fetched",
        users=[_to_profile(r) for r in rows],
    )


@router.get("/{user_id}", response_model=ProfileResponse)
def get_profile(
    user_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Fetch any user's profile by ID. JWT token required."""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return ProfileResponse(
        status=200,
        message="Profile fetched",
        userdetails=_to_profile(user),
    )


@router.patch("/{user_id}", response_model=ProfileResponse)
def update_profile(
    user_id: int,
    payload: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update profile fields by user ID. JWT token required.
    Only the account owner (token sub == user_id) may update."""
    if str(current_user.get("sub")) != str(user_id):
        raise HTTPException(status_code=403, detail="You can only update your own profile")

    # Build dict of only the fields that were explicitly provided
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    updated = update_user(user_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")

    return ProfileResponse(
        status=200,
        message="Updated Profile",
        userdetails=_to_profile(updated),
    )
