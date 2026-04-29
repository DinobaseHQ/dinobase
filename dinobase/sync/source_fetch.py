"""On-demand fetcher for dlt verified sources.

The dlt-hub/verified-sources repo isn't published to PyPI — it's a collection
of source templates meant to be copied into a project via `dlt init`. Rather
than vendoring all ~40 sources or asking users to install the whole repo, we
fetch just the source they need on first use and cache it under
~/.dinobase/cache/verified-sources/<ref>/.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tarfile
import threading
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from dinobase.config import get_verified_sources_cache_dir


# Pinned commit of github.com/dlt-hub/verified-sources. Bump deliberately —
# downstream sources may change their signatures or required deps between
# revisions, so we want releases to test against a known revision.
VERIFIED_SOURCES_REF = "75b3ec17eab99d0079d9f61b7f47fc8b899a5738"
VERIFIED_SOURCES_REPO = "dlt-hub/verified-sources"

DOWNLOAD_TIMEOUT = 60.0
INSTALL_TIMEOUT = 300

_fetch_lock = threading.Lock()


def cache_root() -> Path:
    """Ref-scoped cache root: ~/.dinobase/cache/verified-sources/<ref>/."""
    return get_verified_sources_cache_dir() / VERIFIED_SOURCES_REF


def ensure_verified_source(name: str) -> Path:
    """Make `sources.<name>` importable, fetching and installing deps if needed.

    Returns the ref-scoped cache root (the directory to add to sys.path).
    """
    with _fetch_lock:
        root = cache_root()
        src_dir = root / "sources" / name

        if not src_dir.exists():
            _fetch_source(name, root)

        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

        req_file = src_dir / "requirements.txt"
        marker = src_dir / ".deps-installed"
        if req_file.exists() and not marker.exists():
            _install_requirements(name, req_file)
            marker.touch()

        return root


def _fetch_source(name: str, root: Path) -> None:
    """Download the verified-sources tarball and extract just `sources/<name>/`."""
    url = (
        f"https://codeload.github.com/{VERIFIED_SOURCES_REPO}"
        f"/tar.gz/{VERIFIED_SOURCES_REF}"
    )
    print(
        f"  Fetching verified source '{name}' from {VERIFIED_SOURCES_REPO}@"
        f"{VERIFIED_SOURCES_REF[:7]}...",
        file=sys.stderr,
    )

    try:
        with urlopen(url, timeout=DOWNLOAD_TIMEOUT) as resp:
            data = resp.read()
    except URLError as e:
        raise RuntimeError(
            f"Could not download dlt verified source '{name}' from {url}: {e}. "
            f"Check your internet connection."
        ) from e

    sources_root = root / "sources"
    sources_root.mkdir(parents=True, exist_ok=True)
    init_file = sources_root / "__init__.py"
    if not init_file.exists():
        init_file.write_text("")

    target_dir = sources_root / name
    extracted = _extract_subtree(
        data,
        prefix=f"verified-sources-{VERIFIED_SOURCES_REF}/sources/{name}/",
        dest=target_dir,
    )

    if extracted == 0:
        raise RuntimeError(
            f"Verified source '{name}' not found in "
            f"{VERIFIED_SOURCES_REPO}@{VERIFIED_SOURCES_REF}. "
            f"Check the source name."
        )


def _extract_subtree(data: bytes, prefix: str, dest: Path) -> int:
    """Extract members under `prefix` into `dest`, refusing paths that escape it."""
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()

    extracted = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for member in tf.getmembers():
            if not member.name.startswith(prefix):
                continue
            rel = member.name[len(prefix):]
            if not rel:
                continue

            target = (dest / rel).resolve()
            try:
                target.relative_to(dest_resolved)
            except ValueError:
                raise RuntimeError(f"Tarball entry escapes destination: {rel}")

            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue  # skip links/special entries — never needed for source code

            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                continue
            with open(target, "wb") as f:
                shutil.copyfileobj(src, f)
            extracted += 1

    return extracted


def _install_requirements(name: str, req_file: Path) -> None:
    """Install a verified source's runtime dependencies into the current env."""
    print(
        f"  Installing dependencies for '{name}' from {req_file.name}...",
        file=sys.stderr,
    )

    cmd = _install_command() + ["-r", str(req_file)]
    try:
        # Stream output (no capture_output) so users see pip progress on slow
        # networks. Bound install time so a wedged resolver doesn't hang sync.
        result = subprocess.run(cmd, check=False, timeout=INSTALL_TIMEOUT)
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Could not install dependencies for '{name}': {e}. "
            f"Install them manually: pip install -r {req_file}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"Installing dependencies for '{name}' timed out after "
            f"{INSTALL_TIMEOUT}s. Install them manually: pip install -r {req_file}"
        ) from e

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to install dependencies for '{name}'. "
            f"Install them manually: pip install -r {req_file}"
        )


def _install_command() -> list[str]:
    """Return the pip-install command appropriate for the current environment.

    uv-managed tool envs ship without pip, so we prefer `uv pip install
    --python <sys.executable>` when uv is available. Otherwise fall back to
    `python -m pip install`.
    """
    uv_bin = shutil.which("uv") or os.environ.get("UV")
    if uv_bin:
        return [uv_bin, "pip", "install", "--python", sys.executable]
    return [sys.executable, "-m", "pip", "install"]
