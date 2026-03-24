"""Generic GraphQL dlt source with Relay-style cursor pagination.

Supports any GraphQL API that uses the Relay connection pattern
(nodes/pageInfo/hasNextPage/endCursor). Each resource config specifies
a query with a $cursor variable, a data_path to extract results, and
a cursor_path to find pagination info.
"""

from __future__ import annotations

from typing import Any, Iterable

import dlt
import requests
from dlt.sources import DltResource


def _traverse(obj: dict, dotted_path: str) -> Any:
    """Navigate a nested dict by dot-separated keys.

    >>> _traverse({"a": {"b": [1, 2]}}, "a.b")
    [1, 2]
    """
    for key in dotted_path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)  # type: ignore[assignment]
    return obj


def _paginate(
    endpoint: str,
    headers: dict[str, str],
    query: str,
    variables: dict[str, Any],
    data_path: str,
    cursor_path: str | None,
) -> Iterable[dict]:
    """Execute a GraphQL query with Relay cursor pagination, yielding each node."""
    cursor: str | None = None

    while True:
        vars_with_cursor = {**variables}
        if cursor is not None:
            vars_with_cursor["cursor"] = cursor

        resp = requests.post(
            endpoint,
            json={"query": query, "variables": vars_with_cursor},
            headers=headers,
            timeout=60,
        )
        resp.raise_for_status()
        body = resp.json()

        if "errors" in body and body["errors"]:
            msgs = "; ".join(e.get("message", str(e)) for e in body["errors"])
            raise RuntimeError(f"GraphQL errors: {msgs}")

        nodes = _traverse(body, data_path)
        if not nodes:
            break

        yield from nodes

        if not cursor_path:
            break

        page_info = _traverse(body, cursor_path)
        if not page_info or not page_info.get("hasNextPage"):
            break

        cursor = page_info.get("endCursor")
        if not cursor:
            break


def _make_resource(
    name: str,
    endpoint: str,
    headers: dict[str, str],
    query: str,
    data_path: str,
    cursor_path: str | None,
    variables: dict[str, Any],
    primary_key: str,
) -> DltResource:
    """Build a dlt resource for a single GraphQL query."""

    def _fetch() -> Iterable[dict]:
        yield from _paginate(endpoint, headers, query, variables, data_path, cursor_path)

    return dlt.resource(
        _fetch,
        name=name,
        write_disposition="merge",
        primary_key=primary_key,
    )


@dlt.source
def graphql_source(
    endpoint: str,
    token: str,
    resources: list[dict[str, Any]],
    auth_prefix: str = "Bearer ",
) -> Iterable[DltResource]:
    """Generic GraphQL dlt source.

    Args:
        endpoint: GraphQL endpoint URL.
        token: Auth token.
        resources: List of resource configs, each with keys:
            name, query, data_path, cursor_path (optional), variables (optional).
        auth_prefix: Prefix for the Authorization header (default "Bearer ").
    """
    headers = {
        "Authorization": f"{auth_prefix}{token}",
        "Content-Type": "application/json",
    }

    for res_cfg in resources:
        yield _make_resource(
            name=res_cfg["name"],
            endpoint=endpoint,
            headers=headers,
            query=res_cfg["query"],
            data_path=res_cfg["data_path"],
            cursor_path=res_cfg.get("cursor_path"),
            variables=dict(res_cfg.get("variables", {})),
            primary_key=res_cfg.get("primary_key", "id"),
        )
