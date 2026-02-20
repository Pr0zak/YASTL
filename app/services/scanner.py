"""Directory scanner service for discovering and indexing 3D model files.

Walks a configurable directory tree, extracts metadata from each supported
3D file, computes content hashes for duplicate detection, generates preview
thumbnails, and inserts new records into the SQLite database. Categories
are auto-created from the directory hierarchy (folder names become categories).
"""

import asyncio
import logging
import os
from pathlib import Path

import aiosqlite

from app.services import hasher, processor, thumbnail
from app.database import update_fts_for_model

logger = logging.getLogger(__name__)


class Scanner:
    """Scans a directory tree for 3D model files and indexes them in the database.

    Attributes:
        is_scanning: Whether a scan is currently in progress.
        total_files: Total number of supported files discovered on disk.
        processed_files: Number of files processed so far in the current scan.
    """

    def __init__(
        self,
        scan_path: str,
        db_path: str,
        thumbnail_path: str,
        supported_extensions: set[str],
    ) -> None:
        self.scan_path = Path(scan_path)
        self.db_path = db_path
        self.thumbnail_path = thumbnail_path
        self.supported_extensions: set[str] = {
            ext.lower() for ext in supported_extensions
        }

        # Scanning status
        self.is_scanning: bool = False
        self.total_files: int = 0
        self.processed_files: int = 0

        # Prevent concurrent scans
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scan(self) -> dict:
        """Walk the scan_path directory tree and index all supported files.

        Uses an asyncio lock to prevent concurrent scans. If a scan is
        already running the method returns immediately with zeroed stats.

        Returns:
            A stats dictionary with keys:
                total_files  - number of supported files found on disk
                new_files    - number of files newly inserted into the DB
                skipped_files - number of files already present in the DB
                errors       - number of files that caused processing errors
        """
        if self._lock.locked():
            logger.warning(
                "A scan is already in progress -- refusing to start another."
            )
            return {
                "total_files": 0,
                "new_files": 0,
                "skipped_files": 0,
                "errors": 0,
            }

        async with self._lock:
            return await self._run_scan()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_scan(self) -> dict:
        """Core scanning logic executed under the lock."""
        self.is_scanning = True
        self.total_files = 0
        self.processed_files = 0

        stats: dict = {
            "total_files": 0,
            "new_files": 0,
            "skipped_files": 0,
            "errors": 0,
        }

        logger.info("Starting scan of %s", self.scan_path)

        # 1. Discover files on disk (potentially slow -- run in executor)
        loop = asyncio.get_running_loop()
        all_files: list[Path] = await loop.run_in_executor(
            None, self._discover_files
        )

        self.total_files = len(all_files)
        stats["total_files"] = self.total_files
        logger.info("Found %d supported files.", self.total_files)

        # 2. Process each file inside a single database connection
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        try:
            for file_path in all_files:
                try:
                    added = await self._process_file(db, file_path, loop)
                    if added:
                        stats["new_files"] += 1
                    else:
                        stats["skipped_files"] += 1
                except Exception:
                    logger.exception("Error processing %s", file_path)
                    stats["errors"] += 1
                finally:
                    self.processed_files += 1

            await db.commit()
        finally:
            await db.close()

        self.is_scanning = False
        logger.info(
            "Scan complete -- total=%d new=%d skipped=%d errors=%d",
            stats["total_files"],
            stats["new_files"],
            stats["skipped_files"],
            stats["errors"],
        )
        return stats

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------

    def _discover_files(self) -> list[Path]:
        """Synchronously walk the scan_path and return all matching file paths."""
        matches: list[Path] = []
        for dirpath, _dirnames, filenames in os.walk(self.scan_path):
            for fname in filenames:
                if Path(fname).suffix.lower() in self.supported_extensions:
                    matches.append(Path(dirpath) / fname)
        return matches

    # ------------------------------------------------------------------
    # Per-file processing
    # ------------------------------------------------------------------

    async def _process_file(
        self,
        db: aiosqlite.Connection,
        file_path: Path,
        loop: asyncio.AbstractEventLoop,
    ) -> bool:
        """Process a single file.

        Extracts metadata, computes a file hash, generates a thumbnail,
        inserts a new record into the ``models`` table, creates category
        associations derived from the directory hierarchy, and updates
        the FTS index.

        Returns:
            True if the file was newly inserted, False if it was skipped
            because a record with the same ``file_path`` already exists.
        """
        file_path_str = str(file_path)

        # Skip if this file path is already in the database
        cursor = await db.execute(
            "SELECT id FROM models WHERE file_path = ?", (file_path_str,)
        )
        existing = await cursor.fetchone()
        if existing is not None:
            logger.debug("Skipping already-indexed file: %s", file_path_str)
            return False

        # Extract metadata (CPU-bound -- run in executor)
        metadata: dict = await loop.run_in_executor(
            None, processor.extract_metadata, file_path_str
        )

        # Compute file hash (I/O-bound -- run in executor)
        file_hash: str = await loop.run_in_executor(
            None, hasher.compute_file_hash, file_path_str
        )

        # Derive basic fields
        name = file_path.stem
        file_format = metadata.get(
            "file_format",
            file_path.suffix.lower().lstrip(".").upper(),
        )
        file_size = metadata.get("file_size") or os.path.getsize(file_path)

        # Insert model row (we need the id for the thumbnail filename)
        cursor = await db.execute(
            """
            INSERT INTO models (
                name, description, file_path, file_format, file_size,
                file_hash, vertex_count, face_count,
                dimensions_x, dimensions_y, dimensions_z,
                thumbnail_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                "",
                file_path_str,
                file_format,
                file_size,
                file_hash,
                metadata.get("vertex_count"),
                metadata.get("face_count"),
                metadata.get("dimensions_x"),
                metadata.get("dimensions_y"),
                metadata.get("dimensions_z"),
                None,  # thumbnail set after generation
            ),
        )
        model_id = cursor.lastrowid

        # Generate thumbnail (CPU-bound -- run in executor)
        thumb_filename: str | None = await loop.run_in_executor(
            None,
            thumbnail.generate_thumbnail,
            file_path_str,
            self.thumbnail_path,
            model_id,
        )

        # Update the model row with the thumbnail path
        if thumb_filename is not None:
            await db.execute(
                "UPDATE models SET thumbnail_path = ? WHERE id = ?",
                (thumb_filename, model_id),
            )

        # Auto-create categories from directory structure
        await self._create_categories_from_path(db, file_path, model_id)

        # Update FTS index for this model
        await update_fts_for_model(db, model_id)

        logger.debug("Indexed new model id=%d  %s", model_id, file_path_str)
        return True

    # ------------------------------------------------------------------
    # Category helpers
    # ------------------------------------------------------------------

    async def _create_categories_from_path(
        self,
        db: aiosqlite.Connection,
        file_path: Path,
        model_id: int,
    ) -> None:
        """Derive categories from the relative directory path.

        For a file at ``<scan_path>/Figurines/Animals/dragon.stl`` the
        categories ``Figurines`` and ``Animals`` (child of ``Figurines``)
        are created and associated with the model.
        """
        try:
            rel = file_path.parent.relative_to(self.scan_path)
        except ValueError:
            return

        parts = rel.parts
        if not parts:
            return

        parent_id: int | None = None
        for part in parts:
            # Upsert category
            cursor = await db.execute(
                """
                SELECT id FROM categories
                WHERE name = ? AND (parent_id IS ? OR parent_id = ?)
                """,
                (part, parent_id, parent_id),
            )
            row = await cursor.fetchone()

            if row is not None:
                category_id = row[0] if not isinstance(row, dict) else row["id"]
            else:
                cursor = await db.execute(
                    "INSERT INTO categories (name, parent_id) VALUES (?, ?)",
                    (part, parent_id),
                )
                category_id = cursor.lastrowid

            # Link category to model (ignore duplicate)
            await db.execute(
                """
                INSERT OR IGNORE INTO model_categories (model_id, category_id)
                VALUES (?, ?)
                """,
                (model_id, category_id),
            )
            parent_id = category_id
