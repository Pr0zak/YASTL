"""Tests for app.database module."""

import aiosqlite
import pytest

from app.database import init_db, get_db, set_db_path, rebuild_fts, update_fts_for_model


@pytest.mark.asyncio
async def test_init_db_creates_tables(db_path):
    """init_db should create all required tables."""
    await init_db(db_path)

    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]

    assert "models" in tables
    assert "tags" in tables
    assert "model_tags" in tables
    assert "categories" in tables
    assert "model_categories" in tables
    assert "models_fts" in tables


@pytest.mark.asyncio
async def test_init_db_creates_parent_directory(tmp_path):
    """init_db should create parent directories if they don't exist."""
    nested_path = str(tmp_path / "a" / "b" / "c" / "test.db")
    await init_db(nested_path)

    async with aiosqlite.connect(nested_path) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in await cursor.fetchall()]
    assert "models" in tables


@pytest.mark.asyncio
async def test_init_db_is_idempotent(db_path):
    """Calling init_db twice should not raise or corrupt the database."""
    await init_db(db_path)
    await init_db(db_path)

    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM models")
        row = await cursor.fetchone()
    assert row[0] == 0


@pytest.mark.asyncio
async def test_get_db_returns_connection(db):
    """get_db should return a working database connection."""
    async with get_db() as conn:
        cursor = await conn.execute("SELECT 1")
        row = await cursor.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_get_db_uses_wal_mode(db):
    """get_db should enable WAL mode."""
    async with get_db() as conn:
        cursor = await conn.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
    # row_factory returns a dict
    mode = row["journal_mode"] if isinstance(row, dict) else row[0]
    assert mode.lower() == "wal"


@pytest.mark.asyncio
async def test_get_db_enables_foreign_keys(db):
    """get_db should enable foreign keys."""
    async with get_db() as conn:
        cursor = await conn.execute("PRAGMA foreign_keys")
        row = await cursor.fetchone()
    fk = row["foreign_keys"] if isinstance(row, dict) else row[0]
    assert fk == 1


@pytest.mark.asyncio
async def test_set_db_path(tmp_path):
    """set_db_path should change the module-level DB_PATH."""
    new_path = str(tmp_path / "new.db")
    set_db_path(new_path)
    # The import reflects the change
    from app.database import DB_PATH
    assert str(DB_PATH) == new_path


@pytest.mark.asyncio
async def test_rebuild_fts(db):
    """rebuild_fts should repopulate the FTS index from models table."""
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            """INSERT INTO models (name, description, file_path, file_format)
               VALUES ('dragon', 'a fire dragon', '/tmp/dragon.stl', 'STL')"""
        )
        await conn.execute(
            """INSERT INTO models (name, description, file_path, file_format)
               VALUES ('cube', 'simple cube', '/tmp/cube.stl', 'STL')"""
        )
        await conn.commit()

    set_db_path(db)
    await rebuild_fts()

    async with aiosqlite.connect(db) as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM models_fts")
        row = await cursor.fetchone()
    assert row[0] == 2


@pytest.mark.asyncio
async def test_update_fts_for_model(db):
    """update_fts_for_model should update the FTS entry for a single model."""
    async with aiosqlite.connect(db) as conn:
        cursor = await conn.execute(
            """INSERT INTO models (name, description, file_path, file_format)
               VALUES ('robot', 'mech robot', '/tmp/robot.stl', 'STL')"""
        )
        model_id = cursor.lastrowid
        await conn.commit()

        await update_fts_for_model(conn, model_id)
        await conn.commit()

        # Search FTS for the inserted model
        cursor = await conn.execute(
            "SELECT rowid FROM models_fts WHERE models_fts MATCH 'robot'"
        )
        rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == model_id


@pytest.mark.asyncio
async def test_models_table_schema(db):
    """Verify the models table has all expected columns."""
    async with aiosqlite.connect(db) as conn:
        cursor = await conn.execute("PRAGMA table_info(models)")
        columns = {row[1] for row in await cursor.fetchall()}

    expected = {
        "id", "name", "description", "file_path", "file_format",
        "file_size", "vertex_count", "face_count",
        "dimensions_x", "dimensions_y", "dimensions_z",
        "thumbnail_path", "file_hash", "created_at", "updated_at",
    }
    assert expected.issubset(columns)


@pytest.mark.asyncio
async def test_unique_file_path_constraint(db):
    """Inserting two models with the same file_path should raise."""
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            """INSERT INTO models (name, description, file_path, file_format)
               VALUES ('m1', '', '/tmp/same.stl', 'STL')"""
        )
        await conn.commit()

        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                """INSERT INTO models (name, description, file_path, file_format)
                   VALUES ('m2', '', '/tmp/same.stl', 'STL')"""
            )


@pytest.mark.asyncio
async def test_cascade_delete_model_tags(db):
    """Deleting a model should cascade-delete its model_tags entries."""
    async with aiosqlite.connect(db) as conn:
        await conn.execute("PRAGMA foreign_keys=ON")
        cursor = await conn.execute(
            """INSERT INTO models (name, description, file_path, file_format)
               VALUES ('m1', '', '/tmp/m1.stl', 'STL')"""
        )
        model_id = cursor.lastrowid

        cursor = await conn.execute("INSERT INTO tags (name) VALUES ('red')")
        tag_id = cursor.lastrowid

        await conn.execute(
            "INSERT INTO model_tags (model_id, tag_id) VALUES (?, ?)",
            (model_id, tag_id),
        )
        await conn.commit()

        # Delete the model
        await conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
        await conn.commit()

        # Verify model_tags entry is gone
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM model_tags WHERE model_id = ?", (model_id,)
        )
        row = await cursor.fetchone()
    assert row[0] == 0
