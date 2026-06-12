"""
===========================================================
RTIPVD — Performance Timer
File: src/utils/timer.py
===========================================================

Simple context manager for timing code blocks.
Useful for profiling individual pipeline stages.

Usage:
    from src.utils.timer import Timer

    with Timer("YOLOv8 Inference"):
        results = model.predict(frame)
    # Prints: [TIMER] YOLOv8 Inference: 23.4ms

    # Or manual usage:
    t = Timer("Ego-Motion")
    t.start()
    # ... code ...
    elapsed = t.stop()
"""

import time

from src.utils.logger import get_logger

logger = get_logger("Timer")


class Timer:
    """
    Simple performance timer with context manager support.

    Attributes:
        name (str): Label for this timer (used in log output).
        _start (float): Start timestamp.
        _elapsed (float): Elapsed time in seconds after stop().
    """

    def __init__(self, name: str = "Block", log: bool = True):
        """
        Initialize the timer.

        Args:
            name: Label for the timed block (appears in logs).
            log: If True, automatically logs elapsed time on stop().
        """
        self.name = name
        self._log = log
        self._start = 0.0
        self._elapsed = 0.0

    def start(self) -> "Timer":
        """Start the timer. Returns self for chaining."""
        self._start = time.perf_counter()
        return self

    def stop(self) -> float:
        """
        Stop the timer and return elapsed time.

        Returns:
            float: Elapsed time in seconds.
        """
        self._elapsed = time.perf_counter() - self._start

        if self._log:
            ms = self._elapsed * 1000
            logger.info(f"{self.name}: {ms:.1f}ms")

        return self._elapsed

    @property
    def elapsed_ms(self) -> float:
        """Elapsed time in milliseconds."""
        return self._elapsed * 1000

    # Context manager support: with Timer("name"): ...
    def __enter__(self) -> "Timer":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()

    def __repr__(self) -> str:
        return f"Timer(name='{self.name}', elapsed={self.elapsed_ms:.1f}ms)"