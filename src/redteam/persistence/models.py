"""Declarative base shared by persistence models and migrations."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Metadata root for the SQLite schema."""
