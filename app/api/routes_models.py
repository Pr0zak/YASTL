"""API routes for 3D model CRUD operations."""

import logging
import os

from fastapi import APIRouter, HTTPException, Query, Request
import aiosqlite
from pathlib import Path

from app.config import settings
from app.services import zip_handler
from app.api._helpers import (
    _get_db_path,
    _fetch_model_with_relations,
    _sanitize_filename,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["models"])


# ---------------------------------------------------------------------------
# List models (with pagination and optional filters)
# ---------------------------------------------------------------------------


@router.get("")
async def list_models(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    format: str | None = Query(default=None, alias="format"),
    tag: str | None = Query(default=None),
    tags: str | None = Query(default=None),
    category: str | None = Query(default=None),
    categories: str | None = Query(default=None),
    collection: int | None = Query(default=None),
    favorites_only: bool = Query(default=False),
    duplicates_only: bool = Query(default=False),
    sort_by: str = Query(default="updated_at"),
    sort_order: str = Query(default="desc"),
    library_id: int | None = Query(default=None),
):
    """List models with pagination and filters.

    Supports multi-tag (AND logic) and multi-category (OR logic) filtering,
    collection membership, favorites, duplicates, library, and configurable
    sorting.
    """
    db_path = _get_db_path(request)

    # Validate sort params
    allowed_sort = {
        "name", "created_at", "updated_at", "file_size",
        "vertex_count", "face_count",
    }
    if sort_by not in allowed_sort:
        sort_by = "updated_at"
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"

    # Merge single tag/tags params into one list
    tag_list: list[str] = []
    if tag:
        tag_list.append(tag)
    if tags:
        tag_list.extend(t.strip() for t in tags.split(",") if t.strip())

    # Merge single category/categories params
    category_list: list[str] = []
    if category:
        category_list.append(category)
    if categories:
        category_list.extend(c.strip() for c in categories.split(",") if c.strip())

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Build dynamic query with filters
        where_clauses: list[str] = []
        params: list[str | int] = []

        # Only show active models by default (exclude missing/deleted)
        where_clauses.append("m.status = 'active'")

        if format is not None:
            where_clauses.append("LOWER(m.file_format) = ?")
            params.append(format.lower())

        # Multi-tag filter (AND logic — model must have ALL tags)
        if tag_list:
            tag_placeholders = ", ".join("?" for _ in tag_list)
            where_clauses.append(
                f"""m.id IN (
                    SELECT mt.model_id FROM model_tags mt
                    JOIN tags t ON t.id = mt.tag_id
                    WHERE t.name IN ({tag_placeholders})
                    GROUP BY mt.model_id
                    HAVING COUNT(DISTINCT t.name) = ?
                )"""
            )
            params.extend(tag_list)
            params.append(len(tag_list))

        # Multi-category filter (OR logic — model in ANY category)
        if category_list:
            cat_placeholders = ", ".join("?" for _ in category_list)
            where_clauses.append(
                f"""m.id IN (
                    SELECT mc.model_id FROM model_categories mc
                    JOIN categories c ON c.id = mc.category_id
                    WHERE c.name IN ({cat_placeholders})
                )"""
            )
            params.extend(category_list)

        # Collection filter
        if collection is not None:
            where_clauses.append(
                "m.id IN (SELECT cm.model_id FROM collection_models cm "
                "WHERE cm.collection_id = ?)"
            )
            params.append(collection)

        # Favorites filter
        if favorites_only:
            where_clauses.append(
                "m.id IN (SELECT f.model_id FROM favorites f)"
            )

        # Duplicates filter — only show models whose hash appears more than once
        if duplicates_only:
            where_clauses.append(
                """m.file_hash IS NOT NULL AND m.file_hash != ''
                AND m.file_hash IN (
                    SELECT file_hash FROM models
                    WHERE file_hash IS NOT NULL AND file_hash != ''
                      AND status = 'active'
                    GROUP BY file_hash
                    HAVING COUNT(*) > 1
                )"""
            )

        if library_id is not None:
            where_clauses.append("m.library_id = ?")
            params.append(library_id)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Count total matching models
        count_sql = f"SELECT COUNT(*) as cnt FROM models m {where_sql}"
        cursor = await db.execute(count_sql, params)
        total_row = await cursor.fetchone()
        total = dict(total_row)["cnt"]

        # Fetch the page of models with sorting
        order_sql = f"m.{sort_by} {sort_order}"
        query_sql = f"""
            SELECT m.* FROM models m
            {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
        """
        cursor = await db.execute(query_sql, params + [limit, offset])
        rows = await cursor.fetchall()

        # Enrich each model with tags, categories, and favorite status
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

            # Favorite status
            cursor = await db.execute(
                "SELECT 1 FROM favorites WHERE model_id = ?", (model_id,)
            )
            model["is_favorite"] = await cursor.fetchone() is not None

            models.append(model)

        # Mark duplicates: compute set of hashes that appear more than once
        hashes_in_page = [m["file_hash"] for m in models if m.get("file_hash")]
        dup_hashes: set[str] = set()
        if hashes_in_page:
            placeholders = ", ".join("?" for _ in hashes_in_page)
            cursor = await db.execute(
                f"""SELECT file_hash FROM models
                    WHERE file_hash IN ({placeholders})
                      AND file_hash IS NOT NULL AND file_hash != ''
                      AND status = 'active'
                    GROUP BY file_hash
                    HAVING COUNT(*) > 1""",
                hashes_in_page,
            )
            dup_hashes = {dict(r)["file_hash"] for r in await cursor.fetchall()}

        for m in models:
            m["is_duplicate"] = bool(m.get("file_hash") and m["file_hash"] in dup_hashes)

        return {"models": models, "total": total, "limit": limit, "offset": offset}


# ---------------------------------------------------------------------------
# Find duplicates
# ---------------------------------------------------------------------------


@router.get("/duplicates")
async def find_duplicates(request: Request):
    """Find all groups of duplicate files, grouped by file_hash where count > 1."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Find hashes with more than one model
        cursor = await db.execute(
            """
            SELECT file_hash, COUNT(*) as count
            FROM models
            WHERE file_hash IS NOT NULL AND file_hash != ''
              AND status = 'active'
            GROUP BY file_hash
            HAVING COUNT(*) > 1
            ORDER BY count DESC
            """
        )
        hash_rows = await cursor.fetchall()

        groups = []
        for hash_row in hash_rows:
            hash_dict = dict(hash_row)
            file_hash = hash_dict["file_hash"]

            cursor = await db.execute(
                "SELECT * FROM models WHERE file_hash = ? ORDER BY name",
                (file_hash,),
            )
            model_rows = await cursor.fetchall()
            groups.append(
                {
                    "file_hash": file_hash,
                    "count": hash_dict["count"],
                    "models": [dict(r) for r in model_rows],
                }
            )

        return {"duplicate_groups": groups, "total_groups": len(groups)}


# ---------------------------------------------------------------------------
# Get single model
# ---------------------------------------------------------------------------


@router.get("/{model_id}")
async def get_model(request: Request, model_id: int):
    """Get a single model by ID with its tags and categories."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        model = await _fetch_model_with_relations(db, model_id)

    if model is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    return model


# ---------------------------------------------------------------------------
# Update model
# ---------------------------------------------------------------------------


@router.put("/{model_id}")
async def update_model(request: Request, model_id: int):
    """Update a model's name and/or description."""
    db_path = _get_db_path(request)
    body = await request.json()

    name = body.get("name")
    description = body.get("description")

    if name is None and description is None:
        raise HTTPException(
            status_code=400,
            detail="At least one of 'name' or 'description' is required",
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Verify model exists
        cursor = await db.execute("SELECT id FROM models WHERE id = ?", (model_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        # Build dynamic UPDATE
        set_clauses: list[str] = []
        params: list[str | int] = []

        if name is not None:
            set_clauses.append("name = ?")
            params.append(name)
        if description is not None:
            set_clauses.append("description = ?")
            params.append(description)

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        params.append(model_id)

        await db.execute(
            f"UPDATE models SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )

        # Update FTS index
        from app.database import update_fts_for_model

        await update_fts_for_model(db, model_id)
        await db.commit()

        model = await _fetch_model_with_relations(db, model_id)

    return model


# ---------------------------------------------------------------------------
# Rename file on disk
# ---------------------------------------------------------------------------


@router.post("/{model_id}/rename-file")
async def rename_model_file(request: Request, model_id: int):
    """Rename the actual file on disk based on the model's display name.

    Preserves the original file extension. Updates file_path in the database.
    Does not work for zip-embedded models.
    """
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        model = await _fetch_model_with_relations(db, model_id)
        if model is None:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        if model.get("zip_path"):
            raise HTTPException(
                status_code=400,
                detail="Cannot rename files inside zip archives",
            )

        old_path = Path(model["file_path"])
        if not old_path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")

        # Build new filename from model name
        new_stem = _sanitize_filename(model["name"])
        ext = old_path.suffix  # preserve original extension
        new_name = f"{new_stem}{ext}"
        new_path = old_path.parent / new_name

        # Avoid overwriting existing files
        if new_path != old_path and new_path.exists():
            counter = 1
            while True:
                candidate = old_path.parent / f"{new_stem}_{counter}{ext}"
                if not candidate.exists():
                    new_path = candidate
                    break
                counter += 1

        if new_path == old_path:
            return {**model, "detail": "File already has this name"}

        # Rename on disk
        try:
            old_path.rename(new_path)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Rename failed: {e}")

        # Update database
        await db.execute(
            "UPDATE models SET file_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(new_path), model_id),
        )

        from app.database import update_fts_for_model
        await update_fts_for_model(db, model_id)
        await db.commit()

        model = await _fetch_model_with_relations(db, model_id)

    logger.info("Renamed file: %s -> %s", old_path, new_path)
    return model


# ---------------------------------------------------------------------------
# Delete model
# ---------------------------------------------------------------------------


@router.delete("/{model_id}")
async def delete_model(request: Request, model_id: int):
    """Delete a model and its thumbnail file."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Fetch model to get thumbnail path and zip info before deletion
        cursor = await db.execute(
            "SELECT id, thumbnail_path, zip_path, zip_entry FROM models WHERE id = ?",
            (model_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        model_dict = dict(row)
        thumbnail_path = model_dict.get("thumbnail_path")

        # Remove FTS entry
        await db.execute("DELETE FROM models_fts WHERE rowid = ?", (model_id,))

        # Delete the model (cascades to model_tags and model_categories)
        await db.execute("DELETE FROM models WHERE id = ?", (model_id,))
        await db.commit()

    # Remove thumbnail file from disk
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            os.remove(thumbnail_path)
        except OSError:
            pass  # Non-critical: log but don't fail

    # Remove cached GLB preview if it exists
    glb_cache_path = os.path.join(
        str(settings.MODEL_LIBRARY_THUMBNAIL_PATH), "preview_cache", f"{model_id}.glb"
    )
    if os.path.exists(glb_cache_path):
        try:
            os.remove(glb_cache_path)
        except OSError:
            pass

    # Remove cached zip extraction if it exists
    if model_dict.get("zip_path"):
        zip_handler.cleanup_zip_cache(
            str(settings.MODEL_LIBRARY_THUMBNAIL_PATH), model_id
        )

    return {"detail": f"Model {model_id} deleted"}
