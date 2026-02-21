import re

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Shared allowed values
# ---------------------------------------------------------------------------

ALLOWED_SORT_BY = {"name", "created_at", "updated_at", "file_size", "vertex_count", "face_count"}
ALLOWED_SORT_ORDER = {"asc", "desc"}
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


# ---------------------------------------------------------------------------
# Model (3D file) schemas
# ---------------------------------------------------------------------------


class ModelCreate(BaseModel):
    """Schema for creating a new 3D model record."""

    name: str
    description: str = ""
    file_path: str
    file_format: str
    file_size: int | None = None
    vertex_count: int | None = None
    face_count: int | None = None
    dimensions_x: float | None = None
    dimensions_y: float | None = None
    dimensions_z: float | None = None
    thumbnail_path: str | None = None
    file_hash: str | None = None


class ModelResponse(BaseModel):
    """Full model representation returned by the API."""

    id: int
    name: str
    description: str
    file_path: str
    file_format: str
    file_size: int | None = None
    vertex_count: int | None = None
    face_count: int | None = None
    dimensions_x: float | None = None
    dimensions_y: float | None = None
    dimensions_z: float | None = None
    thumbnail_path: str | None = None
    file_hash: str | None = None
    zip_path: str | None = None
    zip_entry: str | None = None
    created_at: str
    updated_at: str
    tags: list[str] = []
    categories: list[str] = []
    is_favorite: bool = False


class ModelUpdate(BaseModel):
    """Schema for updating an existing model (partial update)."""

    name: str | None = None
    description: str | None = None


# ---------------------------------------------------------------------------
# Tag schemas
# ---------------------------------------------------------------------------


class TagCreate(BaseModel):
    """Schema for creating a new tag."""

    name: str

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Tag name must not be empty or whitespace-only")
        return v


class TagResponse(BaseModel):
    """Tag representation returned by the API."""

    id: int
    name: str


# ---------------------------------------------------------------------------
# Category schemas
# ---------------------------------------------------------------------------


class CategoryCreate(BaseModel):
    """Schema for creating a new category."""

    name: str
    parent_id: int | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Category name must not be empty or whitespace-only")
        return v


class CategoryResponse(BaseModel):
    """Category representation returned by the API."""

    id: int
    name: str
    parent_id: int | None = None


# ---------------------------------------------------------------------------
# Library schemas
# ---------------------------------------------------------------------------


class LibraryCreate(BaseModel):
    """Schema for creating a new library."""

    name: str
    path: str


class LibraryResponse(BaseModel):
    """Library representation returned by the API."""

    id: int
    name: str
    path: str
    created_at: str


# ---------------------------------------------------------------------------
# Collection schemas
# ---------------------------------------------------------------------------


class CollectionCreate(BaseModel):
    """Schema for creating a new collection."""
    name: str
    description: str = ""
    color: str | None = None

    @field_validator("color")
    @classmethod
    def color_must_be_valid_hex(cls, v: str | None) -> str | None:
        if v is not None and not _HEX_COLOR_RE.match(v):
            raise ValueError("Color must be a valid hex color (#RGB or #RRGGBB)")
        return v


class CollectionUpdate(BaseModel):
    """Schema for updating a collection (partial update)."""
    name: str | None = None
    description: str | None = None
    color: str | None = None

    @field_validator("color")
    @classmethod
    def color_must_be_valid_hex(cls, v: str | None) -> str | None:
        if v is not None and not _HEX_COLOR_RE.match(v):
            raise ValueError("Color must be a valid hex color (#RGB or #RRGGBB)")
        return v


class CollectionResponse(BaseModel):
    """Collection representation returned by the API."""
    id: int
    name: str
    description: str
    color: str | None = None
    model_count: int = 0
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Saved search schemas
# ---------------------------------------------------------------------------


class SavedSearchCreate(BaseModel):
    """Schema for creating a saved search."""
    name: str
    query: str = ""
    filters: dict = {}
    sort_by: str = "created_at"
    sort_order: str = "desc"

    @field_validator("sort_by")
    @classmethod
    def sort_by_must_be_allowed(cls, v: str) -> str:
        if v not in ALLOWED_SORT_BY:
            raise ValueError(
                f"sort_by must be one of: {', '.join(sorted(ALLOWED_SORT_BY))}"
            )
        return v

    @field_validator("sort_order")
    @classmethod
    def sort_order_must_be_asc_or_desc(cls, v: str) -> str:
        if v not in ALLOWED_SORT_ORDER:
            raise ValueError("sort_order must be 'asc' or 'desc'")
        return v


class SavedSearchUpdate(BaseModel):
    """Schema for updating a saved search (partial update)."""
    name: str | None = None
    query: str | None = None
    filters: dict | None = None
    sort_by: str | None = None
    sort_order: str | None = None

    @field_validator("sort_by")
    @classmethod
    def sort_by_must_be_allowed(cls, v: str | None) -> str | None:
        if v is not None and v not in ALLOWED_SORT_BY:
            raise ValueError(
                f"sort_by must be one of: {', '.join(sorted(ALLOWED_SORT_BY))}"
            )
        return v

    @field_validator("sort_order")
    @classmethod
    def sort_order_must_be_asc_or_desc(cls, v: str | None) -> str | None:
        if v is not None and v not in ALLOWED_SORT_ORDER:
            raise ValueError("sort_order must be 'asc' or 'desc'")
        return v


class SavedSearchResponse(BaseModel):
    """Saved search representation returned by the API."""
    id: int
    name: str
    query: str
    filters: dict
    sort_by: str
    sort_order: str
    created_at: str


# ---------------------------------------------------------------------------
# Bulk operation schemas
# ---------------------------------------------------------------------------


class BulkTagRequest(BaseModel):
    """Bulk add tags to multiple models."""
    model_ids: list[int]
    tags: list[str]

    @field_validator("model_ids")
    @classmethod
    def model_ids_must_not_be_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("model_ids must be a non-empty list")
        return v

    @field_validator("tags")
    @classmethod
    def tags_must_not_be_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("tags must be a non-empty list")
        return v


class BulkCategoryRequest(BaseModel):
    """Bulk add categories to multiple models."""
    model_ids: list[int]
    category_ids: list[int]

    @field_validator("model_ids")
    @classmethod
    def model_ids_must_not_be_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("model_ids must be a non-empty list")
        return v

    @field_validator("category_ids")
    @classmethod
    def category_ids_must_not_be_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("category_ids must be a non-empty list")
        return v


class BulkCollectionRequest(BaseModel):
    """Bulk add models to a collection."""
    model_ids: list[int]
    collection_id: int

    @field_validator("model_ids")
    @classmethod
    def model_ids_must_not_be_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("model_ids must be a non-empty list")
        return v


class BulkFavoriteRequest(BaseModel):
    """Bulk favorite/unfavorite models."""
    model_ids: list[int]
    favorite: bool = True

    @field_validator("model_ids")
    @classmethod
    def model_ids_must_not_be_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("model_ids must be a non-empty list")
        return v


class BulkDeleteRequest(BaseModel):
    """Bulk delete models."""
    model_ids: list[int]

    @field_validator("model_ids")
    @classmethod
    def model_ids_must_not_be_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("model_ids must be a non-empty list")
        return v


# ---------------------------------------------------------------------------
# Search schemas
# ---------------------------------------------------------------------------


class SearchResult(BaseModel):
    """Wrapper for full-text search results."""

    models: list[ModelResponse]
    total: int
    query: str


# ---------------------------------------------------------------------------
# Scan status schema
# ---------------------------------------------------------------------------


class ScanStatus(BaseModel):
    """Reports the current state of the file-system scanner."""

    scanning: bool
    total_files: int
    processed_files: int
    last_scan: str | None = None
