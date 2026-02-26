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


def _zip_display_name(zip_path: str) -> str:
    """Extract a display name from a zip path (filename without .zip extension)."""
    import posixpath
    basename = posixpath.basename(zip_path.replace("\\", "/"))
    if basename.lower().endswith(".zip"):
        return basename[:-4]
    return basename


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
    favorites_first: bool = Query(default=False),
    group_zips: bool = Query(default=False),
    zip_path: str | None = Query(default=None),
    status: str = Query(default="active"),
    tag_match: str = Query(default="and"),
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

        # Filter by model status
        if status == "all":
            # Show all statuses (useful for admin views)
            where_clauses.append("m.status IN ('active', 'error')")
        elif status == "error":
            where_clauses.append("m.status = 'error'")
        else:
            # Default: only show active models (exclude missing/error)
            where_clauses.append("m.status = 'active'")

        if format is not None:
            where_clauses.append("LOWER(m.file_format) = ?")
            params.append(format.lower())

        # Multi-tag filter (AND or OR logic)
        if tag_list:
            tag_placeholders = ", ".join("?" for _ in tag_list)
            if tag_match == "or":
                where_clauses.append(
                    f"""m.id IN (
                        SELECT mt.model_id FROM model_tags mt
                        JOIN tags t ON t.id = mt.tag_id
                        WHERE t.name IN ({tag_placeholders})
                    )"""
                )
                params.extend(tag_list)
            else:
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

        # Zip path filter — show only models from a specific zip archive
        if zip_path is not None:
            where_clauses.append("m.zip_path = ?")
            params.append(zip_path)

        # Zip grouping — collapse zip models into one representative per zip
        zip_group_map: dict[int, dict] = {}  # rep_id -> {count, zip_path, name}
        if group_zips and zip_path is None:
            # Pre-query: find representative models for each zip
            # Build same WHERE for the pre-query (minus any group_zips clause)
            zip_where_sql = ""
            if where_clauses:
                zip_where_sql = "WHERE " + " AND ".join(where_clauses)
            zip_sql = f"""
                SELECT m.zip_path, MIN(m.id) AS rep_id, COUNT(*) AS cnt
                FROM models m
                {zip_where_sql}
                AND m.zip_path IS NOT NULL
                GROUP BY m.zip_path
                HAVING COUNT(*) > 1
            """
            cursor = await db.execute(zip_sql, params)
            zip_rows = await cursor.fetchall()
            rep_ids = set()
            for zr in zip_rows:
                zd = dict(zr)
                rep_ids.add(zd["rep_id"])
                zip_group_map[zd["rep_id"]] = {
                    "count": zd["cnt"],
                    "zip_path": zd["zip_path"],
                    "name": _zip_display_name(zd["zip_path"]),
                }

            if rep_ids:
                # Hide non-representative zip models
                rep_placeholders = ", ".join("?" for _ in rep_ids)
                where_clauses.append(
                    f"(m.zip_path IS NULL OR m.id IN ({rep_placeholders}))"
                )
                params.extend(rep_ids)

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
        fav_prefix = ""
        fav_join = ""
        if favorites_first:
            fav_join = "LEFT JOIN favorites fav ON fav.model_id = m.id"
            fav_prefix = "CASE WHEN fav.model_id IS NOT NULL THEN 0 ELSE 1 END, "
        query_sql = f"""
            SELECT m.* FROM models m
            {fav_join}
            {where_sql}
            ORDER BY {fav_prefix}{order_sql}
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

            # Collections (name + color for card display)
            cursor = await db.execute(
                """
                SELECT c.name, c.color FROM collections c
                JOIN collection_models cm ON cm.collection_id = c.id
                WHERE cm.model_id = ?
                """,
                (model_id,),
            )
            col_rows = await cursor.fetchall()
            model["collections"] = [
                {"name": dict(r)["name"], "color": dict(r)["color"]}
                for r in col_rows
            ]
            model["collection_colors"] = [
                c["color"] for c in model["collections"] if c["color"]
            ]

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

        # Attach zip group info to representative models
        if zip_group_map:
            for m in models:
                if m["id"] in zip_group_map:
                    info = zip_group_map[m["id"]]
                    m["zip_model_count"] = info["count"]
                    m["zip_group_name"] = info["name"]

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
    """Update a model's name, description, and/or source_url."""
    db_path = _get_db_path(request)
    body = await request.json()

    name = body.get("name")
    description = body.get("description")
    # source_url can be a string or null/empty to clear
    source_url = body.get("source_url")
    has_source_url = "source_url" in body

    if name is None and description is None and not has_source_url:
        raise HTTPException(
            status_code=400,
            detail="At least one of 'name', 'description', or 'source_url' is required",
        )

    # Validate source_url format
    if has_source_url and source_url is not None:
        source_url = source_url.strip()
        if source_url == "":
            source_url = None
        elif not source_url.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=400,
                detail="source_url must start with http:// or https://",
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
        if has_source_url:
            set_clauses.append("source_url = ?")
            params.append(source_url)

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
    """Delete a model, its thumbnail, and the source file from disk."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Fetch model to get file path, thumbnail path, and zip info before deletion
        cursor = await db.execute(
            "SELECT id, file_path, thumbnail_path, zip_path, zip_entry FROM models WHERE id = ?",
            (model_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        model_dict = dict(row)
        file_path = model_dict.get("file_path")
        thumbnail_path = model_dict.get("thumbnail_path")
        zip_path = model_dict.get("zip_path")

        # Remove FTS entry
        await db.execute("DELETE FROM models_fts WHERE rowid = ?", (model_id,))

        # Delete the model (cascades to model_tags and model_categories)
        await db.execute("DELETE FROM models WHERE id = ?", (model_id,))
        await db.commit()

    file_deleted = False

    # Delete the source model file from disk
    if file_path and not zip_path:
        # Regular file (not inside a zip) — the file_path is a real filesystem path
        real_path = file_path
        if os.path.isfile(real_path):
            try:
                os.remove(real_path)
                file_deleted = True
                logger.info("Deleted model file from disk: %s", real_path)
            except OSError as e:
                logger.warning("Failed to delete model file %s: %s", real_path, e)

    # Remove thumbnail file from disk
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            os.remove(thumbnail_path)
        except OSError:
            pass

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
    if zip_path:
        zip_handler.cleanup_zip_cache(
            str(settings.MODEL_LIBRARY_THUMBNAIL_PATH), model_id
        )

    return {
        "detail": f"Model {model_id} deleted",
        "file_deleted": file_deleted,
    }


# ---------------------------------------------------------------------------
# Related models (same zip or folder)
# ---------------------------------------------------------------------------


@router.get("/{model_id}/related")
async def get_related_models(request: Request, model_id: int):
    """Return models that share the same zip file or parent folder.

    Returns up to 50 related models excluding the model itself.
    """
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Get the model's zip_path and file_path
        cursor = await db.execute(
            "SELECT id, file_path, zip_path FROM models WHERE id = ?",
            (model_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        model = dict(row)
        related: list[dict] = []

        if model["zip_path"]:
            # Find other models in the same zip
            cursor = await db.execute(
                "SELECT id, name, file_format, file_size, thumbnail_path, zip_entry "
                "FROM models WHERE zip_path = ? AND id != ? AND status = 'active' "
                "ORDER BY name LIMIT 50",
                (model["zip_path"], model_id),
            )
        else:
            # Find other models in the same parent folder
            parent_folder = str(Path(model["file_path"]).parent)
            cursor = await db.execute(
                "SELECT id, name, file_format, file_size, thumbnail_path, zip_entry "
                "FROM models WHERE file_path LIKE ? AND id != ? AND status = 'active' "
                "AND zip_path IS NULL "
                "ORDER BY name LIMIT 50",
                (parent_folder + "/%", model_id),
            )

        related = [dict(r) for r in await cursor.fetchall()]

    return {"related": related, "count": len(related)}
