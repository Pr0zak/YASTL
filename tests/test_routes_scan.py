"""Tests for app.api.routes_scan API endpoints."""

import pytest
import aiosqlite



@pytest.mark.asyncio
class TestTriggerScan:
    async def test_no_scanner(self, client):
        """POST /api/scan without scanner should return 503."""
        resp = await client.post("/api/scan")
        assert resp.status_code == 503

    async def test_with_mock_scanner(self, test_app):
        """POST /api/scan with scanner should start scan."""
        from httpx import ASGITransport, AsyncClient

        app, db_path, scan_dir, thumb_dir = test_app

        # Create a mock scanner
        class MockScanner:
            is_scanning = False
            total_files = 0
            processed_files = 0

            async def scan(self):
                pass

        app.state.scanner = MockScanner()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/scan")
            assert resp.status_code == 200
            data = resp.json()
            assert data["scanning"] is True

    async def test_scan_already_running(self, test_app):
        """POST /api/scan while scanning should return 409."""
        from httpx import ASGITransport, AsyncClient

        app, db_path, scan_dir, thumb_dir = test_app

        class MockScanner:
            is_scanning = True
            total_files = 10
            processed_files = 5

        app.state.scanner = MockScanner()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/scan")
            assert resp.status_code == 409


@pytest.mark.asyncio
class TestScanStatus:
    async def test_no_scanner(self, client):
        """GET /api/scan/status without scanner should return 503."""
        resp = await client.get("/api/scan/status")
        assert resp.status_code == 503

    async def test_scan_status(self, test_app):
        """GET /api/scan/status should return scanner status."""
        from httpx import ASGITransport, AsyncClient

        app, db_path, scan_dir, thumb_dir = test_app

        class MockScanner:
            is_scanning = True
            total_files = 100
            processed_files = 42

        app.state.scanner = MockScanner()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/scan/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["scanning"] is True
            assert data["total_files"] == 100
            assert data["processed_files"] == 42


@pytest.mark.asyncio
class TestRebuildFtsIndex:
    async def test_rebuild_fts_empty(self, client):
        """POST /api/scan/reindex on empty DB should succeed."""
        resp = await client.post("/api/scan/reindex")
        assert resp.status_code == 200
        data = resp.json()
        assert data["models_indexed"] == 0

    async def test_rebuild_fts_with_models(self, client):
        """POST /api/scan/reindex should rebuild FTS from models."""
        db_path = client._db_path

        # Insert models without FTS entries
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                """INSERT INTO models (name, description, file_path, file_format)
                   VALUES ('dragon', 'fire breather', '/tmp/d.stl', 'STL')"""
            )
            await conn.execute(
                """INSERT INTO models (name, description, file_path, file_format)
                   VALUES ('cube', 'simple shape', '/tmp/c.stl', 'STL')"""
            )
            await conn.commit()

        resp = await client.post("/api/scan/reindex")
        assert resp.status_code == 200
        data = resp.json()
        assert data["models_indexed"] == 2

        # Verify FTS works after reindex
        resp = await client.get("/api/search?q=dragon")
        data = resp.json()
        assert data["total"] == 1
