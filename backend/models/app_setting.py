"""
backend/models/app_setting.py

Small key/value store for app-wide settings (e.g. the tax timezone).
A new table: create_tables() adds it to existing databases automatically.
"""

from sqlalchemy import Column, String

from backend.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
