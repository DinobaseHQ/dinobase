# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Sync endpoints — trigger syncs, check status."""

from __future__ import annotations

from typing import Any

import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from dinobase_hosted.auth import User, get_current_user
from dinobase_hosted.db import (
    list_user_sources,
    get_user_source,
    create_sync_job,
    get_sync_job,
    get_latest_sync_jobs,
    update_sync_job,
)
from dinobase_hosted.models import SyncRequest
from dinobase_hosted.workers.sync_worker import run_sync_job, request_cancel


router = APIRouter(tags=["sync"])


@router.post("/")
async def trigger_sync(
    body: SyncRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Trigger a sync for one or all sources."""
    if body.source_name:
        source = get_user_source(user.id, body.source_name)
        if not source:
            raise HTTPException(404, f"Source '{body.source_name}' not found")
        sources_to_sync = [source]
    else:
        sources_to_sync = list_user_sources(user.id)

    if not sources_to_sync:
        raise HTTPException(400, "No sources to sync")

    job_ids = []
    run_inline = os.environ.get("DINOBASE_MODE", "all") == "all"
    for source in sources_to_sync:
        job = create_sync_job(user.id, source["source_name"])
        job_ids.append(job["id"])
        if run_inline:
            # all mode: run sync in-process via BackgroundTasks (no worker needed)
            background_tasks.add_task(run_sync_job, job["id"], user.id, source)

    return {
        "job_ids": job_ids,
        "status": "queued",
        "sources": len(sources_to_sync),
    }


@router.get("/status")
async def sync_status(user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    """Get the latest sync status for all sources."""
    sources = list_user_sources(user.id)
    jobs = {j["source_name"]: j for j in get_latest_sync_jobs(user.id)}

    result = []
    for src in sources:
        job = jobs.get(src["source_name"])
        result.append({
            "source": src["source_name"],
            "type": src["source_type"],
            "status": job["status"] if job else "never_synced",
            "last_sync": job["finished_at"] if job else None,
            "tables_synced": job["tables_synced"] if job else 0,
            "rows_synced": job["rows_synced"] if job else 0,
            "error": job.get("error_message") if job else None,
        })
    return result


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Cancel a running sync job. Stops at the next table boundary."""
    job = get_sync_job(job_id)
    if not job or job["user_id"] != user.id:
        raise HTTPException(404, "Job not found")
    if job["status"] not in ("running", "pending"):
        raise HTTPException(400, f"Job is not running (status: {job['status']})")
    request_cancel(job_id)
    update_sync_job(job_id, "cancelled")
    return {"cancelled": True}


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get the status of a specific sync job."""
    job = get_sync_job(job_id)
    if not job or job["user_id"] != user.id:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": job["id"],
        "source": job["source_name"],
        "status": job["status"],
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "tables_synced": job["tables_synced"],
        "tables_total": job.get("tables_total", 0),
        "rows_synced": job["rows_synced"],
        "error": job.get("error_message"),
    }
