"""API routes for the YASTL Connect browser extension.

Connect is a Manifest V3 browser extension that captures 3D model downloads
from hosting sites and pushes them here with the source page's metadata already
attached.  The browser does the fetching, which is the entire point: it is
already authenticated to the site, already past whatever bot check the site
runs, and holds presigned CDN URLs while they are still valid.  See
``docs/plan-connect-extension.md``.

These routes are deliberately separate from ``routes_import``.  The payload is
richer, the contract needs to version independently of the SPA, and — most
importantly — the token check below must not leak onto the routes the web UI
depends on.

Security posture, stated plainly because it matters: this is a shared-secret
bearer token sent over whatever transport the user has configured, which on a
typical LAN deployment is plain HTTP.  It stops an arbitrary web page from
silently writing into the library.  It does not protect against someone who is
already on the network and reading traffic.  Connect is disabled by default and
has to be turned on explicitly in Settings.
"""

import logging
import secrets
from pathlib import Path

import aiosqlite
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)

from app.api._helpers import _get_db_path, open_db
from app.database import get_db, get_setting, set_setting
from app.services.importer import (
    MODEL_EXTENSIONS,
    process_imported_file,
    process_uploaded_zip,
    safe_subfolder,
    _deduplicate_path,
    _sanitize_filename,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connect", tags=["connect"])

# Bumped when the extension<->server contract changes in a way that an older
# extension build would get wrong.  The extension compares this against its own
# expectation and tells the user to update rather than failing obscurely.
CONNECT_PROTOCOL_VERSION = 1


# ---------------------------------------------------------------------------
# Token auth
# ---------------------------------------------------------------------------


async def _connect_config() -> tuple[bool, str]:
    """Return ``(enabled, token)`` for Connect."""
    enabled = (await get_setting("connect_enabled", "false")) == "true"
    token = await get_setting("connect_token", "") or ""
    return enabled, token


async def require_connect_token(
    x_yastl_token: str | None = Header(default=None),
) -> None:
    """Reject the request unless Connect is enabled and the token matches.

    Compared with :func:`secrets.compare_digest` so a wrong token cannot be
    recovered a character at a time by timing the response.
    """
    enabled, token = await _connect_config()
    if not enabled:
        raise HTTPException(
            status_code=403,
            detail="Connect is disabled. Enable it in Settings -> Connect.",
        )
    if not token:
        raise HTTPException(
            status_code=403,
            detail="Connect has no access token set. Generate one in Settings -> Connect.",
        )
    if not x_yastl_token or not secrets.compare_digest(x_yastl_token, token):
        raise HTTPException(status_code=401, detail="Invalid Connect token.")


# ---------------------------------------------------------------------------
# Handshake
# ---------------------------------------------------------------------------


@router.get("/info")
async def connect_info():
    """Unauthenticated handshake for the extension's "Test connection" button.

    Deliberately reachable without a token so the extension can tell *server is
    up but Connect is switched off* apart from *server is unreachable* — two
    problems with completely different fixes.  It reveals only that this is a
    YASTL instance and whether Connect is on; no library contents, no token.
    """
    enabled, token = await _connect_config()
    return {
        "app": "yastl",
        "protocol": CONNECT_PROTOCOL_VERSION,
        "connect_enabled": enabled,
        "token_configured": bool(token),
    }


# ---------------------------------------------------------------------------
# Destination targets
# ---------------------------------------------------------------------------


@router.get("/targets", dependencies=[Depends(require_connect_token)])
async def connect_targets(request: Request):
    """Return the libraries and collections the extension can import into."""
    db_path = _get_db_path(request)
    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT l.id, l.name, l.path, COUNT(m.id) AS model_count
            FROM libraries l
            LEFT JOIN models m ON m.library_id = l.id AND m.status = 'active'
            GROUP BY l.id
            ORDER BY l.name
            """
        )
        libraries = [dict(r) for r in await cursor.fetchall()]

        cursor = await db.execute(
            "SELECT id, name, color FROM collections ORDER BY pinned DESC, name"
        )
        collections = [dict(r) for r in await cursor.fetchall()]

    return {
        "libraries": libraries,
        "collections": collections,
        "extensions": sorted(MODEL_EXTENSIONS),
    }


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def _split_tags(raw: str | None) -> list[str]:
    """Parse the comma-separated tag field, dropping blanks and duplicates."""
    seen: list[str] = []
    for part in (raw or "").split(","):
        tag = part.strip()
        if tag and tag not in seen:
            seen.append(tag)
    return seen


@router.post("/capture", dependencies=[Depends(require_connect_token)])
async def connect_capture(
    file: UploadFile = File(...),
    library_id: int = Form(...),
    subfolder: str | None = Form(None),
    source_url: str | None = Form(None),
    name: str | None = Form(None),
    description: str | None = Form(None),
    tags: str | None = Form(None),
    author: str | None = Form(None),
    license: str | None = Form(None),
    collection_id: int | None = Form(None),
):
    """Accept one captured model file plus its source-page metadata.

    The file has already been fetched by the browser, so this is a plain
    multipart upload; from here it follows exactly the same path as a manual
    upload.  Zips are expanded, everything else goes through
    :func:`process_imported_file`.
    """
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
        try:
            dest_dir = safe_subfolder(dest_dir, subfolder)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="subfolder must stay inside the library directory",
            )
    dest_dir.mkdir(parents=True, exist_ok=True)

    if source_url:
        source_url = source_url.strip() or None
        if source_url and not source_url.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=400,
                detail="source_url must start with http:// or https://",
            )

    tag_list = _split_tags(tags)
    # The originating site is worth knowing at a glance and is free to derive.
    if author:
        author = author.strip() or None
    if license:
        license = license.strip() or None
    if name:
        name = name.strip() or None
    if description:
        description = description.strip() or None

    fname = _sanitize_filename(file.filename or "capture")
    ext = Path(fname).suffix.lower()
    if ext not in MODEL_EXTENSIONS:
        raise HTTPException(
            status_code=400, detail=f"Unsupported format: {ext or '(none)'}"
        )

    dest = _deduplicate_path(dest_dir / fname)
    try:
        content = await file.read()
        dest.write_bytes(content)
    except Exception as e:
        logger.warning("Connect capture write failed for %s: %s", fname, e)
        raise HTTPException(status_code=500, detail=f"Could not save file: {e}")

    model_ids: list[int] = []
    results: list[dict] = []

    try:
        if ext == ".zip":
            for zr in await process_uploaded_zip(
                zip_path=dest,
                library_id=library_id,
                library_path=library_path,
                subfolder=subfolder,
                extra_tags=tag_list or None,
            ):
                results.append(zr)
                if zr.get("model_id"):
                    model_ids.append(zr["model_id"])
        else:
            model_id = await process_imported_file(
                file_path=dest,
                library_id=library_id,
                source_url=source_url,
                scraped_title=name,
                scraped_tags=tag_list or None,
                subfolder=subfolder,
                library_path=library_path,
            )
            if model_id is None:
                results.append(
                    {
                        "filename": fname,
                        "status": "error",
                        "error": "Processing failed or duplicate",
                    }
                )
            else:
                model_ids.append(model_id)
                results.append(
                    {"filename": fname, "status": "ok", "model_id": model_id}
                )
    except Exception as e:
        logger.warning("Connect capture processing failed for %s: %s", fname, e)
        raise HTTPException(status_code=500, detail=str(e))

    await _apply_capture_metadata(
        model_ids,
        name=name,
        source_url=source_url,
        description=description,
        author=author,
        license=license,
        collection_id=collection_id,
    )

    ok = sum(1 for r in results if r["status"] == "ok")
    return {
        "detail": f"{ok}/{len(results)} model(s) captured",
        "results": results,
        "model_ids": model_ids,
    }


async def _apply_capture_metadata(
    model_ids: list[int],
    *,
    name: str | None,
    source_url: str | None,
    description: str | None,
    author: str | None,
    license: str | None,
    collection_id: int | None,
) -> None:
    """Write the page metadata onto the freshly created models.

    Failures here are logged and swallowed: the file is already in the library
    and indexed, so losing the description is a far smaller problem than
    failing the whole capture and leaving the user unsure what landed.
    """
    if not model_ids:
        return

    # Author has no column of its own; it rides along as a namespaced tag, which
    # the frontend already tints and filters on (see frontend/src/tags.js).
    author_tag = f"author:{author}" if author else None

    try:
        async with get_db() as db:
            set_parts: list[str] = []
            params: list[str | int] = []
            if name:
                set_parts.append("name = ?")
                params.append(name)
            if source_url:
                set_parts.append("source_url = ?")
                params.append(source_url)
            if description:
                set_parts.append("description = ?")
                params.append(description)
            if license:
                set_parts.append("license = ?")
                params.append(license)

            if set_parts:
                set_parts.append("updated_at = CURRENT_TIMESTAMP")
                set_sql = ", ".join(set_parts)
                for mid in model_ids:
                    await db.execute(
                        f"UPDATE models SET {set_sql} WHERE id = ?", params + [mid]
                    )

            if author_tag:
                await db.execute(
                    "INSERT OR IGNORE INTO tags (name) VALUES (?)", (author_tag,)
                )
                cursor = await db.execute(
                    "SELECT id FROM tags WHERE name = ?", (author_tag,)
                )
                row = await cursor.fetchone()
                if row is not None:
                    tag_id = row["id"]
                    for mid in model_ids:
                        await db.execute(
                            "INSERT OR IGNORE INTO model_tags "
                            "(model_id, tag_id, source) VALUES (?, ?, 'auto')",
                            (mid, tag_id),
                        )

            if collection_id:
                cursor = await db.execute(
                    "SELECT COALESCE(MAX(position), 0) + 1 AS next_pos "
                    "FROM collection_models WHERE collection_id = ?",
                    (collection_id,),
                )
                row = await cursor.fetchone()
                next_pos = row["next_pos"]
                for mid in model_ids:
                    await db.execute(
                        "INSERT OR IGNORE INTO collection_models "
                        "(collection_id, model_id, position) VALUES (?, ?, ?)",
                        (collection_id, mid, next_pos),
                    )
                    next_pos += 1
                await db.execute(
                    "UPDATE collections SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (collection_id,),
                )

            await db.commit()
    except Exception as e:
        logger.warning("Connect capture metadata update failed: %s", e)


# ---------------------------------------------------------------------------
# Token management (called by the Settings UI, not the extension)
# ---------------------------------------------------------------------------


@router.post("/token")
async def rotate_connect_token():
    """Generate a fresh Connect token and return it in full, once.

    This is the only response that ever contains the whole token — reads through
    ``GET /api/settings`` come back masked.  Rotating invalidates any extension
    still holding the previous value, which is the intended way to revoke one.
    """
    token = secrets.token_urlsafe(32)
    await set_setting("connect_token", token)
    return {"token": token}
