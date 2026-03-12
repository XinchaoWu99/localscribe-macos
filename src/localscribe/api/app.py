from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..config import Settings
from .routes import register_routes
from .services import build_services


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    static_dir = Path(__file__).resolve().parent.parent / "static"

    services = build_services(active_settings, static_dir)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        services.startup()
        try:
            yield
        finally:
            services.shutdown()

    app = FastAPI(title="LocalScribe", version="0.1.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.state.services = services
    register_routes(app, services)
    return app


app = create_app()
