"""PostHog telemetry — fire-and-forget, opt-out via DINOBASE_TELEMETRY=false."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

_POSTHOG_KEY = "phc_qLLY2ezUuyUsjqxDqZryB3DJ2bine2YDrRqzha8iWeDN"
_POSTHOG_HOST = "https://us.i.posthog.com"

_client = None
_distinct_id: str | None = None


def _enabled() -> bool:
    return os.environ.get("DINOBASE_TELEMETRY", "1").lower() not in ("0", "false", "no", "off")


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not _enabled():
        return None
    try:
        from posthog import Posthog
        _client = Posthog(_POSTHOG_KEY, host=_POSTHOG_HOST, enable_exception_autocapture=True)
    except Exception:
        pass
    return _client


def _get_id() -> str:
    global _distinct_id
    if _distinct_id:
        return _distinct_id
    # Cloud user → use server-assigned user_id
    try:
        from dinobase.config import load_cloud_credentials
        creds = load_cloud_credentials()
        if creds and creds.get("user_id"):
            _distinct_id = creds["user_id"]
            return _distinct_id
    except Exception:
        pass
    # Anonymous → persistent UUID in ~/.dinobase/telemetry_id
    try:
        p = Path.home() / ".dinobase" / "telemetry_id"
        if p.exists():
            _distinct_id = p.read_text().strip()
        else:
            _distinct_id = str(uuid.uuid4())
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_distinct_id)
    except Exception:
        _distinct_id = "anonymous"
    return _distinct_id or "anonymous"


def capture(event: str, properties: dict | None = None) -> None:
    """Fire-and-forget event capture. Never raises."""
    client = _get_client()
    if not client:
        return
    try:
        client.capture(event, distinct_id=_get_id(), properties=properties or {})
    except Exception:
        pass


def identify(user_id: str, email: str | None = None) -> None:
    """Call after successful login to associate events with a cloud user."""
    client = _get_client()
    if not client:
        return
    try:
        props = {"email": email} if email else {}
        client.set(distinct_id=user_id, properties=props)
        global _distinct_id
        _distinct_id = user_id
    except Exception:
        pass
