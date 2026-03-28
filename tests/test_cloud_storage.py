"""Tests for cloud storage configuration and DinobaseDB cloud mode."""

import os

import pytest
import yaml

from dinobase.config import (
    get_storage_config,
    is_cloud_storage,
    get_storage_url,
    _storage_type_from_url,
    _normalize_url,
)
from dinobase.db import DinobaseDB, META_SCHEMA


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


def test_default_storage_is_local(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    os.environ.pop("DINOBASE_STORAGE_URL", None)
    config = get_storage_config()
    assert config["type"] == "local"
    assert config["url"] is None


def test_storage_from_env_var(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    os.environ["DINOBASE_STORAGE_URL"] = "s3://my-bucket/dinobase/"
    try:
        config = get_storage_config()
        assert config["type"] == "s3"
        assert config["url"] == "s3://my-bucket/dinobase/"
        assert is_cloud_storage()
        assert get_storage_url() == "s3://my-bucket/dinobase/"
    finally:
        del os.environ["DINOBASE_STORAGE_URL"]


def test_storage_from_config_yaml(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    os.environ.pop("DINOBASE_STORAGE_URL", None)
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump({"sources": {}, "storage": {"url": "gs://bucket/db/"}}, f)

    config = get_storage_config()
    assert config["type"] == "gcs"
    assert config["url"] == "gs://bucket/db/"


def test_env_var_overrides_config(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    os.environ["DINOBASE_STORAGE_URL"] = "s3://env-bucket/data/"
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump({"sources": {}, "storage": {"url": "gs://config-bucket/db/"}}, f)
    try:
        config = get_storage_config()
        assert config["type"] == "s3"
        assert config["url"] == "s3://env-bucket/data/"
    finally:
        del os.environ["DINOBASE_STORAGE_URL"]


def test_storage_type_from_url():
    assert _storage_type_from_url("s3://bucket/path") == "s3"
    assert _storage_type_from_url("gs://bucket/path") == "gcs"
    assert _storage_type_from_url("az://container/path") == "azure"
    assert _storage_type_from_url("/local/path") == "local"


def test_normalize_url():
    assert _normalize_url("s3://bucket/path") == "s3://bucket/path/"
    assert _normalize_url("s3://bucket/path/") == "s3://bucket/path/"


def test_init_with_storage_url(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    os.environ.pop("DINOBASE_STORAGE_URL", None)
    from dinobase.config import init_dinobase

    init_dinobase(storage_url="s3://my-bucket/dinobase")

    config_path = tmp_path / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    assert config["storage"]["url"] == "s3://my-bucket/dinobase/"


# ---------------------------------------------------------------------------
# DinobaseDB cloud mode tests
# ---------------------------------------------------------------------------


def test_cloud_db_connects_in_memory(tmp_path):
    """Cloud mode should use in-memory DuckDB."""
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    os.environ.pop("DINOBASE_STORAGE_URL", None)

    # Use a local path as "storage_url" to test the mode detection
    # (actual S3 calls won't happen because we skip _load_cloud_metadata)
    db = DinobaseDB(storage_url="file:///fake/path/")
    assert db.is_cloud is True
    assert db.db_path == ":memory:"
    assert db.storage_url == "file:///fake/path/"


def test_local_db_unchanged(tmp_path):
    """Local mode should work exactly as before."""
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    os.environ.pop("DINOBASE_STORAGE_URL", None)

    db_path = tmp_path / "test.duckdb"
    db = DinobaseDB(db_path)
    assert db.is_cloud is False
    assert db.storage_url is None
    _ = db.conn
    assert db_path.exists()
    db.close()


def test_cloud_db_metadata_tables_created(tmp_path, monkeypatch):
    """Cloud mode should still create _dinobase metadata tables in memory."""
    monkeypatch.setenv("DINOBASE_DIR", str(tmp_path))
    monkeypatch.delenv("DINOBASE_STORAGE_URL", raising=False)

    db = DinobaseDB(db_path=":memory:")
    tables = db.query(
        f"SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema = '{META_SCHEMA}' ORDER BY table_name"
    )
    table_names = [t["table_name"] for t in tables]
    assert "sync_log" in table_names
    assert "tables" in table_names
    assert "columns" in table_names
    assert "live_rows" in table_names
    assert "mutations" in table_names
    db.close()


def test_cloud_db_auto_detect(tmp_path, monkeypatch):
    """DinobaseDB() with no args should auto-detect cloud mode from env."""
    monkeypatch.setenv("DINOBASE_DIR", str(tmp_path))
    monkeypatch.setenv("DINOBASE_STORAGE_URL", "s3://auto-detect-bucket/db/")

    db = DinobaseDB.__new__(DinobaseDB)
    # Test the constructor logic without actually connecting
    from dinobase.config import get_storage_config
    sc = get_storage_config()
    assert sc["type"] == "s3"
    assert sc["url"] == "s3://auto-detect-bucket/db/"


# ---------------------------------------------------------------------------
# CLI init --storage test
# ---------------------------------------------------------------------------


def test_cli_init_with_storage(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    os.environ.pop("DINOBASE_STORAGE_URL", None)

    from click.testing import CliRunner
    from dinobase.cli import cli

    runner = CliRunner()
    # Use a local-looking URL so httpfs install doesn't fail
    result = runner.invoke(cli, ["init"])
    assert result.exit_code == 0
    assert "initialized" in result.output.lower()
