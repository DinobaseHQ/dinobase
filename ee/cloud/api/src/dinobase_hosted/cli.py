# Copyright (c) Dinobase. Licensed under the Elastic License 2.0 (ELv2).
# See ee/LICENSE for details.

"""CLI entry point — run the Dinobase Cloud API server."""

from __future__ import annotations

import os
import sys


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    import uvicorn
    from dinobase_hosted.config import get_host, get_port

    host = get_host()
    port = get_port()
    dev = os.environ.get("DINOBASE_ENV", "production") == "development"

    print(f"Starting Dinobase Cloud API on {host}:{port}", file=sys.stderr)

    reload_dirs = None
    if dev:
        import dinobase
        from pathlib import Path
        dinobase_src = str(Path(dinobase.__file__).parent.parent)
        hosted_src = str(Path(__file__).parent.parent)
        reload_dirs = [dinobase_src, hosted_src]

    uvicorn.run(
        "dinobase_hosted.app:app",
        host=host,
        port=port,
        log_level="info",
        reload=dev,
        reload_dirs=reload_dirs,
    )


if __name__ == "__main__":
    main()
