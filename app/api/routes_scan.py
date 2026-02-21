"""API routes for triggering and monitoring directory scans."""

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
import aiosqlite

from app.config import settings as app_settings
from app.database import get_db, get_setting, update_fts_for_model
from app.services import hasher, processor, thumbnail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scan", tags=["scan"])


def _get_db_path(request: Request) -> str:
    """Retrieve the database path from FastAPI app state."""
    return request.app.state.db_path


# ---------------------------------------------------------------------------
# Trigger full directory scan
# ---------------------------------------------------------------------------


@router.post("")
async def trigger_scan(request: Request, background_tasks: BackgroundTasks):
    """Trigger a full directory scan in the background.

    The scan walks the configured directory tree, discovers new 3D model
    files, extracts metadata, generates thumbnails, and indexes them in
    the database.

    Returns immediately with a status message. Use ``GET /api/scan/status``
    to monitor progress.
    """
    scanner = getattr(request.app.state, "scanner", None)
    if scanner is None:
        raise HTTPException(
            status_code=503,
            detail="Scanner service is not available",
        )

    if scanner.is_scanning:
        raise HTTPException(
            status_code=409,
            detail="A scan is already in progress",
        )

    background_tasks.add_task(scanner.scan)

    return {
        "detail": "Scan started in background",
        "scanning": True,
    }


# ---------------------------------------------------------------------------
# Get scan status
# ---------------------------------------------------------------------------


@router.get("/status")
async def get_scan_status(request: Request):
    """Get the current status of the directory scanner.

    Returns whether a scan is running, total files discovered, and how
    many have been processed so far.
    """
    scanner = getattr(request.app.state, "scanner", None)
    if scanner is None:
        raise HTTPException(
            status_code=503,
            detail="Scanner service is not available",
        )

    return {
        "scanning": scanner.is_scanning,
        "total_files": scanner.total_files,
        "processed_files": scanner.processed_files,
    }


# ---------------------------------------------------------------------------
# Rebuild FTS index
# ---------------------------------------------------------------------------


@router.post("/reindex")
async def rebuild_fts_index(request: Request):
    """Rebuild the full-text search index from current model data.

    Clears the existing FTS index and re-populates it from all models in
    the database. This is useful after bulk imports or if the FTS index
    gets out of sync.
    """
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Clear existing FTS data
        await db.execute("DELETE FROM models_fts")

        # Re-populate from all models
        await db.execute(
            """
            INSERT INTO models_fts(rowid, name, description)
            SELECT m.id, m.name, m.description
            FROM models m
            """
        )
        await db.commit()

        # Report how many models were indexed
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM models")
        count_row = await cursor.fetchone()
        total = dict(count_row)["cnt"]

    return {
        "detail": "FTS index rebuilt successfully",
        "models_indexed": total,
    }


# ---------------------------------------------------------------------------
# Repair models with missing metadata or thumbnails
# ---------------------------------------------------------------------------


@router.post("/repair")
async def repair_models(request: Request, background_tasks: BackgroundTasks):
    """Reprocess models that have missing metadata or thumbnails.

    Finds models where vertex_count is NULL or thumbnail_path is NULL and
    re-extracts metadata, re-generates thumbnails, and updates the database.
    This is useful after installing missing dependencies (e.g. networkx
    for 3MF, cascadio/gmsh for STEP).

    Runs in the background and returns immediately.
    """
    scanner = getattr(request.app.state, "scanner", None)
    if scanner is not None and scanner.is_scanning:
        raise HTTPException(
            status_code=409,
            detail="A scan is already in progress",
        )

    background_tasks.add_task(_repair_incomplete_models)

    return {"detail": "Repair started in background"}


async def _repair_incomplete_models() -> None:
    """Re-extract metadata and regenerate thumbnails for incomplete models."""
    loop = asyncio.get_running_loop()
    thumbnail_path = str(app_settings.MODEL_LIBRARY_THUMBNAIL_PATH)
    thumb_mode = await get_setting("thumbnail_mode", "wireframe")

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, file_path FROM models "
            "WHERE vertex_count IS NULL OR thumbnail_path IS NULL"
        )
        rows = await cursor.fetchall()

    if not rows:
        logger.info("Repair: no incomplete models found")
        return

    logger.info("Repair: reprocessing %d models with missing data", len(rows))

    repaired = 0
    errors = 0

    for row in rows:
        model_id = row["id"]
        file_path = row["file_path"]

        if not os.path.exists(file_path):
            logger.warning("Repair: file missing for model %d: %s", model_id, file_path)
            errors += 1
            continue

        try:
            # Re-extract metadata
            metadata = await loop.run_in_executor(
                None, processor.extract_metadata, file_path
            )

            # Re-compute file hash
            file_hash = await loop.run_in_executor(
                None, hasher.compute_file_hash, file_path
            )

            # Re-generate thumbnail
            thumb_filename = await loop.run_in_executor(
                None,
                thumbnail.generate_thumbnail,
                file_path,
                thumbnail_path,
                model_id,
                thumb_mode,
            )

            # Update the database record
            async with get_db() as db:
                await db.execute(
                    """UPDATE models SET
                        vertex_count = ?,
                        face_count = ?,
                        dimensions_x = ?,
                        dimensions_y = ?,
                        dimensions_z = ?,
                        file_hash = COALESCE(?, file_hash),
                        thumbnail_path = COALESCE(?, thumbnail_path),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?""",
                    (
                        metadata.get("vertex_count"),
                        metadata.get("face_count"),
                        metadata.get("dimensions_x"),
                        metadata.get("dimensions_y"),
                        metadata.get("dimensions_z"),
                        file_hash,
                        thumb_filename,
                        model_id,
                    ),
                )
                await update_fts_for_model(db, model_id)
                await db.commit()

            repaired += 1
            logger.debug("Repair: updated model %d (%s)", model_id, file_path)

        except Exception:
            logger.exception("Repair: failed to reprocess model %d", model_id)
            errors += 1

    logger.info(
        "Repair complete: %d repaired, %d errors out of %d total",
        repaired,
        errors,
        len(rows),
    )
