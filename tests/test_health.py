"""Tests for health check and root endpoints."""

import pytest


@pytest.mark.asyncio
class TestHealthCheck:
    async def test_health_endpoint(self, client):
        """GET /health should return status ok."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["app"] == "yastl"
        assert "version" in data
