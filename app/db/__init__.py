"""Optional SQLAlchemy persistence for assistant conversations and evidence."""

from app.db.base import Base
from app.db.session import DatabaseSessionManager

__all__ = ["Base", "DatabaseSessionManager"]
