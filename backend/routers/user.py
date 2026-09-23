# FILE: backend/routers/user.py

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Optional

from pydantic import BaseModel

# Pydantic schemas for user creation, reading, and updating
from backend.schemas.user import UserCreate, UserRead, UserUpdate

# Service functions that interact with the database
from backend.services.user import (
    get_all_users,
    get_user_by_username,
    create_user,
    update_user as update_user_service,
    delete_user as delete_user_service
)

# Database session provider
from backend.database import get_db

# User model (for the protected-route lookup)
from backend.models.user import User

# Create a FastAPI router instance with the "users" tag for API documentation
router = APIRouter(tags=["users"])

@router.post("/register", response_model=UserRead)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user: POST /api/users/register

    Enforces a single-user system:
    1. If any user exists, blocks registration (400 error).
    2. Checks if the username is taken (redundant in single-user system but kept for flexibility).
    3. Creates the user with a hashed password via create_user and returns the UserRead schema.

    Best Practices:
    - Password complexity: Ensure UserCreate schema or create_user enforces IRS Publication 1075 requirements.
    - Secure storage: Verify create_user uses strong hashing (e.g., bcrypt).
    """
    # Check if any user exists (single-user limit)
    existing_users = get_all_users(db)
    if existing_users:
        raise HTTPException(
            status_code=400,
            detail="Only one user allowed. A user already exists."
        )

    # Check if this username is taken (redundant but retained for clarity)
    existing_user = get_user_by_username(user.username, db)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Username already registered"
        )

    # Create the user record
    new_user = create_user(user, db)
    if not new_user:
        raise HTTPException(
            status_code=500,
            detail="Unable to create user"
        )

    return new_user

# Credentials every fresh install starts with (database.seed_defaults). While
# they are unchanged, knowing them grants nothing an attacker doesn't have.
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "password"


def _session_user_id(request: Request) -> int:
    """Logged-in user's id from the session cookie, or 401."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


def _require_self(user_id: int, request: Request) -> None:
    if _session_user_id(request) != user_id:
        raise HTTPException(status_code=403, detail="You can only change your own account.")


def _is_default_account(user: User) -> bool:
    return user.username == DEFAULT_USERNAME and user.verify_password(DEFAULT_PASSWORD)


@router.get("/setup-status")
def setup_status(db: Session = Depends(get_db)):
    """
    Public: whether the single account still has the shipped default login.
    Used by the first-run (Register) page before anyone is logged in.
    """
    users = get_all_users(db)
    return {"has_user": bool(users), "is_default": bool(users) and _is_default_account(users[0])}


class AccountReset(BaseModel):
    username: str
    password: str
    current_password: Optional[str] = None


@router.post("/reset-account")
def reset_account(payload: AccountReset, db: Session = Depends(get_db)):
    """
    First-run / re-registration: set new credentials and clear all
    transactions. Allowed only while the account still has the default login,
    or when current_password is the account's real password (verified here,
    server-side).
    """
    users = get_all_users(db)
    if not users:
        raise HTTPException(status_code=404, detail="No account to reset.")
    user = users[0]
    authorized = _is_default_account(user) or (
        payload.current_password is not None and user.verify_password(payload.current_password)
    )
    if not authorized:
        raise HTTPException(status_code=403, detail="Current password is incorrect.")
    if payload.username.strip().lower() == DEFAULT_USERNAME:
        raise HTTPException(status_code=400, detail="Choose a username other than 'admin'.")

    from backend.services.transaction import delete_all_transactions
    delete_all_transactions(db)
    update_user_service(user.id, UserUpdate(username=payload.username, password=payload.password), db)
    return {"detail": "Account reset. Log in with your new credentials."}


@router.get("/", response_model=List[UserRead])
def get_users(request: Request, db: Session = Depends(get_db)):
    """List users (logged-in only)."""
    _session_user_id(request)
    return get_all_users(db)


@router.patch("/{user_id}", response_model=UserRead)
def patch_user(user_id: int, user_data: UserUpdate, request: Request, db: Session = Depends(get_db)):
    """
    Change your own username and/or password: PATCH /api/users/{user_id}.
    Requires being logged in as that user.
    """
    _require_self(user_id, request)
    updated_user = update_user_service(user_id, user_data, db)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found.")
    return updated_user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Delete your own account: DELETE /api/users/{user_id}. Clears the session.
    Requires being logged in as that user.
    """
    _require_self(user_id, request)
    success = delete_user_service(user_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="User not found or cannot be deleted.")
    request.session.clear()
    return


@router.get("/protected")
def protected_route(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Not authenticated")

    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {"username": user.username}