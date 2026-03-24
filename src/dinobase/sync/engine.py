"""Sync engine — wraps dlt to load data from sources into DuckDB."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

import dlt

from dinobase.db import DinobaseDB


@dataclass
class SyncResult:
    source_name: str
    source_type: str
    tables_synced: int
    rows_synced: int
    status: str
    error: str | None = None


class SyncEngine:
    def __init__(self, db: DinobaseDB):
        self.db = db

    def sync(self, source_name: str, source_config: dict[str, Any]) -> SyncResult:
        """Sync a single source into DuckDB."""
        source_type = source_config["type"]
        credentials = source_config.get("credentials", {})

        sync_id = self.db.log_sync_start(source_name, source_type)

        try:
            result = self._run_pipeline(source_name, source_type, credentials)

            # Extract metadata from the source API (descriptions, enums, etc.)
            synced_tables = [
                t for t in self.db.get_tables(source_name)
                if not t.startswith("_dlt_")
            ]
            from dinobase.sync.sources import extract_metadata
            annotations = extract_metadata(source_type, credentials, synced_tables)

            self.db.update_table_metadata(source_name, source_name, annotations=annotations)

            # Clear live/staging rows — parquet is now fresh
            self.db.clear_live_rows(source_name)
            for t in synced_tables:
                staging = f"_live_{t}"
                if staging in self.db.get_tables(source_name):
                    try:
                        self.db.conn.execute(f'DELETE FROM "{source_name}"."{staging}"')
                    except Exception:
                        pass

            self.db.log_sync_end(
                sync_id,
                status="success",
                tables_synced=result.tables_synced,
                rows_synced=result.rows_synced,
            )
            return result
        except Exception as e:
            error_msg = str(e)
            self.db.log_sync_end(sync_id, status="error", error_message=error_msg)
            return SyncResult(
                source_name=source_name,
                source_type=source_type,
                tables_synced=0,
                rows_synced=0,
                status="error",
                error=error_msg,
            )

    def _run_pipeline(
        self, source_name: str, source_type: str, credentials: dict[str, str],
        resource_names: list[str] | None = None,
    ) -> SyncResult:
        from dinobase.sync.sources import get_source

        dlt_source = get_source(source_type, credentials, resource_names=resource_names)

        pipeline = dlt.pipeline(
            pipeline_name=f"dinobase_{source_name}",
            destination=dlt.destinations.duckdb(self.db.db_path),
            dataset_name=source_name,
            progress="log",
        )

        print(f"Syncing {source_name} ({source_type})...", file=sys.stderr)
        load_info = pipeline.run(dlt_source)

        # Count tables and rows from load info
        tables_synced = 0
        rows_synced = 0
        if load_info.loads_ids:
            # Query the dataset to count what was loaded
            tables = self.db.get_tables(source_name)
            tables_synced = len([t for t in tables if not t.startswith("_dlt_")])
            for table in tables:
                if not table.startswith("_dlt_"):
                    rows_synced += self.db.get_row_count(source_name, table)

        return SyncResult(
            source_name=source_name,
            source_type=source_type,
            tables_synced=tables_synced,
            rows_synced=rows_synced,
            status="success",
        )
