"""API routes for application settings."""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.config import settings as app_settings
from app.database import get_all_settings, get_db, get_setting, set_setting
from app.services import thumbnail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Settings with their allowed values and defaults
SETTINGS_SCHEMA: dict[str, dict] = {
    "thumbnail_mode": {
        "allowed": ["wireframe", "solid"],
        "default": "wireframe",
    },
    "thumbnail_quality": {
        "allowed": ["fast", "quality"],
        "default": "fast",
    },
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
    thumbnail_path = str(app_settings.MODEL_LIBRARY_THUMBNAIL_PATH)
    mode = await get_setting("thumbnail_mode", "wireframe")
    quality = await get_setting("thumbnail_quality", "fast")

    background_tasks.add_task(_regenerate_all_thumbnails, thumbnail_path, mode, quality)

    return {"detail": "Thumbnail regeneration started in background"}


async def _regenerate_all_thumbnails(
    thumbnail_path: str, mode: str, quality: str = "fast"
) -> None:
    """Walk all models and regenerate their thumbnails."""
    loop = asyncio.get_event_loop()
    async with get_db() as db:
        cursor = await db.execute("SELECT id, file_path FROM models")
        rows = await cursor.fetchall()

    logger.info(
        "Regenerating thumbnails for %d models (mode=%s, quality=%s)",
        len(rows), mode, quality,
    )

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
                        "UPDATE models SET thumbnail_path = ? WHERE id = ?",
                        (thumb_filename, model_id),
                    )
                    await db.commit()
        except Exception as e:
            logger.warning(
                "Failed to regenerate thumbnail for model %d: %s", model_id, e
            )

    logger.info("Thumbnail regeneration complete")
