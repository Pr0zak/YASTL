"""Tests for AI Phase 1: embeddings store, RRF, backfill, semantic/hybrid search.

Uses a deterministic keyword->vector fake embedder so ranking is testable
without a live API key.
"""

import numpy as np
import pytest

from app.services import ai_client, embeddings
from tests.conftest import insert_test_model

VOCAB = ["dragon", "gear", "vase", "cat", "articulated"]


async def fake_embed(texts):
    """Deterministic: one dimension per vocab word, present -> ~1.1 else 0.1."""
    return [[0.1 + (1.0 if w in t.lower() else 0.0) for w in VOCAB] for t in texts]


@pytest.mark.asyncio
class TestEmbeddingsUnit:
    async def test_compose_text_includes_fields(self):
        text = embeddings.compose_text(
            {"name": "Dragon", "file_path": "/lib/Minis/dragon.stl",
             "description": "A mini."},
            tags=["fantasy", "articulated"],
        )
        assert "Dragon" in text
        assert "Minis" in text          # folder segment
        assert "fantasy" in text        # tags
        assert "A mini." in text

    async def test_source_hash_changes(self):
        a = embeddings.source_hash("hello", "m1")
        assert a == embeddings.source_hash("hello", "m1")
        assert a != embeddings.source_hash("hello", "m2")   # model switch
        assert a != embeddings.source_hash("world", "m1")   # text change

    async def test_pack_unpack_roundtrip(self):
        blob = embeddings.pack_vec([1.0, 2.5, -3.0])
        vec = embeddings.unpack_vec(blob, 3)
        assert list(np.round(vec, 3)) == [1.0, 2.5, -3.0]

    async def test_rrf_fuse(self):
        # id 2 appears high in both lists -> should win.
        fused = embeddings.rrf_fuse([1, 2, 3], [2, 4, 1])
        assert fused[0] == 2

    async def test_search_nearest(self):
        embeddings.clear()
        mat = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32)
        embeddings.set_store([10, 20, 30], embeddings._normalize(mat), 3)
        assert embeddings.search([0.9, 0.1, 0.0], 1) == [10]
        assert embeddings.search([0.0, 0.0, 1.0], 1) == [30]

    async def test_search_empty_store(self):
        embeddings.clear()
        assert embeddings.search([1, 2, 3], 5) == []


@pytest.mark.asyncio
class TestBackfillAndSearch:
    async def _setup(self, client, monkeypatch):
        embeddings.clear()
        await client.put("/api/settings", json={
            "ai_enabled": "true", "ai_provider": "openai", "ai_api_key": "k",
            "ai_embed_provider": "openai",
        })
        monkeypatch.setattr(ai_client, "embed_texts", fake_embed)

    async def test_backfill_then_semantic_ranks_by_meaning(self, client, monkeypatch):
        await self._setup(client, monkeypatch)
        await insert_test_model(client._db_path, name="Articulated Dragon", file_path="/m/dragon_v2_final.stl")
        await insert_test_model(client._db_path, name="Spur Gear", file_path="/m/gear.stl")
        await insert_test_model(client._db_path, name="Spiral Vase", file_path="/m/vase.stl")

        from app.api.routes_settings import _embed_backfill
        await _embed_backfill()
        assert embeddings.count() == 3

        r = await client.get("/api/search", params={"q": "dragon", "mode": "semantic"})
        data = r.json()
        assert data["mode"] == "semantic"
        assert data["models"], "expected semantic results"
        assert data["models"][0]["name"] == "Articulated Dragon"

    async def test_hybrid_returns_results(self, client, monkeypatch):
        await self._setup(client, monkeypatch)
        await insert_test_model(client._db_path, name="Gear Box", file_path="/m/gear.stl")
        await insert_test_model(client._db_path, name="Vase", file_path="/m/vase.stl")
        from app.api.routes_settings import _embed_backfill
        await _embed_backfill()

        r = await client.get("/api/search", params={"q": "gear", "mode": "hybrid"})
        data = r.json()
        assert data["mode"] == "hybrid"
        assert data["models"][0]["name"] == "Gear Box"

    async def test_semantic_respects_filters(self, client, monkeypatch):
        await self._setup(client, monkeypatch)
        await insert_test_model(client._db_path, name="Dragon STL", file_path="/m/d.stl", file_format="STL")
        await insert_test_model(client._db_path, name="Dragon OBJ", file_path="/m/d.obj", file_format="OBJ")
        from app.api.routes_settings import _embed_backfill
        await _embed_backfill()

        r = await client.get("/api/search", params={"q": "dragon", "mode": "semantic", "format": "obj"})
        names = [m["name"] for m in r.json()["models"]]
        assert names == ["Dragon OBJ"]  # STL filtered out despite matching semantically

    async def test_backfill_reembeds_only_stale(self, client, monkeypatch):
        await self._setup(client, monkeypatch)
        await insert_test_model(client._db_path, name="Dragon", file_path="/m/d.stl")
        from app.api.routes_settings import _embed_backfill, _embed_progress
        await _embed_backfill()
        assert _embed_progress["embedded"] == 1
        # Second run: nothing stale -> embeds 0
        await _embed_backfill()
        assert _embed_progress["total"] == 0


@pytest.mark.asyncio
class TestSemanticFallback:
    async def test_semantic_falls_back_without_embeddings(self, client):
        embeddings.clear()
        await insert_test_model(client._db_path, name="dragon", file_path="/m/d.stl")
        # No matrix + AI disabled -> semantic path not taken (graceful keyword).
        r = await client.get("/api/search", params={"q": "dragon", "mode": "semantic"})
        assert r.status_code == 200
        assert "mode" not in r.json()  # fell back to keyword path

    async def test_embed_backfill_requires_config(self, client):
        r = await client.post("/api/settings/ai/embed-backfill")
        assert r.status_code == 400
