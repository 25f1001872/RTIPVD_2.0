"""
RTIPVD — Source Package
Real-Time Illegal Parking Vehicle Detection

Modules:
    preprocessing   - Frame cleaning and enhancement
    detection       - YOLOv8 vehicle detection + ByteTrack tracking
    ego_motion      - Lane detection + camera ego-motion estimation
    analyzer        - Parking classification + adaptive calibration
    ocr             - License plate detection, reading, and validation
    visualization   - Frame rendering + stats overlay
    evidence        - Screenshot capture, GPS, map overlay
    database        - Local storage and backend sync
    geospatial      - Vehicle coordinate projection from camera GPS
    streaming       - Pi-to-laptop packet transport + GPS sync
    utils           - Shared utilities (logging, timing, validation)
"""

__version__ = "1.0.0"
__project__ = "RTIPVD"