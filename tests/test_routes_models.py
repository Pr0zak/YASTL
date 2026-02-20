"""Tests for app.api.routes_models API endpoints."""

import pytest
import aiosqlite

from tests.conftest import insert_test_model


@pytest.mark.asyncio
class TestListModels:
    async def test_empty_list(self, client):
        """GET /api/models should return empty list when no models exist."""
        resp = await client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["models"] == []
        assert data["total"] == 0

    async def test_list_with_models(self, client):
        """GET /api/models should return inserted models."""
        db_path = client._db_path
        await insert_test_model(db_path, name="cube", file_path="/tmp/cube.stl")
        await insert_test_model(db_path, name="sphere", file_path="/tmp/sphere.stl")

        resp = await client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["models"]) == 2

    async def test_pagination_limit(self, client):
        """GET /api/models should respect limit parameter."""
        db_path = client._db_path
        for i in range(5):
            await insert_test_model(
                db_path, name=f"model_{i}", file_path=f"/tmp/m{i}.stl"
            )

        resp = await client.get("/api/models?limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["models"]) == 2

    async def test_pagination_offset(self, client):
        """GET /api/models should respect offset parameter."""
        db_path = client._db_path
        for i in range(5):
            await insert_test_model(
                db_path, name=f"model_{i}", file_path=f"/tmp/m{i}.stl"
            )

        resp = await client.get("/api/models?limit=2&offset=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["models"]) == 2

    async def test_filter_by_format(self, client):
        """GET /api/models?format=OBJ should filter by format."""
        db_path = client._db_path
        await insert_test_model(
            db_path, name="cube", file_path="/tmp/cube.stl", file_format="STL"
        )
        await insert_test_model(
            db_path, name="sphere", file_path="/tmp/sphere.obj", file_format="obj"
        )

        resp = await client.get("/api/models?format=obj")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["models"][0]["name"] == "sphere"

    async def test_filter_by_tag(self, client):
        """GET /api/models?tag=red should filter models by tag."""
        db_path = client._db_path
        model_id = await insert_test_model(
            db_path, name="tagged", file_path="/tmp/tagged.stl"
        )
        await insert_test_model(
            db_path, name="untagged", file_path="/tmp/untagged.stl"
        )

        # Add a tag to the first model
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "INSERT INTO tags (name) VALUES ('red')"
            )
            tag_id = cursor.lastrowid
            await conn.execute(
                "INSERT INTO model_tags (model_id, tag_id) VALUES (?, ?)",
                (model_id, tag_id),
            )
            await conn.commit()

        resp = await client.get("/api/models?tag=red")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["models"][0]["name"] == "tagged"


@pytest.mark.asyncio
class TestGetModel:
    async def test_get_existing_model(self, client):
        """GET /api/models/{id} should return the model."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="dragon")

        resp = await client.get(f"/api/models/{model_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "dragon"
        assert data["id"] == model_id
        assert "tags" in data
        assert "categories" in data

    async def test_get_nonexistent_model(self, client):
        """GET /api/models/999 should return 404."""
        resp = await client.get("/api/models/999")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestUpdateModel:
    async def test_update_name(self, client):
        """PUT /api/models/{id} should update the model name."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="old_name")

        resp = await client.put(
            f"/api/models/{model_id}",
            json={"name": "new_name"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "new_name"

    async def test_update_description(self, client):
        """PUT /api/models/{id} should update the description."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="model")

        resp = await client.put(
            f"/api/models/{model_id}",
            json={"description": "updated description"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "updated description"

    async def test_update_both_fields(self, client):
        """PUT /api/models/{id} should update both name and description."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="old")

        resp = await client.put(
            f"/api/models/{model_id}",
            json={"name": "new", "description": "new desc"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "new"
        assert data["description"] == "new desc"

    async def test_update_no_fields(self, client):
        """PUT /api/models/{id} with empty body should return 400."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="model")

        resp = await client.put(f"/api/models/{model_id}", json={})
        assert resp.status_code == 400

    async def test_update_nonexistent_model(self, client):
        """PUT /api/models/999 should return 404."""
        resp = await client.put("/api/models/999", json={"name": "new"})
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestDeleteModel:
    async def test_delete_existing(self, client):
        """DELETE /api/models/{id} should delete the model."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="to_delete")

        resp = await client.delete(f"/api/models/{model_id}")
        assert resp.status_code == 200

        # Verify it's gone
        resp = await client.get(f"/api/models/{model_id}")
        assert resp.status_code == 404

    async def test_delete_nonexistent(self, client):
        """DELETE /api/models/999 should return 404."""
        resp = await client.delete("/api/models/999")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestFindDuplicates:
    async def test_no_duplicates(self, client):
        """GET /api/models/duplicates should return empty when no duplicates."""
        resp = await client.get("/api/models/duplicates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["duplicate_groups"] == []
        assert data["total_groups"] == 0

    async def test_with_duplicates(self, client):
        """GET /api/models/duplicates should find groups of duplicate files."""
        db_path = client._db_path
        shared_hash = "deadbeef" * 4
        await insert_test_model(
            db_path, name="dup1", file_path="/tmp/dup1.stl", file_hash=shared_hash
        )
        await insert_test_model(
            db_path, name="dup2", file_path="/tmp/dup2.stl", file_hash=shared_hash
        )
        await insert_test_model(
            db_path, name="unique", file_path="/tmp/unique.stl", file_hash="unique_hash"
        )

        resp = await client.get("/api/models/duplicates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_groups"] == 1
        assert len(data["duplicate_groups"]) == 1
        assert data["duplicate_groups"][0]["count"] == 2


@pytest.mark.asyncio
class TestModelTags:
    async def test_add_tags(self, client):
        """POST /api/models/{id}/tags should add tags to a model."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="model")

        resp = await client.post(
            f"/api/models/{model_id}/tags",
            json={"tags": ["red", "blue"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "red" in data["tags"]
        assert "blue" in data["tags"]

    async def test_add_tags_invalid_body(self, client):
        """POST /api/models/{id}/tags with invalid body should return 400."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="model")

        resp = await client.post(
            f"/api/models/{model_id}/tags", json={"tags": []}
        )
        assert resp.status_code == 400

    async def test_add_tags_nonexistent_model(self, client):
        """POST /api/models/999/tags should return 404."""
        resp = await client.post(
            "/api/models/999/tags", json={"tags": ["red"]}
        )
        assert resp.status_code == 404

    async def test_remove_tag(self, client):
        """DELETE /api/models/{id}/tags/{name} should remove the tag."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="model")

        # First add a tag
        await client.post(
            f"/api/models/{model_id}/tags", json={"tags": ["red"]}
        )

        # Then remove it
        resp = await client.delete(f"/api/models/{model_id}/tags/red")
        assert resp.status_code == 200

    async def test_remove_nonexistent_tag(self, client):
        """DELETE /api/models/{id}/tags/nonexistent should return 404."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="model")

        resp = await client.delete(f"/api/models/{model_id}/tags/nonexistent")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestModelCategories:
    async def test_add_category(self, client):
        """POST /api/models/{id}/categories should add a category."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="model")

        # Create a category first
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "INSERT INTO categories (name) VALUES ('Figurines')"
            )
            cat_id = cursor.lastrowid
            await conn.commit()

        resp = await client.post(
            f"/api/models/{model_id}/categories",
            json={"category_id": cat_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Figurines" in data["categories"]

    async def test_add_category_missing_id(self, client):
        """POST /api/models/{id}/categories without category_id returns 400."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="model")

        resp = await client.post(
            f"/api/models/{model_id}/categories", json={}
        )
        assert resp.status_code == 400

    async def test_remove_category(self, client):
        """DELETE /api/models/{id}/categories/{cat_id} should remove it."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="model")

        # Create and assign a category
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "INSERT INTO categories (name) VALUES ('Tools')"
            )
            cat_id = cursor.lastrowid
            await conn.execute(
                "INSERT INTO model_categories (model_id, category_id) VALUES (?, ?)",
                (model_id, cat_id),
            )
            await conn.commit()

        resp = await client.delete(
            f"/api/models/{model_id}/categories/{cat_id}"
        )
        assert resp.status_code == 200

    async def test_remove_nonexistent_category_link(self, client):
        """Removing a category not linked should return 404."""
        db_path = client._db_path
        model_id = await insert_test_model(db_path, name="model")

        resp = await client.delete(f"/api/models/{model_id}/categories/999")
        assert resp.status_code == 404
