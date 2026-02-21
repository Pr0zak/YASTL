"""Database schema definitions, migrations, and post-migration indexes.

Extracted from database.py to keep schema constants separate from
connection and query logic.
"""

# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS libraries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
    thumbnail_mode TEXT,
    thumbnail_quality TEXT,
    thumbnail_generated_at TIMESTAMP,
    file_hash TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    library_id INTEGER REFERENCES libraries(id) ON DELETE SET NULL,
    zip_path TEXT,
    zip_entry TEXT,
    source_url TEXT,
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

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS favorites (
    model_id INTEGER PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    color TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collection_models (
    collection_id INTEGER REFERENCES collections(id) ON DELETE CASCADE,
    model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
    position INTEGER DEFAULT 0,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (collection_id, model_id)
);

CREATE TABLE IF NOT EXISTS saved_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    query TEXT DEFAULT '',
    filters TEXT DEFAULT '{}',
    sort_by TEXT DEFAULT 'created_at',
    sort_order TEXT DEFAULT 'desc',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_models_file_path ON models(file_path);
CREATE INDEX IF NOT EXISTS idx_models_file_hash ON models(file_hash);
CREATE INDEX IF NOT EXISTS idx_models_file_format ON models(file_format);
CREATE INDEX IF NOT EXISTS idx_models_library_id ON models(library_id);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
CREATE INDEX IF NOT EXISTS idx_collection_models_model ON collection_models(model_id);
CREATE INDEX IF NOT EXISTS idx_collection_models_position ON collection_models(collection_id, position);
"""

# Indexes on migrated columns — created after migrations in init_db()
_POST_MIGRATION_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_models_status ON models(status)",
    "CREATE INDEX IF NOT EXISTS idx_models_zip_path ON models(zip_path)",
]

MIGRATION_SQL = """
-- Add library_id column to models if it doesn't exist (migration for existing DBs)
ALTER TABLE models ADD COLUMN library_id INTEGER REFERENCES libraries(id) ON DELETE SET NULL;
"""

FTS_SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS models_fts USING fts5(
    name,
    description,
    tokenize='porter unicode61'
);
"""
