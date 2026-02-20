"""YASTL - Yet Another STL: 3D Model Library"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes_categories import router as categories_router
from app.api.routes_models import router as models_router
from app.api.routes_scan import router as scan_router
from app.api.routes_search import router as search_router
from app.api.routes_tags import router as tags_router
from app.config import settings
from app.database import init_db
from app.services.scanner import Scanner
from app.services.watcher import ModelFileWatcher

logger = logging.getLogger("yastl")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("Starting YASTL - Yet Another STL")
    logger.info("Database: %s", settings.MODEL_LIBRARY_DB)
    logger.info("Scan path: %s", settings.MODEL_LIBRARY_SCAN_PATH)
    logger.info("Thumbnail path: %s", settings.MODEL_LIBRARY_THUMBNAIL_PATH)

    # Ensure directories exist
    os.makedirs(os.path.dirname(settings.MODEL_LIBRARY_DB), exist_ok=True)
    os.makedirs(settings.MODEL_LIBRARY_THUMBNAIL_PATH, exist_ok=True)

    # Initialize database
    await init_db(settings.MODEL_LIBRARY_DB)
    app.state.db_path = settings.MODEL_LIBRARY_DB

    # Initialize scanner
    app.state.scanner = Scanner(
        scan_path=settings.MODEL_LIBRARY_SCAN_PATH,
        db_path=settings.MODEL_LIBRARY_DB,
        thumbnail_path=settings.MODEL_LIBRARY_THUMBNAIL_PATH,
        supported_extensions=settings.SUPPORTED_EXTENSIONS,
    )

    # Initialize and start file watcher
    watcher = ModelFileWatcher(
        scan_path=settings.MODEL_LIBRARY_SCAN_PATH,
        db_path=settings.MODEL_LIBRARY_DB,
        thumbnail_path=settings.MODEL_LIBRARY_THUMBNAIL_PATH,
        supported_extensions=settings.SUPPORTED_EXTENSIONS,
    )
    app.state.watcher = watcher

    try:
        watcher.start()
        logger.info("File watcher started for: %s", settings.MODEL_LIBRARY_SCAN_PATH)
    except Exception as e:
        logger.warning("Could not start file watcher: %s", e)

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

app.include_router(models_router)
app.include_router(tags_router)
app.include_router(categories_router)
app.include_router(scan_router)
app.include_router(search_router)

# Serve static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
async def root():
    """Serve the main frontend page."""
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "app": "yastl", "version": "0.1.0"}
