"""Tests for YAML-to-dlt source translation."""

import pytest

from dinobase.sync.yaml_source import (
    load_yaml_config,
    _translate_config,
    _substitute,
    _build_auth,
    _build_paginator,
    get_write_endpoints,
)


# --- Config loading ---

def test_load_amplitude_config():
    config = load_yaml_config("amplitude")
    assert config is not None
    assert config["name"] == "amplitude"


def test_load_nonexistent():
    assert load_yaml_config("nonexistent_source") is None


# --- Credential substitution ---

def test_substitute_simple():
    assert _substitute("{api_key}", {"api_key": "test123"}) == "test123"


def test_substitute_multiple():
    result = _substitute("{user}:{pass}", {"user": "admin", "pass": "secret"})
    assert result == "admin:secret"


def test_substitute_preserves_dlt_templates():
    """dlt templates like {incremental.start_value} should not be substituted."""
    result = _substitute("{incremental.start_value}", {"incremental": "nope"})
    assert result == "{incremental.start_value}"


def test_substitute_missing_key():
    assert _substitute("{missing}", {}) == "{missing}"


# --- Auth building ---

def test_auth_bearer():
    auth = _build_auth({"type": "bearer", "token": "{api_key}"}, {"api_key": "tk_123"})
    assert auth["type"] == "bearer"
    assert auth["token"] == "tk_123"


def test_auth_basic():
    auth = _build_auth(
        {"type": "http_basic", "username": "{key}", "password": ""},
        {"key": "sk_test"},
    )
    assert auth["username"] == "sk_test"
    assert auth["password"] == ""


def test_auth_api_key():
    auth = _build_auth(
        {"type": "api_key", "name": "X-Api-Key", "api_key": "{token}", "location": "header"},
        {"token": "abc"},
    )
    assert auth["api_key"] == "abc"
    assert auth["location"] == "header"


# --- Paginator building ---

def test_paginator_cursor():
    pag = _build_paginator({
        "type": "cursor",
        "cursor_path": "data[-1].id",
        "cursor_param": "starting_after",
    })
    assert pag["type"] == "cursor"
    assert pag["cursor_path"] == "data[-1].id"


def test_paginator_json_link():
    pag = _build_paginator({"type": "json_link", "next_url_path": "paging.next"})
    assert pag["type"] == "json_link"


# --- Write endpoints ---

def test_amplitude_write_endpoints():
    """Amplitude uses legacy format (endpoints with write: true)."""
    endpoints = get_write_endpoints("amplitude")
    names = [ep["name"] for ep in endpoints]
    assert "track_events" in names
    assert "identify" in names
    assert "create_annotation" in names


def test_write_endpoints_nonexistent():
    assert get_write_endpoints("nonexistent") == []
