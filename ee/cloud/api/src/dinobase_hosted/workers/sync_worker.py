# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Background sync worker — wraps the existing SyncEngine for server-side sync."""

from __future__ import annotations

import os
import sys
import time
from typing import Any

from dinobase_hosted.db import (
    get_profile,
    get_pending_sync_jobs,
    get_sync_job,
    get_user_source,
    update_sync_job,
    update_sync_progress,
)
from dinobase_hosted.storage import ensure_user_storage
from dinobase_hosted.encryption import decrypt_credentials


class _SyncCancelled(Exception):
    pass


def request_cancel(job_id: str) -> None:
    """No-op — the cancel endpoint writes 'cancelled' to Supabase directly.

    The worker checks Supabase at each table boundary via _on_progress, so
    cancellation propagates across processes without in-memory state.
    """


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
    """Run a sync job.

    Called directly via BackgroundTasks in 'all' mode, or by the worker loop
    in 'worker' mode after the job has been claimed (status set to 'running').
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

        if local_root:
            user_dir = os.path.join(local_root.rstrip("/"), user_id)
            os.makedirs(user_dir, exist_ok=True)
            db = DinobaseDB(db_path=os.path.join(user_dir, "dinobase.duckdb"))
        else:
            db = DinobaseDB(storage_url=storage_url)
        engine = SyncEngine(db)

        def _on_progress(tables_synced: int, tables_total: int) -> None:
            # Check Supabase for cancellation — works across processes since the
            # cancel endpoint writes directly to the DB rather than a local flag.
            try:
                job = get_sync_job(job_id)
                if job and job["status"] == "cancelled":
                    raise _SyncCancelled()
            except _SyncCancelled:
                raise
            except Exception:
                pass  # DB errors don't interrupt the sync

            try:
                update_sync_progress(job_id, tables_synced, tables_total)
            except Exception:
                pass  # progress updates are best-effort; never fail the sync

        result = engine.sync(source_name, source_config, on_progress=_on_progress)

        if result.status == "success":
            update_sync_job(
                job_id, "success",
                tables_synced=result.tables_synced,
                rows_synced=result.rows_synced,
            )
            # Invalidate the cached query DB so the next query re-initialises
            # with the fresh parquet data.
            if not local_root:
                from dinobase_hosted.routers.query import invalidate_db_cache
                invalidate_db_cache(storage_url)
            try:
                from dinobase.semantic_agent import spawn_semantic_agent
                spawn_semantic_agent(source_name)
            except Exception:
                pass  # semantic annotations are best-effort; don't fail the sync
        else:
            raw_error = result.error or "Unknown error"
            print(f"Sync job {job_id} error: {raw_error}", file=sys.stderr)
            update_sync_job(
                job_id, "error",
                error_message=_classify_error(raw_error, source_name),
            )

        db.close()

    except _SyncCancelled:
        print(f"Sync job {job_id} cancelled by user", file=sys.stderr)
        # DB status was already set to "cancelled" by the API endpoint.
    except Exception as e:
        raw_error = str(e)
        print(f"Sync job {job_id} failed: {raw_error}", file=sys.stderr)
        update_sync_job(job_id, "error", error_message=_classify_error(raw_error, source_name))


def run_worker_loop() -> None:
    """Poll Supabase for pending sync jobs and execute them.

    Runs forever. Each iteration claims all pending jobs (oldest first) and
    runs them sequentially. Jobs that are already 'running' (claimed by another
    worker or a previous crashed run) are skipped.

    Set DINOBASE_SYNC_POLL_INTERVAL (seconds, default 5) to tune latency vs
    Supabase query frequency.
    """
    interval = int(os.environ.get("DINOBASE_SYNC_POLL_INTERVAL", "5"))
    print(f"Sync worker starting (poll interval: {interval}s)", file=sys.stderr)

    while True:
        try:
            for job in get_pending_sync_jobs():
                job_id = job["id"]
                user_id = job["user_id"]
                source_name = job["source_name"]

                source = get_user_source(user_id, source_name)
                if not source:
                    update_sync_job(job_id, "error", error_message=f"Source '{source_name}' not found")
                    continue

                print(f"[worker] running sync job {job_id} ({source_name})", file=sys.stderr)
                run_sync_job(job_id, user_id, source)

        except Exception as e:
            print(f"[worker] error in poll loop: {e}", file=sys.stderr)

        time.sleep(interval)
