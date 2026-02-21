"""Shared helper functions for model API routes."""

import logging
import os
import re

import aiosqlite
from fastapi import Request

from app.config import settings
from app.services import zip_handler

logger = logging.getLogger(__name__)

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


def _sanitize_filename(name: str) -> str:
    """Clean a string for use as a filename."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(". ")
    return name or "model"


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

    # Collections
    cursor = await db.execute(
        """
        SELECT c.id, c.name, c.color FROM collections c
        JOIN collection_models cm ON cm.collection_id = c.id
        WHERE cm.model_id = ?
        ORDER BY c.name
        """,
        (model_id,),
    )
    col_rows = await cursor.fetchall()
    model["collections"] = [dict(r) for r in col_rows]

    return model
