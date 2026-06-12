"""
===========================================================
RTIPVD — Vehicle Tracker
File: src/detection/vehicle_tracker.py
===========================================================

Handles multi-object tracking using ByteTrack on top of
the YOLOv8 detections from VehicleDetector.

Responsibilities:
    1. Run YOLOv8 + ByteTrack in streaming mode
    2. Assign persistent track IDs across frames
    3. Provide frame-by-frame results as a generator

Separation from VehicleDetector allows:
    - Swapping tracker (ByteTrack → BoT-SORT, StrongSORT)
    - Swapping detector (YOLOv8 → YOLOv9, RT-DETR)
    - Independent testing of detection vs tracking logic

Pipeline position:
    PREPROCESSED FRAME → Detector → [THIS MODULE] → Analyzer

Usage:
    from src.detection.vehicle_detector import VehicleDetector
    from src.detection.vehicle_tracker import VehicleTracker

    detector = VehicleDetector(model_path="weights/best.pt")
    tracker = VehicleTracker(detector, tracker_config="config/bytetrack.yaml")

    for result in tracker.stream(source="data/videos/d1.mp4"):
        boxes = result.boxes
        frame = result.orig_img
"""

from src.detection.vehicle_detector import VehicleDetector


class VehicleTracker:
    """
    ByteTrack-based multi-object tracker built on top of VehicleDetector.

    ByteTrack tracks objects by matching detections across frames using
    IoU (Intersection over Union). Unlike DeepSORT, it does NOT require
    a separate Re-ID neural network — making it faster and lighter.

    Key feature: ByteTrack uses BOTH high-confidence and low-confidence
    detections for matching. This means partially occluded vehicles
    (low confidence) still maintain their track IDs instead of being
    lost and re-assigned new IDs.

    Attributes:
        detector (VehicleDetector): The detection model wrapper.
        tracker_config (str): Path to ByteTrack YAML configuration.
        _model (YOLO): Direct reference to the YOLO model for tracking calls.
    """

    def __init__(self, detector: VehicleDetector, tracker_config: str):
        """
        Initialize the tracker with a detector and tracker config.

        Args:
            detector: VehicleDetector instance (owns the YOLO model).
            tracker_config: Path to the ByteTrack YAML config file.
                            Example: "config/bytetrack.yaml"
        """
        self.detector = detector
        self.tracker_config = tracker_config

        # Get the underlying YOLO model from the detector.
        # model.track() is an ultralytics method that runs
        # detection + tracking in a single call.
        self._model = detector.get_model()

    def stream(
        self,
        source: str,
        conf: float = 0.3,
        iou: float = 0.5,
        imgsz: int = 640,
        verbose: bool = False,
    ):
        """
        Start tracking vehicles in a video source (streaming mode).

        Returns a generator that yields one result object per frame.
        Each result contains:
            - result.orig_img: Original frame (numpy array)
            - result.boxes: Detected bounding boxes with:
                - boxes.xyxy: [x1, y1, x2, y2] coordinates
                - boxes.id: Track IDs (persistent across frames)
                - boxes.cls: Class IDs
                - boxes.conf: Confidence scores

        Args:
            source: Path to video file or camera index.
                    Examples: "data/videos/d1.mp4", 0 (webcam)
            conf: Minimum confidence threshold for detections.
                  Lower = more detections but more false positives.
                  0.3 is a good balance for vehicle detection.
            iou: IoU threshold for Non-Maximum Suppression (NMS).
                 Lower = more aggressive suppression of overlapping boxes.
                 0.5 is standard for vehicle detection.
            imgsz: Input image size for YOLO inference.
                   640 is default. Use 1280 for better accuracy on
                   small/distant vehicles (at the cost of speed).
            verbose: If True, ultralytics prints per-frame logs.
                     Set False for clean output.

        Yields:
            ultralytics.engine.results.Results: Detection + tracking
            result for each frame. Access via result.boxes, result.orig_img.

        Example:
            >>> for result in tracker.stream("video.mp4"):
            ...     for box in result.boxes:
            ...         track_id = int(box.id[0]) if box.id is not None else -1
            ...         x1, y1, x2, y2 = map(int, box.xyxy[0])
        """
        return self._model.track(
            source=source,
            tracker=self.tracker_config,
            stream=True,
            persist=True,
            conf=conf,
            iou=iou,
            imgsz=imgsz,
            verbose=verbose,
            device=self.detector.device,
        )

    def is_vehicle(self, cls_id: int) -> bool:
        """
        Convenience proxy — delegates to detector's vehicle check.

        Allows calling tracker.is_vehicle() without needing
        a separate reference to the detector in the main loop.

        Args:
            cls_id: YOLO class ID to check.

        Returns:
            bool: True if the class is a vehicle.
        """
        return self.detector.is_vehicle(cls_id)

    def get_label(self, cls_id: int) -> str:
        """
        Convenience proxy — delegates to detector's label lookup.

        Args:
            cls_id: YOLO class ID.

        Returns:
            str: Human-readable class name.
        """
        return self.detector.get_label(cls_id)

    def __repr__(self) -> str:
        """Readable string representation for debugging."""
        return (
            f"VehicleTracker("
            f"detector={self.detector}, "
            f"config='{self.tracker_config}')"
        )