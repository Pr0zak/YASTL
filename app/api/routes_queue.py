"""API routes for the print queue (print pipeline).

On a transition to ``done`` the queued item is logged to ``print_log`` and the
model's ``print_count`` / ``last_printed_at`` summary is bumped, so the queue
feeds the finished-prints inventory.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
import aiosqlite

from app.api._helpers import open_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/queue", tags=["queue"])

_STATUSES = {"queued", "printing", "done", "failed"}


def _get_db_path(request: Request) -> str:
    return request.app.state.db_path


@router.get("")
async def list_queue(request: Request):
    """List queue items (with model name/thumbnail/format), ordered by position."""
    db_path = _get_db_path(request)
    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT q.*, m.name AS model_name, m.file_format AS model_format,
                      m.thumbnail_path AS model_thumbnail
               FROM print_queue q
               JOIN models m ON m.id = q.model_id
               ORDER BY q.position, q.id"""
        )
        items = [dict(r) for r in await cursor.fetchall()]
    return {"queue": items}


@router.post("", status_code=201)
async def add_to_queue(request: Request):
    """Add a model to the end of the queue. Body: {"model_id": N}."""
    db_path = _get_db_path(request)
    body = await request.json()
    model_id = body.get("model_id")
    if not model_id:
        raise HTTPException(status_code=400, detail="'model_id' is required")
    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id FROM models WHERE id = ?", (model_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
        cursor = await db.execute("SELECT COALESCE(MAX(position), 0) + 1 AS p FROM print_queue")
        position = dict(await cursor.fetchone())["p"]
        cursor = await db.execute(
            "INSERT INTO print_queue (model_id, status, position) VALUES (?, 'queued', ?)",
            (model_id, position),
        )
        qid = cursor.lastrowid
        await db.commit()
        cursor = await db.execute("SELECT * FROM print_queue WHERE id = ?", (qid,))
        row = dict(await cursor.fetchone())
    return row


@router.put("/reorder")
async def reorder_queue(request: Request):
    """Set queue order. Body: {"ids": [id, id, ...]} in the desired order."""
    db_path = _get_db_path(request)
    body = await request.json()
    ids = body.get("ids", [])
    if not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="'ids' must be a list")
    async with open_db(db_path) as db:
        for pos, qid in enumerate(ids):
            await db.execute(
                "UPDATE print_queue SET position = ? WHERE id = ?", (pos, qid)
            )
        await db.commit()
    return {"reordered": len(ids)}


@router.put("/{queue_id}")
async def update_queue_item(request: Request, queue_id: int):
    """Update a queue item's status/printer/notes.

    Transition side effects: ``printing`` sets started_at; ``done`` sets
    finished_at, inserts a print_log row and bumps the model's print_count;
    ``failed`` sets finished_at.
    """
    db_path = _get_db_path(request)
    body = await request.json()
    status = body.get("status")
    if status is not None and status not in _STATUSES:
        raise HTTPException(
            status_code=400, detail=f"status must be one of {sorted(_STATUSES)}"
        )

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM print_queue WHERE id = ?", (queue_id,))
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Queue item {queue_id} not found")
        item = dict(row)

        sets = []
        params: list = []
        if "printer" in body:
            sets.append("printer = ?")
            params.append(str(body.get("printer") or ""))
        if "notes" in body:
            sets.append("notes = ?")
            params.append(str(body.get("notes") or ""))

        if status is not None and status != item["status"]:
            sets.append("status = ?")
            params.append(status)
            if status == "printing" and item["started_at"] is None:
                sets.append("started_at = CURRENT_TIMESTAMP")
            if status in ("done", "failed"):
                sets.append("finished_at = CURRENT_TIMESTAMP")
            # Transition to done -> record a finished print.
            if status == "done":
                await db.execute(
                    "INSERT INTO print_log (model_id, quantity) VALUES (?, 1)",
                    (item["model_id"],),
                )
                await db.execute(
                    "UPDATE models SET print_count = COALESCE(print_count, 0) + 1, "
                    "last_printed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (item["model_id"],),
                )

        if sets:
            params.append(queue_id)
            await db.execute(
                f"UPDATE print_queue SET {', '.join(sets)} WHERE id = ?", params
            )
        await db.commit()
        cursor = await db.execute("SELECT * FROM print_queue WHERE id = ?", (queue_id,))
        updated = dict(await cursor.fetchone())
    return updated


@router.delete("/{queue_id}")
async def delete_queue_item(request: Request, queue_id: int):
    """Remove an item from the queue (does not touch print history)."""
    db_path = _get_db_path(request)
    async with open_db(db_path) as db:
        cursor = await db.execute("DELETE FROM print_queue WHERE id = ?", (queue_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Queue item {queue_id} not found")
        await db.commit()
    return {"deleted": queue_id}
