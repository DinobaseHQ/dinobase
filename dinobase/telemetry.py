"""PostHog telemetry — fire-and-forget, opt-out via DINOBASE_TELEMETRY=false."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
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


def _anon_id_path() -> Path:
    return Path.home() / ".dinobase" / "telemetry_id"


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
        p = _anon_id_path()
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


def alias(previous_id: str, new_id: str) -> None:
    """Merge `previous_id` into `new_id` in PostHog. Never raises."""
    if not previous_id or not new_id or previous_id == new_id:
        return
    client = _get_client()
    if not client:
        return
    try:
        client.alias(previous_id=previous_id, distinct_id=new_id)
    except Exception:
        pass


def identify(user_id: str, email: str | None = None) -> None:
    """Call after successful login to associate events with a cloud user.

    Also aliases any prior anonymous distinct_id to the cloud user_id so
    pre-login events are stitched together in PostHog.
    """
    if not user_id:
        return
    client = _get_client()
    if not client:
        return
    global _distinct_id
    prior = _distinct_id
    if prior is None:
        try:
            p = _anon_id_path()
            if p.exists():
                prior = p.read_text().strip() or None
        except Exception:
            prior = None
    try:
        if prior and prior != user_id:
            try:
                client.alias(previous_id=prior, distinct_id=user_id)
            except Exception:
                pass
        props = {"email": email} if email else {}
        client.set(distinct_id=user_id, properties=props)
        _distinct_id = user_id
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Installed-client dedup (used by `dinobase install <client>`)
# ---------------------------------------------------------------------------


def _installed_clients_path() -> Path:
    return Path.home() / ".dinobase" / "installed_clients.json"


def _load_installed_clients() -> dict:
    try:
        p = _installed_clients_path()
        if p.exists():
            data = json.loads(p.read_text())
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def was_installed(client: str) -> bool:
    return client in _load_installed_clients()


def mark_installed(client: str) -> None:
    """Record that `client` has been installed on this machine. Never raises."""
    try:
        data = _load_installed_clients()
        data[client] = datetime.now(timezone.utc).isoformat()
        p = _installed_clients_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2))
    except Exception:
        pass
