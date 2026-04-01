# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Background sync worker — wraps the existing SyncEngine for server-side sync."""

from __future__ import annotations

import os
import sys
from typing import Any

from dinobase_hosted.db import get_profile, update_sync_job
from dinobase_hosted.storage import ensure_user_storage
from dinobase_hosted.encryption import decrypt_credentials


def _classify_error(error: str, source_name: str) -> str:
    """Return a user-friendly error message based on the raw error string."""
    e = error.lower()
    if any(x in e for x in ("401", "403", "unauthorized", "forbidden", "invalid api key", "invalid token", "authentication failed")):
        return "Credentials invalid or expired. Click 'Edit credentials' to update."
    if any(x in e for x in ("429", "rate limit", "too many requests", "quota exceeded")):
        return f"Rate limited by {source_name}. Try again in a few minutes."
    if any(x in e for x in ("connection refused", "connection error", "cannot connect", "failed to connect", "no route to host", "network unreachable")):
        return f"Could not connect to {source_name}. Check your credentials and network."
    if any(x in e for x in ("timeout", "timed out", "read timeout", "connect timeout")):
        return f"Connection to {source_name} timed out. The service may be temporarily unavailable."
    if "ssl" in e or "certificate" in e:
        return f"SSL error connecting to {source_name}. Check your network."
    return error


def run_sync_job(job_id: str, user_id: str, source: dict[str, Any]) -> None:
    """Run a sync job in the background.

    This wraps the existing dinobase SyncEngine so we reuse all the
    dlt pipeline logic, pagination, auth, incremental loading, etc.
    """
    source_name = source["source_name"]
    source_type = source["source_type"]

    # Mark as running
    update_sync_job(job_id, "running")

    try:
        # Get user's storage URL
        profile = get_profile(user_id)
        if not profile:
            storage_url = ensure_user_storage(user_id)
        else:
            storage_url = profile["storage_url"]

        # In local dev, use a per-user local DuckDB file instead of S3.
        # Set DINOBASE_LOCAL_STORAGE_ROOT=/some/path in .env to skip S3.
        local_root = os.environ.get("DINOBASE_LOCAL_STORAGE_ROOT")
        if local_root:
            user_dir = os.path.join(local_root.rstrip("/"), user_id)
            os.makedirs(user_dir, exist_ok=True)
            os.environ["DINOBASE_DIR"] = user_dir
            os.environ.pop("DINOBASE_STORAGE_URL", None)
        else:
            os.environ["DINOBASE_STORAGE_URL"] = storage_url

        # Decrypt credentials
        credentials = decrypt_credentials(source["credentials_encrypted"])

        # Build source config matching what SyncEngine expects
        source_config: dict[str, Any] = {
            "type": source_type,
            "credentials": credentials,
        }

        # Import and run the sync engine
        from dinobase.db import DinobaseDB
        from dinobase.sync.engine import SyncEngine

        db = DinobaseDB()
        engine = SyncEngine(db)

        result = engine.sync(source_name, source_config)

        if result.status == "success":
            update_sync_job(
                job_id, "success",
                tables_synced=result.tables_synced,
                rows_synced=result.rows_synced,
            )
            from dinobase.semantic_agent import spawn_semantic_agent
            spawn_semantic_agent(source_name)
        else:
            raw_error = result.error or "Unknown error"
            print(f"Sync job {job_id} error: {raw_error}", file=sys.stderr)
            update_sync_job(
                job_id, "error",
                error_message=_classify_error(raw_error, source_name),
            )

        db.close()

    except Exception as e:
        raw_error = str(e)
        print(f"Sync job {job_id} failed: {raw_error}", file=sys.stderr)
        update_sync_job(job_id, "error", error_message=_classify_error(raw_error, source_name))
