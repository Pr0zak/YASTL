"""Tests for the finished-prints log: /api/models/{id}/print + /api/prints."""

import aiosqlite
import pytest

from tests.conftest import insert_test_model


async def _filament(client, **kw):
    resp = await client.post("/api/filaments", json=kw)
    return resp.json()["id"]


@pytest.mark.asyncio
class TestPrintLog:
    async def test_log_print_no_body(self, client):
        mid = await insert_test_model(client._db_path, name="m1", file_path="/tmp/m1.stl")
        resp = await client.post(f"/api/models/{mid}/print")
        assert resp.status_code == 200
        assert resp.json()["print_count"] == 1
        # one log row exists
        prints = (await client.get(f"/api/prints?model_id={mid}")).json()["prints"]
        assert len(prints) == 1
        assert prints[0]["quantity"] == 1

    async def test_log_print_with_details_and_filament(self, client):
        mid = await insert_test_model(client._db_path, name="m2", file_path="/tmp/m2.stl")
        fid = await _filament(client, brand="Poly", material="PLA", spool_weight_g=1000, remaining_g=1000)
        resp = await client.post(f"/api/models/{mid}/print", json={
            "quantity": 2, "filament_id": fid, "grams_used": 50,
            "location": "Bin A3", "status": "kept", "notes": "gift",
        })
        assert resp.status_code == 200
        assert resp.json()["print_count"] == 2  # bumped by quantity

        prints = (await client.get(f"/api/prints?model_id={mid}")).json()["prints"]
        assert prints[0]["location"] == "Bin A3"
        assert prints[0]["filament_id"] == fid
        assert prints[0]["filament_brand"] == "Poly"  # joined

        # filament decremented by grams_used
        fils = (await client.get("/api/filaments")).json()["filaments"]
        assert next(f for f in fils if f["id"] == fid)["remaining_g"] == 950

    async def test_undo_deletes_latest_and_recredits(self, client):
        mid = await insert_test_model(client._db_path, name="m3", file_path="/tmp/m3.stl")
        fid = await _filament(client, remaining_g=500)
        await client.post(f"/api/models/{mid}/print", json={"filament_id": fid, "grams_used": 30})
        # remaining now 470
        resp = await client.delete(f"/api/models/{mid}/print")
        assert resp.status_code == 200
        assert resp.json()["print_count"] == 0
        assert resp.json()["last_printed_at"] is None
        # log row gone
        assert (await client.get(f"/api/prints?model_id={mid}")).json()["prints"] == []
        # filament re-credited
        fils = (await client.get("/api/filaments")).json()["filaments"]
        assert next(f for f in fils if f["id"] == fid)["remaining_g"] == 500

    async def test_undo_legacy_counter_fallback(self, client):
        """Models with a print_count but no log rows still decrement."""
        mid = await insert_test_model(client._db_path, name="m4", file_path="/tmp/m4.stl")
        async with aiosqlite.connect(client._db_path) as conn:
            await conn.execute(
                "UPDATE models SET print_count = 3 WHERE id = ?", (mid,)
            )
            await conn.commit()
        resp = await client.delete(f"/api/models/{mid}/print")
        assert resp.status_code == 200
        assert resp.json()["print_count"] == 2

    async def test_log_print_model_not_found(self, client):
        resp = await client.post("/api/models/9999/print")
        assert resp.status_code == 404

    async def test_inventory_grouped_by_location(self, client):
        m1 = await insert_test_model(client._db_path, name="a", file_path="/tmp/a.stl")
        m2 = await insert_test_model(client._db_path, name="b", file_path="/tmp/b.stl")
        await client.post(f"/api/models/{m1}/print", json={"location": "Shelf 1", "quantity": 2})
        await client.post(f"/api/models/{m2}/print", json={"location": "Shelf 1"})
        await client.post(f"/api/models/{m2}/print", json={})  # unspecified location

        inv = (await client.get("/api/prints/inventory")).json()["locations"]
        by_loc = {row["location"]: row for row in inv}
        assert by_loc["Shelf 1"]["total_quantity"] == 3
        assert by_loc["Shelf 1"]["distinct_models"] == 2
        assert "(unspecified)" in by_loc

    async def test_delete_specific_print_adjusts_summary(self, client):
        mid = await insert_test_model(client._db_path, name="c", file_path="/tmp/c.stl")
        fid = await _filament(client, remaining_g=200)
        await client.post(f"/api/models/{mid}/print", json={"quantity": 3, "filament_id": fid, "grams_used": 40})
        pid = (await client.get(f"/api/prints?model_id={mid}")).json()["prints"][0]["id"]

        resp = await client.delete(f"/api/prints/{pid}")
        assert resp.status_code == 200
        # model still exists but count back to 0, filament re-credited
        fils = (await client.get("/api/filaments")).json()["filaments"]
        assert next(f for f in fils if f["id"] == fid)["remaining_g"] == 200

    async def test_delete_print_not_found(self, client):
        resp = await client.delete("/api/prints/9999")
        assert resp.status_code == 404
