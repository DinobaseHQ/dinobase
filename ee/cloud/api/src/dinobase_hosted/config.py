# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Configuration for the Dinobase Cloud API.

All configuration is read from environment variables.
"""

from __future__ import annotations

import os


def get_host() -> str:
    return os.environ.get("DINOBASE_HOST", "0.0.0.0")


def get_port() -> int:
    return int(os.environ.get("DINOBASE_PORT", "8787"))


def get_base_url() -> str:
    """Public-facing URL of this service."""
    return os.environ.get(
        "DINOBASE_BASE_URL",
        f"http://localhost:{get_port()}",
    ).rstrip("/")


# -- Supabase --

def get_supabase_url() -> str:
    return os.environ["SUPABASE_URL"]


def get_supabase_publishable_key() -> str:
    return os.environ["SUPABASE_PUBLISHABLE_KEY"]


def get_supabase_secret_key() -> str:
    return os.environ["SUPABASE_SECRET_KEY"]


# -- Storage --

def get_storage_bucket() -> str:
    """S3 bucket for user data."""
    return os.environ.get("DINOBASE_STORAGE_BUCKET", "dinobase-cloud")


def get_storage_prefix() -> str:
    """Base prefix within the bucket (e.g., 'data/')."""
    return os.environ.get("DINOBASE_STORAGE_PREFIX", "").rstrip("/")


def get_user_storage_url(user_id: str) -> str:
    """Return the S3 URL for a user's data."""
    bucket = get_storage_bucket()
    prefix = get_storage_prefix()
    if prefix:
        return f"s3://{bucket}/{prefix}/{user_id}/"
    return f"s3://{bucket}/{user_id}/"


# -- Encryption --

def get_encryption_key() -> str:
    """Fernet key for encrypting stored credentials."""
    return os.environ["DINOBASE_ENCRYPTION_KEY"]


# -- CORS --

def get_query_url() -> str | None:
    """URL of the query server. Set DINOBASE_QUERY_URL in web mode to proxy there."""
    return os.environ.get("DINOBASE_QUERY_URL")


def get_allowed_origins() -> list[str]:
    """Origins allowed to call the API (the web frontend)."""
    origins = os.environ.get("DINOBASE_ALLOWED_ORIGINS", "")
    if origins:
        return [o.strip() for o in origins.split(",")]
    return [
        "http://localhost:3000",
        "https://cloud.dinobase.dev",
        "https://app.dinobase.ai",
    ]
