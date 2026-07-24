"""Tests for AI Phase 2: vision auto-tagging (per-model + bulk)."""

from pathlib import Path

import aiosqlite
import pytest

from app.services import ai_client
from tests.conftest import insert_test_model


def _dummy_png(path):
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


async def _model_with_thumb(client, name, thumb_name, desc=""):
    mid = await insert_test_model(
        client._db_path, name=name, file_path=f"/m/{name}.stl", description=desc
    )
    thumb = Path(client._thumb_dir) / thumb_name
    _dummy_png(thumb)
    async with aiosqlite.connect(client._db_path) as conn:
        await conn.execute(
            "UPDATE models SET thumbnail_path = ? WHERE id = ?", (str(thumb), mid)
        )
        await conn.commit()
    return mid


async def fake_vision(image_bytes, filename, vocab):
    return {"tags": ["Dragon", "articulated", "unknownword"],
            "description": "A dragon mini."}


@pytest.mark.asyncio
class TestVisionTagging:
    async def _enable(self, client, vocab_mode="controlled"):
        await client.put("/api/settings", json={
            "ai_enabled": "true", "ai_provider": "openai", "ai_api_key": "k",
            "ai_autotag_vocab_mode": vocab_mode,
        })

    async def test_controlled_adds_only_vocab_tags_as_ai(self, client, monkeypatch):
        await self._enable(client, "controlled")
        # seed vocabulary on a different model
        other = await insert_test_model(client._db_path, name="other", file_path="/m/o.stl")
        await client.post(f"/api/models/{other}/tags", json={"tags": ["dragon", "articulated"]})
        mid = await _model_with_thumb(client, "target", "t.png")
        monkeypatch.setattr(ai_client, "vision_tags", fake_vision)

        r = await client.post(f"/api/models/{mid}/ai-tag")
        assert r.status_code == 200
        model = r.json()["model"]
        assert set(model["tags"]) >= {"dragon", "articulated"}
        assert "unknownword" not in model["tags"]          # dropped in controlled mode
        assert model["tag_sources"]["dragon"] == "ai"

    async def test_open_adds_up_to_two_new_tags(self, client, monkeypatch):
        await self._enable(client, "open")
        mid = await _model_with_thumb(client, "t2", "t2.png")
        monkeypatch.setattr(ai_client, "vision_tags", fake_vision)

        r = await client.post(f"/api/models/{mid}/ai-tag")
        model = r.json()["model"]
        # open allows up to 2 new tags -> dragon, articulated (3rd dropped)
        assert set(model["tags"]) == {"dragon", "articulated"}

    async def test_fills_empty_description(self, client, monkeypatch):
        await self._enable(client)
        mid = await _model_with_thumb(client, "t3", "t3.png", desc="")
        monkeypatch.setattr(ai_client, "vision_tags", fake_vision)
        await client.post(f"/api/models/{mid}/ai-tag")
        m = (await client.get(f"/api/models/{mid}")).json()
        assert m["description"] == "A dragon mini."

    async def test_keeps_existing_description(self, client, monkeypatch):
        await self._enable(client)
        mid = await _model_with_thumb(client, "t4", "t4.png", desc="Original text.")
        monkeypatch.setattr(ai_client, "vision_tags", fake_vision)
        await client.post(f"/api/models/{mid}/ai-tag")
        m = (await client.get(f"/api/models/{mid}")).json()
        assert m["description"] == "Original text."

    async def test_does_not_downgrade_manual_tag(self, client, monkeypatch):
        await self._enable(client, "controlled")
        mid = await _model_with_thumb(client, "t6", "t6.png")
        await client.post(f"/api/models/{mid}/tags", json={"tags": ["dragon"]})  # manual
        monkeypatch.setattr(ai_client, "vision_tags", fake_vision)
        await client.post(f"/api/models/{mid}/ai-tag")
        m = (await client.get(f"/api/models/{mid}")).json()
        assert m["tag_sources"]["dragon"] == "manual"  # stays manual

    async def test_no_thumbnail_400(self, client, monkeypatch):
        await self._enable(client)
        mid = await insert_test_model(client._db_path, name="nothumb", file_path="/m/n.stl")
        monkeypatch.setattr(ai_client, "vision_tags", fake_vision)
        r = await client.post(f"/api/models/{mid}/ai-tag")
        assert r.status_code == 400

    async def test_not_configured_400(self, client):
        mid = await insert_test_model(client._db_path, name="x", file_path="/m/x.stl")
        r = await client.post(f"/api/models/{mid}/ai-tag")
        assert r.status_code == 400

    async def test_clear_auto_removes_ai_tags(self, client, monkeypatch):
        await self._enable(client, "open")
        mid = await _model_with_thumb(client, "t5", "t5.png")
        monkeypatch.setattr(ai_client, "vision_tags", fake_vision)
        await client.post(f"/api/models/{mid}/ai-tag")
        assert (await client.get(f"/api/models/{mid}")).json()["tags"]  # has ai tags
        r = await client.delete(f"/api/models/{mid}/tags/auto")
        assert r.status_code == 200
        assert r.json()["model"]["tags"] == []  # ai tags cleared too

    async def test_bulk_auto_tag(self, client, monkeypatch):
        await self._enable(client, "open")
        await _model_with_thumb(client, "b1", "b1.png")
        await _model_with_thumb(client, "b2", "b2.png")
        monkeypatch.setattr(ai_client, "vision_tags", fake_vision)
        from app.api.routes_settings import _ai_auto_tag_all, _ai_tag_progress
        await _ai_auto_tag_all()
        assert _ai_tag_progress["completed"] == 2
        assert _ai_tag_progress["tags_added"] >= 2

    async def test_bulk_requires_config(self, client):
        r = await client.post("/api/settings/ai/auto-tag-all")
        assert r.status_code == 400
