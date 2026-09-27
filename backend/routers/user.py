# FILE: backend/routers/user.py

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List, Optional

from pydantic import BaseModel, field_validator

# Pydantic schemas for user creation, reading, and updating
from backend.schemas.user import UserCreate, UserRead, UserUpdate, check_new_password
from backend.services import first_run, login_throttle

# Service functions that interact with the database
from backend.services.user import (
    get_all_users,
    get_user_by_username,
    create_user,
    update_user as update_user_service,
)
from backend.session_auth import require_login, start_session

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

WRONG_PASSWORD = "Current password is incorrect."


def _session_user_id(request: Request, db: Session) -> int:
    """Logged-in user's id from the session cookie, or 401."""
    return require_login(request, db)


def _require_self(user_id: int, request: Request, db: Session) -> None:
    if _session_user_id(request, db) != user_id:
        raise HTTPException(status_code=403, detail="You can only change your own account.")


def _authorize_change(user: User, request: Request, current_password: Optional[str],
                      setup_code: Optional[str], default_login_ok: bool) -> None:
    """
    May the login of `user` be changed? With its current password, or, while
    it still has the default login and default_login_ok, by knowing that
    (plus the setup code outside the Mac app: first_run.py). Failures count
    towards the login throttle (login_throttle.py).
    """
    login_throttle.check(request)
    is_default = first_run.is_default_account(user)
    if is_default and first_run.code_required():
        if not first_run.check_code(setup_code):
            login_throttle.failed(request)
            detail = first_run.CODE_WRONG if setup_code else first_run.CODE_REQUIRED
            raise HTTPException(status_code=403, detail=detail)
    if not (is_default and default_login_ok) and (
        current_password is None or not user.verify_password(current_password)
    ):
        login_throttle.failed(request)
        raise HTTPException(status_code=403, detail=WRONG_PASSWORD)
    login_throttle.succeeded(request)


@router.get("/setup-status")
def setup_status(db: Session = Depends(get_db)):
    """
    Public: whether the single account still has the shipped default login,
    and whether claiming it needs the first-run setup code (never the code).
    Used by the first-run (Register) page before anyone is logged in.
    """
    users = get_all_users(db)
    is_default = bool(users) and first_run.is_default_account(users[0])
    return {
        "has_user": bool(users),
        "is_default": is_default,
        "setup_code_required": is_default and first_run.code_required(),
    }


class AccountReset(BaseModel):
    username: str
    password: str
    current_password: Optional[str] = None
    setup_code: Optional[str] = None

    @field_validator("username", "password")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("can't be empty")
        return v

    @field_validator("password")
    @classmethod
    def long_enough(cls, v: str) -> str:
        return check_new_password(v)


@router.post("/reset-account")
def reset_account(payload: AccountReset, request: Request, db: Session = Depends(get_db)):
    """
    First-run / re-registration: set new credentials and clear all
    transactions. Allowed while the account still has the default login
    (with the setup code, outside the Mac app), or when current_password is
    the account's real password (verified here, server-side). Throttled like
    the login.
    """
    users = get_all_users(db)
    if not users:
        raise HTTPException(status_code=404, detail="No account to reset.")
    user = users[0]
    _authorize_change(user, request, payload.current_password, payload.setup_code, default_login_ok=True)
    if payload.username.strip().lower() == first_run.DEFAULT_USERNAME:
        raise HTTPException(status_code=400, detail="Choose a username other than 'admin'.")

    from backend.services.transaction import delete_all_transactions
    delete_all_transactions(db)
    update_user_service(user.id, UserUpdate(username=payload.username, password=payload.password), db)
    first_run.clear_code()
    return {"detail": "Account reset. Log in with your new credentials."}


@router.get("/", response_model=List[UserRead])
def get_users(request: Request, db: Session = Depends(get_db)):
    """List users (logged-in only)."""
    _session_user_id(request, db)
    return get_all_users(db)


@router.patch("/{user_id}", response_model=UserRead)
def patch_user(user_id: int, user_data: UserUpdate, request: Request, db: Session = Depends(get_db)):
    """
    Change your own username and/or password: PATCH /api/users/{user_id}.
    Requires being logged in as that user and current_password (so a
    session left open can't take over the login); while the account has the
    default login, also the setup code (first_run.py).
    """
    _require_self(user_id, request, db)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    _authorize_change(user, request, user_data.current_password, user_data.setup_code, default_login_ok=False)
    updated_user = update_user_service(user_id, user_data, db)
    # Other sessions end with the old password; this one carries on.
    start_session(request, updated_user)
    if not first_run.is_default_account(updated_user):
        first_run.clear_code()
    return updated_user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    """
    BitcoinTX has exactly one account, which owns the ledger's accounts, so
    it can't be deleted (this used to fail with a 500). Settings → Reset
    Username & Password changes the login; reset-account starts over.
    """
    _require_self(user_id, request, db)
    raise HTTPException(
        status_code=409,
        detail="The account can't be deleted. Change its username and password in Settings instead.",
    )


@router.get("/protected")
def protected_route(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Not authenticated")

    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {"username": user.username}