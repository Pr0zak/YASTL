"""Tests for geometry-derived shape tags (app/services/tagger.py)."""

from app.services.tagger import _classify_shape, suggest_tags


def test_flat_plate():
    assert "flat" in _classify_shape(100, 80, 5)
    assert "tall" not in _classify_shape(100, 80, 5)


def test_tall_tower():
    assert "tall" in _classify_shape(30, 30, 120)
    assert "flat" not in _classify_shape(30, 30, 120)


def test_cube_has_no_shape_tag():
    assert _classify_shape(50, 50, 50) == []


def test_missing_dims_returns_empty():
    assert _classify_shape(50, None, 50) == []


def test_suggest_tags_includes_shape():
    tags = suggest_tags({
        "name": "dragon_figure",
        "dimensions_x": 25, "dimensions_y": 25, "dimensions_z": 90,
        "face_count": 250000, "file_format": "stl",
    })
    assert "tall" in tags
