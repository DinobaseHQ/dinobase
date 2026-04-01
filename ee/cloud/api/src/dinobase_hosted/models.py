# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Pydantic models for API requests and responses."""

from __future__ import annotations

from pydantic import BaseModel


# -- Accounts --

class LoginRequest(BaseModel):
    redirect_uri: str
    state: str


class TokenExchangeRequest(BaseModel):
    code: str
    redirect_uri: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: int
    user: dict


class UserInfo(BaseModel):
    id: str
    email: str
    plan: str
    storage_url: str
    sources_count: int


# -- Sources --

class AddSourceRequest(BaseModel):
    name: str
    type: str
    credentials: dict[str, str]
    sync_interval: str = "1h"


class SourceOAuthCallbackRequest(BaseModel):
    code: str
    redirect_uri: str
    state: str


class SourceResponse(BaseModel):
    name: str
    type: str
    auth_method: str
    status: str


# -- Sync --

class SyncRequest(BaseModel):
    source_name: str | None = None


class SyncJobResponse(BaseModel):
    job_id: str
    status: str


# -- Query --

class QueryRequest(BaseModel):
    sql: str
    max_rows: int = 200
