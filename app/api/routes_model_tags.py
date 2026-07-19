"""API routes for managing tags on individual models."""

import logging

from fastapi import APIRouter, HTTPException, Request

from app.api._helpers import _get_db_path, _fetch_model_with_relations, open_db
from app.database import update_fts_for_model

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

    async with open_db(db_path) as db:
        model = await _fetch_model_with_relations(db, model_id)

    if model is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    suggestions = suggest_tags(model)
    return {"model_id": model_id, "suggestions": suggestions}


@router.get("/{model_id}/related-tags")
async def related_tags(request: Request, model_id: int, limit: int = 8):
    """Tags that frequently co-occur with this model's tags on other models.

    Powers "Often tagged with" suggestions: for models sharing any of this
    model's tags, count the OTHER tags and rank them, excluding tags this
    model already has.
    """
    db_path = _get_db_path(request)
    async with open_db(db_path) as db:
        cursor = await db.execute(
            "SELECT tag_id FROM model_tags WHERE model_id = ?", (model_id,)
        )
        own = [r["tag_id"] for r in await cursor.fetchall()]
        if not own:
            return {"model_id": model_id, "suggestions": []}

        ph = ", ".join("?" for _ in own)
        cursor = await db.execute(
            f"""
            SELECT t.name, COUNT(*) AS cnt
            FROM model_tags mt_self
            JOIN model_tags mt_other
              ON mt_other.model_id = mt_self.model_id
             AND mt_other.tag_id != mt_self.tag_id
            JOIN tags t ON t.id = mt_other.tag_id
            WHERE mt_self.tag_id IN ({ph})
              AND mt_other.tag_id NOT IN ({ph})
              AND mt_self.model_id != ?
            GROUP BY mt_other.tag_id
            ORDER BY cnt DESC, t.name
            LIMIT ?
            """,
            [*own, *own, model_id, limit],
        )
        suggestions = [r["name"] for r in await cursor.fetchall()]
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

    async with open_db(db_path) as db:
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

        await update_fts_for_model(db, model_id)
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

    async with open_db(db_path) as db:
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

        await update_fts_for_model(db, model_id)
        await db.commit()

    return {"detail": f"Tag '{tag_name}' removed from model {model_id}"}
