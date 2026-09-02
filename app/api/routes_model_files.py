"""API routes for serving 3D model files, downloads, GLB conversion, and thumbnails."""

import asyncio
import logging
import os
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
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
    from app.services.preview import detail_max_faces, preview_cache_name

    detail = await get_setting("preview_detail", "detailed")
    cache_path = os.path.join(cache_dir, preview_cache_name(model_id, detail))

    src_mtime = os.path.getmtime(file_path)

    def _hit() -> FileResponse:
        return FileResponse(
            path=cache_path,
            media_type="model/gltf-binary",
            filename=f"{os.path.splitext(model['name'])[0]}.glb",
        )

    if os.path.exists(cache_path) and src_mtime <= os.path.getmtime(cache_path):
        return _hit()

    # A model that cannot be converted must not be retried on every open. The
    # conversion runs on a single-worker pool, so one unconvertible file was a
    # repeatable denial of that worker: 95 seconds of work, every time, for a
    # guaranteed failure — while every other preview and thumbnail job queued
    # behind it. The marker is invalidated by the source file changing, so a
    # repaired file converts again on its next open.
    fail_path = cache_path + ".failed"
    if os.path.exists(fail_path) and src_mtime <= os.path.getmtime(fail_path):
        raise HTTPException(
            status_code=422,
            detail="Could not convert model to GLB for preview (cached failure)",
        )

    # Concurrent opens of the same model must share one conversion. Without
    # this, arrowing through a folder queued a separate multi-minute job per
    # request onto the one worker, and the client that had already navigated
    # away still owned a place in that queue.
    lock = _glb_locks.setdefault(model_id, asyncio.Lock())
    try:
        async with lock:
            # Another request may have finished the work while we waited.
            if os.path.exists(cache_path) and src_mtime <= os.path.getmtime(cache_path):
                return _hit()
            if os.path.exists(fail_path) and src_mtime <= os.path.getmtime(fail_path):
                raise HTTPException(
                    status_code=422,
                    detail="Could not convert model to GLB for preview (cached failure)",
                )

            # Build a decimated preview GLB in the worker pool (OOM-protected,
            # off the event loop). Large meshes are simplified so the client
            # parse is trivial and the viewer never blocks; small meshes pass
            # through. Recycle the worker after a big-mesh conversion so its
            # memory doesn't linger for the next request.
            #
            # face_count is NULL for exactly the files whose metadata extraction
            # already failed — the ones most likely to be heavy or broken — so
            # treat an unknown count as heavy rather than as zero.
            face_count = model.get("face_count")
            heavy = face_count is None or face_count > 200_000
            try:
                glb_data = await run_cpu_job(
                    build_preview_glb, file_path, detail_max_faces(detail), recycle=heavy
                )
            except Exception as e:
                logger.warning(
                    "GLB conversion failed for model %d (%s): %s", model_id, file_path, e
                )
                try:
                    with open(fail_path, "wb"):
                        pass
                except OSError:
                    logger.debug("Could not record GLB failure marker for %d", model_id)
                raise HTTPException(
                    status_code=422,
                    detail="Could not convert model to GLB for preview",
                )

            # Write to cache before releasing, so a waiter finds the result
            # rather than starting the same conversion again.
            with open(cache_path, "wb") as f:
                f.write(glb_data)
    finally:
        # Only the last holder clears the entry; a waiter that is still queued
        # re-creates it, which is harmless because the cache check above will
        # short-circuit it.
        if not lock.locked():
            _glb_locks.pop(model_id, None)

    # Evict old cache entries if over size limit
    _evict_glb_cache(cache_dir)

    return _hit()


# One in-flight conversion per model. Entries are removed as each conversion
# settles, so this never grows beyond the number of models being converted.
_glb_locks: dict[int, "asyncio.Lock"] = {}


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

# Cap on images returned for one model, so a folder holding hundreds of photos
# cannot turn the detail panel into a directory listing.
_MAX_DOC_IMAGES = 24

# Shortest stem that may match by prefix. Without a floor, a model called "a"
# would claim every file in the folder.
_MIN_STEM_MATCH = 4


def _is_readme(name: str) -> bool:
    low = name.lower()
    return low.startswith("readme") or low.startswith("read_me")


def _is_folder_doc(name: str) -> bool:
    """True for documents that describe a whole download rather than one model.

    A README or a licence sitting beside twenty STLs belongs to the pack, not to
    any one of them. These stay visible in a shared folder, but are reported
    with scope "folder" so the UI can say whose they are.
    """
    low = name.lower()
    return _is_readme(low) or "license" in low or "licence" in low


def _norm_stem(name: str) -> str:
    """Filename stem reduced to lowercase alphanumerics.

    Lets "Wall Mount v2.stl" match "wall_mount_v2-assembled.jpg", which is how
    people actually name the photo they took of a print.
    """
    stem = os.path.splitext(name)[0].lower()
    return re.sub(r"[^a-z0-9]+", "", stem)


def _stems_related(model_stem: str, other_stem: str) -> bool:
    """Whether a sibling file's name ties it to this model.

    Either name may be the longer one: a photo is usually the model name plus a
    suffix, but a model is sometimes the photo name plus one.
    """
    if not model_stem or not other_stem:
        return False
    if model_stem == other_stem:
        return True
    longer, shorter = (
        (model_stem, other_stem)
        if len(model_stem) >= len(other_stem)
        else (other_stem, model_stem)
    )
    return len(shorter) >= _MIN_STEM_MATCH and longer.startswith(shorter)


def _doc_kind(name: str) -> str | None:
    ext = os.path.splitext(name)[1].lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _DOC_EXTS or _is_readme(name) or "license" in name.lower():
        return "doc"
    return None


async def _model_docs(model: dict, shared_folder: bool = False):
    """Return (base_dir, entries) for the doc/image files belonging to a model.

    Each entry is (full_path, basename, kind, size, scope) where scope is
    "model" for a file named after this model and "folder" for a pack-level
    README or licence.

    When ``shared_folder`` is true the directory holds more than one model, so
    returning everything in it would attribute unrelated files to whichever
    model the user happened to open — the folder's other photos, screenshots
    and stray downloads. In that case only files whose name ties them to this
    model are returned, plus pack-level documents. When the model has the
    folder to itself, everything in it is genuinely its own.

    Handles both loose files on disk and files inside a zip archive. Returns
    (None, []) when nothing is available."""
    model_name = os.path.basename(
        model.get("zip_entry") or model.get("file_path") or ""
    )
    model_stem = _norm_stem(model_name)

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
                        scope = _entry_scope(base, model_stem, shared_folder)
                        if scope is not None:
                            found.append((info.filename, base, kind, info.file_size, scope))
        except Exception:
            logger.exception("Failed reading docs from zip %s", zip_path)
        return zip_path, _cap_images(found)

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
            if not kind:
                continue
            scope = _entry_scope(entry.name, model_stem, shared_folder)
            if scope is not None:
                found.append((entry.name, entry.name, kind, entry.stat().st_size, scope))
    except OSError:
        return None, []
    return base_dir, _cap_images(found)


def _entry_scope(name: str, model_stem: str, shared_folder: bool) -> str | None:
    """Classify a sibling file, or None when it does not belong to this model."""
    if not shared_folder:
        return "model" if _stems_related(model_stem, _norm_stem(name)) else "folder"
    if _stems_related(model_stem, _norm_stem(name)):
        return "model"
    if _is_folder_doc(name):
        return "folder"
    return None


def _cap_images(entries: list) -> list:
    """Keep every document but at most _MAX_DOC_IMAGES images."""
    kept, images = [], 0
    for e in entries:
        if e[2] == "image":
            if images >= _MAX_DOC_IMAGES:
                continue
            images += 1
        kept.append(e)
    return kept


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

    model = dict(row)
    shared = await _folder_holds_other_models(db_path, model)
    base, entries = await _model_docs(model, shared)
    docs, images, readme = [], [], None
    for full, name, kind, size, scope in entries:
        item = {"name": name, "path": full, "size": size, "scope": scope}
        if kind == "image":
            images.append(item)
        else:
            docs.append(item)

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
                          "truncated": len(data) > _MAX_README_BYTES,
                          "scope": readme_entry["scope"]}
        except Exception:
            logger.debug("Could not read README for model %d", model_id)

    return {
        "readme": readme,
        "docs": docs,
        "images": images,
        "shared_folder": shared,
    }


async def _folder_holds_other_models(db_path: str, model: dict) -> bool:
    """Whether this model shares its directory (or zip directory) with others.

    A folder with one model in it is that model's folder, and everything in it
    is fair to show. A folder with fifty is a library directory, where a photo
    is no more this model's than any other's.
    """
    from pathlib import Path, PurePosixPath

    zip_path = model.get("zip_path")
    try:
        async with open_db(db_path) as db:
            if zip_path:
                entry_dir = str(PurePosixPath(model.get("zip_entry", "")).parent)
                cursor = await db.execute(
                    "SELECT zip_entry FROM models WHERE zip_path = ? AND id != ? "
                    "AND status = 'active' LIMIT 200",
                    (zip_path, model["id"]),
                )
                return any(
                    str(PurePosixPath(r[0] or "").parent) == entry_dir
                    for r in await cursor.fetchall()
                )

            file_path = model.get("file_path")
            if not file_path:
                return False
            parent = str(Path(file_path).parent)
            # Same indexed range scan the related-models query uses: SQLite's
            # case-insensitive LIKE cannot use idx_models_file_path. '0' is the
            # character after '/' in ASCII, so this bounds the subtree.
            cursor = await db.execute(
                "SELECT file_path FROM models WHERE file_path > ? AND file_path < ? "
                "AND id != ? AND status = 'active' AND zip_path IS NULL LIMIT 200",
                (parent + "/", parent + "0", model["id"]),
            )
            # The range covers subdirectories too, so compare the parent exactly.
            return any(
                os.path.dirname(r[0] or "") == parent for r in await cursor.fetchall()
            )
    except Exception:
        logger.exception("Could not count folder siblings for model %s", model.get("id"))
        # Fall back to the permissive behaviour rather than hiding real docs.
        return False


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


# ---------------------------------------------------------------------------
# Multi-plate Bambu/Orca 3MF: plate listing + per-plate embedded preview
# ---------------------------------------------------------------------------
async def _model_row(request: Request, model_id: int) -> dict:
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
    return dict(row)


@router.get("/{model_id}/plates")
async def list_model_plates(request: Request, model_id: int):
    """List the build plates of a multi-plate Bambu/Orca 3MF (else one plate)."""
    from app.services.threemf_plates import inspect_3mf

    model = await _model_row(request, model_id)
    resolved = _resolve_model_file(model)
    if resolved is None or not resolved.lower().endswith(".3mf"):
        return {"kind": "plain", "plate_count": 1, "plates": []}
    info = inspect_3mf(resolved)
    for i, plate in enumerate(info["plates"]):
        plate["index"] = i
        plate["has_thumbnail"] = bool(plate.get("thumbnail"))
    return info


@router.get("/{model_id}/plates/{plate_index}/thumbnail")
async def serve_plate_thumbnail(request: Request, model_id: int, plate_index: int):
    """Serve a plate's embedded preview PNG (Bambu's own slicer render)."""
    from app.services.threemf_plates import inspect_3mf, read_plate_thumbnail

    model = await _model_row(request, model_id)
    resolved = _resolve_model_file(model)
    if resolved is None or not resolved.lower().endswith(".3mf"):
        raise HTTPException(status_code=404, detail="Not a 3MF file")
    info = inspect_3mf(resolved)
    if plate_index < 0 or plate_index >= len(info["plates"]):
        raise HTTPException(status_code=404, detail="Plate not found")
    data, ctype = read_plate_thumbnail(resolved, info["plates"][plate_index])
    if data is None:
        raise HTTPException(status_code=404, detail="No embedded preview for this plate")
    return Response(content=data, media_type=ctype)


@router.get("/{model_id}/plates/{plate_index}/glb")
async def serve_plate_glb(request: Request, model_id: int, plate_index: int):
    """Serve a decimated GLB of a single build plate (its objects only)."""
    from app.services.preview import build_plate_glb
    from app.services.threemf_plates import inspect_3mf

    model = await _model_row(request, model_id)
    resolved = _resolve_model_file(model)
    if resolved is None or not resolved.lower().endswith(".3mf"):
        raise HTTPException(status_code=404, detail="Not a 3MF file")
    info = inspect_3mf(resolved)
    if plate_index < 0 or plate_index >= len(info["plates"]):
        raise HTTPException(status_code=404, detail="Plate not found")
    object_ids = info["plates"][plate_index].get("object_ids") or []

    cache_dir = os.path.join(
        str(settings.MODEL_LIBRARY_THUMBNAIL_PATH), "preview_cache"
    )
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"plate_{model_id}_{plate_index}.glb")

    if os.path.exists(cache_path):
        try:
            if os.path.getmtime(resolved) <= os.path.getmtime(cache_path):
                return FileResponse(path=cache_path, media_type="model/gltf-binary")
        except OSError:
            pass

    try:
        glb_data = await run_cpu_job(build_plate_glb, resolved, object_ids, recycle=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("Plate GLB build failed for model %s plate %s: %s",
                       model_id, plate_index, e)
        raise HTTPException(status_code=500, detail="Failed to build plate preview")

    try:
        with open(cache_path, "wb") as f:
            f.write(glb_data)
        _evict_glb_cache(cache_dir)
    except OSError:
        pass
    return Response(content=glb_data, media_type="model/gltf-binary")
