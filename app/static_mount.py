"""Serve built SPA from app/static (Vite outDir)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent / "static"


def mount_frontend(app: FastAPI) -> None:
    if not STATIC_DIR.exists():
        return

    assets = STATIC_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    def spa_index():
        index = STATIC_DIR / "index.html"
        if not index.exists():
            raise HTTPException(404, "frontend not built")
        return FileResponse(index)

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # Never shadow API / health / docs
        if full_path.startswith(("api/", "health", "docs", "openapi.json", "redoc")):
            raise HTTPException(404, "not found")
        candidate = STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        index = STATIC_DIR / "index.html"
        if not index.exists():
            raise HTTPException(404, "frontend not built")
        return FileResponse(index)
