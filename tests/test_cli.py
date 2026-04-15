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
    import re
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert re.search(r"\d+\.\d+\.\d+", result.output)


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
    assert "stripe" in config["connectors"]
    # Registry uses the dlt param name "stripe_secret_key"
    assert config["connectors"]["stripe"]["credentials"]["stripe_secret_key"] == "sk_test_123"


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
    assert "stripe_prod" in config["connectors"]


def test_status_no_data(runner):
    runner.invoke(cli, ["init"])
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    # JSON output by default — empty connectors list
    assert "connectors" in result.output


def test_query_direct(runner):
    runner.invoke(cli, ["init"])
    result = runner.invoke(cli, ["query", "SELECT 42 as answer"])
    assert result.exit_code == 0
    assert "42" in result.output


def test_sync_no_sources(runner):
    runner.invoke(cli, ["init"])
    result = runner.invoke(cli, ["sync"])
    assert result.exit_code == 1
    assert "No connectors configured" in result.output


def test_mcp_config(runner):
    result = runner.invoke(cli, ["mcp-config"])
    assert result.exit_code == 0
    assert "mcpServers" in result.output
    assert "dinobase" in result.output


# ---------------------------------------------------------------------------
# install command
# ---------------------------------------------------------------------------


def test_install_claude_code(runner, tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    result = runner.invoke(cli, ["install", "claude-code"])
    assert result.exit_code == 0

    target = tmp_path / ".claude" / "CLAUDE.md"
    assert target.exists()
    text = target.read_text()
    assert "<dinobase>" in text
    assert "</dinobase>" in text
    assert "dinobase info" in text


def test_install_claude_code_idempotent(runner, tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    target = tmp_path / ".claude" / "CLAUDE.md"
    target.parent.mkdir(parents=True)
    target.write_text("# My global rules\n\n<dinobase>\nold content\n</dinobase>\n\n# Other stuff\n")

    result = runner.invoke(cli, ["install", "claude-code"])
    assert result.exit_code == 0

    text = target.read_text()
    # Old content replaced
    assert "old content" not in text
    # Surrounding content preserved
    assert "# My global rules" in text
    assert "# Other stuff" in text
    # New content present, exactly one block
    assert text.count("<dinobase>") == 1
    assert "dinobase info" in text


def test_install_codex(runner, tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    result = runner.invoke(cli, ["install", "codex"])
    assert result.exit_code == 0

    target = tmp_path / ".codex" / "AGENTS.md"
    assert target.exists()
    text = target.read_text()
    assert "<dinobase>" in text
    assert "dinobase info" in text


def test_install_cursor(runner, tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
    result = runner.invoke(cli, ["install", "cursor"])
    assert result.exit_code == 0
    assert "local" in result.output.lower()

    target = tmp_path / "AGENTS.md"
    assert target.exists()
    text = target.read_text()
    assert "<dinobase>" in text
    assert "dinobase info" in text


def test_install_claude_desktop(runner, tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("sys.platform", "darwin")
    result = runner.invoke(cli, ["install", "claude-desktop"])
    assert result.exit_code == 0

    config_path = tmp_path / "Library/Application Support/Claude/claude_desktop_config.json"
    assert config_path.exists()
    import json
    data = json.loads(config_path.read_text())
    assert "mcpServers" in data
    assert "dinobase" in data["mcpServers"]
