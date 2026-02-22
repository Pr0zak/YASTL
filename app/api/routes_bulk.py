"""API routes for bulk operations on models."""

import os

from fastapi import APIRouter, HTTPException, Request
import aiosqlite

from app.api._helpers import apply_auto_tags

router = APIRouter(prefix="/api/bulk", tags=["bulk"])


def _get_db_path(request: Request) -> str:
    return request.app.state.db_path


@router.post("/tags")
async def bulk_add_tags(request: Request):
    """Add tags to multiple models.

    Expects JSON body: {"model_ids": [1, 2, 3], "tags": ["tag1", "tag2"]}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    model_ids = body.get("model_ids", [])
    tag_names = body.get("tags", [])

    if not model_ids or not isinstance(model_ids, list):
        raise HTTPException(
            status_code=400, detail="'model_ids' must be a non-empty list"
        )
    if not tag_names or not isinstance(tag_names, list):
        raise HTTPException(
            status_code=400, detail="'tags' must be a non-empty list"
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        affected = 0
        for tag_name in tag_names:
            tag_name = tag_name.strip()
            if not tag_name:
                continue

            # Create tag if it doesn't exist
            cursor = await db.execute(
                "SELECT id FROM tags WHERE name = ?", (tag_name,)
            )
            tag_row = await cursor.fetchone()
            if tag_row is None:
                cursor = await db.execute(
                    "INSERT INTO tags (name) VALUES (?)", (tag_name,)
                )
                tag_id = cursor.lastrowid
            else:
                tag_id = dict(tag_row)["id"]

            for model_id in model_ids:
                # Verify model exists
                cursor = await db.execute(
                    "SELECT id FROM models WHERE id = ?", (model_id,)
                )
                if await cursor.fetchone() is None:
                    continue

                await db.execute(
                    "INSERT OR IGNORE INTO model_tags (model_id, tag_id) VALUES (?, ?)",
                    (model_id, tag_id),
                )
                affected += 1

        await db.commit()

    return {"detail": "Tags applied to models", "affected": affected}


@router.post("/categories")
async def bulk_add_categories(request: Request):
    """Add categories to multiple models.

    Expects JSON body: {"model_ids": [1, 2, 3], "category_ids": [10, 20]}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    model_ids = body.get("model_ids", [])
    category_ids = body.get("category_ids", [])

    if not model_ids or not isinstance(model_ids, list):
        raise HTTPException(
            status_code=400, detail="'model_ids' must be a non-empty list"
        )
    if not category_ids or not isinstance(category_ids, list):
        raise HTTPException(
            status_code=400, detail="'category_ids' must be a non-empty list"
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        affected = 0
        for category_id in category_ids:
            # Verify category exists
            cursor = await db.execute(
                "SELECT id FROM categories WHERE id = ?", (category_id,)
            )
            if await cursor.fetchone() is None:
                continue

            for model_id in model_ids:
                cursor = await db.execute(
                    "SELECT id FROM models WHERE id = ?", (model_id,)
                )
                if await cursor.fetchone() is None:
                    continue

                await db.execute(
                    "INSERT OR IGNORE INTO model_categories "
                    "(model_id, category_id) VALUES (?, ?)",
                    (model_id, category_id),
                )
                affected += 1

        await db.commit()

    return {"detail": "Categories applied to models", "affected": affected}


@router.post("/collections")
async def bulk_add_to_collection(request: Request):
    """Add multiple models to a collection.

    Expects JSON body: {"model_ids": [1, 2, 3], "collection_id": 5}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    model_ids = body.get("model_ids", [])
    collection_id = body.get("collection_id")

    if not model_ids or not isinstance(model_ids, list):
        raise HTTPException(
            status_code=400, detail="'model_ids' must be a non-empty list"
        )
    if collection_id is None:
        raise HTTPException(
            status_code=400, detail="'collection_id' is required"
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Verify collection exists
        cursor = await db.execute(
            "SELECT id FROM collections WHERE id = ?", (collection_id,)
        )
        if await cursor.fetchone() is None:
            raise HTTPException(
                status_code=404, detail=f"Collection {collection_id} not found"
            )

        # Get current max position
        cursor = await db.execute(
            "SELECT COALESCE(MAX(position), -1) as max_pos "
            "FROM collection_models WHERE collection_id = ?",
            (collection_id,),
        )
        max_pos = dict(await cursor.fetchone())["max_pos"]

        added = 0
        for model_id in model_ids:
            cursor = await db.execute(
                "SELECT id FROM models WHERE id = ?", (model_id,)
            )
            if await cursor.fetchone() is None:
                continue

            max_pos += 1
            await db.execute(
                "INSERT OR IGNORE INTO collection_models "
                "(collection_id, model_id, position) VALUES (?, ?, ?)",
                (collection_id, model_id, max_pos),
            )
            added += 1

        await db.execute(
            "UPDATE collections SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (collection_id,),
        )
        await db.commit()

    return {"detail": f"Added {added} model(s) to collection", "added": added}


@router.post("/favorite")
async def bulk_favorite(request: Request):
    """Favorite or unfavorite multiple models.

    Expects JSON body: {"model_ids": [1, 2, 3], "favorite": true}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    model_ids = body.get("model_ids", [])
    favorite = body.get("favorite", True)

    if not model_ids or not isinstance(model_ids, list):
        raise HTTPException(
            status_code=400, detail="'model_ids' must be a non-empty list"
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        affected = 0
        for model_id in model_ids:
            cursor = await db.execute(
                "SELECT id FROM models WHERE id = ?", (model_id,)
            )
            if await cursor.fetchone() is None:
                continue

            if favorite:
                await db.execute(
                    "INSERT OR IGNORE INTO favorites (model_id) VALUES (?)",
                    (model_id,),
                )
            else:
                await db.execute(
                    "DELETE FROM favorites WHERE model_id = ?", (model_id,)
                )
            affected += 1

        await db.commit()

    action = "favorited" if favorite else "unfavorited"
    return {"detail": f"{affected} model(s) {action}", "affected": affected}


@router.post("/delete")
async def bulk_delete(request: Request):
    """Delete multiple models.

    Expects JSON body: {"model_ids": [1, 2, 3]}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    model_ids = body.get("model_ids", [])

    if not model_ids or not isinstance(model_ids, list):
        raise HTTPException(
            status_code=400, detail="'model_ids' must be a non-empty list"
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        deleted = 0
        thumbnail_paths = []

        for model_id in model_ids:
            cursor = await db.execute(
                "SELECT id, thumbnail_path FROM models WHERE id = ?", (model_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                continue

            model_dict = dict(row)
            if model_dict.get("thumbnail_path"):
                thumbnail_paths.append(model_dict["thumbnail_path"])

            await db.execute(
                "DELETE FROM models_fts WHERE rowid = ?", (model_id,)
            )
            await db.execute("DELETE FROM models WHERE id = ?", (model_id,))
            deleted += 1

        await db.commit()

    # Clean up thumbnail files
    for path in thumbnail_paths:
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    return {"detail": f"{deleted} model(s) deleted", "deleted": deleted}


@router.post("/auto-tags")
async def bulk_auto_tags(request: Request):
    """Generate and apply tag suggestions to multiple models.

    Expects JSON body: {"model_ids": [1, 2, 3]}

    For each model, generates tag suggestions from metadata (filename words,
    categories, format, size, complexity) and applies them.
    """
    db_path = _get_db_path(request)
    body = await request.json()
    model_ids = body.get("model_ids", [])

    if not model_ids or not isinstance(model_ids, list):
        raise HTTPException(
            status_code=400, detail="'model_ids' must be a non-empty list"
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        total_tags_added = 0
        models_tagged = 0

        for model_id in model_ids:
            tags_added = await apply_auto_tags(db, model_id)
            if tags_added > 0:
                models_tagged += 1
                total_tags_added += tags_added

        await db.commit()

    return {
        "detail": f"Auto-tagged {models_tagged} model(s) with {total_tags_added} tags",
        "models_tagged": models_tagged,
        "tags_added": total_tags_added,
    }
