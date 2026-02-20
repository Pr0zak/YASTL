"""API route for backend system status."""

import os

import aiosqlite
from fastapi import APIRouter, Request

from app.config import settings

router = APIRouter(prefix="/api/status", tags=["status"])


@router.get("")
async def get_system_status(request: Request):
    """Return the status of all backend subsystems."""

    # --- Scanner ---
    scanner = getattr(request.app.state, "scanner", None)
    if scanner is not None:
        scanner_status = {
            "status": "scanning" if scanner.is_scanning else "idle",
            "is_scanning": scanner.is_scanning,
            "total_files": scanner.total_files,
            "processed_files": scanner.processed_files,
        }
    else:
        scanner_status = {"status": "unavailable"}

    # --- File Watcher ---
    watcher = getattr(request.app.state, "watcher", None)
    if watcher is not None:
        is_running = watcher.is_running
        watched = watcher.watched_paths
        watcher_status = {
            "status": "watching" if (is_running and watched) else (
                "idle" if is_running else "stopped"
            ),
            "is_running": is_running,
            "watched_paths": sorted(watched),
            "watched_count": len(watched),
        }
    else:
        watcher_status = {"status": "unavailable"}

    # --- Database ---
    db_path = str(settings.MODEL_LIBRARY_DB)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT COUNT(*) as cnt FROM models")
            row = await cursor.fetchone()
            total_models = dict(row)["cnt"]

            cursor = await db.execute("SELECT COUNT(*) as cnt FROM libraries")
            row = await cursor.fetchone()
            total_libraries = dict(row)["cnt"]

        db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0

        database_status = {
            "status": "ok",
            "total_models": total_models,
            "total_libraries": total_libraries,
            "db_size_bytes": db_size,
        }
    except Exception:
        database_status = {"status": "error"}

    # --- Thumbnails ---
    thumb_path = str(settings.MODEL_LIBRARY_THUMBNAIL_PATH)
    if os.path.isdir(thumb_path):
        try:
            thumb_files = [
                f for f in os.listdir(thumb_path) if f.endswith(".png")
            ]
            thumbnail_status = {
                "status": "ok",
                "total_cached": len(thumb_files),
                "path": thumb_path,
            }
        except Exception:
            thumbnail_status = {"status": "error"}
    else:
        thumbnail_status = {"status": "unavailable", "total_cached": 0}

    # --- STEP support ---
    from app.services.step_converter import _detect_backend

    step_backend = _detect_backend()
    step_status = {
        "status": "ok" if step_backend else "unavailable",
        "backend": step_backend,
    }

    # --- Overall health ---
    statuses = [
        scanner_status["status"],
        watcher_status["status"],
        database_status["status"],
        thumbnail_status["status"],
    ]
    if "error" in statuses:
        health = "error"
    elif "unavailable" in statuses or "stopped" in statuses:
        health = "degraded"
    else:
        health = "ok"

    return {
        "health": health,
        "scanner": scanner_status,
        "watcher": watcher_status,
        "database": database_status,
        "thumbnails": thumbnail_status,
        "step_support": step_status,
    }
