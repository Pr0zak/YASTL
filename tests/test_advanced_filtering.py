"""Tests for advanced filtering on GET /api/models."""

import pytest
import aiosqlite

from tests.conftest import insert_test_model


async def _setup_models_with_tags_and_categories(db_path: str):
    """Create test models with tags and categories for filtering tests.

    Returns dict with model IDs and category/tag IDs.
    """
    m1 = await insert_test_model(db_path, name="cube", file_path="/tmp/af1.stl")
    m2 = await insert_test_model(
        db_path, name="sphere", file_path="/tmp/af2.stl", file_hash="afh2"
    )
    m3 = await insert_test_model(
        db_path, name="cylinder", file_path="/tmp/af3.stl", file_hash="afh3"
    )

    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("PRAGMA foreign_keys=ON")

        # Create tags
        cursor = await conn.execute("INSERT INTO tags (name) VALUES ('red')")
        red_id = cursor.lastrowid
        cursor = await conn.execute("INSERT INTO tags (name) VALUES ('blue')")
        blue_id = cursor.lastrowid
        cursor = await conn.execute("INSERT INTO tags (name) VALUES ('green')")
        green_id = cursor.lastrowid

        # Create categories
        cursor = await conn.execute(
            "INSERT INTO categories (name) VALUES ('Shapes')"
        )
        shapes_id = cursor.lastrowid
        cursor = await conn.execute(
            "INSERT INTO categories (name) VALUES ('Objects')"
        )
        objects_id = cursor.lastrowid

        # Assign tags:
        # m1 (cube): red, blue
        # m2 (sphere): red, green
        # m3 (cylinder): blue
        await conn.execute(
            "INSERT INTO model_tags VALUES (?, ?)", (m1, red_id)
        )
        await conn.execute(
            "INSERT INTO model_tags VALUES (?, ?)", (m1, blue_id)
        )
        await conn.execute(
            "INSERT INTO model_tags VALUES (?, ?)", (m2, red_id)
        )
        await conn.execute(
            "INSERT INTO model_tags VALUES (?, ?)", (m2, green_id)
        )
        await conn.execute(
            "INSERT INTO model_tags VALUES (?, ?)", (m3, blue_id)
        )

        # Assign categories:
        # m1 (cube): Shapes
        # m2 (sphere): Shapes, Objects
        # m3 (cylinder): Objects
        await conn.execute(
            "INSERT INTO model_categories VALUES (?, ?)", (m1, shapes_id)
        )
        await conn.execute(
            "INSERT INTO model_categories VALUES (?, ?)", (m2, shapes_id)
        )
        await conn.execute(
            "INSERT INTO model_categories VALUES (?, ?)", (m2, objects_id)
        )
        await conn.execute(
            "INSERT INTO model_categories VALUES (?, ?)", (m3, objects_id)
        )

        # Favorite m1
        await conn.execute(
            "INSERT INTO favorites (model_id) VALUES (?)", (m1,)
        )

        await conn.commit()

    return {
        "m1": m1, "m2": m2, "m3": m3,
        "red_id": red_id, "blue_id": blue_id, "green_id": green_id,
        "shapes_id": shapes_id, "objects_id": objects_id,
    }


@pytest.mark.asyncio
class TestMultiTagFilter:
    async def test_single_tag_filter(self, client):
        """?tags=red should return models with tag 'red'."""
        db_path = client._db_path
        ids = await _setup_models_with_tags_and_categories(db_path)

        resp = await client.get("/api/models?tags=red")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["models"]]
        assert "cube" in names
        assert "sphere" in names
        assert "cylinder" not in names

    async def test_multi_tag_and_filter(self, client):
        """?tags=red,blue should return models with BOTH tags (AND logic)."""
        db_path = client._db_path
        ids = await _setup_models_with_tags_and_categories(db_path)

        resp = await client.get("/api/models?tags=red,blue")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["models"]]
        # Only cube has both red AND blue
        assert names == ["cube"]

    async def test_legacy_single_tag_param(self, client):
        """?tag=blue should still work (backwards compat)."""
        db_path = client._db_path
        ids = await _setup_models_with_tags_and_categories(db_path)

        resp = await client.get("/api/models?tag=blue")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["models"]]
        assert "cube" in names
        assert "cylinder" in names
        assert "sphere" not in names


@pytest.mark.asyncio
class TestMultiCategoryFilter:
    async def test_single_category_filter(self, client):
        """?categories=Shapes should return models in Shapes category."""
        db_path = client._db_path
        ids = await _setup_models_with_tags_and_categories(db_path)

        resp = await client.get("/api/models?categories=Shapes")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["models"]]
        assert "cube" in names
        assert "sphere" in names
        assert "cylinder" not in names

    async def test_multi_category_or_filter(self, client):
        """?categories=Shapes,Objects should return models in EITHER (OR logic)."""
        db_path = client._db_path
        ids = await _setup_models_with_tags_and_categories(db_path)

        resp = await client.get("/api/models?categories=Shapes,Objects")
        assert resp.status_code == 200
        # All 3 models are in at least one category
        assert resp.json()["total"] == 3


@pytest.mark.asyncio
class TestFavoritesFilter:
    async def test_favorites_only(self, client):
        """?favorites_only=true should return only favorited models."""
        db_path = client._db_path
        ids = await _setup_models_with_tags_and_categories(db_path)

        resp = await client.get("/api/models?favorites_only=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["models"][0]["name"] == "cube"
        assert data["models"][0]["is_favorite"] is True


@pytest.mark.asyncio
class TestCollectionFilter:
    async def test_collection_filter(self, client):
        """?collection=ID should return models in that collection."""
        db_path = client._db_path
        ids = await _setup_models_with_tags_and_categories(db_path)

        # Create collection and add m2 (sphere)
        resp = await client.post(
            "/api/collections", json={"name": "FilterColl"}
        )
        cid = resp.json()["id"]
        await client.post(
            f"/api/collections/{cid}/models",
            json={"model_ids": [ids["m2"]]},
        )

        resp = await client.get(f"/api/models?collection={cid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["models"][0]["name"] == "sphere"


@pytest.mark.asyncio
class TestSorting:
    async def test_sort_by_name_asc(self, client):
        """?sort_by=name&sort_order=asc should sort alphabetically."""
        db_path = client._db_path
        await _setup_models_with_tags_and_categories(db_path)

        resp = await client.get("/api/models?sort_by=name&sort_order=asc")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["models"]]
        assert names == sorted(names)

    async def test_sort_by_name_desc(self, client):
        """?sort_by=name&sort_order=desc should sort reverse alphabetically."""
        db_path = client._db_path
        await _setup_models_with_tags_and_categories(db_path)

        resp = await client.get("/api/models?sort_by=name&sort_order=desc")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["models"]]
        assert names == sorted(names, reverse=True)

    async def test_invalid_sort_by_falls_back(self, client):
        """?sort_by=invalid should fall back to updated_at."""
        db_path = client._db_path
        await insert_test_model(db_path)

        resp = await client.get("/api/models?sort_by=invalid")
        assert resp.status_code == 200

    async def test_is_favorite_in_model_list(self, client):
        """GET /api/models should include is_favorite field."""
        db_path = client._db_path
        ids = await _setup_models_with_tags_and_categories(db_path)

        resp = await client.get("/api/models")
        assert resp.status_code == 200
        models = resp.json()["models"]
        # Find cube (favorited)
        cube = next(m for m in models if m["name"] == "cube")
        assert cube["is_favorite"] is True
        # Find sphere (not favorited)
        sphere = next(m for m in models if m["name"] == "sphere")
        assert sphere["is_favorite"] is False


@pytest.mark.asyncio
class TestCombinedFilters:
    async def test_tag_and_favorites(self, client):
        """?tags=red&favorites_only=true should combine filters."""
        db_path = client._db_path
        ids = await _setup_models_with_tags_and_categories(db_path)

        resp = await client.get("/api/models?tags=red&favorites_only=true")
        assert resp.status_code == 200
        data = resp.json()
        # cube has red tag AND is favorited; sphere has red but isn't favorited
        assert data["total"] == 1
        assert data["models"][0]["name"] == "cube"

    async def test_category_and_tag(self, client):
        """?tags=red&categories=Objects should combine tag AND category."""
        db_path = client._db_path
        ids = await _setup_models_with_tags_and_categories(db_path)

        resp = await client.get("/api/models?tags=red&categories=Objects")
        assert resp.status_code == 200
        data = resp.json()
        # sphere has red tag AND is in Objects
        assert data["total"] == 1
        assert data["models"][0]["name"] == "sphere"
