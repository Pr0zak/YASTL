"""Tests for app.api.routes_bulk API endpoints."""

import pytest
import aiosqlite

from tests.conftest import insert_test_model


@pytest.mark.asyncio
class TestBulkTags:
    async def test_bulk_add_tags(self, client):
        """POST /api/bulk/tags should add tags to multiple models."""
        db_path = client._db_path
        m1 = await insert_test_model(db_path, name="bt1", file_path="/tmp/bt1.stl")
        m2 = await insert_test_model(
            db_path, name="bt2", file_path="/tmp/bt2.stl", file_hash="bth2"
        )

        resp = await client.post(
            "/api/bulk/tags",
            json={"model_ids": [m1, m2], "tags": ["red", "blue"]},
        )
        assert resp.status_code == 200
        assert resp.json()["affected"] > 0

        # Verify tags were applied
        resp = await client.get(f"/api/models/{m1}")
        tags = resp.json()["tags"]
        assert "red" in tags
        assert "blue" in tags

    async def test_bulk_add_tags_missing_model_ids(self, client):
        """POST /api/bulk/tags with empty model_ids should return 400."""
        resp = await client.post(
            "/api/bulk/tags", json={"model_ids": [], "tags": ["x"]}
        )
        assert resp.status_code == 400

    async def test_bulk_add_tags_missing_tags(self, client):
        """POST /api/bulk/tags with empty tags should return 400."""
        resp = await client.post(
            "/api/bulk/tags", json={"model_ids": [1], "tags": []}
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestBulkCategories:
    async def test_bulk_add_categories(self, client):
        """POST /api/bulk/categories should add categories to models."""
        db_path = client._db_path
        m1 = await insert_test_model(db_path, name="bc1", file_path="/tmp/bc1.stl")

        # Create a category
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "INSERT INTO categories (name) VALUES ('TestCat')"
            )
            cat_id = cursor.lastrowid
            await conn.commit()

        resp = await client.post(
            "/api/bulk/categories",
            json={"model_ids": [m1], "category_ids": [cat_id]},
        )
        assert resp.status_code == 200
        assert resp.json()["affected"] > 0

    async def test_bulk_add_categories_missing_ids(self, client):
        """POST /api/bulk/categories with empty lists should return 400."""
        resp = await client.post(
            "/api/bulk/categories",
            json={"model_ids": [], "category_ids": [1]},
        )
        assert resp.status_code == 400

        resp = await client.post(
            "/api/bulk/categories",
            json={"model_ids": [1], "category_ids": []},
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestBulkCollections:
    async def test_bulk_add_to_collection(self, client):
        """POST /api/bulk/collections should add models to a collection."""
        db_path = client._db_path
        m1 = await insert_test_model(
            db_path, name="bcol1", file_path="/tmp/bcol1.stl"
        )
        m2 = await insert_test_model(
            db_path, name="bcol2", file_path="/tmp/bcol2.stl", file_hash="bcolh2"
        )

        resp = await client.post(
            "/api/collections", json={"name": "BulkColl"}
        )
        cid = resp.json()["id"]

        resp = await client.post(
            "/api/bulk/collections",
            json={"model_ids": [m1, m2], "collection_id": cid},
        )
        assert resp.status_code == 200
        assert resp.json()["added"] >= 1

        # Verify they're in the collection
        resp = await client.get(f"/api/collections/{cid}")
        assert resp.json()["model_count"] == 2

    async def test_bulk_add_to_collection_not_found(self, client):
        """POST /api/bulk/collections with nonexistent collection should 404."""
        resp = await client.post(
            "/api/bulk/collections",
            json={"model_ids": [1], "collection_id": 9999},
        )
        assert resp.status_code == 404

    async def test_bulk_add_to_collection_missing_ids(self, client):
        """POST /api/bulk/collections with empty model_ids should 400."""
        resp = await client.post(
            "/api/bulk/collections",
            json={"model_ids": [], "collection_id": 1},
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestBulkFavorite:
    async def test_bulk_favorite(self, client):
        """POST /api/bulk/favorite should favorite multiple models."""
        db_path = client._db_path
        m1 = await insert_test_model(
            db_path, name="bf1", file_path="/tmp/bf1.stl"
        )
        m2 = await insert_test_model(
            db_path, name="bf2", file_path="/tmp/bf2.stl", file_hash="bfh2"
        )

        resp = await client.post(
            "/api/bulk/favorite",
            json={"model_ids": [m1, m2], "favorite": True},
        )
        assert resp.status_code == 200
        assert resp.json()["affected"] == 2

        # Verify
        resp = await client.get("/api/favorites")
        assert resp.json()["total"] == 2

    async def test_bulk_unfavorite(self, client):
        """POST /api/bulk/favorite with favorite=false should unfavorite."""
        db_path = client._db_path
        mid = await insert_test_model(
            db_path, name="bunf", file_path="/tmp/bunf.stl"
        )
        await client.post(f"/api/models/{mid}/favorite")

        resp = await client.post(
            "/api/bulk/favorite",
            json={"model_ids": [mid], "favorite": False},
        )
        assert resp.status_code == 200

        resp = await client.get("/api/favorites")
        assert resp.json()["total"] == 0

    async def test_bulk_favorite_missing_ids(self, client):
        """POST /api/bulk/favorite with empty model_ids should 400."""
        resp = await client.post(
            "/api/bulk/favorite", json={"model_ids": []}
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestBulkDelete:
    async def test_bulk_delete(self, client):
        """POST /api/bulk/delete should delete multiple models."""
        db_path = client._db_path
        m1 = await insert_test_model(
            db_path, name="bd1", file_path="/tmp/bd1.stl"
        )
        m2 = await insert_test_model(
            db_path, name="bd2", file_path="/tmp/bd2.stl", file_hash="bdh2"
        )

        resp = await client.post(
            "/api/bulk/delete", json={"model_ids": [m1, m2]}
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2

        # Verify deleted
        resp = await client.get(f"/api/models/{m1}")
        assert resp.status_code == 404

    async def test_bulk_delete_skips_nonexistent(self, client):
        """POST /api/bulk/delete should skip models that don't exist."""
        db_path = client._db_path
        mid = await insert_test_model(
            db_path, name="bdx", file_path="/tmp/bdx.stl"
        )

        resp = await client.post(
            "/api/bulk/delete", json={"model_ids": [mid, 9999]}
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 1

    async def test_bulk_delete_missing_ids(self, client):
        """POST /api/bulk/delete with empty list should 400."""
        resp = await client.post(
            "/api/bulk/delete", json={"model_ids": []}
        )
        assert resp.status_code == 400
