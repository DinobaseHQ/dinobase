"""Parquet/CSV/file source — creates DuckDB views over external files.

No sync needed. DuckDB reads files at query time via views.
Supports local paths, globs, and S3/GCS URLs.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import duckdb

from dinobase.db import DinobaseDB


def add_file_source(
    db: DinobaseDB,
    source_name: str,
    path: str,
    file_format: str = "parquet",
) -> dict[str, Any]:
    """Register a file source by creating DuckDB views over the files.

    Args:
        db: DinobaseDB instance
        source_name: Schema name for this source (e.g., "analytics")
        path: Path to files — can be:
            - A directory: ./data/events/ (will glob for files)
            - A glob pattern: ./data/events/*.parquet
            - An S3 URL: s3://bucket/prefix/
            - A single file: ./data/export.parquet
        file_format: "parquet" or "csv"

    Returns: dict with tables created and row counts
    """
    db.conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{source_name}"')

    read_fn = "read_parquet" if file_format == "parquet" else "read_csv_auto"
    ext = ".parquet" if file_format == "parquet" else ".csv"

    files = _resolve_files(path, ext)
    if not files:
        raise ValueError(f"No {file_format} files found at '{path}'")

    tables_created = []
    total_rows = 0

    for file_path, table_name in files:
        # Create a staging table for live rows (recently written records).
        # This is a real table with the same schema as the parquet file,
        # so UPDATEs work and UNION ALL is type-safe.
        staging_table = f"_live_{table_name}"
        db.conn.execute(
            f'CREATE TABLE IF NOT EXISTS "{source_name}"."{staging_table}" '
            f"AS SELECT * FROM {read_fn}('{file_path}') WHERE false"
        )

        # Create view that merges parquet + live rows.
        # Live rows (staging table) override parquet rows with the same ID.
        db.conn.execute(
            f'CREATE OR REPLACE VIEW "{source_name}"."{table_name}" AS '
            f'SELECT * FROM "{source_name}"."{staging_table}" '
            f"UNION ALL "
            f"SELECT * FROM {read_fn}('{file_path}') "
            f"WHERE CAST(id AS VARCHAR) NOT IN ("
            f'  SELECT CAST(id AS VARCHAR) FROM "{source_name}"."{staging_table}"'
            f")"
        )

        # Count rows
        try:
            result = db.conn.execute(
                f'SELECT COUNT(*) FROM "{source_name}"."{table_name}"'
            ).fetchone()
            row_count = result[0] if result else 0
        except Exception:
            row_count = 0

        tables_created.append({"name": table_name, "rows": row_count, "path": file_path})
        total_rows += row_count
        print(f"  {source_name}.{table_name}: {row_count:,} rows → {file_path}", file=sys.stderr)

    return {
        "source_name": source_name,
        "tables": tables_created,
        "total_rows": total_rows,
    }


def extract_metadata(
    db: DinobaseDB, source_name: str
) -> dict[str, dict[str, dict[str, str]]]:
    """Extract column metadata from parquet schema.

    Parquet files have column types but no descriptions.
    We can infer basic annotations from column names and types.
    """
    annotations: dict[str, dict[str, dict[str, str]]] = {}
    tables = db.get_tables(source_name)

    for table in tables:
        if table.startswith("_dlt_"):
            continue
        columns = db.get_columns(source_name, table)
        table_anns: dict[str, dict[str, str]] = {}

        for col in columns:
            col_name = col["column_name"]
            col_type = col["data_type"]
            ann = _infer_annotation(col_name, col_type)
            if ann:
                table_anns[col_name] = ann

        if table_anns:
            annotations[table] = table_anns

    return annotations


def _resolve_files(path: str, ext: str) -> list[tuple[str, str]]:
    """Resolve a path into a list of (file_path, table_name) tuples.

    Handles:
    - Single file: ./data/events.parquet → [("./data/events.parquet", "events")]
    - Directory: ./data/ → all .parquet files in it
    - Glob: ./data/*.parquet → matching files
    - S3 URL: s3://bucket/prefix/ → passed through as-is (DuckDB handles S3)
    """
    # S3/GCS URLs — pass through, use the prefix as a single "table"
    if path.startswith("s3://") or path.startswith("gs://"):
        if path.endswith("/"):
            # Directory-like URL — glob for files
            glob_path = f"{path}*{ext}"
            table_name = path.rstrip("/").split("/")[-1]
            return [(glob_path, table_name)]
        else:
            table_name = _path_to_table_name(path)
            return [(path, table_name)]

    p = Path(path)

    # Single file
    if p.is_file():
        return [(str(p), _path_to_table_name(str(p)))]

    # Directory — find all matching files
    if p.is_dir():
        files = sorted(p.glob(f"*{ext}"))
        if not files:
            # Try recursive
            files = sorted(p.rglob(f"*{ext}"))
        return [(str(f), _path_to_table_name(str(f))) for f in files]

    # Glob pattern
    parent = p.parent
    pattern = p.name
    if parent.exists():
        files = sorted(parent.glob(pattern))
        return [(str(f), _path_to_table_name(str(f))) for f in files]

    return []


def _path_to_table_name(path: str) -> str:
    """Convert a file path to a clean table name."""
    name = Path(path).stem  # filename without extension
    # Clean up: replace hyphens/spaces with underscores, lowercase
    name = name.replace("-", "_").replace(" ", "_").lower()
    # Remove common prefixes that aren't meaningful
    for prefix in ("stripe_", "hubspot_", "export_", "data_"):
        if name.startswith(prefix) and len(name) > len(prefix):
            name = name[len(prefix):]
            break
    return name


def _infer_annotation(col_name: str, col_type: str) -> dict[str, str] | None:
    """Infer basic annotations from column name and type.

    This is a fallback for sources without API metadata.
    Keep it conservative — only annotate what we're confident about.
    """
    name_lower = col_name.lower()
    ann: dict[str, str] = {}

    # Timestamp columns
    if name_lower in ("created_at", "updated_at", "deleted_at", "timestamp", "ts"):
        ann["description"] = name_lower.replace("_", " ").title()
    elif name_lower.endswith("_at") and "TIME" in col_type.upper():
        ann["description"] = name_lower.replace("_", " ").replace(" at", " timestamp").title()

    # ID columns
    if name_lower == "id":
        ann["description"] = "Primary key"
    elif name_lower.endswith("_id"):
        ref = name_lower[:-3].replace("_", " ")
        ann["description"] = f"Foreign key"
        ann["note"] = f"Likely references {ref} table"

    # Email
    if name_lower == "email":
        ann["description"] = "Email address"
        ann["note"] = "Potential join key across sources"

    return ann if ann else None
