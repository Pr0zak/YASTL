"""Tests for backup/export endpoints."""

import json

import pytest

from tests.conftest import insert_test_model


@pytest.mark.asyncio
class TestBackup:
    async def test_manifest_includes_curation(self, client):
        db_path = client._db_path
        mid = await insert_test_model(db_path, name="dragon", file_path="/d.stl",
                                      file_hash="hash123")
        await client.post(f"/api/models/{mid}/tags", json={"tags": ["mini"]})
        await client.post(f"/api/models/{mid}/favorite")

        resp = await client.get("/api/backup/manifest")
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")
        data = json.loads(resp.content)
        assert data["model_count"] == 1
        entry = data["models"][0]
        assert entry["hash"] == "hash123"
        assert "mini" in entry["tags"]
        assert entry["favorite"] is True

    async def test_database_snapshot_downloads(self, client):
        await insert_test_model(client._db_path, name="m", file_path="/m.stl")
        resp = await client.get("/api/backup/database")
        assert resp.status_code == 200
        # SQLite files start with this magic header
        assert resp.content[:16].startswith(b"SQLite format 3")
