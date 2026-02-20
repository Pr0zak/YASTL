"""Tests for app.models.schemas module."""

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    ModelCreate,
    ModelResponse,
    ModelUpdate,
    TagCreate,
    TagResponse,
    CategoryCreate,
    CategoryResponse,
    SearchResult,
    ScanStatus,
)


class TestModelCreate:
    def test_minimal_fields(self):
        m = ModelCreate(name="cube", file_path="/tmp/cube.stl", file_format="STL")
        assert m.name == "cube"
        assert m.description == ""
        assert m.file_size is None

    def test_all_fields(self):
        m = ModelCreate(
            name="cube",
            description="A simple cube",
            file_path="/tmp/cube.stl",
            file_format="STL",
            file_size=1024,
            vertex_count=8,
            face_count=12,
            dimensions_x=1.0,
            dimensions_y=1.0,
            dimensions_z=1.0,
            thumbnail_path="/thumb/1.png",
            file_hash="abc123",
        )
        assert m.file_size == 1024
        assert m.vertex_count == 8

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            ModelCreate(description="no name or path")


class TestModelResponse:
    def test_valid_response(self):
        r = ModelResponse(
            id=1,
            name="cube",
            description="",
            file_path="/tmp/cube.stl",
            file_format="STL",
            created_at="2024-01-01",
            updated_at="2024-01-01",
        )
        assert r.id == 1
        assert r.tags == []
        assert r.categories == []

    def test_with_tags_and_categories(self):
        r = ModelResponse(
            id=1,
            name="cube",
            description="",
            file_path="/tmp/cube.stl",
            file_format="STL",
            created_at="2024-01-01",
            updated_at="2024-01-01",
            tags=["red", "blue"],
            categories=["Figurines"],
        )
        assert len(r.tags) == 2
        assert "red" in r.tags


class TestModelUpdate:
    def test_partial_update_name_only(self):
        u = ModelUpdate(name="new_name")
        assert u.name == "new_name"
        assert u.description is None

    def test_partial_update_description_only(self):
        u = ModelUpdate(description="new desc")
        assert u.description == "new desc"
        assert u.name is None

    def test_empty_update(self):
        u = ModelUpdate()
        assert u.name is None
        assert u.description is None


class TestTagCreate:
    def test_valid(self):
        t = TagCreate(name="red")
        assert t.name == "red"

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            TagCreate()


class TestTagResponse:
    def test_valid(self):
        t = TagResponse(id=1, name="blue")
        assert t.id == 1


class TestCategoryCreate:
    def test_root_category(self):
        c = CategoryCreate(name="Figurines")
        assert c.parent_id is None

    def test_child_category(self):
        c = CategoryCreate(name="Animals", parent_id=1)
        assert c.parent_id == 1


class TestCategoryResponse:
    def test_valid(self):
        c = CategoryResponse(id=1, name="Figurines")
        assert c.id == 1
        assert c.parent_id is None


class TestSearchResult:
    def test_empty_search(self):
        s = SearchResult(models=[], total=0, query="test")
        assert s.total == 0


class TestScanStatus:
    def test_idle(self):
        s = ScanStatus(scanning=False, total_files=0, processed_files=0)
        assert not s.scanning

    def test_scanning(self):
        s = ScanStatus(
            scanning=True,
            total_files=100,
            processed_files=50,
            last_scan="2024-01-01",
        )
        assert s.scanning
        assert s.processed_files == 50
