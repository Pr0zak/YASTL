"""API routes for managing categories on individual models."""

import logging

from fastapi import APIRouter, HTTPException, Request
import aiosqlite

from app.api._helpers import _get_db_path, _fetch_model_with_relations

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["model-categories"])


# ---------------------------------------------------------------------------
# Add category to a model
# ---------------------------------------------------------------------------


@router.post("/{model_id}/categories")
async def add_category_to_model(request: Request, model_id: int):
    """Add a category to a model.

    Expects JSON body: {"category_id": 123}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    category_id = body.get("category_id")

    if category_id is None:
        raise HTTPException(status_code=400, detail="'category_id' is required")

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Verify model exists
        cursor = await db.execute("SELECT id FROM models WHERE id = ?", (model_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        # Verify category exists
        cursor = await db.execute(
            "SELECT id FROM categories WHERE id = ?", (category_id,)
        )
        if await cursor.fetchone() is None:
            raise HTTPException(
                status_code=404, detail=f"Category {category_id} not found"
            )

        # Link category to model
        await db.execute(
            "INSERT OR IGNORE INTO model_categories (model_id, category_id) VALUES (?, ?)",
            (model_id, category_id),
        )
        await db.commit()

        model = await _fetch_model_with_relations(db, model_id)

    return model


# ---------------------------------------------------------------------------
# Remove category from a model
# ---------------------------------------------------------------------------


@router.delete("/{model_id}/categories/{category_id}")
async def remove_category_from_model(request: Request, model_id: int, category_id: int):
    """Remove a category from a model."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Verify model exists
        cursor = await db.execute("SELECT id FROM models WHERE id = ?", (model_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        # Remove the link
        result = await db.execute(
            "DELETE FROM model_categories WHERE model_id = ? AND category_id = ?",
            (model_id, category_id),
        )
        if result.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Category {category_id} is not associated with model {model_id}",
            )

        await db.commit()

    return {"detail": f"Category {category_id} removed from model {model_id}"}
