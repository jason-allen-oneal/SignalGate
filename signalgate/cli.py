from __future__ import annotations

import os
import sys

import uvicorn

from .settings import load_runtime_config


def main() -> None:
    cfg, raw = load_runtime_config()

    # Ensure project root on sys.path when running from repo.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    server_raw = (raw.get("server") or {}) if isinstance(raw, dict) else {}
    uds_path = server_raw.get("uds_path")

    if isinstance(uds_path, str) and uds_path:
        # UDS binding ignores host/port.
        uvicorn.run(
            "signalgate.app:app",
            uds=uds_path,
            log_level=cfg.server.log_level,
        )
        return

    uvicorn.run(
        "signalgate.app:app",
        host=cfg.server.host,
        port=cfg.server.port,
        log_level=cfg.server.log_level,
    )


if __name__ == "__main__":
    main()
