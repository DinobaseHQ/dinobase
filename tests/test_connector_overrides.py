"""Tests for per-connector resource selection and source-factory params.

Covers the gap that issue #14 raised: a user should be able to declaratively
limit which resources a verified-source sync pulls, and pass extra kwargs
(like `start_date`) through to the source factory function.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. Config round-trip
# ---------------------------------------------------------------------------

def test_add_connector_persists_resources_and_params(tmp_path):
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    try:
        from dinobase.config import add_connector, load_config

        add_connector(
            name="freshdesk",
            connector_type="freshdesk",
            credentials={"api_secret_key": "x", "domain": "y"},
            resources=["tickets", "agents"],
            params={"start_date": "2026-03-20T00:00:00Z"},
        )
        cfg = load_config()["connectors"]["freshdesk"]
        assert cfg["resources"] == ["tickets", "agents"]
        assert cfg["params"] == {"start_date": "2026-03-20T00:00:00Z"}
    finally:
        os.environ.pop("DINOBASE_DIR", None)


def test_add_connector_omits_empty_overrides(tmp_path):
    """No extra YAML keys are written when the user didn't pass overrides."""
    os.environ["DINOBASE_DIR"] = str(tmp_path)
    try:
        from dinobase.config import add_connector, load_config

        add_connector(
            name="stripe",
            connector_type="stripe",
            credentials={"api_key": "sk_test"},
        )
        cfg = load_config()["connectors"]["stripe"]
        assert "resources" not in cfg
        assert "params" not in cfg
    finally:
        os.environ.pop("DINOBASE_DIR", None)


# ---------------------------------------------------------------------------
# 2. get_source() merges user params into the source factory kwargs
# ---------------------------------------------------------------------------

def _stub_registry(monkeypatch, entry):
    """Replace the registry lookup so get_source uses our fake entry."""
    from dinobase.sync import sources as sources_pkg
    monkeypatch.setattr(sources_pkg, "get_source_entry", lambda _: entry)


def _stub_yaml_lookup(monkeypatch):
    """Force the verified-source code path (no YAML config)."""
    from dinobase.sync import sources as sources_pkg
    monkeypatch.setattr(sources_pkg, "load_yaml_config", lambda _: None)


def _make_entry(import_path, credentials_params):
    """Build a minimal SourceEntry-like object for the verified-source path."""
    from dinobase.sync.registry import CredentialParam

    creds = [
        CredentialParam(name=n, cli_flag=f"--{n.replace('_', '-')}",
                        env_var=None, prompt=None)
        for n in credentials_params
    ]
    return SimpleNamespace(
        import_path=import_path,
        credentials=creds,
        extra_params={},
        graphql_config=None,
        pip_extra=None,
        live_fetch_config=None,
    )


def test_get_source_forwards_user_params_to_factory(monkeypatch):
    from dinobase.sync.sources import get_source
    from dinobase.sync import source_fetch

    captured = {}

    def fake_source_func(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(resources={}, with_resources=lambda *a: None)

    fake_module = SimpleNamespace(my_source=fake_source_func)

    entry = _make_entry("sources.fakething.my_source", ["api_key"])
    _stub_registry(monkeypatch, entry)
    _stub_yaml_lookup(monkeypatch)
    # Skip the on-demand fetch — we're not exercising that path.
    monkeypatch.setattr(source_fetch, "ensure_verified_source", lambda _: None)
    monkeypatch.setattr("importlib.import_module", lambda _: fake_module)

    get_source(
        "fakething",
        credentials={"api_key": "secret"},
        params={"start_date": "2026-03-20T00:00:00Z", "page_size": "50"},
    )

    assert captured["api_key"] == "secret"
    assert captured["start_date"] == "2026-03-20T00:00:00Z"
    assert captured["page_size"] == "50"


def test_get_source_does_not_let_params_clobber_credentials(monkeypatch):
    """A user --param api_key=x must NOT override the real credential."""
    from dinobase.sync.sources import get_source
    from dinobase.sync import source_fetch

    captured = {}

    def fake_source_func(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(resources={}, with_resources=lambda *a: None)

    fake_module = SimpleNamespace(my_source=fake_source_func)

    entry = _make_entry("sources.fakething.my_source", ["api_key"])
    _stub_registry(monkeypatch, entry)
    _stub_yaml_lookup(monkeypatch)
    monkeypatch.setattr(source_fetch, "ensure_verified_source", lambda _: None)
    monkeypatch.setattr("importlib.import_module", lambda _: fake_module)

    get_source(
        "fakething",
        credentials={"api_key": "real_secret"},
        params={"api_key": "attacker_value", "page_size": "10"},
    )

    assert captured["api_key"] == "real_secret"
    assert captured["page_size"] == "10"


# ---------------------------------------------------------------------------
# 3. SyncEngine.sync() forwards config-stored resources/params
# ---------------------------------------------------------------------------

def test_engine_sync_forwards_resources_and_params_to_run_pipeline():
    """The public sync() entry point must pass the config overrides through."""
    from dinobase.sync.engine import SyncEngine, SyncResult

    db = MagicMock()
    db.is_cloud = False
    db.log_sync_start.return_value = 1
    engine = SyncEngine(db)

    # Stub out _run_pipeline so we can capture what got forwarded.
    captured = {}

    def fake_run_pipeline(self, source_name, source_type, credentials, **kwargs):
        captured.update(kwargs)
        return SyncResult(
            connector_name=source_name, connector_type=source_type,
            tables_synced=0, rows_synced=0, status="success",
        )

    # Avoid the metadata + telemetry side effects we don't care about here.
    with patch.object(SyncEngine, "_run_pipeline", fake_run_pipeline), \
         patch("dinobase.sync.sources.extract_metadata", return_value={}), \
         patch("dinobase.semantic_agent.spawn_semantic_agent"), \
         patch("dinobase.auth.ensure_fresh_credentials",
               side_effect=lambda _name, _type, c: c), \
         patch("dinobase.fetch.connector.is_local_connector", return_value=False):
        engine.sync(
            "freshdesk",
            {
                "type": "freshdesk",
                "credentials": {"api_secret_key": "x", "domain": "y"},
                "resources": ["tickets", "agents"],
                "params": {"start_date": "2026-03-20T00:00:00Z"},
            },
        )

    assert captured.get("resource_names") == ["tickets", "agents"]
    assert captured.get("params") == {"start_date": "2026-03-20T00:00:00Z"}


def test_engine_sync_no_overrides_passes_none():
    """A connector without resources/params still works (regression check)."""
    from dinobase.sync.engine import SyncEngine, SyncResult

    db = MagicMock()
    db.is_cloud = False
    db.log_sync_start.return_value = 1
    engine = SyncEngine(db)

    captured = {}

    def fake_run_pipeline(self, source_name, source_type, credentials, **kwargs):
        captured.update(kwargs)
        return SyncResult(
            connector_name=source_name, connector_type=source_type,
            tables_synced=0, rows_synced=0, status="success",
        )

    with patch.object(SyncEngine, "_run_pipeline", fake_run_pipeline), \
         patch("dinobase.sync.sources.extract_metadata", return_value={}), \
         patch("dinobase.semantic_agent.spawn_semantic_agent"), \
         patch("dinobase.auth.ensure_fresh_credentials",
               side_effect=lambda _name, _type, c: c), \
         patch("dinobase.fetch.connector.is_local_connector", return_value=False):
        engine.sync(
            "stripe",
            {"type": "stripe", "credentials": {"api_key": "sk"}},
        )

    assert captured.get("resource_names") is None
    assert captured.get("params") is None
