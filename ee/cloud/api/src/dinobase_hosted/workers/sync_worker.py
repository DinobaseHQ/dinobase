# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Background sync worker — wraps the existing SyncEngine for server-side sync."""

from __future__ import annotations

import os
import sys
from typing import Any

from dinobase_hosted.db import get_profile, update_sync_job
from dinobase_hosted.encryption import decrypt_credentials


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
            update_sync_job(job_id, "error", error_message="No user profile found")
            return

        storage_url = profile["storage_url"]

        # Decrypt credentials
        credentials = decrypt_credentials(source["credentials_encrypted"])

        # Configure environment for the sync engine
        os.environ["DINOBASE_STORAGE_URL"] = storage_url

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
        else:
            update_sync_job(
                job_id, "error",
                error_message=result.error or "Unknown error",
            )

        db.close()

    except Exception as e:
        print(f"Sync job {job_id} failed: {e}", file=sys.stderr)
        update_sync_job(job_id, "error", error_message=str(e))
