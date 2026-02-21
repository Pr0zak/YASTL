"""API routes for managing tags on individual models."""

import logging

from fastapi import APIRouter, HTTPException, Request
import aiosqlite

from app.api._helpers import _get_db_path, _fetch_model_with_relations

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["model-tags"])


# ---------------------------------------------------------------------------
# Tag suggestions
# ---------------------------------------------------------------------------


@router.get("/suggest-tags/{model_id}")
async def suggest_tags_for_model(request: Request, model_id: int):
    """Return tag suggestions for a model based on its metadata."""
    from app.services.tagger import suggest_tags

    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        model = await _fetch_model_with_relations(db, model_id)

    if model is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    suggestions = suggest_tags(model)
    return {"model_id": model_id, "suggestions": suggestions}


# ---------------------------------------------------------------------------
# Add tags to a model
# ---------------------------------------------------------------------------


@router.post("/{model_id}/tags")
async def add_tags_to_model(request: Request, model_id: int):
    """Add tags to a model. Creates tags if they don't already exist.

    Expects JSON body: {"tags": ["tag1", "tag2", ...]}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    tag_names = body.get("tags", [])

    if not tag_names or not isinstance(tag_names, list):
        raise HTTPException(status_code=400, detail="'tags' must be a non-empty list")

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Verify model exists
        cursor = await db.execute("SELECT id FROM models WHERE id = ?", (model_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        added_tags = []
        for tag_name in tag_names:
            tag_name = tag_name.strip()
            if not tag_name:
                continue

            # Create tag if it doesn't exist
            cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_row = await cursor.fetchone()

            if tag_row is None:
                cursor = await db.execute(
                    "INSERT INTO tags (name) VALUES (?)", (tag_name,)
                )
                tag_id = cursor.lastrowid
            else:
                tag_id = dict(tag_row)["id"]

            # Link tag to model (ignore if already linked)
            await db.execute(
                "INSERT OR IGNORE INTO model_tags (model_id, tag_id) VALUES (?, ?)",
                (model_id, tag_id),
            )
            added_tags.append(tag_name)

        await db.commit()

        # Return updated model
        model = await _fetch_model_with_relations(db, model_id)

    return model


# ---------------------------------------------------------------------------
# Remove tag from a model
# ---------------------------------------------------------------------------


@router.delete("/{model_id}/tags/{tag_name}")
async def remove_tag_from_model(request: Request, model_id: int, tag_name: str):
    """Remove a tag from a model."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Verify model exists
        cursor = await db.execute("SELECT id FROM models WHERE id = ?", (model_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        # Find the tag
        cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
        tag_row = await cursor.fetchone()
        if tag_row is None:
            raise HTTPException(status_code=404, detail=f"Tag '{tag_name}' not found")

        tag_id = dict(tag_row)["id"]

        # Remove the link
        result = await db.execute(
            "DELETE FROM model_tags WHERE model_id = ? AND tag_id = ?",
            (model_id, tag_id),
        )
        if result.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Tag '{tag_name}' is not associated with model {model_id}",
            )

        await db.commit()

    return {"detail": f"Tag '{tag_name}' removed from model {model_id}"}
