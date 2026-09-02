"""Tests for the decimated GLB preview builder (app/services/preview.py)."""

import io

import pytest
import trimesh

from app.services.preview import build_preview_glb


def _glb_faces(glb_bytes: bytes) -> int:
    loaded = trimesh.load(io.BytesIO(glb_bytes), file_type="glb")
    if isinstance(loaded, trimesh.Trimesh):
        return len(loaded.faces)
    return sum(len(g.faces) for g in loaded.geometry.values())


def test_large_mesh_is_decimated(tmp_path):
    big = trimesh.creation.icosphere(subdivisions=7)  # ~320k faces
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


class TestPreviewShading:
    """The preview GLB must not carry smoothed vertex normals.

    trimesh averages face normals across every shared vertex with no crease
    threshold. On a hard-surface print model that describes a different surface
    from the geometry — measured at 42 degrees of average error on a real wall
    bracket — and renders soft and inflated. Omitting NORMAL makes a glTF client
    flat-shade, which is both truthful and smaller.
    """

    @staticmethod
    def _gltf_attributes(glb: bytes) -> set[str]:
        import json
        import struct

        json_len = struct.unpack_from("<I", glb, 12)[0]
        doc = json.loads(glb[20 : 20 + json_len])
        attrs: set[str] = set()
        for mesh in doc.get("meshes", []):
            for primitive in mesh.get("primitives", []):
                attrs |= set(primitive.get("attributes", {}).keys())
        return attrs

    def test_preview_glb_has_positions_but_no_normals(self, tmp_path):
        import trimesh

        from app.services.preview import build_preview_glb

        # A cube is the clearest case: every vertex is shared by faces that are
        # 90 degrees apart, so smoothing would be maximally wrong.
        src = tmp_path / "cube.stl"
        trimesh.creation.box(extents=(10, 10, 10)).export(str(src))

        attrs = self._gltf_attributes(build_preview_glb(str(src)))
        assert "POSITION" in attrs
        assert "NORMAL" not in attrs, (
            "Smoothed normals are back in the preview GLB; hard edges will "
            "render rounded."
        )

    def test_omitting_normals_makes_the_glb_smaller(self, tmp_path):
        import trimesh

        from app.services.preview import build_preview_glb

        src = tmp_path / "cube.stl"
        mesh = trimesh.creation.box(extents=(10, 10, 10))
        mesh.export(str(src))

        with_normals = trimesh.load(str(src), force="mesh")
        _ = with_normals.vertex_normals
        assert len(build_preview_glb(str(src))) < len(
            with_normals.export(file_type="glb")
        )


def test_cache_name_carries_the_current_version():
    """A cached GLB from an older generation must not be reachable by name.

    The cache is keyed by version precisely so a change to the output — the face
    target, the attributes written — invalidates it everywhere rather than only
    where someone remembered to delete the files. Getting this wrong is silent:
    the new code deploys, the cache keeps answering, and the fix looks broken.
    """
    from app.services.preview import (
        PREVIEW_CACHE_VERSION,
        PREVIEW_DETAIL_DEFAULT,
        preview_cache_name,
    )

    assert preview_cache_name(42) == (
        f"42.v{PREVIEW_CACHE_VERSION}-{PREVIEW_DETAIL_DEFAULT}.glb"
    )
    assert PREVIEW_CACHE_VERSION >= 3, (
        "v3 dropped vertex normals; a lower version would serve smoothed GLBs."
    )


class TestPreviewDetail:
    """The detail setting must reach both the face target and the cache key."""

    def test_each_level_maps_to_its_face_target(self):
        from app.services.preview import PREVIEW_DETAIL_FACES, detail_max_faces

        assert detail_max_faces("fast") < detail_max_faces("balanced")
        assert detail_max_faces("balanced") < detail_max_faces("detailed")
        assert set(PREVIEW_DETAIL_FACES) == {"fast", "balanced", "detailed"}

    def test_an_unknown_level_falls_back_rather_than_raising(self):
        from app.services.preview import PREVIEW_DETAIL_DEFAULT, detail_max_faces

        assert detail_max_faces(None) == detail_max_faces(PREVIEW_DETAIL_DEFAULT)
        assert detail_max_faces("nonsense") == detail_max_faces(PREVIEW_DETAIL_DEFAULT)

    def test_cache_name_is_distinct_per_level(self):
        """Otherwise changing the setting keeps serving the previous file."""
        from app.services.preview import preview_cache_name

        names = {preview_cache_name(7, d) for d in ("fast", "balanced", "detailed")}
        assert len(names) == 3, names
        for name in names:
            assert name.startswith("7.v")
            assert name.endswith(".glb")

    def test_unknown_level_reuses_the_default_cache_entry(self):
        from app.services.preview import PREVIEW_DETAIL_DEFAULT, preview_cache_name

        assert preview_cache_name(7, "nonsense") == preview_cache_name(
            7, PREVIEW_DETAIL_DEFAULT
        )

    def test_a_lower_level_produces_a_smaller_glb(self, tmp_path):
        import trimesh

        from app.services.preview import build_preview_glb, detail_max_faces

        # An icosphere subdivided enough to exceed the "fast" target, so the
        # levels genuinely differ rather than both serving the mesh whole.
        src = tmp_path / "sphere.stl"
        mesh = trimesh.creation.icosphere(subdivisions=6)
        mesh.export(str(src))
        assert len(mesh.faces) > 80_000

        small = build_preview_glb(str(src), max_faces=20_000)
        large = build_preview_glb(str(src), max_faces=detail_max_faces("detailed"))
        assert len(small) < len(large)
