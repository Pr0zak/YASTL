"""Tests for app.api.routes_favorites API endpoints."""

import pytest
import aiosqlite

from tests.conftest import insert_test_model


@pytest.mark.asyncio
class TestListFavorites:
    async def test_empty_favorites(self, client):
        """GET /api/favorites should return empty list when no favorites exist."""
        resp = await client.get("/api/favorites")
        assert resp.status_code == 200
        data = resp.json()
        assert data["models"] == []
        assert data["total"] == 0

    async def test_list_favorites(self, client):
        """GET /api/favorites should return favorited models."""
        db_path = client._db_path
        m1 = await insert_test_model(db_path, name="fav_model", file_path="/tmp/f1.stl")
        m2 = await insert_test_model(db_path, name="not_fav", file_path="/tmp/f2.stl")

        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                "INSERT INTO favorites (model_id) VALUES (?)", (m1,)
            )
            await conn.commit()

        resp = await client.get("/api/favorites")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["models"]) == 1
        assert data["models"][0]["name"] == "fav_model"
        assert data["models"][0]["is_favorite"] is True

    async def test_favorites_pagination(self, client):
        """GET /api/favorites supports limit/offset."""
        db_path = client._db_path
        for i in range(5):
            mid = await insert_test_model(
                db_path, name=f"model_{i}", file_path=f"/tmp/p{i}.stl",
                file_hash=f"hash{i}",
            )
            async with aiosqlite.connect(db_path) as conn:
                await conn.execute(
                    "INSERT INTO favorites (model_id) VALUES (?)", (mid,)
                )
                await conn.commit()

        resp = await client.get("/api/favorites?limit=2&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["models"]) == 2


@pytest.mark.asyncio
class TestAddFavorite:
    async def test_add_favorite(self, client):
        """POST /api/models/{id}/favorite should add model to favorites."""
        db_path = client._db_path
        mid = await insert_test_model(db_path)

        resp = await client.post(f"/api/models/{mid}/favorite")
        assert resp.status_code == 201
        data = resp.json()
        assert data["model_id"] == mid

    async def test_add_favorite_idempotent(self, client):
        """POST /api/models/{id}/favorite twice should not error."""
        db_path = client._db_path
        mid = await insert_test_model(db_path)

        resp = await client.post(f"/api/models/{mid}/favorite")
        assert resp.status_code == 201
        resp = await client.post(f"/api/models/{mid}/favorite")
        assert resp.status_code == 201

    async def test_add_favorite_nonexistent_model(self, client):
        """POST /api/models/9999/favorite should return 404."""
        resp = await client.post("/api/models/9999/favorite")
        assert resp.status_code == 404

    async def test_favorite_appears_in_model_response(self, client):
        """After favoriting, GET /api/models/{id} should have is_favorite=true."""
        db_path = client._db_path
        mid = await insert_test_model(db_path)

        await client.post(f"/api/models/{mid}/favorite")

        resp = await client.get(f"/api/models/{mid}")
        assert resp.status_code == 200
        assert resp.json()["is_favorite"] is True


@pytest.mark.asyncio
class TestRemoveFavorite:
    async def test_remove_favorite(self, client):
        """DELETE /api/models/{id}/favorite should remove from favorites."""
        db_path = client._db_path
        mid = await insert_test_model(db_path)

        # Add then remove
        await client.post(f"/api/models/{mid}/favorite")
        resp = await client.delete(f"/api/models/{mid}/favorite")
        assert resp.status_code == 200

        # Verify removed
        resp = await client.get("/api/favorites")
        assert resp.json()["total"] == 0

    async def test_remove_favorite_not_in_favorites(self, client):
        """DELETE /api/models/{id}/favorite when not favorited should return 404."""
        db_path = client._db_path
        mid = await insert_test_model(db_path)

        resp = await client.delete(f"/api/models/{mid}/favorite")
        assert resp.status_code == 404
