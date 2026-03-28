"""Tests for cloud storage operations (CloudStorage class)."""

import json
import os
import tempfile

import pytest

from dinobase.cloud import CloudStorage


@pytest.fixture
def local_cloud(tmp_path):
    """CloudStorage using local filesystem (fsspec 'file' protocol)."""
    storage_url = f"file://{tmp_path}/cloud/"
    os.makedirs(f"{tmp_path}/cloud", exist_ok=True)
    return CloudStorage(storage_url)


def test_write_and_read_json(local_cloud, tmp_path):
    url = f"{local_cloud.storage_url}test.json"
    local_cloud.write_json(url, {"key": "value", "num": 42})

    result = local_cloud.read_json(url)
    assert result == {"key": "value", "num": 42}


def test_read_json_not_found(local_cloud):
    result = local_cloud.read_json(f"{local_cloud.storage_url}nonexistent.json")
    assert result is None


def test_list_files(local_cloud, tmp_path):
    cloud_dir = tmp_path / "cloud" / "data"
    cloud_dir.mkdir(parents=True)
    (cloud_dir / "a.parquet").write_text("data")
    (cloud_dir / "b.parquet").write_text("data")
    (cloud_dir / "c.json").write_text("data")

    files = local_cloud.list_files(f"{local_cloud.storage_url}data/")
    assert len(files) == 3

    parquet_files = local_cloud.list_files(f"{local_cloud.storage_url}data/", suffix=".parquet")
    assert len(parquet_files) == 2


def test_delete_files_with_exclude(local_cloud, tmp_path):
    cloud_dir = tmp_path / "cloud" / "table"
    cloud_dir.mkdir(parents=True)
    (cloud_dir / "load1.parquet").write_text("old")
    (cloud_dir / "load2.parquet").write_text("old")
    (cloud_dir / "_compacted.parquet").write_text("new")

    deleted = local_cloud.delete_files(
        f"{local_cloud.storage_url}table/",
        exclude=["_compacted.parquet"],
    )
    assert deleted == 2
    assert (cloud_dir / "_compacted.parquet").exists()
    assert not (cloud_dir / "load1.parquet").exists()


def test_upload_and_download_dir(local_cloud, tmp_path):
    # Create local files
    local_dir = tmp_path / "local_state"
    local_dir.mkdir()
    (local_dir / "state.json").write_text('{"cursor": 42}')
    sub = local_dir / "schemas"
    sub.mkdir()
    (sub / "schema.json").write_text('{"version": 1}')

    # Upload
    remote_url = f"{local_cloud.storage_url}_state/pipeline/"
    count = local_cloud.upload_dir(str(local_dir), remote_url)
    assert count == 2

    # Download to a different location
    download_dir = tmp_path / "downloaded"
    count = local_cloud.download_dir(remote_url, str(download_dir))
    assert count >= 1
    assert (download_dir / "state.json").exists()


def test_acquire_and_release_lock(local_cloud):
    # Acquire should succeed
    assert local_cloud.acquire_lock("stripe") is True

    # Second acquire should fail (lock held)
    assert local_cloud.acquire_lock("stripe") is False

    # Release
    local_cloud.release_lock("stripe")

    # Now acquire should succeed again
    assert local_cloud.acquire_lock("stripe") is True
    local_cloud.release_lock("stripe")


def test_stale_lock_is_overwritten(local_cloud):
    # Write a lock with old timestamp
    lock_url = f"{local_cloud.storage_url}_locks/old_source.json"
    local_cloud.write_json(lock_url, {
        "timestamp": 0,  # Very old
        "pid": 99999,
        "hostname": "old-host",
    })

    # Should acquire because lock is stale (ttl=600, timestamp=0)
    assert local_cloud.acquire_lock("old_source", ttl=600) is True
    local_cloud.release_lock("old_source")


def test_different_sources_lock_independently(local_cloud):
    assert local_cloud.acquire_lock("stripe") is True
    assert local_cloud.acquire_lock("hubspot") is True

    # stripe is locked, hubspot is locked
    assert local_cloud.acquire_lock("stripe") is False
    assert local_cloud.acquire_lock("hubspot") is False

    local_cloud.release_lock("stripe")
    local_cloud.release_lock("hubspot")
