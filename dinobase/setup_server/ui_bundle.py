"""Abstraction over "where does the setup UI come from".

A `UIBundle` unifies three backends:

- `bundled`  — `importlib.resources` inside the installed wheel (offline floor)
- `cache`    — a directory under `~/.dinobase/setup-ui-cache/<version>/files/`
- `dir`      — an arbitrary disk path (DINOBASE_SETUP_UI_DIR dev mode)

The setup server's static-asset handler calls `ui_bundle.read(relative_path)`
without caring which backend is active.
"""

from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path
from typing import Iterable, Literal


BundleKind = Literal["bundled", "remote", "dev"]


_MIME_BY_SUFFIX = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


class UIBundle:
    """Resolved UI source for the setup server.

    Attributes
    ----------
    kind    : how the bundle was obtained
    version : UI semver ("dev" for dir mode, "bundled" for wheel floor)
    """

    def __init__(self, kind: BundleKind, version: str, root_path: Path | None = None) -> None:
        self.kind = kind
        self.version = version
        self._root_path = root_path  # None => bundled (importlib.resources)

    def __repr__(self) -> str:  # pragma: no cover
        return f"UIBundle(kind={self.kind!r}, version={self.version!r})"

    def read(self, relative_path: str) -> tuple[bytes, str] | None:
        """Return (body, content_type) or None if not found / traversal attempt."""
        rel = (relative_path or "").lstrip("/")
        parts: Iterable[str] = Path(rel).parts
        if any(p in ("..", "") for p in parts):
            return None

        if self._root_path is None:
            return _read_from_package(parts)
        return _read_from_dir(self._root_path, parts)

    def list_dir(self, relative_dir: str, suffix: str = "") -> list[str]:
        """Return sorted filenames inside a subdirectory of the bundle.

        `suffix` optionally filters by extension (e.g. ".svg") and is stripped
        from the returned names. Rejects traversal segments. Returns [] if the
        directory is missing.
        """
        rel = (relative_dir or "").strip("/")
        parts = [p for p in Path(rel).parts if p not in ("", ".")]
        if any(p == ".." for p in parts):
            return []

        if self._root_path is None:
            return _list_from_package(parts, suffix)
        return _list_from_dir(self._root_path, parts, suffix)

    # ---- factories ----

    @classmethod
    def bundled(cls) -> "UIBundle":
        version = _bundled_version()
        return cls("bundled", version, root_path=None)

    @classmethod
    def from_cache(cls, cache_root: Path, ui_version: str) -> "UIBundle":
        root = cache_root / ui_version / "files"
        return cls("remote", ui_version, root_path=root)

    @classmethod
    def from_dir(cls, disk_path: Path, ui_version: str = "dev") -> "UIBundle":
        return cls("dev", ui_version, root_path=disk_path)


def _read_from_package(parts: Iterable[str]) -> tuple[bytes, str] | None:
    root = files("dinobase.setup_server") / "ui"
    target = root
    for part in parts:
        target = target / part
    with as_file(target) as path:
        if not path.exists() or not path.is_file():
            return None
        body = path.read_bytes()
        suffix = path.suffix.lower()
    return body, _MIME_BY_SUFFIX.get(suffix, "application/octet-stream")


def _list_from_package(parts: Iterable[str], suffix: str) -> list[str]:
    root = files("dinobase.setup_server") / "ui"
    target = root
    for part in parts:
        target = target / part
    try:
        with as_file(target) as path:
            if not path.is_dir():
                return []
            names = [p.name for p in path.iterdir() if p.is_file()]
    except (FileNotFoundError, NotADirectoryError):
        return []
    if suffix:
        names = [n[: -len(suffix)] for n in names if n.endswith(suffix)]
    return sorted(names)


def _list_from_dir(root: Path, parts: Iterable[str], suffix: str) -> list[str]:
    target = root
    for part in parts:
        target = target / part
    try:
        real = target.resolve()
        if not real.is_dir():
            return []
        if not str(real).startswith(str(root.resolve()) + "/") and real != root.resolve():
            return []
        names = [p.name for p in real.iterdir() if p.is_file()]
    except OSError:
        return []
    if suffix:
        names = [n[: -len(suffix)] for n in names if n.endswith(suffix)]
    return sorted(names)


def _read_from_dir(root: Path, parts: Iterable[str]) -> tuple[bytes, str] | None:
    target = root
    for part in parts:
        target = target / part
    try:
        real = target.resolve()
        if not real.is_file():
            return None
        # Defense in depth: refuse to serve files outside the bundle root.
        if not str(real).startswith(str(root.resolve()) + "/") and real != root.resolve():
            return None
        body = real.read_bytes()
    except OSError:
        return None
    suffix = real.suffix.lower()
    return body, _MIME_BY_SUFFIX.get(suffix, "application/octet-stream")


def _bundled_version() -> str:
    """Read the UI version baked into the wheel (from ui_meta.json)."""
    try:
        meta_ref = files("dinobase.setup_server") / "ui" / "ui_meta.json"
        with as_file(meta_ref) as path:
            if not path.exists():
                return "0.0.0"
            import json
            data = json.loads(path.read_text())
        v = data.get("ui_version")
        return str(v) if v else "0.0.0"
    except Exception:
        return "0.0.0"
