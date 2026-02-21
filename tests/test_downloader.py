"""Tests for app.services.downloader — file download and path utilities."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.services.downloader import (
    _sanitize_filename,
    _deduplicate_path,
    _is_presigned_s3,
    download_file,
)


# ---------------------------------------------------------------------------
# _sanitize_filename()
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    """Tests for the _sanitize_filename() function."""

    def test_clean_filename_unchanged(self):
        assert _sanitize_filename("model.stl") == "model.stl"

    def test_replaces_unsafe_characters(self):
        result = _sanitize_filename('file<>:"/\\|?*name.stl')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_strips_leading_trailing_dots_and_spaces(self):
        assert _sanitize_filename("...model.stl...") == "model.stl"

    def test_empty_string_returns_download(self):
        assert _sanitize_filename("") == "download"

    def test_only_dots_returns_download(self):
        assert _sanitize_filename("...") == "download"

    def test_only_spaces_returns_download(self):
        assert _sanitize_filename("   ") == "download"

    def test_replaces_control_characters(self):
        result = _sanitize_filename("file\x00\x01\x1fname.stl")
        assert "\x00" not in result
        assert "\x01" not in result
        assert "\x1f" not in result

    def test_preserves_unicode(self):
        result = _sanitize_filename("modèle_3d.stl")
        assert result == "modèle_3d.stl"

    def test_preserves_hyphens_and_underscores(self):
        assert _sanitize_filename("my-model_v2.stl") == "my-model_v2.stl"


# ---------------------------------------------------------------------------
# _deduplicate_path()
# ---------------------------------------------------------------------------


class TestDeduplicatePath:
    """Tests for the _deduplicate_path() function."""

    def test_returns_same_path_if_not_exists(self, tmp_path):
        dest = tmp_path / "model.stl"
        assert _deduplicate_path(dest) == dest

    def test_appends_counter_if_exists(self, tmp_path):
        dest = tmp_path / "model.stl"
        dest.touch()
        result = _deduplicate_path(dest)
        assert result == tmp_path / "model_1.stl"

    def test_increments_counter_for_multiple_duplicates(self, tmp_path):
        dest = tmp_path / "model.stl"
        dest.touch()
        (tmp_path / "model_1.stl").touch()
        (tmp_path / "model_2.stl").touch()
        result = _deduplicate_path(dest)
        assert result == tmp_path / "model_3.stl"

    def test_preserves_extension(self, tmp_path):
        dest = tmp_path / "model.3mf"
        dest.touch()
        result = _deduplicate_path(dest)
        assert result.suffix == ".3mf"
        assert result.name == "model_1.3mf"


# ---------------------------------------------------------------------------
# _is_presigned_s3()
# ---------------------------------------------------------------------------


class TestIsPresignedS3:
    """Tests for the _is_presigned_s3() function."""

    def test_s3_v4_signature(self):
        url = "https://bucket.s3.amazonaws.com/key?X-Amz-Signature=abc123&X-Amz-Expires=300"
        assert _is_presigned_s3(url) is True

    def test_s3_v2_signature(self):
        url = "https://bucket.s3.amazonaws.com/key?Signature=abc123&Expires=123"
        assert _is_presigned_s3(url) is True

    def test_non_s3_url(self):
        assert _is_presigned_s3("https://example.com/file.stl") is False

    def test_amazonaws_without_signature(self):
        url = "https://bucket.s3.amazonaws.com/key"
        assert _is_presigned_s3(url) is False

    def test_signature_in_non_aws_url(self):
        url = "https://example.com/file?Signature=abc"
        assert _is_presigned_s3(url) is False


# ---------------------------------------------------------------------------
# download_file() — with mocked HTTP
# ---------------------------------------------------------------------------


class TestDownloadFile:
    """Tests for the download_file() function with mocked HTTP."""

    async def test_download_with_explicit_filename(self, tmp_path):
        """When filename is provided, should use it directly."""
        dest_dir = tmp_path / "downloads"
        content = b"fake STL content"

        # Create a mock streaming response
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.headers = {}

        async def mock_aiter_bytes(chunk_size=None):
            yield content

        mock_resp.aiter_bytes = mock_aiter_bytes

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=AsyncContextManagerMock(mock_resp))

        result = await download_file(
            "https://example.com/files/model.stl",
            mock_client,
            dest_dir,
            filename="custom_name.stl",
        )

        assert result.name == "custom_name.stl"
        assert result.exists()
        assert result.read_bytes() == content

    async def test_download_detects_filename_from_url(self, tmp_path):
        """When no filename provided, should extract from URL path."""
        dest_dir = tmp_path / "downloads"
        content = b"fake content"

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.headers = {"content-disposition": ""}
        mock_resp.url = "https://example.com/files/cool_model.stl"

        async def mock_aiter_bytes(chunk_size=None):
            yield content

        mock_resp.aiter_bytes = mock_aiter_bytes

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=AsyncContextManagerMock(mock_resp))

        result = await download_file(
            "https://example.com/files/cool_model.stl",
            mock_client,
            dest_dir,
        )

        assert result.name == "cool_model.stl"
        assert result.exists()

    async def test_download_detects_filename_from_content_disposition(self, tmp_path):
        """Should parse Content-Disposition header for filename."""
        dest_dir = tmp_path / "downloads"
        content = b"fake content"

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.headers = {
            "content-disposition": 'attachment; filename="header_name.stl"'
        }
        mock_resp.url = "https://example.com/download?id=123"

        async def mock_aiter_bytes(chunk_size=None):
            yield content

        mock_resp.aiter_bytes = mock_aiter_bytes

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=AsyncContextManagerMock(mock_resp))

        result = await download_file(
            "https://example.com/download?id=123",
            mock_client,
            dest_dir,
        )

        assert result.name == "header_name.stl"

    async def test_download_creates_dest_dir(self, tmp_path):
        """Should create destination directory if it doesn't exist."""
        dest_dir = tmp_path / "new" / "nested" / "dir"
        content = b"content"

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.headers = {}

        async def mock_aiter_bytes(chunk_size=None):
            yield content

        mock_resp.aiter_bytes = mock_aiter_bytes

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=AsyncContextManagerMock(mock_resp))

        result = await download_file(
            "https://example.com/model.stl",
            mock_client,
            dest_dir,
            filename="model.stl",
        )

        assert dest_dir.exists()
        assert result.exists()

    async def test_download_s3_presigned_uses_urllib(self, tmp_path):
        """S3 presigned URLs should use urllib instead of httpx."""
        dest_dir = tmp_path / "downloads"
        dest_dir.mkdir()
        content = b"s3 content"

        s3_url = "https://bucket.s3.amazonaws.com/model.stl?X-Amz-Signature=abc"

        with patch("app.services.downloader._download_raw") as mock_raw:
            mock_raw.return_value = None
            # Simulate the file being written by _download_raw
            def write_file(url, dest):
                dest.write_bytes(content)
            mock_raw.side_effect = write_file

            mock_client = AsyncMock()  # Should not be used
            result = await download_file(s3_url, mock_client, dest_dir)

        mock_raw.assert_called_once()
        assert result.name == "model.stl"


# ---------------------------------------------------------------------------
# Helper: Async context manager mock
# ---------------------------------------------------------------------------


class AsyncContextManagerMock:
    """Helper to mock async context managers (async with client.stream(...))."""

    def __init__(self, return_value):
        self._return_value = return_value

    async def __aenter__(self):
        return self._return_value

    async def __aexit__(self, *args):
        pass
