from pydantic import BaseModel


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


class CollectionUpdate(BaseModel):
    """Schema for updating a collection (partial update)."""
    name: str | None = None
    description: str | None = None
    color: str | None = None


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


class SavedSearchUpdate(BaseModel):
    """Schema for updating a saved search (partial update)."""
    name: str | None = None
    query: str | None = None
    filters: dict | None = None
    sort_by: str | None = None
    sort_order: str | None = None


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


class BulkCategoryRequest(BaseModel):
    """Bulk add categories to multiple models."""
    model_ids: list[int]
    category_ids: list[int]


class BulkCollectionRequest(BaseModel):
    """Bulk add models to a collection."""
    model_ids: list[int]
    collection_id: int


class BulkFavoriteRequest(BaseModel):
    """Bulk favorite/unfavorite models."""
    model_ids: list[int]
    favorite: bool = True


class BulkDeleteRequest(BaseModel):
    """Bulk delete models."""
    model_ids: list[int]


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
