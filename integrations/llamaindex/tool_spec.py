"""Dinobase tool spec for LlamaIndex agents."""

from __future__ import annotations

import json
from typing import Annotated

from llama_index.core.tools import BaseToolSpec

from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine


class DinobaseToolSpec(BaseToolSpec):
    """LlamaIndex tool spec for querying Dinobase.

    Provides tools to query business data synced from 100+ SaaS APIs,
    databases, and files into a local DuckDB database.

    Usage:
        from integrations.llamaindex.tool_spec import DinobaseToolSpec

        tool_spec = DinobaseToolSpec()
        tools = tool_spec.to_tool_list()
    """

    spec_functions = [
        "dinobase_query",
        "dinobase_list_connectors",
        "dinobase_describe",
        "dinobase_refresh",
    ]

    def __init__(self, engine: QueryEngine | None = None):
        self._engine = engine

    @property
    def engine(self) -> QueryEngine:
        if self._engine is None:
            db = DinobaseDB()
            self._engine = QueryEngine(db)
        return self._engine

    def dinobase_query(
        self,
        sql: Annotated[str, "SQL query to execute (DuckDB dialect). Reference tables as schema.table."],
        max_rows: Annotated[int, "Maximum rows to return (default 200, max 10000)."] = 200,
    ) -> str:
        """Execute a SQL query against Dinobase (DuckDB dialect).

        Use this to query business data from connected connectors. Tables are
        referenced as schema.table (e.g., stripe.customers, hubspot.contacts).
        Cross-connector JOINs work via shared columns like email.
        """
        result = self.engine.execute(sql, max_rows=max_rows)
        return json.dumps(result, indent=2, default=str)

    def dinobase_list_connectors(self) -> str:
        """List all connected Dinobase data connectors with tables, row counts, and freshness.

        Use this first to understand what business data is available before writing queries.
        """
        result = self.engine.list_connectors()
        return json.dumps(result, indent=2, default=str)

    def dinobase_describe(
        self,
        table: Annotated[str, "Table reference as schema.table (e.g., stripe.customers)."],
    ) -> str:
        """Describe a table's columns, types, annotations, and sample data.

        Use this before writing queries to understand column names and types.
        """
        result = self.engine.describe_table(table)
        return json.dumps(result, indent=2, default=str)

    def dinobase_refresh(
        self,
        connector_name: Annotated[str, "Name of the connector to refresh (e.g., stripe, hubspot)."],
    ) -> str:
        """Re-sync a connector to get fresh data.

        Use when data might be stale and you need up-to-date results.
        """
        from dinobase.config import get_connectors
        from dinobase.sync.engine import SyncEngine

        connectors = get_connectors()
        if connector_name not in connectors:
            return json.dumps({"error": f"Connector '{connector_name}' not found. Available: {', '.join(connectors.keys())}"})

        config = connectors[connector_name]
        if config.get("type") in ("parquet", "csv"):
            return json.dumps({"error": "File connectors read live data — no refresh needed."})

        sync_engine = SyncEngine(self.engine.db)
        result = sync_engine.sync(connector_name, config)
        freshness = self.engine.get_freshness(connector_name)

        return json.dumps({
            "connector": connector_name,
            "status": result.status,
            "tables_synced": result.tables_synced,
            "rows_synced": result.rows_synced,
            "error": result.error,
            "freshness": freshness,
        }, indent=2, default=str)
