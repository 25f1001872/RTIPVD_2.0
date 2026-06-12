"""
RTIPVD — Evidence Module [Phase 2]
Handles violation evidence capture:
    - Screenshot capture (frame at time of violation)
    - GPS tagging (camera coordinates)
    - Map overlay (Google Maps / OpenStreetMap)
"""

from src.evidence.gps_tagger import GPSTagger
from src.evidence.violation_service import ViolationService

__all__ = [
    "GPSTagger",
    "ViolationService",
]