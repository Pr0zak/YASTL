"""API routes for serving 3D model files, downloads, GLB conversion, and thumbnails."""

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
import aiosqlite

from app.config import settings
from app.database import get_setting
from app.services import thumbnail
from app.services.preview import build_preview_glb
from app.workers import run_cpu_job
from app.api._helpers import open_db, _get_db_path, _resolve_model_file, resolve_thumbnail, MIME_TYPES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["model-files"])

# Maximum total size of the GLB preview cache in bytes (500 MB)
_GLB_CACHE_MAX_BYTES = 500 * 1024 * 1024


def _evict_glb_cache(cache_dir: str) -> None:
    """Evict oldest GLB cache entries if total size exceeds the limit."""
    try:
        entries = []
        total_size = 0
        for name in os.listdir(cache_dir):
            if not name.endswith(".glb"):
                continue
            path = os.path.join(cache_dir, name)
            try:
                stat = os.stat(path)
                entries.append((path, stat.st_mtime, stat.st_size))
                total_size += stat.st_size
            except OSError:
                continue

        if total_size <= _GLB_CACHE_MAX_BYTES:
            return

        # Sort by mtime ascending (oldest first) and delete until under limit
        entries.sort(key=lambda e: e[1])
        for path, _, size in entries:
            if total_size <= _GLB_CACHE_MAX_BYTES:
                break
            try:
                os.remove(path)
                total_size -= size
                logger.debug("Evicted GLB cache: %s (%.1f MB)", path, size / 1024 / 1024)
            except OSError:
                continue
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Serve 3D model file
# ---------------------------------------------------------------------------


@router.get("/{model_id}/file")
async def serve_model_file(request: Request, model_id: int):
    """Serve the actual 3D model file for the Three.js viewer."""
    db_path = _get_db_path(request)

    async with open_db(db_path) as db:
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
@router.get("/{model_id}/download/{filename}")
async def download_model_file(request: Request, model_id: int, filename: str | None = None):
    """Download the original 3D model file as an attachment.

    The optional trailing ``filename`` segment is cosmetic and ignored:
    slicer URL schemes (Bambu Studio, OrcaSlicer, PrusaSlicer) detect the
    file format from the URL path extension, so the frontend appends
    ``<name>.<ext>`` to the download URL it hands to the slicer.
    """
    db_path = _get_db_path(request)

    async with open_db(db_path) as db:
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

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT id, file_path, name, zip_path, zip_entry, face_count "
            "FROM models WHERE id = ?",
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
    from app.services.preview import preview_cache_name

    cache_path = os.path.join(cache_dir, preview_cache_name(model_id))

    if os.path.exists(cache_path):
        src_mtime = os.path.getmtime(file_path)
        cache_mtime = os.path.getmtime(cache_path)
        if src_mtime <= cache_mtime:
            return FileResponse(
                path=cache_path,
                media_type="model/gltf-binary",
                filename=f"{os.path.splitext(model['name'])[0]}.glb",
            )

    # Build a decimated preview GLB in the worker pool (OOM-protected, off
    # the event loop). Large meshes are simplified so the client parse is
    # trivial and the viewer never blocks; small meshes pass through.
    # Recycle the worker after a big-mesh conversion so its memory doesn't
    # linger for the next request (small meshes don't need it).
    heavy = (model.get("face_count") or 0) > 200_000
    try:
        glb_data = await run_cpu_job(build_preview_glb, file_path, recycle=heavy)
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

    # Evict old cache entries if over size limit
    _evict_glb_cache(cache_dir)

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

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT thumbnail_path FROM models WHERE id = ?", (model_id,)
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    model = dict(row)
    thumbnail_path = resolve_thumbnail(model.get("thumbnail_path"))

    if not thumbnail_path or not os.path.exists(thumbnail_path):
        raise HTTPException(status_code=404, detail="Thumbnail not available")

    return FileResponse(
        path=thumbnail_path,
        media_type="image/png",
    )


# ---------------------------------------------------------------------------
# Regenerate thumbnail for a single model
# ---------------------------------------------------------------------------


@router.post("/{model_id}/regenerate-thumbnail")
async def regenerate_model_thumbnail(request: Request, model_id: int):
    """Regenerate the thumbnail for a single model."""
    db_path = _get_db_path(request)
    thumbnail_path = str(settings.MODEL_LIBRARY_THUMBNAIL_PATH)

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT id, file_path, zip_path, zip_entry FROM models WHERE id = ?",
            (model_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    model = dict(row)
    actual_path = _resolve_model_file(model)

    if actual_path is None:
        raise HTTPException(status_code=404, detail="Model file not found on disk")

    thumb_mode = await get_setting("thumbnail_mode", "solid")
    thumb_quality = await get_setting("thumbnail_quality", "fast")

    thumb_filename: str | None = await asyncio.to_thread(
        thumbnail.generate_thumbnail,
        actual_path,
        thumbnail_path,
        model_id,
        thumb_mode,
        thumb_quality,
    )

    if thumb_filename is None:
        raise HTTPException(
            status_code=422, detail="Failed to generate thumbnail"
        )

    async with open_db(db_path) as db:
        await db.execute(
            "UPDATE models SET thumbnail_path = ?, thumbnail_mode = ?, thumbnail_quality = ?, thumbnail_generated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (thumb_filename, thumb_mode, thumb_quality, model_id),
        )
        await db.commit()

    return {
        "detail": "Thumbnail regenerated",
        "thumbnail_path": thumb_filename,
    }


# ---------------------------------------------------------------------------
# Model docs (README / license / photos sitting next to the model)
# ---------------------------------------------------------------------------

_DOC_EXTS = {".md", ".txt", ".rst", ".pdf", ".nfo"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_MAX_README_BYTES = 60_000


def _is_readme(name: str) -> bool:
    low = name.lower()
    return low.startswith("readme") or low.startswith("read_me")


def _doc_kind(name: str) -> str | None:
    ext = os.path.splitext(name)[1].lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _DOC_EXTS or _is_readme(name) or "license" in name.lower():
        return "doc"
    return None


async def _model_docs(model: dict):
    """Return (base_dir, entries) where entries is a list of sibling doc/image
    files. Handles both loose files on disk and files inside a zip archive.
    Returns (None, []) when nothing is available."""
    zip_path = model.get("zip_path")
    if zip_path:
        if not os.path.exists(zip_path):
            return None, []
        import zipfile
        from pathlib import PurePosixPath

        entry_dir = str(PurePosixPath(model.get("zip_entry", "")).parent)
        found = []
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    p = PurePosixPath(info.filename)
                    base = p.name
                    if base.startswith(".") or base.startswith("__MACOSX"):
                        continue
                    kind = _doc_kind(base)
                    if kind and (str(p.parent) == entry_dir or str(p.parent) == "."):
                        found.append((info.filename, base, kind, info.file_size))
        except Exception:
            logger.exception("Failed reading docs from zip %s", zip_path)
        return zip_path, found

    file_path = model.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return None, []
    base_dir = os.path.dirname(file_path)
    found = []
    try:
        for entry in os.scandir(base_dir):
            if not entry.is_file() or entry.name.startswith("."):
                continue
            kind = _doc_kind(entry.name)
            if kind:
                found.append((entry.name, entry.name, kind, entry.stat().st_size))
    except OSError:
        return None, []
    return base_dir, found


@router.get("/{model_id}/docs")
async def list_model_docs(request: Request, model_id: int):
    """List README/license/photo files next to a model, with README text."""
    db_path = _get_db_path(request)
    async with open_db(db_path) as db:
        cursor = await db.execute(
            "SELECT id, file_path, zip_path, zip_entry FROM models WHERE id = ?",
            (model_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    base, entries = await _model_docs(dict(row))
    docs, images, readme = [], [], None
    for full, name, kind, size in entries:
        if kind == "image":
            images.append({"name": name, "path": full, "size": size})
        else:
            docs.append({"name": name, "path": full, "size": size})

    # Pick a README and read a preview of its text
    readme_entry = next(
        (d for d in docs if _is_readme(d["name"])
         and os.path.splitext(d["name"])[1].lower() in (".md", ".txt", ".rst", "")),
        None,
    )
    if readme_entry is not None:
        try:
            data = await _read_doc_bytes(dict(row), readme_entry["path"], base)
            if data is not None:
                text = data[:_MAX_README_BYTES].decode("utf-8", errors="replace")
                readme = {"name": readme_entry["name"], "text": text,
                          "truncated": len(data) > _MAX_README_BYTES}
        except Exception:
            logger.debug("Could not read README for model %d", model_id)

    return {"readme": readme, "docs": docs, "images": images}


async def _read_doc_bytes(model: dict, entry_path: str, base) -> bytes | None:
    """Read a sibling doc/image, confined to the model's directory / zip."""
    if model.get("zip_path"):
        import zipfile
        try:
            with zipfile.ZipFile(model["zip_path"], "r") as zf:
                return zf.read(entry_path)
        except Exception:
            return None
    # loose file: confine to base_dir
    safe = os.path.normpath(os.path.join(base, os.path.basename(entry_path)))
    if not safe.startswith(os.path.realpath(base) + os.sep) and safe != base:
        # basename-only join already prevents traversal, but double-check
        if os.path.dirname(safe) != base:
            return None
    if not os.path.isfile(safe):
        return None
    with open(safe, "rb") as f:
        return f.read()


@router.get("/{model_id}/docs/file")
async def serve_model_doc(request: Request, model_id: int, name: str):
    """Serve a specific sibling doc/image file for a model (by basename)."""
    db_path = _get_db_path(request)
    async with open_db(db_path) as db:
        cursor = await db.execute(
            "SELECT id, file_path, zip_path, zip_entry FROM models WHERE id = ?",
            (model_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    model = dict(row)
    base, entries = await _model_docs(model)
    match = next((e for e in entries if e[1] == os.path.basename(name)), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Doc not found")

    data = await _read_doc_bytes(model, match[0], base)
    if data is None:
        raise HTTPException(status_code=404, detail="Doc not readable")

    ext = os.path.splitext(match[1])[1].lower()
    media = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
        ".pdf": "application/pdf", ".md": "text/markdown", ".txt": "text/plain",
    }.get(ext, "application/octet-stream")

    from fastapi.responses import Response
    return Response(content=data, media_type=media)
