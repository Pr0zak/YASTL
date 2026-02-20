# CLAUDE.md

## Project Overview

YASTL (Yet Another STL) is a full-stack web application for browsing, searching, and previewing 3D model files. Python FastAPI backend with a Vue 3 + Three.js frontend served as static files (no build step).

## Tech Stack

- **Backend:** Python 3.12, FastAPI, Uvicorn, aiosqlite (async SQLite with FTS5)
- **Frontend:** Vue 3 + Three.js via CDN (no build tooling, no bundler)
- **3D Processing:** trimesh, numpy-stl, pygltflib, manifold3d
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
  database.py           # SQLite schema, FTS5, async context managers
  api/                  # Route modules (models, search, scan, tags, categories)
  models/schemas.py     # Pydantic request/response schemas
  services/             # Business logic (scanner, processor, hasher, thumbnail, watcher, search)
  static/               # Frontend SPA (index.html, js/, css/)
tests/                  # pytest test suite (13 modules)
  conftest.py           # Shared fixtures (temp dirs, temp DB, async client)
```

## Common Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

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

## Environment Variables

All use the `YASTL_` prefix:

| Variable | Default | Purpose |
|---|---|---|
| `YASTL_MODEL_LIBRARY_DB` | `/data/library.db` | SQLite database path |
| `YASTL_MODEL_LIBRARY_SCAN_PATH` | `/nfs/DATA/3dPrinting` | Directory to scan for 3D models |
| `YASTL_MODEL_LIBRARY_THUMBNAIL_PATH` | `/data/thumbnails` | Thumbnail storage directory |

## Testing

Tests use `pytest-asyncio` with shared fixtures from `tests/conftest.py` that provide temporary directories, an in-memory database, and an async HTTP client. All route tests use `httpx.AsyncClient` against the FastAPI test app.
