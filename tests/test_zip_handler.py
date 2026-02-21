"""Tests for app.services.zip_handler utility functions."""

import os
import zipfile

import pytest

from app.services.zip_handler import (
    cleanup_zip_cache,
    ensure_cached,
    extract_entry_to_temp,
    is_zip_file,
    list_models_in_zip,
    make_zip_file_path,
)
from tests.conftest import create_test_zip

SUPPORTED = {".stl", ".obj", ".gltf", ".glb", ".3mf", ".ply", ".dae", ".off"}


class TestIsZipFile:
    def test_valid_zip(self, tmp_path):
        zp = tmp_path / "test.zip"
        create_test_zip(zp, create_stl_entries=["model.stl"])
        assert is_zip_file(str(zp)) is True

    def test_not_a_zip(self, tmp_path):
        f = tmp_path / "notzip.txt"
        f.write_text("hello")
        assert is_zip_file(str(f)) is False

    def test_nonexistent_file(self, tmp_path):
        assert is_zip_file(str(tmp_path / "missing.zip")) is False


class TestListModelsInZip:
    def test_finds_stl_files(self, tmp_path):
        zp = tmp_path / "models.zip"
        create_test_zip(zp, create_stl_entries=["cube.stl", "sphere.stl"])
        entries = list_models_in_zip(str(zp), SUPPORTED)
        assert sorted(entries) == ["cube.stl", "sphere.stl"]

    def test_finds_nested_entries(self, tmp_path):
        zp = tmp_path / "nested.zip"
        create_test_zip(zp, create_stl_entries=["Models/sub/dragon.stl"])
        entries = list_models_in_zip(str(zp), SUPPORTED)
        assert entries == ["Models/sub/dragon.stl"]

    def test_skips_non_model_files(self, tmp_path):
        zp = tmp_path / "mixed.zip"
        create_test_zip(
            zp,
            entries={
                "model.stl": None,
                "readme.txt": b"hello",
                "image.png": b"\x89PNG",
            },
        )
        entries = list_models_in_zip(str(zp), SUPPORTED)
        assert entries == ["model.stl"]

    def test_skips_macosx_entries(self, tmp_path):
        zp = tmp_path / "macos.zip"
        create_test_zip(
            zp,
            entries={
                "model.stl": None,
                "__MACOSX/._model.stl": b"resource fork",
            },
        )
        entries = list_models_in_zip(str(zp), SUPPORTED)
        assert entries == ["model.stl"]

    def test_skips_hidden_files(self, tmp_path):
        zp = tmp_path / "hidden.zip"
        create_test_zip(
            zp,
            entries={
                "model.stl": None,
                ".hidden.stl": None,
            },
        )
        entries = list_models_in_zip(str(zp), SUPPORTED)
        assert entries == ["model.stl"]

    def test_corrupt_zip_returns_empty(self, tmp_path):
        zp = tmp_path / "corrupt.zip"
        zp.write_bytes(b"not a zip file at all")
        entries = list_models_in_zip(str(zp), SUPPORTED)
        assert entries == []

    def test_empty_zip(self, tmp_path):
        zp = tmp_path / "empty.zip"
        with zipfile.ZipFile(zp, "w"):
            pass
        entries = list_models_in_zip(str(zp), SUPPORTED)
        assert entries == []

    def test_multiple_formats(self, tmp_path):
        zp = tmp_path / "multi.zip"
        create_test_zip(
            zp,
            entries={
                "a.stl": None,
                "b.obj": b"# OBJ file",
                "c.glb": b"\x00" * 10,
            },
        )
        entries = list_models_in_zip(str(zp), SUPPORTED)
        assert sorted(entries) == ["a.stl", "b.obj", "c.glb"]


class TestExtractEntryToTemp:
    def test_extracts_to_temp(self, tmp_path):
        zp = tmp_path / "test.zip"
        create_test_zip(zp, create_stl_entries=["cube.stl"])
        tmp_file = extract_entry_to_temp(str(zp), "cube.stl")
        try:
            assert tmp_file.exists()
            assert tmp_file.suffix == ".stl"
            assert tmp_file.stat().st_size > 0
        finally:
            tmp_file.unlink()

    def test_preserves_extension(self, tmp_path):
        zp = tmp_path / "test.zip"
        create_test_zip(zp, entries={"model.obj": b"# OBJ"})
        tmp_file = extract_entry_to_temp(str(zp), "model.obj")
        try:
            assert tmp_file.suffix == ".obj"
        finally:
            tmp_file.unlink()

    def test_missing_entry_raises(self, tmp_path):
        zp = tmp_path / "test.zip"
        create_test_zip(zp, create_stl_entries=["cube.stl"])
        with pytest.raises(KeyError):
            extract_entry_to_temp(str(zp), "nonexistent.stl")

    def test_corrupt_zip_raises(self, tmp_path):
        zp = tmp_path / "corrupt.zip"
        zp.write_bytes(b"not a zip")
        with pytest.raises(zipfile.BadZipFile):
            extract_entry_to_temp(str(zp), "anything.stl")


class TestEnsureCached:
    def test_creates_cache_on_first_call(self, tmp_path):
        zp = tmp_path / "test.zip"
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        create_test_zip(zp, create_stl_entries=["cube.stl"])

        path = ensure_cached(str(zp), "cube.stl", str(cache_dir), model_id=42)
        assert os.path.exists(path)
        assert path.endswith(".stl")
        assert "42" in os.path.basename(path)

    def test_returns_cached_on_second_call(self, tmp_path):
        zp = tmp_path / "test.zip"
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        create_test_zip(zp, create_stl_entries=["cube.stl"])

        path1 = ensure_cached(str(zp), "cube.stl", str(cache_dir), model_id=42)
        mtime1 = os.path.getmtime(path1)

        # Second call should return same path without re-extracting
        path2 = ensure_cached(str(zp), "cube.stl", str(cache_dir), model_id=42)
        mtime2 = os.path.getmtime(path2)

        assert path1 == path2
        assert mtime1 == mtime2

    def test_re_extracts_when_zip_updated(self, tmp_path):
        zp = tmp_path / "test.zip"
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        create_test_zip(zp, create_stl_entries=["cube.stl"])

        path1 = ensure_cached(str(zp), "cube.stl", str(cache_dir), model_id=42)

        # Touch the zip to simulate modification (make it newer than cache)
        import time

        time.sleep(0.1)
        os.utime(str(zp), None)

        path2 = ensure_cached(str(zp), "cube.stl", str(cache_dir), model_id=42)
        assert path1 == path2  # Same path but re-extracted


class TestCleanupZipCache:
    def test_removes_cached_file(self, tmp_path):
        cache_dir = tmp_path / "cache"
        zip_cache = cache_dir / "zip_cache"
        zip_cache.mkdir(parents=True)

        cached_file = zip_cache / "42.stl"
        cached_file.write_bytes(b"test data")
        assert cached_file.exists()

        cleanup_zip_cache(str(cache_dir), 42, ".stl")
        assert not cached_file.exists()

    def test_no_error_when_missing(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        # Should not raise
        cleanup_zip_cache(str(cache_dir), 999, ".stl")

    def test_removes_without_ext(self, tmp_path):
        cache_dir = tmp_path / "cache"
        zip_cache = cache_dir / "zip_cache"
        zip_cache.mkdir(parents=True)

        cached_file = zip_cache / "42.stl"
        cached_file.write_bytes(b"test data")

        cleanup_zip_cache(str(cache_dir), 42)
        assert not cached_file.exists()


class TestMakeZipFilePath:
    def test_format(self):
        result = make_zip_file_path("/path/to/archive.zip", "Models/dragon.stl")
        assert result == "/path/to/archive.zip::Models/dragon.stl"

    def test_simple_entry(self):
        result = make_zip_file_path("/data/models.zip", "cube.stl")
        assert result == "/data/models.zip::cube.stl"
