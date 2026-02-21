"""URL-based model import service.

Downloads 3D model files from URLs, scrapes metadata from known hosting sites
(Thingiverse, MakerWorld, Printables, MyMiniFactory, Cults3D, Thangs), and
feeds them through the standard processing pipeline (metadata extraction,
hashing, thumbnail generation, DB insert, FTS update).
"""

import asyncio
import logging
import os
import re
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from app.database import get_db, get_setting, update_fts_for_model
from app.services import hasher, processor, thumbnail

# Re-export submodule names so existing ``from app.services.importer import ...``
# statements continue to work without changes.
from app.services.scrapers import (  # noqa: F401
    MODEL_EXTENSIONS,
    SITE_HOSTS,
    _DEFAULT_HEADERS,
    detect_site,
    scrape_metadata,
)
from app.services.downloader import (  # noqa: F401
    download_file,
    _sanitize_filename,
    _deduplicate_path,
    _is_presigned_s3,
)
from app.services.import_credentials import (  # noqa: F401
    CREDENTIAL_SETTINGS_KEY,
    get_credentials,
    set_credentials,
    delete_credentials,
    mask_credentials,
)

logger = logging.getLogger(__name__)


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

    from app.services.processor import TRIMESH_SUPPORTED, FALLBACK_ONLY
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
# Zip upload processing
# ---------------------------------------------------------------------------

# 3D model extensions to extract from zips (no .zip -- no nested zips)
_ZIP_MODEL_EXTENSIONS: set[str] = {
    ".stl", ".obj", ".gltf", ".glb", ".3mf",
    ".ply", ".dae", ".off", ".step", ".stp", ".fbx",
}


def extract_zip_metadata(zip_path: Path) -> dict:
    """Extract metadata from a zip file based on its name and contents.

    Detects Thingiverse zips (filenames like ``Model_Name_12345_files.zip``
    or containing ``Attribution`` / ``license`` text files) and builds a
    source URL.  Parses the zip name and any attribution/readme files
    for tags, title, and source URL.

    Returns dict with keys: title, source_url, tags, model_files, site.
    """
    meta: dict = {
        "title": None,
        "source_url": None,
        "tags": [],
        "model_files": [],
        "site": None,
    }

    stem = zip_path.stem

    # Detect Thingiverse zip patterns
    # Patterns: "ModelName_12345_files", "ModelName_12345",
    #           "Model Name - 12345", "Model Name - 12345 - files"
    tv_match = re.search(r"[\s_-]+(\d{4,})(?:[\s_-]+files)?$", stem)
    if tv_match:
        thing_id = tv_match.group(1)
        meta["source_url"] = f"https://www.thingiverse.com/thing:{thing_id}"
        meta["site"] = "thingiverse"
        # Title: everything before the ID, cleaned up
        title_part = stem[:tv_match.start()]
        title_part = re.sub(r"[\s_\-]+$", "", title_part).strip()
        if title_part:
            meta["title"] = title_part

    try:
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                # Skip macOS resource forks and hidden files
                if name.startswith("__MACOSX/") or PurePosixPath(name).name.startswith("."):
                    continue

                ext = PurePosixPath(name).suffix.lower()
                if ext in _ZIP_MODEL_EXTENSIONS:
                    meta["model_files"].append(name)

                # Look for attribution / readme / license files
                basename_lower = PurePosixPath(name).name.lower()
                if basename_lower in ("attribution.txt", "attribution_card.html", "readme.txt", "license.txt"):
                    try:
                        text = zf.read(name).decode("utf-8", errors="replace")
                        _parse_attribution(text, meta)
                    except Exception:
                        pass
    except zipfile.BadZipFile:
        logger.warning("Corrupt zip: %s", zip_path)
    except Exception:
        logger.exception("Error reading zip: %s", zip_path)

    # Fall back title from zip name
    if not meta["title"]:
        cleaned = re.sub(r"[_\-]+", " ", stem).strip()
        if cleaned:
            meta["title"] = cleaned

    # Generate tags from zip name if none found
    if not meta["tags"]:
        from app.services.tagger import _split_filename
        meta["tags"] = _split_filename(stem)

    return meta


def _parse_attribution(text: str, meta: dict) -> None:
    """Parse Thingiverse attribution / readme text for metadata.

    Typical Thingiverse ``Attribution_card.html`` or ``attribution.txt``
    contains lines like:
        Title: Model Name
        URL: https://www.thingiverse.com/thing:12345
        Creator: username
        Tags: tag1, tag2, tag3
    """
    for line in text.split("\n"):
        line = line.strip()
        # Strip HTML tags
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if not clean:
            continue

        # Look for key: value patterns
        kv = re.match(r"^(Title|URL|Creator|Tags|Description)\s*:\s*(.+)", clean, re.IGNORECASE)
        if not kv:
            # Thingiverse README format: "Title by Creator on Thingiverse: URL"
            tv_readme = re.match(
                r"^(.+?)\s+by\s+(\S+)\s+on\s+Thingiverse:\s*(https?://\S+)",
                clean, re.IGNORECASE,
            )
            if tv_readme:
                if not meta["title"]:
                    meta["title"] = tv_readme.group(1).strip()
                if not meta.get("creator"):
                    meta["creator"] = tv_readme.group(2).strip()
                if not meta["source_url"]:
                    meta["source_url"] = tv_readme.group(3).strip()
                    meta["site"] = "thingiverse"
                continue

            # Also try "thing:12345" URLs embedded anywhere
            url_match = re.search(r"(https?://(?:www\.)?thingiverse\.com/thing[:/]\d+)", clean)
            if url_match and not meta["source_url"]:
                meta["source_url"] = url_match.group(1)
                meta["site"] = "thingiverse"
            # Check for printables URLs
            url_match = re.search(r"(https?://(?:www\.)?printables\.com/model/\d+)", clean)
            if url_match and not meta["source_url"]:
                meta["source_url"] = url_match.group(1)
                meta["site"] = "printables"
            # Check for MakerWorld URLs
            url_match = re.search(r"(https?://(?:www\.)?makerworld\.com/\S*models/\d+)", clean)
            if url_match and not meta["source_url"]:
                meta["source_url"] = url_match.group(1)
                meta["site"] = "makerworld"
            continue

        key = kv.group(1).lower()
        val = kv.group(2).strip()
        if key == "title" and not meta["title"]:
            meta["title"] = val
        elif key == "url" and not meta["source_url"]:
            meta["source_url"] = val
            if "thingiverse" in val:
                meta["site"] = "thingiverse"
            elif "printables" in val:
                meta["site"] = "printables"
            elif "makerworld" in val:
                meta["site"] = "makerworld"
        elif key == "tags":
            parsed = [t.strip() for t in val.split(",") if t.strip()]
            meta["tags"].extend(parsed)
        elif key == "creator":
            meta["tags"].append(val)


async def process_uploaded_zip(
    zip_path: Path,
    library_id: int,
    library_path: str,
    subfolder: str | None = None,
    extra_tags: list[str] | None = None,
) -> list[dict]:
    """Extract model files from an uploaded zip and process each one.

    Parses zip metadata (title, source URL, tags) from filename and
    attribution files.  Returns a list of per-file result dicts.
    """
    meta = extract_zip_metadata(zip_path)
    all_tags = list(meta["tags"])
    if extra_tags:
        for t in extra_tags:
            if t not in all_tags:
                all_tags.append(t)
    if meta["site"]:
        if meta["site"] not in all_tags:
            all_tags.append(meta["site"])

    results: list[dict] = []
    if not meta["model_files"]:
        results.append({
            "filename": zip_path.name,
            "status": "error",
            "error": "No 3D model files found in zip",
        })
        return results

    dest_dir = Path(library_path)
    if subfolder:
        dest_dir = dest_dir / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            for entry_name in meta["model_files"]:
                entry_basename = PurePosixPath(entry_name).name
                fname = _sanitize_filename(entry_basename)
                dest = _deduplicate_path(dest_dir / fname)
                try:
                    data = zf.read(entry_name)
                    with open(dest, "wb") as f:
                        f.write(data)

                    # Use zip title as model name for all extracted files
                    title = meta["title"]

                    model_id = await process_imported_file(
                        file_path=dest,
                        library_id=library_id,
                        source_url=meta["source_url"],
                        scraped_title=title,
                        scraped_tags=all_tags or None,
                        subfolder=subfolder,
                        library_path=library_path,
                    )
                    if model_id is not None:
                        results.append({
                            "filename": fname,
                            "status": "ok",
                            "model_id": model_id,
                        })
                    else:
                        results.append({
                            "filename": fname,
                            "status": "error",
                            "error": "Processing failed or duplicate",
                        })
                except Exception as e:
                    logger.warning("Failed to process %s from zip: %s", entry_name, e)
                    results.append({
                        "filename": fname,
                        "status": "error",
                        "error": str(e),
                    })
    except zipfile.BadZipFile:
        results.append({
            "filename": zip_path.name,
            "status": "error",
            "error": "Corrupt or invalid zip file",
        })
    except Exception as e:
        logger.exception("Error processing zip: %s", zip_path)
        results.append({
            "filename": zip_path.name,
            "status": "error",
            "error": str(e),
        })

    # Clean up the uploaded zip after extracting
    try:
        zip_path.unlink(missing_ok=True)
    except OSError:
        pass

    logger.info(
        "Processed zip %s: %d model(s), meta=%s",
        zip_path.name, len([r for r in results if r["status"] == "ok"]),
        {k: v for k, v in meta.items() if k != "model_files"},
    )
    return results


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
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True, headers=_DEFAULT_HEADERS) as client:
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
