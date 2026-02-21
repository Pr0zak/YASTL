"""API routes for saved searches."""

import json

from fastapi import APIRouter, HTTPException, Request
import aiosqlite

router = APIRouter(prefix="/api/saved-searches", tags=["saved-searches"])


def _get_db_path(request: Request) -> str:
    return request.app.state.db_path


@router.get("")
async def list_saved_searches(request: Request):
    """List all saved searches."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT * FROM saved_searches ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        item = dict(row)
        # Parse filters JSON
        try:
            item["filters"] = json.loads(item.get("filters") or "{}")
        except (json.JSONDecodeError, TypeError):
            item["filters"] = {}
        results.append(item)

    return {"saved_searches": results}


@router.post("", status_code=201)
async def create_saved_search(request: Request):
    """Create a new saved search.

    Expects JSON body: {"name": "...", "query": "...", "filters": {...},
                        "sort_by": "...", "sort_order": "..."}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    name = body.get("name")
    query = body.get("query", "")
    filters = body.get("filters", {})
    sort_by = body.get("sort_by", "created_at")
    sort_order = body.get("sort_order", "desc")

    if not name or not isinstance(name, str) or not name.strip():
        raise HTTPException(
            status_code=400,
            detail="'name' is required and must be a non-empty string",
        )

    # Validate sort_order
    if sort_order not in ("asc", "desc"):
        raise HTTPException(
            status_code=400, detail="'sort_order' must be 'asc' or 'desc'"
        )

    filters_json = json.dumps(filters) if isinstance(filters, dict) else "{}"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "INSERT INTO saved_searches (name, query, filters, sort_by, sort_order) "
            "VALUES (?, ?, ?, ?, ?)",
            (name.strip(), query, filters_json, sort_by, sort_order),
        )
        search_id = cursor.lastrowid
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM saved_searches WHERE id = ?", (search_id,)
        )
        row = await cursor.fetchone()

    result = dict(row)
    try:
        result["filters"] = json.loads(result.get("filters") or "{}")
    except (json.JSONDecodeError, TypeError):
        result["filters"] = {}
    return result


@router.put("/{search_id}")
async def update_saved_search(request: Request, search_id: int):
    """Update a saved search.

    Expects JSON body with optional: {"name", "query", "filters", "sort_by", "sort_order"}
    """
    db_path = _get_db_path(request)
    body = await request.json()

    name = body.get("name")
    query = body.get("query")
    filters = body.get("filters")
    sort_by = body.get("sort_by")
    sort_order = body.get("sort_order")

    if all(v is None for v in (name, query, filters, sort_by, sort_order)):
        raise HTTPException(
            status_code=400, detail="At least one field must be provided"
        )

    if sort_order is not None and sort_order not in ("asc", "desc"):
        raise HTTPException(
            status_code=400, detail="'sort_order' must be 'asc' or 'desc'"
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT id FROM saved_searches WHERE id = ?", (search_id,)
        )
        if await cursor.fetchone() is None:
            raise HTTPException(
                status_code=404, detail=f"Saved search {search_id} not found"
            )

        set_clauses: list[str] = []
        params: list = []

        if name is not None:
            set_clauses.append("name = ?")
            params.append(name.strip())
        if query is not None:
            set_clauses.append("query = ?")
            params.append(query)
        if filters is not None:
            set_clauses.append("filters = ?")
            params.append(
                json.dumps(filters) if isinstance(filters, dict) else "{}"
            )
        if sort_by is not None:
            set_clauses.append("sort_by = ?")
            params.append(sort_by)
        if sort_order is not None:
            set_clauses.append("sort_order = ?")
            params.append(sort_order)

        params.append(search_id)
        await db.execute(
            f"UPDATE saved_searches SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM saved_searches WHERE id = ?", (search_id,)
        )
        row = await cursor.fetchone()

    result = dict(row)
    try:
        result["filters"] = json.loads(result.get("filters") or "{}")
    except (json.JSONDecodeError, TypeError):
        result["filters"] = {}
    return result


@router.delete("/{search_id}")
async def delete_saved_search(request: Request, search_id: int):
    """Delete a saved search."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT id, name FROM saved_searches WHERE id = ?", (search_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Saved search {search_id} not found"
            )

        name = dict(row)["name"]
        await db.execute("DELETE FROM saved_searches WHERE id = ?", (search_id,))
        await db.commit()

    return {"detail": f"Saved search '{name}' (id={search_id}) deleted"}
