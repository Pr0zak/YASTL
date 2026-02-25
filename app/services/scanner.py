"""Directory scanner service for discovering and indexing 3D model files.

Walks a configurable directory tree, extracts metadata from each supported
3D file, computes content hashes for duplicate detection, generates preview
thumbnails, and inserts new records into the SQLite database. Categories
are auto-created from the directory hierarchy (folder names become categories).
"""

import asyncio
import logging
import os
import time
from pathlib import Path

import aiosqlite

from app.services import hasher, processor, thumbnail
from app.services import zip_handler
from app.services.importer import extract_zip_metadata, extract_folder_metadata
from app.database import get_setting, update_fts_for_model
from app.workers import get_pool, log_memory, tick_job, maybe_recycle

logger = logging.getLogger(__name__)

# Files larger than this are skipped during scanning to prevent OOM.
# trimesh can expand a 330MB 3MF to 4-6GB in memory, which crashes the
# single-worker process pool on memory-constrained containers.
MAX_FILE_SIZE_MB: int = 200


class Scanner:
    """Scans library directories for 3D model files and indexes them in the database.

    Libraries are loaded from the ``libraries`` table in the database.  Each
    scan walks every registered library path, discovers supported files, and
    inserts new records into the ``models`` table.

    Attributes:
        is_scanning: Whether a scan is currently in progress.
        total_files: Total number of supported files discovered on disk.
        processed_files: Number of files processed so far in the current scan.
    """

    def __init__(
        self,
        db_path: str,
        thumbnail_path: str,
        supported_extensions: set[str],
    ) -> None:
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

    async def scan(self, update_only: bool = False) -> dict:
        """Scan all registered libraries and index supported files.

        Uses an asyncio lock to prevent concurrent scans. If a scan is
        already running the method returns immediately with zeroed stats.

        Args:
            update_only: If True, only discover and index new files without
                checking for moved/missing files (much faster).

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
            return await self._run_scan(update_only=update_only)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_libraries(self) -> list[dict]:
        """Load all libraries from the database."""
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        try:
            cursor = await db.execute("SELECT * FROM libraries ORDER BY name")
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await db.close()

    async def _run_scan(self, update_only: bool = False) -> dict:
        """Core scanning logic executed under the lock."""
        self.is_scanning = True
        self.total_files = 0
        self.processed_files = 0

        stats: dict = {
            "total_files": 0,
            "new_files": 0,
            "skipped_files": 0,
            "moved_files": 0,
            "missing_files": 0,
            "reactivated_files": 0,
            "errors": 0,
        }

        libraries = await self._get_libraries()
        if not libraries:
            logger.warning("No libraries configured -- nothing to scan.")
            self.is_scanning = False
            return stats

        mode_label = "update-only scan" if update_only else "full scan"
        logger.info("Starting %s of %d libraries", mode_label, len(libraries))
        log_memory("scan_start")

        # 1. Discover files across all libraries
        loop = asyncio.get_running_loop()
        # Per-library items: {library_id: [(file_path, scan_root), ...]}
        library_items: dict[int, list[tuple[Path, Path]]] = {}

        for lib in libraries:
            scan_root = Path(lib["path"])
            library_id = lib["id"]
            if not scan_root.is_dir():
                logger.warning(
                    "Library '%s' path does not exist: %s", lib["name"], scan_root
                )
                continue

            files: list[Path] = await loop.run_in_executor(
                None, self._discover_files, scan_root
            )
            library_items[library_id] = [(f, scan_root) for f in files]

        # Separate zip files from regular model files per library and
        # expand zip contents into a flat list for processing after
        # per-library reconciliation.
        zip_entries: list[
            tuple[Path, str, int, Path]
        ] = []  # (zip_path, entry, lib_id, root)

        for library_id, items in list(library_items.items()):
            regular: list[tuple[Path, Path]] = []
            for file_path, scan_root in items:
                if file_path.suffix.lower() == ".zip":
                    entries = await loop.run_in_executor(
                        None,
                        zip_handler.list_models_in_zip,
                        str(file_path),
                        self.supported_extensions,
                    )
                    for entry in entries:
                        zip_entries.append((file_path, entry, library_id, scan_root))
                else:
                    regular.append((file_path, scan_root))
            library_items[library_id] = regular

        all_count = sum(len(items) for items in library_items.values()) + len(
            zip_entries
        )
        self.total_files = all_count
        stats["total_files"] = all_count
        logger.info(
            "Found %d supported files across all libraries (%d regular, %d zip entries).",
            all_count,
            all_count - len(zip_entries),
            len(zip_entries),
        )

        # 2. Process each library with reconciliation
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        try:
            # Process regular (non-zip) model files per library with
            # move detection and orphan reconciliation.
            folder_meta_cache: dict[str, dict] = {}
            for library_id, items in library_items.items():
                orphan_index: dict[str, list[dict]] = {}

                if not update_only:
                    disk_paths = {str(fp) for fp, _ in items}

                    # Load existing DB records for regular (non-zip) models in this library
                    cursor = await db.execute(
                        "SELECT id, file_path, file_hash, status FROM models WHERE library_id = ? AND zip_path IS NULL",
                        (library_id,),
                    )
                    db_records = [dict(r) for r in await cursor.fetchall()]
                    db_path_set = {r["file_path"] for r in db_records}

                    # Categorise paths
                    orphaned_paths = db_path_set - disk_paths

                    # Build orphan hash index: {hash: [record, ...]}
                    for rec in db_records:
                        if rec["file_path"] in orphaned_paths and rec["file_hash"]:
                            orphan_index.setdefault(rec["file_hash"], []).append(rec)

                    # Reactivate previously-missing files found at their original path
                    for rec in db_records:
                        if rec["file_path"] in disk_paths and rec["status"] == "missing":
                            await db.execute(
                                "UPDATE models SET status = 'active', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                                (rec["id"],),
                            )
                            stats["reactivated_files"] += 1
                            logger.info(
                                "Reactivated previously-missing model id=%d  %s",
                                rec["id"],
                                rec["file_path"],
                            )

                # Process each file on disk
                for file_path, scan_root in items:
                    try:
                        result = await self._process_file(
                            db, file_path, loop, library_id, scan_root, orphan_index,
                            folder_meta_cache=folder_meta_cache,
                        )
                        if result == "new":
                            stats["new_files"] += 1
                            # Commit after each new file so progress survives restarts
                            await db.commit()
                        elif result == "moved":
                            stats["moved_files"] += 1
                            await db.commit()
                        else:
                            stats["skipped_files"] += 1
                    except Exception:
                        logger.exception("Error processing %s", file_path)
                        stats["errors"] += 1
                    finally:
                        self.processed_files += 1
                        if self.processed_files % 100 == 0:
                            logger.info(
                                "Scan progress: %d/%d files (new=%d skipped=%d errors=%d)",
                                self.processed_files,
                                self.total_files,
                                stats["new_files"],
                                stats["skipped_files"],
                                stats["errors"],
                            )

                if not update_only:
                    # Mark remaining orphans (not matched by moves) as missing
                    for records in orphan_index.values():
                        for rec in records:
                            await db.execute(
                                "UPDATE models SET status = 'missing', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                                (rec["id"],),
                            )
                            stats["missing_files"] += 1
                            logger.info(
                                "Marked model as missing: id=%d  %s",
                                rec["id"],
                                rec["file_path"],
                            )
                    # Also mark orphans that had no hash (NULL file_hash)
                    for rec in db_records:
                        if (
                            rec["file_path"] in orphaned_paths
                            and not rec["file_hash"]
                            and rec["status"] != "missing"
                        ):
                            await db.execute(
                                "UPDATE models SET status = 'missing', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                                (rec["id"],),
                            )
                            stats["missing_files"] += 1
                            logger.info(
                                "Marked model as missing (no hash): id=%d  %s",
                                rec["id"],
                                rec["file_path"],
                            )

            # Pre-compute zip metadata (once per zip file)
            zip_meta_cache: dict[str, dict] = {}
            for zip_path, entry_name, library_id, scan_root in zip_entries:
                zp_str = str(zip_path)
                if zp_str not in zip_meta_cache:
                    try:
                        zip_meta_cache[zp_str] = await loop.run_in_executor(
                            None, extract_zip_metadata, zip_path
                        )
                    except Exception:
                        logger.debug("Failed to extract zip metadata: %s", zp_str)
                        zip_meta_cache[zp_str] = {}

            # Process model entries inside zip archives
            for zip_path, entry_name, library_id, scan_root in zip_entries:
                try:
                    zip_meta = zip_meta_cache.get(str(zip_path), {})
                    added = await self._process_zip_entry(
                        db, zip_path, entry_name, loop, library_id, scan_root,
                        zip_meta=zip_meta,
                    )
                    if added:
                        stats["new_files"] += 1
                        # Commit after each new zip entry so progress survives restarts
                        await db.commit()
                    else:
                        stats["skipped_files"] += 1
                except Exception:
                    logger.exception("Error processing %s in %s", entry_name, zip_path)
                    stats["errors"] += 1
                finally:
                    self.processed_files += 1

            # Reconcile zip entries: mark missing or reactivate
            if not update_only:
                discovered_zip_paths = {
                    zip_handler.make_zip_file_path(str(zp), en)
                    for zp, en, _, _ in zip_entries
                }
                all_lib_ids = set(library_items.keys()) | {
                    lid for _, _, lid, _ in zip_entries
                }
                for lib_id in all_lib_ids:
                    cursor = await db.execute(
                        "SELECT id, file_path, status FROM models WHERE library_id = ? AND zip_path IS NOT NULL",
                        (lib_id,),
                    )
                    zip_db_records = [dict(r) for r in await cursor.fetchall()]
                    for rec in zip_db_records:
                        if rec["file_path"] in discovered_zip_paths:
                            if rec["status"] == "missing":
                                await db.execute(
                                    "UPDATE models SET status = 'active', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                                    (rec["id"],),
                                )
                                stats["reactivated_files"] += 1
                                logger.info(
                                    "Reactivated zip entry: id=%d  %s",
                                    rec["id"],
                                    rec["file_path"],
                                )
                        else:
                            if rec["status"] != "missing":
                                await db.execute(
                                    "UPDATE models SET status = 'missing', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                                    (rec["id"],),
                                )
                                stats["missing_files"] += 1
                                logger.info(
                                    "Marked zip entry as missing: id=%d  %s",
                                    rec["id"],
                                    rec["file_path"],
                                )

            await db.commit()
        finally:
            await db.close()

        self.is_scanning = False
        log_memory("scan_complete")
        logger.info(
            "Scan complete -- total=%d new=%d moved=%d skipped=%d missing=%d reactivated=%d errors=%d",
            stats["total_files"],
            stats["new_files"],
            stats["moved_files"],
            stats["skipped_files"],
            stats["missing_files"],
            stats["reactivated_files"],
            stats["errors"],
        )
        return stats

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------

    def _discover_files(self, scan_path: Path) -> list[Path]:
        """Synchronously walk the scan_path and return all matching file paths.

        Also discovers ``.zip`` files so that their contents can be
        scanned for models.
        """
        matches: list[Path] = []
        for dirpath, _dirnames, filenames in os.walk(scan_path):
            for fname in filenames:
                suffix = Path(fname).suffix.lower()
                if suffix in self.supported_extensions or suffix == ".zip":
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
        library_id: int,
        scan_root: Path,
        orphan_index: dict[str, list[dict]] | None = None,
        folder_meta_cache: dict[str, dict] | None = None,
    ) -> str:
        """Process a single file.

        Extracts metadata, computes a file hash, generates a thumbnail,
        inserts a new record into the ``models`` table (or updates an
        existing orphaned record if the hash matches a moved file), creates
        category associations derived from the directory hierarchy, and
        updates the FTS index.

        Args:
            folder_meta_cache: Shared cache of folder metadata dicts keyed
                by directory path string.  Populated lazily.

        Returns:
            ``"new"`` if the file was newly inserted, ``"moved"`` if an
            orphaned record was updated (file was moved), or ``"skipped"``
            if a record with the same ``file_path`` already exists.
        """
        file_path_str = str(file_path)

        # Skip if this file path is already in the database
        cursor = await db.execute(
            "SELECT id FROM models WHERE file_path = ?", (file_path_str,)
        )
        existing = await cursor.fetchone()
        if existing is not None:
            logger.debug("Skipping already-indexed file: %s", file_path_str)
            return "skipped"

        # Skip files that are too large (would OOM the worker process)
        try:
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            if file_size_mb > MAX_FILE_SIZE_MB:
                logger.warning(
                    "Skipping oversized file (%.0f MB > %d MB limit): %s",
                    file_size_mb,
                    MAX_FILE_SIZE_MB,
                    file_path_str,
                )
                return "skipped"
        except OSError:
            pass  # stat failed, try processing anyway

        # Extract metadata (CPU-bound -- run in process pool)
        metadata: dict = await loop.run_in_executor(
            get_pool(), processor.extract_metadata, file_path_str
        )
        tick_job()

        # Compute file hash (CPU-bound -- run in process pool)
        file_hash: str = await loop.run_in_executor(
            get_pool(), hasher.compute_file_hash, file_path_str
        )
        tick_job()

        # Check if this file matches an orphaned record (moved file)
        if orphan_index and file_hash in orphan_index and orphan_index[file_hash]:
            orphan = orphan_index[file_hash].pop(0)
            # If the list is now empty, remove the key so it won't be
            # marked missing later
            if not orphan_index[file_hash]:
                del orphan_index[file_hash]

            model_id = orphan["id"]
            name = file_path.stem

            # Update the existing record with new path and refreshed metadata
            file_size = metadata.get("file_size") or os.path.getsize(file_path)
            await db.execute(
                """
                UPDATE models SET
                    file_path = ?,
                    name = ?,
                    file_size = ?,
                    file_hash = ?,
                    vertex_count = ?,
                    face_count = ?,
                    dimensions_x = ?,
                    dimensions_y = ?,
                    dimensions_z = ?,
                    status = 'active',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    file_path_str,
                    name,
                    file_size,
                    file_hash,
                    metadata.get("vertex_count"),
                    metadata.get("face_count"),
                    metadata.get("dimensions_x"),
                    metadata.get("dimensions_y"),
                    metadata.get("dimensions_z"),
                    model_id,
                ),
            )

            # Replace category associations with new path-derived categories
            await db.execute(
                "DELETE FROM model_categories WHERE model_id = ?", (model_id,)
            )
            await self._create_categories_from_path(db, file_path, model_id, scan_root)

            # Update FTS index (name may have changed)
            await update_fts_for_model(db, model_id)

            logger.info(
                "Detected moved file: id=%d  %s -> %s",
                model_id,
                orphan["file_path"],
                file_path_str,
            )
            return "moved"

        # Derive basic fields
        name = file_path.stem
        file_format = metadata.get(
            "file_format",
            file_path.suffix.lower().lstrip(".").upper(),
        )
        file_size = metadata.get("file_size") or os.path.getsize(file_path)

        # Extract folder metadata (README, attribution files)
        folder_meta: dict = {}
        if folder_meta_cache is not None:
            folder_key = str(file_path.parent)
            if folder_key not in folder_meta_cache:
                try:
                    folder_meta_cache[folder_key] = await loop.run_in_executor(
                        None, extract_folder_metadata, file_path.parent
                    )
                except Exception:
                    logger.debug("Failed to extract folder metadata: %s", folder_key)
                    folder_meta_cache[folder_key] = {}
            folder_meta = folder_meta_cache[folder_key]

        description = folder_meta.get("description") or ""
        source_url = folder_meta.get("source_url")

        # Insert model row (we need the id for the thumbnail filename)
        cursor = await db.execute(
            """
            INSERT INTO models (
                name, description, file_path, file_format, file_size,
                file_hash, vertex_count, face_count,
                dimensions_x, dimensions_y, dimensions_z,
                thumbnail_path, library_id, source_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                description,
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
                library_id,
                source_url,
            ),
        )
        model_id = cursor.lastrowid

        # Generate thumbnail (CPU-bound -- run in process pool)
        thumb_mode = await get_setting("thumbnail_mode", "wireframe")
        thumb_quality = await get_setting("thumbnail_quality", "fast")
        t0 = time.monotonic()
        thumb_filename: str | None = await loop.run_in_executor(
            get_pool(),
            thumbnail.generate_thumbnail,
            file_path_str,
            self.thumbnail_path,
            model_id,
            thumb_mode,
            thumb_quality,
        )
        tick_job()
        elapsed = time.monotonic() - t0
        if elapsed > 10:
            logger.warning(
                "Slow thumbnail: model %d took %.1fs  %s", model_id, elapsed, file_path_str
            )
            log_memory(f"slow_scan_model_{model_id}")

        # Recycle worker process if it has accumulated too many jobs
        maybe_recycle()

        # Update the model row with the thumbnail path and tracking columns
        if thumb_filename is not None:
            await db.execute(
                "UPDATE models SET thumbnail_path = ?, thumbnail_mode = ?, thumbnail_quality = ?, thumbnail_generated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (thumb_filename, thumb_mode, thumb_quality, model_id),
            )

        # Apply tags from folder metadata
        if folder_meta:
            await self._apply_tags(db, model_id, folder_meta.get("tags", []))
            site = folder_meta.get("site")
            if site:
                await self._apply_tags(db, model_id, [site])

        # Auto-create categories from directory structure
        await self._create_categories_from_path(db, file_path, model_id, scan_root)

        # Update FTS index for this model
        await update_fts_for_model(db, model_id)

        logger.debug("Indexed new model id=%d  %s", model_id, file_path_str)
        return "new"

    # ------------------------------------------------------------------
    # Zip entry processing
    # ------------------------------------------------------------------

    async def _process_zip_entry(
        self,
        db: aiosqlite.Connection,
        zip_path: Path,
        entry_name: str,
        loop: asyncio.AbstractEventLoop,
        library_id: int,
        scan_root: Path,
        zip_meta: dict | None = None,
    ) -> bool:
        """Process a single model entry inside a zip archive.

        Extracts the entry to a temporary file, runs metadata extraction,
        hashing, and thumbnail generation against it, then cleans up.

        Args:
            zip_meta: Pre-extracted zip metadata (title, source_url, tags,
                description) from ``extract_zip_metadata()``.

        Returns:
            True if the entry was newly inserted, False if skipped.
        """
        zip_path_str = str(zip_path)
        synthetic_path = zip_handler.make_zip_file_path(zip_path_str, entry_name)

        # Skip if already indexed
        cursor = await db.execute(
            "SELECT id FROM models WHERE file_path = ?", (synthetic_path,)
        )
        if await cursor.fetchone() is not None:
            logger.debug("Skipping already-indexed zip entry: %s", synthetic_path)
            return False

        # Check entry size before extracting (avoid OOM on huge entries)
        try:
            import zipfile

            with zipfile.ZipFile(zip_path_str, "r") as zf:
                info = zf.getinfo(entry_name)
                entry_size_mb = info.file_size / (1024 * 1024)
                if entry_size_mb > MAX_FILE_SIZE_MB:
                    logger.warning(
                        "Skipping oversized zip entry (%.0f MB > %d MB limit): %s::%s",
                        entry_size_mb,
                        MAX_FILE_SIZE_MB,
                        zip_path_str,
                        entry_name,
                    )
                    return False
        except Exception:
            pass  # if we can't check size, try processing anyway

        # Extract to temp file for processing
        tmp_path: Path | None = None
        try:
            tmp_path = await loop.run_in_executor(
                None, zip_handler.extract_entry_to_temp, zip_path_str, entry_name
            )
            tmp_path_str = str(tmp_path)

            # Extract metadata (CPU-bound -- process pool)
            metadata: dict = await loop.run_in_executor(
                get_pool(), processor.extract_metadata, tmp_path_str
            )
            tick_job()

            # Compute hash of the entry content (CPU-bound -- process pool)
            file_hash: str = await loop.run_in_executor(
                get_pool(), hasher.compute_file_hash, tmp_path_str
            )
            tick_job()

            # Derive fields from the entry name
            from pathlib import PurePosixPath

            entry_p = PurePosixPath(entry_name)
            name = entry_p.stem
            file_format = metadata.get(
                "file_format",
                entry_p.suffix.lower().lstrip(".").upper(),
            )
            file_size = metadata.get("file_size") or os.path.getsize(tmp_path)

            # Extract description and source_url from zip metadata
            description = ""
            source_url = None
            if zip_meta:
                description = zip_meta.get("description") or ""
                source_url = zip_meta.get("source_url")

            # Insert model row
            cursor = await db.execute(
                """
                INSERT INTO models (
                    name, description, file_path, file_format, file_size,
                    file_hash, vertex_count, face_count,
                    dimensions_x, dimensions_y, dimensions_z,
                    thumbnail_path, library_id, zip_path, zip_entry,
                    source_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    description,
                    synthetic_path,
                    file_format,
                    file_size,
                    file_hash,
                    metadata.get("vertex_count"),
                    metadata.get("face_count"),
                    metadata.get("dimensions_x"),
                    metadata.get("dimensions_y"),
                    metadata.get("dimensions_z"),
                    None,
                    library_id,
                    zip_path_str,
                    entry_name,
                    source_url,
                ),
            )
            model_id = cursor.lastrowid

            # Generate thumbnail (CPU-bound -- process pool)
            thumb_mode = await get_setting("thumbnail_mode", "wireframe")
            thumb_quality = await get_setting("thumbnail_quality", "fast")
            thumb_filename: str | None = await loop.run_in_executor(
                get_pool(),
                thumbnail.generate_thumbnail,
                tmp_path_str,
                self.thumbnail_path,
                model_id,
                thumb_mode,
                thumb_quality,
            )
            tick_job()
            maybe_recycle()

            if thumb_filename is not None:
                await db.execute(
                    "UPDATE models SET thumbnail_path = ?, thumbnail_mode = ?, thumbnail_quality = ?, thumbnail_generated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (thumb_filename, thumb_mode, thumb_quality, model_id),
                )

            # Apply tags from zip metadata
            if zip_meta:
                await self._apply_tags(db, model_id, zip_meta.get("tags", []))
                # Add site name as tag
                site = zip_meta.get("site")
                if site:
                    await self._apply_tags(db, model_id, [site])

            # Categories: use zip file's directory + entry's internal path
            await self._create_categories_for_zip_entry(
                db, zip_path, entry_name, model_id, scan_root
            )

            await update_fts_for_model(db, model_id)

            logger.debug(
                "Indexed zip entry id=%d  %s::%s", model_id, zip_path_str, entry_name
            )
            return True
        finally:
            # Clean up temp file
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    async def _apply_tags(
        self,
        db: aiosqlite.Connection,
        model_id: int,
        tags: list[str],
    ) -> None:
        """Insert tags for a model, creating tag records as needed."""
        for tag_name in tags:
            tag_name = tag_name.strip()
            if not tag_name:
                continue
            await db.execute(
                "INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,)
            )
            cursor = await db.execute(
                "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (tag_name,)
            )
            tag_row = await cursor.fetchone()
            if tag_row:
                tag_id = tag_row[0] if not isinstance(tag_row, dict) else tag_row["id"]
                await db.execute(
                    "INSERT OR IGNORE INTO model_tags (model_id, tag_id) VALUES (?, ?)",
                    (model_id, tag_id),
                )

    async def _create_categories_for_zip_entry(
        self,
        db: aiosqlite.Connection,
        zip_path: Path,
        entry_name: str,
        model_id: int,
        scan_root: Path,
    ) -> None:
        """Create categories from both the zip file's directory and the entry's internal path."""
        from pathlib import PurePosixPath

        # Build combined parts: zip directory relative to scan root + entry directories
        try:
            rel_zip = zip_path.parent.relative_to(scan_root)
        except ValueError:
            rel_zip = Path()

        # Add zip filename (without extension) as a category
        zip_stem = zip_path.stem

        # Entry may have subdirectories (e.g., "Models/dragon.stl")
        entry_parent = PurePosixPath(entry_name).parent
        entry_parts = entry_parent.parts if str(entry_parent) != "." else ()

        parts = list(rel_zip.parts) + [zip_stem] + list(entry_parts)
        if not parts:
            return

        parent_id: int | None = None
        for part in parts:
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

            await db.execute(
                """
                INSERT OR IGNORE INTO model_categories (model_id, category_id)
                VALUES (?, ?)
                """,
                (model_id, category_id),
            )
            parent_id = category_id

    # ------------------------------------------------------------------
    # Category helpers
    # ------------------------------------------------------------------

    async def _create_categories_from_path(
        self,
        db: aiosqlite.Connection,
        file_path: Path,
        model_id: int,
        scan_root: Path,
    ) -> None:
        """Derive categories from the relative directory path.

        For a file at ``<scan_path>/Figurines/Animals/dragon.stl`` the
        categories ``Figurines`` and ``Animals`` (child of ``Figurines``)
        are created and associated with the model.
        """
        try:
            rel = file_path.parent.relative_to(scan_root)
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
