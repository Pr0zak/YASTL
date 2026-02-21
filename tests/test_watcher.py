"""Tests for the file watcher service (app/services/watcher.py).

Tests cover:
  - _DebouncedHandler: event filtering, debouncing, dispatch
  - ModelFileWatcher: lifecycle (start/stop), watch/unwatch, event routing
"""

import time
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest

from app.services.watcher import _DebouncedHandler, ModelFileWatcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(event_type: str, src_path: str, dest_path: str | None = None):
    """Create a mock FileSystemEvent."""
    event = MagicMock()
    event.event_type = event_type
    event.src_path = src_path
    event.is_directory = False
    if dest_path is not None:
        event.dest_path = dest_path
    else:
        # Simulate that dest_path attribute doesn't exist for non-move events
        type(event).dest_path = PropertyMock(side_effect=AttributeError)
        # But getattr should return None
        del event.dest_path
    return event


def _make_dir_event(event_type: str, src_path: str):
    """Create a mock directory FileSystemEvent."""
    event = MagicMock()
    event.event_type = event_type
    event.src_path = src_path
    event.is_directory = True
    return event


# ===========================================================================
# _DebouncedHandler tests
# ===========================================================================


class TestDebouncedHandler:
    """Tests for the debounce logic in _DebouncedHandler."""

    def setup_method(self):
        self.callback = MagicMock()
        self.extensions = {".stl", ".obj", ".3mf", ".gltf", ".glb", ".ply"}

    def teardown_method(self):
        # Stop any handler created during the test
        if hasattr(self, "handler"):
            self.handler.stop()

    def _make_handler(self, debounce: float = 0.3):
        self.handler = _DebouncedHandler(
            callback=self.callback,
            supported_extensions=self.extensions,
            debounce=debounce,
        )
        return self.handler

    def test_supported_extension_enqueues(self):
        """Events for supported extensions are enqueued."""
        handler = self._make_handler()
        event = _make_event("created", "/models/cube.stl")
        handler.on_created(event)

        assert len(handler._pending) == 1
        assert "/models/cube.stl" in handler._pending

    def test_unsupported_extension_ignored(self):
        """Events for unsupported extensions are not enqueued."""
        handler = self._make_handler()
        event = _make_event("created", "/models/readme.txt")
        handler.on_created(event)

        assert len(handler._pending) == 0

    def test_zip_extension_supported(self):
        """Zip files are always supported regardless of extension set."""
        handler = self._make_handler()
        event = _make_event("created", "/models/archive.zip")
        handler.on_created(event)

        assert len(handler._pending) == 1

    def test_directory_events_ignored(self):
        """Directory events are filtered out by all handler methods."""
        handler = self._make_handler()

        dir_event = _make_dir_event("created", "/models/subdir")
        handler.on_created(dir_event)
        handler.on_modified(dir_event)
        handler.on_deleted(dir_event)
        handler.on_moved(dir_event)

        assert len(handler._pending) == 0

    def test_events_coalesced_within_debounce_window(self):
        """Multiple events on the same file within the debounce window are coalesced."""
        handler = self._make_handler(debounce=1.0)

        event1 = _make_event("created", "/models/cube.stl")
        event2 = _make_event("modified", "/models/cube.stl")

        handler.on_created(event1)
        handler.on_modified(event2)

        # Only one entry should exist (the latest event replaces the earlier one)
        assert len(handler._pending) == 1
        # The pending event should be the most recent one
        stored_event, _ = handler._pending["/models/cube.stl"]
        assert stored_event.event_type == "modified"

    def test_different_files_debounced_independently(self):
        """Events on different files are tracked independently."""
        handler = self._make_handler(debounce=1.0)

        event_a = _make_event("created", "/models/cube.stl")
        event_b = _make_event("created", "/models/sphere.obj")

        handler.on_created(event_a)
        handler.on_created(event_b)

        assert len(handler._pending) == 2

    def test_debounced_events_dispatched_after_window(self):
        """Events are dispatched to the callback after the debounce window."""
        handler = self._make_handler(debounce=0.2)

        event = _make_event("created", "/models/cube.stl")
        handler.on_created(event)

        # Wait for debounce + timer poll interval
        time.sleep(1.0)

        assert self.callback.call_count == 1
        dispatched_event = self.callback.call_args[0][0]
        assert dispatched_event.src_path == "/models/cube.stl"

    def test_events_not_dispatched_before_window(self):
        """Events are NOT dispatched while within the debounce window."""
        handler = self._make_handler(debounce=5.0)

        event = _make_event("created", "/models/cube.stl")
        handler.on_created(event)

        # Brief pause -- well within the debounce window
        time.sleep(0.2)

        assert self.callback.call_count == 0

    def test_callback_exception_does_not_crash_timer(self):
        """An exception in the callback does not stop the debounce timer."""
        self.callback.side_effect = [RuntimeError("boom"), None]
        handler = self._make_handler(debounce=0.2)

        event1 = _make_event("created", "/models/cube.stl")
        handler.on_created(event1)

        time.sleep(1.0)

        # First call raised, but the timer should still be running
        assert self.callback.call_count == 1

        event2 = _make_event("created", "/models/sphere.obj")
        handler.on_created(event2)

        time.sleep(1.0)

        # Second call should have succeeded
        assert self.callback.call_count == 2

    def test_stop_stops_timer_thread(self):
        """Calling stop() signals the timer thread to exit."""
        handler = self._make_handler()
        assert handler._timer_thread.is_alive()

        handler.stop()

        # Thread should have exited
        assert not handler._timer_thread.is_alive()

    def test_moved_event_with_supported_dest(self):
        """Move events with a supported destination extension are enqueued."""
        handler = self._make_handler()

        event = _make_event("moved", "/models/old.txt", dest_path="/models/new.stl")
        handler.on_moved(event)

        assert len(handler._pending) == 1

    def test_moved_event_with_unsupported_both(self):
        """Move events where both src and dest are unsupported are ignored."""
        handler = self._make_handler()

        event = _make_event("moved", "/models/old.txt", dest_path="/models/new.doc")
        handler.on_moved(event)

        assert len(handler._pending) == 0

    def test_on_modified_enqueues(self):
        """on_modified enqueues file events."""
        handler = self._make_handler()
        event = _make_event("modified", "/models/cube.stl")
        handler.on_modified(event)

        assert len(handler._pending) == 1

    def test_on_deleted_enqueues(self):
        """on_deleted enqueues file events."""
        handler = self._make_handler()
        event = _make_event("deleted", "/models/cube.stl")
        handler.on_deleted(event)

        assert len(handler._pending) == 1


# ===========================================================================
# ModelFileWatcher tests
# ===========================================================================


class TestModelFileWatcher:
    """Tests for the ModelFileWatcher public API and event routing."""

    def setup_method(self):
        self.watcher = ModelFileWatcher(
            db_path="/tmp/test.db",
            thumbnail_path="/tmp/thumbnails",
            supported_extensions={".stl", ".obj", ".3mf"},
        )

    def teardown_method(self):
        try:
            self.watcher.stop()
        except Exception:
            pass

    def test_initial_state(self):
        """Watcher starts in a stopped state with no watched paths."""
        assert not self.watcher.is_running
        assert self.watcher.watched_paths == set()

    def test_extensions_normalized_to_lowercase(self):
        """Supported extensions are normalized to lowercase."""
        w = ModelFileWatcher(
            db_path="/tmp/test.db",
            thumbnail_path="/tmp/thumbs",
            supported_extensions={".STL", ".Obj", ".3MF"},
        )
        assert w.supported_extensions == {".stl", ".obj", ".3mf"}

    @patch("app.services.watcher.Observer")
    def test_start_creates_observer(self, MockObserver):
        """start() creates and starts an Observer."""
        mock_observer = MagicMock()
        MockObserver.return_value = mock_observer

        self.watcher.start()

        MockObserver.assert_called_once()
        mock_observer.start.assert_called_once()
        assert self.watcher._observer is mock_observer
        assert self.watcher._handler is not None

    @patch("app.services.watcher.Observer")
    def test_start_sets_observer_as_daemon(self, MockObserver):
        """start() sets observer.daemon = True."""
        mock_observer = MagicMock()
        MockObserver.return_value = mock_observer

        self.watcher.start()

        assert mock_observer.daemon is True

    @patch("app.services.watcher.Observer")
    def test_watch_path_schedules_directory(self, MockObserver):
        """watch_path() schedules a directory for recursive watching."""
        mock_observer = MagicMock()
        MockObserver.return_value = mock_observer

        self.watcher.start()

        with patch("os.path.isdir", return_value=True):
            self.watcher.watch_path("/models")

        mock_observer.schedule.assert_called_once()
        args, kwargs = mock_observer.schedule.call_args
        assert kwargs.get("path") == "/models" or args[1] == "/models"
        assert kwargs.get("recursive") is True
        assert "/models" in self.watcher.watched_paths

    @patch("app.services.watcher.Observer")
    def test_watch_path_nonexistent_directory(self, MockObserver):
        """watch_path() logs a warning and skips non-existent directories."""
        mock_observer = MagicMock()
        MockObserver.return_value = mock_observer

        self.watcher.start()

        with patch("os.path.isdir", return_value=False):
            self.watcher.watch_path("/nonexistent/path")

        mock_observer.schedule.assert_not_called()
        assert "/nonexistent/path" not in self.watcher.watched_paths

    @patch("app.services.watcher.Observer")
    def test_watch_path_duplicate_ignored(self, MockObserver):
        """watch_path() with an already-watched path is a no-op."""
        mock_observer = MagicMock()
        MockObserver.return_value = mock_observer

        self.watcher.start()

        with patch("os.path.isdir", return_value=True):
            self.watcher.watch_path("/models")
            self.watcher.watch_path("/models")

        assert mock_observer.schedule.call_count == 1

    @patch("app.services.watcher.Observer")
    def test_watch_path_before_start_does_nothing(self, MockObserver):
        """watch_path() before start() is a no-op."""
        self.watcher.watch_path("/models")

        MockObserver.return_value.schedule.assert_not_called()
        assert "/models" not in self.watcher.watched_paths

    @patch("app.services.watcher.Observer")
    def test_unwatch_path_removes_directory(self, MockObserver):
        """unwatch_path() removes a watched directory."""
        mock_observer = MagicMock()
        mock_watch = MagicMock()
        mock_observer.schedule.return_value = mock_watch
        MockObserver.return_value = mock_observer

        self.watcher.start()

        with patch("os.path.isdir", return_value=True):
            self.watcher.watch_path("/models")

        self.watcher.unwatch_path("/models")

        mock_observer.unschedule.assert_called_once_with(mock_watch)
        assert "/models" not in self.watcher.watched_paths

    @patch("app.services.watcher.Observer")
    def test_unwatch_path_not_watched_is_noop(self, MockObserver):
        """unwatch_path() for a path that was never watched is a no-op."""
        mock_observer = MagicMock()
        MockObserver.return_value = mock_observer

        self.watcher.start()
        self.watcher.unwatch_path("/never_watched")

        mock_observer.unschedule.assert_not_called()

    @patch("app.services.watcher.Observer")
    def test_stop_cleans_up(self, MockObserver):
        """stop() stops the observer and cleans up state."""
        mock_observer = MagicMock()
        MockObserver.return_value = mock_observer

        self.watcher.start()

        with patch("os.path.isdir", return_value=True):
            self.watcher.watch_path("/models")

        self.watcher.stop()

        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()
        assert self.watcher._observer is None
        assert self.watcher._handler is None
        assert self.watcher.watched_paths == set()

    @patch("app.services.watcher.Observer")
    def test_stop_before_start_is_safe(self, MockObserver):
        """stop() before start() does not raise."""
        self.watcher.stop()  # Should not raise

    @patch("app.services.watcher.Observer")
    def test_watched_paths_returns_copy(self, MockObserver):
        """watched_paths property returns a copy, not the internal set."""
        mock_observer = MagicMock()
        MockObserver.return_value = mock_observer

        self.watcher.start()

        with patch("os.path.isdir", return_value=True):
            self.watcher.watch_path("/models")

        paths = self.watcher.watched_paths
        paths.add("/something_else")

        assert "/something_else" not in self.watcher.watched_paths

    def test_find_library_root(self):
        """_find_library_root finds the correct library root for a file."""
        self.watcher._watched_paths = {"/lib1", "/lib2/subdir"}

        assert self.watcher._find_library_root("/lib1/cube.stl") == "/lib1"
        assert (
            self.watcher._find_library_root("/lib2/subdir/deep/model.obj")
            == "/lib2/subdir"
        )
        assert self.watcher._find_library_root("/other/path.stl") is None

    @patch("app.services.watcher.Observer")
    def test_is_running_reflects_observer_state(self, MockObserver):
        """is_running reflects whether the observer is alive."""
        assert not self.watcher.is_running

        mock_observer = MagicMock()
        mock_observer.is_alive.return_value = True
        MockObserver.return_value = mock_observer

        self.watcher.start()
        assert self.watcher.is_running

        mock_observer.is_alive.return_value = False
        assert not self.watcher.is_running


# ===========================================================================
# Event dispatch / async handler tests
# ===========================================================================


class TestWatcherEventDispatch:
    """Tests for _dispatch_event and _handle_event routing."""

    def setup_method(self):
        self.watcher = ModelFileWatcher(
            db_path="/tmp/test.db",
            thumbnail_path="/tmp/thumbnails",
            supported_extensions={".stl", ".obj"},
        )

    def teardown_method(self):
        try:
            self.watcher.stop()
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_handle_event_routes_created(self):
        """_handle_event routes 'created' events to _on_created."""
        event = _make_event("created", "/models/cube.stl")

        with patch.object(self.watcher, "_on_created", new_callable=AsyncMock) as mock:
            await self.watcher._handle_event(event)
            mock.assert_awaited_once_with("/models/cube.stl")

    @pytest.mark.asyncio
    async def test_handle_event_routes_modified(self):
        """_handle_event routes 'modified' events to _on_modified."""
        event = _make_event("modified", "/models/cube.stl")

        with patch.object(
            self.watcher, "_on_modified", new_callable=AsyncMock
        ) as mock:
            await self.watcher._handle_event(event)
            mock.assert_awaited_once_with("/models/cube.stl")

    @pytest.mark.asyncio
    async def test_handle_event_routes_deleted(self):
        """_handle_event routes 'deleted' events to _on_deleted."""
        event = _make_event("deleted", "/models/cube.stl")

        with patch.object(self.watcher, "_on_deleted", new_callable=AsyncMock) as mock:
            await self.watcher._handle_event(event)
            mock.assert_awaited_once_with("/models/cube.stl")

    @pytest.mark.asyncio
    async def test_handle_event_routes_moved(self):
        """_handle_event routes 'moved' events to _on_moved."""
        event = _make_event("moved", "/models/old.stl", dest_path="/models/new.stl")

        with patch.object(self.watcher, "_on_moved", new_callable=AsyncMock) as mock:
            await self.watcher._handle_event(event)
            mock.assert_awaited_once_with("/models/old.stl", "/models/new.stl")

    @pytest.mark.asyncio
    async def test_handle_event_exception_does_not_propagate(self):
        """Exceptions in individual handlers are caught and logged."""
        event = _make_event("created", "/models/cube.stl")

        with patch.object(
            self.watcher,
            "_on_created",
            new_callable=AsyncMock,
            side_effect=RuntimeError("db error"),
        ):
            # Should not raise
            await self.watcher._handle_event(event)

    def test_dispatch_event_schedules_coroutine(self):
        """_dispatch_event calls _run_async with the coroutine."""
        event = _make_event("created", "/models/cube.stl")

        with patch.object(self.watcher, "_run_async") as mock_run:
            self.watcher._dispatch_event(event)
            mock_run.assert_called_once()

    def test_run_async_with_running_loop(self):
        """_run_async uses run_coroutine_threadsafe when loop is running."""
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        self.watcher._loop = mock_loop

        coro = AsyncMock()()

        with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
            self.watcher._run_async(coro)
            mock_rcts.assert_called_once_with(coro, mock_loop)

    def test_run_async_without_loop_uses_asyncio_run(self):
        """_run_async uses asyncio.run() when no loop is available."""
        self.watcher._loop = None

        coro = AsyncMock()()

        with patch("asyncio.run") as mock_run:
            self.watcher._run_async(coro)
            mock_run.assert_called_once_with(coro)


# ===========================================================================
# Zip handler routing tests
# ===========================================================================


class TestWatcherZipRouting:
    """Tests for zip-specific event routing in _handle_event."""

    def setup_method(self):
        self.watcher = ModelFileWatcher(
            db_path="/tmp/test.db",
            thumbnail_path="/tmp/thumbnails",
            supported_extensions={".stl", ".obj"},
        )

    @pytest.mark.asyncio
    async def test_created_zip_routes_to_on_zip_created(self):
        """Created .zip files are routed to _on_zip_created."""
        event = _make_event("created", "/models/archive.zip")

        with patch.object(
            self.watcher, "_on_zip_created", new_callable=AsyncMock
        ) as mock:
            with patch.object(self.watcher, "_on_created", wraps=self.watcher._on_created):
                await self.watcher._handle_event(event)
                mock.assert_awaited_once_with("/models/archive.zip")

    @pytest.mark.asyncio
    async def test_deleted_zip_routes_to_on_zip_deleted(self):
        """Deleted .zip files are routed to _on_zip_deleted."""
        event = _make_event("deleted", "/models/archive.zip")

        with patch.object(
            self.watcher, "_on_zip_deleted", new_callable=AsyncMock
        ) as mock:
            with patch.object(self.watcher, "_on_deleted", wraps=self.watcher._on_deleted):
                await self.watcher._handle_event(event)
                mock.assert_awaited_once_with("/models/archive.zip")

    @pytest.mark.asyncio
    async def test_modified_zip_routes_to_on_zip_modified(self):
        """Modified .zip files are routed to _on_zip_modified."""
        event = _make_event("modified", "/models/archive.zip")

        with patch.object(
            self.watcher, "_on_zip_modified", new_callable=AsyncMock
        ) as mock:
            with patch.object(self.watcher, "_on_modified", wraps=self.watcher._on_modified):
                await self.watcher._handle_event(event)
                mock.assert_awaited_once_with("/models/archive.zip")

    @pytest.mark.asyncio
    async def test_moved_zip_routes_to_on_zip_moved(self):
        """Moved .zip files are routed to _on_zip_moved."""
        event = _make_event(
            "moved", "/models/old.zip", dest_path="/models/new.zip"
        )

        with patch.object(
            self.watcher, "_on_zip_moved", new_callable=AsyncMock
        ) as mock:
            with patch.object(self.watcher, "_on_moved", wraps=self.watcher._on_moved):
                await self.watcher._handle_event(event)
                mock.assert_awaited_once_with("/models/old.zip", "/models/new.zip")

    @pytest.mark.asyncio
    async def test_moved_to_unsupported_extension_triggers_delete(self):
        """Moving a file to an unsupported extension triggers deletion."""
        event = _make_event(
            "moved", "/models/cube.stl", dest_path="/models/cube.txt"
        )

        with patch.object(
            self.watcher, "_on_deleted", new_callable=AsyncMock
        ) as mock_del:
            await self.watcher._handle_event(event)
            mock_del.assert_awaited_once_with("/models/cube.stl")

    @pytest.mark.asyncio
    async def test_moved_no_dest_logs_warning(self):
        """Move event with no destination path is handled gracefully."""
        event = MagicMock()
        event.event_type = "moved"
        event.src_path = "/models/cube.stl"
        event.is_directory = False
        event.dest_path = None

        # Should not raise (watcher logs a warning and returns)
        await self.watcher._handle_event(event)


# ===========================================================================
# DebouncedHandler _is_supported tests
# ===========================================================================


class TestIsSupported:
    """Tests for the _is_supported extension check."""

    def setup_method(self):
        self.callback = MagicMock()
        self.handler = _DebouncedHandler(
            callback=self.callback,
            supported_extensions={".stl", ".obj"},
            debounce=10.0,  # High value so nothing fires during tests
        )

    def teardown_method(self):
        self.handler.stop()

    def test_supported_extension(self):
        assert self.handler._is_supported("/path/model.stl") is True

    def test_supported_extension_case_insensitive(self):
        assert self.handler._is_supported("/path/model.STL") is True

    def test_unsupported_extension(self):
        assert self.handler._is_supported("/path/readme.txt") is False

    def test_zip_always_supported(self):
        assert self.handler._is_supported("/path/archive.zip") is True

    def test_no_extension(self):
        assert self.handler._is_supported("/path/noextfile") is False

    def test_hidden_file_with_extension(self):
        assert self.handler._is_supported("/path/.hidden.stl") is True
