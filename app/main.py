"""YASTL - Yet Another STL: 3D Model Library"""

import logging
import os
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes_bulk import router as bulk_router
from app.api.routes_categories import router as categories_router
from app.api.routes_import import router as import_router
from app.api.routes_collections import router as collections_router
from app.api.routes_favorites import router as favorites_router
from app.api.routes_libraries import router as libraries_router
from app.api.routes_models import router as models_router
from app.api.routes_model_files import router as model_files_router
from app.api.routes_model_tags import router as model_tags_router
from app.api.routes_model_categories import router as model_categories_router
from app.api.routes_saved_searches import router as saved_searches_router
from app.api.routes_scan import router as scan_router
from app.api.routes_search import router as search_router
from app.api.routes_settings import router as settings_router
from app.api.routes_status import router as status_router
from app.api.routes_tags import router as tags_router
from app.api.routes_update import router as update_router
from app.config import settings
from app.database import init_db
from app.services.scanner import Scanner
from app.services.updater import Updater
from app.services.watcher import ModelFileWatcher

logger = logging.getLogger("yastl")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def _migrate_legacy_scan_path(db_path: str, scan_path: str) -> None:
    """Import the legacy YASTL_MODEL_LIBRARY_SCAN_PATH env var as a library.

    For backwards compatibility, if the env var is set we create a library
    entry for it on first start (only if no library with that path exists).
    """
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id FROM libraries WHERE path = ?", (str(scan_path),)
        )
        if await cursor.fetchone() is None:
            await db.execute(
                "INSERT INTO libraries (name, path) VALUES (?, ?)",
                ("Default Library", str(scan_path)),
            )
            await db.commit()
            logger.info("Migrated legacy scan path as library: %s", scan_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("Starting YASTL - Yet Another STL")
    logger.info("Database: %s", settings.MODEL_LIBRARY_DB)
    logger.info("Thumbnail path: %s", settings.MODEL_LIBRARY_THUMBNAIL_PATH)

    # Ensure directories exist
    os.makedirs(os.path.dirname(settings.MODEL_LIBRARY_DB), exist_ok=True)
    os.makedirs(settings.MODEL_LIBRARY_THUMBNAIL_PATH, exist_ok=True)

    # Initialize database
    await init_db(settings.MODEL_LIBRARY_DB)
    app.state.db_path = settings.MODEL_LIBRARY_DB

    # Backwards compat: import legacy env-var scan path as a library
    if settings.MODEL_LIBRARY_SCAN_PATH is not None:
        await _migrate_legacy_scan_path(
            settings.MODEL_LIBRARY_DB,
            settings.MODEL_LIBRARY_SCAN_PATH,
        )

    # Initialize scanner (reads libraries from DB)
    app.state.scanner = Scanner(
        db_path=settings.MODEL_LIBRARY_DB,
        thumbnail_path=settings.MODEL_LIBRARY_THUMBNAIL_PATH,
        supported_extensions=settings.SUPPORTED_EXTENSIONS,
    )

    # Initialize and start file watcher
    watcher = ModelFileWatcher(
        db_path=settings.MODEL_LIBRARY_DB,
        thumbnail_path=settings.MODEL_LIBRARY_THUMBNAIL_PATH,
        supported_extensions=settings.SUPPORTED_EXTENSIONS,
    )
    app.state.watcher = watcher

    try:
        watcher.start()
        # Watch all existing library paths
        async with aiosqlite.connect(str(settings.MODEL_LIBRARY_DB)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT path FROM libraries")
            rows = await cursor.fetchall()
            for row in rows:
                lib_path = dict(row)["path"]
                if os.path.isdir(lib_path):
                    watcher.watch_path(lib_path)
                    logger.info("File watcher watching: %s", lib_path)
    except Exception as e:
        logger.warning("Could not start file watcher: %s", e)

    # Initialize update service
    app.state.updater = Updater(app_version="0.1.0")

    yield

    # Shutdown
    logger.info("Shutting down YASTL")
    try:
        watcher.stop()
    except Exception:
        pass


app = FastAPI(
    title="YASTL",
    description="Yet Another STL - 3D Model Library",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(libraries_router)
app.include_router(models_router)
app.include_router(model_files_router)
app.include_router(model_tags_router)
app.include_router(model_categories_router)
app.include_router(tags_router)
app.include_router(categories_router)
app.include_router(scan_router)
app.include_router(search_router)
app.include_router(settings_router)
app.include_router(update_router)
app.include_router(status_router)
app.include_router(favorites_router)
app.include_router(collections_router)
app.include_router(saved_searches_router)
app.include_router(bulk_router)
app.include_router(import_router)

# Serve static files (legacy CDN frontend and favicon/assets)
static_dir = os.path.join(os.path.dirname(__file__), "static")
dist_dir = os.path.join(static_dir, "dist")

app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Serve Vite build assets when the dist directory exists
if os.path.isdir(dist_dir):
    _dist_assets = os.path.join(dist_dir, "assets")
    if os.path.isdir(_dist_assets):
        app.mount("/assets", StaticFiles(directory=_dist_assets), name="dist-assets")

# Serve thumbnails as static files (avoids DB lookup per request)
# check_dir=False because the directory is created in the lifespan handler.
app.mount(
    "/thumbnails",
    StaticFiles(directory=str(settings.MODEL_LIBRARY_THUMBNAIL_PATH), check_dir=False),
    name="thumbnails",
)


@app.get("/", include_in_schema=False)
async def root():
    """Serve the main frontend page.

    Serves the Vite build output when available, otherwise falls back
    to the legacy CDN-based frontend.
    """
    dist_index = os.path.join(dist_dir, "index.html")
    if os.path.isfile(dist_index):
        return FileResponse(dist_index)
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "app": "yastl", "version": "0.1.0"}
