"""API routes for application settings."""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.config import settings as app_settings
from app.database import get_all_settings, get_db, get_setting, set_setting, update_fts_for_model
from app.services import thumbnail
from app.services.importer import extract_zip_metadata, extract_folder_metadata
from app.api._helpers import apply_auto_tags
from app.workers import get_pool, log_memory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Settings with their allowed values and defaults
SETTINGS_SCHEMA: dict[str, dict] = {
    "thumbnail_mode": {
        "allowed": ["wireframe", "solid"],
        "default": "wireframe",
    },
    "bed_shape": {
        "allowed": ["rectangular", "circular"],
        "default": "rectangular",
    },
    "bed_enabled": {
        "allowed": ["true", "false"],
        "default": "false",
    },
    "color_theme": {
        "allowed": ["default", "light"],
        "default": "default",
    },
    "favorites_first": {
        "allowed": ["true", "false"],
        "default": "false",
    },
    "collection_card_tint": {
        "allowed": ["true", "false"],
        "default": "false",
    },
}

# Numeric settings with min/max validation (stored as strings in DB)
NUMERIC_SETTINGS: dict[str, dict] = {
    "bed_width": {"default": "256", "min": 50, "max": 1000},
    "bed_depth": {"default": "256", "min": 50, "max": 1000},
    "bed_height": {"default": "256", "min": 50, "max": 1000},
}

# Module-level regeneration progress state
_regen_progress: dict = {
    "running": False,
    "total": 0,
    "completed": 0,
}

# Module-level auto-tag progress state
_autotag_progress: dict = {
    "running": False,
    "total": 0,
    "completed": 0,
    "tags_added": 0,
}

# Module-level metadata backfill progress state
_metadata_progress: dict = {
    "running": False,
    "total": 0,
    "completed": 0,
    "updated": 0,
}


@router.get("")
async def get_settings():
    """Return all application settings with defaults applied."""
    stored = await get_all_settings()
    result: dict[str, str] = {}
    for key, schema in SETTINGS_SCHEMA.items():
        result[key] = stored.get(key, schema["default"])
    for key, schema in NUMERIC_SETTINGS.items():
        result[key] = stored.get(key, schema["default"])
    return result


@router.put("")
async def update_settings(body: dict):
    """Update one or more application settings.

    Accepts a JSON object with setting keys and their new values.
    Only known setting keys with valid values are accepted.
    """
    updated: dict[str, str] = {}
    for key, value in body.items():
        schema = SETTINGS_SCHEMA.get(key)
        numeric = NUMERIC_SETTINGS.get(key)
        if schema is None and numeric is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown setting: {key}",
            )
        if schema is not None:
            if value not in schema["allowed"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid value for {key}: {value!r}. "
                    f"Allowed: {schema['allowed']}",
                )
        elif numeric is not None:
            try:
                num_val = int(value)
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid value for {key}: {value!r}. Must be an integer.",
                )
            if num_val < numeric["min"] or num_val > numeric["max"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Value for {key} must be between {numeric['min']} and {numeric['max']}.",
                )
            value = str(num_val)
        await set_setting(key, value)
        updated[key] = value

    # Return all settings after update
    stored = await get_all_settings()
    result: dict[str, str] = {}
    for key, schema in SETTINGS_SCHEMA.items():
        result[key] = stored.get(key, schema["default"])
    for key, schema in NUMERIC_SETTINGS.items():
        result[key] = stored.get(key, schema["default"])
    return result


@router.post("/regenerate-thumbnails")
async def regenerate_thumbnails(request: Request, background_tasks: BackgroundTasks):
    """Regenerate all thumbnails using the current thumbnail_mode setting.

    Runs in the background and returns immediately.
    """
    if _regen_progress["running"]:
        raise HTTPException(
            status_code=409,
            detail="Thumbnail regeneration is already in progress",
        )

    thumbnail_path = str(app_settings.MODEL_LIBRARY_THUMBNAIL_PATH)
    mode = await get_setting("thumbnail_mode", "wireframe")
    quality = await get_setting("thumbnail_quality", "fast")

    background_tasks.add_task(_regenerate_all_thumbnails, thumbnail_path, mode, quality)

    return {"detail": "Thumbnail regeneration started in background"}


@router.get("/regenerate-thumbnails/status")
async def regenerate_thumbnails_status():
    """Return the current progress of thumbnail regeneration."""
    return {
        "running": _regen_progress["running"],
        "total": _regen_progress["total"],
        "completed": _regen_progress["completed"],
    }


async def _regenerate_all_thumbnails(
    thumbnail_path: str, mode: str, quality: str = "fast"
) -> None:
    """Walk all models and regenerate their thumbnails.

    Runs thumbnail generation in a ProcessPoolExecutor so the event loop
    stays responsive on another core while CPU-bound rendering happens.
    """
    from app.services import zip_handler

    loop = asyncio.get_event_loop()
    pool = get_pool()

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, file_path, zip_path, zip_entry FROM models "
            "WHERE status = 'active'"
        )
        rows = await cursor.fetchall()

    _regen_progress["running"] = True
    _regen_progress["total"] = len(rows)
    _regen_progress["completed"] = 0

    logger.info(
        "Regenerating thumbnails for %d models (mode=%s, quality=%s)",
        len(rows), mode, quality,
    )
    log_memory("regen_start")

    async def _process_one(row: dict) -> None:
        """Regenerate a single model's thumbnail."""
        import time

        model_id = row["id"]
        zip_path = row["zip_path"]
        zip_entry = row["zip_entry"]
        tmp_path = None
        t0 = time.monotonic()
        try:
            if zip_path and zip_entry:
                tmp_path = await loop.run_in_executor(
                    None, zip_handler.extract_entry_to_temp,
                    zip_path, zip_entry,
                )
                render_path = str(tmp_path)
            else:
                render_path = row["file_path"]

            thumb_filename: str | None = await loop.run_in_executor(
                pool,
                thumbnail.generate_thumbnail,
                render_path,
                thumbnail_path,
                model_id,
                mode,
                quality,
            )
            if thumb_filename is not None:
                async with get_db() as db:
                    await db.execute(
                        "UPDATE models SET thumbnail_path = ?, thumbnail_mode = ?, thumbnail_quality = ?, thumbnail_generated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (thumb_filename, mode, quality, model_id),
                    )
                    await db.commit()
        except Exception as e:
            logger.warning(
                "Failed to regenerate thumbnail for model %d: %s", model_id, e
            )
        finally:
            elapsed = time.monotonic() - t0
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            _regen_progress["completed"] += 1
            # Flag slow models and check memory pressure
            if elapsed > 10:
                logger.warning(
                    "Slow thumbnail: model %d took %.1fs (%s)",
                    model_id, elapsed, row["file_path"],
                )
                log_memory(f"slow_model_{model_id}")

    try:
        for idx, row in enumerate(rows):
            await _process_one(row)
            # Log memory every 50 models for diagnostics
            if (idx + 1) % 50 == 0:
                log_memory(f"regen_progress_{idx + 1}/{len(rows)}")
            # Brief yield so the event loop stays responsive
            await asyncio.sleep(0.05)
    finally:
        _regen_progress["running"] = False

    log_memory("regen_complete")
    logger.info("Thumbnail regeneration complete")


@router.post("/auto-tag-all")
async def auto_tag_all(background_tasks: BackgroundTasks):
    """Generate and apply tag suggestions to all active models.

    Runs in the background and returns immediately.
    """
    if _autotag_progress["running"]:
        raise HTTPException(
            status_code=409,
            detail="Auto-tagging is already in progress",
        )

    background_tasks.add_task(_auto_tag_all_models)

    return {"detail": "Auto-tagging started in background"}


@router.get("/auto-tag-all/status")
async def auto_tag_all_status():
    """Return the current progress of the auto-tag-all operation."""
    return {
        "running": _autotag_progress["running"],
        "total": _autotag_progress["total"],
        "completed": _autotag_progress["completed"],
        "tags_added": _autotag_progress["tags_added"],
    }


async def _auto_tag_all_models() -> None:
    """Walk all active models and apply auto-tag suggestions."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM models WHERE status = 'active'"
        )
        rows = await cursor.fetchall()

    model_ids = [row["id"] for row in rows]

    _autotag_progress["running"] = True
    _autotag_progress["total"] = len(model_ids)
    _autotag_progress["completed"] = 0
    _autotag_progress["tags_added"] = 0

    logger.info("Auto-tagging %d models", len(model_ids))

    try:
        for model_id in model_ids:
            try:
                async with get_db() as db:
                    tags_added = await apply_auto_tags(db, model_id)
                    await db.commit()
                _autotag_progress["tags_added"] += tags_added
            except Exception as e:
                logger.warning(
                    "Failed to auto-tag model %d: %s", model_id, e
                )
            finally:
                _autotag_progress["completed"] += 1
                await asyncio.sleep(0.01)
    finally:
        _autotag_progress["running"] = False

    logger.info(
        "Auto-tagging complete: %d models, %d tags added",
        _autotag_progress["total"],
        _autotag_progress["tags_added"],
    )


@router.post("/extract-metadata")
async def extract_metadata_all(background_tasks: BackgroundTasks):
    """Extract metadata from zip/folder README files for all active models.

    Only updates models that currently have an empty description.
    Runs in the background and returns immediately.
    """
    if _metadata_progress["running"]:
        raise HTTPException(
            status_code=409,
            detail="Metadata extraction is already in progress",
        )

    background_tasks.add_task(_extract_metadata_all_models)

    return {"detail": "Metadata extraction started in background"}


@router.get("/extract-metadata/status")
async def extract_metadata_status():
    """Return the current progress of the metadata extraction operation."""
    return {
        "running": _metadata_progress["running"],
        "total": _metadata_progress["total"],
        "completed": _metadata_progress["completed"],
        "updated": _metadata_progress["updated"],
    }


async def _extract_metadata_all_models() -> None:
    """Walk all active models and extract metadata from their zip/folder files."""
    loop = asyncio.get_event_loop()

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, file_path, zip_path, description, source_url "
            "FROM models WHERE status = 'active' AND "
            "(description IS NULL OR description = '')"
        )
        rows = [dict(r) for r in await cursor.fetchall()]

    _metadata_progress["running"] = True
    _metadata_progress["total"] = len(rows)
    _metadata_progress["completed"] = 0
    _metadata_progress["updated"] = 0

    logger.info("Extracting metadata for %d models", len(rows))

    # Caches to avoid re-parsing the same zip/folder
    zip_cache: dict[str, dict] = {}
    folder_cache: dict[str, dict] = {}

    try:
        for row in rows:
            model_id = row["id"]
            try:
                meta: dict = {}

                if row["zip_path"]:
                    # Zip-based model
                    zp = row["zip_path"]
                    if zp not in zip_cache:
                        try:
                            zip_cache[zp] = await loop.run_in_executor(
                                None, extract_zip_metadata, Path(zp)
                            )
                        except Exception:
                            zip_cache[zp] = {}
                    meta = zip_cache[zp]
                else:
                    # Regular file — check parent folder
                    folder = str(Path(row["file_path"]).parent)
                    if folder not in folder_cache:
                        try:
                            folder_cache[folder] = await loop.run_in_executor(
                                None, extract_folder_metadata, Path(folder)
                            )
                        except Exception:
                            folder_cache[folder] = {}
                    meta = folder_cache[folder]

                description = meta.get("description") or ""
                source_url = meta.get("source_url")
                tags = meta.get("tags", [])
                site = meta.get("site")

                if not description and not source_url and not tags:
                    continue

                async with get_db() as db:
                    # Update description and source_url
                    updates = []
                    params = []
                    if description:
                        updates.append("description = ?")
                        params.append(description)
                    if source_url and not row["source_url"]:
                        updates.append("source_url = ?")
                        params.append(source_url)

                    if updates:
                        params.append(model_id)
                        await db.execute(
                            f"UPDATE models SET {', '.join(updates)} WHERE id = ?",
                            tuple(params),
                        )

                    # Apply tags
                    all_tags = list(tags)
                    if site and site not in all_tags:
                        all_tags.append(site)
                    for tag_name in all_tags:
                        tag_name = tag_name.strip()
                        if not tag_name:
                            continue
                        await db.execute(
                            "INSERT OR IGNORE INTO tags (name) VALUES (?)",
                            (tag_name,),
                        )
                        cursor = await db.execute(
                            "SELECT id FROM tags WHERE name = ? COLLATE NOCASE",
                            (tag_name,),
                        )
                        tag_row = await cursor.fetchone()
                        if tag_row:
                            tag_id = tag_row["id"]
                            await db.execute(
                                "INSERT OR IGNORE INTO model_tags (model_id, tag_id) VALUES (?, ?)",
                                (model_id, tag_id),
                            )

                    # Update FTS index
                    await update_fts_for_model(db, model_id)
                    await db.commit()

                _metadata_progress["updated"] += 1

            except Exception as e:
                logger.warning(
                    "Failed to extract metadata for model %d: %s", model_id, e
                )
            finally:
                _metadata_progress["completed"] += 1
                await asyncio.sleep(0.01)
    finally:
        _metadata_progress["running"] = False

    logger.info(
        "Metadata extraction complete: %d models checked, %d updated",
        _metadata_progress["total"],
        _metadata_progress["updated"],
    )
