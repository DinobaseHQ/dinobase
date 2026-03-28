# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""CLI entry point — run the Dinobase Cloud API server."""

from __future__ import annotations

import sys


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    import uvicorn
    from dinobase_hosted.config import get_host, get_port

    host = get_host()
    port = get_port()

    print(f"Starting Dinobase Cloud API on {host}:{port}", file=sys.stderr)
    uvicorn.run(
        "dinobase_hosted.app:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
