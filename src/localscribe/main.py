from __future__ import annotations

import argparse

import uvicorn

from .api.app import app, create_app
from .config import Settings

__all__ = ["app", "create_app", "cli"]


def cli() -> None:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Run LocalScribe.")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--reload", action="store_true", help="Enable auto reload for development.")
    args = parser.parse_args()

    uvicorn.run("localscribe.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    cli()
