"""
===========================================================
RTIPVD — License Plate Reader (OCR)
File: src/ocr/plate_reader.py
===========================================================

Reads license plate text from preprocessed plate crops using
EasyOCR, validates against Indian plate regex, and applies
temporal majority voting for accuracy.

Responsibilities:
    1. Initialize EasyOCR engine (GPU-accelerated on RTX 4050)
    2. Read text from enhanced plate crops
    3. Clean OCR output (remove hallucinated symbols)
    4. Validate against Indian license plate regex
    5. Maintain per-vehicle plate history (rolling window)
    6. Return the most-voted plate string across frames

WHY TEMPORAL VOTING?
    OCR on low-resolution, motion-blurred, or partially occluded
    plates is inherently noisy. A single frame might read:
        Frame 1: "MH12AB1234" ✓
        Frame 2: "MHI2ABI234" ✗ (OCR confused 1↔I)
        Frame 3: "MH12AB1234" ✓
        Frame 4: "MH12A81234" ✗ (OCR confused B↔8)
        Frame 5: "MH12AB1234" ✓

    By keeping the last 7 valid reads and returning the most
    common one, we get "MH12AB1234" with high confidence —
    even though individual frames had errors.

PERFORMANCE NOTE:
    OCR is triggered ONLY for vehicles already classified as
    PARKED. Moving vehicles never trigger OCR → saves ~80%
    of the compute that would otherwise be wasted on
    vehicles we don't care about.

Pipeline position:
    Parking Analyzer (PARKED) → Plate Detector → [THIS MODULE] → Display

Usage:
    from src.ocr.plate_reader import PlateReader

    reader = PlateReader(use_mock=False)
    plate_text = reader.read(frame, x1, y1, x2, y2, track_id)
"""

import re
from collections import Counter

from config.config import (
    USE_MOCK_OCR,
    OCR_LANGUAGE,
    OCR_USE_GPU,
    OCR_HISTORY_WINDOW,
    PLATE_REGEX_PATTERN,
)

from src.ocr.plate_detector import PlateDetector


class PlateReader:
    """
    Reads and validates license plate text using EasyOCR.

    Combines PlateDetector (crop + preprocess) with EasyOCR (text extraction),
    regex validation, and temporal majority voting into a single callable unit.

    Attributes:
        use_mock (bool): If True, returns fake plate without running OCR.
        _detector (PlateDetector): Handles crop extraction and preprocessing.
        _reader (easyocr.Reader): EasyOCR engine instance (loaded once).
        _pattern (re.Pattern): Compiled Indian license plate regex.
        _history (dict): Per-vehicle rolling window of valid plate reads.
                         Format: {track_id: [list of valid plate strings]}
        _max_history (int): Maximum reads to keep per vehicle.
    """

    # Default mock plate for testing (valid Indian format)
    _MOCK_PLATE = "MH12AB1234"

    # Placeholder text shown while OCR is still gathering reads
    _DETECTING_TEXT = "DETECTING..."

    def __init__(
        self,
        use_mock: bool = USE_MOCK_OCR,
        max_history: int = OCR_HISTORY_WINDOW,
    ):
        """
        Initialize the plate reader.

        Loads the EasyOCR model into GPU memory (takes 3-5 seconds on first run).
        Subsequent runs use cached weights from the weights/ directory.

        Args:
            use_mock: If True, skips EasyOCR loading entirely and returns
                      a fake plate string. Useful for:
                      - Testing the pipeline without GPU
                      - Debugging other modules faster
                      - CI/CD environments without GPU
            max_history: Size of the rolling window for temporal voting.
                         7 frames provides a good accuracy-latency tradeoff.
        """
        self.use_mock = use_mock
        self._max_history = max_history
        self._history = {}

        # Plate region detector and preprocessor
        self._detector = PlateDetector()

        # Compile regex once (reused for every OCR result)
        self._pattern = re.compile(PLATE_REGEX_PATTERN)

        # Initialize EasyOCR engine (heavy — loads neural network)
        self._reader = None
        if not self.use_mock:
            self._load_ocr_engine()

    def _load_ocr_engine(self) -> None:
        """
        Load the EasyOCR model into memory.

        Separated into its own method for:
            - Lazy loading (can be deferred until first read)
            - Clear error messages if easyocr is not installed
            - Easy mocking in unit tests
        """
        try:
            import easyocr

            print("[PlateReader] Loading EasyOCR model (first run downloads ~100MB)...")
            self._reader = easyocr.Reader(
                OCR_LANGUAGE,
                gpu=OCR_USE_GPU,
                model_storage_directory="weights",
                user_network_directory="weights",
                verbose=False,
            )
            print("[PlateReader] EasyOCR loaded successfully.")

        except ImportError:
            print("[PlateReader] WARNING: easyocr not installed. Falling back to mock mode.")
            self.use_mock = True

        except Exception as e:
            print(f"[PlateReader] WARNING: EasyOCR failed to load: {e}. Falling back to mock mode.")
            self.use_mock = True

    def read(
        self,
        frame,
        x1: int, y1: int,
        x2: int, y2: int,
        track_id: int,
    ) -> str:
        """
        Read the license plate of a vehicle.

        Full pipeline:
            1. Extract plate region from vehicle bbox (PlateDetector)
            2. Preprocess crop (grayscale + blur + CLAHE)
            3. Run EasyOCR text extraction
            4. Clean OCR output (strip non-alphanumeric characters)
            5. Validate against Indian plate regex
            6. Add valid reads to rolling history
            7. Return majority-voted plate string

        Args:
            frame: Full BGR frame from video (np.ndarray, HxWx3).
            x1, y1: Top-left corner of vehicle bounding box.
            x2, y2: Bottom-right corner of vehicle bounding box.
            track_id: Unique vehicle ID from ByteTrack.

        Returns:
            str: Best plate string from temporal voting.
                 Returns "DETECTING..." if no valid reads yet.
                 Returns the mock plate if use_mock=True.
        """
        # Initialize history for this vehicle if first encounter
        if track_id not in self._history:
            self._history[track_id] = []

        # ----------------------------------------------------------
        # Step 1: Extract plate region
        # ----------------------------------------------------------
        plate_crop = self._detector.extract(frame, x1, y1, x2, y2)

        # If crop failed (zero area), return best existing vote
        if plate_crop is None:
            return self._get_best_vote(track_id)

        # ----------------------------------------------------------
        # Step 2: Mock mode — skip OCR entirely
        # ----------------------------------------------------------
        if self.use_mock:
            self._add_to_history(track_id, self._MOCK_PLATE)
            return self._get_best_vote(track_id)

        # ----------------------------------------------------------
        # Step 3: Preprocess and run OCR
        # ----------------------------------------------------------
        enhanced_crop = self._detector.preprocess(plate_crop)

        # EasyOCR returns list of strings (detail=0 mode)
        # Example: ["MH12", "AB1234"] or ["MH12AB1234"]
        results = self._reader.readtext(enhanced_crop, detail=0)

        # ----------------------------------------------------------
        # Step 4: Clean and validate OCR output
        # ----------------------------------------------------------
        if results:
            # Concatenate all detected text fragments
            raw_text = "".join(results).replace(" ", "").upper()

            # Remove non-alphanumeric characters (OCR hallucinations)
            # Common hallucinations: dashes, dots, underscores, brackets
            clean_text = re.sub(r"[^A-Z0-9]", "", raw_text)

            # Validate against Indian license plate format
            if self._pattern.match(clean_text):
                self._add_to_history(track_id, clean_text)

        # ----------------------------------------------------------
        # Step 5: Return majority-voted result
        # ----------------------------------------------------------
        return self._get_best_vote(track_id)

    def _add_to_history(self, track_id: int, plate_text: str) -> None:
        """
        Add a valid plate read to the rolling history window.

        Maintains a fixed-size window (max_history). When the window
        is full, the oldest read is dropped (FIFO).

        Args:
            track_id: Vehicle track ID.
            plate_text: Validated plate string to add.
        """
        self._history[track_id].append(plate_text)

        # Enforce rolling window size
        if len(self._history[track_id]) > self._max_history:
            self._history[track_id].pop(0)

    def _get_best_vote(self, track_id: int) -> str:
        """
        Get the most frequently occurring plate string for a vehicle.

        Uses Counter.most_common() for O(n) frequency counting.
        If no valid reads exist yet, returns the detecting placeholder.

        Args:
            track_id: Vehicle track ID.

        Returns:
            str: Most common plate string, or "DETECTING..." if empty.
        """
        history = self._history.get(track_id, [])

        if not history:
            return self._DETECTING_TEXT

        # Return the most frequent plate string in the window
        return Counter(history).most_common(1)[0][0]

    def clear_track(self, track_id: int) -> None:
        """
        Remove plate history for a specific vehicle.

        Called when a track is purged from the parking analyzer
        (vehicle left the frame). Prevents unbounded memory growth.

        Args:
            track_id: Vehicle track ID to remove.
        """
        self._history.pop(track_id, None)

    def reset(self) -> None:
        """
        Clear all plate history for all vehicles.

        Call when switching video sources or after a scene cut.
        Does NOT reload the OCR engine (expensive).
        """
        self._history.clear()

    @property
    def active_tracks(self) -> int:
        """Number of vehicles with active plate history."""
        return len(self._history)

    def __repr__(self) -> str:
        """Readable string representation for debugging."""
        mode = "MOCK" if self.use_mock else "EASYOCR"
        return (
            f"PlateReader("
            f"mode={mode}, "
            f"history_window={self._max_history}, "
            f"active_tracks={self.active_tracks})"
        )