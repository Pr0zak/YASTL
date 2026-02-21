"""API routes for 3D model CRUD operations and file serving."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
import aiosqlite
import os
import trimesh

from app.config import settings
from app.services import zip_handler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["models"])

# Extension to MIME type mapping for 3D file serving
MIME_TYPES: dict[str, str] = {
    ".stl": "model/stl",
    ".obj": "text/plain",
    ".gltf": "model/gltf+json",
    ".glb": "model/gltf-binary",
    ".3mf": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
    ".ply": "application/x-ply",
    ".fbx": "application/octet-stream",
}


def _get_db_path(request: Request) -> str:
    """Retrieve the database path from FastAPI app state."""
    return request.app.state.db_path


def _resolve_model_file(model: dict) -> str | None:
    """Resolve the on-disk path for a model, extracting from zip if needed.

    For regular files, returns the ``file_path`` directly.
    For zip-contained models, ensures the entry is extracted to the
    persistent cache and returns the cached path.

    Returns ``None`` if the file cannot be found.
    """
    zip_path = model.get("zip_path")
    if zip_path:
        # Model lives inside a zip archive
        if not os.path.exists(zip_path):
            return None
        entry_name = model.get("zip_entry", "")
        cache_dir = str(settings.MODEL_LIBRARY_THUMBNAIL_PATH)
        model_id = model["id"]
        try:
            return zip_handler.ensure_cached(zip_path, entry_name, cache_dir, model_id)
        except Exception:
            logger.exception(
                "Failed to extract zip entry %s from %s", entry_name, zip_path
            )
            return None
    else:
        file_path = model["file_path"]
        if os.path.exists(file_path):
            return file_path
        return None


# ---------------------------------------------------------------------------
# Helper: fetch a model with its tags and categories
# ---------------------------------------------------------------------------


async def _fetch_model_with_relations(
    db: aiosqlite.Connection,
    model_id: int,
) -> dict | None:
    """Load a single model row along with its tags and categories.

    Returns None if the model does not exist.
    """
    cursor = await db.execute("SELECT * FROM models WHERE id = ?", (model_id,))
    row = await cursor.fetchone()
    if row is None:
        return None

    model = dict(row)

    # Fetch tags
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

    # Fetch categories
    cursor = await db.execute(
        """
        SELECT c.id, c.name FROM categories c
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

    return model


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
    sort_by: str = Query(default="updated_at"),
    sort_order: str = Query(default="desc"),
    library_id: int | None = Query(default=None),
):
    """List models with pagination and filters.

    Supports multi-tag (AND logic) and multi-category (OR logic) filtering,
    collection membership, favorites, library, and configurable sorting.
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

        if format is not None:
            where_clauses.append("m.file_format = ?")
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

        return {"models": models, "total": total, "limit": limit, "offset": offset}


# ---------------------------------------------------------------------------
# Get single model
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


# ---------------------------------------------------------------------------
# Serve 3D model file
# ---------------------------------------------------------------------------


@router.get("/{model_id}/file")
async def serve_model_file(request: Request, model_id: int):
    """Serve the actual 3D model file for the Three.js viewer."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT id, file_path, name, zip_path, zip_entry FROM models WHERE id = ?",
            (model_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    model = dict(row)
    resolved_path = _resolve_model_file(model)

    if resolved_path is None:
        raise HTTPException(status_code=404, detail="Model file not found on disk")

    # Determine content type from extension
    ext = os.path.splitext(resolved_path)[1].lower()
    media_type = MIME_TYPES.get(ext, "application/octet-stream")

    filename = os.path.basename(resolved_path)

    return FileResponse(
        path=resolved_path,
        media_type=media_type,
        filename=filename,
    )


# ---------------------------------------------------------------------------
# Download model file
# ---------------------------------------------------------------------------


@router.get("/{model_id}/download")
async def download_model_file(request: Request, model_id: int):
    """Download the original 3D model file as an attachment."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT id, file_path, name, file_format, zip_path, zip_entry FROM models WHERE id = ?",
            (model_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    model = dict(row)
    resolved_path = _resolve_model_file(model)

    if resolved_path is None:
        raise HTTPException(status_code=404, detail="Model file not found on disk")

    # Build a download filename from the model name + original extension
    ext = os.path.splitext(resolved_path)[1].lower()
    model_name = model["name"]
    # Ensure the filename has the correct extension
    if not model_name.lower().endswith(ext):
        download_name = f"{model_name}{ext}"
    else:
        download_name = model_name

    media_type = MIME_TYPES.get(ext, "application/octet-stream")

    return FileResponse(
        path=resolved_path,
        media_type=media_type,
        filename=download_name,
        content_disposition_type="attachment",
    )


# ---------------------------------------------------------------------------
# Serve GLB conversion for browser preview
# ---------------------------------------------------------------------------


@router.get("/{model_id}/file/glb")
async def serve_model_glb(request: Request, model_id: int):
    """Convert and serve a model as GLB for browser 3D preview.

    Enables preview of formats not natively supported by Three.js
    (e.g. 3MF, DAE, FBX) by converting them to GLB via trimesh.
    Results are cached alongside thumbnails.
    """
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT id, file_path, name, zip_path, zip_entry FROM models WHERE id = ?",
            (model_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    model = dict(row)
    file_path = _resolve_model_file(model)

    if file_path is None:
        raise HTTPException(status_code=404, detail="Model file not found on disk")

    # Check cache
    cache_dir = os.path.join(
        str(settings.MODEL_LIBRARY_THUMBNAIL_PATH), "preview_cache"
    )
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{model_id}.glb")

    if os.path.exists(cache_path):
        src_mtime = os.path.getmtime(file_path)
        cache_mtime = os.path.getmtime(cache_path)
        if src_mtime <= cache_mtime:
            return FileResponse(
                path=cache_path,
                media_type="model/gltf-binary",
                filename=f"{os.path.splitext(model['name'])[0]}.glb",
            )

    # Convert using trimesh in a thread pool to avoid blocking
    def _convert():
        loaded = None

        try:
            loaded = trimesh.load(file_path, force=None)
        except Exception as e:
            logger.debug("trimesh.load failed for %s: %s", file_path, e)

        # For STEP/STP files, fall back to the dedicated converter
        if loaded is None or (
            isinstance(loaded, trimesh.Scene) and len(loaded.geometry) == 0
        ):
            from app.services.step_converter import is_step_file, load_step

            if is_step_file(file_path):
                logger.debug("Trying STEP converter for %s", file_path)
                mesh = load_step(file_path)
                if mesh is not None:
                    loaded = mesh

        if loaded is None:
            raise ValueError(f"Cannot load file for GLB conversion: {file_path}")

        if isinstance(loaded, trimesh.Trimesh):
            return loaded.export(file_type="glb")
        elif isinstance(loaded, trimesh.Scene):
            try:
                return loaded.export(file_type="glb")
            except Exception:
                # Scene GLB export failed; concatenate into a single mesh
                concatenated = trimesh.load(file_path, force="mesh")
                return concatenated.export(file_type="glb")
        else:
            raise ValueError(
                f"Cannot convert to GLB: unsupported type {type(loaded).__name__}"
            )

    try:
        glb_data = await asyncio.to_thread(_convert)
    except Exception as e:
        logger.warning(
            "GLB conversion failed for model %d (%s): %s", model_id, file_path, e
        )
        raise HTTPException(
            status_code=422,
            detail="Could not convert model to GLB for preview",
        )

    # Write to cache
    with open(cache_path, "wb") as f:
        f.write(glb_data)

    return FileResponse(
        path=cache_path,
        media_type="model/gltf-binary",
        filename=f"{os.path.splitext(model['name'])[0]}.glb",
    )


# ---------------------------------------------------------------------------
# Serve thumbnail
# ---------------------------------------------------------------------------


@router.get("/{model_id}/thumbnail")
async def serve_thumbnail(request: Request, model_id: int):
    """Serve the thumbnail image for a model."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT thumbnail_path FROM models WHERE id = ?", (model_id,)
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    model = dict(row)
    thumbnail_path = model.get("thumbnail_path")

    if not thumbnail_path or not os.path.exists(thumbnail_path):
        raise HTTPException(status_code=404, detail="Thumbnail not available")

    return FileResponse(
        path=thumbnail_path,
        media_type="image/png",
    )


# ---------------------------------------------------------------------------
# Tag management on a model
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


# ---------------------------------------------------------------------------
# Category management on a model
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
