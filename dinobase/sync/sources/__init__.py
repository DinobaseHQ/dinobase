"""Source connectors for Dinobase.

Resolution order:
1. YAML config (src/dinobase/sync/sources/configs/<name>.yaml) → dlt rest_api_source
2. Registry entry (dlt verified source or built-in) → import and call
3. File sources (parquet, csv) → handled separately, no dlt pipeline

YAML configs are preferred because they support the full spec (incremental,
nested resources, write endpoints, resource selection).
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

from dinobase.sync.registry import get_source_entry
from dinobase.sync.yaml_source import load_yaml_config, build_dlt_source


def get_source(
    source_type: str,
    credentials: dict[str, str],
    resource_names: list[str] | None = None,
    extra_skip_tables: list[str] | None = None,
) -> Any:
    """Return a dlt source for the given source type.

    Args:
        source_type: Source name (e.g., "hubspot", "stripe", "amplitude")
        credentials: Credential values from user config
        resource_names: Optional list of resources to sync (None = all)
        extra_skip_tables: Additional tables to exclude on top of engine-type filtering.
            Used during recovery to skip tables that caused extraction errors.
    """
    # File sources don't use dlt
    if source_type in ("parquet", "csv"):
        raise ValueError(
            f"File sources ({source_type}) don't use the sync engine. "
            f"Use `dinobase add {source_type} --path ...` instead."
        )

    # 1. Try YAML config first (full spec support)
    yaml_config = load_yaml_config(source_type)
    if yaml_config and "client" in yaml_config:
        print(f"  Using YAML config: configs/{source_type}.yaml", file=sys.stderr)
        return build_dlt_source(source_type, credentials, resource_names)

    # 2. Fall back to registry (dlt verified sources / built-in sources)
    entry = get_source_entry(source_type)
    if entry is None:
        from dinobase.sync.registry import list_available_sources
        available = ", ".join(list_available_sources())
        raise ValueError(f"Unknown source type: {source_type}. Available: {available}")

    # Verified sources (import_path = "sources.X.Y") aren't on PyPI — they live
    # in dlt-hub/verified-sources and are meant to be copied into a project via
    # `dlt init`. Fetch the requested source on demand and install its
    # requirements.txt before importing.
    module_path, func_name = entry.import_path.rsplit(".", 1)
    if module_path.startswith("sources."):
        from dinobase.sync.source_fetch import ensure_verified_source
        verified_source_name = module_path.split(".", 2)[1]
        try:
            ensure_verified_source(verified_source_name)
        except Exception as e:
            raise ImportError(
                f"Could not prepare verified source '{source_type}': {e}"
            ) from e
    else:
        # Built-in dlt sources / dinobase-internal modules: just check the
        # registry's pip_extra hint. Some pip package names differ from their
        # importable module names.
        _PIP_TO_MODULE: dict[str, str] = {
            "snowflake-sqlalchemy": "snowflake.sqlalchemy",
            "databricks-sql-connector": "databricks.sql",
            "google-api-python-client": "googleapiclient",
            "google-analytics-data": "google.analytics.data",
            "google-ads": "google.ads.googleads",
            "facebook_business": "facebook_business",
            "confluent_kafka": "confluent_kafka",
            "oracledb": "oracledb",
        }
        if entry.pip_extra:
            module_name = _PIP_TO_MODULE.get(
                entry.pip_extra, entry.pip_extra.replace("-", "_")
            )
            try:
                importlib.import_module(module_name)
            except ImportError as _e:
                # Only surface the friendly error when the package is genuinely absent.
                # Some installed packages (e.g. sqlalchemy-redshift) have broken
                # internal imports that would cause a false "not installed" message.
                if "No module named" in str(_e):
                    raise ImportError(
                        f"Source '{source_type}' requires an extra package. "
                        f"Install it with: pip install {entry.pip_extra}"
                    )

    # Import the source function
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise ImportError(
            f"Could not import source '{source_type}' from {module_path}: {e}"
        )
    source_func = getattr(module, func_name)

    # Map credentials to the source function's parameter names
    kwargs = dict(entry.extra_params)
    if entry.import_path == "dlt.sources.sql_database.sql_database":
        # Build a SQLAlchemy Engine directly and pass it to sql_database.
        # This bypasses dlt's ConnectionStringCredentials, which only accepts
        # a narrow set of standard drivers and rejects e.g. clickhouse://.
        conn_str = credentials.get("credentials", "").strip()
        # postgres:// was dropped in SQLAlchemy 2.0
        conn_str = conn_str.replace("postgres://", "postgresql://", 1)
        # clickhouse:// / clickhouse+http:// use HTTP (port 8123).
        # Port 9000 is the native TCP port — auto-correct to avoid a confusing
        # "Port 9000 is for clickhouse-client" error.
        if conn_str.startswith(("clickhouse://", "clickhouse+http://")):
            from urllib.parse import urlparse, urlunparse
            _parsed = urlparse(conn_str)
            if _parsed.port == 9000:
                _netloc = _parsed.netloc.replace(":9000", ":8123", 1)
                conn_str = urlunparse(_parsed._replace(netloc=_netloc))
                print(
                    "  Auto-corrected ClickHouse port 9000→8123 (HTTP). "
                    "Use clickhouse+native:// to keep port 9000.",
                    file=sys.stderr,
                )
        from sqlalchemy import create_engine, String
        from sqlalchemy.engine import make_url

        # ClickHouse returns Python types that are not JSON-serialisable or that
        # overflow DuckDB's INT64:
        #   IPv4/IPv6  → ipaddress.IPv4Address / IPv6Address
        #   UUID       → uuid.UUID
        #   Enum8/16   → Python enum objects (e.g. <QueryFinish: 2>)
        #   UInt64     → Python int, but values can exceed INT64_MAX → DuckDB cast error
        #   UInt128/256, Int128/256 → same overflow problem
        #
        # Fix: table_adapter_callback patches the reflected column types with a
        # TypeDecorator that normalises all these to plain strings.
        # (type_adapter_callback only changes the dlt schema, not SQLAlchemy result
        #  processing — table_adapter_callback is the right hook for data-level coercion.)
        if source_type in ("clickhouse",):
            import enum as _enum_mod
            from sqlalchemy.types import TypeDecorator

            class _AsString(TypeDecorator):
                """Normalise non-serialisable ClickHouse driver values to str."""
                impl = String
                cache_ok = True

                def process_result_value(self, value, dialect):  # type: ignore[override]
                    if value is None:
                        return None
                    if isinstance(value, _enum_mod.Enum):
                        return value.name  # e.g. "QueryFinish" not "<QueryFinish: 2>"
                    if isinstance(value, (list, dict)):
                        import json as _json
                        try:
                            return _json.dumps(value, default=str)
                        except Exception:
                            return str(value)
                    return str(value)

            # Types whose Python driver values are not safely JSON-serialisable or
            # that overflow DuckDB's INT64.
            _COERCE_TO_STR = {
                # Non-serialisable identity types
                "IPv4", "IPv6",
                "UUID",
                # Enums
                "Enum8", "Enum16",
                # Large integers that overflow DuckDB INT64
                "UInt64", "UInt128", "UInt256",
                "Int128", "Int256",
                # String variants
                "FixedString",
                "LowCardinality",
                # Nullable wraps any of the above — coerce the whole column to str
                # so the inner type doesn't matter (None is preserved as NULL).
                "Nullable",
                # DateTime64 has sub-second precision and timezone qualifiers that
                # dlt's standard datetime mapping doesn't preserve correctly.
                "DateTime64",
                # Compound / collection types — serialise as JSON strings.
                "Array", "Map", "Tuple", "Nested",
                # Aggregate function columns (e.g. SimpleAggregateFunction(sum, Int64))
                "SimpleAggregateFunction", "AggregateFunction",
                # Decimal types — precision/scale mismatches cause dlt normalize to fail
                # with "Rescaling Decimal value would cause data loss"; coerce to str.
                "Decimal", "Numeric",
            }

            # Populated after engine creation; closed over by _ch_table_adapter
            _ephemeral_columns: dict[str, set[str]] = {}

            def _ch_table_adapter(table):  # type: ignore[return]
                # Remove EPHEMERAL columns — ClickHouse raises UNKNOWN_IDENTIFIER on SELECT
                for col in list(table._columns):
                    if col.name in _ephemeral_columns.get(table.name, set()):
                        table._columns.remove(col)
                for col in table.columns:
                    if type(col.type).__name__ in _COERCE_TO_STR:
                        col.type = _AsString()

            def _ch_type_adapter(t: object) -> object:
                # Tell dlt to use text in the schema for types we coerce to str.
                # Without this, dlt keeps INT64 in the schema for UInt64 columns and
                # DuckDB tries to cast the string values back to INT64 → overflow.
                if type(t).__name__ in _COERCE_TO_STR:
                    return String()
                return None

            def _ch_query_adapter(query, table, incremental, engine):  # type: ignore[return]
                # Belt-and-suspenders: remove any EPHEMERAL columns that survived to
                # query-generation time (e.g. via restored pipeline schema).
                eph = _ephemeral_columns.get(table.name, set())
                all_cols = list(table.columns)
                col_names = [c.name for c in all_cols]
                bad = [n for n in col_names if n in eph]
                print(
                    f"  [query_adapter] {table.name}: {len(col_names)} cols, "
                    f"ephemeral set={eph or 'empty'}, "
                    f"bad_in_table={bad or 'none'}",
                    file=sys.stderr,
                )
                if not bad:
                    return query
                keep = [c for c in all_cols if c.name not in eph]
                print(
                    f"  [query_adapter] Dropping {len(bad)} EPHEMERAL col(s) "
                    f"from SELECT on {table.name}: {bad}",
                    file=sys.stderr,
                )
                try:
                    return query.with_only_columns(*keep, maintain_column_froms=True)
                except TypeError:
                    # SQLAlchemy <2.0 compat
                    return query.with_only_columns(keep)

            kwargs["table_adapter_callback"] = _ch_table_adapter
            kwargs["type_adapter_callback"] = _ch_type_adapter
            kwargs["query_adapter_callback"] = _ch_query_adapter

        _EXAMPLES = {
            "postgres": "postgresql://user:password@host:5432/dbname",
            "mysql": "mysql+pymysql://user:password@host:3306/dbname",
            "mariadb": "mysql+pymysql://user:password@host:3306/dbname",
            "clickhouse": "clickhouse://user:password@host:8123/dbname",
            "snowflake": "snowflake://user:password@account/database/schema?warehouse=WH",
            "bigquery": "bigquery://project/dataset",
            "redshift": "postgresql://user:password@cluster.region.redshift.amazonaws.com:5439/dbname",
            "mssql": "mssql+pyodbc://user:password@host:1433/dbname?driver=ODBC+Driver+17+for+SQL+Server",
            "oracle": "oracle+oracledb://user:password@host:1521/dbname",
            "trino": "trino://user@host:8080/catalog/schema",
            "presto": "presto://user@host:8080/catalog/schema",
            "databricks": "databricks+connector://token:ACCESS_TOKEN@HOST/PATH?http_path=/sql/1.0/warehouses/ID",
        }
        try:
            make_url(conn_str)  # validate before passing to create_engine
        except Exception:
            example = _EXAMPLES.get(source_type, "driver://user:password@host:port/database")
            raise ValueError(
                f"Invalid connection string for '{source_type}'. "
                f"Expected format:\n  {example}"
            )
        _url = make_url(conn_str)
        _pool_kwargs: dict = {}
        if _url.drivername and not _url.drivername.startswith("sqlite"):
            # NullPool creates a fresh connection per request so concurrent table
            # extraction doesn't exhaust a fixed-size pool when many tables are
            # pulled in parallel.
            from sqlalchemy.pool import NullPool
            _pool_kwargs = {"poolclass": NullPool}
        engine = create_engine(conn_str, **_pool_kwargs)
        kwargs["credentials"] = engine

        # For ClickHouse: skip tables whose engines don't support direct SELECT
        # (Kafka, RabbitMQ, NATS, S3Queue — reading would consume the queue).
        # We discover these via system.tables before building the dlt source so
        # dlt never even tries to extract them.
        _effective_resources = resource_names
        if source_type == "clickhouse" and resource_names is None:
            try:
                from sqlalchemy import text as _sql_text
                _db = make_url(conn_str).database or "default"
                # Engines that must not be directly SELECTed:
                #   Kafka / RabbitMQ / NATS / S3Queue  — consuming reads from a queue
                #   Distributed   — routing layer; querying it may timeout trying to
                #                   reach remote shards; the underlying sharded tables
                #                   hold the actual data
                #   MaterializedView / View — virtual; underlying tables have the data
                #   Dictionary    — in-memory lookup tables; too large to bulk-export
                #   Buffer        — write buffer; rows are in-flight, not stable
                _SKIP_ENGINES = (
                    "Kafka", "RabbitMQ", "RabbitMQNew", "NATS", "S3Queue",
                    "Distributed",
                    "MaterializedView", "View",
                    "Dictionary",
                    "Buffer",
                )
                _engines_csv = ", ".join(f"'{e}'" for e in _SKIP_ENGINES)
                with engine.connect() as _conn:
                    _rows = _conn.execute(_sql_text(
                        f"SELECT name, engine FROM system.tables "
                        f"WHERE database = '{_db}' AND engine IN ({_engines_csv})"
                    )).fetchall()
                _skip = {r[0] for r in _rows}
                if _skip:
                    # Build full table list minus the skipped ones
                    from sqlalchemy import inspect as _inspect
                    _all = _inspect(engine).get_table_names()
                    _effective_resources = [t for t in _all if t not in _skip]
                    print(
                        f"  Skipping {len(_skip)} non-data tables "
                        f"(Kafka/Distributed/View/MaterializedView/Dictionary); "
                        f"syncing {len(_effective_resources)} data tables.",
                        file=sys.stderr,
                    )
            except Exception as _e:
                print(f"  Warning: could not query system.tables to filter engine types: {_e}", file=sys.stderr)

        # For ClickHouse: pre-load columns that cannot appear in SELECT:
        #   EPHEMERAL: only exists at INSERT time, never stored
        #   ALIAS referencing an EPHEMERAL: re-evaluated at SELECT time using the
        #     ephemeral expression → ClickHouse raises UNKNOWN_IDENTIFIER
        if source_type == "clickhouse":
            try:
                from sqlalchemy import text as _sql_text
                _db = make_url(conn_str).database or "default"
                with engine.connect() as _conn:
                    # Fetch EPHEMERAL columns and ALIAS columns together
                    _col_rows = _conn.execute(_sql_text(
                        f"SELECT table, name, default_kind, default_expression "
                        f"FROM system.columns "
                        f"WHERE database = '{_db}' "
                        f"AND default_kind IN ('EPHEMERAL', 'ALIAS')"
                    )).fetchall()
                # First pass: collect all EPHEMERAL column names per table
                for _tbl, _col, _dtype, _expr in _col_rows:
                    if _dtype == "EPHEMERAL":
                        _ephemeral_columns.setdefault(_tbl, set()).add(_col)
                # Second pass: any ALIAS whose expression references an EPHEMERAL col
                # is also unsafe to SELECT (ClickHouse re-evaluates it at query time)
                for _tbl, _col, _dtype, _expr in _col_rows:
                    if _dtype == "ALIAS":
                        _eph = _ephemeral_columns.get(_tbl, set())
                        if any(_eph_col in (_expr or "") for _eph_col in _eph):
                            _ephemeral_columns.setdefault(_tbl, set()).add(_col)
                if _ephemeral_columns:
                    _total = sum(len(v) for v in _ephemeral_columns.values())
                    print(
                        f"  Filtering {_total} unsafe columns (EPHEMERAL + dependent ALIAS) "
                        f"from {len(_ephemeral_columns)} tables.",
                        file=sys.stderr,
                    )
            except Exception as _e:
                print(
                    f"  Warning: could not query system.columns for unsafe columns: {_e}",
                    file=sys.stderr,
                )

        # Apply extra_skip_tables (used during recovery to exclude tables that
        # caused UNKNOWN_IDENTIFIER or other extraction errors on a previous attempt).
        if extra_skip_tables:
            if _effective_resources is None:
                # No explicit list yet; build one from all tables minus the skip set
                from sqlalchemy import inspect as _inspect
                _all = _inspect(engine).get_table_names()
                _effective_resources = [t for t in _all if t not in extra_skip_tables]
            else:
                _effective_resources = [
                    t for t in _effective_resources if t not in extra_skip_tables
                ]
            print(
                f"  Skipping {len(extra_skip_tables)} table(s) with prior extraction "
                f"errors: {extra_skip_tables}",
                file=sys.stderr,
            )

        source = source_func(**kwargs)
        if _effective_resources is not None and hasattr(source, "with_resources"):
            source = source.with_resources(*_effective_resources)

        # ---------------------------------------------------------------
        # Auto-configure write disposition + incremental cursor per table.
        # dlt defaults to append, which duplicates rows on every sync.
        # We detect cursor columns and merge keys from the schema and apply:
        #   cursor + merge_key → merge (incremental upsert, deduplicates)
        #   otherwise          → replace (full reload, idempotent)
        # ---------------------------------------------------------------
        import dlt as _dlt
        from sqlalchemy import inspect as _sa_inspect, text as _sql_text

        _CURSOR_CANDIDATES = (
            ["_timestamp", "updated_at", "created_at", "version"]
            if source_type == "clickhouse"
            else ["updated_at", "created_at"]
        )
        _MERGE_KEY_FALLBACKS = ["uuid", "id", "query_id", "session_id", "session_id_v7"]

        # 1. Discover which tables have which cursor column (one DB round-trip per candidate)
        _cursor_map: dict[str, str] = {}
        try:
            with engine.connect() as _cur_conn:
                _db_name = make_url(conn_str).database or "default"
                for _cand in _CURSOR_CANDIDATES:
                    if source_type == "clickhouse":
                        _crows = _cur_conn.execute(_sql_text(
                            f"SELECT DISTINCT `table` FROM system.columns "
                            f"WHERE database='{_db_name}' AND name='{_cand}'"
                        )).fetchall()
                    else:
                        _crows = _cur_conn.execute(_sql_text(
                            f"SELECT table_name FROM information_schema.columns "
                            f"WHERE column_name='{_cand}' "
                            f"AND table_schema=current_schema()"
                        )).fetchall()
                    for (_tbl,) in _crows:
                        if _tbl not in _cursor_map:
                            _cursor_map[_tbl] = _cand
        except Exception as _ce:
            print(f"  Warning: cursor detection failed: {_ce}", file=sys.stderr)

        # 2. Discover merge keys using two bulk queries — avoids one NullPool
        #    connection per table (which was the main source of START latency).
        _merge_key_map: dict[str, list[str]] = {}
        _tables_with_cursors = list(_cursor_map.keys())
        if _tables_with_cursors:
            try:
                _db_name = make_url(conn_str).database or "default"
                with engine.connect() as _mk_conn:
                    if source_type == "clickhouse":
                        # ClickHouse: sort key from system.tables + columns from system.columns
                        _sk_rows = _mk_conn.execute(_sql_text(
                            "SELECT name, sorting_key FROM system.tables "
                            "WHERE database = :db"
                        ), {"db": _db_name}).fetchall()
                        _tables_csv = ", ".join(f"'{t}'" for t in _tables_with_cursors)
                        _col_rows = _mk_conn.execute(_sql_text(
                            f"SELECT table, name FROM system.columns "
                            f"WHERE database = :db AND table IN ({_tables_csv})"
                        ), {"db": _db_name}).fetchall()
                        _tbl_cols_bulk: dict[str, set[str]] = {}
                        for _ct, _cc in _col_rows:
                            _tbl_cols_bulk.setdefault(_ct, set()).add(_cc)
                        for _tbl_name, _sk in _sk_rows:
                            if _tbl_name not in _cursor_map:
                                continue
                            _cols = _tbl_cols_bulk.get(_tbl_name, set())
                            _sk_cols = [c.strip() for c in _sk.split(",")] if _sk else []
                            _pk_cols = [c for c in _sk_cols if c in _cols]
                            if not _pk_cols:
                                _pk_cols = [c for c in _MERGE_KEY_FALLBACKS if c in _cols][:1]
                            if _pk_cols:
                                _merge_key_map[_tbl_name] = _pk_cols
                    else:
                        # PostgreSQL / MySQL: one query for all PKs + one for all column names
                        _pk_rows = _mk_conn.execute(_sql_text(
                            "SELECT kcu.table_name, kcu.column_name "
                            "FROM information_schema.table_constraints tc "
                            "JOIN information_schema.key_column_usage kcu "
                            "  ON tc.constraint_name = kcu.constraint_name "
                            "  AND tc.table_schema = kcu.table_schema "
                            "WHERE tc.constraint_type = 'PRIMARY KEY' "
                            "  AND tc.table_schema = current_schema()"
                        )).fetchall()
                        _pk_bulk: dict[str, list[str]] = {}
                        for _pt, _pc in _pk_rows:
                            _pk_bulk.setdefault(_pt, []).append(_pc)

                        _col_rows = _mk_conn.execute(_sql_text(
                            "SELECT table_name, column_name "
                            "FROM information_schema.columns "
                            "WHERE table_schema = current_schema() "
                            "  AND table_name = ANY(:tables)"
                        ), {"tables": _tables_with_cursors}).fetchall()
                        _tbl_cols_bulk: dict[str, set[str]] = {}
                        for _ct, _cc in _col_rows:
                            _tbl_cols_bulk.setdefault(_ct, set()).add(_cc)

                        for _tbl in _tables_with_cursors:
                            _cols = _tbl_cols_bulk.get(_tbl, set())
                            # Filter PK cols to real column names (ClickHouse-style expression
                            # keys don't apply here, but filter anyway for correctness)
                            _pk_cols = [c for c in _pk_bulk.get(_tbl, []) if c in _cols]
                            if not _pk_cols:
                                _pk_cols = [c for c in _MERGE_KEY_FALLBACKS if c in _cols][:1]
                            if _pk_cols:
                                _merge_key_map[_tbl] = _pk_cols
            except Exception as _ke:
                print(f"  Warning: merge key detection failed: {_ke}", file=sys.stderr)

        # 3. Apply per-resource hints
        _n_merge = _n_replace = 0
        for _rname, _res in source.resources.items():
            _cursor = _cursor_map.get(_rname)
            _mkeys  = _merge_key_map.get(_rname, [])
            if _cursor and _mkeys:
                _res.apply_hints(
                    write_disposition={"disposition": "merge", "strategy": "upsert"},
                    merge_key=_mkeys,
                    incremental=_dlt.sources.incremental(
                        _cursor, on_cursor_value_missing="include"
                    ),
                )
                _n_merge += 1
            else:
                _res.apply_hints(write_disposition="replace")
                _n_replace += 1

        return source
    for param in entry.credentials:
        value = credentials.get(param.name) or credentials.get(param.cli_flag.lstrip("-").replace("-", "_"))
        if not value:
            for config_key in (
                "api_key",
                "token",
                "access_token",
                "connection_string",
                "password",
                "secret_key",
            ):
                if config_key in credentials:
                    value = credentials[config_key]
                    break
        if value:
            kwargs[param.name] = value

    # GraphQL connectors declare user-facing credential fields in YAML
    # (for example `api_key`), but the shared graphql_source expects `token`.
    if entry.graphql_config:
        if "token" not in kwargs:
            for key in ("token", "access_token", "api_key", "secret_key"):
                value = kwargs.get(key) or credentials.get(key)
                if value:
                    kwargs["token"] = value
                    break
        if "token" not in kwargs:
            for param in entry.credentials:
                value = kwargs.get(param.name)
                if value:
                    kwargs["token"] = value
                    break
        for param in entry.credentials:
            if param.name != "token":
                kwargs.pop(param.name, None)
        kwargs.pop("access_token", None)
        kwargs["endpoint"] = entry.graphql_config["endpoint"]
        kwargs["resources"] = entry.graphql_config["resources"]
        if "auth_prefix" in entry.graphql_config:
            kwargs["auth_prefix"] = entry.graphql_config["auth_prefix"]

    # Resource selection for verified sources
    print(f"  Using dlt source: {entry.import_path}", file=sys.stderr)
    source = source_func(**kwargs)

    if resource_names and hasattr(source, "with_resources"):
        source = source.with_resources(*resource_names)

    return source


def extract_metadata(
    source_type: str, credentials: dict[str, str], tables: list[str]
) -> dict[str, dict[str, dict[str, str]]]:
    """Extract column metadata from the source API."""
    entry = get_source_entry(source_type)

    if entry and entry.metadata_openapi_url:
        if source_type == "stripe":
            from dinobase.sync.metadata import extract_stripe_metadata
            return extract_stripe_metadata(credentials.get("api_key", ""), tables)

    if source_type == "hubspot":
        from dinobase.sync.metadata import extract_hubspot_metadata
        api_key = credentials.get("api_key", "")
        if api_key:
            return extract_hubspot_metadata(api_key, tables)

    if source_type in ("postgres", "mysql"):
        from dinobase.sync.metadata import extract_postgres_metadata
        conn_str = credentials.get("connection_string", credentials.get("credentials", ""))
        schema = credentials.get("schema", "public")
        if conn_str:
            return extract_postgres_metadata(conn_str, schema, tables)

    return {}
