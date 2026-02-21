# CLAUDE.md

## Project Overview

YASTL (Yet Another STL) is a full-stack web application for browsing, searching, and previewing 3D model files. Python FastAPI backend with a Vue 3 + Three.js frontend served as static files (no build step).

**Repo:** https://github.com/Pr0zak/YASTL

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, Uvicorn, aiosqlite (async SQLite with FTS5)
- **Frontend:** Vue 3 + Three.js via CDN (no build tooling, no bundler)
- **3D Processing:** trimesh, numpy-stl, pygltflib, manifold3d, scipy
- **trimesh extras:** networkx (3MF scene graphs), lxml (3MF XML parsing), cascadio + gmsh (STEP files, optional)
- **Hashing:** xxhash (xxh128 for duplicate detection)
- **File Watching:** watchdog
- **Testing:** pytest, pytest-asyncio, httpx
- **Linting:** ruff
- **Deployment:** Docker / Docker Compose / Proxmox LXC

## Project Structure

```
app/                    # Main application package
  main.py               # FastAPI app init and lifespan
  config.py             # Pydantic settings (YASTL_ env prefix)
  database.py           # SQLite schema, migrations, FTS5, async context managers
  api/                  # Route modules
    routes_models.py    # Model CRUD, file serving, GLB conversion, tags, categories
    routes_search.py    # Full-text search with filters
    routes_scan.py      # Scan triggers, reindex, repair
    routes_tags.py      # Tag management
    routes_categories.py # Category management
    routes_libraries.py # Library management
    routes_settings.py  # Settings API, thumbnail regeneration
    routes_catalog.py   # Favorites, collections, bulk ops, saved searches
  models/schemas.py     # Pydantic request/response schemas
  services/             # Business logic
    scanner.py          # Directory scanning, auto-categories from dir structure
    processor.py        # 3D metadata extraction (FORMAT_MAP, TRIMESH_SUPPORTED)
    thumbnail.py        # Server-side thumbnail generation (wireframe/solid modes)
    hasher.py           # xxhash-based file hashing
    watcher.py          # watchdog file system observer
    zip_handler.py      # Zip archive support (extraction, caching)
    step_converter.py   # STEP→trimesh conversion (OCP or gmsh backends)
  static/               # Frontend SPA
    index.html          # Main page
    js/app.js           # Vue 3 app, API calls, state management
    js/viewer.js        # Three.js viewer (STL/OBJ/glTF/PLY/3MF loaders)
    css/style.css       # CSS custom properties theming
tests/                  # pytest test suite
  conftest.py           # Shared fixtures (temp dirs, temp DB, async client)
```

## Common Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Install with STEP file support
pip install -e ".[dev,step]"

# Run dev server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run all tests
pytest

# Run a specific test file
pytest tests/test_routes_models.py

# Run tests matching a name pattern
pytest -k test_name

# Lint
ruff check app/ tests/

# Format
ruff format app/ tests/

# Docker
docker compose up -d
```

## Code Conventions

- **Async-first:** All I/O operations use async/await (aiosqlite, FastAPI async endpoints)
- **CPU-bound work:** Use `asyncio.to_thread()` or `loop.run_in_executor()` for trimesh ops
- **Type hints:** Python 3.10+ union syntax (`str | None`, `list[str]`)
- **Naming:** snake_case for functions/variables, PascalCase for classes
- **No ORM:** Direct SQL with parameterized queries (`?` placeholders) and context managers
- **Error handling:** `HTTPException` for API errors; try/except with logging in services
- **Logging:** `logging` module with `"yastl"` root logger name
- **Frontend:** Vue 3 composition API, CSS custom properties for theming, inline SVG icons

## Architecture Notes

- **No build step** for frontend — Vue 3 and Three.js loaded from CDN via ES modules
- **SQLite with WAL mode** — concurrent reads, FTS5 for full-text search (porter tokenizer)
- **Service layer pattern** — business logic in `app/services/`, routes in `app/api/`
- **Background tasks** — directory scanning and file watching run off the request/response thread
- **Server-side thumbnails** — trimesh rendering with Pillow wireframe fallback (256x256 PNG)
- **GLB conversion** — server-side trimesh conversion for formats Three.js can't load natively (3MF, STEP)
- **Zip archive support** — models inside zip files are extracted on demand and cached

## Database Migrations

`database.py` uses a migration pattern for existing databases:
- `SCHEMA_SQL` defines `CREATE TABLE IF NOT EXISTS` — safe for both new and existing DBs
- New columns added via `ALTER TABLE` migrations gated by `PRAGMA table_info` checks
- **Critical:** Indexes on migrated columns go in `_POST_MIGRATION_INDEXES` (created *after* all ALTER TABLE runs), NOT in `SCHEMA_SQL` — otherwise `executescript` fails on existing DBs that don't have the column yet

## Model Status

The `models` table has a `status` column:
- `'active'` — file exists on disk, shown in UI
- `'missing'` — file no longer found on disk (set by scanner during re-scan)

All listing/search API endpoints filter `WHERE status = 'active'` so missing models don't appear in the UI. The scanner marks files as missing on re-scan and reactivates them if they reappear.

## Environment Variables

All use the `YASTL_` prefix:

| Variable | Default | Purpose |
|---|---|---|
| `YASTL_MODEL_LIBRARY_DB` | `/data/library.db` | SQLite database path |
| `YASTL_MODEL_LIBRARY_SCAN_PATH` | *(none)* | Legacy: auto-imports as a library on first start |
| `YASTL_MODEL_LIBRARY_THUMBNAIL_PATH` | `/data/thumbnails` | Thumbnail storage directory |

Libraries (scan directories) are now managed via the web UI Settings page rather than environment variables.

## Testing

Tests use `pytest-asyncio` with `asyncio_mode = "auto"` and shared fixtures from `tests/conftest.py` that provide temporary directories, an in-memory database, and an async HTTP client. All route tests use `httpx.AsyncClient` against the FastAPI test app.

## Deployment (CT333 on PVE3)

- **Host:** Proxmox LXC container CT333 on PVE3 (Debian 12 bookworm)
- **SSH access:** `ssh root@pve3 "pct exec 333 -- <cmd>"`
- **Install path:** `/opt/yastl/` (src/, venv/, data/)
- **Systemd service:** `yastl.service` — restart with `systemctl restart yastl`
- **Database:** `/opt/yastl/data/library.db`
- **Thumbnails:** `/opt/yastl/data/thumbnails/`
- **Model source files:** NFS mount at `/mnt/DATA/3dPrinting`
- **Port:** 8000
- **Resources:** 4GB RAM, 1GB swap (needed for large 3MF processing)
- **Update from main:** `cd /opt/yastl/src && git checkout -- . && git pull origin main && systemctl restart yastl`
