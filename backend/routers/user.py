"""
The one login: first registration, the first-run status and account reset,
and changes to the logged-in user's name and password.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from pydantic import BaseModel, field_validator

from backend.schemas.user import UserCreate, UserRead, UserUpdate, check_new_password, check_text
from backend.services import first_run, login_throttle, wipe
from backend.services.desktop import is_desktop
from backend.services.user import (
    get_all_users,
    get_user_by_username,
    create_user,
    update_user as update_user_service,
)
from backend.session_auth import require_login, start_session
from backend.database import get_db
from backend.models.user import User

router = APIRouter(tags=["users"])


@router.post("/register", response_model=UserRead)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    """Create the login, when there is none yet (BitcoinTX has one user)."""
    existing_users = get_all_users(db)
    if existing_users:
        raise HTTPException(
            status_code=400,
            detail="Only one user allowed. A user already exists."
        )

    existing_user = get_user_by_username(user.username, db)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Username already registered"
        )

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


def _authorize_change(user: User, request: Request, db: Session, current_password: str | None,
                      setup_code: str | None, default_login_ok: bool) -> None:
    """
    May the login of `user` be changed? With its current password, or, while
    it still has the default login and default_login_ok, by knowing that;
    while it has the default login, also with the setup code (first_run.py).
    Each try counts towards the login throttle until it's right
    (login_throttle.py).
    """
    login_throttle.check(request, db)
    is_default = first_run.is_default_account(user)
    if is_default and not first_run.check_code(setup_code):
        raise HTTPException(status_code=403, detail=first_run.code_refused(setup_code))
    if not (is_default and default_login_ok) and (
        current_password is None or not user.verify_password(current_password)
    ):
        raise HTTPException(status_code=403, detail=WRONG_PASSWORD)
    login_throttle.succeeded(request)


@router.get("/setup-status")
def setup_status(db: Session = Depends(get_db)):
    """
    Public: whether the single account still has the shipped default login,
    and so whether logging in with it and claiming it need the first-run
    setup code (never the code), and whether this is the Mac app, which
    keeps the code in its data folder rather than a server's log (its pages
    in a browser have no window to ask). Used by the Login and Register
    pages before anyone is logged in.
    """
    users = get_all_users(db)
    is_default = bool(users) and first_run.is_default_account(users[0])
    return {
        "has_user": bool(users),
        "is_default": is_default,
        "setup_code_required": is_default,
        "desktop": is_desktop(),
    }


class AccountReset(BaseModel):
    username: str
    password: str
    current_password: str | None = None
    setup_code: str | None = None
    # "DELETE", typed in the dialog, when the ledger has transactions (#256),
    # and what the dialog showed: how many, over which tax years (#377)
    confirm: str | None = None
    transactions: int | None = None
    first_year: int | None = None
    last_year: int | None = None

    @field_validator("username", "password")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("can't be empty")
        return v

    @field_validator("username")
    @classmethod
    def username_is_text(cls, v: str) -> str:
        return check_text(v, "username")

    @field_validator("password")
    @classmethod
    def long_enough(cls, v: str) -> str:
        return check_new_password(v)


@router.post("/reset-account")
def reset_account(payload: AccountReset, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    First-run / re-registration: set new credentials and clear all
    transactions. Allowed while the account still has the default login
    (with the setup code), or when current_password is
    the account's real password (verified here, server-side). Throttled like
    the login. With transactions to delete, only with confirm=DELETE (for
    what the dialog showed, when given: #377), asked once the code or
    password is right: otherwise 409 says what would go, and nothing
    changes. A copy of the database comes first (#256), and the delete and
    the new login are one save: a failure leaves both as they were.
    """
    users = get_all_users(db)
    if not users:
        raise HTTPException(status_code=404, detail="No account to reset.")
    user = users[0]
    _authorize_change(user, request, db, payload.current_password, payload.setup_code, default_login_ok=True)
    if payload.username.strip().lower() == first_run.DEFAULT_USERNAME:
        raise HTTPException(status_code=400, detail="Choose a username other than 'admin'.")

    new_login = UserUpdate(username=payload.username, password=payload.password)
    shown = payload.model_dump(include={"transactions", "first_year", "last_year"})
    refused = wipe.delete_all(db, payload.confirm, shown,
                              save_with=lambda session: update_user_service(user.id, new_login, session))
    if refused is not None:
        return refused
    first_run.clear_code()
    login_throttle.remember_device(response, user)
    return {"detail": "Account reset. Log in with your new credentials."}


@router.get("/", response_model=list[UserRead])
def get_users(request: Request, db: Session = Depends(get_db)):
    """List users (logged-in only)."""
    _session_user_id(request, db)
    return get_all_users(db)


@router.patch("/{user_id}", response_model=UserRead)
def patch_user(user_id: int, user_data: UserUpdate, request: Request, response: Response,
               db: Session = Depends(get_db)):
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
    _authorize_change(user, request, db, user_data.current_password, user_data.setup_code, default_login_ok=False)
    updated_user = update_user_service(user_id, user_data, db)
    # Other sessions end with the old password; this one carries on.
    start_session(request, updated_user, db)
    login_throttle.remember_device(response, updated_user)
    if not first_run.is_default_account(updated_user):
        first_run.clear_code()
    return updated_user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    """
    BitcoinTX has exactly one account, which owns the ledger's accounts, so
    it can't be deleted (409, not a server error). Settings → Reset
    Username & Password changes the login; reset-account starts over.
    """
    _require_self(user_id, request, db)
    raise HTTPException(
        status_code=409,
        detail="The account can't be deleted. Change its username and password in Settings instead.",
    )
