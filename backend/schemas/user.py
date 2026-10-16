"""
The login's request and response shapes, and the rule every new password
follows.
"""

from pydantic import BaseModel, ConfigDict, field_validator

# For every new password (Register, Settings, the CLI). A password set before
# v1.1.0 that is shorter still logs in.
MIN_PASSWORD_LENGTH = 12
PASSWORD_TOO_SHORT = f"The password must be at least {MIN_PASSWORD_LENGTH} characters."
# bcrypt reads at most 72 bytes (User.set_password refuses more)
MAX_PASSWORD_BYTES = 72
PASSWORD_TOO_LONG = (f"The password can be at most {MAX_PASSWORD_BYTES} characters "
                     "(fewer with accented letters or symbols).")
NOT_TEXT = "The {} holds a character that isn't text (a lone surrogate): choose another."


def is_text(value: str) -> bool:
    """
    Whether `value` is real text. A JSON string can hold a lone surrogate
    ("\\ud800"), which no keyboard types and UTF-8 can't encode: bcrypt and
    SQLite would fail on it with a server error (#210).
    """
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def check_text(value: str, what: str) -> str:
    if not is_text(value):
        raise ValueError(NOT_TEXT.format(what))
    return value


def check_new_password(password: str) -> str:
    check_text(password, "password")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(PASSWORD_TOO_SHORT)
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(PASSWORD_TOO_LONG)
    return password


class UserBase(BaseModel):
    """
    Shared user fields. 'username' is the primary unique identifier.
    """
    username: str

    @field_validator("username")
    @classmethod
    def username_is_text(cls, v: str) -> str:
        return check_text(v, "username")


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
    username: str | None = None
    password: str | None = None
    current_password: str | None = None
    setup_code: str | None = None

    @field_validator("username", "password")
    @classmethod
    def not_blank(cls, v: str | None) -> str | None:
        """An empty value is refused rather than read as "keep the old one";
        leave the field out to keep it."""
        if v is not None and not v.strip():
            raise ValueError("can't be empty")
        return v

    @field_validator("username")
    @classmethod
    def username_is_text(cls, v: str | None) -> str | None:
        return v if v is None else check_text(v, "username")

    @field_validator("password")
    @classmethod
    def long_enough(cls, v: str | None) -> str | None:
        return v if v is None else check_new_password(v)


class UserRead(UserBase):
    """
    Schema for returning user data to clients.
    Includes the DB 'id' but excludes the hashed password.
    """
    id: int

    model_config = ConfigDict(from_attributes=True)