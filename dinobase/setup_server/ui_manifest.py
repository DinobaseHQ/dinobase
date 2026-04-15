"""Resolve a `UIBundle` to serve at `dinobase setup` startup.

Flow
----
1. Env-var escape hatches (dev / offline / manifest override).
2. Fetch a *redirect manifest* from the cloud over HTTPS.
3. Filter releases by the running backend version's compatibility range.
4. Rollback protection against ``last_seen.json``.
5. Resolve the real download URL via ``api.github.com`` (second trust
   anchor, independent of the cloud domain).
6. Enforce a host allowlist on the resolved URL.
7. Download the tarball with a size cap, verify SHA-256 against the
   manifest, extract safely, cache.
8. On *any* failure, fall back silently to the bundled copy shipped in
   the wheel.

See `/Users/.../wise-sniffing-gray.md` for the threat model.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from dinobase.config import get_setup_ui_cache_dir
from dinobase.setup_server.ui_bundle import UIBundle


# ---------------------------------------------------------------------------
# Constants — pinned in the wheel. Any change requires a wheel release.
# ---------------------------------------------------------------------------

DEFAULT_MANIFEST_URL = "https://app.dinobase.ai/setup-ui/manifest.json"
DEFAULT_GITHUB_REPO = "DinobaseHQ/dinobase"

MANIFEST_TIMEOUT = 3.0  # seconds
MANIFEST_MAX_BYTES = 64 * 1024
GITHUB_API_TIMEOUT = 5.0
DOWNLOAD_TIMEOUT = 15.0
DOWNLOAD_MAX_BYTES = 10 * 1024 * 1024
EXTRACT_PER_ENTRY_MAX_BYTES = 8 * 1024 * 1024
EXTRACT_TOTAL_MAX_BYTES = 16 * 1024 * 1024
CLOCK_SKEW_TOLERANCE_SECONDS = 24 * 3600

ALLOWED_DOWNLOAD_HOSTS = frozenset({
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
})

USER_AGENT = "dinobase-setup-ui-fetcher/1"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def resolve_ui_bundle(backend_version: str) -> UIBundle:
    """Pick a UI bundle to serve. Returns a `UIBundle` — never raises.

    On any failure, returns ``UIBundle.bundled()`` (the wheel's floor copy).
    """
    # 1) Dev-mode escape hatch: serve a disk path verbatim.
    dev_dir = os.environ.get("DINOBASE_SETUP_UI_DIR")
    if dev_dir:
        path = Path(dev_dir).expanduser()
        if path.is_dir():
            return UIBundle.from_dir(path, ui_version="dev")
        _log(f"DINOBASE_SETUP_UI_DIR points to a non-directory: {dev_dir}")
        return UIBundle.bundled()

    # 2) Offline opt-out.
    if _flag("DINOBASE_SETUP_UI_OFFLINE"):
        return UIBundle.bundled()

    manifest_url = os.environ.get("DINOBASE_SETUP_UI_MANIFEST_URL") or DEFAULT_MANIFEST_URL
    repo = os.environ.get("DINOBASE_SETUP_UI_REPO") or DEFAULT_GITHUB_REPO

    try:
        return _resolve_remote(backend_version, manifest_url, repo)
    except _ResolveAbort as e:
        _log(f"setup UI: falling back to bundled ({e})")
        return UIBundle.bundled()
    except Exception as e:  # pragma: no cover — defensive
        _log(f"setup UI: unexpected error ({type(e).__name__}: {e}); using bundled")
        return UIBundle.bundled()


# ---------------------------------------------------------------------------
# Resolution pipeline
# ---------------------------------------------------------------------------


class _ResolveAbort(Exception):
    """Raised internally to trigger the fallback path with a reason string."""


def _resolve_remote(backend_version: str, manifest_url: str, repo: str) -> UIBundle:
    _require_https(manifest_url, "manifest URL")

    manifest = _fetch_manifest(manifest_url)
    _validate_manifest_schema(manifest)
    _check_clock_skew(manifest)

    releases = manifest["releases"]
    compatible = [r for r in releases if _version_in_range(backend_version, r.get("min_backend"), r.get("max_backend"))]
    if not compatible:
        raise _ResolveAbort("no compatible UI release in manifest")

    compatible.sort(key=lambda r: _version_tuple(r["ui_version"]), reverse=True)

    # Rollback protection — never downgrade below last_seen.
    cache_root = get_setup_ui_cache_dir()
    last_seen = _read_last_seen(cache_root)
    if last_seen is not None:
        last_tuple = _version_tuple(last_seen)
        picked = None
        for r in compatible:
            if _version_tuple(r["ui_version"]) >= last_tuple:
                picked = r
                break
        if picked is None:
            raise _ResolveAbort(
                f"manifest only offers versions below last-seen {last_seen}; "
                "refusing downgrade"
            )
        release = picked
    else:
        release = compatible[0]

    ui_version = release["ui_version"]
    expected_sha = release["sha256"].lower()

    # Cache hit.
    cached_meta = _read_cached_meta(cache_root, ui_version)
    if cached_meta and cached_meta.get("sha256", "").lower() == expected_sha:
        _write_last_seen(cache_root, ui_version)
        return UIBundle.from_cache(cache_root, ui_version)

    # Cache miss. Resolve actual download URL via GitHub API.
    download_url = _resolve_github_asset_url(
        repo_override=release.get("github_repo") or repo,
        tag=release["github_tag"],
        asset_name=release["asset_name"],
    )
    _require_https(download_url, "download URL")
    _require_allowed_host(download_url)

    # Download with size cap.
    tarball_bytes = _download_bounded(download_url, DOWNLOAD_MAX_BYTES, DOWNLOAD_TIMEOUT)

    # Verify SHA.
    actual_sha = hashlib.sha256(tarball_bytes).hexdigest()
    if actual_sha != expected_sha:
        raise _ResolveAbort(
            f"SHA-256 mismatch for {ui_version}: "
            f"expected {expected_sha[:12]}..., got {actual_sha[:12]}..."
        )

    # Extract into cache.
    target_dir = cache_root / ui_version / "files"
    _prepare_fresh_dir(target_dir)
    _safe_extract_tarball(tarball_bytes, target_dir)

    # Record meta + last_seen.
    meta_path = cache_root / ui_version / "meta.json"
    meta_path.write_text(
        json.dumps({
            "ui_version": ui_version,
            "sha256": expected_sha,
            "downloaded_at": int(time.time()),
            "github_tag": release["github_tag"],
        })
    )
    _write_last_seen(cache_root, ui_version)

    # Prune old cached versions (keep 3 most recent).
    _prune_cache(cache_root, keep=3)

    return UIBundle.from_cache(cache_root, ui_version)


# ---------------------------------------------------------------------------
# Manifest fetch + schema validation
# ---------------------------------------------------------------------------


def _fetch_manifest(url: str) -> dict[str, Any]:
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urlopen(req, timeout=MANIFEST_TIMEOUT) as resp:
            status = getattr(resp, "status", None)
            if status is not None and status != 200:
                raise _ResolveAbort(f"manifest fetch returned HTTP {status}")
            raw = resp.read(MANIFEST_MAX_BYTES + 1)
    except HTTPError as e:
        raise _ResolveAbort(f"manifest HTTP error: {e.code}")
    except URLError as e:
        raise _ResolveAbort(f"manifest network error: {e.reason}")
    except TimeoutError:
        raise _ResolveAbort(f"manifest fetch timed out after {MANIFEST_TIMEOUT}s")

    if len(raw) > MANIFEST_MAX_BYTES:
        raise _ResolveAbort(f"manifest exceeds {MANIFEST_MAX_BYTES} byte cap")

    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise _ResolveAbort(f"manifest JSON parse failed: {e}")


def _validate_manifest_schema(manifest: Any) -> None:
    if not isinstance(manifest, dict):
        raise _ResolveAbort("manifest is not a JSON object")
    if manifest.get("manifest_version") != 1:
        raise _ResolveAbort(
            f"unsupported manifest_version: {manifest.get('manifest_version')!r}"
        )
    releases = manifest.get("releases")
    if not isinstance(releases, list):
        raise _ResolveAbort("manifest.releases must be a list")

    required = ("ui_version", "github_tag", "asset_name", "sha256")
    for i, r in enumerate(releases):
        if not isinstance(r, dict):
            raise _ResolveAbort(f"releases[{i}] is not an object")
        for k in required:
            v = r.get(k)
            if not isinstance(v, str) or not v:
                raise _ResolveAbort(f"releases[{i}].{k} missing or not a string")
        if not _is_hex_sha256(r["sha256"]):
            raise _ResolveAbort(f"releases[{i}].sha256 is not a 64-char hex digest")
        # Optional string fields.
        for k in ("min_backend", "max_backend", "github_repo"):
            v = r.get(k)
            if v is not None and not isinstance(v, str):
                raise _ResolveAbort(f"releases[{i}].{k} must be string or null")


def _check_clock_skew(manifest: dict[str, Any]) -> None:
    ts = manifest.get("updated_at")
    if not isinstance(ts, str):
        return  # optional
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        raise _ResolveAbort(f"manifest.updated_at is not ISO 8601: {ts!r}")
    skew = dt.timestamp() - time.time()
    if skew > CLOCK_SKEW_TOLERANCE_SECONDS:
        raise _ResolveAbort(
            f"manifest.updated_at is {int(skew)}s in the future "
            f"(> {CLOCK_SKEW_TOLERANCE_SECONDS}s tolerance)"
        )


# ---------------------------------------------------------------------------
# GitHub API — resolve actual download URL
# ---------------------------------------------------------------------------


def _resolve_github_asset_url(repo_override: str, tag: str, asset_name: str) -> str:
    if "/" not in repo_override:
        raise _ResolveAbort(f"invalid github repo: {repo_override!r}")
    api_url = f"https://api.github.com/repos/{repo_override}/releases/tags/{tag}"
    _require_https(api_url, "github API URL")
    try:
        req = Request(
            api_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
        )
        with urlopen(req, timeout=GITHUB_API_TIMEOUT) as resp:
            if resp.status != 200:
                raise _ResolveAbort(f"github API returned HTTP {resp.status}")
            raw = resp.read(256 * 1024)  # plenty for a single release JSON
    except HTTPError as e:
        raise _ResolveAbort(f"github API HTTP error: {e.code}")
    except URLError as e:
        raise _ResolveAbort(f"github API network error: {e.reason}")
    except TimeoutError:
        raise _ResolveAbort(f"github API timed out after {GITHUB_API_TIMEOUT}s")

    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise _ResolveAbort(f"github API JSON parse failed: {e}")

    if not isinstance(data, dict):
        raise _ResolveAbort("github API response is not an object")
    if data.get("draft") is True:
        raise _ResolveAbort("github release is a draft")
    assets = data.get("assets")
    if not isinstance(assets, list):
        raise _ResolveAbort("github release has no assets array")

    for a in assets:
        if isinstance(a, dict) and a.get("name") == asset_name:
            url = a.get("browser_download_url")
            if not isinstance(url, str) or not url:
                raise _ResolveAbort("github asset has no browser_download_url")
            return url

    raise _ResolveAbort(f"github release {tag!r} has no asset named {asset_name!r}")


# ---------------------------------------------------------------------------
# Download + extract
# ---------------------------------------------------------------------------


def _download_bounded(url: str, max_bytes: int, timeout: float) -> bytes:
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise _ResolveAbort(f"download returned HTTP {resp.status}")
            # Guard against Content-Length lies by capping the read.
            declared = resp.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise _ResolveAbort(
                    f"download Content-Length {declared} exceeds {max_bytes} cap"
                )
            raw = resp.read(max_bytes + 1)
    except HTTPError as e:
        raise _ResolveAbort(f"download HTTP error: {e.code}")
    except URLError as e:
        raise _ResolveAbort(f"download network error: {e.reason}")
    except TimeoutError:
        raise _ResolveAbort(f"download timed out after {timeout}s")

    if len(raw) > max_bytes:
        raise _ResolveAbort(f"download exceeds {max_bytes} byte cap")
    return raw


def _safe_extract_tarball(data: bytes, dest: Path) -> None:
    """Extract a .tar.gz from in-memory bytes into `dest` with all safety checks."""
    import io

    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()

    total_extracted = 0
    try:
        buf = io.BytesIO(data)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            # Python 3.12+: use the built-in data filter as an extra layer.
            use_data_filter = sys.version_info >= (3, 12)
            for member in tar.getmembers():
                # Reject anything that isn't a regular file or directory.
                if not (member.isfile() or member.isdir()):
                    raise _ResolveAbort(
                        f"tarball contains disallowed entry type "
                        f"({member.name}: type={member.type!r})"
                    )
                if member.islnk() or member.issym():
                    raise _ResolveAbort(f"tarball contains link entry: {member.name}")
                # Reject absolute paths.
                name = member.name
                if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
                    raise _ResolveAbort(f"tarball contains absolute path: {name}")
                # Resolve and check containment.
                target = (dest / name).resolve()
                try:
                    target.relative_to(dest_resolved)
                except ValueError:
                    raise _ResolveAbort(f"tarball entry escapes dest: {name}")
                # Size caps.
                if member.isfile():
                    if member.size > EXTRACT_PER_ENTRY_MAX_BYTES:
                        raise _ResolveAbort(
                            f"tarball entry {name} exceeds per-entry cap "
                            f"({member.size} > {EXTRACT_PER_ENTRY_MAX_BYTES})"
                        )
                    total_extracted += member.size
                    if total_extracted > EXTRACT_TOTAL_MAX_BYTES:
                        raise _ResolveAbort(
                            f"tarball total uncompressed size exceeds "
                            f"{EXTRACT_TOTAL_MAX_BYTES} cap"
                        )

            # Re-open to actually extract (getmembers consumed the iterator).
            buf.seek(0)
            with tarfile.open(fileobj=buf, mode="r:gz") as tar2:
                if use_data_filter:
                    tar2.extractall(dest, filter="data")  # type: ignore[arg-type]
                else:
                    tar2.extractall(dest)
    except tarfile.TarError as e:
        raise _ResolveAbort(f"tarball extract failed: {e}")


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _read_cached_meta(cache_root: Path, ui_version: str) -> dict[str, Any] | None:
    meta_path = cache_root / ui_version / "meta.json"
    files_dir = cache_root / ui_version / "files"
    if not (meta_path.exists() and files_dir.is_dir()):
        return None
    try:
        return json.loads(meta_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _prepare_fresh_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


def _prune_cache(cache_root: Path, keep: int) -> None:
    if not cache_root.is_dir():
        return
    versions = []
    for child in cache_root.iterdir():
        if child.is_dir() and (child / "meta.json").exists():
            try:
                versions.append((_version_tuple(child.name), child))
            except ValueError:
                continue
    versions.sort(key=lambda x: x[0], reverse=True)
    for _, path in versions[keep:]:
        shutil.rmtree(path, ignore_errors=True)


def _read_last_seen(cache_root: Path) -> str | None:
    p = cache_root / "last_seen.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        v = data.get("ui_version")
        return str(v) if isinstance(v, str) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_last_seen(cache_root: Path, ui_version: str) -> None:
    cache_root.mkdir(parents=True, exist_ok=True)
    p = cache_root / "last_seen.json"
    try:
        p.write_text(json.dumps({"ui_version": ui_version, "updated_at": int(time.time())}))
    except OSError:
        pass  # best effort


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


def _version_tuple(v: str) -> tuple[int, ...]:
    """Parse a dotted version into a 4-tuple of ints. 'x' or '*' → 0."""
    parts = v.strip().split(".")
    out = []
    for p in parts[:4]:
        if p in ("x", "*", ""):
            out.append(0)
        else:
            try:
                out.append(int(p))
            except ValueError:
                raise ValueError(f"non-numeric version component: {p!r} in {v!r}")
    while len(out) < 4:
        out.append(0)
    return tuple(out)


def _version_in_range(v: str, lo: str | None, hi: str | None) -> bool:
    try:
        vt = _version_tuple(v)
    except ValueError:
        return False
    if lo:
        try:
            if vt < _version_tuple(lo):
                return False
        except ValueError:
            return False
    if hi:
        try:
            # A max like "0.3.x" means "anything with same major.minor",
            # so compare as prefix: pad unspecified components with 9999.
            hi_parts = hi.strip().split(".")
            padded = []
            for p in hi_parts[:4]:
                if p in ("x", "*"):
                    padded.append(9999)
                else:
                    padded.append(int(p))
            while len(padded) < 4:
                padded.append(9999)
            if vt > tuple(padded):
                return False
        except ValueError:
            return False
    return True


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def _require_https(url: str, label: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        # Local file manifest — dev/testing only. Allow but only for manifest.
        if label == "manifest URL":
            return
        raise _ResolveAbort(f"{label} must use HTTPS ({url!r})")
    if parsed.scheme != "https":
        raise _ResolveAbort(f"{label} must use HTTPS ({url!r})")


def _require_allowed_host(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_DOWNLOAD_HOSTS:
        raise _ResolveAbort(f"download host {host!r} not in allowlist")


def _is_hex_sha256(s: str) -> bool:
    if len(s) != 64:
        return False
    try:
        int(s, 16)
    except ValueError:
        return False
    return True


def _flag(name: str) -> bool:
    v = os.environ.get(name, "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _log(msg: str) -> None:
    print(f"[dinobase] {msg}", file=sys.stderr)
