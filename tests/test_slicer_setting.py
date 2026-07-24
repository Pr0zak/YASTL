"""Tests for the extended preferred_slicer setting (slicer handoff)."""

import pytest


@pytest.mark.asyncio
class TestPreferredSlicer:
    @pytest.mark.parametrize("slicer", [
        "none", "orcaslicer", "cura", "bambustudio", "prusaslicer", "superslicer",
    ])
    async def test_accepts_supported_slicers(self, client, slicer):
        r = await client.put("/api/settings", json={"preferred_slicer": slicer})
        assert r.status_code == 200
        assert r.json()["preferred_slicer"] == slicer

    async def test_rejects_unknown_slicer(self, client):
        r = await client.put("/api/settings", json={"preferred_slicer": "kisslicer"})
        assert r.status_code == 400
