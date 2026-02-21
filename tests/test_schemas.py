"""Tests for app.models.schemas module."""

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    BulkCategoryRequest,
    BulkCollectionRequest,
    BulkDeleteRequest,
    BulkFavoriteRequest,
    BulkTagRequest,
    CategoryCreate,
    CategoryResponse,
    CollectionCreate,
    CollectionUpdate,
    ModelCreate,
    ModelResponse,
    ModelUpdate,
    SavedSearchCreate,
    SavedSearchUpdate,
    ScanStatus,
    SearchResult,
    TagCreate,
    TagResponse,
)


# ---------------------------------------------------------------------------
# Model schemas (existing tests)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Tag name validation
# ---------------------------------------------------------------------------


class TestTagCreate:
    def test_valid(self):
        t = TagCreate(name="red")
        assert t.name == "red"

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            TagCreate()

    def test_strips_whitespace(self):
        t = TagCreate(name="  spaced  ")
        assert t.name == "spaced"

    def test_rejects_empty_string(self):
        with pytest.raises(ValidationError, match="empty"):
            TagCreate(name="")

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValidationError, match="empty"):
            TagCreate(name="   ")

    def test_rejects_tabs_only(self):
        with pytest.raises(ValidationError, match="empty"):
            TagCreate(name="\t\n")

    def test_preserves_internal_spaces(self):
        t = TagCreate(name="two words")
        assert t.name == "two words"


class TestTagResponse:
    def test_valid(self):
        t = TagResponse(id=1, name="blue")
        assert t.id == 1


# ---------------------------------------------------------------------------
# Category name validation
# ---------------------------------------------------------------------------


class TestCategoryCreate:
    def test_root_category(self):
        c = CategoryCreate(name="Figurines")
        assert c.parent_id is None

    def test_child_category(self):
        c = CategoryCreate(name="Animals", parent_id=1)
        assert c.parent_id == 1

    def test_strips_whitespace(self):
        c = CategoryCreate(name="  Figurines  ")
        assert c.name == "Figurines"

    def test_rejects_empty_string(self):
        with pytest.raises(ValidationError, match="empty"):
            CategoryCreate(name="")

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValidationError, match="empty"):
            CategoryCreate(name="   ")


class TestCategoryResponse:
    def test_valid(self):
        c = CategoryResponse(id=1, name="Figurines")
        assert c.id == 1
        assert c.parent_id is None


# ---------------------------------------------------------------------------
# Collection color validation
# ---------------------------------------------------------------------------


class TestCollectionCreate:
    def test_valid_six_digit_hex(self):
        c = CollectionCreate(name="Prints", color="#FF5733")
        assert c.color == "#FF5733"

    def test_valid_three_digit_hex(self):
        c = CollectionCreate(name="Prints", color="#F00")
        assert c.color == "#F00"

    def test_valid_lowercase_hex(self):
        c = CollectionCreate(name="Prints", color="#abc123")
        assert c.color == "#abc123"

    def test_none_color_is_valid(self):
        c = CollectionCreate(name="Prints", color=None)
        assert c.color is None

    def test_no_color_defaults_to_none(self):
        c = CollectionCreate(name="Prints")
        assert c.color is None

    def test_rejects_invalid_hex_no_hash(self):
        with pytest.raises(ValidationError, match="hex color"):
            CollectionCreate(name="Prints", color="FF5733")

    def test_rejects_invalid_hex_wrong_length(self):
        with pytest.raises(ValidationError, match="hex color"):
            CollectionCreate(name="Prints", color="#FFFF")

    def test_rejects_non_hex_characters(self):
        with pytest.raises(ValidationError, match="hex color"):
            CollectionCreate(name="Prints", color="#GGGGGG")

    def test_rejects_empty_string(self):
        with pytest.raises(ValidationError, match="hex color"):
            CollectionCreate(name="Prints", color="")

    def test_rejects_named_color(self):
        with pytest.raises(ValidationError, match="hex color"):
            CollectionCreate(name="Prints", color="red")


class TestCollectionUpdate:
    def test_valid_color(self):
        c = CollectionUpdate(color="#ABC")
        assert c.color == "#ABC"

    def test_none_color_is_valid(self):
        c = CollectionUpdate(color=None)
        assert c.color is None

    def test_rejects_invalid_color(self):
        with pytest.raises(ValidationError, match="hex color"):
            CollectionUpdate(color="invalid")

    def test_rejects_eight_digit_hex(self):
        with pytest.raises(ValidationError, match="hex color"):
            CollectionUpdate(color="#FF5733AA")


# ---------------------------------------------------------------------------
# Saved search sort validation
# ---------------------------------------------------------------------------


class TestSavedSearchCreate:
    def test_valid_defaults(self):
        s = SavedSearchCreate(name="My search")
        assert s.sort_by == "created_at"
        assert s.sort_order == "desc"

    def test_all_valid_sort_by_values(self):
        for field in ["name", "created_at", "updated_at", "file_size", "vertex_count", "face_count"]:
            s = SavedSearchCreate(name="test", sort_by=field)
            assert s.sort_by == field

    def test_rejects_invalid_sort_by(self):
        with pytest.raises(ValidationError, match="sort_by"):
            SavedSearchCreate(name="test", sort_by="invalid_column")

    def test_rejects_sql_injection_sort_by(self):
        with pytest.raises(ValidationError, match="sort_by"):
            SavedSearchCreate(name="test", sort_by="name; DROP TABLE models")

    def test_valid_sort_order_asc(self):
        s = SavedSearchCreate(name="test", sort_order="asc")
        assert s.sort_order == "asc"

    def test_valid_sort_order_desc(self):
        s = SavedSearchCreate(name="test", sort_order="desc")
        assert s.sort_order == "desc"

    def test_rejects_invalid_sort_order(self):
        with pytest.raises(ValidationError, match="sort_order"):
            SavedSearchCreate(name="test", sort_order="ascending")

    def test_rejects_empty_sort_order(self):
        with pytest.raises(ValidationError, match="sort_order"):
            SavedSearchCreate(name="test", sort_order="")


class TestSavedSearchUpdate:
    def test_none_values_are_valid(self):
        s = SavedSearchUpdate()
        assert s.sort_by is None
        assert s.sort_order is None

    def test_valid_sort_by(self):
        s = SavedSearchUpdate(sort_by="name")
        assert s.sort_by == "name"

    def test_rejects_invalid_sort_by(self):
        with pytest.raises(ValidationError, match="sort_by"):
            SavedSearchUpdate(sort_by="bad_column")

    def test_valid_sort_order(self):
        s = SavedSearchUpdate(sort_order="asc")
        assert s.sort_order == "asc"

    def test_rejects_invalid_sort_order(self):
        with pytest.raises(ValidationError, match="sort_order"):
            SavedSearchUpdate(sort_order="UP")

    def test_none_sort_by_is_valid(self):
        """None explicitly passed should be accepted (partial update)."""
        s = SavedSearchUpdate(sort_by=None)
        assert s.sort_by is None

    def test_none_sort_order_is_valid(self):
        """None explicitly passed should be accepted (partial update)."""
        s = SavedSearchUpdate(sort_order=None)
        assert s.sort_order is None


# ---------------------------------------------------------------------------
# Bulk operation model_ids validation
# ---------------------------------------------------------------------------


class TestBulkTagRequest:
    def test_valid(self):
        r = BulkTagRequest(model_ids=[1, 2, 3], tags=["pla", "vase"])
        assert len(r.model_ids) == 3

    def test_rejects_empty_model_ids(self):
        with pytest.raises(ValidationError, match="model_ids"):
            BulkTagRequest(model_ids=[], tags=["pla"])

    def test_rejects_empty_tags(self):
        with pytest.raises(ValidationError, match="tags"):
            BulkTagRequest(model_ids=[1], tags=[])


class TestBulkCategoryRequest:
    def test_valid(self):
        r = BulkCategoryRequest(model_ids=[1], category_ids=[10])
        assert r.model_ids == [1]

    def test_rejects_empty_model_ids(self):
        with pytest.raises(ValidationError, match="model_ids"):
            BulkCategoryRequest(model_ids=[], category_ids=[10])

    def test_rejects_empty_category_ids(self):
        with pytest.raises(ValidationError, match="category_ids"):
            BulkCategoryRequest(model_ids=[1], category_ids=[])


class TestBulkCollectionRequest:
    def test_valid(self):
        r = BulkCollectionRequest(model_ids=[1, 2], collection_id=5)
        assert r.collection_id == 5

    def test_rejects_empty_model_ids(self):
        with pytest.raises(ValidationError, match="model_ids"):
            BulkCollectionRequest(model_ids=[], collection_id=5)


class TestBulkFavoriteRequest:
    def test_valid(self):
        r = BulkFavoriteRequest(model_ids=[1])
        assert r.favorite is True

    def test_rejects_empty_model_ids(self):
        with pytest.raises(ValidationError, match="model_ids"):
            BulkFavoriteRequest(model_ids=[])


class TestBulkDeleteRequest:
    def test_valid(self):
        r = BulkDeleteRequest(model_ids=[1, 2])
        assert len(r.model_ids) == 2

    def test_rejects_empty_model_ids(self):
        with pytest.raises(ValidationError, match="model_ids"):
            BulkDeleteRequest(model_ids=[])


# ---------------------------------------------------------------------------
# Search and Scan schemas (existing tests)
# ---------------------------------------------------------------------------


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
