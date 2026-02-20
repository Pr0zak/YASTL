"""Tests for app.api.routes_categories API endpoints."""

import pytest
import aiosqlite



@pytest.mark.asyncio
class TestListCategories:
    async def test_empty_categories(self, client):
        """GET /api/categories should return empty list when no categories."""
        resp = await client.get("/api/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert data["categories"] == []

    async def test_list_categories_tree(self, client):
        """GET /api/categories should return a nested tree structure."""
        db_path = client._db_path

        async with aiosqlite.connect(db_path) as conn:
            # Create parent category
            cursor = await conn.execute(
                "INSERT INTO categories (name) VALUES ('Figurines')"
            )
            parent_id = cursor.lastrowid

            # Create child category
            await conn.execute(
                "INSERT INTO categories (name, parent_id) VALUES ('Animals', ?)",
                (parent_id,),
            )
            await conn.commit()

        resp = await client.get("/api/categories")
        assert resp.status_code == 200
        data = resp.json()

        # Should have one root category
        assert len(data["categories"]) == 1
        root = data["categories"][0]
        assert root["name"] == "Figurines"
        assert len(root["children"]) == 1
        assert root["children"][0]["name"] == "Animals"


@pytest.mark.asyncio
class TestCreateCategory:
    async def test_create_root_category(self, client):
        """POST /api/categories should create a root category."""
        resp = await client.post(
            "/api/categories", json={"name": "Figurines"}
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Figurines"
        assert data["parent_id"] is None

    async def test_create_child_category(self, client):
        """POST /api/categories with parent_id should create a child."""
        resp = await client.post(
            "/api/categories", json={"name": "Figurines"}
        )
        parent_id = resp.json()["id"]

        resp = await client.post(
            "/api/categories",
            json={"name": "Animals", "parent_id": parent_id},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Animals"
        assert data["parent_id"] == parent_id

    async def test_create_duplicate_category(self, client):
        """POST /api/categories with duplicate name+parent should return 409."""
        await client.post("/api/categories", json={"name": "Figurines"})
        resp = await client.post("/api/categories", json={"name": "Figurines"})
        assert resp.status_code == 409

    async def test_create_same_name_different_parent(self, client):
        """Categories with same name but different parents should be allowed."""
        resp = await client.post(
            "/api/categories", json={"name": "Parent1"}
        )
        p1_id = resp.json()["id"]

        resp = await client.post(
            "/api/categories", json={"name": "Parent2"}
        )
        p2_id = resp.json()["id"]

        resp = await client.post(
            "/api/categories",
            json={"name": "Child", "parent_id": p1_id},
        )
        assert resp.status_code == 201

        resp = await client.post(
            "/api/categories",
            json={"name": "Child", "parent_id": p2_id},
        )
        assert resp.status_code == 201

    async def test_create_empty_name(self, client):
        """POST /api/categories with empty name should return 400."""
        resp = await client.post("/api/categories", json={"name": ""})
        assert resp.status_code == 400

    async def test_create_nonexistent_parent(self, client):
        """POST /api/categories with nonexistent parent should return 404."""
        resp = await client.post(
            "/api/categories", json={"name": "child", "parent_id": 999}
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestUpdateCategory:
    async def test_update_name(self, client):
        """PUT /api/categories/{id} should update the name."""
        resp = await client.post(
            "/api/categories", json={"name": "old_name"}
        )
        cat_id = resp.json()["id"]

        resp = await client.put(
            f"/api/categories/{cat_id}", json={"name": "new_name"}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "new_name"

    async def test_update_parent(self, client):
        """PUT /api/categories/{id} should update parent_id."""
        resp = await client.post("/api/categories", json={"name": "A"})
        a_id = resp.json()["id"]

        resp = await client.post("/api/categories", json={"name": "B"})
        b_id = resp.json()["id"]

        resp = await client.put(
            f"/api/categories/{b_id}", json={"parent_id": a_id}
        )
        assert resp.status_code == 200
        assert resp.json()["parent_id"] == a_id

    async def test_update_self_parent(self, client):
        """Setting a category as its own parent should return 400."""
        resp = await client.post("/api/categories", json={"name": "self"})
        cat_id = resp.json()["id"]

        resp = await client.put(
            f"/api/categories/{cat_id}", json={"parent_id": cat_id}
        )
        assert resp.status_code == 400

    async def test_update_nonexistent_category(self, client):
        """PUT /api/categories/999 should return 404."""
        resp = await client.put("/api/categories/999", json={"name": "new"})
        assert resp.status_code == 404

    async def test_update_no_fields(self, client):
        """PUT /api/categories/{id} with no fields should return 400."""
        resp = await client.post("/api/categories", json={"name": "cat"})
        cat_id = resp.json()["id"]

        resp = await client.put(f"/api/categories/{cat_id}", json={})
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestDeleteCategory:
    async def test_delete_leaf_category(self, client):
        """DELETE /api/categories/{id} should delete a leaf category."""
        resp = await client.post("/api/categories", json={"name": "leaf"})
        cat_id = resp.json()["id"]

        resp = await client.delete(f"/api/categories/{cat_id}")
        assert resp.status_code == 200

        # Verify it's gone
        resp = await client.get("/api/categories")
        assert len(resp.json()["categories"]) == 0

    async def test_delete_parent_reassigns_children(self, client):
        """Deleting a parent category should move children to grandparent."""
        resp = await client.post("/api/categories", json={"name": "Parent"})
        parent_id = resp.json()["id"]

        resp = await client.post(
            "/api/categories",
            json={"name": "Child", "parent_id": parent_id},
        )
        resp.json()["id"]  # child created

        # Delete the parent
        resp = await client.delete(f"/api/categories/{parent_id}")
        assert resp.status_code == 200

        # Child should now be a root category
        resp = await client.get("/api/categories")
        data = resp.json()
        assert len(data["categories"]) == 1
        assert data["categories"][0]["name"] == "Child"
        assert data["categories"][0]["parent_id"] is None

    async def test_delete_nonexistent_category(self, client):
        """DELETE /api/categories/999 should return 404."""
        resp = await client.delete("/api/categories/999")
        assert resp.status_code == 404
