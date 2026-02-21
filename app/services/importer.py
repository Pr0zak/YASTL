"""URL-based model import service.

Downloads 3D model files from URLs, scrapes metadata from known hosting sites
(Thingiverse, MakerWorld, Printables, MyMiniFactory, Cults3D, Thangs), and
feeds them through the standard processing pipeline (metadata extraction,
hashing, thumbnail generation, DB insert, FTS update).
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse, unquote

import httpx
from bs4 import BeautifulSoup

from app.database import get_db, get_setting, update_fts_for_model
from app.services import hasher, processor, thumbnail

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Site detection
# ---------------------------------------------------------------------------

SITE_HOSTS: dict[str, str] = {
    "thingiverse.com": "thingiverse",
    "www.thingiverse.com": "thingiverse",
    "makerworld.com": "makerworld",
    "www.makerworld.com": "makerworld",
    "printables.com": "printables",
    "www.printables.com": "printables",
    "myminifactory.com": "myminifactory",
    "www.myminifactory.com": "myminifactory",
    "cults3d.com": "cults3d",
    "www.cults3d.com": "cults3d",
    "thangs.com": "thangs",
    "www.thangs.com": "thangs",
}

# Extensions we treat as downloadable 3D model files
MODEL_EXTENSIONS: set[str] = {
    ".stl", ".obj", ".gltf", ".glb", ".3mf",
    ".ply", ".dae", ".off", ".step", ".stp", ".fbx", ".zip",
}


def detect_site(url: str) -> str | None:
    """Identify the hosting site from a URL, or None for unknown/direct links."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return None
    return SITE_HOSTS.get(host.lower())


# ---------------------------------------------------------------------------
# Metadata scraping
# ---------------------------------------------------------------------------

async def _fetch_page(client: httpx.AsyncClient, url: str) -> str:
    """GET a URL and return its text content."""
    resp = await client.get(url, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def _extract_og_metadata(html: str) -> dict:
    """Extract Open Graph meta tags from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    title = None
    description = None

    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()

    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        description = og_desc["content"].strip()

    if not title:
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            title = title_tag.string.strip()

    # Attempt to extract tags from meta keywords
    tags: list[str] = []
    meta_kw = soup.find("meta", attrs={"name": "keywords"})
    if meta_kw and meta_kw.get("content"):
        tags = [t.strip() for t in meta_kw["content"].split(",") if t.strip()]

    return {
        "title": title,
        "description": description,
        "tags": tags,
        "download_urls": [],
    }


async def _scrape_thingiverse(
    client: httpx.AsyncClient, url: str, credentials: dict | None = None,
) -> dict:
    """Scrape metadata from Thingiverse.

    If an API key is provided in credentials, uses the REST API for richer data.
    Otherwise falls back to og: tag scraping.
    """
    # Extract thing ID from URL
    match = re.search(r"thing[:/](\d+)", url, re.IGNORECASE)
    thing_id = match.group(1) if match else None

    api_key = (credentials or {}).get("api_key")
    if thing_id and api_key:
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            thing_resp = await client.get(
                f"https://api.thingiverse.com/things/{thing_id}",
                headers=headers,
            )
            thing_resp.raise_for_status()
            thing_data = thing_resp.json()

            files_resp = await client.get(
                f"https://api.thingiverse.com/things/{thing_id}/files",
                headers=headers,
            )
            files_resp.raise_for_status()
            files_data = files_resp.json()

            download_urls = [
                f.get("public_url") or f.get("download_url", "")
                for f in files_data
                if f.get("public_url") or f.get("download_url")
            ]

            tags = [t.get("name", "") for t in thing_data.get("tags", []) if t.get("name")]

            return {
                "title": thing_data.get("name"),
                "description": thing_data.get("description", ""),
                "tags": tags,
                "download_urls": download_urls,
                "source_site": "thingiverse",
            }
        except Exception as e:
            logger.warning("Thingiverse API failed for thing %s: %s, falling back to scrape", thing_id, e)

    # Fallback: og: tag scraping
    html = await _fetch_page(client, url)
    meta = _extract_og_metadata(html)
    meta["source_site"] = "thingiverse"

    # Try to find download links in page
    soup = BeautifulSoup(html, "html.parser")
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if "/download" in href or any(href.lower().endswith(ext) for ext in MODEL_EXTENSIONS):
            if href.startswith("/"):
                href = f"https://www.thingiverse.com{href}"
            meta["download_urls"].append(href)

    return meta


async def _scrape_generic(
    client: httpx.AsyncClient, url: str, site_name: str, _credentials: dict | None = None,
) -> dict:
    """Generic og: tag scraper for sites without specific API support."""
    try:
        html = await _fetch_page(client, url)
    except httpx.HTTPStatusError:
        return {
            "title": None,
            "description": None,
            "tags": [],
            "download_urls": [],
            "source_site": site_name,
        }
    meta = _extract_og_metadata(html)
    meta["source_site"] = site_name

    # Try to find download links
    soup = BeautifulSoup(html, "html.parser")
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if any(href.lower().endswith(ext) for ext in MODEL_EXTENSIONS):
            if href.startswith("/"):
                parsed = urlparse(url)
                href = f"{parsed.scheme}://{parsed.netloc}{href}"
            meta["download_urls"].append(href)

    return meta


# Scraper registry: maps site key to async scraper function
_SCRAPERS: dict[str, callable] = {
    "thingiverse": _scrape_thingiverse,
}

# Generic sites use the same og: scraper
for _site in ("makerworld", "printables", "myminifactory", "cults3d", "thangs"):
    _SCRAPERS[_site] = lambda client, url, creds=None, s=_site: _scrape_generic(client, url, s, creds)


async def scrape_metadata(
    url: str, credentials: dict | None = None,
) -> dict:
    """Detect site and scrape metadata for a URL.

    Returns dict with keys: title, description, tags, download_urls, source_site.
    """
    site = detect_site(url)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        if site and site in _SCRAPERS:
            site_creds = (credentials or {}).get(site)
            return await _SCRAPERS[site](client, url, site_creds)
        else:
            # Unknown site / direct link
            return {
                "title": None,
                "description": None,
                "tags": [],
                "download_urls": [url],
                "source_site": None,
            }


# ---------------------------------------------------------------------------
# File download
# ---------------------------------------------------------------------------

def _sanitize_filename(name: str) -> str:
    """Remove or replace characters unsafe for filenames."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(". ")
    return name or "download"


def _deduplicate_path(dest: Path) -> Path:
    """Append _1, _2, etc. if the file already exists."""
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


async def download_file(
    url: str,
    client: httpx.AsyncClient,
    dest_dir: Path,
    filename: str | None = None,
) -> Path:
    """Stream-download a file to dest_dir.

    Detects filename from Content-Disposition header or URL path if not provided.
    Returns the path to the saved file.
    """
    async with client.stream("GET", url, follow_redirects=True) as resp:
        resp.raise_for_status()

        # Determine filename
        if not filename:
            # Try Content-Disposition
            cd = resp.headers.get("content-disposition", "")
            match = re.search(r'filename[*]?=["\']?([^"\';\r\n]+)', cd)
            if match:
                filename = unquote(match.group(1).strip())
            else:
                # Fall back to URL path
                path_part = urlparse(str(resp.url)).path
                filename = unquote(path_part.rsplit("/", 1)[-1]) or "download"

        filename = _sanitize_filename(filename)
        dest = _deduplicate_path(dest_dir / filename)

        dest_dir.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                f.write(chunk)

    logger.info("Downloaded %s -> %s", url, dest)
    return dest


# ---------------------------------------------------------------------------
# Processing pipeline
# ---------------------------------------------------------------------------

async def process_imported_file(
    file_path: Path,
    library_id: int,
    source_url: str | None = None,
    scraped_title: str | None = None,
    scraped_tags: list[str] | None = None,
    subfolder: str | None = None,
    library_path: str | None = None,
) -> int | None:
    """Run a downloaded file through the standard pipeline and insert into DB.

    Returns the new model ID, or None on failure.
    """
    file_path_str = str(file_path)
    loop = asyncio.get_running_loop()

    # Check extension is supported
    ext = file_path.suffix.lower()
    if ext == ".zip":
        # Zip files are left for the scanner to pick up on next scan
        logger.info("Zip file saved at %s - will be processed on next scan", file_path_str)
        return None

    from app.services.processor import FORMAT_MAP, TRIMESH_SUPPORTED, FALLBACK_ONLY
    all_known = TRIMESH_SUPPORTED | FALLBACK_ONLY
    if ext not in all_known:
        logger.warning("Unsupported format %s for imported file %s", ext, file_path_str)
        return None

    # Extract metadata (CPU-bound)
    metadata: dict = await loop.run_in_executor(
        None, processor.extract_metadata, file_path_str,
    )

    # Compute hash (I/O-bound)
    file_hash: str = await loop.run_in_executor(
        None, hasher.compute_file_hash, file_path_str,
    )

    # Derive fields
    name = scraped_title or file_path.stem
    file_format = metadata.get("file_format", ext.lstrip(".").upper())
    file_size = metadata.get("file_size") or os.path.getsize(file_path)

    async with get_db() as db:
        # Check for duplicate file_path
        cursor = await db.execute(
            "SELECT id FROM models WHERE file_path = ?", (file_path_str,)
        )
        if await cursor.fetchone() is not None:
            logger.info("File already indexed: %s", file_path_str)
            return None

        # Insert model row
        cursor = await db.execute(
            """
            INSERT INTO models (
                name, description, file_path, file_format, file_size,
                file_hash, vertex_count, face_count,
                dimensions_x, dimensions_y, dimensions_z,
                thumbnail_path, library_id, source_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                "",
                file_path_str,
                file_format,
                file_size,
                file_hash,
                metadata.get("vertex_count"),
                metadata.get("face_count"),
                metadata.get("dimensions_x"),
                metadata.get("dimensions_y"),
                metadata.get("dimensions_z"),
                None,
                library_id,
                source_url,
            ),
        )
        model_id = cursor.lastrowid

        # Generate thumbnail (CPU-bound)
        from app.config import settings as app_settings
        thumb_path = str(app_settings.MODEL_LIBRARY_THUMBNAIL_PATH)
        thumb_mode = await get_setting("thumbnail_mode", "wireframe")
        thumb_quality = await get_setting("thumbnail_quality", "fast")
        thumb_filename: str | None = await loop.run_in_executor(
            None,
            thumbnail.generate_thumbnail,
            file_path_str,
            thumb_path,
            model_id,
            thumb_mode,
            thumb_quality,
        )

        if thumb_filename is not None:
            await db.execute(
                "UPDATE models SET thumbnail_path = ?, thumbnail_mode = ?, thumbnail_quality = ?, thumbnail_generated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (thumb_filename, thumb_mode, thumb_quality, model_id),
            )

        # Auto-add scraped tags
        if scraped_tags:
            for tag_name in scraped_tags:
                tag_name = tag_name.strip()
                if not tag_name:
                    continue
                # Upsert tag
                await db.execute(
                    "INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,)
                )
                cursor = await db.execute(
                    "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (tag_name,)
                )
                tag_row = await cursor.fetchone()
                if tag_row:
                    tag_id = tag_row["id"]
                    await db.execute(
                        "INSERT OR IGNORE INTO model_tags (model_id, tag_id) VALUES (?, ?)",
                        (model_id, tag_id),
                    )

        # Auto-create categories from subfolder path
        if subfolder and library_path:
            full_dir = file_path.parent
            try:
                scan_root = Path(library_path)
                rel = full_dir.relative_to(scan_root)
                parts = rel.parts
                if parts:
                    parent_id: int | None = None
                    for part in parts:
                        cursor = await db.execute(
                            "SELECT id FROM categories WHERE name = ? AND (parent_id IS ? OR parent_id = ?)",
                            (part, parent_id, parent_id),
                        )
                        row = await cursor.fetchone()
                        if row is not None:
                            category_id = row["id"]
                        else:
                            cursor = await db.execute(
                                "INSERT INTO categories (name, parent_id) VALUES (?, ?)",
                                (part, parent_id),
                            )
                            category_id = cursor.lastrowid
                        await db.execute(
                            "INSERT OR IGNORE INTO model_categories (model_id, category_id) VALUES (?, ?)",
                            (model_id, category_id),
                        )
                        parent_id = category_id
            except ValueError:
                pass

        # Update FTS index
        await update_fts_for_model(db, model_id)
        await db.commit()

    logger.info("Imported model id=%d  %s", model_id, file_path_str)
    return model_id


# ---------------------------------------------------------------------------
# Single URL import
# ---------------------------------------------------------------------------

async def import_from_url(
    url: str,
    library_id: int,
    library_path: str,
    subfolder: str | None = None,
    credentials: dict | None = None,
) -> dict:
    """Import model(s) from a single URL.

    Returns dict with keys: url, status, models (list of model IDs), error.
    """
    result: dict = {"url": url, "status": "ok", "models": [], "error": None}

    try:
        # Scrape metadata
        meta = await scrape_metadata(url, credentials)
        title = meta.get("title")
        tags = meta.get("tags", [])
        download_urls = meta.get("download_urls", [])

        # If no download URLs found, try the URL itself as a direct download
        if not download_urls:
            download_urls = [url]

        # Determine destination directory
        dest_dir = Path(library_path)
        if subfolder:
            dest_dir = dest_dir / subfolder
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Download and process each file
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            for dl_url in download_urls:
                try:
                    file_path = await download_file(dl_url, client, dest_dir)

                    # Only process model files (skip HTML pages etc.)
                    if file_path.suffix.lower() not in MODEL_EXTENSIONS:
                        logger.info("Skipping non-model file: %s", file_path)
                        file_path.unlink(missing_ok=True)
                        continue

                    model_id = await process_imported_file(
                        file_path=file_path,
                        library_id=library_id,
                        source_url=url,
                        scraped_title=title if len(download_urls) == 1 else None,
                        scraped_tags=tags,
                        subfolder=subfolder,
                        library_path=library_path,
                    )
                    if model_id is not None:
                        result["models"].append(model_id)
                except Exception as e:
                    logger.warning("Failed to download/process %s: %s", dl_url, e)

        if not result["models"]:
            result["status"] = "no_models"
            result["error"] = "No model files were successfully imported"

    except Exception as e:
        logger.exception("Import failed for URL: %s", url)
        result["status"] = "error"
        result["error"] = str(e)

    return result


# ---------------------------------------------------------------------------
# Batch import with progress tracking
# ---------------------------------------------------------------------------

_import_progress: dict = {
    "running": False,
    "total": 0,
    "completed": 0,
    "current_url": None,
    "results": [],
}


def get_import_progress() -> dict:
    """Return current import progress state."""
    return dict(_import_progress)


async def import_urls_batch(
    urls: list[str],
    library_id: int,
    library_path: str,
    subfolder: str | None = None,
    credentials: dict | None = None,
) -> None:
    """Process multiple URLs sequentially with progress tracking.

    Runs as a background task. Updates _import_progress as it goes.
    """
    _import_progress["running"] = True
    _import_progress["total"] = len(urls)
    _import_progress["completed"] = 0
    _import_progress["current_url"] = None
    _import_progress["results"] = []

    try:
        for url in urls:
            url = url.strip()
            if not url:
                _import_progress["completed"] += 1
                continue

            _import_progress["current_url"] = url
            result = await import_from_url(
                url=url,
                library_id=library_id,
                library_path=library_path,
                subfolder=subfolder,
                credentials=credentials,
            )
            _import_progress["results"].append(result)
            _import_progress["completed"] += 1
    finally:
        _import_progress["running"] = False
        _import_progress["current_url"] = None

    logger.info(
        "Batch import complete: %d URLs processed",
        len(urls),
    )


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

CREDENTIAL_SETTINGS_KEY = "import_credentials"


async def get_credentials() -> dict:
    """Load stored import credentials from the settings table."""
    raw = await get_setting(CREDENTIAL_SETTINGS_KEY, "{}")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


async def set_credentials(site: str, creds: dict) -> None:
    """Store credentials for a specific site."""
    all_creds = await get_credentials()
    all_creds[site] = creds
    from app.database import set_setting
    await set_setting(CREDENTIAL_SETTINGS_KEY, json.dumps(all_creds))


async def delete_credentials(site: str) -> None:
    """Remove credentials for a specific site."""
    all_creds = await get_credentials()
    all_creds.pop(site, None)
    from app.database import set_setting
    await set_setting(CREDENTIAL_SETTINGS_KEY, json.dumps(all_creds))


def mask_credentials(creds: dict) -> dict:
    """Mask credential values for API responses (show last 4 chars)."""
    masked: dict = {}
    for site, site_creds in creds.items():
        masked[site] = {}
        for key, value in site_creds.items():
            if isinstance(value, str) and len(value) > 4:
                masked[site][key] = "****" + value[-4:]
            elif isinstance(value, str):
                masked[site][key] = "****"
            else:
                masked[site][key] = value
    return masked
