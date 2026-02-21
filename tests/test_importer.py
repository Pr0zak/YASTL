"""Tests for app.services.importer — main import pipeline."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.importer import (
    _parse_attribution,
    extract_zip_metadata,
    get_import_progress,
    import_from_url,
    import_urls_batch,
    process_imported_file,
)
from tests.conftest import _create_test_stl, create_test_zip


# ---------------------------------------------------------------------------
# extract_zip_metadata()
# ---------------------------------------------------------------------------


class TestExtractZipMetadata:
    """Tests for extract_zip_metadata() — zip file metadata parsing."""

    def test_thingiverse_pattern_with_files_suffix(self, tmp_path):
        """Detect Thingiverse zips like 'Model_Name_12345_files.zip'."""
        zip_path = tmp_path / "Cool_Benchy_67890_files.zip"
        create_test_zip(zip_path, create_stl_entries=["benchy.stl"])

        meta = extract_zip_metadata(zip_path)
        assert meta["source_url"] == "https://www.thingiverse.com/thing:67890"
        assert meta["site"] == "thingiverse"
        assert meta["title"] == "Cool_Benchy"
        assert "benchy.stl" in meta["model_files"]

    def test_thingiverse_pattern_without_files_suffix(self, tmp_path):
        """Detect Thingiverse zips like 'Model_Name_12345.zip'."""
        zip_path = tmp_path / "Dragon_99999.zip"
        create_test_zip(zip_path, create_stl_entries=["dragon.stl"])

        meta = extract_zip_metadata(zip_path)
        assert meta["source_url"] == "https://www.thingiverse.com/thing:99999"
        assert meta["site"] == "thingiverse"
        assert meta["title"] == "Dragon"

    def test_thingiverse_pattern_with_spaces_and_dashes(self, tmp_path):
        """Detect Thingiverse zips like 'Model Name - 12345.zip'."""
        zip_path = tmp_path / "Cool Model - 54321.zip"
        create_test_zip(zip_path, create_stl_entries=["model.stl"])

        meta = extract_zip_metadata(zip_path)
        assert meta["source_url"] == "https://www.thingiverse.com/thing:54321"
        assert meta["site"] == "thingiverse"
        assert meta["title"] == "Cool Model"

    def test_generic_zip_with_model_files(self, tmp_path):
        """Non-Thingiverse zip with model files should list them."""
        zip_path = tmp_path / "my_models.zip"
        create_test_zip(
            zip_path,
            create_stl_entries=["part1.stl", "part2.obj"],
        )

        meta = extract_zip_metadata(zip_path)
        assert meta["source_url"] is None
        assert meta["site"] is None
        assert "part1.stl" in meta["model_files"]
        assert "part2.obj" in meta["model_files"]
        # Title derived from zip name
        assert meta["title"] == "my models"

    def test_empty_zip(self, tmp_path):
        """Empty zip should return empty model_files and a fallback title."""
        zip_path = tmp_path / "empty.zip"
        create_test_zip(zip_path)

        meta = extract_zip_metadata(zip_path)
        assert meta["model_files"] == []
        assert meta["title"] == "empty"

    def test_zip_with_no_model_files(self, tmp_path):
        """Zip with only non-model files should return empty model_files."""
        zip_path = tmp_path / "docs_only.zip"
        create_test_zip(zip_path, entries={"readme.txt": b"Hello", "notes.pdf": b"PDF"})

        meta = extract_zip_metadata(zip_path)
        assert meta["model_files"] == []
        assert meta["title"] is not None

    def test_zip_with_attribution_file(self, tmp_path):
        """Zip containing attribution.txt should parse it for metadata."""
        attr_text = (
            "Title: My Cool Dragon\n"
            "URL: https://www.thingiverse.com/thing:11111\n"
            "Tags: dragon, fantasy, miniature\n"
            "Creator: bob\n"
        )
        zip_path = tmp_path / "some_model.zip"
        create_test_zip(
            zip_path,
            entries={
                "attribution.txt": attr_text.encode("utf-8"),
                "dragon.stl": None,  # auto-generates STL bytes
            },
        )

        meta = extract_zip_metadata(zip_path)
        assert meta["title"] == "My Cool Dragon"
        assert meta["source_url"] == "https://www.thingiverse.com/thing:11111"
        assert "dragon" in meta["tags"]
        assert "fantasy" in meta["tags"]
        assert "miniature" in meta["tags"]
        # Creator name gets added as a tag
        assert "bob" in meta["tags"]

    def test_macosx_resource_forks_skipped(self, tmp_path):
        """Files under __MACOSX/ should be ignored."""
        zip_path = tmp_path / "with_macosx.zip"
        create_test_zip(
            zip_path,
            entries={
                "model.stl": None,
                "__MACOSX/._model.stl": b"resource fork",
            },
        )

        meta = extract_zip_metadata(zip_path)
        assert len(meta["model_files"]) == 1
        assert "model.stl" in meta["model_files"]

    def test_hidden_files_skipped(self, tmp_path):
        """Files starting with a dot should be ignored."""
        zip_path = tmp_path / "with_hidden.zip"
        create_test_zip(
            zip_path,
            entries={
                "model.stl": None,
                ".DS_Store": b"apple",
            },
        )

        meta = extract_zip_metadata(zip_path)
        assert len(meta["model_files"]) == 1

    def test_corrupt_zip_handled_gracefully(self, tmp_path):
        """Corrupt zip should not raise, should return empty model_files."""
        zip_path = tmp_path / "corrupt.zip"
        zip_path.write_bytes(b"this is not a zip file")

        meta = extract_zip_metadata(zip_path)
        assert meta["model_files"] == []

    def test_nested_directory_model_files(self, tmp_path):
        """Model files in subdirectories should be detected."""
        zip_path = tmp_path / "nested.zip"
        create_test_zip(
            zip_path,
            entries={
                "models/part1.stl": None,
                "models/subdir/part2.obj": None,
            },
        )

        meta = extract_zip_metadata(zip_path)
        assert "models/part1.stl" in meta["model_files"]
        assert "models/subdir/part2.obj" in meta["model_files"]

    def test_all_supported_extensions(self, tmp_path):
        """Various 3D model extensions should be detected."""
        entries = {}
        for ext in [".stl", ".obj", ".gltf", ".glb", ".3mf", ".ply", ".dae", ".off", ".step", ".stp", ".fbx"]:
            entries[f"model{ext}"] = None
        zip_path = tmp_path / "all_formats.zip"
        create_test_zip(zip_path, entries=entries)

        meta = extract_zip_metadata(zip_path)
        assert len(meta["model_files"]) == 11


# ---------------------------------------------------------------------------
# _parse_attribution()
# ---------------------------------------------------------------------------


class TestParseAttribution:
    """Tests for _parse_attribution() — attribution text parsing."""

    def test_standard_thingiverse_format(self):
        """Parse standard Thingiverse attribution with Key: Value lines."""
        meta = {
            "title": None,
            "source_url": None,
            "tags": [],
            "model_files": [],
            "site": None,
        }
        text = (
            "Title: Cool Model\n"
            "URL: https://www.thingiverse.com/thing:12345\n"
            "Tags: pla, support-free, miniature\n"
            "Creator: artist123\n"
        )
        _parse_attribution(text, meta)

        assert meta["title"] == "Cool Model"
        assert meta["source_url"] == "https://www.thingiverse.com/thing:12345"
        assert meta["site"] == "thingiverse"
        assert "pla" in meta["tags"]
        assert "support-free" in meta["tags"]
        assert "miniature" in meta["tags"]
        # Creator appended as tag
        assert "artist123" in meta["tags"]

    def test_readme_format(self):
        """Parse 'Title by Creator on Thingiverse: URL' format."""
        meta = {
            "title": None,
            "source_url": None,
            "tags": [],
            "model_files": [],
            "site": None,
        }
        text = "Cool Dragon by artist42 on Thingiverse: https://www.thingiverse.com/thing:99999\n"
        _parse_attribution(text, meta)

        assert meta["title"] == "Cool Dragon"
        assert meta["source_url"] == "https://www.thingiverse.com/thing:99999"
        assert meta["site"] == "thingiverse"
        assert meta.get("creator") == "artist42"

    def test_embedded_thingiverse_url(self):
        """Detect embedded Thingiverse URLs in free text."""
        meta = {
            "title": None,
            "source_url": None,
            "tags": [],
            "model_files": [],
            "site": None,
        }
        text = "Check out this model at https://www.thingiverse.com/thing:55555 for details\n"
        _parse_attribution(text, meta)

        assert meta["source_url"] == "https://www.thingiverse.com/thing:55555"
        assert meta["site"] == "thingiverse"

    def test_embedded_printables_url(self):
        """Detect embedded Printables URLs in free text."""
        meta = {
            "title": None,
            "source_url": None,
            "tags": [],
            "model_files": [],
            "site": None,
        }
        text = "Source: https://www.printables.com/model/12345\n"
        _parse_attribution(text, meta)

        assert meta["source_url"] == "https://www.printables.com/model/12345"
        assert meta["site"] == "printables"

    def test_embedded_makerworld_url(self):
        """Detect embedded MakerWorld URLs in free text."""
        meta = {
            "title": None,
            "source_url": None,
            "tags": [],
            "model_files": [],
            "site": None,
        }
        text = "Download from https://www.makerworld.com/en/models/12345\n"
        _parse_attribution(text, meta)

        assert meta["source_url"] == "https://www.makerworld.com/en/models/12345"
        assert meta["site"] == "makerworld"

    def test_html_tags_stripped(self):
        """HTML tags should be stripped before parsing."""
        meta = {
            "title": None,
            "source_url": None,
            "tags": [],
            "model_files": [],
            "site": None,
        }
        text = "<p>Title: <b>HTML Model</b></p>\n"
        _parse_attribution(text, meta)

        assert meta["title"] == "HTML Model"

    def test_missing_fields(self):
        """Missing fields should leave meta values unchanged."""
        meta = {
            "title": None,
            "source_url": None,
            "tags": [],
            "model_files": [],
            "site": None,
        }
        text = "Some random text with no structured data.\n"
        _parse_attribution(text, meta)

        assert meta["title"] is None
        assert meta["source_url"] is None

    def test_empty_input(self):
        """Empty text should leave meta unchanged."""
        meta = {
            "title": None,
            "source_url": None,
            "tags": [],
            "model_files": [],
            "site": None,
        }
        _parse_attribution("", meta)

        assert meta["title"] is None
        assert meta["source_url"] is None
        assert meta["tags"] == []

    def test_does_not_overwrite_existing_title(self):
        """If meta already has a title, it should not be overwritten."""
        meta = {
            "title": "Existing Title",
            "source_url": None,
            "tags": [],
            "model_files": [],
            "site": None,
        }
        text = "Title: New Title\n"
        _parse_attribution(text, meta)

        assert meta["title"] == "Existing Title"

    def test_does_not_overwrite_existing_url(self):
        """If meta already has a source_url, it should not be overwritten."""
        meta = {
            "title": None,
            "source_url": "https://existing.com",
            "tags": [],
            "model_files": [],
            "site": None,
        }
        text = "URL: https://www.thingiverse.com/thing:12345\n"
        _parse_attribution(text, meta)

        assert meta["source_url"] == "https://existing.com"

    def test_printables_url_key_value(self):
        """Printables URL in key:value format should set site correctly."""
        meta = {
            "title": None,
            "source_url": None,
            "tags": [],
            "model_files": [],
            "site": None,
        }
        text = "URL: https://www.printables.com/model/999-widget\n"
        _parse_attribution(text, meta)

        assert meta["source_url"] == "https://www.printables.com/model/999-widget"
        assert meta["site"] == "printables"

    def test_tags_accumulate(self):
        """Multiple tag lines should accumulate, not replace."""
        meta = {
            "title": None,
            "source_url": None,
            "tags": ["existing"],
            "model_files": [],
            "site": None,
        }
        text = "Tags: new1, new2\n"
        _parse_attribution(text, meta)

        assert "existing" in meta["tags"]
        assert "new1" in meta["tags"]
        assert "new2" in meta["tags"]


# ---------------------------------------------------------------------------
# process_imported_file() — with mocked dependencies
# ---------------------------------------------------------------------------


class TestProcessImportedFile:
    """Tests for process_imported_file() with mocked DB and services."""

    def _make_mock_db(self, duplicate=False):
        """Create a mock async DB connection and context manager."""
        mock_cursor = AsyncMock()
        if duplicate:
            mock_cursor.fetchone = AsyncMock(return_value={"id": 99})
        else:
            mock_cursor.fetchone = AsyncMock(return_value=None)
        mock_cursor.lastrowid = 42

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_cursor)
        mock_db.commit = AsyncMock()

        return mock_db

    @pytest.fixture
    def stl_file(self, tmp_path):
        """Create a minimal STL file for testing."""
        path = tmp_path / "test_model.stl"
        _create_test_stl(path)
        return path

    async def test_process_valid_model_file(self, stl_file, tmp_path):
        """A valid model file should be processed and inserted into the DB."""
        mock_db = self._make_mock_db(duplicate=False)

        mock_metadata = {
            "file_format": "STL",
            "file_size": 134,
            "vertex_count": 3,
            "face_count": 1,
            "dimensions_x": 1.0,
            "dimensions_y": 1.0,
            "dimensions_z": 0.0,
        }

        with (
            patch("app.services.importer.get_db") as mock_get_db,
            patch("app.services.importer.processor") as mock_processor,
            patch("app.services.importer.hasher") as mock_hasher,
            patch("app.services.importer.thumbnail") as mock_thumbnail,
            patch("app.services.importer.get_setting", new_callable=AsyncMock) as mock_get_setting,
            patch("app.services.importer.update_fts_for_model", new_callable=AsyncMock),
            patch("app.config.settings") as mock_settings,
        ):
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_processor.extract_metadata.return_value = mock_metadata
            mock_processor.TRIMESH_SUPPORTED = {".stl", ".obj", ".glb"}
            mock_processor.FALLBACK_ONLY = {".step", ".stp"}
            mock_hasher.compute_file_hash.return_value = "abcdef123456"
            mock_thumbnail.generate_thumbnail.return_value = "thumb_42.png"
            mock_get_setting.return_value = "wireframe"
            mock_settings.MODEL_LIBRARY_THUMBNAIL_PATH = tmp_path / "thumbs"

            result = await process_imported_file(
                file_path=stl_file,
                library_id=1,
                source_url="https://example.com/model",
            )

        assert result == 42
        # Verify DB insert was called
        assert mock_db.execute.call_count >= 2  # SELECT + INSERT at minimum
        mock_db.commit.assert_called_once()

    async def test_process_duplicate_file(self, stl_file, tmp_path):
        """Duplicate file (already in DB) should return None."""
        mock_db = self._make_mock_db(duplicate=True)

        mock_metadata = {"file_format": "STL", "file_size": 134}

        with (
            patch("app.services.importer.get_db") as mock_get_db,
            patch("app.services.importer.processor") as mock_processor,
            patch("app.services.importer.hasher") as mock_hasher,
            patch("app.services.importer.get_setting", new_callable=AsyncMock),
            patch("app.services.importer.update_fts_for_model", new_callable=AsyncMock),
            patch("app.config.settings") as mock_settings,
        ):
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_processor.extract_metadata.return_value = mock_metadata
            mock_processor.TRIMESH_SUPPORTED = {".stl", ".obj", ".glb"}
            mock_processor.FALLBACK_ONLY = {".step", ".stp"}
            mock_hasher.compute_file_hash.return_value = "abcdef123456"
            mock_settings.MODEL_LIBRARY_THUMBNAIL_PATH = tmp_path / "thumbs"

            result = await process_imported_file(
                file_path=stl_file,
                library_id=1,
            )

        assert result is None

    async def test_process_unsupported_extension(self, tmp_path):
        """Unsupported file extensions should return None immediately."""
        bad_file = tmp_path / "model.txt"
        bad_file.write_text("not a model")

        with (
            patch("app.services.importer.processor") as mock_processor,
        ):
            mock_processor.TRIMESH_SUPPORTED = {".stl", ".obj", ".glb"}
            mock_processor.FALLBACK_ONLY = {".step", ".stp"}

            result = await process_imported_file(
                file_path=bad_file,
                library_id=1,
            )

        assert result is None

    async def test_process_zip_file_returns_none(self, tmp_path):
        """Zip files should be skipped (handled by scanner)."""
        zip_file = tmp_path / "archive.zip"
        create_test_zip(zip_file, create_stl_entries=["model.stl"])

        result = await process_imported_file(
            file_path=zip_file,
            library_id=1,
        )

        assert result is None

    async def test_process_with_tags(self, stl_file, tmp_path):
        """Scraped tags should be inserted into the DB."""
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(side_effect=[
            None,       # First: duplicate check returns None (no duplicate)
            None,       # Second: tag SELECT - not found initially
            {"id": 10}, # Third: tag SELECT after INSERT - tag found
            None,       # Fourth: tag SELECT
            {"id": 11}, # Fifth: tag SELECT after INSERT
        ])
        mock_cursor.lastrowid = 42

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_cursor)
        mock_db.commit = AsyncMock()

        mock_metadata = {
            "file_format": "STL",
            "file_size": 134,
            "vertex_count": 3,
            "face_count": 1,
        }

        with (
            patch("app.services.importer.get_db") as mock_get_db,
            patch("app.services.importer.processor") as mock_processor,
            patch("app.services.importer.hasher") as mock_hasher,
            patch("app.services.importer.thumbnail") as mock_thumbnail,
            patch("app.services.importer.get_setting", new_callable=AsyncMock) as mock_get_setting,
            patch("app.services.importer.update_fts_for_model", new_callable=AsyncMock),
            patch("app.config.settings") as mock_settings,
        ):
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_processor.extract_metadata.return_value = mock_metadata
            mock_processor.TRIMESH_SUPPORTED = {".stl", ".obj", ".glb"}
            mock_processor.FALLBACK_ONLY = {".step", ".stp"}
            mock_hasher.compute_file_hash.return_value = "hash123"
            mock_thumbnail.generate_thumbnail.return_value = None
            mock_get_setting.return_value = "wireframe"
            mock_settings.MODEL_LIBRARY_THUMBNAIL_PATH = tmp_path / "thumbs"

            result = await process_imported_file(
                file_path=stl_file,
                library_id=1,
                scraped_tags=["pla", "dragon"],
            )

        assert result == 42
        # Tag INSERT OR IGNORE should have been called for both tags
        tag_insert_calls = [
            c for c in mock_db.execute.call_args_list
            if c.args and isinstance(c.args[0], str) and "INSERT OR IGNORE INTO tags" in c.args[0]
        ]
        assert len(tag_insert_calls) == 2

    async def test_process_uses_scraped_title(self, stl_file, tmp_path):
        """When scraped_title is given, it should be used as model name."""
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)
        mock_cursor.lastrowid = 42

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_cursor)
        mock_db.commit = AsyncMock()

        mock_metadata = {"file_format": "STL", "file_size": 134}

        with (
            patch("app.services.importer.get_db") as mock_get_db,
            patch("app.services.importer.processor") as mock_processor,
            patch("app.services.importer.hasher") as mock_hasher,
            patch("app.services.importer.thumbnail") as mock_thumbnail,
            patch("app.services.importer.get_setting", new_callable=AsyncMock) as mock_get_setting,
            patch("app.services.importer.update_fts_for_model", new_callable=AsyncMock),
            patch("app.config.settings") as mock_settings,
        ):
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_processor.extract_metadata.return_value = mock_metadata
            mock_processor.TRIMESH_SUPPORTED = {".stl"}
            mock_processor.FALLBACK_ONLY = set()
            mock_hasher.compute_file_hash.return_value = "hash456"
            mock_thumbnail.generate_thumbnail.return_value = None
            mock_get_setting.return_value = "wireframe"
            mock_settings.MODEL_LIBRARY_THUMBNAIL_PATH = tmp_path / "thumbs"

            result = await process_imported_file(
                file_path=stl_file,
                library_id=1,
                scraped_title="Cool Benchy Print",
            )

        assert result == 42
        # Check that the INSERT used the scraped title
        insert_calls = [
            c for c in mock_db.execute.call_args_list
            if c.args and isinstance(c.args[0], str) and "INSERT INTO models" in c.args[0]
        ]
        assert len(insert_calls) == 1
        args_tuple = insert_calls[0].args[1]
        assert args_tuple[0] == "Cool Benchy Print"  # name is first param


# ---------------------------------------------------------------------------
# import_from_url() — with mocked HTTP
# ---------------------------------------------------------------------------


class TestImportFromUrl:
    """Tests for import_from_url() with mocked scraping and download."""

    async def test_successful_import(self, tmp_path):
        """Successful URL import should return ok status and model IDs."""
        dest_dir = tmp_path / "library"
        dest_dir.mkdir()

        stl_file = dest_dir / "model.stl"
        _create_test_stl(stl_file)

        mock_meta = {
            "title": "Test Model",
            "tags": ["pla"],
            "download_urls": ["https://example.com/model.stl"],
            "error": None,
        }

        with (
            patch("app.services.importer.scrape_metadata", new_callable=AsyncMock) as mock_scrape,
            patch("app.services.importer.download_file", new_callable=AsyncMock) as mock_download,
            patch("app.services.importer.process_imported_file", new_callable=AsyncMock) as mock_process,
            patch("app.services.importer.httpx") as mock_httpx,
        ):
            mock_scrape.return_value = mock_meta
            mock_download.return_value = stl_file
            mock_process.return_value = 42

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await import_from_url(
                url="https://example.com/models/123",
                library_id=1,
                library_path=str(dest_dir),
            )

        assert result["status"] == "ok"
        assert 42 in result["models"]

    async def test_scraping_failure(self, tmp_path):
        """When scraping raises an exception, result should be error."""
        with patch(
            "app.services.importer.scrape_metadata",
            new_callable=AsyncMock,
            side_effect=Exception("Scrape failed"),
        ):
            result = await import_from_url(
                url="https://example.com/bad",
                library_id=1,
                library_path=str(tmp_path),
            )

        assert result["status"] == "error"
        assert "Scrape failed" in result["error"]

    async def test_no_models_imported(self, tmp_path):
        """When no files are successfully imported, status should be no_models."""
        dest_dir = tmp_path / "library"
        dest_dir.mkdir()

        html_file = dest_dir / "page.html"
        html_file.write_text("<html></html>")

        mock_meta = {
            "title": "Test",
            "tags": [],
            "download_urls": ["https://example.com/page.html"],
            "error": None,
        }

        with (
            patch("app.services.importer.scrape_metadata", new_callable=AsyncMock) as mock_scrape,
            patch("app.services.importer.download_file", new_callable=AsyncMock) as mock_download,
            patch("app.services.importer.httpx") as mock_httpx,
        ):
            mock_scrape.return_value = mock_meta
            mock_download.return_value = html_file

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await import_from_url(
                url="https://example.com/page",
                library_id=1,
                library_path=str(dest_dir),
            )

        assert result["status"] == "no_models"

    async def test_download_failure_continues(self, tmp_path):
        """If one download fails, import should continue with others."""
        dest_dir = tmp_path / "library"
        dest_dir.mkdir()

        stl_file = dest_dir / "model.stl"
        _create_test_stl(stl_file)

        mock_meta = {
            "title": "Multi",
            "tags": [],
            "download_urls": [
                "https://example.com/bad.stl",
                "https://example.com/model.stl",
            ],
            "error": None,
        }

        call_count = 0

        async def download_side_effect(url, client, dest):
            nonlocal call_count
            call_count += 1
            if "bad.stl" in url:
                raise Exception("Download failed")
            return stl_file

        with (
            patch("app.services.importer.scrape_metadata", new_callable=AsyncMock) as mock_scrape,
            patch("app.services.importer.download_file", new_callable=AsyncMock) as mock_download,
            patch("app.services.importer.process_imported_file", new_callable=AsyncMock) as mock_process,
            patch("app.services.importer.httpx") as mock_httpx,
        ):
            mock_scrape.return_value = mock_meta
            mock_download.side_effect = download_side_effect
            mock_process.return_value = 42

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await import_from_url(
                url="https://example.com/multi",
                library_id=1,
                library_path=str(dest_dir),
            )

        assert result["status"] == "ok"
        assert 42 in result["models"]

    async def test_no_download_urls_uses_original(self, tmp_path):
        """When scraping finds no download URLs, the original URL is used."""
        dest_dir = tmp_path / "library"
        dest_dir.mkdir()

        stl_file = dest_dir / "model.stl"
        _create_test_stl(stl_file)

        mock_meta = {
            "title": "Direct",
            "tags": [],
            "download_urls": [],  # No download URLs from scraper
            "error": None,
        }

        with (
            patch("app.services.importer.scrape_metadata", new_callable=AsyncMock) as mock_scrape,
            patch("app.services.importer.download_file", new_callable=AsyncMock) as mock_download,
            patch("app.services.importer.process_imported_file", new_callable=AsyncMock) as mock_process,
            patch("app.services.importer.httpx") as mock_httpx,
        ):
            mock_scrape.return_value = mock_meta
            mock_download.return_value = stl_file
            mock_process.return_value = 55

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await import_from_url(
                url="https://example.com/direct.stl",
                library_id=1,
                library_path=str(dest_dir),
            )

        assert result["status"] == "ok"
        # download_file should have been called with the original URL
        mock_download.assert_called_once()
        assert mock_download.call_args.args[0] == "https://example.com/direct.stl"


# ---------------------------------------------------------------------------
# import_urls_batch() + get_import_progress()
# ---------------------------------------------------------------------------


class TestImportUrlsBatch:
    """Tests for batch URL import and progress tracking."""

    async def test_batch_import_processes_all_urls(self, tmp_path):
        """All URLs should be processed sequentially."""
        urls = [
            "https://example.com/model1.stl",
            "https://example.com/model2.stl",
        ]

        results = []

        async def mock_import(url, library_id, library_path, subfolder=None, credentials=None):
            result = {"url": url, "status": "ok", "models": [1], "error": None}
            results.append(result)
            return result

        with patch("app.services.importer.import_from_url", side_effect=mock_import):
            await import_urls_batch(
                urls=urls,
                library_id=1,
                library_path=str(tmp_path),
            )

        assert len(results) == 2

    async def test_batch_import_tracks_progress(self, tmp_path):
        """Progress dict should be updated as URLs are processed."""
        progress_snapshots = []

        async def mock_import(url, library_id, library_path, subfolder=None, credentials=None):
            progress_snapshots.append(get_import_progress().copy())
            return {"url": url, "status": "ok", "models": [], "error": None}

        with patch("app.services.importer.import_from_url", side_effect=mock_import):
            await import_urls_batch(
                urls=["https://example.com/a", "https://example.com/b"],
                library_id=1,
                library_path=str(tmp_path),
            )

        # After completion, running should be False
        final = get_import_progress()
        assert final["running"] is False

        # During processing, running should have been True
        assert len(progress_snapshots) == 2
        assert progress_snapshots[0]["running"] is True
        assert progress_snapshots[0]["total"] == 2

    async def test_batch_import_skips_empty_urls(self, tmp_path):
        """Empty/whitespace URLs should be skipped."""
        call_count = 0

        async def mock_import(url, library_id, library_path, subfolder=None, credentials=None):
            nonlocal call_count
            call_count += 1
            return {"url": url, "status": "ok", "models": [], "error": None}

        with patch("app.services.importer.import_from_url", side_effect=mock_import):
            await import_urls_batch(
                urls=["", " ", "https://example.com/model.stl"],
                library_id=1,
                library_path=str(tmp_path),
            )

        assert call_count == 1

    async def test_batch_import_passes_credentials(self, tmp_path):
        """Credentials should be forwarded to import_from_url."""
        captured_creds = []

        async def mock_import(url, library_id, library_path, subfolder=None, credentials=None):
            captured_creds.append(credentials)
            return {"url": url, "status": "ok", "models": [], "error": None}

        creds = {"thingiverse": {"api_key": "abc123"}}

        with patch("app.services.importer.import_from_url", side_effect=mock_import):
            await import_urls_batch(
                urls=["https://example.com/model.stl"],
                library_id=1,
                library_path=str(tmp_path),
                credentials=creds,
            )

        assert captured_creds[0] == creds

    async def test_batch_import_running_flag_reset_on_error(self, tmp_path):
        """Running flag should be reset even if an error occurs."""
        async def mock_import(url, library_id, library_path, subfolder=None, credentials=None):
            raise RuntimeError("Something broke")

        with patch("app.services.importer.import_from_url", side_effect=mock_import):
            # The RuntimeError should propagate out of the for loop
            # but the finally block should still reset the running flag.
            # Actually the error is caught by the for loop since
            # import_from_url itself catches errors. Let's test the
            # finally block by raising in the import function side_effect.
            try:
                await import_urls_batch(
                    urls=["https://example.com/model.stl"],
                    library_id=1,
                    library_path=str(tmp_path),
                )
            except RuntimeError:
                pass

        final = get_import_progress()
        assert final["running"] is False
