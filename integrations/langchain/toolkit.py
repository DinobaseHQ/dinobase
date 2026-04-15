"""Dinobase toolkit for LangChain / LangGraph agents."""

from __future__ import annotations

import json

from langchain_core.tools import BaseTool, BaseToolkit
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from dinobase.db import DinobaseDB
from dinobase.query.engine import QueryEngine


class QueryInput(BaseModel):
    sql: str = Field(description="SQL query to execute (DuckDB dialect). Reference tables as schema.table.")
    max_rows: int = Field(default=200, description="Maximum rows to return (1-10000).")


class TableInput(BaseModel):
    table: str = Field(description="Table reference as schema.table (e.g., stripe.customers).")


class ConnectorInput(BaseModel):
    connector_name: str = Field(description="Name of the connector to refresh (e.g., stripe, hubspot).")


class DinobaseToolkit(BaseToolkit):
    """LangChain toolkit for querying Dinobase.

    Provides tools to query business data synced from 100+ SaaS APIs,
    databases, and files into a local DuckDB database.

    Usage:
        from integrations.langchain.toolkit import DinobaseToolkit

        toolkit = DinobaseToolkit()
        tools = toolkit.get_tools()
    """

    engine: QueryEngine | None = None

    class Config:
        arbitrary_types_allowed = True

    def _get_engine(self) -> QueryEngine:
        if self.engine is None:
            db = DinobaseDB()
            self.engine = QueryEngine(db)
        return self.engine

    def get_tools(self) -> list[BaseTool]:
        engine = self._get_engine()

        @tool("dinobase_query", args_schema=QueryInput)
        def dinobase_query(sql: str, max_rows: int = 200) -> str:
            """Execute a SQL query against Dinobase (DuckDB dialect).

            Use this to query business data from connected connectors. Tables are
            referenced as schema.table (e.g., stripe.customers, hubspot.contacts).
            Cross-connector JOINs work via shared columns like email.
            """
            result = engine.execute(sql, max_rows=max_rows)
            return json.dumps(result, indent=2, default=str)

        @tool("dinobase_list_connectors")
        def dinobase_list_connectors() -> str:
            """List all connected Dinobase data connectors with tables, row counts, and freshness.

            Use this first to understand what business data is available.
            """
            result = engine.list_connectors()
            return json.dumps(result, indent=2, default=str)

        @tool("dinobase_describe", args_schema=TableInput)
        def dinobase_describe(table: str) -> str:
            """Describe a table's columns, types, annotations, and sample data.

            Use this before writing queries to understand column names and types.
            """
            result = engine.describe_table(table)
            return json.dumps(result, indent=2, default=str)

        @tool("dinobase_refresh", args_schema=ConnectorInput)
        def dinobase_refresh(connector_name: str) -> str:
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

            sync_engine = SyncEngine(engine.db)
            result = sync_engine.sync(connector_name, config)
            freshness = engine.get_freshness(connector_name)

            return json.dumps({
                "connector": connector_name,
                "status": result.status,
                "tables_synced": result.tables_synced,
                "rows_synced": result.rows_synced,
                "error": result.error,
                "freshness": freshness,
            }, indent=2, default=str)

        return [dinobase_query, dinobase_list_connectors, dinobase_describe, dinobase_refresh]
