"""FastAPI application. JSON routers live under /api/v1; the dashboard bundle is served at /."""

from satsa.api.main import app, create_app

__all__ = ["app", "create_app"]
