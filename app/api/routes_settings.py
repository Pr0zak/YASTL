"""API routes for application settings."""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.config import settings as app_settings
from app.database import get_all_settings, get_db, get_setting, set_setting
from app.services import thumbnail
from app.api._helpers import apply_auto_tags

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Settings with their allowed values and defaults
SETTINGS_SCHEMA: dict[str, dict] = {
    "thumbnail_mode": {
        "allowed": ["wireframe", "solid"],
        "default": "wireframe",
    },
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


@router.get("")
async def get_settings():
    """Return all application settings with defaults applied."""
    stored = await get_all_settings()
    result: dict[str, str] = {}
    for key, schema in SETTINGS_SCHEMA.items():
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
        if schema is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown setting: {key}",
            )
        if value not in schema["allowed"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid value for {key}: {value!r}. "
                f"Allowed: {schema['allowed']}",
            )
        await set_setting(key, value)
        updated[key] = value

    # Return all settings after update
    stored = await get_all_settings()
    result: dict[str, str] = {}
    for key, schema in SETTINGS_SCHEMA.items():
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
    """Walk all models and regenerate their thumbnails."""
    loop = asyncio.get_event_loop()
    async with get_db() as db:
        cursor = await db.execute("SELECT id, file_path FROM models")
        rows = await cursor.fetchall()

    _regen_progress["running"] = True
    _regen_progress["total"] = len(rows)
    _regen_progress["completed"] = 0

    logger.info(
        "Regenerating thumbnails for %d models (mode=%s, quality=%s)",
        len(rows), mode, quality,
    )

    try:
        for row in rows:
            model_id = row["id"]
            file_path = row["file_path"]
            try:
                thumb_filename: str | None = await loop.run_in_executor(
                    None,
                    thumbnail.generate_thumbnail,
                    file_path,
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
                _regen_progress["completed"] += 1
    finally:
        _regen_progress["running"] = False

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
    finally:
        _autotag_progress["running"] = False

    logger.info(
        "Auto-tagging complete: %d models, %d tags added",
        _autotag_progress["total"],
        _autotag_progress["tags_added"],
    )
