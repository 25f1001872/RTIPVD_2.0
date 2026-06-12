"""
RTIPVD — Database Module [Phase 2]
Handles violation data storage and retrieval:
    - License plate (primary key)
    - Violation timestamp
    - Frame screenshot path
    - GPS coordinates
    - Duration of illegal parking
"""

from src.database.backend_client import BackendClient
from src.database.db_manager import DatabaseManager
from src.database.models import GPSFix, ViolationRecord

__all__ = [
    "BackendClient",
    "DatabaseManager",
    "GPSFix",
    "ViolationRecord",
]