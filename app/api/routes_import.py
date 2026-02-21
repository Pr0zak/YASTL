"""API routes for URL-based model import."""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.services.importer import (
    delete_credentials,
    get_credentials,
    get_import_progress,
    import_urls_batch,
    mask_credentials,
    scrape_metadata,
    set_credentials,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/import", tags=["import"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ImportRequest(BaseModel):
    urls: list[str]
    library_id: int
    subfolder: str | None = None


class PreviewRequest(BaseModel):
    url: str


class CredentialSetRequest(BaseModel):
    site: str
    credentials: dict


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("")
async def start_import(body: ImportRequest, background_tasks: BackgroundTasks):
    """Start importing models from one or more URLs.

    Downloads files into the selected library path, runs them through the
    processing pipeline, and inserts them into the database.
    """
    progress = get_import_progress()
    if progress["running"]:
        raise HTTPException(
            status_code=409,
            detail="An import is already in progress",
        )

    if not body.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    # Look up library path
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, path FROM libraries WHERE id = ?", (body.library_id,)
        )
        lib = await cursor.fetchone()
        if lib is None:
            raise HTTPException(status_code=404, detail="Library not found")

    library_path = lib["path"]

    # Load credentials for authenticated site access
    credentials = await get_credentials()

    # Clean URLs
    urls = [u.strip() for u in body.urls if u.strip()]
    if not urls:
        raise HTTPException(status_code=400, detail="No valid URLs provided")

    background_tasks.add_task(
        import_urls_batch,
        urls=urls,
        library_id=body.library_id,
        library_path=library_path,
        subfolder=body.subfolder,
        credentials=credentials,
    )

    return {"detail": f"Import started for {len(urls)} URL(s)", "total": len(urls)}


@router.get("/status")
async def import_status():
    """Return the current import progress."""
    return get_import_progress()


@router.post("/preview")
async def preview_url(body: PreviewRequest):
    """Scrape metadata from a URL without downloading files.

    Returns title, description, tags, download file count, and detected site.
    """
    if not body.url.strip():
        raise HTTPException(status_code=400, detail="URL is required")

    credentials = await get_credentials()

    try:
        meta = await scrape_metadata(body.url.strip(), credentials)
    except Exception as e:
        logger.warning("Preview scrape failed for %s: %s", body.url, e)
        raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {e}")

    return {
        "url": body.url.strip(),
        "title": meta.get("title"),
        "description": meta.get("description"),
        "tags": meta.get("tags", []),
        "file_count": len(meta.get("download_urls", [])),
        "source_site": meta.get("source_site"),
    }


@router.get("/credentials")
async def list_credentials():
    """List configured site credentials with values masked."""
    creds = await get_credentials()
    return mask_credentials(creds)


@router.put("/credentials")
async def update_credentials(body: CredentialSetRequest):
    """Set credentials for a specific site."""
    valid_sites = {"thingiverse", "makerworld", "printables", "myminifactory", "cults3d", "thangs"}
    if body.site not in valid_sites:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown site: {body.site}. Valid: {', '.join(sorted(valid_sites))}",
        )
    await set_credentials(body.site, body.credentials)
    creds = await get_credentials()
    return mask_credentials(creds)


@router.delete("/credentials/{site}")
async def remove_credentials(site: str):
    """Remove stored credentials for a site."""
    await delete_credentials(site)
    creds = await get_credentials()
    return mask_credentials(creds)
