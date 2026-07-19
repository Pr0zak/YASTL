"""API routes for full-text search across 3D models."""

import re

from fastapi import APIRouter, Query, Request
import aiosqlite

from app.api._helpers import open_db, enrich_models_page

from app.api.routes_models import _zip_display_name

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
    remaining token in double-quotes with a trailing ``*`` for prefix
    matching, so that partial words match (e.g. "ben" matches "benchy").

    Returns an empty string if no usable tokens remain.
    """
    # Remove special characters
    cleaned = _FTS5_SPECIAL_RE.sub(" ", raw)
    # Split into tokens, quote each one to avoid FTS5 keyword
    # interpretation (AND, OR, NOT, NEAR), and add * for prefix matching
    tokens = cleaned.split()
    if not tokens:
        return ""
    return " ".join(f'"{tok}"*' for tok in tokens)


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
    group_zips: bool = Query(default=False),
    zip_path: str | None = Query(default=None),
    tag_match: str = Query(default="and"),
    favorites_only: bool = Query(default=False),
    duplicates_only: bool = Query(default=False),
    collection: int | None = Query(default=None),
    sort_by: str = Query(default="relevance"),
    sort_order: str = Query(default="desc"),
    status: str = Query(default="active"),
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

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row

        # -----------------------------------------------------------------
        # Build the query dynamically
        # -----------------------------------------------------------------
        where_clauses: list[str] = []
        params: list = []

        # Only show active models by default (exclude missing/deleted)
        if status == "all":
            where_clauses.append("m.status IN ('active', 'error')")
        elif status == "error":
            where_clauses.append("m.status = 'error'")
        else:
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

        # Tag filter (AND or OR logic)
        if tag_list:
            tag_placeholders = ", ".join("?" for _ in tag_list)
            if tag_match == "or":
                where_clauses.append(
                    f"""m.id IN (
                        SELECT mt.model_id FROM model_tags mt
                        JOIN tags t ON t.id = mt.tag_id
                        WHERE t.name IN ({tag_placeholders})
                    )"""
                )
                params.extend(tag_list)
            else:
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

        # Collection membership filter
        if collection is not None:
            where_clauses.append(
                "m.id IN (SELECT cm.model_id FROM collection_models cm "
                "WHERE cm.collection_id = ?)"
            )
            params.append(collection)

        # Favorites filter
        if favorites_only:
            where_clauses.append(
                "m.id IN (SELECT f.model_id FROM favorites f)"
            )

        # Duplicates filter — only models whose hash appears more than once
        if duplicates_only:
            where_clauses.append(
                """m.file_hash IS NOT NULL AND m.file_hash != ''
                AND m.file_hash IN (
                    SELECT file_hash FROM models
                    WHERE file_hash IS NOT NULL AND file_hash != ''
                      AND status = 'active'
                    GROUP BY file_hash
                    HAVING COUNT(*) > 1
                )"""
            )

        # Zip path filter
        if zip_path is not None:
            where_clauses.append("m.zip_path = ?")
            params.append(zip_path)

        # Zip grouping
        zip_group_map: dict[int, dict] = {}
        if group_zips and zip_path is None:
            zip_where_sql = ""
            if where_clauses:
                zip_where_sql = "WHERE " + " AND ".join(where_clauses)
            zip_sql = f"""
                SELECT m.zip_path, MIN(m.id) AS rep_id, COUNT(*) AS cnt
                FROM models m
                {zip_where_sql}
                AND m.zip_path IS NOT NULL
                GROUP BY m.zip_path
                HAVING COUNT(*) > 1
            """
            cursor = await db.execute(zip_sql, params)
            zip_rows = await cursor.fetchall()
            rep_ids = set()
            for zr in zip_rows:
                zd = dict(zr)
                rep_ids.add(zd["rep_id"])
                zip_group_map[zd["rep_id"]] = {
                    "count": zd["cnt"],
                    "zip_path": zd["zip_path"],
                    "name": _zip_display_name(zd["zip_path"]),
                }

            if rep_ids:
                rep_placeholders = ", ".join("?" for _ in rep_ids)
                where_clauses.append(
                    f"(m.zip_path IS NULL OR m.id IN ({rep_placeholders}))"
                )
                params.extend(rep_ids)

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
        # Explicit sort overrides relevance ranking (used when the
        # unified frontend fetch carries a user-chosen sort).
        allowed_sort = {
            "name", "created_at", "updated_at", "file_size",
            "vertex_count", "face_count",
        }
        direction = "ASC" if sort_order.lower() == "asc" else "DESC"
        explicit_order = (
            f"m.{sort_by} {direction}" if sort_by in allowed_sort else None
        )

        if use_fts:
            # FTS5 only populates the hidden `rank` column on the table
            # instance being MATCHed, so rank must come from a MATCHed
            # subquery — joining models_fts bare yields rank = NULL for
            # every row (arbitrary result order).
            query_sql = f"""
                SELECT m.*, fts.rank AS _fts_rank
                FROM models m
                JOIN (
                    SELECT rowid, rank FROM models_fts
                    WHERE models_fts MATCH ?
                ) AS fts ON fts.rowid = m.id
                {where_sql}
                ORDER BY {explicit_order or 'fts.rank'}
                LIMIT ? OFFSET ?
            """
            page_params = [sanitized_q] + params + [limit, offset]
        else:
            query_sql = f"""
                SELECT m.* FROM models m
                {where_sql}
                ORDER BY {explicit_order or 'm.updated_at DESC'}
                LIMIT ? OFFSET ?
            """
            page_params = params + [limit, offset]
        cursor = await db.execute(query_sql, page_params)
        rows = await cursor.fetchall()

        # -----------------------------------------------------------------
        # Enrich the page (tags, categories, favorites, collections, dups)
        # -----------------------------------------------------------------
        models = []
        for row in rows:
            model = dict(row)
            model.pop("_fts_rank", None)
            models.append(model)
        await enrich_models_page(db, models)

        # Attach zip group info to representative models
        if zip_group_map:
            for m in models:
                if m["id"] in zip_group_map:
                    info = zip_group_map[m["id"]]
                    m["zip_model_count"] = info["count"]
                    m["zip_group_name"] = info["name"]

    return {
        "models": models,
        "total": total,
        "query": q,
        "limit": limit,
        "offset": offset,
    }
