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
