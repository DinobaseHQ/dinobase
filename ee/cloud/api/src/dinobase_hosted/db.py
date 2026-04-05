# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Supabase PostgreSQL client for application data."""

from __future__ import annotations

from typing import Any

from supabase import create_client, Client

from dinobase_hosted.config import get_supabase_url, get_supabase_secret_key


_client: Client | None = None


def get_db() -> Client:
    """Get the Supabase client (singleton)."""
    global _client
    if _client is None:
        _client = create_client(get_supabase_url(), get_supabase_secret_key())
    return _client


# -- User profiles --

def get_or_create_profile(user_id: str, storage_url: str) -> dict[str, Any]:
    """Get or create a user profile. Returns the profile row."""
    db = get_db()

    # Try to get existing
    resp = db.table("user_profiles").select("*").eq("user_id", user_id).execute()
    if resp.data:
        return resp.data[0]

    # Create new
    row = {"user_id": user_id, "storage_url": storage_url}
    resp = db.table("user_profiles").insert(row).execute()
    return resp.data[0]


def get_profile(user_id: str) -> dict[str, Any] | None:
    """Get a user profile by ID."""
    db = get_db()
    resp = db.table("user_profiles").select("*").eq("user_id", user_id).execute()
    return resp.data[0] if resp.data else None


# -- User sources --

def list_user_sources(user_id: str) -> list[dict[str, Any]]:
    """List all sources for a user."""
    db = get_db()
    resp = (
        db.table("user_sources")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    return resp.data


def get_user_source(user_id: str, source_name: str) -> dict[str, Any] | None:
    """Get a specific source for a user."""
    db = get_db()
    resp = (
        db.table("user_sources")
        .select("*")
        .eq("user_id", user_id)
        .eq("source_name", source_name)
        .execute()
    )
    return resp.data[0] if resp.data else None


def upsert_user_source(
    user_id: str,
    source_name: str,
    source_type: str,
    auth_method: str,
    credentials_encrypted: str,
    sync_interval: str = "1h",
) -> dict[str, Any]:
    """Insert or update a user source."""
    db = get_db()
    row = {
        "user_id": user_id,
        "source_name": source_name,
        "source_type": source_type,
        "auth_method": auth_method,
        "credentials_encrypted": credentials_encrypted,
        "sync_interval": sync_interval,
    }
    resp = (
        db.table("user_sources")
        .upsert(row, on_conflict="user_id,source_name")
        .execute()
    )
    return resp.data[0]


def rename_user_source(user_id: str, old_name: str, new_name: str) -> bool:
    """Rename a source, updating both user_sources and sync_jobs. Returns True if found."""
    db = get_db()
    resp = (
        db.table("user_sources")
        .update({"source_name": new_name})
        .eq("user_id", user_id)
        .eq("source_name", old_name)
        .execute()
    )
    if not resp.data:
        return False
    db.table("sync_jobs").update({"source_name": new_name}).eq("user_id", user_id).eq("source_name", old_name).execute()
    return True


def delete_user_source(user_id: str, source_name: str) -> bool:
    """Delete a source and its sync history for a user. Returns True if deleted."""
    db = get_db()
    # Clear sync jobs first so re-adding with the same name starts fresh.
    db.table("sync_jobs").delete().eq("user_id", user_id).eq("source_name", source_name).execute()
    resp = (
        db.table("user_sources")
        .delete()
        .eq("user_id", user_id)
        .eq("source_name", source_name)
        .execute()
    )
    return len(resp.data) > 0


# -- Sync jobs --

def create_sync_job(user_id: str, source_name: str) -> dict[str, Any]:
    """Create a pending sync job."""
    db = get_db()
    row = {
        "user_id": user_id,
        "source_name": source_name,
        "status": "pending",
    }
    resp = db.table("sync_jobs").insert(row).execute()
    return resp.data[0]


def update_sync_job(
    job_id: str,
    status: str,
    tables_synced: int = 0,
    rows_synced: int = 0,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Update a sync job's status."""
    from datetime import datetime, timezone
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    update: dict[str, Any] = {"status": status}
    if status == "running":
        update["started_at"] = now
    if status in ("success", "error", "cancelled"):
        update["finished_at"] = now
    if status in ("success", "error"):
        update["tables_synced"] = tables_synced
        update["rows_synced"] = rows_synced
    if error_message:
        update["error_message"] = error_message
    query = db.table("sync_jobs").update(update).eq("id", job_id)
    # Don't overwrite a terminal state (e.g. worker finishing after a cancel)
    if status in ("success", "error"):
        query = query.eq("status", "running")
    resp = query.execute()
    return resp.data[0] if resp.data else {}


def update_sync_progress(job_id: str, tables_synced: int, tables_total: int = 0) -> None:
    """Update tables_synced (and optionally tables_total) mid-sync.

    Uses .eq("status", "running") to avoid clobbering a job already marked
    success/error by a concurrent update.
    """
    db = get_db()
    update: dict[str, Any] = {"tables_synced": tables_synced}
    if tables_total > 0:
        update["tables_total"] = tables_total
    db.table("sync_jobs").update(update).eq("id", job_id).eq("status", "running").execute()


def get_sync_job(job_id: str) -> dict[str, Any] | None:
    """Get a sync job by ID."""
    db = get_db()
    resp = db.table("sync_jobs").select("*").eq("id", job_id).execute()
    return resp.data[0] if resp.data else None


def get_pending_sync_jobs() -> list[dict[str, Any]]:
    """Get all pending sync jobs across all users, oldest first.

    Used by the sync worker to poll for work.
    """
    db = get_db()
    resp = (
        db.table("sync_jobs")
        .select("*")
        .eq("status", "pending")
        .order("created_at")
        .execute()
    )
    return resp.data


def get_latest_sync_jobs(user_id: str) -> list[dict[str, Any]]:
    """Get the latest sync job per source for a user."""
    db = get_db()
    # Get all jobs, ordered by created_at desc, then deduplicate in Python
    resp = (
        db.table("sync_jobs")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )
    seen: set[str] = set()
    latest: list[dict[str, Any]] = []
    for job in resp.data:
        if job["source_name"] not in seen:
            seen.add(job["source_name"])
            latest.append(job)
    return latest
