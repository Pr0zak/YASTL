"""API routes for the finished-prints log (print pipeline).

Per-model logging lives on ``/api/models/{id}/print`` (see routes_models);
these endpoints query and manage the log collection.
"""

import logging

from fastapi import APIRouter, HTTPException, Query, Request
import aiosqlite

from app.api._helpers import open_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prints", tags=["prints"])


def _get_db_path(request: Request) -> str:
    return request.app.state.db_path


# ---------------------------------------------------------------------------
# List print-log entries (optionally filtered by model or location)
# ---------------------------------------------------------------------------
@router.get("")
async def list_prints(
    request: Request,
    model_id: int | None = Query(default=None),
    location: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    """List print-log entries, newest first, with filament + model info joined."""
    db_path = _get_db_path(request)
    where: list[str] = []
    params: list = []
    if model_id is not None:
        where.append("pl.model_id = ?")
        params.append(model_id)
    if location is not None:
        where.append("pl.location = ?")
        params.append(location)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"""SELECT pl.*,
                       f.brand AS filament_brand, f.material AS filament_material,
                       f.color_name AS filament_color_name, f.color_hex AS filament_color_hex,
                       m.name AS model_name
                FROM print_log pl
                LEFT JOIN filaments f ON f.id = pl.filament_id
                LEFT JOIN models m ON m.id = pl.model_id
                {where_sql}
                ORDER BY pl.printed_at DESC, pl.id DESC
                LIMIT ?""",
            [*params, limit],
        )
        rows = [dict(r) for r in await cursor.fetchall()]
    return {"prints": rows}


# ---------------------------------------------------------------------------
# Physical inventory grouped by location
# ---------------------------------------------------------------------------
@router.get("/inventory")
async def print_inventory(request: Request):
    """Aggregate the print log by physical storage location."""
    db_path = _get_db_path(request)
    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT COALESCE(NULLIF(pl.location, ''), '(unspecified)') AS location,
                      COUNT(*) AS entries,
                      SUM(pl.quantity) AS total_quantity,
                      COUNT(DISTINCT pl.model_id) AS distinct_models,
                      GROUP_CONCAT(DISTINCT m.name) AS model_names
               FROM print_log pl
               LEFT JOIN models m ON m.id = pl.model_id
               GROUP BY COALESCE(NULLIF(pl.location, ''), '(unspecified)')
               ORDER BY total_quantity DESC, location"""
        )
        rows = []
        for r in await cursor.fetchall():
            d = dict(r)
            names = (d.pop("model_names", None) or "")
            d["models"] = [n for n in names.split(",") if n][:12]
            rows.append(d)
    return {"locations": rows}


# ---------------------------------------------------------------------------
# Delete a specific print-log entry (adjusts the model summary + filament)
# ---------------------------------------------------------------------------
@router.delete("/{print_id}")
async def delete_print(request: Request, print_id: int):
    """Delete one print-log entry, decrementing the model's summary counter by
    its quantity and re-crediting any filament used."""
    db_path = _get_db_path(request)
    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM print_log WHERE id = ?", (print_id,)
        )
        entry = await cursor.fetchone()
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Print {print_id} not found")
        e = dict(entry)

        await db.execute("DELETE FROM print_log WHERE id = ?", (print_id,))
        await db.execute(
            "UPDATE models SET print_count = MAX(COALESCE(print_count, 0) - ?, 0), "
            "last_printed_at = (SELECT MAX(printed_at) FROM print_log WHERE model_id = ?) "
            "WHERE id = ?",
            (e["quantity"] or 1, e["model_id"], e["model_id"]),
        )
        if e["filament_id"] and e["grams_used"]:
            await db.execute(
                "UPDATE filaments SET remaining_g = COALESCE(remaining_g, 0) + ? "
                "WHERE id = ?",
                (e["grams_used"], e["filament_id"]),
            )
        await db.commit()
    return {"deleted": print_id}
