"""Tests for app.services.scanner move detection and missing file tracking."""

import shutil

import aiosqlite
import pytest
import pytest_asyncio

from app.database import init_db
from app.services.scanner import Scanner
from tests.conftest import _create_test_stl


SUPPORTED_EXTENSIONS = {".stl"}


@pytest.fixture
def library_dir(tmp_path):
    """Create a temporary library directory."""
    d = tmp_path / "library"
    d.mkdir()
    return d


@pytest.fixture
def thumb_dir(tmp_path):
    """Create a temporary thumbnail directory."""
    d = tmp_path / "thumbnails"
    d.mkdir()
    return d


@pytest_asyncio.fixture
async def scanner_env(tmp_path, library_dir, thumb_dir):
    """Set up a scanner with an initialised DB and registered library.

    Yields (scanner, db_path, library_dir, library_id).
    """
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)

    # Register a library
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "INSERT INTO libraries (name, path) VALUES (?, ?)",
            ("test-lib", str(library_dir)),
        )
        library_id = cursor.lastrowid
        await db.commit()

    scanner = Scanner(
        db_path=db_path,
        thumbnail_path=str(thumb_dir),
        supported_extensions=SUPPORTED_EXTENSIONS,
    )
    yield scanner, db_path, library_dir, library_id


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _get_model_by_id(db_path: str, model_id: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM models WHERE id = ?", (model_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def _get_all_models(db_path: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM models ORDER BY id")
        return [dict(r) for r in await cursor.fetchall()]


async def _get_model_tag_names(db_path: str, model_id: int) -> list[str]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT t.name FROM tags t
            JOIN model_tags mt ON mt.tag_id = t.id
            WHERE mt.model_id = ?
            ORDER BY t.name
            """,
            (model_id,),
        )
        return [dict(r)["name"] for r in await cursor.fetchall()]


async def _get_model_category_names(db_path: str, model_id: int) -> list[str]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT c.name FROM categories c
            JOIN model_categories mc ON mc.category_id = c.id
            WHERE mc.model_id = ?
            ORDER BY c.name
            """,
            (model_id,),
        )
        return [dict(r)["name"] for r in await cursor.fetchall()]


async def _add_tag_to_model(db_path: str, model_id: int, tag_name: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
        tag_id = cursor.lastrowid
        await db.execute(
            "INSERT INTO model_tags (model_id, tag_id) VALUES (?, ?)",
            (model_id, tag_id),
        )
        await db.commit()


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
class TestScannerMoveDetection:
    async def test_scan_detects_moved_file(self, scanner_env):
        """Moving a file to a new path should update the existing record."""
        scanner, db_path, library_dir, _ = scanner_env

        # Create and index a file
        stl = library_dir / "dragon.stl"
        _create_test_stl(stl)
        stats = await scanner.scan()
        assert stats["new_files"] == 1

        models = await _get_all_models(db_path)
        assert len(models) == 1
        original_id = models[0]["id"]

        # Move the file to a subdirectory
        subdir = library_dir / "Animals"
        subdir.mkdir()
        dest = subdir / "dragon.stl"
        shutil.move(str(stl), str(dest))

        # Re-scan
        stats = await scanner.scan()
        assert stats["moved_files"] == 1
        assert stats["new_files"] == 0
        assert stats["missing_files"] == 0

        # Same model ID, updated path
        model = await _get_model_by_id(db_path, original_id)
        assert model is not None
        assert model["file_path"] == str(dest)
        assert model["status"] == "active"

        # No duplicate records
        all_models = await _get_all_models(db_path)
        assert len(all_models) == 1

    async def test_scan_moved_preserves_tags(self, scanner_env):
        """Tags should be preserved when a file is moved."""
        scanner, db_path, library_dir, _ = scanner_env

        stl = library_dir / "cube.stl"
        _create_test_stl(stl)
        await scanner.scan()

        models = await _get_all_models(db_path)
        model_id = models[0]["id"]

        # Add tags
        await _add_tag_to_model(db_path, model_id, "printable")
        await _add_tag_to_model(db_path, model_id, "geometric")

        # Move file
        dest = library_dir / "cube_renamed.stl"
        shutil.move(str(stl), str(dest))

        await scanner.scan()

        # Tags still attached to the same model
        tags = await _get_model_tag_names(db_path, model_id)
        assert "printable" in tags
        assert "geometric" in tags

    async def test_scan_moved_updates_categories(self, scanner_env):
        """Categories should be updated to reflect the new directory."""
        scanner, db_path, library_dir, _ = scanner_env

        # Create file in Animals/
        animals_dir = library_dir / "Animals"
        animals_dir.mkdir()
        stl = animals_dir / "dragon.stl"
        _create_test_stl(stl)
        await scanner.scan()

        models = await _get_all_models(db_path)
        model_id = models[0]["id"]
        cats = await _get_model_category_names(db_path, model_id)
        assert "Animals" in cats

        # Move to Vehicles/
        vehicles_dir = library_dir / "Vehicles"
        vehicles_dir.mkdir()
        dest = vehicles_dir / "dragon.stl"
        shutil.move(str(stl), str(dest))

        await scanner.scan()

        # Categories should now reflect Vehicles, not Animals
        cats = await _get_model_category_names(db_path, model_id)
        assert "Vehicles" in cats
        assert "Animals" not in cats

    async def test_scan_moved_updates_name(self, scanner_env):
        """The model name should update when the file is renamed."""
        scanner, db_path, library_dir, _ = scanner_env

        stl = library_dir / "old_name.stl"
        _create_test_stl(stl)
        await scanner.scan()

        models = await _get_all_models(db_path)
        model_id = models[0]["id"]
        assert models[0]["name"] == "old_name"

        dest = library_dir / "new_name.stl"
        shutil.move(str(stl), str(dest))

        await scanner.scan()

        model = await _get_model_by_id(db_path, model_id)
        assert model["name"] == "new_name"


@pytest.mark.asyncio
class TestScannerMissingFiles:
    async def test_scan_marks_missing_file(self, scanner_env):
        """Deleting a file should mark the record as missing, not delete it."""
        scanner, db_path, library_dir, _ = scanner_env

        stl = library_dir / "dragon.stl"
        _create_test_stl(stl)
        await scanner.scan()

        models = await _get_all_models(db_path)
        model_id = models[0]["id"]

        # Delete the file
        stl.unlink()

        stats = await scanner.scan()
        assert stats["missing_files"] == 1

        # Record still exists but is marked missing
        model = await _get_model_by_id(db_path, model_id)
        assert model is not None
        assert model["status"] == "missing"

    async def test_scan_missing_preserves_tags(self, scanner_env):
        """Tags should be preserved when a file is marked missing."""
        scanner, db_path, library_dir, _ = scanner_env

        stl = library_dir / "cube.stl"
        _create_test_stl(stl)
        await scanner.scan()

        models = await _get_all_models(db_path)
        model_id = models[0]["id"]
        await _add_tag_to_model(db_path, model_id, "favorite")

        stl.unlink()
        await scanner.scan()

        tags = await _get_model_tag_names(db_path, model_id)
        assert "favorite" in tags

    async def test_scan_reactivates_missing_file(self, scanner_env):
        """Restoring a file at its original path should reactivate it."""
        scanner, db_path, library_dir, _ = scanner_env

        stl = library_dir / "dragon.stl"
        _create_test_stl(stl)
        await scanner.scan()

        models = await _get_all_models(db_path)
        model_id = models[0]["id"]

        # Delete -> missing
        stl.unlink()
        await scanner.scan()
        model = await _get_model_by_id(db_path, model_id)
        assert model["status"] == "missing"

        # Restore the file
        _create_test_stl(stl)
        stats = await scanner.scan()
        assert stats["reactivated_files"] == 1

        model = await _get_model_by_id(db_path, model_id)
        assert model["status"] == "active"


@pytest.mark.asyncio
class TestScannerNewFiles:
    async def test_scan_new_file_no_orphan_match(self, scanner_env):
        """A genuinely new file should be inserted normally."""
        scanner, db_path, library_dir, _ = scanner_env

        stl = library_dir / "new_model.stl"
        _create_test_stl(stl)

        stats = await scanner.scan()
        assert stats["new_files"] == 1
        assert stats["moved_files"] == 0

        models = await _get_all_models(db_path)
        assert len(models) == 1
        assert models[0]["status"] == "active"

    async def test_scan_skips_existing_file(self, scanner_env):
        """An already-indexed file at the same path should be skipped."""
        scanner, db_path, library_dir, _ = scanner_env

        stl = library_dir / "model.stl"
        _create_test_stl(stl)

        stats1 = await scanner.scan()
        assert stats1["new_files"] == 1

        stats2 = await scanner.scan()
        assert stats2["new_files"] == 0
        assert stats2["skipped_files"] == 1

    async def test_scan_ambiguous_hash(self, scanner_env):
        """When multiple orphans share a hash, moves should still work."""
        scanner, db_path, library_dir, _ = scanner_env

        # Create two identical files
        stl_a = library_dir / "copy_a.stl"
        _create_test_stl(stl_a)
        stl_b = library_dir / "copy_b.stl"
        shutil.copy2(str(stl_a), str(stl_b))

        await scanner.scan()
        models_before = await _get_all_models(db_path)
        assert len(models_before) == 2

        # Move both files to new names
        dest_a = library_dir / "renamed_a.stl"
        dest_b = library_dir / "renamed_b.stl"
        shutil.move(str(stl_a), str(dest_a))
        shutil.move(str(stl_b), str(dest_b))

        stats = await scanner.scan()
        assert stats["moved_files"] == 2
        assert stats["missing_files"] == 0
        assert stats["new_files"] == 0

        # Should still have exactly 2 models
        models_after = await _get_all_models(db_path)
        assert len(models_after) == 2
        # Same IDs
        assert {m["id"] for m in models_after} == {m["id"] for m in models_before}
