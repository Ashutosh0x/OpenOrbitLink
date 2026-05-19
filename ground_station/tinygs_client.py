from __future__ import annotations

"""
TinyGS API client.

TinyGS documents a programmatic API for station control with Bearer-token
authentication and base64-encoded transmit frames. Endpoint paths have changed
while the API has been under development, so this client keeps the base URL and
station TX path configurable.
"""

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


class TinyGSError(RuntimeError):
    """Raised when TinyGS returns an error or cannot be reached."""


@dataclass(frozen=True)
class TinyGSTransmitResult:
    ok: bool
    status_code: int
    response: dict[str, Any] | str


class TinyGSClient:
    def __init__(
        self,
        base_url: str = "https://api.tinygs.com/v1",
        bearer_token: Optional[str] = None,
        station_tx_path: str = "/station/{station_id}/tx",
        timeout_seconds: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.station_tx_path = station_tx_path
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def frame_to_base64(frame: bytes) -> str:
        return base64.b64encode(frame).decode("ascii")

    @staticmethod
    def frame_from_base64(encoded: str) -> bytes:
        return base64.b64decode(encoded.encode("ascii"), validate=True)

    def station_tx_url(self, station_id: str) -> str:
        path = self.station_tx_path.format(station_id=station_id).lstrip("/")
        return f"{self.base_url}/{path}"

    def _request(self, method: str, url: str, payload: Optional[dict[str, Any]] = None) -> TinyGSTransmitResult:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                try:
                    parsed: dict[str, Any] | str = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    parsed = raw
                return TinyGSTransmitResult(ok=200 <= resp.status < 300, status_code=resp.status, response=parsed)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = raw
            return TinyGSTransmitResult(ok=False, status_code=exc.code, response=parsed)
        except urllib.error.URLError as exc:
            raise TinyGSError(str(exc)) from exc

    def transmit_frame(
        self,
        station_id: str,
        frame: bytes,
        *,
        satellite: str = "",
        frequency_hz: Optional[float] = None,
        dry_run: bool = False,
    ) -> TinyGSTransmitResult:
        """Command a TinyGS station to transmit a base64 frame."""
        payload: dict[str, Any] = {
            "frame": self.frame_to_base64(frame),
            "encoding": "base64",
        }
        if satellite:
            payload["satellite"] = satellite
        if frequency_hz is not None:
            payload["frequency_hz"] = frequency_hz
        if dry_run:
            return TinyGSTransmitResult(ok=True, status_code=0, response=payload)
        return self._request("POST", self.station_tx_url(station_id), payload)

    def poll_packets(self, path: str = "/packets", limit: int = 50) -> dict[str, Any] | str:
        """Fetch recently received packets from a configurable TinyGS endpoint."""
        separator = "&" if "?" in path else "?"
        url = f"{self.base_url}/{path.lstrip('/')}{separator}limit={int(limit)}"
        result = self._request("GET", url)
        if not result.ok:
            raise TinyGSError(f"TinyGS packet poll failed: HTTP {result.status_code}: {result.response}")
        return result.response

    def receive_packets(
        self,
        since_timestamp: float | None = None,
        limit: int = 50,
        destination_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch received packets with optional timestamp and destination filtering.

        Used by the backend to populate user inboxes from satellite data.
        Wraps poll_packets with post-processing for the API layer.

        Args:
            since_timestamp: Unix timestamp; only return packets after this time.
            limit: Maximum packets to return.
            destination_filter: If set, only return packets addressed to this ID.

        Returns:
            List of packet dicts with normalized fields.
        """
        raw = self.poll_packets(limit=limit)

        # Normalize response to list
        if isinstance(raw, str):
            return []
        if isinstance(raw, dict):
            packets = raw.get("packets", raw.get("data", []))
            if not isinstance(packets, list):
                return []
        elif isinstance(raw, list):
            packets = raw
        else:
            return []

        # Filter by timestamp
        if since_timestamp is not None:
            packets = [
                p for p in packets
                if p.get("timestamp", p.get("time", 0)) >= since_timestamp
            ]

        # Filter by destination
        if destination_filter:
            packets = [
                p for p in packets
                if destination_filter in (
                    p.get("destination", ""),
                    p.get("dst", ""),
                    p.get("to", ""),
                )
            ]

        return packets[:limit]

