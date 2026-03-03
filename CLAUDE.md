# CLAUDE.md

## Project Overview

YASTL (Yet Another STL) is a full-stack web application for browsing, searching, and previewing 3D model files. Python FastAPI backend with a Vue 3 + Three.js frontend (Vite SFC build).

**Repo:** https://github.com/Pr0zak/YASTL

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, Uvicorn, aiosqlite (async SQLite with FTS5)
- **Frontend:** Vue 3 + Three.js — Vite SFC build (`frontend/` → `app/static/dist/`)
- **Build:** Vite 6, vue-tsc, ESLint
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
  main.py               # FastAPI app init and lifespan (serves Vite dist/)
  config.py             # Pydantic settings (YASTL_ env prefix)
  workers.py            # Shared ProcessPoolExecutor + memory diagnostics
  database.py           # Runtime DB logic (imports schema from database_schema.py)
  database_schema.py    # SCHEMA_SQL, FTS_SCHEMA_SQL, migrations, indexes
  api/                  # Route modules (split into focused files)
    _helpers.py         # Shared route helpers (_get_db_path, _fetch_model_with_relations, open_db)
    routes_models.py    # Model CRUD (name, description, source_url)
    routes_model_files.py # File serving, GLB conversion, thumbnails
    routes_model_tags.py  # Per-model tag operations
    routes_model_categories.py # Per-model category operations
    routes_search.py    # Full-text search with filters
    routes_scan.py      # Scan triggers (full/update/single-library), cancel, reindex, repair
    routes_tags.py      # Tag management
    routes_categories.py # Category management
    routes_libraries.py # Library management
    routes_import.py    # URL import + file upload (source_url, description metadata)
    routes_settings.py  # Settings API, thumbnail regeneration, bed config
    routes_stats.py     # Library statistics dashboard (GET /api/stats)
    routes_status.py    # System health status (scanner, watcher, DB, thumbnails)
    routes_catalog.py   # Favorites, collections, bulk ops, saved searches
    routes_update.py    # Git-based update check and apply
  models/schemas.py     # Pydantic request/response schemas
  services/             # Business logic (split into focused modules)
    scanner.py          # Directory scanning, auto-categories from dir structure
    processor.py        # 3D metadata extraction (FORMAT_MAP, TRIMESH_SUPPORTED)
    importer.py         # Import pipeline (URL download, zip handling)
    scrapers.py         # Site detection + metadata scraping (6 sites)
    downloader.py       # File download + S3 detection
    tagger.py           # Auto-tag suggestions from URLs and filenames
    import_credentials.py # Credential CRUD + masking
    thumbnail.py        # Thumbnail generation entry point
    thumbnail_render.py # Rendering backends (wireframe, solid)
    thumbnail_mesh.py   # Mesh collection + simplification
    hasher.py           # xxhash-based file hashing
    watcher.py          # watchdog file system observer
    zip_handler.py      # Zip archive support (extraction, caching)
    step_converter.py   # STEP→trimesh conversion (OCP or gmsh backends)
  static/               # Static file root
    dist/               # Vite build output
frontend/               # Vite + Vue SFC source
  src/
    App.vue             # Main Vue app component
    api.js              # API wrapper functions
    components/         # Vue SFC components (DetailPanel, ImportModal, SettingsPanel, etc.)
    composables/        # Vue composables (useImport, useViewer, etc.)
  vite.config.js        # Vite config (builds to ../app/static/dist/)
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

# Build Vite frontend
cd frontend && npm run build

# Docker
docker compose up -d
```

## Code Conventions

- **Async-first:** All I/O operations use async/await (aiosqlite, FastAPI async endpoints)
- **CPU-bound work:** Use `loop.run_in_executor(get_pool(), ...)` with the shared `ProcessPoolExecutor` from `app.workers` for CPU-bound ops (trimesh, hashing); use default thread pool (`None`) for I/O-bound work
- **Type hints:** Python 3.10+ union syntax (`str | None`, `list[str]`)
- **Naming:** snake_case for functions/variables, PascalCase for classes
- **No ORM:** Direct SQL with parameterized queries (`?` placeholders) and context managers
- **Error handling:** `HTTPException` for API errors; try/except with logging in services
- **Logging:** `logging` module with `"yastl"` root logger name
- **Frontend:** Vue 3 composition API (SFC), CSS custom properties for theming, inline SVG icons

## Architecture Notes

- **Vite frontend** — SFC build in `frontend/` outputs to `app/static/dist/`; `main.py` serves dist/. Build filenames include `Date.now()` timestamp via rollup config to guarantee unique filenames on every deploy (prevents browser cache collisions). `index.html` is served with `Cache-Control: no-store` to prevent browsers from caching stale asset references.
- **SQLite with WAL mode** — concurrent reads, FTS5 for full-text search (porter tokenizer)
- **Service layer pattern** — business logic in `app/services/`, routes in `app/api/`
- **Process pool** — `app/workers.py` manages a shared `ProcessPoolExecutor(max_workers=1)` created at startup. CPU-bound work (thumbnail rendering, metadata extraction, file hashing) uses `loop.run_in_executor(get_pool(), ...)` to bypass the GIL — CPU work runs on core 1 while the asyncio event loop stays responsive on core 0. **Only 1 worker** to avoid OOM; each worker process loads ~300MB of Python+trimesh+numpy — 2 workers caused OOM when CT333 had 4GB RAM (now 8GB but kept at 1 for safety). I/O-bound work (zip extraction, file discovery) stays on the default thread pool.
- **Worker recycling** — `app/workers.py` provides `tick_job()` and `maybe_recycle()`. After every 25 CPU-bound jobs the worker pool is shut down and recreated via `recycle_pool()`, shedding accumulated memory from trimesh/numpy loads. All CPU-bound callers (scanner, thumbnail regen) call `tick_job()` after each job and `maybe_recycle()` after thumbnail generation. Always use `get_pool()` fresh before each `run_in_executor` call (never cache the pool reference) since recycling replaces the pool instance.
- **Combined metadata+thumbnail extraction** — `processor.process_and_thumbnail()` performs a single `trimesh.load()` call and extracts both metadata (vertex/face counts, dimensions) and generates the thumbnail from the same in-memory object. The scanner uses this for new files to halve peak memory usage (previously two separate loads could push the worker past `RLIMIT_AS`). Moved files use `extract_metadata()` alone (no thumbnail regen needed). Models taking >10s trigger a forced `recycle_pool()`.
- **Memory cleanup** — `processor.py` and `thumbnail.py` wrap trimesh loads in try/finally blocks that clear `loaded._cache`, iterate scene geometries to clear their caches, `del` references, and call `gc.collect()`. This prevents Python's allocator from holding freed numpy arrays indefinitely.
- **Memory diagnostics** — `app/workers.py` provides `log_memory(context)` which logs process RSS + system available/total/swap via `/proc/meminfo`. Called at scan start/end, thumbnail regen start/end, every 50 models during regen, on worker recycle, and on any model taking >10s (logged as `WARNING: Slow thumbnail: model <id> took <N>s <path>`). View with `journalctl -u yastl | grep -E 'Memory:|Slow thumbnail|recycle'`.
- **Slow request logging** — `main.py` middleware logs a `WARNING` for any HTTP request taking >1s, including method, path, duration, and status code. View with `journalctl -u yastl | grep 'Slow request'`.
- **Incremental scan commits** — the scanner commits to the database after each new/moved file is processed, so progress is preserved if the service restarts mid-scan. Previously, a single `db.commit()` at the end of the scan meant all progress was lost on restart. Progress is logged every 100 files.
- **Background tasks** — directory scanning and file watching run off the request/response thread
- **Server-side thumbnails** — trimesh rendering with Pillow wireframe fallback (256x256 PNG)
- **GLB conversion** — server-side trimesh conversion for formats Three.js can't load natively (3MF, STEP). GLB preview cache in `preview_cache/` directory is capped at 500 MB with LRU eviction by mtime.
- **Zip archive support** — models inside zip files are extracted on demand and cached; shown with purple ZIP badge in UI. Multi-model zips are grouped into a single card with a count badge; clicking drills into individual models with breadcrumb navigation.
- **Unified collections** — regular and smart collections share a single sidebar section. Every collection can optionally have smart filter rules. Collections without rules are manual (add models explicitly); collections with rules auto-match models. `is_smart` flag is auto-detected from rules content.
- **Thumbnail tracking** — `thumbnail_mode`, `thumbnail_quality`, `thumbnail_generated_at` columns track generation settings per model; UI shows colored status dots (green=current, amber=stale, red=missing)
- **Stats & status** — `/api/stats` returns aggregate library statistics; `/api/status` returns system health. Both displayed in a unified Stats modal (bar chart icon in navbar with health dot). Replaced the old separate status dropdown.
- **Print bed overlay** — configurable bed dimensions stored as settings (`bed_width`, `bed_depth`, `bed_height`, `bed_shape`, `bed_enabled`). Viewer renders a wireframe build volume at correct scale; shows "Fits" / "Too large" indicator. Presets for common printers (Ender 3, Prusa MK3S+, Bambu Lab P1S/A1, Voron 2.4).
- **Detail panel tabs** — Model detail overlay uses a tabbed layout (Info, Tags, More) to reduce clutter; file details (vertices, faces, dimensions, path, hash) are collapsed by default behind a toggle; Download/Delete actions are pinned at the bottom across all tabs
- **Theme-aware 3D viewer** — `useViewer.js` exposes `setViewerTheme(theme)` which updates the Three.js scene background and grid colors. `initViewer()` accepts an optional theme parameter. `App.vue` passes `colorTheme` on init and calls `setViewerTheme()` when the theme changes while the viewer is open. Dark theme: navy background (`0x12182a`), blue grid. Light theme: light gray background (`0xf5f5f5`), subtle gray grid.
- **File upload drag-and-drop** — Import modal file upload area supports both click-to-browse and drag-and-drop; drop events feed `dataTransfer.files` into `onFilesSelected` via a synthetic event
- **Error tracking** — Files that fail during scanning (oversized >80MB, worker crash/OOM, processing errors) are inserted as `status='error'` models with `error_reason` text. Auto-added to a "Failed to Process" collection (red, `#dc3545`). Shown with red error badge in the collection view.
- **Single-library scan** — `POST /api/scan?library_id=N` scans only one library. Settings UI has a per-library rescan button. `apiTriggerScan(mode, libraryId)` in `api.js` supports the optional `libraryId` param.
- **Scan cancellation** — `POST /api/scan/cancel` sets `_cancel_requested` flag on the scanner. Cancellation is checked in all phases: file discovery, zip expansion, per-library processing, zip metadata extraction, and per-file iteration. Orphan reconciliation is skipped on cancel to avoid false "missing" status. UI shows a cancel button (X) in the scan progress banner.
- **Busy timeout** — `_helpers.py` provides `open_db()` async context manager with `PRAGMA busy_timeout = 5000` to prevent SQLite lock contention when the scanner holds a write connection. Scanner also sets busy_timeout on its own connection.
- **PWA support** — `manifest.json` (served at `/manifest.json` with `application/manifest+json`), minimal service worker (`sw.js` at root scope), and PNG icons (192x192 + 512x512 in `app/static/`). Manifest includes both `any` and `maskable` purpose icons. SW has install/activate/fetch handlers but no caching (app requires live API). iOS meta tags (`apple-mobile-web-app-capable`, etc.) in `index.html`. On LAN without HTTPS, use Chrome flag `chrome://flags/#unsafely-treat-insecure-origin-as-secure` with the server origin to enable PWA install.

## Database Migrations

`database.py` uses a migration pattern for existing databases:
- `SCHEMA_SQL` defines `CREATE TABLE IF NOT EXISTS` — safe for both new and existing DBs
- New columns added via `ALTER TABLE` migrations gated by `PRAGMA table_info` checks
- **Critical:** Indexes on migrated columns go in `_POST_MIGRATION_INDEXES` (created *after* all ALTER TABLE runs), NOT in `SCHEMA_SQL` — otherwise `executescript` fails on existing DBs that don't have the column yet

## Model Status

The `models` table has a `status` column:
- `'active'` — file exists on disk, shown in UI
- `'missing'` — file no longer found on disk (set by scanner during re-scan)
- `'error'` — file failed to process (oversized, worker crash, processing error); stored with `error_reason` column

All listing/search API endpoints filter `WHERE status = 'active'` by default so missing/error models don't appear in normal browsing. The `GET /api/models` endpoint accepts an optional `status` query param (`active`, `error`, or `all`). Error models are auto-added to a "Failed to Process" collection.

## Thumbnail Tracking

The `models` table has thumbnail tracking columns:
- `thumbnail_mode` — rendering mode used (`wireframe` or `solid`)
- `thumbnail_quality` — rendering quality used (always `fast` — quality option removed from UI)
- `thumbnail_generated_at` — timestamp of last generation

The frontend compares `thumbnail_mode` against the current setting to show status dots on model cards. Bulk regeneration via `POST /api/settings/regenerate-thumbnails` tracks progress in a module-level dict, exposed via `GET /api/settings/regenerate-thumbnails/status`.

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

## Deployment (CT333 on PVE4)

- **Host:** Proxmox LXC container CT333 on PVE4 (Debian 12 bookworm)
- **SSH access:** `ssh root@pve4 "lxc-attach -n 333 -- <cmd>"` (preferred over `pct exec` which can hang)
- **Install path:** `/opt/yastl/` (src/, venv/, data/)
- **Editable install:** Package MUST be installed with `pip install -e .` (editable mode) so Python imports from the source tree. Non-editable `pip install .` copies files to site-packages and `git pull`/`npm run build` changes won't take effect. The `yastl-update` script and in-app updater both use `-e`.
- **Systemd service:** `yastl.service` — restart with `systemctl restart yastl`
- **Database:** `/opt/yastl/data/library.db`
- **Thumbnails:** `/opt/yastl/data/thumbnails/`
- **Model source files:** NFS mount at `/mnt/DATA/3dPrinting`
- **Port:** 8000
- **Resources:** 8GB RAM (previously 4GB, upgraded to avoid OOM)
- **Update from main:** `yastl-update` script (git pull + npm build + pip install -e + restart)
- **Manual update:** `cd /opt/yastl/src && git checkout -- . && git pull origin main && cd frontend && npm run build && cd .. && /opt/yastl/venv/bin/pip install -e . && systemctl restart yastl`
