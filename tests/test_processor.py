"""Tests for app.services.processor module."""

import struct
from pathlib import Path


from app.services.processor import (
    extract_metadata,
    FORMAT_MAP,
    TRIMESH_SUPPORTED,
    FALLBACK_ONLY,
)


def _create_binary_stl(path: Path, num_triangles: int = 1) -> None:
    """Create a minimal valid binary STL file."""
    header = b"\x00" * 80
    with open(path, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", num_triangles))
        for _ in range(num_triangles):
            # normal
            f.write(struct.pack("<fff", 0.0, 0.0, 1.0))
            # vertex 1
            f.write(struct.pack("<fff", 0.0, 0.0, 0.0))
            # vertex 2
            f.write(struct.pack("<fff", 1.0, 0.0, 0.0))
            # vertex 3
            f.write(struct.pack("<fff", 0.0, 1.0, 0.0))
            # attribute byte count
            f.write(struct.pack("<H", 0))


class TestExtractMetadata:
    def test_stl_metadata(self, tmp_path):
        """extract_metadata should return correct metadata for STL files."""
        stl_path = tmp_path / "test.stl"
        _create_binary_stl(stl_path, num_triangles=2)

        meta = extract_metadata(str(stl_path))
        assert meta["file_format"] == "STL"
        assert meta["file_size"] > 0
        assert meta["vertex_count"] is not None
        assert meta["face_count"] is not None

    def test_stl_dimensions(self, tmp_path):
        """extract_metadata should extract bounding box dimensions."""
        stl_path = tmp_path / "test.stl"
        _create_binary_stl(stl_path)

        meta = extract_metadata(str(stl_path))
        # Our test STL has vertices at (0,0,0), (1,0,0), (0,1,0)
        assert meta["dimensions_x"] is not None
        assert meta["dimensions_y"] is not None
        assert meta["dimensions_z"] is not None

    def test_unsupported_format(self, tmp_path):
        """extract_metadata should return partial metadata for unknown formats."""
        txt_path = tmp_path / "test.txt"
        txt_path.write_text("not a 3d file")

        meta = extract_metadata(str(txt_path))
        assert meta["file_format"] == "TXT"
        assert meta["vertex_count"] is None
        assert meta["face_count"] is None

    def test_nonexistent_file(self, tmp_path):
        """extract_metadata should handle missing files gracefully."""
        meta = extract_metadata(str(tmp_path / "missing.stl"))
        assert meta["file_size"] is None

    def test_format_map_coverage(self):
        """FORMAT_MAP should cover all supported extensions."""
        assert ".stl" in FORMAT_MAP
        assert ".obj" in FORMAT_MAP
        assert ".gltf" in FORMAT_MAP
        assert ".glb" in FORMAT_MAP
        assert ".3mf" in FORMAT_MAP
        assert ".step" in FORMAT_MAP
        assert ".stp" in FORMAT_MAP

    def test_trimesh_supported_and_fallback_disjoint(self):
        """TRIMESH_SUPPORTED and FALLBACK_ONLY should not overlap."""
        assert TRIMESH_SUPPORTED.isdisjoint(FALLBACK_ONLY)

    def test_step_file_fallback(self, tmp_path):
        """STEP files should return basic metadata without crashing."""
        step_path = tmp_path / "test.step"
        step_path.write_text("ISO-10303-21;")

        meta = extract_metadata(str(step_path))
        assert meta["file_format"] == "STEP"
        assert meta["file_size"] is not None
