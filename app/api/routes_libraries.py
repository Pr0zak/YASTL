"""API routes for managing model libraries (scan directories)."""

import logging
import os

from fastapi import APIRouter, HTTPException, Request
import aiosqlite

from app.services.watcher import ModelFileWatcher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/libraries", tags=["libraries"])


def _get_db_path(request: Request) -> str:
    """Retrieve the database path from FastAPI app state."""
    return request.app.state.db_path


def _get_watcher(request: Request) -> ModelFileWatcher | None:
    """Retrieve the file watcher from FastAPI app state, if available."""
    return getattr(request.app.state, "watcher", None)


# ---------------------------------------------------------------------------
# List libraries
# ---------------------------------------------------------------------------


@router.get("")
async def list_libraries(request: Request):
    """Return all configured libraries."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM libraries ORDER BY name"
        )
        rows = await cursor.fetchall()

    libraries = [dict(r) for r in rows]
    return {"libraries": libraries}


# ---------------------------------------------------------------------------
# Create library
# ---------------------------------------------------------------------------


@router.post("")
async def create_library(request: Request):
    """Create a new library with a name and local path.

    Expects JSON body: {"name": "My Models", "path": "/path/to/models"}
    """
    db_path = _get_db_path(request)
    body = await request.json()

    name = body.get("name", "").strip()
    path = body.get("path", "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required")
    if not path:
        raise HTTPException(status_code=400, detail="'path' is required")

    # Validate the path exists and is a directory
    if not os.path.isdir(path):
        raise HTTPException(
            status_code=400,
            detail=f"Path does not exist or is not a directory: {path}",
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Check for duplicate path
        cursor = await db.execute(
            "SELECT id FROM libraries WHERE path = ?", (path,)
        )
        if await cursor.fetchone() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"A library with path '{path}' already exists",
            )

        cursor = await db.execute(
            "INSERT INTO libraries (name, path) VALUES (?, ?)",
            (name, path),
        )
        library_id = cursor.lastrowid
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM libraries WHERE id = ?", (library_id,)
        )
        library = dict(await cursor.fetchone())

    # Notify watcher to start watching the new library path
    watcher = _get_watcher(request)
    if watcher is not None and watcher.is_running:
        watcher.watch_path(path)

    return library


# ---------------------------------------------------------------------------
# Update library
# ---------------------------------------------------------------------------


@router.put("/{library_id}")
async def update_library(request: Request, library_id: int):
    """Update a library's name and/or path.

    Expects JSON body: {"name": "...", "path": "..."}
    """
    db_path = _get_db_path(request)
    body = await request.json()

    name = body.get("name")
    path = body.get("path")

    if name is not None:
        name = name.strip()
    if path is not None:
        path = path.strip()

    if not name and not path:
        raise HTTPException(
            status_code=400,
            detail="At least one of 'name' or 'path' is required",
        )

    if path and not os.path.isdir(path):
        raise HTTPException(
            status_code=400,
            detail=f"Path does not exist or is not a directory: {path}",
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        cursor = await db.execute(
            "SELECT * FROM libraries WHERE id = ?", (library_id,)
        )
        existing = await cursor.fetchone()
        if existing is None:
            raise HTTPException(
                status_code=404,
                detail=f"Library {library_id} not found",
            )
        old_path = dict(existing)["path"]

        set_clauses: list[str] = []
        params: list[str | int] = []

        if name:
            set_clauses.append("name = ?")
            params.append(name)
        if path:
            set_clauses.append("path = ?")
            params.append(path)

        params.append(library_id)
        await db.execute(
            f"UPDATE libraries SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM libraries WHERE id = ?", (library_id,)
        )
        library = dict(await cursor.fetchone())

    # If the path changed, update the watcher
    if path and path != old_path:
        watcher = _get_watcher(request)
        if watcher is not None and watcher.is_running:
            watcher.unwatch_path(old_path)
            watcher.watch_path(path)

    return library


# ---------------------------------------------------------------------------
# Delete library
# ---------------------------------------------------------------------------


@router.delete("/{library_id}")
async def delete_library(request: Request, library_id: int):
    """Delete a library. Models from this library remain in the database."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        cursor = await db.execute(
            "SELECT id, path FROM libraries WHERE id = ?", (library_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Library {library_id} not found",
            )
        lib_path = dict(row)["path"]

        await db.execute("DELETE FROM libraries WHERE id = ?", (library_id,))
        await db.commit()

    # Stop watching the deleted library's path
    watcher = _get_watcher(request)
    if watcher is not None and watcher.is_running:
        watcher.unwatch_path(lib_path)

    return {"detail": f"Library {library_id} deleted"}
