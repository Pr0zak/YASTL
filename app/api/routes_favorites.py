"""API routes for favorites management."""

from fastapi import APIRouter, HTTPException, Query, Request
import aiosqlite

router = APIRouter(prefix="/api", tags=["favorites"])


def _get_db_path(request: Request) -> str:
    return request.app.state.db_path


@router.get("/favorites")
async def list_favorites(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List all favorited models with pagination."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Count total favorites
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM favorites f "
            "JOIN models m ON m.id = f.model_id"
        )
        total_row = await cursor.fetchone()
        total = dict(total_row)["cnt"]

        # Fetch favorited models
        cursor = await db.execute(
            """
            SELECT m.* FROM models m
            JOIN favorites f ON f.model_id = m.id
            ORDER BY f.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = await cursor.fetchall()

        models = []
        for row in rows:
            model = dict(row)
            model_id = model["id"]

            # Tags
            cursor = await db.execute(
                """
                SELECT t.name FROM tags t
                JOIN model_tags mt ON mt.tag_id = t.id
                WHERE mt.model_id = ?
                ORDER BY t.name
                """,
                (model_id,),
            )
            tag_rows = await cursor.fetchall()
            model["tags"] = [dict(r)["name"] for r in tag_rows]

            # Categories
            cursor = await db.execute(
                """
                SELECT c.name FROM categories c
                JOIN model_categories mc ON mc.category_id = c.id
                WHERE mc.model_id = ?
                ORDER BY c.name
                """,
                (model_id,),
            )
            cat_rows = await cursor.fetchall()
            model["categories"] = [dict(r)["name"] for r in cat_rows]

            model["is_favorite"] = True
            models.append(model)

        return {"models": models, "total": total, "limit": limit, "offset": offset}


@router.post("/models/{model_id}/favorite", status_code=201)
async def add_favorite(request: Request, model_id: int):
    """Add a model to favorites."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Verify model exists
        cursor = await db.execute("SELECT id FROM models WHERE id = ?", (model_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        # Add to favorites (ignore if already favorited)
        await db.execute(
            "INSERT OR IGNORE INTO favorites (model_id) VALUES (?)",
            (model_id,),
        )
        await db.commit()

    return {"detail": f"Model {model_id} added to favorites", "model_id": model_id}


@router.delete("/models/{model_id}/favorite")
async def remove_favorite(request: Request, model_id: int):
    """Remove a model from favorites."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        result = await db.execute(
            "DELETE FROM favorites WHERE model_id = ?", (model_id,)
        )
        if result.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_id} is not in favorites",
            )
        await db.commit()

    return {"detail": f"Model {model_id} removed from favorites"}
