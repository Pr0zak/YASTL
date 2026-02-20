"""API routes for managing model libraries (scan directories)."""

import os

from fastapi import APIRouter, HTTPException, Request
import aiosqlite

router = APIRouter(prefix="/api/libraries", tags=["libraries"])


def _get_db_path(request: Request) -> str:
    """Retrieve the database path from FastAPI app state."""
    return request.app.state.db_path


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
        if await cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail=f"Library {library_id} not found",
            )

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
            "SELECT id FROM libraries WHERE id = ?", (library_id,)
        )
        if await cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail=f"Library {library_id} not found",
            )

        await db.execute("DELETE FROM libraries WHERE id = ?", (library_id,))
        await db.commit()

    return {"detail": f"Library {library_id} deleted"}
