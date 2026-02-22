"""API route for library statistics dashboard."""

import aiosqlite
from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
async def get_stats():
    """Return aggregated library statistics."""
    db_path = str(settings.MODEL_LIBRARY_DB)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Total active models and file size
        cursor = await db.execute(
            "SELECT COUNT(*) as count, COALESCE(SUM(file_size), 0) as total_size "
            "FROM models WHERE status = 'active'"
        )
        row = dict(await cursor.fetchone())
        total_models = row["count"]
        total_size = row["total_size"]

        # Models by format
        cursor = await db.execute(
            "SELECT file_format, COUNT(*) as count, "
            "COALESCE(SUM(file_size), 0) as total_size "
            "FROM models WHERE status = 'active' "
            "GROUP BY file_format ORDER BY count DESC"
        )
        formats = [dict(r) for r in await cursor.fetchall()]

        # Models by library
        cursor = await db.execute(
            "SELECT l.id, l.name, COUNT(m.id) as count, "
            "COALESCE(SUM(m.file_size), 0) as total_size "
            "FROM libraries l "
            "LEFT JOIN models m ON m.library_id = l.id AND m.status = 'active' "
            "GROUP BY l.id ORDER BY count DESC"
        )
        libraries = [dict(r) for r in await cursor.fetchall()]

        # Top 20 tags by model count
        cursor = await db.execute(
            "SELECT t.name, COUNT(mt.model_id) as count "
            "FROM tags t "
            "JOIN model_tags mt ON mt.tag_id = t.id "
            "JOIN models m ON m.id = mt.model_id AND m.status = 'active' "
            "GROUP BY t.id ORDER BY count DESC LIMIT 20"
        )
        top_tags = [dict(r) for r in await cursor.fetchall()]

        # Total unique tags
        cursor = await db.execute(
            "SELECT COUNT(DISTINCT t.id) as count FROM tags t "
            "JOIN model_tags mt ON mt.tag_id = t.id "
            "JOIN models m ON m.id = mt.model_id AND m.status = 'active'"
        )
        total_tags = dict(await cursor.fetchone())["count"]

        # Categories count
        cursor = await db.execute("SELECT COUNT(*) as count FROM categories")
        total_categories = dict(await cursor.fetchone())["count"]

        # Favorites count
        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM favorites f "
            "JOIN models m ON m.id = f.model_id AND m.status = 'active'"
        )
        total_favorites = dict(await cursor.fetchone())["count"]

        # Collections count
        cursor = await db.execute("SELECT COUNT(*) as count FROM collections")
        total_collections = dict(await cursor.fetchone())["count"]

        # Duplicate groups (models sharing the same file_hash)
        cursor = await db.execute(
            "SELECT COUNT(*) as groups FROM ("
            "  SELECT file_hash FROM models "
            "  WHERE status = 'active' AND file_hash IS NOT NULL AND file_hash != '' "
            "  GROUP BY file_hash HAVING COUNT(*) > 1"
            ")"
        )
        duplicate_groups = dict(await cursor.fetchone())["groups"]

        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM models "
            "WHERE status = 'active' AND file_hash IN ("
            "  SELECT file_hash FROM models "
            "  WHERE status = 'active' AND file_hash IS NOT NULL AND file_hash != '' "
            "  GROUP BY file_hash HAVING COUNT(*) > 1"
            ")"
        )
        duplicate_models = dict(await cursor.fetchone())["count"]

        # Thumbnail coverage
        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM models "
            "WHERE status = 'active' AND thumbnail_path IS NOT NULL"
        )
        thumbnails_generated = dict(await cursor.fetchone())["count"]

        # Zip-sourced models
        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM models "
            "WHERE status = 'active' AND zip_path IS NOT NULL"
        )
        zip_models = dict(await cursor.fetchone())["count"]

        # Models with source URLs
        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM models "
            "WHERE status = 'active' AND source_url IS NOT NULL AND source_url != ''"
        )
        sourced_models = dict(await cursor.fetchone())["count"]

        # Recently added (last 7 days / 30 days)
        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM models "
            "WHERE status = 'active' AND created_at >= datetime('now', '-7 days')"
        )
        added_7d = dict(await cursor.fetchone())["count"]

        cursor = await db.execute(
            "SELECT COUNT(*) as count FROM models "
            "WHERE status = 'active' AND created_at >= datetime('now', '-30 days')"
        )
        added_30d = dict(await cursor.fetchone())["count"]

        # Top 10 largest models
        cursor = await db.execute(
            "SELECT id, name, file_format, file_size "
            "FROM models WHERE status = 'active' AND file_size IS NOT NULL "
            "ORDER BY file_size DESC LIMIT 10"
        )
        largest_models = [dict(r) for r in await cursor.fetchall()]

    return {
        "total_models": total_models,
        "total_size": total_size,
        "formats": formats,
        "libraries": libraries,
        "top_tags": top_tags,
        "total_tags": total_tags,
        "total_categories": total_categories,
        "total_favorites": total_favorites,
        "total_collections": total_collections,
        "duplicate_groups": duplicate_groups,
        "duplicate_models": duplicate_models,
        "thumbnails_generated": thumbnails_generated,
        "thumbnail_coverage": round(thumbnails_generated / total_models * 100, 1) if total_models > 0 else 0,
        "zip_models": zip_models,
        "sourced_models": sourced_models,
        "added_7d": added_7d,
        "added_30d": added_30d,
        "largest_models": largest_models,
    }
