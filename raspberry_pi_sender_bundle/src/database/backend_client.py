"""
RTIPVD backend sync client.

Sends violation records to a remote backend API so other
departments can consume live incidents.
"""

from typing import Optional

from config.config import (
    BACKEND_API_KEY,
    BACKEND_ENABLED,
    BACKEND_TIMEOUT_SEC,
    BACKEND_URL,
    BACKEND_VERIFY_SSL,
)
from src.database.models import ViolationRecord

try:
    import requests
except ImportError:  # pragma: no cover - handled safely at runtime
    requests = None


class BackendClient:
    """Simple HTTP client for pushing violations to backend APIs."""

    def __init__(
        self,
        enabled: bool = BACKEND_ENABLED,
        url: str = BACKEND_URL,
        api_key: str = BACKEND_API_KEY,
        timeout_sec: float = BACKEND_TIMEOUT_SEC,
        verify_ssl: bool = BACKEND_VERIFY_SSL,
    ):
        self.enabled = enabled
        self.url = url
        self.api_key = api_key
        self.timeout_sec = timeout_sec
        self.verify_ssl = verify_ssl

        self._session = requests.Session() if (self.enabled and requests is not None) else None

    @property
    def is_ready(self) -> bool:
        """Return True if backend sync is enabled and dependencies are available."""
        return self.enabled and self._session is not None and bool(self.url)

    def send_violation(
        self,
        record: ViolationRecord,
        violation_id: Optional[int] = None,
        event_type: str = "updated",
    ) -> bool:
        """POST one violation payload to backend endpoint."""
        if not self.is_ready:
            return False

        payload = record.to_api_payload(
            violation_id=violation_id,
            event_type=event_type,
        )

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        try:
            assert self._session is not None
            response = self._session.post(
                self.url,
                json=payload,
                headers=headers,
                timeout=self.timeout_sec,
                verify=self.verify_ssl,
            )
            return response.ok
        except Exception as exc:
            print(f"[BackendClient] WARNING: Failed to sync violation: {exc}")
            return False

    def close(self) -> None:
        """Close internal HTTP session."""
        if self._session is not None:
            self._session.close()
            self._session = None

    def __repr__(self) -> str:
        state = "enabled" if self.enabled else "disabled"
        return f"BackendClient(state={state}, url='{self.url}')"
