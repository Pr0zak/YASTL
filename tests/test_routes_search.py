"""Tests for app.api.routes_search API endpoints."""

import pytest
import aiosqlite

from app.api.routes_search import _sanitize_fts_query
from tests.conftest import insert_test_model


@pytest.mark.asyncio
class TestSearchModels:
    async def test_empty_query_returns_all(self, client):
        """GET /api/search with empty query should return all models."""
        db_path = client._db_path
        await insert_test_model(db_path, name="cube", file_path="/tmp/cube.stl")
        await insert_test_model(db_path, name="sphere", file_path="/tmp/sphere.stl")

        resp = await client.get("/api/search?q=")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    async def test_fts_search(self, client):
        """GET /api/search?q=dragon should find matching models."""
        db_path = client._db_path
        await insert_test_model(
            db_path, name="dragon", file_path="/tmp/dragon.stl",
            description="a fire breathing dragon"
        )
        await insert_test_model(
            db_path, name="cube", file_path="/tmp/cube.stl",
            description="simple cube"
        )

        resp = await client.get("/api/search?q=dragon")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["models"][0]["name"] == "dragon"
        assert data["query"] == "dragon"

    async def test_search_by_description(self, client):
        """FTS should match on description too."""
        db_path = client._db_path
        await insert_test_model(
            db_path, name="model1", file_path="/tmp/m1.stl",
            description="beautiful unicorn"
        )
        await insert_test_model(
            db_path, name="model2", file_path="/tmp/m2.stl",
            description="plain box"
        )

        resp = await client.get("/api/search?q=unicorn")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["models"][0]["name"] == "model1"

    async def test_search_no_results(self, client):
        """FTS search with no matches should return empty list."""
        db_path = client._db_path
        await insert_test_model(db_path, name="cube", file_path="/tmp/cube.stl")

        resp = await client.get("/api/search?q=nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["models"] == []

    async def test_search_with_format_filter(self, client):
        """Search should filter by file format."""
        db_path = client._db_path
        await insert_test_model(
            db_path, name="dragon_stl", file_path="/tmp/dragon.stl",
            file_format="stl", description="dragon model"
        )
        await insert_test_model(
            db_path, name="dragon_obj", file_path="/tmp/dragon.obj",
            file_format="obj", description="dragon model"
        )

        resp = await client.get("/api/search?q=dragon&format=stl")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["models"][0]["name"] == "dragon_stl"

    async def test_search_with_tag_filter(self, client):
        """Search should filter by tags."""
        db_path = client._db_path
        model_id = await insert_test_model(
            db_path, name="tagged_dragon", file_path="/tmp/tagged.stl",
            description="tagged dragon"
        )
        await insert_test_model(
            db_path, name="untagged_dragon", file_path="/tmp/untagged.stl",
            description="untagged dragon"
        )

        # Add tag to first model
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute("INSERT INTO tags (name) VALUES ('fantasy')")
            tag_id = cursor.lastrowid
            await conn.execute(
                "INSERT INTO model_tags (model_id, tag_id) VALUES (?, ?)",
                (model_id, tag_id),
            )
            await conn.commit()

        resp = await client.get("/api/search?q=dragon&tags=fantasy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["models"][0]["name"] == "tagged_dragon"

    async def test_search_pagination(self, client):
        """Search should respect limit and offset."""
        db_path = client._db_path
        for i in range(5):
            await insert_test_model(
                db_path, name=f"item_{i}", file_path=f"/tmp/item_{i}.stl",
                description="searchable item"
            )

        resp = await client.get("/api/search?q=item&limit=2&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["models"]) == 2

    async def test_search_enriches_tags_and_categories(self, client):
        """Search results should include tags and categories."""
        db_path = client._db_path
        model_id = await insert_test_model(
            db_path, name="enriched", file_path="/tmp/enriched.stl",
            description="enriched model"
        )

        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute("INSERT INTO tags (name) VALUES ('red')")
            tag_id = cursor.lastrowid
            await conn.execute(
                "INSERT INTO model_tags (model_id, tag_id) VALUES (?, ?)",
                (model_id, tag_id),
            )
            cursor = await conn.execute(
                "INSERT INTO categories (name) VALUES ('Toys')"
            )
            cat_id = cursor.lastrowid
            await conn.execute(
                "INSERT INTO model_categories (model_id, category_id) VALUES (?, ?)",
                (model_id, cat_id),
            )
            await conn.commit()

        resp = await client.get("/api/search?q=enriched")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["models"]) == 1
        model = data["models"][0]
        assert "red" in model["tags"]
        assert "Toys" in model["categories"]

    async def test_search_with_special_characters(self, client):
        """Search with FTS5 special chars should not raise errors."""
        db_path = client._db_path
        await insert_test_model(
            db_path, name="test model", file_path="/tmp/test.stl",
            description="a test model"
        )

        # Characters that would break raw FTS5 queries
        for query in ['"unclosed', 'a AND', 'a OR', 'test*', 'a(b)', 'x:y', 'a+b']:
            resp = await client.get(f"/api/search?q={query}")
            assert resp.status_code == 200, f"Failed for query: {query}"

    async def test_search_with_category_filter(self, client):
        """Search should filter by categories."""
        db_path = client._db_path
        model_id = await insert_test_model(
            db_path, name="categorized_dragon", file_path="/tmp/cat.stl",
            description="categorized dragon"
        )
        await insert_test_model(
            db_path, name="uncategorized_dragon", file_path="/tmp/uncat.stl",
            description="uncategorized dragon"
        )

        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "INSERT INTO categories (name) VALUES ('Fantasy')"
            )
            cat_id = cursor.lastrowid
            await conn.execute(
                "INSERT INTO model_categories (model_id, category_id) VALUES (?, ?)",
                (model_id, cat_id),
            )
            await conn.commit()

        resp = await client.get("/api/search?q=dragon&categories=Fantasy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["models"][0]["name"] == "categorized_dragon"

    async def test_search_only_special_characters(self, client):
        """Query with only special characters should return all models."""
        db_path = client._db_path
        await insert_test_model(
            db_path, name="cube", file_path="/tmp/cube.stl"
        )

        resp = await client.get('/api/search?q="*()+-')
        assert resp.status_code == 200
        data = resp.json()
        # All special chars stripped → treated as empty query → returns all
        assert data["total"] == 1


class TestSanitizeFtsQuery:
    """Unit tests for the _sanitize_fts_query helper."""

    def test_plain_text(self):
        assert _sanitize_fts_query("dragon") == '"dragon"*'

    def test_multiple_tokens(self):
        assert _sanitize_fts_query("fire dragon") == '"fire"* "dragon"*'

    def test_strips_quotes(self):
        result = _sanitize_fts_query('"hello world"')
        # Quotes from user input are stripped; tokens are re-quoted with prefix *
        assert "hello" in result
        assert "world" in result

    def test_strips_special_chars(self):
        result = _sanitize_fts_query("a*b(c)d:e")
        # Should produce quoted tokens without special chars (except trailing * for prefix matching)
        assert "(" not in result
        assert ":" not in result
        # Each token gets a trailing * for prefix matching
        assert '"a"*' in result

    def test_empty_after_stripping(self):
        assert _sanitize_fts_query("***") == ""

    def test_boolean_keywords_quoted(self):
        result = _sanitize_fts_query("cat AND dog")
        # AND should be inside quotes, not treated as operator; each token gets prefix *
        assert result == '"cat"* "AND"* "dog"*'
