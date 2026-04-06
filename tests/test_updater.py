"""Tests for the auto-update module."""

import json
import os
import time

import pytest

from dinobase.updater import (
    _load_state,
    _save_state,
    _check_enabled,
    _version_tuple,
    check_for_update,
    detect_install_method,
    get_update_command,
)


@pytest.fixture(autouse=True)
def dinobase_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DINOBASE_DIR", str(tmp_path))
    monkeypatch.delenv("DINOBASE_NO_UPDATE_CHECK", raising=False)
    return tmp_path


class TestState:
    def test_load_missing(self, dinobase_dir):
        assert _load_state() == {}

    def test_save_and_load(self, dinobase_dir):
        state = {"last_check": 123.0, "latest_version": "1.0.0"}
        _save_state(state)
        assert _load_state() == state

    def test_load_corrupt(self, dinobase_dir):
        (dinobase_dir / "update_check.json").write_text("not json")
        assert _load_state() == {}


class TestCheckEnabled:
    def test_enabled_by_default(self):
        assert _check_enabled() is True

    def test_disabled_by_env(self, monkeypatch):
        monkeypatch.setenv("DINOBASE_NO_UPDATE_CHECK", "1")
        assert _check_enabled() is False

    def test_disabled_by_env_true(self, monkeypatch):
        monkeypatch.setenv("DINOBASE_NO_UPDATE_CHECK", "true")
        assert _check_enabled() is False

    def test_disabled_by_config(self, dinobase_dir):
        import yaml
        config = {"sources": {}, "auto_update": False}
        config_path = dinobase_dir / "config.yaml"
        config_path.write_text(yaml.dump(config))
        config_path.chmod(0o600)
        assert _check_enabled() is False


class TestVersionTuple:
    def test_simple(self):
        assert _version_tuple("0.2.4") < _version_tuple("0.3.0")
        assert _version_tuple("1.0.0") > _version_tuple("0.9.9")
        assert _version_tuple("0.2.4") == _version_tuple("0.2.4")


class TestCheckForUpdate:
    def test_returns_none_when_disabled(self, monkeypatch):
        monkeypatch.setenv("DINOBASE_NO_UPDATE_CHECK", "1")
        assert check_for_update() is None

    def test_uses_cache(self, dinobase_dir):
        state = {
            "last_check": time.time(),
            "latest_version": "99.0.0",
        }
        _save_state(state)
        result = check_for_update()
        assert result is not None
        assert result["update_available"] is True
        assert result["latest_version"] == "99.0.0"

    def test_cache_no_update(self, dinobase_dir, monkeypatch):
        import dinobase.updater as mod
        monkeypatch.setattr(mod, "__version__", "99.0.0")
        state = {
            "last_check": time.time(),
            "latest_version": "1.0.0",
        }
        _save_state(state)
        assert check_for_update() is None

    def test_network_error(self, dinobase_dir, monkeypatch):
        """Stale cache + network failure => saves timestamp and returns None."""
        state = {"last_check": 0}
        _save_state(state)

        def fake_urlopen(*a, **kw):
            raise ConnectionError("no network")

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        assert check_for_update() is None
        # Timestamp should be updated to prevent immediate retry
        new_state = _load_state()
        assert new_state["last_check"] > 0

    def test_force_ignores_cache(self, dinobase_dir, monkeypatch):
        """force=True should hit the network even with fresh cache."""
        state = {"last_check": time.time(), "latest_version": "0.0.1"}
        _save_state(state)

        def fake_urlopen(*a, **kw):
            raise ConnectionError("no network")

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        # force=True should attempt network (and fail), not just return cache
        result = check_for_update(force=True)
        assert result is None


class TestDetectInstallMethod:
    def test_uv(self, monkeypatch):
        monkeypatch.setattr("sys.prefix", "/home/user/.local/share/uv/tools/dinobase")
        assert detect_install_method() == "uv"

    def test_pip(self, monkeypatch):
        monkeypatch.setattr("sys.prefix", "/home/user/.venv")
        assert detect_install_method() in ("pip", "unknown")


class TestGetUpdateCommand:
    def test_uv(self):
        assert get_update_command("uv") == "uv tool install dinobase --force"

    def test_pip(self):
        assert get_update_command("pip") == "pip install --upgrade dinobase"
