"""Tests for app.api.routes_filament API endpoints."""

import pytest


@pytest.mark.asyncio
class TestFilaments:
    async def test_list_empty(self, client):
        resp = await client.get("/api/filaments")
        assert resp.status_code == 200
        assert resp.json() == {"filaments": []}

    async def test_create_with_fields(self, client):
        resp = await client.post("/api/filaments", json={
            "brand": "Polymaker", "material": "PLA", "color_name": "Teal",
            "color_hex": "#1a9e8f", "spool_weight_g": 1000, "remaining_g": 820,
            "cost": 22.99, "vendor": "Amazon",
        })
        assert resp.status_code == 201
        row = resp.json()
        assert row["id"] > 0
        assert row["brand"] == "Polymaker"
        assert row["material"] == "PLA"
        assert row["color_hex"] == "#1a9e8f"
        assert row["remaining_g"] == 820
        assert row["diameter"] == 1.75  # default
        assert row["status"] == "active"  # default

    async def test_create_defaults_only(self, client):
        resp = await client.post("/api/filaments", json={})
        assert resp.status_code == 201
        row = resp.json()
        assert row["status"] == "active"
        assert row["diameter"] == 1.75

    async def test_create_invalid_status(self, client):
        resp = await client.post("/api/filaments", json={"status": "bogus"})
        assert resp.status_code == 400

    async def test_update_partial(self, client):
        fid = (await client.post("/api/filaments", json={
            "brand": "eSun", "remaining_g": 500,
        })).json()["id"]
        resp = await client.put(f"/api/filaments/{fid}", json={
            "remaining_g": 300, "status": "active",
        })
        assert resp.status_code == 200
        row = resp.json()
        assert row["remaining_g"] == 300
        assert row["brand"] == "eSun"  # unchanged

    async def test_update_empty_body(self, client):
        fid = (await client.post("/api/filaments", json={"brand": "x"})).json()["id"]
        resp = await client.put(f"/api/filaments/{fid}", json={})
        assert resp.status_code == 400

    async def test_update_invalid_status(self, client):
        fid = (await client.post("/api/filaments", json={"brand": "x"})).json()["id"]
        resp = await client.put(f"/api/filaments/{fid}", json={"status": "melted"})
        assert resp.status_code == 400

    async def test_update_not_found(self, client):
        resp = await client.put("/api/filaments/9999", json={"brand": "x"})
        assert resp.status_code == 404

    async def test_delete(self, client):
        fid = (await client.post("/api/filaments", json={"brand": "gone"})).json()["id"]
        resp = await client.delete(f"/api/filaments/{fid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == fid
        # gone from list
        listing = (await client.get("/api/filaments")).json()["filaments"]
        assert all(f["id"] != fid for f in listing)

    async def test_delete_not_found(self, client):
        resp = await client.delete("/api/filaments/9999")
        assert resp.status_code == 404

    async def test_list_orders_active_first(self, client):
        await client.post("/api/filaments", json={"brand": "ZArchived", "status": "archived"})
        await client.post("/api/filaments", json={"brand": "AActive", "status": "active"})
        listing = (await client.get("/api/filaments")).json()["filaments"]
        assert listing[0]["status"] == "active"
        assert listing[0]["brand"] == "AActive"
