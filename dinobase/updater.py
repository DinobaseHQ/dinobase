"""Auto-update logic for Dinobase CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from dinobase import __version__
from dinobase.config import get_dinobase_dir

PYPI_URL = "https://pypi.org/pypi/dinobase/json"
CHECK_INTERVAL = 4 * 3600  # 4 hours


def _update_state_path() -> Path:
    return get_dinobase_dir() / "update_check.json"


def _load_state() -> dict:
    try:
        with open(_update_state_path()) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    try:
        path = _update_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f)
    except OSError:
        pass


def _check_enabled() -> bool:
    if os.environ.get("DINOBASE_NO_UPDATE_CHECK", "").lower() in ("1", "true", "yes", "on"):
        return False
    try:
        from dinobase.config import load_config
        return load_config().get("auto_update", True) is not False
    except Exception:
        return True


def _version_tuple(v: str) -> tuple:
    """Parse version string into a comparable tuple."""
    try:
        from packaging.version import Version
        return Version(v)
    except Exception:
        # Fallback: split on dots and compare as ints
        parts = []
        for p in v.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(p)
        return tuple(parts)


def check_for_update(force: bool = False) -> dict | None:
    """Check PyPI for a newer version. Returns update info or None.

    Uses cached result if checked within CHECK_INTERVAL, unless force=True.
    """
    if not force and not _check_enabled():
        return None

    state = _load_state()

    # Use cache if fresh enough
    if not force and state.get("last_check"):
        if time.time() - state["last_check"] < CHECK_INTERVAL:
            latest = state.get("latest_version", "")
            if latest and _version_tuple(latest) > _version_tuple(__version__):
                return {"latest_version": latest, "update_available": True}
            return None

    # Fetch from PyPI
    try:
        from urllib.request import Request, urlopen

        req = Request(PYPI_URL, headers={"Accept": "application/json"})
        with urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        latest = data["info"]["version"]
    except Exception:
        # Network error — save timestamp to avoid retrying immediately
        state["last_check"] = time.time()
        _save_state(state)
        return None

    state["last_check"] = time.time()
    state["latest_version"] = latest
    _save_state(state)

    if _version_tuple(latest) > _version_tuple(__version__):
        return {"latest_version": latest, "update_available": True}
    return None


def detect_install_method() -> str:
    """Detect whether dinobase was installed via uv or pip."""
    import shutil

    # uv tool installs live under a path like ~/.local/share/uv/tools/dinobase/
    if "uv" in sys.prefix and "tools" in sys.prefix:
        return "uv"
    if shutil.which("pip") or shutil.which("pip3"):
        return "pip"
    return "unknown"


def get_update_command(method: str | None = None) -> str:
    method = method or detect_install_method()
    if method == "uv":
        return "uv tool install dinobase --force"
    return "pip install --upgrade dinobase"


def perform_update() -> tuple[bool, str]:
    """Run the update command. Returns (success, message)."""
    method = detect_install_method()
    cmd = get_update_command(method)
    try:
        result = subprocess.run(
            cmd.split(),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return True, f"Updated successfully via {method}."
        return False, f"Update failed:\n{result.stderr}"
    except Exception as e:
        return False, f"Update failed: {e}"


def maybe_auto_update(cmd: str) -> None:
    """Check for updates and auto-install if available. May re-exec the process."""
    if not _check_enabled():
        return

    # Don't auto-update during the update command itself
    if cmd == "update":
        return

    # Skip if dinobase dir doesn't exist yet (pre-init)
    if not get_dinobase_dir().exists():
        return

    update_info = check_for_update()
    if not update_info or not update_info.get("update_available"):
        return

    latest = update_info["latest_version"]
    import click

    click.echo(f"Updating dinobase {__version__} -> {latest}...", err=True)

    success, message = perform_update()
    if not success:
        click.echo(f"Auto-update failed: {message}", err=True)
        return

    click.echo(f"Updated to {latest}.", err=True)

    from dinobase import telemetry
    telemetry.capture("cli_updated", {
        "from_version": __version__,
        "to_version": latest,
        "method": detect_install_method(),
    })

    # Re-exec so the new version handles the command
    try:
        os.execvp(sys.argv[0], sys.argv)
    except OSError:
        # If re-exec fails, continue with current version
        pass
