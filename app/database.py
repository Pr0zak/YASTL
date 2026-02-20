import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path
from app.config import settings

DB_PATH: Path = settings.MODEL_LIBRARY_DB


def set_db_path(path: str | Path) -> None:
    """Override the default database path at runtime."""
    global DB_PATH
    DB_PATH = Path(path)

# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    file_path TEXT NOT NULL UNIQUE,
    file_format TEXT NOT NULL,
    file_size INTEGER,
    vertex_count INTEGER,
    face_count INTEGER,
    dimensions_x REAL,
    dimensions_y REAL,
    dimensions_z REAL,
    thumbnail_path TEXT,
    file_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES categories(id),
    UNIQUE(name, parent_id)
);

CREATE TABLE IF NOT EXISTS model_categories (
    model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (model_id, category_id)
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS model_tags (
    model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (model_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_models_file_path ON models(file_path);
CREATE INDEX IF NOT EXISTS idx_models_file_hash ON models(file_hash);
CREATE INDEX IF NOT EXISTS idx_models_file_format ON models(file_format);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
"""

FTS_SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS models_fts USING fts5(
    name,
    description,
    content='',
    tokenize='porter unicode61'
);
"""

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
    WAL mode for better concurrent read performance.
    """
    if db_path is not None:
        set_db_path(db_path)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with get_db() as db:
        await db.executescript(SCHEMA_SQL)
        await db.executescript(FTS_SCHEMA_SQL)
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


async def update_fts_for_model(db: aiosqlite.Connection, model_id: int) -> None:
    """Update the FTS index for a single model within an existing connection."""
    # Remove old entry
    await db.execute("DELETE FROM models_fts WHERE rowid = ?", (model_id,))
    # Insert updated entry
    await db.execute("""
        INSERT INTO models_fts(rowid, name, description)
        SELECT m.id, m.name, m.description
        FROM models m
        WHERE m.id = ?
    """, (model_id,))
