"""Tests for automation settings (webhook_url, scan_interval_minutes)."""

import pytest


@pytest.mark.asyncio
class TestAutomationSettings:
    async def test_webhook_url_persists(self, client):
        resp = await client.put(
            "/api/settings", json={"webhook_url": "http://ha.local/hook"}
        )
        assert resp.status_code == 200
        assert resp.json()["webhook_url"] == "http://ha.local/hook"

        resp = await client.get("/api/settings")
        assert resp.json()["webhook_url"] == "http://ha.local/hook"

    async def test_webhook_url_length_capped(self, client):
        resp = await client.put(
            "/api/settings", json={"webhook_url": "x" * 600}
        )
        assert resp.status_code == 400

    async def test_scan_interval_validates(self, client):
        resp = await client.put(
            "/api/settings", json={"scan_interval_minutes": "60"}
        )
        assert resp.status_code == 200
        assert resp.json()["scan_interval_minutes"] == "60"

        resp = await client.put(
            "/api/settings", json={"scan_interval_minutes": "999999"}
        )
        assert resp.status_code == 400

    async def test_webhook_test_without_url(self, client):
        # No webhook configured -> test returns 400
        await client.put("/api/settings", json={"webhook_url": ""})
        resp = await client.post("/api/settings/webhook/test")
        assert resp.status_code == 400
