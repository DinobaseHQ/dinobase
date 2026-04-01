# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Configuration for the OAuth provider credentials.

Client credentials are read from environment variables following the pattern:
  DINOBASE_OAUTH_{PROVIDER}_CLIENT_ID
  DINOBASE_OAUTH_{PROVIDER}_CLIENT_SECRET

Example:
  DINOBASE_OAUTH_HUBSPOT_CLIENT_ID=abc123
  DINOBASE_OAUTH_HUBSPOT_CLIENT_SECRET=secret456
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCredentials:
    client_id: str
    client_secret: str


def get_provider_credentials(provider: str) -> ProviderCredentials | None:
    """Load client_id and client_secret for a provider from env vars."""
    prefix = f"DINOBASE_OAUTH_{provider.upper()}"
    client_id = os.environ.get(f"{prefix}_CLIENT_ID", "")
    client_secret = os.environ.get(f"{prefix}_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        return None

    return ProviderCredentials(client_id=client_id, client_secret=client_secret)
