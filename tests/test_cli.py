"""Tests for the CLI."""

import os

import pytest
from click.testing import CliRunner

from dinobase.cli import cli


@pytest.fixture
def runner(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    return CliRunner()


def test_version(runner):
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_init(runner, tmp_path):
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0
    assert "initialized" in result.output.lower()
    assert (tmp_path / "config.yaml").exists()
    assert (tmp_path / "dinobase.duckdb").exists()


def test_add_stripe(runner, tmp_path):
    runner.invoke(cli, ["init"])
    result = runner.invoke(cli, ["add", "stripe", "--api-key", "sk_test_123"])
    assert result.exit_code == 0
    assert "Added stripe" in result.output

    # Verify config was saved
    import yaml
    with open(tmp_path / "config.yaml") as f:
        config = yaml.safe_load(f)
    assert "stripe" in config["sources"]
    # Registry uses the dlt param name "stripe_secret_key"
    assert config["sources"]["stripe"]["credentials"]["stripe_secret_key"] == "sk_test_123"


def test_add_hubspot(runner):
    runner.invoke(cli, ["init"])
    result = runner.invoke(cli, ["add", "hubspot", "--api-key", "pat-123"])
    assert result.exit_code == 0
    assert "Added hubspot" in result.output


def test_add_postgres(runner):
    runner.invoke(cli, ["init"])
    result = runner.invoke(
        cli, ["add", "postgres", "--connection-string", "postgresql://user:pass@localhost/db"]
    )
    assert result.exit_code == 0
    assert "Added postgres" in result.output


def test_add_with_custom_name(runner, tmp_path):
    runner.invoke(cli, ["init"])
    result = runner.invoke(
        cli, ["add", "stripe", "--api-key", "sk_test_123", "--name", "stripe_prod"]
    )
    assert result.exit_code == 0
    assert "stripe_prod" in result.output

    import yaml
    with open(tmp_path / "config.yaml") as f:
        config = yaml.safe_load(f)
    assert "stripe_prod" in config["sources"]


def test_status_no_data(runner):
    runner.invoke(cli, ["init"])
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    # JSON output by default — empty sources list
    assert "sources" in result.output


def test_query_direct(runner):
    runner.invoke(cli, ["init"])
    result = runner.invoke(cli, ["query", "SELECT 42 as answer"])
    assert result.exit_code == 0
    assert "42" in result.output


def test_sync_no_sources(runner):
    runner.invoke(cli, ["init"])
    result = runner.invoke(cli, ["sync"])
    assert result.exit_code == 1
    assert "No sources configured" in result.output


def test_mcp_config(runner):
    result = runner.invoke(cli, ["mcp-config"])
    assert result.exit_code == 0
    assert "mcpServers" in result.output
    assert "dinobase" in result.output
