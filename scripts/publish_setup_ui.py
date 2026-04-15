#!/usr/bin/env python3
"""Build the setup-UI tarball + emit release metadata as JSON.

Intended to run in CI (``.github/workflows/release-setup-ui.yml``). Reads
``dinobase/setup_server/ui/ui_meta.json`` to learn the version and backend
compat range, tars the UI directory, computes the SHA-256, and prints a
single-line JSON document that the workflow consumes.

The workflow uses the JSON to:
  - decide on the git tag (``setup-ui-v{ui_version}``)
  - upload the tarball as a release asset
  - prepend an entry to ``ee/cloud/web/public/setup-ui/manifest.json``

Usage:
    python scripts/publish_setup_ui.py --out-dir dist/setup-ui

Outputs (on stdout, one JSON blob):
    {
      "ui_version": "1.0.0",
      "min_backend": "0.2.5",
      "max_backend": null,
      "asset_name": "dinobase-setup-ui-1.0.0.tar.gz",
      "tarball_path": "dist/setup-ui/dinobase-setup-ui-1.0.0.tar.gz",
      "sha256": "abcd..."
    }
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
UI_DIR = REPO_ROOT / "dinobase" / "setup_server" / "ui"
META_FILE = UI_DIR / "ui_meta.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build setup-UI release tarball")
    parser.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / "dist" / "setup-ui"),
        help="Directory where the tarball is written (default: dist/setup-ui)",
    )
    args = parser.parse_args()

    if not META_FILE.is_file():
        print(f"error: {META_FILE} not found", file=sys.stderr)
        return 2

    meta = json.loads(META_FILE.read_text())
    ui_version = meta.get("ui_version")
    if not isinstance(ui_version, str) or not ui_version:
        print("error: ui_meta.json missing ui_version", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    asset_name = f"dinobase-setup-ui-{ui_version}.tar.gz"
    tarball_path = out_dir / asset_name

    # Build a reproducible-ish tarball: sorted entries, fixed uid/gid/mtime.
    # followlinks=True: connector logos live in ``assets/connector-logos`` at
    # the repo root and are symlinked into ``ui/logos`` to dedupe with the
    # marketing site; we want the real files in the tarball.
    files: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(UI_DIR, followlinks=True):
        for fname in filenames:
            files.append(Path(dirpath) / fname)
    files.sort()
    with tarfile.open(tarball_path, "w:gz") as tar:
        for f in files:
            arcname = f.relative_to(UI_DIR).as_posix()
            # Dereference: some leaves (e.g. ``logo.svg``, ``logos/postgresql.svg``)
            # are themselves symlinks into ``assets/``. We need real bytes in the
            # tarball so it's self-contained once extracted client-side.
            info = tar.gettarinfo(str(f.resolve()), arcname=arcname)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            info.mode = 0o644
            with open(f, "rb") as fh:
                tar.addfile(info, fh)

    sha256 = hashlib.sha256(tarball_path.read_bytes()).hexdigest()

    result = {
        "ui_version": ui_version,
        "min_backend": meta.get("min_backend"),
        "max_backend": meta.get("max_backend"),
        "asset_name": asset_name,
        "tarball_path": str(tarball_path),
        "sha256": sha256,
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
