from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All settings can be overridden via environment variables with the
    YASTL_ prefix (e.g. YASTL_MODEL_LIBRARY_DB=/custom/path.db).
    """

    # Database
    MODEL_LIBRARY_DB: Path = Path("/data/library.db")

    # Model scanning — optional legacy env var.  Libraries are now managed
    # via the web UI (/api/libraries).  If set, this path is imported as a
    # library on first startup for backwards compatibility.
    MODEL_LIBRARY_SCAN_PATH: Path | None = None

    # Thumbnails
    MODEL_LIBRARY_THUMBNAIL_PATH: Path = Path("/data/thumbnails")

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Supported 3D file extensions
    SUPPORTED_EXTENSIONS: set[str] = {
        ".stl", ".obj", ".gltf", ".glb", ".3mf",
        ".step", ".stp", ".fbx", ".ply", ".dae", ".off"
    }

    model_config = {"env_prefix": "YASTL_"}


settings = Settings()
