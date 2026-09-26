"""
backend/schemas/user.py

Defines the Pydantic schemas for user creation, update, and read.
No direct references to double-entry ledger fields are needed here,
since a user is simply the owner of multiple Accounts.

Refactored to use 'password' instead of 'password_hash' for creation,
so hashing happens behind the scenes in create_user().
"""

from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional

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

class UserUpdate(BaseModel):
    """
    Fields for updating an existing user record. All optional.
    If 'password' is provided, it will be hashed before saving.
    """
    username: Optional[str] = None
    password: Optional[str] = None

    @field_validator("username", "password")
    @classmethod
    def not_blank(cls, v: Optional[str]) -> Optional[str]:
        """An empty value used to be accepted (an empty password silently
        kept the old one); leave the field out to keep it."""
        if v is not None and not v.strip():
            raise ValueError("can't be empty")
        return v

class UserRead(UserBase):
    """
    Schema for returning user data to clients.
    Includes the DB 'id' but excludes the hashed password.
    """
    id: int

    model_config = ConfigDict(from_attributes=True)