"""Real-time file watcher service using watchdog.

Monitors directory trees for filesystem events (created, modified, deleted,
moved) on supported 3D model files and keeps the database in sync. The
watchdog ``Observer`` runs in a background thread; database mutations are
bridged back to the asyncio event loop.

Supports watching multiple library directories simultaneously.
"""

import asyncio
import logging
import os
import threading
import time
from pathlib import Path

import aiosqlite
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.database import get_setting, update_fts_for_model
from app.services import hasher, processor, thumbnail

logger = logging.getLogger(__name__)

# Debounce window in seconds -- rapid events on the same path within this
# window are collapsed into a single action.
DEBOUNCE_SECONDS: float = 2.0


class _DebouncedHandler(FileSystemEventHandler):
    """FileSystemEventHandler that debounces rapid events.

    Events are collected into a pending dictionary keyed by source path.
    A background timer thread flushes events whose debounce window has
    elapsed, dispatching them to the provided *callback*.
    """

    def __init__(
        self,
        callback,
        supported_extensions: set[str],
        debounce: float = DEBOUNCE_SECONDS,
    ) -> None:
        super().__init__()
        self._callback = callback
        self._supported_extensions = supported_extensions
        self._debounce = debounce

        # {src_path: (event, timestamp)}
        self._pending: dict[str, tuple[FileSystemEvent, float]] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._timer_thread = threading.Thread(
            target=self._timer_loop, daemon=True, name="watcher-debounce"
        )
        self._timer_thread.start()

    # ---- watchdog handler overrides ------------------------------------

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue(event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue(event)

    # ---- internal ------------------------------------------------------

    def _is_supported(self, path: str) -> bool:
        return Path(path).suffix.lower() in self._supported_extensions

    def _enqueue(self, event: FileSystemEvent) -> None:
        src = event.src_path
        # For moved events also check the destination extension
        dest = getattr(event, "dest_path", None)

        if not self._is_supported(src) and (
            dest is None or not self._is_supported(dest)
        ):
            return

        with self._lock:
            self._pending[src] = (event, time.monotonic())

    def _timer_loop(self) -> None:
        """Periodically flush events whose debounce window has expired."""
        while not self._stop_event.is_set():
            time.sleep(0.5)
            now = time.monotonic()
            to_dispatch: list[FileSystemEvent] = []

            with self._lock:
                expired_keys = [
                    key
                    for key, (_, ts) in self._pending.items()
                    if now - ts >= self._debounce
                ]
                for key in expired_keys:
                    event, _ = self._pending.pop(key)
                    to_dispatch.append(event)

            for event in to_dispatch:
                try:
                    self._callback(event)
                except Exception:
                    logger.exception(
                        "Error dispatching watcher event %s", event
                    )

    def stop(self) -> None:
        """Signal the debounce timer thread to exit."""
        self._stop_event.set()
        self._timer_thread.join(timeout=5)


class ModelFileWatcher:
    """Watches library directories for changes to supported 3D model files.

    Supports watching multiple library paths. New paths can be added at
    runtime via :meth:`watch_path`, and all watches are stopped with
    :meth:`stop`.
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

        self._observer: Observer | None = None
        self._handler: _DebouncedHandler | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._watched_paths: set[str] = set()
        # Map watched path -> ObservedWatch handle for unscheduling
        self._watches: dict[str, object] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Initialise the observer. Call :meth:`watch_path` to add directories."""
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
            logger.warning(
                "No running asyncio loop detected; watcher DB operations "
                "will create their own loop context."
            )

        self._handler = _DebouncedHandler(
            callback=self._dispatch_event,
            supported_extensions=self.supported_extensions,
        )

        self._observer = Observer()
        self._observer.daemon = True
        self._observer.start()

        logger.info("File watcher observer started.")

    @property
    def is_running(self) -> bool:
        """Whether the observer thread is alive and watching."""
        return self._observer is not None and self._observer.is_alive()

    @property
    def watched_paths(self) -> set[str]:
        """The set of directories currently being watched."""
        return set(self._watched_paths)

    def watch_path(self, path: str) -> None:
        """Add a directory to the set of watched paths."""
        if self._observer is None or self._handler is None:
            logger.warning("Watcher not started; call start() first.")
            return

        path_str = str(path)
        if path_str in self._watched_paths:
            return

        if not os.path.isdir(path_str):
            logger.warning("Cannot watch non-existent directory: %s", path_str)
            return

        watch = self._observer.schedule(
            self._handler, path=path_str, recursive=True
        )
        self._watched_paths.add(path_str)
        self._watches[path_str] = watch
        logger.info("File watcher watching: %s", path_str)

    def unwatch_path(self, path: str) -> None:
        """Remove a directory from the set of watched paths."""
        if self._observer is None:
            return

        path_str = str(path)
        watch = self._watches.pop(path_str, None)
        if watch is not None:
            try:
                self._observer.unschedule(watch)
            except Exception:
                logger.warning("Failed to unschedule watch for: %s", path_str)
            self._watched_paths.discard(path_str)
            logger.info("File watcher unwatched: %s", path_str)

    def stop(self) -> None:
        """Stop the filesystem watcher and clean up threads."""
        if self._handler is not None:
            self._handler.stop()
            self._handler = None

        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=10)
            self._observer = None

        self._watched_paths.clear()
        self._watches.clear()
        logger.info("File watcher stopped.")

    # ------------------------------------------------------------------
    # Event dispatcher (called from debounce timer thread)
    # ------------------------------------------------------------------

    def _dispatch_event(self, event: FileSystemEvent) -> None:
        """Route a debounced event to the appropriate handler."""
        event_type = event.event_type

        logger.debug(
            "Watcher event: %s  src=%s%s",
            event_type,
            event.src_path,
            f"  dest={event.dest_path}" if hasattr(event, "dest_path") and event.event_type == "moved" else "",
        )

        coro = self._handle_event(event)
        self._run_async(coro)

    def _run_async(self, coro) -> None:
        """Schedule an async coroutine from the watchdog thread."""
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        else:
            asyncio.run(coro)

    # ------------------------------------------------------------------
    # Async event handlers
    # ------------------------------------------------------------------

    async def _handle_event(self, event: FileSystemEvent) -> None:
        """Dispatch a single filesystem event to the correct handler."""
        try:
            event_type = event.event_type
            if event_type == "created":
                await self._on_created(event.src_path)
            elif event_type == "modified":
                await self._on_modified(event.src_path)
            elif event_type == "deleted":
                await self._on_deleted(event.src_path)
            elif event_type == "moved":
                dest_path = getattr(event, "dest_path", None)
                await self._on_moved(event.src_path, dest_path)
        except Exception:
            logger.exception(
                "Error handling watcher event %s for %s",
                event.event_type,
                event.src_path,
            )

    async def _get_db(self) -> aiosqlite.Connection:
        """Open a new database connection with standard pragmas."""
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        return db

    def _find_library_root(self, file_path: str) -> str | None:
        """Find which watched library root contains the given file path."""
        for root in self._watched_paths:
            try:
                Path(file_path).relative_to(root)
                return root
            except ValueError:
                continue
        return None

    # ---- created -------------------------------------------------------

    async def _on_created(self, src_path: str) -> None:
        """A new supported file appeared -- extract metadata and insert."""
        logger.info("New file detected: %s", src_path)

        db = await self._get_db()
        try:
            # Skip if already present
            cursor = await db.execute(
                "SELECT id FROM models WHERE file_path = ?", (src_path,)
            )
            if await cursor.fetchone() is not None:
                logger.debug("File already in database, skipping: %s", src_path)
                return

            loop = asyncio.get_running_loop()

            # Extract metadata
            metadata: dict = await loop.run_in_executor(
                None, processor.extract_metadata, src_path
            )

            # Compute hash
            file_hash: str = await loop.run_in_executor(
                None, hasher.compute_file_hash, src_path
            )

            name = Path(src_path).stem
            file_format = metadata.get(
                "file_format",
                Path(src_path).suffix.lower().lstrip(".").upper(),
            )
            file_size = metadata.get("file_size") or os.path.getsize(src_path)

            # Resolve library_id from watched paths
            library_id = None
            library_root = self._find_library_root(src_path)
            if library_root:
                cursor = await db.execute(
                    "SELECT id FROM libraries WHERE path = ?", (library_root,)
                )
                lib_row = await cursor.fetchone()
                if lib_row:
                    library_id = dict(lib_row)["id"]

            # Insert model
            cursor = await db.execute(
                """
                INSERT INTO models (
                    name, description, file_path, file_format, file_size,
                    file_hash, vertex_count, face_count,
                    dimensions_x, dimensions_y, dimensions_z,
                    thumbnail_path, library_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    "",
                    src_path,
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
                ),
            )
            model_id = cursor.lastrowid

            # Generate thumbnail
            thumb_mode = await get_setting("thumbnail_mode", "wireframe")
            thumb_filename: str | None = await loop.run_in_executor(
                None,
                thumbnail.generate_thumbnail,
                src_path,
                self.thumbnail_path,
                model_id,
                thumb_mode,
            )
            if thumb_filename is not None:
                await db.execute(
                    "UPDATE models SET thumbnail_path = ? WHERE id = ?",
                    (thumb_filename, model_id),
                )

            # Auto-create categories from directory structure
            if library_root:
                await self._create_categories_from_path(
                    db, src_path, model_id, library_root
                )

            # Update FTS
            await update_fts_for_model(db, model_id)

            await db.commit()
            logger.info("Indexed new file via watcher: id=%d  %s", model_id, src_path)
        finally:
            await db.close()

    # ---- modified ------------------------------------------------------

    async def _on_modified(self, src_path: str) -> None:
        """An existing file was modified -- refresh its metadata."""
        logger.info("File modified: %s", src_path)

        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT id FROM models WHERE file_path = ?", (src_path,)
            )
            row = await cursor.fetchone()
            if row is None:
                # Not yet tracked -- treat as a new file
                await db.close()
                await self._on_created(src_path)
                return

            model_id = row[0] if not isinstance(row, dict) else row["id"]
            loop = asyncio.get_running_loop()

            # Re-extract metadata
            metadata: dict = await loop.run_in_executor(
                None, processor.extract_metadata, src_path
            )

            # Re-compute hash
            file_hash: str = await loop.run_in_executor(
                None, hasher.compute_file_hash, src_path
            )

            file_size = metadata.get("file_size") or os.path.getsize(src_path)

            await db.execute(
                """
                UPDATE models SET
                    file_size = ?,
                    file_hash = ?,
                    vertex_count = ?,
                    face_count = ?,
                    dimensions_x = ?,
                    dimensions_y = ?,
                    dimensions_z = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
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

            # Regenerate thumbnail
            thumb_mode = await get_setting("thumbnail_mode", "wireframe")
            thumb_filename: str | None = await loop.run_in_executor(
                None,
                thumbnail.generate_thumbnail,
                src_path,
                self.thumbnail_path,
                model_id,
                thumb_mode,
            )
            if thumb_filename is not None:
                await db.execute(
                    "UPDATE models SET thumbnail_path = ? WHERE id = ?",
                    (thumb_filename, model_id),
                )

            # Update FTS
            await update_fts_for_model(db, model_id)

            await db.commit()
            logger.info("Updated metadata for modified file: id=%d  %s", model_id, src_path)
        finally:
            await db.close()

    # ---- deleted -------------------------------------------------------

    async def _on_deleted(self, src_path: str) -> None:
        """A tracked file was deleted -- remove from DB and clean up thumbnail."""
        logger.info("File deleted: %s", src_path)

        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT id, thumbnail_path FROM models WHERE file_path = ?",
                (src_path,),
            )
            row = await cursor.fetchone()
            if row is None:
                logger.debug("Deleted file was not in database: %s", src_path)
                return

            model_id = row[0] if not isinstance(row, dict) else row["id"]
            thumb_path = row[1] if not isinstance(row, dict) else row.get("thumbnail_path")

            # Delete thumbnail file if it exists
            if thumb_path:
                full_thumb = Path(self.thumbnail_path) / thumb_path
                if full_thumb.exists():
                    try:
                        full_thumb.unlink()
                        logger.debug("Removed thumbnail: %s", full_thumb)
                    except OSError as exc:
                        logger.warning(
                            "Could not delete thumbnail %s: %s", full_thumb, exc
                        )

            # Remove FTS entry
            await db.execute(
                "DELETE FROM models_fts WHERE rowid = ?", (model_id,)
            )

            # Remove model (cascades to model_categories and model_tags)
            await db.execute("DELETE FROM models WHERE id = ?", (model_id,))

            await db.commit()
            logger.info("Removed deleted file from DB: id=%d  %s", model_id, src_path)
        finally:
            await db.close()

    # ---- moved ---------------------------------------------------------

    async def _on_moved(self, src_path: str, dest_path: str | None) -> None:
        """A tracked file was moved/renamed -- update file_path in DB."""
        if dest_path is None:
            logger.warning("Move event with no destination for %s", src_path)
            return

        logger.info("File moved: %s -> %s", src_path, dest_path)

        # If destination extension is not supported, treat as deletion
        if Path(dest_path).suffix.lower() not in self.supported_extensions:
            await self._on_deleted(src_path)
            return

        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT id FROM models WHERE file_path = ?", (src_path,)
            )
            row = await cursor.fetchone()

            if row is None:
                # Source was not tracked -- treat destination as a new file
                await db.close()
                await self._on_created(dest_path)
                return

            model_id = row[0] if not isinstance(row, dict) else row["id"]

            # Update the file path and name
            new_name = Path(dest_path).stem
            await db.execute(
                """
                UPDATE models SET
                    file_path = ?,
                    name = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (dest_path, new_name, model_id),
            )

            # Update FTS (name may have changed)
            await update_fts_for_model(db, model_id)

            await db.commit()
            logger.info(
                "Updated file path for moved file: id=%d  %s -> %s",
                model_id,
                src_path,
                dest_path,
            )
        finally:
            await db.close()

    # ------------------------------------------------------------------
    # Category helpers (mirrors Scanner._create_categories_from_path)
    # ------------------------------------------------------------------

    async def _create_categories_from_path(
        self,
        db: aiosqlite.Connection,
        file_path_str: str,
        model_id: int,
        scan_root: str,
    ) -> None:
        """Derive categories from the relative directory path."""
        file_path = Path(file_path_str)
        root = Path(scan_root)

        try:
            rel = file_path.parent.relative_to(root)
        except ValueError:
            return

        parts = rel.parts
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
