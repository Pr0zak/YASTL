"""Utility functions for handling zip archives containing 3D model files.

Provides helpers to list model entries within a zip, extract individual
entries to temporary files or a persistent cache, and manage cached
extractions.
"""

import logging
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)


def is_zip_file(path: str) -> bool:
    """Check whether *path* points to a valid zip archive."""
    return zipfile.is_zipfile(path)


def list_models_in_zip(
    zip_path: str,
    supported_extensions: set[str],
) -> list[str]:
    """Return entry names inside *zip_path* that match supported 3D model extensions.

    Skips directories, ``__MACOSX/`` resource-fork entries, and hidden
    files (names starting with ``.``).  Only inspects top-level entries
    (no recursive descent into nested zips).
    """
    entries: list[str] = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                # Skip directories
                if info.is_dir():
                    continue

                name = info.filename

                # Skip macOS resource forks
                if name.startswith("__MACOSX/"):
                    continue

                # Skip hidden files
                basename = PurePosixPath(name).name
                if basename.startswith("."):
                    continue

                # Check extension
                ext = PurePosixPath(name).suffix.lower()
                if ext in supported_extensions:
                    entries.append(name)
    except zipfile.BadZipFile:
        logger.warning("Corrupt or invalid zip file: %s", zip_path)
    except Exception:
        logger.exception("Error reading zip file: %s", zip_path)

    return entries


def extract_entry_to_temp(zip_path: str, entry_name: str) -> Path:
    """Extract a single entry from a zip to a temporary file.

    The caller is responsible for deleting the returned file when done.
    The temporary file preserves the original extension so that trimesh
    and other loaders can detect the format.

    Raises ``zipfile.BadZipFile`` if the archive is corrupt, or
    ``KeyError`` if *entry_name* is not found in the archive.
    """
    ext = PurePosixPath(entry_name).suffix
    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            data = zf.read(entry_name)
        os.write(fd, data)
    except Exception:
        os.close(fd)
        os.unlink(tmp_path)
        raise
    else:
        os.close(fd)
    return Path(tmp_path)


def _safe_entry_name(entry_name: str) -> bool:
    """Return True if the entry name is safe (no path traversal)."""
    normalized = os.path.normpath(entry_name)
    return not normalized.startswith("..") and not os.path.isabs(normalized)


def ensure_cached(
    zip_path: str,
    entry_name: str,
    cache_dir: str,
    model_id: int,
) -> str:
    """Ensure the zip entry is extracted to the persistent cache.

    Returns the path to the cached file. If the cached file already
    exists and the zip archive has not been modified since the cache was
    written, the existing cache is returned without re-extraction.

    The cache layout is ``{cache_dir}/zip_cache/{model_id}{ext}``.
    """
    ext = PurePosixPath(entry_name).suffix
    cache_subdir = os.path.join(cache_dir, "zip_cache")
    os.makedirs(cache_subdir, exist_ok=True)
    cache_path = os.path.join(cache_subdir, f"{model_id}{ext}")

    # Check if cache is fresh
    if os.path.exists(cache_path):
        try:
            zip_mtime = os.path.getmtime(zip_path)
            cache_mtime = os.path.getmtime(cache_path)
            if zip_mtime <= cache_mtime:
                return cache_path
        except OSError:
            pass  # Re-extract if we can't stat

    # Extract from zip to cache
    with zipfile.ZipFile(zip_path, "r") as zf:
        data = zf.read(entry_name)
    with open(cache_path, "wb") as f:
        f.write(data)

    return cache_path


def cleanup_zip_cache(cache_dir: str, model_id: int, ext: str = "") -> None:
    """Remove the cached extraction for a model.

    If *ext* is not provided, attempts common extensions.
    """
    cache_subdir = os.path.join(cache_dir, "zip_cache")

    if ext:
        cache_path = os.path.join(cache_subdir, f"{model_id}{ext}")
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
            except OSError:
                pass
        return

    # Try to find any cached file for this model_id
    if os.path.isdir(cache_subdir):
        prefix = f"{model_id}."
        try:
            for fname in os.listdir(cache_subdir):
                if fname.startswith(prefix) or fname == str(model_id):
                    try:
                        os.remove(os.path.join(cache_subdir, fname))
                    except OSError:
                        pass
        except OSError:
            pass


def make_zip_file_path(zip_path: str, entry_name: str) -> str:
    """Build the synthetic ``file_path`` stored in the database.

    Format: ``{zip_path}::{entry_name}``
    """
    return f"{zip_path}::{entry_name}"
