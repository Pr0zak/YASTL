"""API routes for URL-based model import and file upload."""

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.database import get_db
from app.services.importer import (
    MODEL_EXTENSIONS,
    delete_credentials,
    get_credentials,
    get_import_progress,
    import_urls_batch,
    mask_credentials,
    process_imported_file,
    scrape_metadata,
    set_credentials,
    _deduplicate_path,
    _sanitize_filename,
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
        "error": meta.get("error"),
    }


@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    library_id: int = Form(...),
    subfolder: str | None = Form(None),
):
    """Upload local 3D model files and process them into the library."""
    # Look up library path
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, path FROM libraries WHERE id = ?", (library_id,)
        )
        lib = await cursor.fetchone()
        if lib is None:
            raise HTTPException(status_code=404, detail="Library not found")

    library_path = lib["path"]
    dest_dir = Path(library_path)
    if subfolder:
        dest_dir = dest_dir / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for upload in files:
        fname = _sanitize_filename(upload.filename or "upload")
        ext = Path(fname).suffix.lower()
        if ext not in MODEL_EXTENSIONS:
            results.append({"filename": fname, "status": "error", "error": f"Unsupported format: {ext}"})
            continue

        dest = _deduplicate_path(dest_dir / fname)
        try:
            content = await upload.read()
            with open(dest, "wb") as f:
                f.write(content)

            model_id = await process_imported_file(
                file_path=dest,
                library_id=library_id,
                subfolder=subfolder,
                library_path=library_path,
            )
            if model_id is not None:
                results.append({"filename": fname, "status": "ok", "model_id": model_id})
            else:
                results.append({"filename": fname, "status": "error", "error": "Processing failed or duplicate"})
        except Exception as e:
            logger.warning("Upload processing failed for %s: %s", fname, e)
            results.append({"filename": fname, "status": "error", "error": str(e)})

    ok = sum(1 for r in results if r["status"] == "ok")
    return {"detail": f"{ok}/{len(results)} file(s) imported", "results": results}


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
