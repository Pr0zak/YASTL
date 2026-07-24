"""Tests for the print queue: /api/queue."""

import pytest

from tests.conftest import insert_test_model


@pytest.mark.asyncio
class TestPrintQueue:
    async def test_add_and_list(self, client):
        mid = await insert_test_model(client._db_path, name="q1", file_path="/m/q1.stl")
        r = await client.post("/api/queue", json={"model_id": mid})
        assert r.status_code == 201
        assert r.json()["status"] == "queued"

        listing = (await client.get("/api/queue")).json()["queue"]
        assert len(listing) == 1
        assert listing[0]["model_name"] == "q1"
        assert listing[0]["model_id"] == mid

    async def test_add_missing_model(self, client):
        r = await client.post("/api/queue", json={"model_id": 9999})
        assert r.status_code == 404

    async def test_add_requires_model_id(self, client):
        r = await client.post("/api/queue", json={})
        assert r.status_code == 400

    async def test_status_printing_sets_started(self, client):
        mid = await insert_test_model(client._db_path, name="q2", file_path="/m/q2.stl")
        qid = (await client.post("/api/queue", json={"model_id": mid})).json()["id"]
        r = await client.put(f"/api/queue/{qid}", json={"status": "printing"})
        assert r.status_code == 200
        assert r.json()["status"] == "printing"
        assert r.json()["started_at"] is not None

    async def test_done_logs_print_and_bumps_count(self, client):
        mid = await insert_test_model(client._db_path, name="q3", file_path="/m/q3.stl")
        qid = (await client.post("/api/queue", json={"model_id": mid})).json()["id"]
        r = await client.put(f"/api/queue/{qid}", json={"status": "done"})
        assert r.status_code == 200
        assert r.json()["finished_at"] is not None
        # a print_log row was created + model print_count bumped
        prints = (await client.get(f"/api/prints?model_id={mid}")).json()["prints"]
        assert len(prints) == 1
        model = (await client.get(f"/api/models/{mid}")).json()
        assert model["print_count"] == 1

    async def test_invalid_status(self, client):
        mid = await insert_test_model(client._db_path, name="q4", file_path="/m/q4.stl")
        qid = (await client.post("/api/queue", json={"model_id": mid})).json()["id"]
        r = await client.put(f"/api/queue/{qid}", json={"status": "bogus"})
        assert r.status_code == 400

    async def test_update_printer_notes(self, client):
        mid = await insert_test_model(client._db_path, name="q5", file_path="/m/q5.stl")
        qid = (await client.post("/api/queue", json={"model_id": mid})).json()["id"]
        r = await client.put(f"/api/queue/{qid}", json={"printer": "P1S", "notes": "PLA"})
        assert r.json()["printer"] == "P1S"
        assert r.json()["notes"] == "PLA"

    async def test_reorder(self, client):
        ids = []
        for i in range(3):
            mid = await insert_test_model(client._db_path, name=f"r{i}", file_path=f"/m/r{i}.stl")
            ids.append((await client.post("/api/queue", json={"model_id": mid})).json()["id"])
        # reverse order
        await client.put("/api/queue/reorder", json={"ids": list(reversed(ids))})
        listing = (await client.get("/api/queue")).json()["queue"]
        assert [it["id"] for it in listing] == list(reversed(ids))

    async def test_delete(self, client):
        mid = await insert_test_model(client._db_path, name="q6", file_path="/m/q6.stl")
        qid = (await client.post("/api/queue", json={"model_id": mid})).json()["id"]
        r = await client.delete(f"/api/queue/{qid}")
        assert r.status_code == 200
        assert (await client.get("/api/queue")).json()["queue"] == []

    async def test_delete_not_found(self, client):
        r = await client.delete("/api/queue/9999")
        assert r.status_code == 404
