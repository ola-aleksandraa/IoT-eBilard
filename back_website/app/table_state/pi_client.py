"""Minimal client for the Raspberry Pi camera routes (back_raspberry/, /api/v1/camera/*)."""

import httpx


class PiError(RuntimeError):
    """The Pi answered with an error or could not be reached."""


class PiBusy(PiError):
    """The Pi is processing another request (503); retry later."""


class PiClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8002", timeout_s: float = 15.0,
                 client: httpx.Client | None = None):
        # `client` lets tests and the scenario inject an in-process transport.
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout_s)

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, body: dict) -> dict:
        try:
            response = self._client.post(f"/api/v1/camera/{path}", json=body)
        except httpx.HTTPError as exc:
            raise PiError(f"Pi unreachable: {exc}") from exc
        if response.status_code == 503:
            raise PiBusy(response.json().get("detail", "busy") if response.content else "busy")
        if response.status_code != 200:
            detail = response.json().get("detail", "") if response.content else ""
            raise PiError(f"Pi /camera/{path} returned {response.status_code}: {detail}")
        return response.json()

    def calibrate(self, settings: dict) -> dict | None:
        """Returns the table calibration to lock for later frames, or None if no table is visible."""
        result = self._post("calibrate", {"settings": settings})
        return result["calibration"] if result.get("table_status") == "detected" else None

    def detect(self, settings: dict, calibration: dict | None) -> dict:
        """Returns the Pi AnalysisResult JSON."""
        body: dict = {"settings": settings}
        if calibration is not None:
            body["calibration"] = calibration
        return self._post("detect", body)
