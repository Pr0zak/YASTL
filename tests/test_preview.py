"""Tests for the decimated GLB preview builder (app/services/preview.py)."""

import io

import pytest
import trimesh

from app.services.preview import build_preview_glb, DEFAULT_MAX_FACES


def _glb_faces(glb_bytes: bytes) -> int:
    loaded = trimesh.load(io.BytesIO(glb_bytes), file_type="glb")
    if isinstance(loaded, trimesh.Trimesh):
        return len(loaded.faces)
    return sum(len(g.faces) for g in loaded.geometry.values())


def test_large_mesh_is_decimated(tmp_path):
    big = trimesh.creation.icosphere(subdivisions=7)  # ~320k faces
    assert len(big.faces) > DEFAULT_MAX_FACES
    path = tmp_path / "big.stl"
    big.export(str(path))

    glb = build_preview_glb(str(path), max_faces=50_000)
    assert _glb_faces(glb) <= 50_000 + 50  # decimator lands at/under target


def test_small_mesh_passes_through(tmp_path):
    box = trimesh.creation.box()
    path = tmp_path / "box.stl"
    box.export(str(path))

    glb = build_preview_glb(str(path))
    assert _glb_faces(glb) == len(box.faces)


def test_preview_has_normals(tmp_path):
    """GLB must carry normals so the client skips computeVertexNormals."""
    mesh = trimesh.creation.icosphere(subdivisions=3)
    path = tmp_path / "sphere.stl"
    mesh.export(str(path))

    glb = build_preview_glb(str(path))
    reloaded = trimesh.load(io.BytesIO(glb), file_type="glb")
    m = (
        reloaded
        if isinstance(reloaded, trimesh.Trimesh)
        else trimesh.util.concatenate(tuple(reloaded.geometry.values()))
    )
    assert m.vertex_normals.shape[0] > 0


def test_unloadable_file_raises(tmp_path):
    bad = tmp_path / "bad.stl"
    bad.write_bytes(b"not a mesh")
    with pytest.raises(Exception):
        build_preview_glb(str(bad))
