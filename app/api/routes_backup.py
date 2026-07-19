"""Backup / export routes: portable metadata manifest + DB snapshot."""

import json
import logging
import os
import tempfile

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, Response

from app.api._helpers import open_db, _get_db_path

logger = logging.getLogger("yastl")

router = APIRouter(prefix="/api/backup", tags=["backup"])


@router.get("/manifest")
async def export_manifest(request: Request):
    """Stream a portable JSON manifest of the library's curated metadata.

    Keyed by file hash so it can be re-applied after a rescan or on a new
    instance: tags, categories, collections, favorites, print stats,
    descriptions, and source URLs — the expensive-to-recreate curation.
    """
    db_path = _get_db_path(request)
    async with open_db(db_path) as db:
        cursor = await db.execute(
            "SELECT id, name, file_path, file_hash, file_format, file_size, "
            "description, source_url, print_count, last_printed_at, zip_path, "
            "zip_entry FROM models WHERE status = 'active'"
        )
        models = {r["id"]: dict(r) for r in await cursor.fetchall()}

        tags: dict[int, list[str]] = {}
        cursor = await db.execute(
            "SELECT mt.model_id AS mid, t.name FROM model_tags mt "
            "JOIN tags t ON t.id = mt.tag_id"
        )
        for r in await cursor.fetchall():
            tags.setdefault(r["mid"], []).append(r["name"])

        cats: dict[int, list[str]] = {}
        cursor = await db.execute(
            "SELECT mc.model_id AS mid, c.name FROM model_categories mc "
            "JOIN categories c ON c.id = mc.category_id"
        )
        for r in await cursor.fetchall():
            cats.setdefault(r["mid"], []).append(r["name"])

        colls: dict[int, list[str]] = {}
        cursor = await db.execute(
            "SELECT cm.model_id AS mid, c.name FROM collection_models cm "
            "JOIN collections c ON c.id = cm.collection_id"
        )
        for r in await cursor.fetchall():
            colls.setdefault(r["mid"], []).append(r["name"])

        cursor = await db.execute("SELECT model_id FROM favorites")
        favs = {r["model_id"] for r in await cursor.fetchall()}

    entries = []
    for mid, m in models.items():
        entries.append({
            "hash": m["file_hash"],
            "name": m["name"],
            "file_path": m["file_path"],
            "zip_path": m["zip_path"],
            "zip_entry": m["zip_entry"],
            "file_format": m["file_format"],
            "file_size": m["file_size"],
            "description": m["description"] or "",
            "source_url": m["source_url"] or "",
            "print_count": m["print_count"] or 0,
            "last_printed_at": m["last_printed_at"],
            "favorite": mid in favs,
            "tags": tags.get(mid, []),
            "categories": cats.get(mid, []),
            "collections": colls.get(mid, []),
        })

    manifest = {"version": 1, "model_count": len(entries), "models": entries}
    body = json.dumps(manifest, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=yastl-manifest.json"},
    )


@router.get("/database")
async def export_database(request: Request, background_tasks: BackgroundTasks):
    """Stream a consistent snapshot of the SQLite database.

    Uses ``VACUUM INTO`` for a clean copy (no partial WAL state), served as
    an attachment and deleted after the response is sent.
    """
    db_path = _get_db_path(request)
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Database not found")

    fd, snapshot = tempfile.mkstemp(suffix=".db", prefix="yastl-backup-")
    os.close(fd)
    os.remove(snapshot)  # VACUUM INTO requires the target not to exist
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("VACUUM INTO ?", (snapshot,))
    except Exception as e:  # noqa: BLE001
        logger.warning("DB snapshot failed: %s", e)
        raise HTTPException(status_code=500, detail="Could not create DB snapshot")

    background_tasks.add_task(lambda p=snapshot: os.path.exists(p) and os.remove(p))
    return FileResponse(
        path=snapshot,
        media_type="application/x-sqlite3",
        filename="yastl-library.db",
    )
