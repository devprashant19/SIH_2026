"""App factory.

- /api/v1/...   JSON API (one router per domain area, registered below)
- /assets/...   dashboard static assets (when dashboard/dist exists)
- /*            SPA fallback -> dashboard index.html, so deep links like /entities/E03 work
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from satsa.api.jobs import JobRunner
from satsa.api.routers import analysis, core, ops
from satsa.config import Settings, get_settings
from satsa.db.connection import Database, get_database
from satsa.db.migrate import apply_schema
from satsa.version import __version__


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = database or get_database(settings)
        with db.write() as conn:
            apply_schema(conn)
        app.state.settings = settings
        app.state.db = db
        app.state.jobs = JobRunner()
        yield

    app = FastAPI(title="SAT-SA API", version=__version__, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=settings.api.cors_origins, allow_methods=["*"], allow_headers=["*"])

    api = APIRouter(prefix="/api/v1")
    api.include_router(core.router, tags=["core"])
    api.include_router(analysis.router, tags=["analysis"])
    api.include_router(ops.router, tags=["ops"])
    app.include_router(api)
    _mount_dashboard(app, settings.resolve(settings.paths.dashboard_dist))
    return app


def _mount_dashboard(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if not index.exists():
        @app.get("/", include_in_schema=False)
        def no_dashboard() -> JSONResponse:
            return JSONResponse({"detail": "dashboard bundle not built; run `npm run build` in dashboard/"}, status_code=503)
        return

    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
