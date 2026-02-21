"""API routes for serving 3D model files, downloads, GLB conversion, and thumbnails."""

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
import aiosqlite
import trimesh

from app.config import settings
from app.api._helpers import _get_db_path, _resolve_model_file, MIME_TYPES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["model-files"])


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
