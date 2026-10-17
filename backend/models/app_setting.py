"""
Small key/value store for app-wide settings (e.g. the tax timezone).
Created by migration 0002 (backend/migrations/versions/).
"""

from sqlalchemy import Column, String, delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)


def save_setting(db: Session, key: str, value: str | None) -> None:
    """
    Store a setting (None deletes it) in one statement, so two saves at once
    both land, the later one's value kept: a read, then an insert, would fail
    the second of two first saves on the key (UNIQUE constraint, #398).
    """
    if value is None:
        db.execute(delete(AppSetting).where(AppSetting.key == key))
    else:
        db.execute(sqlite_insert(AppSetting).values(key=key, value=value)
                   .on_conflict_do_update(index_elements=[AppSetting.key], set_={"value": value}))
    cached = db.identity_map.get(db.identity_key(AppSetting, key))
    if cached is not None:
        db.expire(cached)  # a later read in this session sees this save, not the row from before it
