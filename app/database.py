import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path
from app.config import settings
from app.database_schema import SCHEMA_SQL, FTS_SCHEMA_SQL, MIGRATION_SQL, _POST_MIGRATION_INDEXES

DB_PATH: Path = settings.MODEL_LIBRARY_DB


def set_db_path(path: str | Path) -> None:
    """Override the default database path at runtime."""
    global DB_PATH
    DB_PATH = Path(path)

# ---------------------------------------------------------------------------
# Helper: dict row factory
# ---------------------------------------------------------------------------


def _dict_row_factory(cursor: aiosqlite.Cursor, row: tuple) -> dict:
    """Convert a sqlite3 Row into a plain dict."""
    columns = [description[0] for description in cursor.description]
    return dict(zip(columns, row))


# ---------------------------------------------------------------------------
# Database access helpers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def get_db():
    """Async context manager that yields an aiosqlite connection.

    Usage:
        async with get_db() as db:
            await db.execute(...)
    """
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = _dict_row_factory
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
    finally:
        await db.close()


async def init_db(db_path: str | Path | None = None) -> None:
    """Create all tables and the FTS5 virtual table.

    Ensures the parent directory for the database file exists and enables
    WAL mode for better concurrent read performance.  Also runs lightweight
    migrations for existing databases (e.g. adding the ``library_id`` column).
    """
    if db_path is not None:
        set_db_path(db_path)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with get_db() as db:
        await db.executescript(SCHEMA_SQL)
        await db.executescript(FTS_SCHEMA_SQL)

        # Run migrations for existing databases
        cursor = await db.execute("PRAGMA table_info(models)")
        columns = [row["name"] for row in await cursor.fetchall()]
        if "library_id" not in columns:
            try:
                await db.executescript(MIGRATION_SQL)
            except Exception:
                pass  # Column already exists or table just created with it

        # Add zip_path and zip_entry columns for zip archive support
        if "zip_path" not in columns:
            try:
                await db.execute("ALTER TABLE models ADD COLUMN zip_path TEXT")
                await db.execute("ALTER TABLE models ADD COLUMN zip_entry TEXT")
            except Exception:
                pass  # Columns already exist or table just created with them

        # Add status column for soft-delete / archive support
        if "status" not in columns:
            try:
                await db.execute(
                    "ALTER TABLE models ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
                )
            except Exception:
                pass  # Column already exists or table just created with it

        # Add thumbnail tracking columns
        if "thumbnail_mode" not in columns:
            try:
                await db.execute(
                    "ALTER TABLE models ADD COLUMN thumbnail_mode TEXT"
                )
                await db.execute(
                    "ALTER TABLE models ADD COLUMN thumbnail_quality TEXT"
                )
                await db.execute(
                    "ALTER TABLE models ADD COLUMN thumbnail_generated_at TIMESTAMP"
                )
            except Exception:
                pass  # Columns already exist or table just created with them

        # Add source_url column for URL-imported models
        if "source_url" not in columns:
            try:
                await db.execute(
                    "ALTER TABLE models ADD COLUMN source_url TEXT"
                )
            except Exception:
                pass  # Column already exists or table just created with it

        # Create indexes on migrated columns (must run after migrations)
        for sql in _POST_MIGRATION_INDEXES:
            try:
                await db.execute(sql)
            except Exception:
                pass

        await db.commit()


# ---------------------------------------------------------------------------
# FTS helpers
# ---------------------------------------------------------------------------


async def rebuild_fts() -> None:
    """Rebuild the full-text search index from current model data."""
    async with get_db() as db:
        await db.execute("DELETE FROM models_fts")
        await db.execute("""
            INSERT INTO models_fts(rowid, name, description)
            SELECT m.id, m.name, m.description
            FROM models m
        """)
        await db.commit()


async def get_setting(key: str, default: str | None = None) -> str | None:
    """Retrieve a setting value by key, returning *default* if not set."""
    async with get_db() as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        if row is not None:
            return row["value"]
        return default


async def set_setting(key: str, value: str) -> None:
    """Insert or update a setting value."""
    async with get_db() as db:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()


async def get_all_settings() -> dict[str, str]:
    """Return all stored settings as a dict."""
    async with get_db() as db:
        cursor = await db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}


async def update_fts_for_model(db: aiosqlite.Connection, model_id: int) -> None:
    """Update the FTS index for a single model within an existing connection."""
    # Remove old entry
    await db.execute("DELETE FROM models_fts WHERE rowid = ?", (model_id,))
    # Insert updated entry
    await db.execute(
        """
        INSERT INTO models_fts(rowid, name, description)
        SELECT m.id, m.name, m.description
        FROM models m
        WHERE m.id = ?
    """,
        (model_id,),
    )
