"""Tests for AI Phase 0: settings/masking + ai_client config & provider calls."""

import pytest

from app.services import ai_client


@pytest.mark.asyncio
class TestAiSettings:
    async def test_defaults(self, client):
        s = (await client.get("/api/settings")).json()
        assert s["ai_enabled"] == "false"
        assert s["ai_provider"] == "openrouter"
        assert s["ai_embed_provider"] == "openrouter"
        assert s["ai_api_key"] == ""

    async def test_key_masked_on_read(self, client):
        await client.put("/api/settings", json={"ai_api_key": "sk-secret-1234abcd"})
        masked = (await client.get("/api/settings")).json()["ai_api_key"]
        assert "secret" not in masked
        assert masked.endswith("abcd")
        assert masked != "sk-secret-1234abcd"

    async def test_mask_not_overwritten(self, client):
        await client.put("/api/settings", json={
            "ai_enabled": "true", "ai_provider": "openai",
            "ai_api_key": "sk-real-key-9999",
        })
        masked = (await client.get("/api/settings")).json()["ai_api_key"]
        # Re-submitting the masked display value must NOT wipe the real key.
        await client.put("/api/settings", json={"ai_api_key": masked})
        cfg = await ai_client.get_ai_config()
        assert cfg["api_key"] == "sk-real-key-9999"

    async def test_provider_validated(self, client):
        r = await client.put("/api/settings", json={"ai_provider": "bogus"})
        assert r.status_code == 400

    async def test_real_key_updates(self, client):
        await client.put("/api/settings", json={"ai_api_key": "sk-one"})
        await client.put("/api/settings", json={"ai_api_key": "sk-two-final"})
        cfg = await ai_client.get_ai_config()
        assert cfg["api_key"] == "sk-two-final"


@pytest.mark.asyncio
class TestAiConfig:
    async def test_disabled_blocks_calls(self, client):
        cfg = await ai_client.get_ai_config()
        assert cfg["enabled"] is False
        with pytest.raises(ai_client.AINotConfigured):
            await ai_client.embed_texts(["hi"])
        with pytest.raises(ai_client.AINotConfigured):
            await ai_client.vision_tags(b"x", "a.stl", [])

    async def test_default_models_by_provider(self, client):
        await client.put("/api/settings", json={
            "ai_enabled": "true", "ai_provider": "anthropic", "ai_api_key": "k",
        })
        cfg = await ai_client.get_ai_config()
        assert cfg["vision_model"] == "claude-haiku-4-5"

    async def test_embed_key_reuses_chat_key_openai(self, client):
        await client.put("/api/settings", json={
            "ai_enabled": "true", "ai_provider": "openai", "ai_api_key": "sk-abc",
            "ai_embed_provider": "openai",
        })
        cfg = await ai_client.get_ai_config()
        assert cfg["embed_key"] == "sk-abc"
        assert cfg["embed_model"] == "text-embedding-3-small"

    async def test_voyage_needs_own_key(self, client):
        await client.put("/api/settings", json={
            "ai_enabled": "true", "ai_provider": "anthropic", "ai_api_key": "sk-ant",
            "ai_embed_provider": "voyage",
        })
        cfg = await ai_client.get_ai_config()
        assert cfg["embed_key"] == ""  # Anthropic key can't be reused for Voyage


@pytest.mark.asyncio
class TestAiCalls:
    async def _enable(self, client, provider="openai"):
        await client.put("/api/settings", json={
            "ai_enabled": "true", "ai_provider": provider, "ai_api_key": "k",
            "ai_embed_provider": "openai",
        })

    async def test_embed_texts_orders_by_index(self, client, monkeypatch):
        await self._enable(client)

        async def fake_post(url, headers, payload):
            assert url.endswith("/embeddings")
            assert payload["input"] == ["a", "b"]
            return {"data": [{"index": 1, "embedding": [0.1, 0.2]},
                             {"index": 0, "embedding": [0.3, 0.4]}]}
        monkeypatch.setattr(ai_client, "_post_json", fake_post)
        vecs = await ai_client.embed_texts(["a", "b"])
        assert vecs == [[0.3, 0.4], [0.1, 0.2]]

    async def test_embed_empty_returns_empty(self, client):
        assert await ai_client.embed_texts([]) == []

    async def test_vision_openai_parses_and_lowercases(self, client, monkeypatch):
        await self._enable(client)

        async def fake_post(url, headers, payload):
            assert url.endswith("/chat/completions")
            return {"choices": [{"message": {"content":
                '{"tags": ["Dragon", "Articulated"], "description": "A dragon."}'}}]}
        monkeypatch.setattr(ai_client, "_post_json", fake_post)
        res = await ai_client.vision_tags(b"PNG", "dragon_v2.stl", ["dragon"])
        assert res["tags"] == ["dragon", "articulated"]
        assert res["description"] == "A dragon."

    async def test_vision_anthropic_shape(self, client, monkeypatch):
        await self._enable(client, provider="anthropic")

        async def fake_post(url, headers, payload):
            assert url.endswith("/messages")
            assert headers.get("x-api-key") == "k"
            return {"content": [{"type": "text",
                                 "text": '{"tags": ["gear"], "description": "A gear."}'}]}
        monkeypatch.setattr(ai_client, "_post_json", fake_post)
        res = await ai_client.vision_tags(b"PNG", "gear.stl", [])
        assert res["tags"] == ["gear"]

    async def test_vision_json_embedded_in_prose(self, client, monkeypatch):
        await self._enable(client)

        async def fake_post(url, headers, payload):
            return {"choices": [{"message": {"content":
                'Here you go:\n{"tags": ["vase"], "description": "A vase."}\nThanks!'}}]}
        monkeypatch.setattr(ai_client, "_post_json", fake_post)
        res = await ai_client.vision_tags(b"PNG", "vase.stl", [])
        assert res["tags"] == ["vase"]


@pytest.mark.asyncio
class TestAiTestEndpoint:
    async def test_no_key(self, client):
        r = await client.post("/api/settings/ai/test")
        assert r.status_code == 200
        assert r.json()["ok"] is False

    async def test_success(self, client, monkeypatch):
        await client.put("/api/settings", json={
            "ai_enabled": "true", "ai_provider": "openai", "ai_api_key": "k",
        })

        async def fake_post(url, headers, payload):
            return {"choices": [{"message": {"content": "ok"}}]}
        monkeypatch.setattr(ai_client, "_post_json", fake_post)
        r = await client.post("/api/settings/ai/test")
        assert r.json()["ok"] is True

    async def test_failure_reported(self, client, monkeypatch):
        await client.put("/api/settings", json={
            "ai_enabled": "true", "ai_provider": "openai", "ai_api_key": "bad",
        })

        async def fake_post(url, headers, payload):
            raise ai_client.AIError("HTTP 401: invalid key")
        monkeypatch.setattr(ai_client, "_post_json", fake_post)
        r = await client.post("/api/settings/ai/test")
        body = r.json()
        assert body["ok"] is False
        assert "401" in body["detail"]
