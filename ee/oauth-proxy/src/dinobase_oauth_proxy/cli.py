# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""CLI entry point — run the OAuth proxy server."""

from __future__ import annotations

import sys


def main() -> None:
    import uvicorn
    from dinobase_oauth_proxy.config import get_host, get_port

    host = get_host()
    port = get_port()

    print(f"Starting Dinobase OAuth proxy on {host}:{port}", file=sys.stderr)
    uvicorn.run(
        "dinobase_oauth_proxy.app:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
