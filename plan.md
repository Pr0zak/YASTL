# Robust Catalog System — Implementation Plan

## Scope

Add four major features to YASTL's organization system:
1. **Favorites** — star/unstar models for quick access
2. **Collections** — user-created groupings (like playlists)
3. **Advanced Filtering** — multi-tag, multi-category, sorting, saved searches
4. **Bulk Operations** — select multiple models and apply actions

Manual organization only. Full frontend UI. Focus on better browsing/discovery.

---

## Phase 1: Database Schema Changes (`app/database.py`)

### New tables:

```sql
-- Favorites: simple boolean-style via junction
favorites (
    model_id INTEGER PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)

-- Collections
collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    color TEXT DEFAULT NULL,          -- hex color for UI badge
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)

-- Collection membership (ordered)
collection_models (
    collection_id INTEGER REFERENCES collections(id) ON DELETE CASCADE,
    model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
    position INTEGER DEFAULT 0,       -- for manual ordering within collection
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (collection_id, model_id)
)

-- Saved searches
saved_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    query TEXT DEFAULT '',            -- FTS query string
    filters TEXT DEFAULT '{}',        -- JSON: {formats:[], tags:[], categories:[], favorites_only: bool, collection_id: int}
    sort_by TEXT DEFAULT 'created_at',
    sort_order TEXT DEFAULT 'desc',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### Migration strategy:
- Add new tables in `initialize_database()` using `CREATE TABLE IF NOT EXISTS`
- No changes to existing tables (backwards compatible)

---

## Phase 2: Pydantic Schemas (`app/models/schemas.py`)

### New schemas:

```python
# Collections
CollectionCreate(name: str, description: str = "", color: str | None = None)
CollectionUpdate(name: str | None = None, description: str | None = None, color: str | None = None)
CollectionResponse(id: int, name: str, description: str, color: str | None, model_count: int, created_at: datetime, updated_at: datetime)

# Saved searches
SavedSearchCreate(name: str, query: str = "", filters: dict = {}, sort_by: str = "created_at", sort_order: str = "desc")
SavedSearchResponse(id: int, name: str, query: str, filters: dict, sort_by: str, sort_order: str, created_at: datetime)

# Bulk operations
BulkTagRequest(model_ids: list[int], tags: list[str])
BulkCategoryRequest(model_ids: list[int], category_ids: list[int])
BulkCollectionRequest(model_ids: list[int], collection_id: int)
BulkFavoriteRequest(model_ids: list[int], favorite: bool)
BulkDeleteRequest(model_ids: list[int])
```

### Extend existing:
- `ModelResponse` — add `is_favorite: bool` field

---

## Phase 3: API Routes

### 3a. Favorites (`app/api/routes_favorites.py` — new file)
- `GET /api/favorites` — list favorited models (with pagination, same format as /api/models)
- `POST /api/models/{model_id}/favorite` — add to favorites
- `DELETE /api/models/{model_id}/favorite` — remove from favorites

### 3b. Collections (`app/api/routes_collections.py` — new file)
- `GET /api/collections` — list all collections with model counts
- `POST /api/collections` — create collection
- `GET /api/collections/{id}` — get collection detail with models
- `PUT /api/collections/{id}` — update collection metadata
- `DELETE /api/collections/{id}` — delete collection (models unaffected)
- `POST /api/collections/{id}/models` — add models to collection (body: `{model_ids: [1,2,3]}`)
- `DELETE /api/collections/{id}/models/{model_id}` — remove model from collection
- `PUT /api/collections/{id}/models/reorder` — reorder models (body: `{model_ids: [3,1,2]}`)

### 3c. Enhanced Models Route (`app/api/routes_models.py` — modify)
- Extend `GET /api/models` query params:
  - `tags` (comma-separated, multiple) — AND logic
  - `categories` (comma-separated, multiple)
  - `collection` — filter by collection ID
  - `favorites_only` — boolean
  - `sort_by` — `name`, `created_at`, `updated_at`, `file_size`, `vertex_count`, `face_count`
  - `sort_order` — `asc` or `desc`
- Add `is_favorite` to model response hydration

### 3d. Saved Searches (`app/api/routes_saved_searches.py` — new file)
- `GET /api/saved-searches` — list all saved searches
- `POST /api/saved-searches` — create saved search
- `PUT /api/saved-searches/{id}` — update
- `DELETE /api/saved-searches/{id}` — delete

### 3e. Bulk Operations (`app/api/routes_bulk.py` — new file)
- `POST /api/bulk/tags` — add tags to multiple models
- `POST /api/bulk/categories` — add categories to multiple models
- `POST /api/bulk/collections` — add models to a collection
- `POST /api/bulk/favorite` — favorite/unfavorite multiple models
- `POST /api/bulk/delete` — delete multiple models

### 3f. Register new routes in `app/main.py`

---

## Phase 4: Search Service Updates (`app/services/search.py`)

- Support multi-tag filtering (AND logic — model must have ALL tags)
- Support multi-category filtering (OR logic — model in ANY category)
- Support `favorites_only` filter
- Support `collection_id` filter
- Support `sort_by` and `sort_order` parameters
- Integrate with saved search deserialization

---

## Phase 5: Frontend — Full UI (`app/static/`)

### 5a. State additions (`js/app.js`)
```javascript
// New reactive state
favorites: new Set(),         // Set of favorited model IDs for quick lookup
collections: [],              // All collections
selectedCollection: null,     // Currently viewed collection
savedSearches: [],            // Saved search presets
selectionMode: false,         // Bulk selection toggle
selectedModels: new Set(),    // Set of selected model IDs
filters: {
    format: '',
    tags: [],                 // CHANGE: array instead of single string
    categories: [],           // CHANGE: array instead of single string
    collection: null,
    favoritesOnly: false,
    sortBy: 'created_at',
    sortOrder: 'desc'
}
```

### 5b. UI Components

**Favorites:**
- Heart/star icon on each model card (toggle on click)
- "Favorites" entry in sidebar navigation
- Favorite count badge in sidebar

**Collections:**
- Sidebar section listing collections with model counts and color badges
- "New Collection" button
- Collection detail view (shows models in collection with ordering)
- Drag-to-reorder within collection (stretch goal — can use position number for v1)
- Right-click or "..." menu on models to "Add to Collection"

**Advanced Filter Panel:**
- Expandable filter panel below search bar
- Multi-select tag chips (click multiple tags to filter)
- Multi-select category checkboxes from tree
- Sort dropdown (Name, Date Added, Date Modified, File Size, Vertices, Faces)
- Sort direction toggle (asc/desc)
- "Save Search" button — saves current query + all filters as a named preset
- Saved searches listed in sidebar (click to restore)
- Active filter summary with "clear" buttons

**Bulk Selection:**
- "Select" toggle button in toolbar
- When active: checkboxes appear on model cards
- Select All / Deselect All
- Floating action bar at bottom: "Tag", "Categorize", "Add to Collection", "Favorite", "Delete"
- Each action opens a small modal/popover for input

### 5c. CSS updates (`css/style.css`)
- Styles for selection mode (checkbox overlay, selected state highlight)
- Collection color badges
- Filter panel layout
- Floating bulk action bar
- Favorite heart icon animation
- Saved search sidebar items

---

## Phase 6: Tests

### New test files:
- `tests/test_routes_favorites.py` — CRUD favorites, hydration in model response
- `tests/test_routes_collections.py` — CRUD collections, add/remove models, reorder
- `tests/test_routes_saved_searches.py` — CRUD saved searches
- `tests/test_routes_bulk.py` — bulk tag, categorize, favorite, delete, collection add
- `tests/test_advanced_filtering.py` — multi-tag, multi-category, sort, combined filters

### Extend existing:
- `tests/test_routes_models.py` — test `is_favorite` field, new query params

---

## Implementation Order

1. **Database schema** — new tables (Phase 1)
2. **Schemas** — Pydantic models (Phase 2)
3. **Favorites** — routes + tests (Phase 3a + 6)
4. **Collections** — routes + tests (Phase 3b + 6)
5. **Advanced filtering** — models route changes + search service + tests (Phase 3c + 4 + 6)
6. **Saved searches** — routes + tests (Phase 3d + 6)
7. **Bulk operations** — routes + tests (Phase 3e + 6)
8. **Register routes** in main.py (Phase 3f)
9. **Frontend** — all UI changes (Phase 5)
10. **Lint + full test suite** — verify everything passes

---

## Files to Create
- `app/api/routes_favorites.py`
- `app/api/routes_collections.py`
- `app/api/routes_saved_searches.py`
- `app/api/routes_bulk.py`
- `tests/test_routes_favorites.py`
- `tests/test_routes_collections.py`
- `tests/test_routes_saved_searches.py`
- `tests/test_routes_bulk.py`
- `tests/test_advanced_filtering.py`

## Files to Modify
- `app/database.py` — new tables
- `app/models/schemas.py` — new + extended schemas
- `app/api/routes_models.py` — advanced filtering params, is_favorite
- `app/services/search.py` — multi-filter, sort support
- `app/main.py` — register new routers
- `app/static/js/app.js` — all frontend features
- `app/static/css/style.css` — new UI styles
- `app/static/index.html` — new HTML structure for collections panel, filter panel, bulk bar
- `tests/test_routes_models.py` — extended filtering tests
