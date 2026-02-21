"""Full-text search service for 3D model files.

Provides FTS5-powered search against the ``models_fts`` virtual table,
with optional filtering by file format, tags, and categories. Results are
ranked by BM25 relevance.
"""

import logging

import aiosqlite

logger = logging.getLogger(__name__)


async def search_models(
    db_path: str,
    query: str,
    limit: int = 50,
    offset: int = 0,
    filters: dict | None = None,
) -> dict:
    """Search models using FTS5 full-text search with optional filters.

    Args:
        db_path: Path to the SQLite database file.
        query: The search query string (passed to FTS5 MATCH).
        limit: Maximum number of results to return.
        offset: Number of results to skip (for pagination).
        filters: Optional dictionary of filters:
            - ``file_format`` (str): filter by exact file format
            - ``tags`` (list[str]): filter to models having *all* listed tags
            - ``categories`` (list[str]): filter to models in *any* of the
              listed categories
            - ``favorites_only`` (bool): only return favorited models
            - ``collection_id`` (int): filter to models in a specific collection
            - ``sort_by`` (str): field to sort by (default: BM25 rank)
            - ``sort_order`` (str): ``asc`` or ``desc``

    Returns:
        A dictionary with keys:
            - ``models`` (list[dict]): matching model rows
            - ``total`` (int): total count of matching rows (before pagination)
            - ``query`` (str): the original search query
    """
    if not query or not query.strip():
        return {"models": [], "total": 0, "query": query}

    filters = filters or {}

    db = await aiosqlite.connect(db_path)
    db.row_factory = _dict_row_factory
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")

    try:
        # ----- Build dynamic WHERE clauses --------------------------------
        where_clauses: list[str] = []
        params: list = []

        # FTS match (always present)
        where_clauses.append("models_fts MATCH ?")
        params.append(query.strip())

        # File format filter
        file_format = filters.get("file_format")
        if file_format:
            where_clauses.append("m.file_format = ?")
            params.append(file_format)

        # Tags filter -- model must have ALL specified tags
        tags: list[str] = filters.get("tags") or []
        if tags:
            tag_placeholders = ", ".join("?" for _ in tags)
            where_clauses.append(
                f"""m.id IN (
                    SELECT mt.model_id
                    FROM model_tags mt
                    JOIN tags t ON t.id = mt.tag_id
                    WHERE t.name IN ({tag_placeholders})
                    GROUP BY mt.model_id
                    HAVING COUNT(DISTINCT t.name) = ?
                )"""
            )
            params.extend(tags)
            params.append(len(tags))

        # Categories filter -- model must be in ANY of the specified categories
        categories: list[str] = filters.get("categories") or []
        if categories:
            cat_placeholders = ", ".join("?" for _ in categories)
            where_clauses.append(
                f"""m.id IN (
                    SELECT mc.model_id
                    FROM model_categories mc
                    JOIN categories c ON c.id = mc.category_id
                    WHERE c.name IN ({cat_placeholders})
                )"""
            )
            params.extend(categories)

        # Favorites filter
        if filters.get("favorites_only"):
            where_clauses.append(
                "m.id IN (SELECT f.model_id FROM favorites f)"
            )

        # Collection filter
        collection_id = filters.get("collection_id")
        if collection_id is not None:
            where_clauses.append(
                "m.id IN (SELECT cm.model_id FROM collection_models cm "
                "WHERE cm.collection_id = ?)"
            )
            params.append(collection_id)

        where_sql = " AND ".join(where_clauses)

        # ----- Count total matching rows ----------------------------------
        count_sql = f"""
            SELECT COUNT(*) AS cnt
            FROM models_fts
            JOIN models m ON m.id = models_fts.rowid
            WHERE {where_sql}
        """
        cursor = await db.execute(count_sql, params)
        count_row = await cursor.fetchone()
        total: int = count_row["cnt"] if count_row else 0

        # ----- Determine sort order ---------------------------------------
        sort_by = filters.get("sort_by")
        sort_order = filters.get("sort_order", "desc")
        if sort_order not in ("asc", "desc"):
            sort_order = "desc"

        allowed_sort = {
            "name", "created_at", "updated_at", "file_size",
            "vertex_count", "face_count",
        }
        if sort_by and sort_by in allowed_sort:
            order_clause = f"m.{sort_by} {sort_order}"
        else:
            order_clause = "rank"  # default BM25 relevance

        # ----- Fetch paginated results ------------------------------------
        select_sql = f"""
            SELECT
                m.*,
                rank
            FROM models_fts
            JOIN models m ON m.id = models_fts.rowid
            WHERE {where_sql}
            ORDER BY {order_clause}
            LIMIT ? OFFSET ?
        """
        page_params = params + [limit, offset]
        cursor = await db.execute(select_sql, page_params)
        rows = await cursor.fetchall()

        # Enrich each model with its tags, categories, and favorite status
        models: list[dict] = []
        for row in rows:
            model = dict(row)
            model.pop("rank", None)  # internal FTS field
            model_id = model["id"]

            # Fetch tags
            tag_cursor = await db.execute(
                """
                SELECT t.name
                FROM tags t
                JOIN model_tags mt ON mt.tag_id = t.id
                WHERE mt.model_id = ?
                ORDER BY t.name
                """,
                (model_id,),
            )
            tag_rows = await tag_cursor.fetchall()
            model["tags"] = [t["name"] for t in tag_rows]

            # Fetch categories
            cat_cursor = await db.execute(
                """
                SELECT c.name
                FROM categories c
                JOIN model_categories mc ON mc.category_id = c.id
                WHERE mc.model_id = ?
                ORDER BY c.name
                """,
                (model_id,),
            )
            cat_rows = await cat_cursor.fetchall()
            model["categories"] = [c["name"] for c in cat_rows]

            # Favorite status
            fav_cursor = await db.execute(
                "SELECT 1 FROM favorites WHERE model_id = ?", (model_id,)
            )
            model["is_favorite"] = await fav_cursor.fetchone() is not None

            models.append(model)

        return {"models": models, "total": total, "query": query}

    finally:
        await db.close()


async def rebuild_fts_index(db_path: str) -> None:
    """Rebuild the FTS5 index from the current contents of the models table.

    Deletes all existing FTS entries and re-inserts every model's name and
    description. Useful after bulk imports or data migrations.

    Args:
        db_path: Path to the SQLite database file.
    """
    logger.info("Rebuilding FTS index from models table...")

    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA journal_mode=WAL")

    try:
        await db.execute("DELETE FROM models_fts")
        await db.execute(
            """
            INSERT INTO models_fts(rowid, name, description)
            SELECT m.id, m.name, m.description
            FROM models m
            """
        )
        await db.commit()
        logger.info("FTS index rebuilt successfully.")
    finally:
        await db.close()


async def update_fts_entry(
    db: aiosqlite.Connection,
    model_id: int,
    name: str,
    description: str,
) -> None:
    """Insert or update a single entry in the FTS index.

    Removes any existing entry for *model_id* first, then inserts the
    current name and description. This function does **not** commit --
    the caller is responsible for committing the transaction.

    Args:
        db: An active aiosqlite connection (caller manages lifecycle).
        model_id: The ``models.id`` primary key.
        name: The model's display name.
        description: The model's description text.
    """
    # Remove stale entry (if any)
    await db.execute(
        "DELETE FROM models_fts WHERE rowid = ?", (model_id,)
    )

    # Insert fresh entry
    await db.execute(
        "INSERT INTO models_fts(rowid, name, description) VALUES (?, ?, ?)",
        (model_id, name, description),
    )

    logger.debug("Updated FTS entry for model id=%d", model_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _dict_row_factory(cursor: aiosqlite.Cursor, row: tuple) -> dict:
    """Convert an aiosqlite row into a plain dictionary."""
    columns = [description[0] for description in cursor.description]
    return dict(zip(columns, row))
