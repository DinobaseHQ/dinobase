"""Cloud storage operations for state persistence, locking, and file management."""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any


class CloudStorage:
    """Minimal cloud file operations using fsspec.

    Supports S3, GCS, Azure, and local filesystem via a unified API.
    fsspec is already a transitive dependency of dlt.
    """

    def __init__(self, storage_url: str):
        self.storage_url = storage_url.rstrip("/") + "/"
        self._fs = None

    @property
    def fs(self):
        if self._fs is None:
            import fsspec

            protocol = self.storage_url.split("://")[0]
            # Map dinobase protocols to fsspec protocols
            proto_map = {"gs": "gcs", "az": "abfs"}
            fs_protocol = proto_map.get(protocol, protocol)
            self._fs = fsspec.filesystem(fs_protocol)
        return self._fs

    def _to_fs_path(self, url: str) -> str:
        """Strip protocol prefix for fsspec operations."""
        return url.split("://", 1)[1] if "://" in url else url

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def list_files(self, remote_url: str, suffix: str = "") -> list[str]:
        """List files under a remote prefix."""
        path = self._to_fs_path(remote_url.rstrip("/"))
        try:
            files = self.fs.ls(path, detail=False)
            if suffix:
                files = [f for f in files if f.endswith(suffix)]
            return files
        except (FileNotFoundError, OSError):
            return []

    def delete_files(self, remote_url: str, exclude: list[str] | None = None) -> int:
        """Delete all files under a prefix, optionally excluding some filenames."""
        exclude = exclude or []
        files = self.list_files(remote_url)
        deleted = 0
        for f in files:
            basename = f.rsplit("/", 1)[-1] if "/" in f else f
            if basename in exclude:
                continue
            try:
                self.fs.rm(f)
                deleted += 1
            except Exception:
                pass
        return deleted

    def write_json(self, remote_url: str, data: dict) -> None:
        """Write a JSON object to a remote path."""
        path = self._to_fs_path(remote_url)
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        if parent:
            self.fs.makedirs(parent, exist_ok=True)
        with self.fs.open(path, "w") as f:
            json.dump(data, f)

    def read_json(self, remote_url: str) -> dict | None:
        """Read a JSON object from a remote path. Returns None if not found."""
        path = self._to_fs_path(remote_url)
        try:
            with self.fs.open(path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, OSError):
            return None

    def upload_dir(self, local_dir: str, remote_url: str) -> int:
        """Upload all files from a local directory to a remote prefix. Returns count."""
        local_path = Path(local_dir)
        if not local_path.exists():
            return 0

        uploaded = 0
        for local_file in local_path.rglob("*"):
            if not local_file.is_file():
                continue
            relative = local_file.relative_to(local_path)
            remote_file = f"{remote_url.rstrip('/')}/{relative}"
            remote_fs_path = self._to_fs_path(remote_file)
            try:
                self.fs.makedirs(self._to_fs_path(remote_file.rsplit("/", 1)[0]), exist_ok=True)
            except Exception:
                pass
            self.fs.put(str(local_file), remote_fs_path)
            uploaded += 1
        return uploaded

    def download_dir(self, remote_url: str, local_dir: str) -> int:
        """Download all files from a remote prefix to a local directory. Returns count."""
        local_path = Path(local_dir)
        remote_prefix = self._to_fs_path(remote_url.rstrip("/"))

        try:
            files = self.fs.ls(remote_prefix, detail=False)
        except (FileNotFoundError, OSError):
            return 0

        downloaded = 0
        for remote_file in files:
            # Get relative path from prefix
            relative = remote_file[len(remote_prefix):].lstrip("/")
            if not relative:
                continue

            local_file = local_path / relative
            local_file.parent.mkdir(parents=True, exist_ok=True)

            try:
                # Check if it's a directory
                if self.fs.isdir(remote_file):
                    # Recurse into subdirectory
                    sub_remote = f"{remote_url.rstrip('/')}/{relative}"
                    sub_local = str(local_file)
                    downloaded += self.download_dir(sub_remote, sub_local)
                else:
                    self.fs.get(remote_file, str(local_file))
                    downloaded += 1
            except Exception:
                pass

        return downloaded

    # ------------------------------------------------------------------
    # Distributed locking
    # ------------------------------------------------------------------

    def acquire_lock(self, source_name: str, ttl: int = 600) -> bool:
        """Try to acquire a sync lock for a source. Returns True if acquired.

        Uses a JSON lock file with TTL. If the lock is older than ttl seconds,
        it's considered stale and will be overwritten.
        """
        lock_url = f"{self.storage_url}_locks/{source_name}.json"
        existing = self.read_json(lock_url)

        if existing:
            age = time.time() - existing.get("timestamp", 0)
            if age < ttl:
                holder = existing.get("hostname", "unknown")
                print(
                    f"  [lock] {source_name} locked by {holder} "
                    f"({int(age)}s ago, ttl={ttl}s)",
                    file=sys.stderr,
                )
                return False

        self.write_json(lock_url, {
            "timestamp": time.time(),
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "source_name": source_name,
        })
        return True

    def release_lock(self, source_name: str) -> None:
        """Release a sync lock."""
        lock_path = self._to_fs_path(
            f"{self.storage_url}_locks/{source_name}.json"
        )
        try:
            self.fs.rm(lock_path)
        except Exception:
            pass
