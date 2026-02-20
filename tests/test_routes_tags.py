"""Tests for app.api.routes_tags API endpoints."""

import pytest
import aiosqlite

from tests.conftest import insert_test_model


@pytest.mark.asyncio
class TestListTags:
    async def test_empty_tags(self, client):
        """GET /api/tags should return empty list when no tags exist."""
        resp = await client.get("/api/tags")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tags"] == []

    async def test_list_tags_with_counts(self, client):
        """GET /api/tags should return tags with model counts."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="model")

        # Create tags and link one to a model
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute("INSERT INTO tags (name) VALUES ('red')")
            tag_id = cursor.lastrowid
            await conn.execute(
                "INSERT INTO model_tags (model_id, tag_id) VALUES (?, ?)",
                (model_id, tag_id),
            )
            await conn.execute("INSERT INTO tags (name) VALUES ('blue')")
            await conn.commit()

        resp = await client.get("/api/tags")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["tags"]) == 2

        # Find the 'red' tag - it should have model_count=1
        red_tag = next(t for t in data["tags"] if t["name"] == "red")
        assert red_tag["model_count"] == 1

        # 'blue' tag has no models
        blue_tag = next(t for t in data["tags"] if t["name"] == "blue")
        assert blue_tag["model_count"] == 0


@pytest.mark.asyncio
class TestCreateTag:
    async def test_create_tag(self, client):
        """POST /api/tags should create a new tag."""
        resp = await client.post("/api/tags", json={"name": "new_tag"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "new_tag"
        assert "id" in data

    async def test_create_tag_strips_whitespace(self, client):
        """POST /api/tags should strip whitespace from name."""
        resp = await client.post("/api/tags", json={"name": "  spaced  "})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "spaced"

    async def test_create_duplicate_tag(self, client):
        """POST /api/tags with duplicate name should return 409."""
        await client.post("/api/tags", json={"name": "dup"})
        resp = await client.post("/api/tags", json={"name": "dup"})
        assert resp.status_code == 409

    async def test_create_tag_empty_name(self, client):
        """POST /api/tags with empty name should return 400."""
        resp = await client.post("/api/tags", json={"name": ""})
        assert resp.status_code == 400

    async def test_create_tag_missing_name(self, client):
        """POST /api/tags without name should return 400."""
        resp = await client.post("/api/tags", json={})
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestDeleteTag:
    async def test_delete_existing_tag(self, client):
        """DELETE /api/tags/{id} should delete the tag."""
        resp = await client.post("/api/tags", json={"name": "to_delete"})
        tag_id = resp.json()["id"]

        resp = await client.delete(f"/api/tags/{tag_id}")
        assert resp.status_code == 200

        # Verify it's gone
        resp = await client.get("/api/tags")
        names = [t["name"] for t in resp.json()["tags"]]
        assert "to_delete" not in names

    async def test_delete_nonexistent_tag(self, client):
        """DELETE /api/tags/999 should return 404."""
        resp = await client.delete("/api/tags/999")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestRenameTag:
    async def test_rename_tag(self, client):
        """PUT /api/tags/{id} should rename the tag."""
        resp = await client.post("/api/tags", json={"name": "old_name"})
        tag_id = resp.json()["id"]

        resp = await client.put(f"/api/tags/{tag_id}", json={"name": "new_name"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "new_name"

    async def test_rename_to_existing_name(self, client):
        """PUT /api/tags/{id} to an existing name should return 409."""
        await client.post("/api/tags", json={"name": "first"})
        resp = await client.post("/api/tags", json={"name": "second"})
        second_id = resp.json()["id"]

        resp = await client.put(f"/api/tags/{second_id}", json={"name": "first"})
        assert resp.status_code == 409

    async def test_rename_nonexistent_tag(self, client):
        """PUT /api/tags/999 should return 404."""
        resp = await client.put("/api/tags/999", json={"name": "new"})
        assert resp.status_code == 404

    async def test_rename_empty_name(self, client):
        """PUT /api/tags/{id} with empty name should return 400."""
        resp = await client.post("/api/tags", json={"name": "tag"})
        tag_id = resp.json()["id"]

        resp = await client.put(f"/api/tags/{tag_id}", json={"name": ""})
        assert resp.status_code == 400
