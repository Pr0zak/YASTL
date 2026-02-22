"""API routes for collection management (regular and smart collections)."""

import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request
import aiosqlite

logger = logging.getLogger("yastl")

router = APIRouter(prefix="/api/collections", tags=["collections"])


def _get_db_path(request: Request) -> str:
    return request.app.state.db_path


def _build_smart_count_query(
    rules: dict,
) -> tuple[str, list]:
    """Build a COUNT query from smart collection rules.

    Returns (sql, params) for counting matching active models.
    """
    where = ["m.status = 'active'"]
    params: list = []

    if rules.get("format"):
        where.append("LOWER(m.file_format) = LOWER(?)")
        params.append(rules["format"])

    if rules.get("library_id"):
        where.append("m.library_id = ?")
        params.append(int(rules["library_id"]))

    if rules.get("tags"):
        tags = rules["tags"]
        placeholders = ",".join("?" for _ in tags)
        where.append(
            f"m.id IN ("
            f"SELECT mt.model_id FROM model_tags mt "
            f"JOIN tags t ON t.id = mt.tag_id "
            f"WHERE t.name IN ({placeholders}) "
            f"GROUP BY mt.model_id "
            f"HAVING COUNT(DISTINCT t.name) = ?)"
        )
        params.extend(tags)
        params.append(len(tags))

    if rules.get("categories"):
        cats = rules["categories"]
        placeholders = ",".join("?" for _ in cats)
        where.append(
            f"m.id IN ("
            f"SELECT mc.model_id FROM model_categories mc "
            f"JOIN categories c ON c.id = mc.category_id "
            f"WHERE c.name IN ({placeholders}))"
        )
        params.extend(cats)

    if rules.get("favoritesOnly"):
        where.append("m.id IN (SELECT f.model_id FROM favorites f)")

    if rules.get("duplicatesOnly"):
        where.append(
            "m.file_hash IS NOT NULL AND m.file_hash != '' "
            "AND m.file_hash IN ("
            "SELECT file_hash FROM models "
            "WHERE file_hash IS NOT NULL AND file_hash != '' "
            "AND status = 'active' "
            "GROUP BY file_hash HAVING COUNT(*) > 1)"
        )

    if rules.get("sizeMin"):
        where.append("m.file_size >= ?")
        params.append(int(rules["sizeMin"]))

    if rules.get("sizeMax"):
        where.append("m.file_size <= ?")
        params.append(int(rules["sizeMax"]))

    if rules.get("dateRange"):
        days_map = {
            "last_7d": 7,
            "last_30d": 30,
            "last_90d": 90,
            "last_365d": 365,
        }
        days = days_map.get(rules["dateRange"])
        if days:
            where.append(
                f"m.created_at >= datetime('now', '-{days} days')"
            )

    sql = f"SELECT COUNT(*) as cnt FROM models m WHERE {' AND '.join(where)}"
    return sql, params


@router.get("")
async def list_collections(request: Request):
    """List all collections with model counts."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT c.*, COUNT(cm.model_id) as model_count
            FROM collections c
            LEFT JOIN collection_models cm ON cm.collection_id = c.id
            GROUP BY c.id
            ORDER BY c.updated_at DESC
            """
        )
        rows = await cursor.fetchall()

        results = []
        for r in rows:
            coll = dict(r)
            # For smart collections, compute model_count dynamically
            if coll.get("is_smart"):
                try:
                    rules = json.loads(coll.get("rules") or "{}")
                    sql, params = _build_smart_count_query(rules)
                    cursor = await db.execute(sql, params)
                    count_row = await cursor.fetchone()
                    coll["model_count"] = dict(count_row)["cnt"]
                except Exception as e:
                    logger.warning("Smart collection %s count failed: %s", coll["id"], e)
                    coll["model_count"] = 0
            results.append(coll)

    return {"collections": results}


@router.post("", status_code=201)
async def create_collection(request: Request):
    """Create a new collection (regular or smart).

    Expects JSON body: {"name": "...", "description": "...", "color": "#hex",
                        "is_smart": false, "rules": {}}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    name = body.get("name")
    description = body.get("description", "")
    color = body.get("color")
    is_smart = 1 if body.get("is_smart") else 0
    rules = body.get("rules", {})

    if not name or not isinstance(name, str) or not name.strip():
        raise HTTPException(
            status_code=400,
            detail="'name' is required and must be a non-empty string",
        )

    name = name.strip()
    rules_json = json.dumps(rules) if isinstance(rules, dict) else "{}"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "INSERT INTO collections (name, description, color, is_smart, rules) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, description or "", color, is_smart, rules_json),
        )
        collection_id = cursor.lastrowid
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM collections WHERE id = ?", (collection_id,)
        )
        row = await cursor.fetchone()

    result = dict(row)
    # Compute smart collection count
    if is_smart:
        try:
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                sql, params = _build_smart_count_query(rules)
                cursor = await db.execute(sql, params)
                count_row = await cursor.fetchone()
                result["model_count"] = dict(count_row)["cnt"]
        except Exception:
            result["model_count"] = 0
    else:
        result["model_count"] = 0
    return result


@router.get("/{collection_id}")
async def get_collection(
    request: Request,
    collection_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Get a collection with its models."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Fetch collection
        cursor = await db.execute(
            "SELECT * FROM collections WHERE id = ?", (collection_id,)
        )
        coll_row = await cursor.fetchone()
        if coll_row is None:
            raise HTTPException(
                status_code=404, detail=f"Collection {collection_id} not found"
            )

        collection = dict(coll_row)

        # Count total models in collection
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM collection_models WHERE collection_id = ?",
            (collection_id,),
        )
        count_row = await cursor.fetchone()
        collection["model_count"] = dict(count_row)["cnt"]

        # Fetch models in collection
        cursor = await db.execute(
            """
            SELECT m.*, cm.position, cm.added_at as collection_added_at
            FROM models m
            JOIN collection_models cm ON cm.model_id = m.id
            WHERE cm.collection_id = ?
            ORDER BY cm.position, cm.added_at
            LIMIT ? OFFSET ?
            """,
            (collection_id, limit, offset),
        )
        rows = await cursor.fetchall()

        models = []
        for row in rows:
            model = dict(row)
            model_id = model["id"]

            # Tags
            cursor = await db.execute(
                """
                SELECT t.name FROM tags t
                JOIN model_tags mt ON mt.tag_id = t.id
                WHERE mt.model_id = ?
                ORDER BY t.name
                """,
                (model_id,),
            )
            tag_rows = await cursor.fetchall()
            model["tags"] = [dict(r)["name"] for r in tag_rows]

            # Categories
            cursor = await db.execute(
                """
                SELECT c.name FROM categories c
                JOIN model_categories mc ON mc.category_id = c.id
                WHERE mc.model_id = ?
                ORDER BY c.name
                """,
                (model_id,),
            )
            cat_rows = await cursor.fetchall()
            model["categories"] = [dict(r)["name"] for r in cat_rows]

            # Favorite status
            cursor = await db.execute(
                "SELECT 1 FROM favorites WHERE model_id = ?", (model_id,)
            )
            model["is_favorite"] = await cursor.fetchone() is not None

            models.append(model)

        collection["models"] = models
        return collection


@router.put("/{collection_id}")
async def update_collection(request: Request, collection_id: int):
    """Update a collection's metadata.

    Expects JSON body with optional: {"name": "...", "description": "...",
                                      "color": "#hex", "rules": {}}
    """
    db_path = _get_db_path(request)
    body = await request.json()

    name = body.get("name")
    description = body.get("description")
    color = body.get("color")
    rules = body.get("rules")

    if name is None and description is None and color is None and rules is None:
        raise HTTPException(
            status_code=400,
            detail="At least one of 'name', 'description', 'color', or 'rules' is required",
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT id FROM collections WHERE id = ?", (collection_id,)
        )
        if await cursor.fetchone() is None:
            raise HTTPException(
                status_code=404, detail=f"Collection {collection_id} not found"
            )

        set_clauses: list[str] = []
        params: list = []

        if name is not None:
            set_clauses.append("name = ?")
            params.append(name.strip())
        if description is not None:
            set_clauses.append("description = ?")
            params.append(description)
        if color is not None:
            set_clauses.append("color = ?")
            params.append(color)
        if rules is not None:
            set_clauses.append("rules = ?")
            params.append(json.dumps(rules) if isinstance(rules, dict) else "{}")

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        params.append(collection_id)

        await db.execute(
            f"UPDATE collections SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )
        await db.commit()

        cursor = await db.execute(
            """
            SELECT c.*, COUNT(cm.model_id) as model_count
            FROM collections c
            LEFT JOIN collection_models cm ON cm.collection_id = c.id
            WHERE c.id = ?
            GROUP BY c.id
            """,
            (collection_id,),
        )
        row = await cursor.fetchone()

        result = dict(row)
        # Recompute smart count
        if result.get("is_smart"):
            try:
                r = json.loads(result.get("rules") or "{}")
                sql, p = _build_smart_count_query(r)
                cursor = await db.execute(sql, p)
                count_row = await cursor.fetchone()
                result["model_count"] = dict(count_row)["cnt"]
            except Exception:
                pass

    return result


@router.delete("/{collection_id}")
async def delete_collection(request: Request, collection_id: int):
    """Delete a collection. Models are NOT deleted."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        cursor = await db.execute(
            "SELECT id, name FROM collections WHERE id = ?", (collection_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Collection {collection_id} not found"
            )

        name = dict(row)["name"]
        await db.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
        await db.commit()

    return {"detail": f"Collection '{name}' (id={collection_id}) deleted"}


@router.post("/{collection_id}/models")
async def add_models_to_collection(request: Request, collection_id: int):
    """Add models to a collection.

    Expects JSON body: {"model_ids": [1, 2, 3]}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    model_ids = body.get("model_ids", [])

    if not model_ids or not isinstance(model_ids, list):
        raise HTTPException(
            status_code=400, detail="'model_ids' must be a non-empty list"
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Verify collection exists
        cursor = await db.execute(
            "SELECT id FROM collections WHERE id = ?", (collection_id,)
        )
        if await cursor.fetchone() is None:
            raise HTTPException(
                status_code=404, detail=f"Collection {collection_id} not found"
            )

        # Get current max position
        cursor = await db.execute(
            "SELECT COALESCE(MAX(position), -1) as max_pos "
            "FROM collection_models WHERE collection_id = ?",
            (collection_id,),
        )
        max_pos = dict(await cursor.fetchone())["max_pos"]

        added = 0
        for model_id in model_ids:
            # Verify model exists
            cursor = await db.execute(
                "SELECT id FROM models WHERE id = ?", (model_id,)
            )
            if await cursor.fetchone() is None:
                continue

            max_pos += 1
            try:
                await db.execute(
                    "INSERT OR IGNORE INTO collection_models "
                    "(collection_id, model_id, position) VALUES (?, ?, ?)",
                    (collection_id, model_id, max_pos),
                )
                if db.total_changes:
                    added += 1
            except Exception:
                pass

        # Update collection timestamp
        await db.execute(
            "UPDATE collections SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (collection_id,),
        )
        await db.commit()

    return {
        "detail": f"Added {added} model(s) to collection",
        "added": added,
    }


@router.delete("/{collection_id}/models/{model_id}")
async def remove_model_from_collection(
    request: Request, collection_id: int, model_id: int
):
    """Remove a model from a collection."""
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        result = await db.execute(
            "DELETE FROM collection_models "
            "WHERE collection_id = ? AND model_id = ?",
            (collection_id, model_id),
        )
        if result.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_id} is not in collection {collection_id}",
            )

        await db.execute(
            "UPDATE collections SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (collection_id,),
        )
        await db.commit()

    return {"detail": f"Model {model_id} removed from collection {collection_id}"}


@router.put("/{collection_id}/models/reorder")
async def reorder_collection_models(request: Request, collection_id: int):
    """Reorder models in a collection.

    Expects JSON body: {"model_ids": [3, 1, 2]} — the order defines positions.
    """
    db_path = _get_db_path(request)
    body = await request.json()
    model_ids = body.get("model_ids", [])

    if not model_ids or not isinstance(model_ids, list):
        raise HTTPException(
            status_code=400, detail="'model_ids' must be a non-empty list"
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT id FROM collections WHERE id = ?", (collection_id,)
        )
        if await cursor.fetchone() is None:
            raise HTTPException(
                status_code=404, detail=f"Collection {collection_id} not found"
            )

        for position, model_id in enumerate(model_ids):
            await db.execute(
                "UPDATE collection_models SET position = ? "
                "WHERE collection_id = ? AND model_id = ?",
                (position, collection_id, model_id),
            )

        await db.execute(
            "UPDATE collections SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (collection_id,),
        )
        await db.commit()

    return {"detail": "Collection reordered", "order": model_ids}
