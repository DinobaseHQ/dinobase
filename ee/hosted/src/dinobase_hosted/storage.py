# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""Per-user S3 storage provisioning.

Each user gets a prefix in a shared S3 bucket:
  s3://dinobase-cloud/{user_id}/

No explicit provisioning is needed — S3 prefixes are implicit.
We just need to track the URL in the user profile.
"""

from __future__ import annotations

from dinobase_hosted.config import get_user_storage_url
from dinobase_hosted.db import get_or_create_profile, get_profile


def ensure_user_storage(user_id: str) -> str:
    """Ensure a user has a storage URL allocated. Returns the URL."""
    profile = get_profile(user_id)
    if profile:
        return profile["storage_url"]

    storage_url = get_user_storage_url(user_id)
    get_or_create_profile(user_id, storage_url)
    return storage_url
