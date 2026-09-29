"""The login's storage: find, create and change the user."""

from __future__ import annotations

from sqlalchemy.orm import Session
from backend.models.user import User
from backend.schemas.user import UserCreate, UserUpdate


def get_all_users(db: Session) -> list[User]:
    """Every user (BitcoinTX has at most one)."""
    return db.query(User).all()


def get_user_by_username(username: str, db: Session) -> User | None:
    """The user with that name, or None."""
    return db.query(User).filter(User.username == username).first()


def create_user(user_data: UserCreate, db: Session) -> User | None:
    """A new user with the password's hash; None when the name is taken."""
    if get_user_by_username(user_data.username, db):
        return None

    new_user = User(username=user_data.username)
    new_user.set_password(user_data.password)

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


def update_user(user_id: int, user_data: UserUpdate, db: Session) -> User | None:
    """The user with a new username or password (None when not found)."""
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        return None

    if user_data.username is not None:
        db_user.username = user_data.username

    if user_data.password:
        db_user.set_password(user_data.password)

    db.commit()
    db.refresh(db_user)
    return db_user
