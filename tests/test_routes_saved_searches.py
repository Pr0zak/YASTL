"""Tests for app.api.routes_saved_searches API endpoints."""

import pytest


@pytest.mark.asyncio
class TestListSavedSearches:
    async def test_empty_saved_searches(self, client):
        """GET /api/saved-searches should return empty list."""
        resp = await client.get("/api/saved-searches")
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved_searches"] == []

    async def test_list_saved_searches(self, client):
        """GET /api/saved-searches should return all saved searches."""
        await client.post(
            "/api/saved-searches",
            json={"name": "Search 1", "query": "cube"},
        )
        await client.post(
            "/api/saved-searches",
            json={"name": "Search 2", "query": "sphere"},
        )

        resp = await client.get("/api/saved-searches")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["saved_searches"]) == 2


@pytest.mark.asyncio
class TestCreateSavedSearch:
    async def test_create_saved_search(self, client):
        """POST /api/saved-searches should create a saved search."""
        resp = await client.post(
            "/api/saved-searches",
            json={
                "name": "My Search",
                "query": "robot",
                "filters": {"tags": ["red", "blue"]},
                "sort_by": "name",
                "sort_order": "asc",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Search"
        assert data["query"] == "robot"
        assert data["filters"] == {"tags": ["red", "blue"]}
        assert data["sort_by"] == "name"
        assert data["sort_order"] == "asc"
        assert "id" in data

    async def test_create_saved_search_minimal(self, client):
        """POST /api/saved-searches with just name should work."""
        resp = await client.post(
            "/api/saved-searches", json={"name": "Minimal"}
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Minimal"
        assert data["query"] == ""
        assert data["filters"] == {}

    async def test_create_saved_search_empty_name(self, client):
        """POST /api/saved-searches with empty name should return 400."""
        resp = await client.post(
            "/api/saved-searches", json={"name": ""}
        )
        assert resp.status_code == 400

    async def test_create_saved_search_missing_name(self, client):
        """POST /api/saved-searches without name should return 400."""
        resp = await client.post("/api/saved-searches", json={})
        assert resp.status_code == 400

    async def test_create_saved_search_invalid_sort_order(self, client):
        """POST /api/saved-searches with bad sort_order should return 400."""
        resp = await client.post(
            "/api/saved-searches",
            json={"name": "Bad", "sort_order": "invalid"},
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestUpdateSavedSearch:
    async def test_update_saved_search(self, client):
        """PUT /api/saved-searches/{id} should update fields."""
        resp = await client.post(
            "/api/saved-searches",
            json={"name": "Original", "query": "old"},
        )
        sid = resp.json()["id"]

        resp = await client.put(
            f"/api/saved-searches/{sid}",
            json={"name": "Updated", "query": "new"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated"
        assert data["query"] == "new"

    async def test_update_saved_search_not_found(self, client):
        """PUT /api/saved-searches/9999 should return 404."""
        resp = await client.put(
            "/api/saved-searches/9999", json={"name": "X"}
        )
        assert resp.status_code == 404

    async def test_update_saved_search_no_fields(self, client):
        """PUT /api/saved-searches/{id} with no fields should return 400."""
        resp = await client.post(
            "/api/saved-searches", json={"name": "NoUpdate"}
        )
        sid = resp.json()["id"]

        resp = await client.put(f"/api/saved-searches/{sid}", json={})
        assert resp.status_code == 400

    async def test_update_saved_search_invalid_sort_order(self, client):
        """PUT /api/saved-searches/{id} with bad sort_order should return 400."""
        resp = await client.post(
            "/api/saved-searches", json={"name": "Test"}
        )
        sid = resp.json()["id"]

        resp = await client.put(
            f"/api/saved-searches/{sid}",
            json={"sort_order": "invalid"},
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestDeleteSavedSearch:
    async def test_delete_saved_search(self, client):
        """DELETE /api/saved-searches/{id} should delete the search."""
        resp = await client.post(
            "/api/saved-searches", json={"name": "ToDelete"}
        )
        sid = resp.json()["id"]

        resp = await client.delete(f"/api/saved-searches/{sid}")
        assert resp.status_code == 200

        # Verify gone
        resp = await client.get("/api/saved-searches")
        assert len(resp.json()["saved_searches"]) == 0

    async def test_delete_saved_search_not_found(self, client):
        """DELETE /api/saved-searches/9999 should return 404."""
        resp = await client.delete("/api/saved-searches/9999")
        assert resp.status_code == 404
