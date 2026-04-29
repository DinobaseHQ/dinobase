"""Tests for the on-demand fetcher of dlt verified sources."""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
from unittest.mock import MagicMock

import pytest

from dinobase.sync import source_fetch


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_dinobase_dir(tmp_path, monkeypatch):
    """Each test gets its own DINOBASE_DIR — keeps cache writes inside tmp_path."""
    monkeypatch.setenv("DINOBASE_DIR", str(tmp_path))
    for entry in list(sys.path):
        if "verified-sources" in entry:
            sys.path.remove(entry)
    yield tmp_path
    for entry in list(sys.path):
        if "verified-sources" in entry:
            sys.path.remove(entry)


@pytest.fixture
def stub_install(monkeypatch):
    """Replace subprocess.run with a stub that records calls and reports success."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(source_fetch.subprocess, "run", fake_run)
    return calls


def _make_tar(prefix: str, files: dict[str, bytes]) -> bytes:
    """Build an in-memory .tar.gz containing regular files under `prefix`."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel, content in files.items():
            info = tarfile.TarInfo(name=f"{prefix}{rel}")
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def _patch_urlopen(monkeypatch, payload: bytes):
    """Patch source_fetch.urlopen to return a context-managing fake response."""
    response = MagicMock()
    response.read = MagicMock(return_value=payload)
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)

    urlopen = MagicMock(return_value=response)
    monkeypatch.setattr(source_fetch, "urlopen", urlopen)
    return urlopen


# ---------------------------------------------------------------------------
# Cache layout — ref-scoped (the correctness fix)
# ---------------------------------------------------------------------------


class TestCacheLayout:
    def test_cache_root_is_ref_scoped(self, isolated_dinobase_dir):
        root = source_fetch.cache_root()
        assert root == (
            isolated_dinobase_dir
            / "cache"
            / "verified-sources"
            / source_fetch.VERIFIED_SOURCES_REF
        )

    def test_cold_cache_fetches_and_extracts(
        self, isolated_dinobase_dir, monkeypatch, stub_install
    ):
        prefix = f"verified-sources-{source_fetch.VERIFIED_SOURCES_REF}/sources/stripe_analytics/"
        payload = _make_tar(
            prefix,
            {
                "__init__.py": b"# stripe analytics\n",
                "stripe_source.py": b"def stripe_source(): pass\n",
                "requirements.txt": b"stripe>=5\n",
            },
        )
        urlopen = _patch_urlopen(monkeypatch, payload)

        root = source_fetch.ensure_verified_source("stripe_analytics")

        assert urlopen.call_count == 1
        src_dir = root / "sources" / "stripe_analytics"
        assert src_dir.is_dir()
        assert (src_dir / "stripe_source.py").read_text().startswith("def stripe_source")
        assert (src_dir / ".deps-installed").exists()
        assert len(stub_install) == 1
        assert stub_install[0][-2:] == ["-r", str(src_dir / "requirements.txt")]

    def test_warm_cache_skips_fetch_and_install(
        self, isolated_dinobase_dir, monkeypatch, stub_install
    ):
        prefix = f"verified-sources-{source_fetch.VERIFIED_SOURCES_REF}/sources/jira/"
        payload = _make_tar(prefix, {"__init__.py": b"", "requirements.txt": b"jira\n"})
        urlopen = _patch_urlopen(monkeypatch, payload)

        source_fetch.ensure_verified_source("jira")
        source_fetch.ensure_verified_source("jira")

        assert urlopen.call_count == 1, "second call should not re-download"
        assert len(stub_install) == 1, "second call should not re-install deps"

    def test_ref_bump_triggers_refetch(
        self, isolated_dinobase_dir, monkeypatch, stub_install
    ):
        """Bumping VERIFIED_SOURCES_REF must invalidate the existing cache.

        This is the correctness bug the rewrite fixes — previously the cache
        path didn't include the ref, so version bumps silently kept stale
        source code.
        """
        original_ref = source_fetch.VERIFIED_SOURCES_REF
        prefix1 = f"verified-sources-{original_ref}/sources/notion/"
        _patch_urlopen(monkeypatch, _make_tar(prefix1, {"v.py": b"V1\n"}))

        root1 = source_fetch.ensure_verified_source("notion")
        assert (root1 / "sources" / "notion" / "v.py").read_text() == "V1\n"

        new_ref = "deadbeef" * 5  # 40 hex chars, fake
        monkeypatch.setattr(source_fetch, "VERIFIED_SOURCES_REF", new_ref)
        prefix2 = f"verified-sources-{new_ref}/sources/notion/"
        _patch_urlopen(monkeypatch, _make_tar(prefix2, {"v.py": b"V2\n"}))

        root2 = source_fetch.ensure_verified_source("notion")
        assert root2 != root1, "different refs must use different cache dirs"
        assert (root2 / "sources" / "notion" / "v.py").read_text() == "V2\n"
        assert (root1 / "sources" / "notion" / "v.py").read_text() == "V1\n"


# ---------------------------------------------------------------------------
# Tarball extraction
# ---------------------------------------------------------------------------


class TestExtraction:
    def test_rejects_path_traversal(
        self, isolated_dinobase_dir, monkeypatch, stub_install
    ):
        prefix = f"verified-sources-{source_fetch.VERIFIED_SOURCES_REF}/sources/foo/"
        payload = _make_tar(prefix, {"../../../etc/passwd": b"x"})
        _patch_urlopen(monkeypatch, payload)

        with pytest.raises(RuntimeError, match="escapes destination"):
            source_fetch.ensure_verified_source("foo")

    def test_missing_source_name_raises_friendly_error(
        self, isolated_dinobase_dir, monkeypatch, stub_install
    ):
        # Tar has files for sources/other/ but not sources/missing/
        other_prefix = (
            f"verified-sources-{source_fetch.VERIFIED_SOURCES_REF}/sources/other/"
        )
        _patch_urlopen(monkeypatch, _make_tar(other_prefix, {"__init__.py": b""}))

        with pytest.raises(RuntimeError, match="not found"):
            source_fetch.ensure_verified_source("missing")


# ---------------------------------------------------------------------------
# Subprocess install — timeouts and failures
# ---------------------------------------------------------------------------


class TestInstallRequirements:
    def test_timeout_raises_friendly_error(
        self, isolated_dinobase_dir, monkeypatch
    ):
        prefix = (
            f"verified-sources-{source_fetch.VERIFIED_SOURCES_REF}/sources/airtable/"
        )
        _patch_urlopen(
            monkeypatch,
            _make_tar(prefix, {"__init__.py": b"", "requirements.txt": b"pyairtable\n"}),
        )

        def slow_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))

        monkeypatch.setattr(source_fetch.subprocess, "run", slow_run)

        with pytest.raises(RuntimeError, match="timed out"):
            source_fetch.ensure_verified_source("airtable")

    def test_install_failure_propagates(
        self, isolated_dinobase_dir, monkeypatch
    ):
        prefix = (
            f"verified-sources-{source_fetch.VERIFIED_SOURCES_REF}/sources/zendesk/"
        )
        _patch_urlopen(
            monkeypatch,
            _make_tar(prefix, {"__init__.py": b"", "requirements.txt": b"zenpy\n"}),
        )

        def failing_run(cmd, **kwargs):
            return subprocess.CompletedProcess(args=cmd, returncode=1)

        monkeypatch.setattr(source_fetch.subprocess, "run", failing_run)

        with pytest.raises(RuntimeError, match="Failed to install"):
            source_fetch.ensure_verified_source("zendesk")

    def test_no_requirements_file_skips_install(
        self, isolated_dinobase_dir, monkeypatch, stub_install
    ):
        prefix = f"verified-sources-{source_fetch.VERIFIED_SOURCES_REF}/sources/bare/"
        _patch_urlopen(monkeypatch, _make_tar(prefix, {"__init__.py": b""}))

        source_fetch.ensure_verified_source("bare")

        assert len(stub_install) == 0
