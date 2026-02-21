"""Shared fixtures for YASTL test suite."""

import os
import zipfile
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import init_db


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory for test files."""
    return tmp_path


@pytest.fixture
def db_path(tmp_path):
    """Provide a temporary database path."""
    return str(tmp_path / "test.db")


@pytest_asyncio.fixture
async def db(db_path):
    """Initialize a fresh test database and yield the path."""
    await init_db(db_path)
    yield db_path


@pytest_asyncio.fixture
async def db_conn(db):
    """Yield an open aiosqlite connection to the test database."""
    conn = await aiosqlite.connect(db)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
def scan_path(tmp_path):
    """Create a temporary scan directory with some dummy 3D files."""
    scan_dir = tmp_path / "models"
    scan_dir.mkdir()
    return scan_dir


@pytest.fixture
def thumbnail_path(tmp_path):
    """Create a temporary thumbnail directory."""
    thumb_dir = tmp_path / "thumbnails"
    thumb_dir.mkdir()
    return thumb_dir


def _create_test_stl(path: Path) -> None:
    """Create a minimal binary STL file for testing."""
    import struct

    header = b"\x00" * 80  # 80-byte header
    num_triangles = 1

    # One triangle: normal + 3 vertices + attribute byte count
    normal = struct.pack("<fff", 0.0, 0.0, 1.0)
    v1 = struct.pack("<fff", 0.0, 0.0, 0.0)
    v2 = struct.pack("<fff", 1.0, 0.0, 0.0)
    v3 = struct.pack("<fff", 0.0, 1.0, 0.0)
    attr = struct.pack("<H", 0)

    with open(path, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", num_triangles))
        f.write(normal + v1 + v2 + v3 + attr)


@pytest.fixture
def create_stl():
    """Return a helper function that creates minimal STL files."""
    return _create_test_stl


@pytest_asyncio.fixture
async def test_app(tmp_path):
    """Create a FastAPI test application with a temporary database."""
    db_file = tmp_path / "data" / "test.db"
    db_file.parent.mkdir(parents=True, exist_ok=True)
    scan_dir = tmp_path / "models"
    scan_dir.mkdir()
    thumb_dir = tmp_path / "thumbnails"
    thumb_dir.mkdir()

    # Set environment variables before importing the app
    os.environ["YASTL_MODEL_LIBRARY_DB"] = str(db_file)
    os.environ["YASTL_MODEL_LIBRARY_SCAN_PATH"] = str(scan_dir)
    os.environ["YASTL_MODEL_LIBRARY_THUMBNAIL_PATH"] = str(thumb_dir)

    # Import fresh app - we need to set up the database ourselves
    # since the lifespan may not run in test mode
    from app.main import app

    await init_db(str(db_file))
    app.state.db_path = str(db_file)
    app.state.scanner = None  # No scanner in tests

    yield app, str(db_file), scan_dir, thumb_dir

    # Cleanup env vars
    for key in [
        "YASTL_MODEL_LIBRARY_DB",
        "YASTL_MODEL_LIBRARY_SCAN_PATH",
        "YASTL_MODEL_LIBRARY_THUMBNAIL_PATH",
    ]:
        os.environ.pop(key, None)


@pytest_asyncio.fixture
async def client(test_app):
    """Provide an async HTTP client for the test application."""
    app, db_path, scan_dir, thumb_dir = test_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac._db_path = db_path  # Store for test convenience
        ac._scan_dir = scan_dir
        ac._thumb_dir = thumb_dir
        yield ac


async def insert_test_model(
    db_path: str,
    name: str = "test_model",
    file_path: str = "/tmp/test.stl",
    file_format: str = "STL",
    file_size: int = 1024,
    file_hash: str = "abc123",
    description: str = "",
    zip_path: str | None = None,
    zip_entry: str | None = None,
) -> int:
    """Insert a test model into the database and return its ID."""
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.execute(
            """
            INSERT INTO models (
                name, description, file_path, file_format, file_size,
                file_hash, vertex_count, face_count,
                dimensions_x, dimensions_y, dimensions_z,
                zip_path, zip_entry
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                description,
                file_path,
                file_format,
                file_size,
                file_hash,
                100,
                50,
                10.0,
                20.0,
                30.0,
                zip_path,
                zip_entry,
            ),
        )
        model_id = cursor.lastrowid
        # Add FTS entry
        await conn.execute(
            "INSERT INTO models_fts(rowid, name, description) VALUES (?, ?, ?)",
            (model_id, name, description),
        )
        await conn.commit()
        return model_id


def create_test_zip(
    zip_path: Path,
    entries: dict[str, bytes | None] = None,
    create_stl_entries: list[str] | None = None,
) -> Path:
    """Create a zip file with the given entries for testing.

    Args:
        zip_path: Where to write the zip file.
        entries: Dict of {entry_name: content_bytes}. If content is None,
            a minimal STL file is generated.
        create_stl_entries: List of entry names that should contain STL data.
            Shorthand for entries with auto-generated STL content.

    Returns:
        The path to the created zip file.
    """
    import struct

    def _stl_bytes() -> bytes:
        header = b"\x00" * 80
        normal = struct.pack("<fff", 0.0, 0.0, 1.0)
        v1 = struct.pack("<fff", 0.0, 0.0, 0.0)
        v2 = struct.pack("<fff", 1.0, 0.0, 0.0)
        v3 = struct.pack("<fff", 0.0, 1.0, 0.0)
        attr = struct.pack("<H", 0)
        return header + struct.pack("<I", 1) + normal + v1 + v2 + v3 + attr

    all_entries: dict[str, bytes] = {}
    if entries:
        for name, data in entries.items():
            all_entries[name] = data if data is not None else _stl_bytes()
    if create_stl_entries:
        for name in create_stl_entries:
            all_entries[name] = _stl_bytes()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in all_entries.items():
            zf.writestr(name, data)

    return zip_path
