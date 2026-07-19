"""API routes for tag management."""

from fastapi import APIRouter, HTTPException, Request
import aiosqlite

from app.api._helpers import open_db

from app.database import update_fts_for_model


async def _refresh_fts_for_tag(db: aiosqlite.Connection, tag_id: int) -> list[int]:
    """Return model ids linked to a tag (call BEFORE mutating the tag)."""
    cursor = await db.execute(
        "SELECT model_id FROM model_tags WHERE tag_id = ?", (tag_id,)
    )
    return [row["model_id"] for row in await cursor.fetchall()]

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

    async with open_db(db_path) as db:
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

    async with open_db(db_path) as db:
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

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Verify tag exists
        cursor = await db.execute("SELECT id, name FROM tags WHERE id = ?", (tag_id,))
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")

        tag_name = dict(row)["name"]

        affected_models = await _refresh_fts_for_tag(db, tag_id)

        # Delete the tag (model_tags entries cascade)
        await db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        for model_id in affected_models:
            await update_fts_for_model(db, model_id)
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

    async with open_db(db_path) as db:
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
        for model_id in await _refresh_fts_for_tag(db, tag_id):
            await update_fts_for_model(db, model_id)
        await db.commit()

    return {"id": tag_id, "name": new_name}


# ---------------------------------------------------------------------------
# Merge tags
# ---------------------------------------------------------------------------


@router.post("/merge")
async def merge_tags(request: Request):
    """Merge one or more source tags into a target tag.

    Every model tagged with a source tag is retargeted to the target tag
    (deduplicated), then the source tags are deleted. FTS is refreshed
    for all affected models.

    Body: {"source_ids": [2, 3], "target_id": 1}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    source_ids = body.get("source_ids") or []
    target_id = body.get("target_id")

    if not isinstance(source_ids, list) or not source_ids:
        raise HTTPException(status_code=400, detail="'source_ids' must be a non-empty list")
    if target_id is None:
        raise HTTPException(status_code=400, detail="'target_id' is required")
    source_ids = [s for s in source_ids if s != target_id]
    if not source_ids:
        raise HTTPException(status_code=400, detail="No source tags distinct from target")

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        cursor = await db.execute("SELECT id FROM tags WHERE id = ?", (target_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Target tag {target_id} not found")

        ph = ", ".join("?" for _ in source_ids)
        cursor = await db.execute(
            f"SELECT DISTINCT model_id FROM model_tags WHERE tag_id IN ({ph})",
            source_ids,
        )
        affected_models = [r["model_id"] for r in await cursor.fetchall()]

        # Retarget links to the target tag (ignore rows that already have it)
        await db.execute(
            f"UPDATE OR IGNORE model_tags SET tag_id = ? WHERE tag_id IN ({ph})",
            [target_id, *source_ids],
        )
        # Any leftover duplicate links (UPDATE OR IGNORE skipped them) are
        # removed with the source tags via cascade.
        await db.execute(f"DELETE FROM tags WHERE id IN ({ph})", source_ids)

        for model_id in affected_models:
            await update_fts_for_model(db, model_id)
        await db.commit()

    return {
        "detail": f"Merged {len(source_ids)} tag(s) into target",
        "target_id": target_id,
        "models_updated": len(affected_models),
    }


# ---------------------------------------------------------------------------
# Delete unused (zero-count) tags
# ---------------------------------------------------------------------------


@router.post("/cleanup")
async def cleanup_unused_tags(request: Request):
    """Delete all tags not attached to any model."""
    db_path = _get_db_path(request)

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        cursor = await db.execute(
            "DELETE FROM tags WHERE id NOT IN "
            "(SELECT DISTINCT tag_id FROM model_tags)"
        )
        removed = cursor.rowcount
        await db.commit()

    return {"detail": f"Removed {removed} unused tag(s)", "removed": removed}
