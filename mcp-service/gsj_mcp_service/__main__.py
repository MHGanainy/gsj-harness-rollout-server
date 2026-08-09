"""Entry point: python -m gsj_mcp_service --config config.yaml"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import uvicorn

from .app import build_asgi
from .config import ConfigError, load_config
from .state import AppState
from .tokens import TokenVerifier


def main() -> None:
    parser = argparse.ArgumentParser(
        description="gsj MCP service — token-scoped streamable-http retrieval "
                    "over the frozen case dataset")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        secret = config.token_secret()   # fail fast; value never logged
        config.source_token()            # fail fast if named env var is unset
    except ConfigError as error:
        print(f"gsj-mcp-service: {error}", file=sys.stderr)
        raise SystemExit(2) from None

    logging.basicConfig(
        level=config.server.log_level.upper(),
        format="%(asctime)s %(name)s %(levelname)s %(message)s")

    state = AppState(config)
    state.start_background_init()
    app = build_asgi(state, TokenVerifier(secret, config.auth.leeway_s))
    logging.getLogger("gsj_mcp_service").info(
        "serving on %s:%d (MCP at /mcp/<token>, health at /health) — "
        "state: %s", config.server.host, config.server.port, state.status)
    uvicorn.run(app, host=config.server.host, port=config.server.port,
                log_level=config.server.log_level)


if __name__ == "__main__":
    main()
