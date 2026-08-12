"""FastAPI application entrypoint."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import router
from app.config import get_settings
from app.config_store import build_config_store


def create_app() -> FastAPI:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    store = build_config_store(settings)

    # Propagate host paths for storage/temp helpers used outside Depends().
    if settings.host_fs_root:
        os.environ["HOST_FS_ROOT"] = settings.host_fs_root
    if settings.host_sys_root:
        os.environ["HOST_SYS_ROOT"] = settings.host_sys_root

    app = FastAPI(
        title="Homeserver Dashboard",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.store = store
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.exists():
        assets = static_dir / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        index_file = static_dir / "index.html"

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(index_file)

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str) -> FileResponse:
            if full_path.startswith("api/") or full_path == "api":
                raise HTTPException(status_code=404, detail="Not found")
            candidate = static_dir / full_path
            if full_path and candidate.exists() and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index_file)

    return app


app = create_app()
