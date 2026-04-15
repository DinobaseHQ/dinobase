"""Local custom connector tooling — YAML template builders shared by CLI and GUI."""

from dinobase.connectors.templates import (
    build_mcp_connector_yaml,
    build_rest_connector_yaml,
)

__all__ = ["build_mcp_connector_yaml", "build_rest_connector_yaml"]
