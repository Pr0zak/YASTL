"""API routes for full-text search across 3D models."""

import re

from fastapi import APIRouter, Query, Request
import aiosqlite

router = APIRouter(prefix="/api/search", tags=["search"])

# Characters that have special meaning in FTS5 query syntax
_FTS5_SPECIAL_RE = re.compile(r'["*^(){}:+\-]')


def _get_db_path(request: Request) -> str:
    """Retrieve the database path from FastAPI app state."""
    return request.app.state.db_path


def _sanitize_fts_query(raw: str) -> str:
    """Sanitize a user-supplied string for safe use with FTS5 MATCH.

    Strips characters that carry special meaning in FTS5 query syntax
    (e.g. ``"``, ``*``, ``NEAR``, boolean operators) and wraps each
    remaining token in double-quotes so that the query is treated as a
    sequence of literal phrases.

    Returns an empty string if no usable tokens remain.
    """
    # Remove special characters
    cleaned = _FTS5_SPECIAL_RE.sub(" ", raw)
    # Split into tokens and quote each one to avoid FTS5 keyword
    # interpretation (AND, OR, NOT, NEAR)
    tokens = cleaned.split()
    if not tokens:
        return ""
    return " ".join(f'"{tok}"' for tok in tokens)


# ---------------------------------------------------------------------------
# Full-text search
# ---------------------------------------------------------------------------


@router.get("")
async def search_models(
    request: Request,
    q: str = Query(default="", description="Search query string"),
    format: str | None = Query(default=None, alias="format"),
    tags: str | None = Query(
        default=None, description="Comma-separated list of tag names"
    ),
    categories: str | None = Query(
        default=None, description="Comma-separated list of category names"
    ),
    library_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Search models using full-text search with optional filters.

    Parameters:
        q: Search query for FTS5 (matched against model name and description).
           If empty, returns all models (with optional filters applied).
        format: Filter by file format (e.g. ``stl``, ``obj``).
        tags: Comma-separated tag names. Models must have ALL specified tags.
        categories: Comma-separated category names. Models in ANY listed
            category are included.
        limit: Maximum number of results to return (1-500, default 50).
        offset: Number of results to skip for pagination (default 0).

    Returns:
        A dict with ``models`` (list), ``total`` (int), and ``query`` (str).
    """
    db_path = _get_db_path(request)

    # Parse comma-separated tags into a list
    tag_list: list[str] = []
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # Parse comma-separated categories into a list
    cat_list: list[str] = []
    if categories:
        cat_list = [c.strip() for c in categories.split(",") if c.strip()]

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # -----------------------------------------------------------------
        # Build the query dynamically
        # -----------------------------------------------------------------
        where_clauses: list[str] = []
        params: list = []

        # Only show active models by default (exclude missing/deleted)
        where_clauses.append("m.status = 'active'")

        # FTS filter: join with the FTS table when a query is provided
        sanitized_q = _sanitize_fts_query(q) if q else ""
        use_fts = bool(sanitized_q)

        if use_fts:
            where_clauses.append(
                """m.id IN (
                    SELECT rowid FROM models_fts WHERE models_fts MATCH ?
                )"""
            )
            params.append(sanitized_q)

        # Format filter
        if format is not None:
            where_clauses.append("LOWER(m.file_format) = ?")
            params.append(format.lower())

        # Tag filter: model must have ALL specified tags
        if tag_list:
            tag_placeholders = ", ".join("?" for _ in tag_list)
            where_clauses.append(
                f"""m.id IN (
                    SELECT mt.model_id FROM model_tags mt
                    JOIN tags t ON t.id = mt.tag_id
                    WHERE t.name IN ({tag_placeholders})
                    GROUP BY mt.model_id
                    HAVING COUNT(DISTINCT t.name) = ?
                )"""
            )
            params.extend(tag_list)
            params.append(len(tag_list))

        # Category filter: model in ANY of the specified categories
        if cat_list:
            cat_placeholders = ", ".join("?" for _ in cat_list)
            where_clauses.append(
                f"""m.id IN (
                    SELECT mc.model_id FROM model_categories mc
                    JOIN categories c ON c.id = mc.category_id
                    WHERE c.name IN ({cat_placeholders})
                )"""
            )
            params.extend(cat_list)

        # Library filter
        if library_id is not None:
            where_clauses.append("m.library_id = ?")
            params.append(library_id)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # -----------------------------------------------------------------
        # Count total matching models
        # -----------------------------------------------------------------
        count_sql = f"SELECT COUNT(*) as cnt FROM models m {where_sql}"
        cursor = await db.execute(count_sql, params)
        count_row = await cursor.fetchone()
        total = dict(count_row)["cnt"]

        # -----------------------------------------------------------------
        # Fetch the page of results.
        # When an FTS query is active, rank by BM25 relevance; otherwise
        # fall back to most-recently-updated first.
        # -----------------------------------------------------------------
        if use_fts:
            query_sql = f"""
                SELECT m.*, models_fts.rank AS _fts_rank
                FROM models m
                JOIN models_fts ON models_fts.rowid = m.id
                {where_sql}
                ORDER BY models_fts.rank
                LIMIT ? OFFSET ?
            """
        else:
            query_sql = f"""
                SELECT m.* FROM models m
                {where_sql}
                ORDER BY m.updated_at DESC
                LIMIT ? OFFSET ?
            """
        cursor = await db.execute(query_sql, params + [limit, offset])
        rows = await cursor.fetchall()

        # -----------------------------------------------------------------
        # Enrich each model with tags and categories
        # -----------------------------------------------------------------
        models = []
        for row in rows:
            model = dict(row)
            model.pop("_fts_rank", None)
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

            models.append(model)

    return {
        "models": models,
        "total": total,
        "query": q,
        "limit": limit,
        "offset": offset,
    }
