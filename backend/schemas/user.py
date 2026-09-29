"""
The login's request and response shapes, and the rule every new password
follows.
"""

from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional

# For every new password (Register, Settings, the CLI). A password set before
# v1.1.0 that is shorter still logs in.
MIN_PASSWORD_LENGTH = 12
PASSWORD_TOO_SHORT = f"The password must be at least {MIN_PASSWORD_LENGTH} characters."


def check_new_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(PASSWORD_TOO_SHORT)
    return password


class UserBase(BaseModel):
    """
    Shared user fields. 'username' is the primary unique identifier.
    """
    username: str


class UserCreate(UserBase):
    """
    For creating a new user. The user supplies a raw 'password'
    which will be hashed by the service layer before storing.
    """
    password: str

    @field_validator("password")
    @classmethod
    def long_enough(cls, v: str) -> str:
        return check_new_password(v)


class UserUpdate(BaseModel):
    """
    Fields for updating an existing user record. All optional.
    If 'password' is provided, it will be hashed before saving.
    current_password (PATCH /api/users/{id}) is checked by the router.
    setup_code: while the account has the default login (first_run.py).
    """
    username: Optional[str] = None
    password: Optional[str] = None
    current_password: Optional[str] = None
    setup_code: Optional[str] = None

    @field_validator("username", "password")
    @classmethod
    def not_blank(cls, v: Optional[str]) -> Optional[str]:
        """An empty value is refused rather than read as "keep the old one";
        leave the field out to keep it."""
        if v is not None and not v.strip():
            raise ValueError("can't be empty")
        return v

    @field_validator("password")
    @classmethod
    def long_enough(cls, v: Optional[str]) -> Optional[str]:
        return v if v is None else check_new_password(v)


class UserRead(UserBase):
    """
    Schema for returning user data to clients.
    Includes the DB 'id' but excludes the hashed password.
    """
    id: int

    model_config = ConfigDict(from_attributes=True)