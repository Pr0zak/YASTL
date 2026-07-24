"""API routes for filament spool inventory (print pipeline)."""

import logging

from fastapi import APIRouter, HTTPException, Request
import aiosqlite

from app.api._helpers import open_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/filaments", tags=["filaments"])

# Fields a client may set on create/update (id/created_at are managed here).
_FIELDS = (
    "brand", "material", "color_name", "color_hex", "diameter",
    "spool_weight_g", "remaining_g", "cost", "vendor", "purchased_at",
    "notes", "status",
)
_ALLOWED_STATUS = {"active", "empty", "archived"}


def _get_db_path(request: Request) -> str:
    """Retrieve the database path from FastAPI app state."""
    return request.app.state.db_path


def _clean(body: dict) -> dict:
    """Pick only known fields from the request body, validating status."""
    data = {k: body[k] for k in _FIELDS if k in body}
    if "status" in data and data["status"] not in _ALLOWED_STATUS:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(_ALLOWED_STATUS)}",
        )
    return data


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------
@router.get("")
async def list_filaments(request: Request):
    """List all filament spools (active first, then by brand/material)."""
    db_path = _get_db_path(request)
    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM filaments
               ORDER BY (status != 'active'), brand, material, color_name"""
        )
        rows = [dict(r) for r in await cursor.fetchall()]
    return {"filaments": rows}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
@router.post("", status_code=201)
async def create_filament(request: Request):
    """Create a filament spool. All fields optional; sensible defaults apply."""
    db_path = _get_db_path(request)
    body = await request.json()
    data = _clean(body)

    cols = list(data.keys())
    placeholders = ", ".join("?" for _ in cols)
    col_sql = ", ".join(cols)

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        if cols:
            cursor = await db.execute(
                f"INSERT INTO filaments ({col_sql}) VALUES ({placeholders})",
                [data[c] for c in cols],
            )
        else:
            cursor = await db.execute("INSERT INTO filaments DEFAULT VALUES")
        fid = cursor.lastrowid
        await db.commit()
        cursor = await db.execute("SELECT * FROM filaments WHERE id = ?", (fid,))
        row = dict(await cursor.fetchone())
    return row


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
@router.put("/{filament_id}")
async def update_filament(request: Request, filament_id: int):
    """Update fields on a filament spool (partial update)."""
    db_path = _get_db_path(request)
    body = await request.json()
    data = _clean(body)
    if not data:
        raise HTTPException(status_code=400, detail="No updatable fields provided")

    set_sql = ", ".join(f"{c} = ?" for c in data)
    params = [data[c] for c in data]
    params.append(filament_id)

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"UPDATE filaments SET {set_sql}, updated_at = CURRENT_TIMESTAMP "
            f"WHERE id = ?",
            params,
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404, detail=f"Filament {filament_id} not found"
            )
        await db.commit()
        cursor = await db.execute(
            "SELECT * FROM filaments WHERE id = ?", (filament_id,)
        )
        row = dict(await cursor.fetchone())
    return row


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
@router.delete("/{filament_id}")
async def delete_filament(request: Request, filament_id: int):
    """Delete a filament spool. print_log.filament_id is set NULL (SET NULL)."""
    db_path = _get_db_path(request)
    async with open_db(db_path) as db:
        cursor = await db.execute(
            "DELETE FROM filaments WHERE id = ?", (filament_id,)
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404, detail=f"Filament {filament_id} not found"
            )
        await db.commit()
    return {"deleted": filament_id}
