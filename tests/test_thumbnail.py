"""Tests for app.services.thumbnail and its sub-modules (mesh + render)."""

import numpy as np
import pytest
import trimesh

from app.services.thumbnail_mesh import (
    _collect_meshes,
    _simplify_for_thumbnail,
    _simplify_mesh,
    _MAX_THUMBNAIL_FACES,
)
from app.services.thumbnail_render import (
    _project_vertices,
    _render_wireframe,
    _render_solid_fast,
)
from app.services.thumbnail import generate_thumbnail


def _make_cube_mesh() -> trimesh.Trimesh:
    """Create a simple unit cube mesh for testing."""
    return trimesh.creation.box(extents=(1.0, 1.0, 1.0))


def _make_high_poly_mesh(n_faces: int = 100000) -> trimesh.Trimesh:
    """Create a mesh with many faces by subdividing a sphere."""
    # trimesh.creation.icosphere subdivisions give exponential face growth
    # 0->20, 1->80, 2->320, 3->1280, 4->5120, 5->20480, 6->81920
    subdivisions = 6  # 81920 faces > _MAX_THUMBNAIL_FACES
    return trimesh.creation.icosphere(subdivisions=subdivisions)


# ---------------------------------------------------------------------------
# _collect_meshes()
# ---------------------------------------------------------------------------


class TestCollectMeshes:
    """Tests for the _collect_meshes() function."""

    def test_single_trimesh(self):
        mesh = _make_cube_mesh()
        result = _collect_meshes(mesh)
        assert len(result) == 1
        assert isinstance(result[0], trimesh.Trimesh)

    def test_scene_with_one_mesh(self):
        mesh = _make_cube_mesh()
        scene = trimesh.Scene(mesh)
        result = _collect_meshes(scene)
        assert len(result) >= 1
        assert all(isinstance(m, trimesh.Trimesh) for m in result)

    def test_scene_with_multiple_meshes(self):
        mesh1 = _make_cube_mesh()
        mesh2 = trimesh.creation.cylinder(radius=0.5, height=1.0)
        scene = trimesh.Scene([mesh1, mesh2])
        result = _collect_meshes(scene)
        assert len(result) >= 2
        assert all(isinstance(m, trimesh.Trimesh) for m in result)

    def test_empty_scene(self):
        scene = trimesh.Scene()
        result = _collect_meshes(scene)
        assert result == []

    def test_non_mesh_geometry_skipped(self):
        """Non-Trimesh geometry in a scene should be skipped."""
        scene = trimesh.Scene()
        # PointCloud is not a Trimesh
        points = trimesh.PointCloud(np.random.rand(10, 3))
        scene.add_geometry(points)
        result = _collect_meshes(scene)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# _simplify_mesh() / _simplify_for_thumbnail()
# ---------------------------------------------------------------------------


class TestSimplifyMesh:
    """Tests for mesh simplification functions."""

    def test_small_mesh_unchanged(self):
        mesh = _make_cube_mesh()
        original_faces = len(mesh.faces)
        result = _simplify_mesh(mesh, _MAX_THUMBNAIL_FACES)
        assert len(result.faces) == original_faces

    def test_simplify_reduces_faces(self):
        """If fast_simplification is available, face count should decrease."""
        try:
            import fast_simplification  # noqa: F401
        except ImportError:
            pytest.skip("fast_simplification not installed")

        mesh = _make_high_poly_mesh()
        target = 10000
        result = _simplify_mesh(mesh, target)
        # Should have fewer faces than original
        assert len(result.faces) < len(mesh.faces)

    def test_simplify_for_thumbnail_under_budget(self):
        """Meshes under budget should be returned unchanged."""
        mesh = _make_cube_mesh()
        result = _simplify_for_thumbnail([mesh])
        assert len(result) == 1
        assert len(result[0].faces) == len(mesh.faces)

    def test_simplify_for_thumbnail_preserves_mesh_count(self):
        """Number of meshes should be preserved after simplification."""
        meshes = [_make_cube_mesh(), _make_cube_mesh()]
        result = _simplify_for_thumbnail(meshes)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _project_vertices()
# ---------------------------------------------------------------------------


class TestProjectVertices:
    """Tests for vertex projection."""

    def test_projects_to_2d(self):
        vertices = np.array([
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1],
        ], dtype=np.float64)
        projected = _project_vertices(vertices, 256, 256, 20)
        assert projected.shape == (4, 2)

    def test_projected_within_bounds(self):
        """Projected vertices should be within the canvas (with padding)."""
        mesh = _make_cube_mesh()
        vertices = mesh.vertices - mesh.vertices.mean(axis=0)
        projected = _project_vertices(vertices, 256, 256, 20)
        assert np.all(projected[:, 0] >= 0)
        assert np.all(projected[:, 0] <= 256)
        assert np.all(projected[:, 1] >= 0)
        assert np.all(projected[:, 1] <= 256)

    def test_degenerate_single_point(self):
        """All vertices at the same point should project to center."""
        vertices = np.array([[1, 1, 1], [1, 1, 1], [1, 1, 1]], dtype=np.float64)
        projected = _project_vertices(vertices, 256, 256, 20)
        assert projected.shape == (3, 2)
        # All should project to center
        assert np.allclose(projected[0], [128, 128])


# ---------------------------------------------------------------------------
# _render_wireframe() / _render_solid_fast()
# ---------------------------------------------------------------------------


class TestRenderWireframe:
    """Tests for wireframe rendering."""

    def test_renders_cube(self, tmp_path):
        mesh = _make_cube_mesh()
        output = str(tmp_path / "wireframe.png")
        result = _render_wireframe([mesh], output)
        assert result is True
        assert (tmp_path / "wireframe.png").exists()
        # Check file is a valid PNG
        with open(output, "rb") as f:
            header = f.read(4)
        assert header[:4] == b"\x89PNG"

    def test_renders_empty_meshes_returns_false(self, tmp_path):
        output = str(tmp_path / "empty.png")
        result = _render_wireframe([], output)
        assert result is False

    def test_renders_multiple_meshes(self, tmp_path):
        meshes = [_make_cube_mesh(), trimesh.creation.cylinder(radius=0.5, height=1.0)]
        output = str(tmp_path / "multi.png")
        result = _render_wireframe(meshes, output)
        assert result is True
        assert (tmp_path / "multi.png").exists()


class TestRenderSolidFast:
    """Tests for solid fast rendering."""

    def test_renders_cube(self, tmp_path):
        mesh = _make_cube_mesh()
        output = str(tmp_path / "solid.png")
        result = _render_solid_fast([mesh], output)
        assert result is True
        assert (tmp_path / "solid.png").exists()
        with open(output, "rb") as f:
            header = f.read(4)
        assert header[:4] == b"\x89PNG"

    def test_renders_empty_meshes_returns_false(self, tmp_path):
        output = str(tmp_path / "empty.png")
        result = _render_solid_fast([], output)
        assert result is False


# ---------------------------------------------------------------------------
# generate_thumbnail() — integration test with a real cube mesh
# ---------------------------------------------------------------------------


class TestGenerateThumbnail:
    """Integration tests for the main generate_thumbnail() entry point."""

    def test_generates_wireframe_thumbnail(self, tmp_path):
        """Should generate a wireframe thumbnail from a real STL file."""
        # Create a real STL file from a cube mesh
        mesh = _make_cube_mesh()
        stl_path = tmp_path / "cube.stl"
        mesh.export(str(stl_path))

        thumb_dir = tmp_path / "thumbs"
        thumb_dir.mkdir()

        result = generate_thumbnail(
            str(stl_path),
            str(thumb_dir),
            model_id=42,
            render_mode="wireframe",
        )

        assert result is not None
        assert result == "42.png"
        assert (thumb_dir / "42.png").exists()

    def test_generates_solid_thumbnail(self, tmp_path):
        """Should generate a solid thumbnail from a real STL file."""
        mesh = _make_cube_mesh()
        stl_path = tmp_path / "cube.stl"
        mesh.export(str(stl_path))

        thumb_dir = tmp_path / "thumbs"
        thumb_dir.mkdir()

        result = generate_thumbnail(
            str(stl_path),
            str(thumb_dir),
            model_id=99,
            render_mode="solid",
            render_quality="fast",
        )

        assert result is not None
        assert result == "99.png"
        assert (thumb_dir / "99.png").exists()

    def test_returns_none_for_nonexistent_file(self, tmp_path):
        """Should return None when the model file doesn't exist."""
        thumb_dir = tmp_path / "thumbs"
        thumb_dir.mkdir()

        result = generate_thumbnail(
            str(tmp_path / "nonexistent.stl"),
            str(thumb_dir),
            model_id=1,
        )

        assert result is None

    def test_creates_output_directory(self, tmp_path):
        """Should create the output directory if it doesn't exist."""
        mesh = _make_cube_mesh()
        stl_path = tmp_path / "cube.stl"
        mesh.export(str(stl_path))

        thumb_dir = tmp_path / "new" / "thumb" / "dir"

        result = generate_thumbnail(
            str(stl_path),
            str(thumb_dir),
            model_id=7,
        )

        assert result is not None
        assert thumb_dir.exists()
        assert (thumb_dir / "7.png").exists()

    def test_generates_from_obj_file(self, tmp_path):
        """Should work with OBJ format too."""
        mesh = _make_cube_mesh()
        obj_path = tmp_path / "cube.obj"
        mesh.export(str(obj_path))

        thumb_dir = tmp_path / "thumbs"
        thumb_dir.mkdir()

        result = generate_thumbnail(
            str(obj_path),
            str(thumb_dir),
            model_id=55,
        )

        assert result is not None
        assert (thumb_dir / "55.png").exists()
