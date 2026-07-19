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


@pytest.mark.asyncio
class TestTagMergeCleanup:
    async def _mk_tag(self, client, name):
        r = await client.post("/api/tags", json={"name": name})
        return r.json()["id"]

    async def test_merge_retargets_and_deletes_sources(self, client):
        db_path = client._db_path
        m1 = await insert_test_model(db_path, name="a", file_path="/tmp/a.stl")
        m2 = await insert_test_model(db_path, name="b", file_path="/tmp/b.stl")

        await client.post(f"/api/models/{m1}/tags", json={"tags": ["dragon"]})
        await client.post(f"/api/models/{m2}/tags", json={"tags": ["dragons"]})

        tags = {t["name"]: t["id"] for t in (await client.get("/api/tags")).json()["tags"]}
        resp = await client.post(
            "/api/tags/merge",
            json={"source_ids": [tags["dragons"]], "target_id": tags["dragon"]},
        )
        assert resp.status_code == 200
        assert resp.json()["models_updated"] == 1

        names = {t["name"] for t in (await client.get("/api/tags")).json()["tags"]}
        assert "dragons" not in names and "dragon" in names
        # m2 now searchable under the merged tag name
        data = (await client.get("/api/search?q=dragon")).json()
        assert {mdl["id"] for mdl in data["models"]} == {m1, m2}

    async def test_cleanup_removes_unused(self, client):
        await self._mk_tag(client, "orphan")
        m1 = await insert_test_model(db_path=client._db_path, name="x", file_path="/tmp/x.stl")
        await client.post(f"/api/models/{m1}/tags", json={"tags": ["used"]})

        resp = await client.post("/api/tags/cleanup")
        assert resp.status_code == 200
        assert resp.json()["removed"] == 1
        names = {t["name"] for t in (await client.get("/api/tags")).json()["tags"]}
        assert "orphan" not in names and "used" in names


@pytest.mark.asyncio
class TestRelatedTags:
    async def test_co_occurrence(self, client):
        db_path = client._db_path
        m1 = await insert_test_model(db_path, name="a", file_path="/a.stl")
        m2 = await insert_test_model(db_path, name="b", file_path="/b.stl")
        target = await insert_test_model(db_path, name="t", file_path="/t.stl")

        # m1: dragon+scaly ; m2: dragon+scaly+mini ; target: dragon
        await client.post(f"/api/models/{m1}/tags", json={"tags": ["dragon", "scaly"]})
        await client.post(f"/api/models/{m2}/tags", json={"tags": ["dragon", "scaly", "mini"]})
        await client.post(f"/api/models/{target}/tags", json={"tags": ["dragon"]})

        resp = await client.get(f"/api/models/{target}/related-tags")
        assert resp.status_code == 200
        sugg = resp.json()["suggestions"]
        # scaly co-occurs with dragon twice, mini once; dragon excluded (own)
        assert sugg[0] == "scaly"
        assert "mini" in sugg
        assert "dragon" not in sugg

    async def test_no_own_tags(self, client):
        db_path = client._db_path
        mid = await insert_test_model(db_path, name="untagged", file_path="/u.stl")
        resp = await client.get(f"/api/models/{mid}/related-tags")
        assert resp.json()["suggestions"] == []


@pytest.mark.asyncio
class TestTagProvenance:
    async def test_manual_tag_is_manual(self, client):
        db_path = client._db_path
        mid = await insert_test_model(db_path, name="m", file_path="/m.stl")
        await client.post(f"/api/models/{mid}/tags", json={"tags": ["hand"]})
        model = (await client.get(f"/api/models/{mid}")).json()
        assert model["tag_sources"]["hand"] == "manual"

    async def test_clear_auto_keeps_manual(self, client):
        import aiosqlite
        db_path = client._db_path
        mid = await insert_test_model(db_path, name="m", file_path="/m.stl")
        # manual tag via API
        await client.post(f"/api/models/{mid}/tags", json={"tags": ["keep"]})
        # inject an auto tag directly
        async with aiosqlite.connect(db_path) as conn:
            cur = await conn.execute("INSERT INTO tags (name) VALUES ('auto1')")
            tid = cur.lastrowid
            await conn.execute(
                "INSERT INTO model_tags (model_id, tag_id, source) VALUES (?, ?, 'auto')",
                (mid, tid),
            )
            await conn.commit()

        resp = await client.delete(f"/api/models/{mid}/tags/auto")
        assert resp.status_code == 200
        assert resp.json()["removed"] == 1
        tags = resp.json()["model"]["tags"]
        assert "keep" in tags and "auto1" not in tags
