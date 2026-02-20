"""API routes for triggering and monitoring directory scans."""

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
import aiosqlite

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
