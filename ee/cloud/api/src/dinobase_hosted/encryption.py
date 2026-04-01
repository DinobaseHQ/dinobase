# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Fernet encryption for stored credentials.

All OAuth tokens and API keys are encrypted at rest in the database.
The encryption key is stored as a Fly.io secret (DINOBASE_ENCRYPTION_KEY).
"""

from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet

from dinobase_hosted.config import get_encryption_key


def _fernet() -> Fernet:
    return Fernet(get_encryption_key().encode())


def encrypt_credentials(credentials: dict[str, Any]) -> str:
    """Encrypt a credentials dict to a base64-encoded string."""
    plaintext = json.dumps(credentials).encode()
    return _fernet().encrypt(plaintext).decode()


def decrypt_credentials(ciphertext: str) -> dict[str, Any]:
    """Decrypt a base64-encoded string back to a credentials dict."""
    plaintext = _fernet().decrypt(ciphertext.encode())
    return json.loads(plaintext)
