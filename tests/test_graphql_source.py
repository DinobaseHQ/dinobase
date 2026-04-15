"""Tests for the generic GraphQL dlt source."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dinobase.sync.sources.graphql import _traverse, graphql_source


# ---------------------------------------------------------------------------
# _traverse helper
# ---------------------------------------------------------------------------


class TestTraverse:
    def test_simple_path(self):
        assert _traverse({"a": {"b": 1}}, "a.b") == 1

    def test_deep_path(self):
        assert _traverse({"a": {"b": {"c": [1, 2]}}}, "a.b.c") == [1, 2]

    def test_missing_key(self):
        assert _traverse({"a": 1}, "b") is None

    def test_missing_nested_key(self):
        assert _traverse({"a": {"b": 1}}, "a.c") is None

    def test_non_dict_intermediate(self):
        assert _traverse({"a": "string"}, "a.b") is None

    def test_single_key(self):
        assert _traverse({"data": [1, 2, 3]}, "data") == [1, 2, 3]


# ---------------------------------------------------------------------------
# graphql_source
# ---------------------------------------------------------------------------


def _mock_response(data: dict, status_code: int = 200):
    """Build a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    return resp


class TestGraphqlSource:
    def test_produces_named_resources(self):
        """graphql_source yields dlt resources matching config names."""
        resources_cfg = [
            {"name": "issues", "query": "query { issues { nodes { id } } }", "data_path": "data.issues.nodes"},
            {"name": "users", "query": "query { users { nodes { id } } }", "data_path": "data.users.nodes"},
        ]
        source = graphql_source("https://example.com/graphql", "token", resources_cfg)
        names = {r.name for r in source.resources.values()}
        assert names == {"issues", "users"}

    @patch("dinobase.sync.sources.graphql.requests.post")
    def test_single_page(self, mock_post):
        """A resource without cursor_path fetches one page."""
        mock_post.return_value = _mock_response({
            "data": {"items": {"nodes": [{"id": "1"}, {"id": "2"}]}}
        })

        resources_cfg = [
            {"name": "items", "query": "query { items { nodes { id } } }", "data_path": "data.items.nodes"},
        ]
        source = graphql_source("https://example.com/graphql", "tok", resources_cfg)
        items_resource = list(source.resources.values())[0]
        rows = list(items_resource)

        assert rows == [{"id": "1"}, {"id": "2"}]
        assert mock_post.call_count == 1

    @patch("dinobase.sync.sources.graphql.requests.post")
    def test_cursor_pagination(self, mock_post):
        """Pagination follows endCursor until hasNextPage is false."""
        mock_post.side_effect = [
            _mock_response({
                "data": {
                    "issues": {
                        "nodes": [{"id": "1"}],
                        "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                    }
                }
            }),
            _mock_response({
                "data": {
                    "issues": {
                        "nodes": [{"id": "2"}],
                        "pageInfo": {"hasNextPage": False, "endCursor": "cursor2"},
                    }
                }
            }),
        ]

        resources_cfg = [{
            "name": "issues",
            "query": "query($cursor: String) { issues(after: $cursor) { nodes { id } pageInfo { hasNextPage endCursor } } }",
            "data_path": "data.issues.nodes",
            "cursor_path": "data.issues.pageInfo",
        }]
        source = graphql_source("https://example.com/graphql", "tok", resources_cfg)
        rows = list(list(source.resources.values())[0])

        assert rows == [{"id": "1"}, {"id": "2"}]
        assert mock_post.call_count == 2

        # Second call should include cursor variable
        second_call_json = mock_post.call_args_list[1][1]["json"]
        assert second_call_json["variables"]["cursor"] == "cursor1"

    @patch("dinobase.sync.sources.graphql.requests.post")
    def test_graphql_error_raises(self, mock_post):
        """GraphQL errors in response body raise an exception."""
        mock_post.return_value = _mock_response({
            "errors": [{"message": "Unauthorized"}],
            "data": None,
        })

        resources_cfg = [{
            "name": "items",
            "query": "query { items { nodes { id } } }",
            "data_path": "data.items.nodes",
        }]
        source = graphql_source("https://example.com/graphql", "tok", resources_cfg)
        with pytest.raises(Exception, match="Unauthorized"):
            list(list(source.resources.values())[0])

    @patch("dinobase.sync.sources.graphql.requests.post")
    def test_empty_response(self, mock_post):
        """Empty nodes array yields nothing."""
        mock_post.return_value = _mock_response({
            "data": {"items": {"nodes": []}}
        })

        resources_cfg = [{
            "name": "items",
            "query": "query { items { nodes { id } } }",
            "data_path": "data.items.nodes",
        }]
        source = graphql_source("https://example.com/graphql", "tok", resources_cfg)
        rows = list(list(source.resources.values())[0])
        assert rows == []

    @patch("dinobase.sync.sources.graphql.requests.post")
    def test_singleton_object_response(self, mock_post):
        """A singleton object at data_path is wrapped into a single-row result."""
        mock_post.return_value = _mock_response({
            "data": {"viewer": {"id": "usr_1", "name": "Alice"}}
        })

        resources_cfg = [{
            "name": "viewer",
            "query": "query { viewer { id name } }",
            "data_path": "data.viewer",
        }]
        source = graphql_source("https://example.com/graphql", "tok", resources_cfg)
        rows = list(list(source.resources.values())[0])
        assert rows == [{"id": "usr_1", "name": "Alice"}]

    @patch("dinobase.sync.sources.graphql.requests.post")
    def test_auth_prefix(self, mock_post):
        """Custom auth_prefix is used in the Authorization header."""
        mock_post.return_value = _mock_response({
            "data": {"items": {"nodes": []}}
        })

        resources_cfg = [{
            "name": "items",
            "query": "query { items { nodes { id } } }",
            "data_path": "data.items.nodes",
        }]
        graphql_source("https://example.com/graphql", "mykey", resources_cfg, auth_prefix="")
        # Force iteration to trigger the POST
        source = graphql_source("https://example.com/graphql", "mykey", resources_cfg, auth_prefix="")
        list(list(source.resources.values())[0])

        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "mykey"

    @patch("dinobase.sync.sources.graphql.requests.post")
    def test_api_key_alias(self, mock_post):
        """graphql_source accepts api_key as an alias for token."""
        mock_post.return_value = _mock_response({
            "data": {"items": {"nodes": []}}
        })

        resources_cfg = [{
            "name": "items",
            "query": "query { items { nodes { id } } }",
            "data_path": "data.items.nodes",
        }]
        source = graphql_source("https://example.com/graphql", resources=resources_cfg, api_key="mykey", auth_prefix="")
        list(list(source.resources.values())[0])

        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "mykey"


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


class TestLinearRegistration:
    def test_linear_registered(self):
        """Linear is loaded from YAML as a GraphQL source."""
        from dinobase.sync.registry import get_source_entry
        entry = get_source_entry("linear")
        assert entry is not None
        assert entry.graphql_config is not None
        assert entry.graphql_config["endpoint"] == "https://api.linear.app/graphql"
        assert "dinobase.sync.sources.graphql" in entry.import_path

    def test_linear_has_expected_resources(self):
        from dinobase.sync.registry import get_source_entry
        entry = get_source_entry("linear")
        resource_names = {r["name"] for r in entry.graphql_config["resources"]}
        # Must have at least the core resources
        assert {"issues", "projects", "teams", "cycles", "users"}.issubset(resource_names)
        assert len(resource_names) >= 5

    def test_linear_resources_have_queries(self):
        from dinobase.sync.registry import get_source_entry
        entry = get_source_entry("linear")
        for res in entry.graphql_config["resources"]:
            assert "query" in res, f"Resource {res['name']} missing query"
            assert "data_path" in res, f"Resource {res['name']} missing data_path"
            # cursor_path is optional for singleton resources (e.g., viewer)

    @patch("dinobase.sync.sources.graphql.requests.post")
    def test_get_source_maps_api_key_to_graphql_token(self, mock_post):
        from dinobase.sync.sources import get_source

        mock_post.return_value = _mock_response({
            "data": {
                "issues": {
                    "nodes": [],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        })

        source = get_source("linear", {"api_key": "lin_api_test"}, resource_names=["issues"])
        rows = list(source.resources["issues"])

        assert rows == []
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "lin_api_test"

    @patch("dinobase.sync.sources.graphql.requests.post")
    def test_get_source_maps_access_token_to_graphql_token(self, mock_post):
        from dinobase.sync.sources import get_source

        mock_post.return_value = _mock_response({
            "data": {
                "issues": {
                    "nodes": [],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        })

        source = get_source("linear", {"access_token": "oauth_token_test"}, resource_names=["issues"])
        rows = list(source.resources["issues"])

        assert rows == []
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "oauth_token_test"
            # cursor_path is optional for singleton resources (e.g., viewer)
