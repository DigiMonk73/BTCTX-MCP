"""
backend/models/app_setting.py

Small key/value store for app-wide settings (e.g. the tax timezone).
Created by migration 0002 (backend/migrations/versions/).
"""

from sqlalchemy import Column, String

from backend.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
