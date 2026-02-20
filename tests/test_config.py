"""Tests for app.config module."""

from pathlib import Path


class TestSettings:
    def test_default_settings(self):
        """Settings should have sensible defaults."""
        from app.config import Settings
        s = Settings()
        assert isinstance(s.MODEL_LIBRARY_DB, Path)
        assert isinstance(s.MODEL_LIBRARY_SCAN_PATH, Path)
        assert isinstance(s.MODEL_LIBRARY_THUMBNAIL_PATH, Path)
        assert s.HOST == "0.0.0.0"
        assert s.PORT == 8000

    def test_supported_extensions(self):
        """Settings should include common 3D file extensions."""
        from app.config import Settings
        s = Settings()
        assert ".stl" in s.SUPPORTED_EXTENSIONS
        assert ".obj" in s.SUPPORTED_EXTENSIONS
        assert ".gltf" in s.SUPPORTED_EXTENSIONS
        assert ".glb" in s.SUPPORTED_EXTENSIONS
        assert ".3mf" in s.SUPPORTED_EXTENSIONS

    def test_env_prefix(self):
        """Settings should use YASTL_ env prefix."""
        from app.config import Settings
        assert Settings.model_config["env_prefix"] == "YASTL_"
