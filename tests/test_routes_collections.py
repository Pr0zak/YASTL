"""Tests for app.api.routes_collections API endpoints."""

import pytest
import aiosqlite

from tests.conftest import insert_test_model


@pytest.mark.asyncio
class TestListCollections:
    async def test_empty_collections(self, client):
        """GET /api/collections should return empty list."""
        resp = await client.get("/api/collections")
        assert resp.status_code == 200
        data = resp.json()
        assert data["collections"] == []

    async def test_list_collections_with_counts(self, client):
        """GET /api/collections should return collections with model counts."""
        db_path = client._db_path
        mid = await insert_test_model(db_path)

        # Create collection and add a model
        resp = await client.post(
            "/api/collections", json={"name": "My Collection"}
        )
        cid = resp.json()["id"]
        await client.post(
            f"/api/collections/{cid}/models", json={"model_ids": [mid]}
        )

        resp = await client.get("/api/collections")
        assert resp.status_code == 200
        collections = resp.json()["collections"]
        assert len(collections) == 1
        assert collections[0]["name"] == "My Collection"
        assert collections[0]["model_count"] == 1


@pytest.mark.asyncio
class TestCreateCollection:
    async def test_create_collection(self, client):
        """POST /api/collections should create a collection."""
        resp = await client.post(
            "/api/collections",
            json={"name": "Test", "description": "A test", "color": "#ff0000"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test"
        assert data["description"] == "A test"
        assert data["color"] == "#ff0000"
        assert data["model_count"] == 0
        assert "id" in data

    async def test_create_collection_minimal(self, client):
        """POST /api/collections with just name should work."""
        resp = await client.post(
            "/api/collections", json={"name": "Minimal"}
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Minimal"

    async def test_create_collection_empty_name(self, client):
        """POST /api/collections with empty name should return 400."""
        resp = await client.post("/api/collections", json={"name": ""})
        assert resp.status_code == 400

    async def test_create_collection_missing_name(self, client):
        """POST /api/collections without name should return 400."""
        resp = await client.post("/api/collections", json={})
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestGetCollection:
    async def test_get_collection(self, client):
        """GET /api/collections/{id} should return collection with models."""
        db_path = client._db_path
        mid = await insert_test_model(db_path)

        resp = await client.post(
            "/api/collections", json={"name": "Detail"}
        )
        cid = resp.json()["id"]
        await client.post(
            f"/api/collections/{cid}/models", json={"model_ids": [mid]}
        )

        resp = await client.get(f"/api/collections/{cid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Detail"
        assert data["model_count"] == 1
        assert len(data["models"]) == 1
        assert data["models"][0]["id"] == mid

    async def test_get_collection_not_found(self, client):
        """GET /api/collections/9999 should return 404."""
        resp = await client.get("/api/collections/9999")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestUpdateCollection:
    async def test_update_collection_name(self, client):
        """PUT /api/collections/{id} should update the name."""
        resp = await client.post(
            "/api/collections", json={"name": "Old Name"}
        )
        cid = resp.json()["id"]

        resp = await client.put(
            f"/api/collections/{cid}", json={"name": "New Name"}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    async def test_update_collection_not_found(self, client):
        """PUT /api/collections/9999 should return 404."""
        resp = await client.put(
            "/api/collections/9999", json={"name": "X"}
        )
        assert resp.status_code == 404

    async def test_update_collection_no_fields(self, client):
        """PUT /api/collections/{id} with no fields should return 400."""
        resp = await client.post(
            "/api/collections", json={"name": "NoUpdate"}
        )
        cid = resp.json()["id"]

        resp = await client.put(f"/api/collections/{cid}", json={})
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestDeleteCollection:
    async def test_delete_collection(self, client):
        """DELETE /api/collections/{id} should delete the collection."""
        resp = await client.post(
            "/api/collections", json={"name": "ToDelete"}
        )
        cid = resp.json()["id"]

        resp = await client.delete(f"/api/collections/{cid}")
        assert resp.status_code == 200

        # Verify gone
        resp = await client.get(f"/api/collections/{cid}")
        assert resp.status_code == 404

    async def test_delete_collection_not_found(self, client):
        """DELETE /api/collections/9999 should return 404."""
        resp = await client.delete("/api/collections/9999")
        assert resp.status_code == 404

    async def test_delete_collection_preserves_models(self, client):
        """Deleting a collection should not delete the models in it."""
        db_path = client._db_path
        mid = await insert_test_model(db_path)

        resp = await client.post(
            "/api/collections", json={"name": "Temp"}
        )
        cid = resp.json()["id"]
        await client.post(
            f"/api/collections/{cid}/models", json={"model_ids": [mid]}
        )

        await client.delete(f"/api/collections/{cid}")

        # Model should still exist
        resp = await client.get(f"/api/models/{mid}")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestCollectionModels:
    async def test_add_models_to_collection(self, client):
        """POST /api/collections/{id}/models should add models."""
        db_path = client._db_path
        m1 = await insert_test_model(db_path, name="m1", file_path="/tmp/c1.stl")
        m2 = await insert_test_model(
            db_path, name="m2", file_path="/tmp/c2.stl", file_hash="h2"
        )

        resp = await client.post(
            "/api/collections", json={"name": "WithModels"}
        )
        cid = resp.json()["id"]

        resp = await client.post(
            f"/api/collections/{cid}/models",
            json={"model_ids": [m1, m2]},
        )
        assert resp.status_code == 200
        assert resp.json()["added"] >= 1

    async def test_add_models_missing_body(self, client):
        """POST /api/collections/{id}/models with empty list should return 400."""
        resp = await client.post(
            "/api/collections", json={"name": "Empty"}
        )
        cid = resp.json()["id"]

        resp = await client.post(
            f"/api/collections/{cid}/models", json={"model_ids": []}
        )
        assert resp.status_code == 400

    async def test_add_models_collection_not_found(self, client):
        """POST /api/collections/9999/models should return 404."""
        resp = await client.post(
            "/api/collections/9999/models", json={"model_ids": [1]}
        )
        assert resp.status_code == 404

    async def test_remove_model_from_collection(self, client):
        """DELETE /api/collections/{cid}/models/{mid} should remove model."""
        db_path = client._db_path
        mid = await insert_test_model(db_path)

        resp = await client.post(
            "/api/collections", json={"name": "Remove"}
        )
        cid = resp.json()["id"]
        await client.post(
            f"/api/collections/{cid}/models", json={"model_ids": [mid]}
        )

        resp = await client.delete(f"/api/collections/{cid}/models/{mid}")
        assert resp.status_code == 200

        # Verify removed
        resp = await client.get(f"/api/collections/{cid}")
        assert resp.json()["model_count"] == 0

    async def test_remove_model_not_in_collection(self, client):
        """DELETE /api/collections/{cid}/models/{mid} returns 404 if not in collection."""
        resp = await client.post(
            "/api/collections", json={"name": "X"}
        )
        cid = resp.json()["id"]

        resp = await client.delete(f"/api/collections/{cid}/models/9999")
        assert resp.status_code == 404

    async def test_reorder_models(self, client):
        """PUT /api/collections/{id}/models/reorder should set positions."""
        db_path = client._db_path
        m1 = await insert_test_model(db_path, name="r1", file_path="/tmp/r1.stl")
        m2 = await insert_test_model(
            db_path, name="r2", file_path="/tmp/r2.stl", file_hash="rh2"
        )

        resp = await client.post(
            "/api/collections", json={"name": "Reorder"}
        )
        cid = resp.json()["id"]
        await client.post(
            f"/api/collections/{cid}/models", json={"model_ids": [m1, m2]}
        )

        resp = await client.put(
            f"/api/collections/{cid}/models/reorder",
            json={"model_ids": [m2, m1]},
        )
        assert resp.status_code == 200
        assert resp.json()["order"] == [m2, m1]

    async def test_reorder_collection_not_found(self, client):
        """PUT /api/collections/9999/models/reorder should return 404."""
        resp = await client.put(
            "/api/collections/9999/models/reorder",
            json={"model_ids": [1, 2]},
        )
        assert resp.status_code == 404
