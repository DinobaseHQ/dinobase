"""Tests for YAML source configs and the write client."""

import pytest

from dinobase.sync.source_config import (
    load_source_config,
    list_yaml_sources,
    get_read_endpoints,
    get_write_endpoints,
    get_endpoint,
    build_auth_headers,
    build_request_body,
    build_url,
)
from dinobase.sync.write_client import WriteClient


# --- YAML config loading ---

def test_load_amplitude_config():
    config = load_source_config("amplitude")
    assert config is not None
    assert config["name"] == "amplitude"


def test_amplitude_has_credentials():
    config = load_source_config("amplitude")
    creds = config["credentials"]
    names = [c["name"] for c in creds]
    assert "api_key" in names
    assert "secret_key" in names


def test_amplitude_has_read_and_write_endpoints():
    config = load_source_config("amplitude")
    reads = get_read_endpoints(config)
    writes = get_write_endpoints(config)
    assert len(reads) > 10
    assert len(writes) > 5


def test_amplitude_read_endpoints():
    config = load_source_config("amplitude")
    reads = get_read_endpoints(config)
    names = [ep["name"] for ep in reads]
    assert "events_list" in names
    assert "export" in names
    assert "cohorts" in names
    assert "taxonomy_events" in names
    assert "user_profile" in names


def test_amplitude_write_endpoints():
    config = load_source_config("amplitude")
    writes = get_write_endpoints(config)
    names = [ep["name"] for ep in writes]
    assert "track_events" in names
    assert "identify" in names
    assert "cohort_upload" in names
    assert "create_annotation" in names
    assert "delete_users" in names


def test_get_specific_endpoint():
    config = load_source_config("amplitude")
    ep = get_endpoint(config, "identify")
    assert ep is not None
    assert ep["method"] == "POST"
    assert ep["write"] is True
    assert ep["auth"] == "ingestion"  # references auth_methods.ingestion


def test_list_yaml_sources():
    sources = list_yaml_sources()
    assert "amplitude" in sources


# --- Auth header building ---

def test_http_basic_auth():
    ep = {"auth": "http_basic"}
    creds = {"api_key": "mykey", "secret_key": "mysecret"}
    headers = build_auth_headers(ep, creds)
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")


def test_bearer_auth():
    ep = {"auth": "bearer"}
    creds = {"token": "mytoken"}
    headers = build_auth_headers(ep, creds)
    assert headers["Authorization"] == "Bearer mytoken"


def test_api_key_header_auth():
    ep = {"auth": "api_key_header"}
    creds = {"secret_key": "mysecret"}
    headers = build_auth_headers(ep, creds)
    assert headers["Authorization"] == "Api-Key mysecret"


def test_api_key_in_body_auth():
    ep = {"auth": "api_key_in_body"}
    creds = {"api_key": "mykey"}
    headers = build_auth_headers(ep, creds)
    # No auth header — it goes in the body
    assert "Authorization" not in headers


# --- Request body building ---

def test_body_injects_api_key():
    ep = {"auth": "api_key_in_body"}
    creds = {"api_key": "mykey"}
    body = build_request_body(ep, creds, {"event": "test"})
    assert body["api_key"] == "mykey"
    assert body["event"] == "test"


def test_body_no_injection_for_basic_auth():
    ep = {"auth": "http_basic"}
    creds = {"api_key": "mykey"}
    body = build_request_body(ep, creds, {"event": "test"})
    assert "api_key" not in body


# --- URL building ---

def test_build_url_simple():
    ep = {"base_url": "https://api.example.com", "path": "/v1/users"}
    assert build_url(ep) == "https://api.example.com/v1/users"


def test_build_url_with_path_params():
    ep = {"base_url": "https://api.example.com", "path": "/v1/events/{event_type}"}
    url = build_url(ep, {"event_type": "purchase"})
    assert url == "https://api.example.com/v1/events/purchase"


def test_build_url_strips_slashes():
    ep = {"base_url": "https://api.example.com/", "path": "/v1/users"}
    assert build_url(ep) == "https://api.example.com/v1/users"


# --- WriteClient ---

def test_write_client_loads_config():
    client = WriteClient("amplitude", {"api_key": "test", "secret_key": "test"})
    assert client.has_config


def test_write_client_lists_operations():
    client = WriteClient("amplitude", {"api_key": "test", "secret_key": "test"})
    ops = client.list_write_operations()
    assert len(ops) > 5
    names = [op["name"] for op in ops]
    assert "track_events" in names
    assert "identify" in names


def test_write_client_no_config():
    client = WriteClient("nonexistent_source", {})
    assert not client.has_config
    assert client.write_endpoints == []


def test_write_client_rejects_read_endpoint():
    client = WriteClient("amplitude", {"api_key": "test", "secret_key": "test"})
    result = client.execute("events_list", {})
    assert "error" in result
    assert "read endpoint" in result["error"].lower()


def test_write_client_rejects_unknown_endpoint():
    client = WriteClient("amplitude", {"api_key": "test", "secret_key": "test"})
    result = client.execute("nonexistent_endpoint", {})
    assert "error" in result
    assert "available_endpoints" in result
