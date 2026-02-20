"""API routes for tag management."""

from fastapi import APIRouter, HTTPException, Request
import aiosqlite

router = APIRouter(prefix="/api/tags", tags=["tags"])


def _get_db_path(request: Request) -> str:
    """Retrieve the database path from FastAPI app state."""
    return request.app.state.db_path


# ---------------------------------------------------------------------------
# List all tags (with model count)
# ---------------------------------------------------------------------------


@router.get("")
async def list_tags(request: Request):
    """List all tags with the number of models associated with each."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT t.id, t.name, COUNT(mt.model_id) as model_count
            FROM tags t
            LEFT JOIN model_tags mt ON mt.tag_id = t.id
            GROUP BY t.id, t.name
            ORDER BY t.name
            """
        )
        rows = await cursor.fetchall()

    return {"tags": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# Create tag
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_tag(request: Request):
    """Create a new tag.

    Expects JSON body: {"name": "tag_name"}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    name = body.get("name")

    if not name or not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=400, detail="'name' is required and must be a non-empty string")

    name = name.strip()

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Check if tag already exists (case-insensitive due to COLLATE NOCASE)
        cursor = await db.execute("SELECT id, name FROM tags WHERE name = ?", (name,))
        existing = await cursor.fetchone()
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Tag '{name}' already exists",
            )

        cursor = await db.execute("INSERT INTO tags (name) VALUES (?)", (name,))
        tag_id = cursor.lastrowid
        await db.commit()

    return {"id": tag_id, "name": name}


# ---------------------------------------------------------------------------
# Delete tag
# ---------------------------------------------------------------------------


@router.delete("/{tag_id}")
async def delete_tag(request: Request, tag_id: int):
    """Delete a tag by ID. Also removes all model-tag associations."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Verify tag exists
        cursor = await db.execute("SELECT id, name FROM tags WHERE id = ?", (tag_id,))
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")

        tag_name = dict(row)["name"]

        # Delete the tag (model_tags entries cascade)
        await db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        await db.commit()

    return {"detail": f"Tag '{tag_name}' (id={tag_id}) deleted"}


# ---------------------------------------------------------------------------
# Rename tag
# ---------------------------------------------------------------------------


@router.put("/{tag_id}")
async def rename_tag(request: Request, tag_id: int):
    """Rename a tag.

    Expects JSON body: {"name": "new_name"}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    new_name = body.get("name")

    if not new_name or not isinstance(new_name, str) or not new_name.strip():
        raise HTTPException(status_code=400, detail="'name' is required and must be a non-empty string")

    new_name = new_name.strip()

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify tag exists
        cursor = await db.execute("SELECT id FROM tags WHERE id = ?", (tag_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")

        # Check if new name conflicts with an existing tag
        cursor = await db.execute(
            "SELECT id FROM tags WHERE name = ? AND id != ?", (new_name, tag_id)
        )
        if await cursor.fetchone() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Tag '{new_name}' already exists",
            )

        await db.execute(
            "UPDATE tags SET name = ? WHERE id = ?", (new_name, tag_id)
        )
        await db.commit()

    return {"id": tag_id, "name": new_name}
