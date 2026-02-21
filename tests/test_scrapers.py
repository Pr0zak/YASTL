"""Tests for app.services.scrapers — site detection and metadata scraping."""

from unittest.mock import AsyncMock, patch

from app.services.scrapers import (
    detect_site,
    scrape_metadata,
    _extract_og_metadata,
    MODEL_EXTENSIONS,
    SITE_HOSTS,
)


# ---------------------------------------------------------------------------
# detect_site()
# ---------------------------------------------------------------------------


class TestDetectSite:
    """Tests for the detect_site() function."""

    def test_thingiverse_url(self):
        assert detect_site("https://www.thingiverse.com/thing:12345") == "thingiverse"

    def test_thingiverse_no_www(self):
        assert detect_site("https://thingiverse.com/thing:12345") == "thingiverse"

    def test_makerworld_url(self):
        assert detect_site("https://makerworld.com/models/12345-cool-thing") == "makerworld"

    def test_makerworld_www(self):
        assert detect_site("https://www.makerworld.com/models/12345") == "makerworld"

    def test_printables_url(self):
        assert detect_site("https://www.printables.com/model/12345-name") == "printables"

    def test_printables_no_www(self):
        assert detect_site("https://printables.com/model/12345-name") == "printables"

    def test_myminifactory_url(self):
        assert detect_site("https://www.myminifactory.com/object/3d-print-something-12345") == "myminifactory"

    def test_cults3d_url(self):
        assert detect_site("https://cults3d.com/en/3d-model/something") == "cults3d"

    def test_thangs_url(self):
        assert detect_site("https://thangs.com/designer/name/3d-model/something") == "thangs"

    def test_unknown_site(self):
        assert detect_site("https://example.com/model.stl") is None

    def test_direct_file_url(self):
        assert detect_site("https://cdn.example.com/files/model.stl") is None

    def test_empty_string(self):
        assert detect_site("") is None

    def test_malformed_url(self):
        assert detect_site("not a url at all") is None

    def test_case_insensitive_host(self):
        """Host matching should be case-insensitive."""
        assert detect_site("https://WWW.THINGIVERSE.COM/thing:12345") == "thingiverse"

    def test_url_with_query_params(self):
        assert detect_site("https://www.thingiverse.com/thing:12345?ref=user") == "thingiverse"

    def test_url_with_fragment(self):
        assert detect_site("https://www.printables.com/model/999#comments") == "printables"


# ---------------------------------------------------------------------------
# _extract_og_metadata()
# ---------------------------------------------------------------------------


class TestExtractOgMetadata:
    """Tests for the _extract_og_metadata() function."""

    def test_extracts_og_title(self):
        html = '<html><head><meta property="og:title" content="Test Model"/></head></html>'
        meta = _extract_og_metadata(html)
        assert meta["title"] == "Test Model"

    def test_extracts_og_description(self):
        html = '<html><head><meta property="og:description" content="A cool model"/></head></html>'
        meta = _extract_og_metadata(html)
        assert meta["description"] == "A cool model"

    def test_falls_back_to_title_tag(self):
        html = "<html><head><title>Fallback Title</title></head></html>"
        meta = _extract_og_metadata(html)
        assert meta["title"] == "Fallback Title"

    def test_prefers_og_title_over_title_tag(self):
        html = '<html><head><meta property="og:title" content="OG Title"/><title>HTML Title</title></head></html>'
        meta = _extract_og_metadata(html)
        assert meta["title"] == "OG Title"

    def test_extracts_meta_keywords_as_tags(self):
        html = '<html><head><meta name="keywords" content="tag1, tag2, tag3"/></head></html>'
        meta = _extract_og_metadata(html)
        assert meta["tags"] == ["tag1", "tag2", "tag3"]

    def test_empty_html(self):
        meta = _extract_og_metadata("")
        assert meta["title"] is None
        assert meta["description"] is None
        assert meta["tags"] == []
        assert meta["download_urls"] == []

    def test_strips_whitespace(self):
        html = '<html><head><meta property="og:title" content="  Spaced Title  "/></head></html>'
        meta = _extract_og_metadata(html)
        assert meta["title"] == "Spaced Title"


# ---------------------------------------------------------------------------
# scrape_metadata() — with mocked HTTP
# ---------------------------------------------------------------------------


class TestScrapeMetadata:
    """Tests for the scrape_metadata() entry point with mocked HTTP responses."""

    async def test_unknown_site_returns_url_as_download(self):
        """Unknown sites should return the URL itself as a download URL."""
        url = "https://example.com/files/model.stl"
        result = await scrape_metadata(url)
        assert result["source_site"] is None
        assert url in result["download_urls"]

    async def test_thingiverse_fallback_scrape(self):
        """Thingiverse without API key should scrape og: tags."""
        html = (
            '<html><head>'
            '<meta property="og:title" content="Cool Print"/>'
            '<meta property="og:description" content="A nice print"/>'
            '</head><body>'
            '<a href="/thing:12345/download">Download</a>'
            '</body></html>'
        )

        mock_response = AsyncMock()
        mock_response.text = html
        mock_response.raise_for_status = lambda: None

        with patch("app.services.scrapers.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await scrape_metadata("https://www.thingiverse.com/thing:12345")

        assert result["source_site"] == "thingiverse"
        assert result["title"] == "Cool Print"
        assert any("/download" in u for u in result["download_urls"])

    async def test_printables_graphql_scrape(self):
        """Printables should attempt GraphQL and parse response."""
        graphql_response = {
            "data": {
                "print": {
                    "name": "Test Print",
                    "description": "A test",
                    "tags": [{"name": "pla"}, {"name": "vase"}],
                    "stls": [{"id": "100", "name": "part.stl", "fileSize": 1024}],
                    "gcodes": [],
                }
            }
        }

        mock_response = AsyncMock()
        mock_response.json = lambda: graphql_response
        mock_response.raise_for_status = lambda: None

        with patch("app.services.scrapers.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await scrape_metadata("https://www.printables.com/model/12345-test")

        assert result["source_site"] == "printables"
        assert result["title"] == "Test Print"
        assert "pla" in result["tags"]
        assert len(result["download_urls"]) == 1

    async def test_makerworld_without_token(self):
        """MakerWorld without credentials should return an error."""
        result = await scrape_metadata("https://makerworld.com/models/12345")
        assert result["source_site"] == "makerworld"
        assert result["error"] is not None
        assert "token" in result["error"].lower()

    async def test_generic_site_scrape(self):
        """Generic sites (myminifactory, cults3d, thangs) use og: scraper."""
        html = (
            '<html><head>'
            '<meta property="og:title" content="Factory Model"/>'
            '</head><body>'
            '<a href="/download/model.stl">Download</a>'
            '</body></html>'
        )

        mock_response = AsyncMock()
        mock_response.text = html
        mock_response.raise_for_status = lambda: None

        with patch("app.services.scrapers.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await scrape_metadata("https://www.myminifactory.com/object/something")

        assert result["source_site"] == "myminifactory"
        assert result["title"] == "Factory Model"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Tests for module-level constants."""

    def test_model_extensions_includes_common_formats(self):
        assert ".stl" in MODEL_EXTENSIONS
        assert ".obj" in MODEL_EXTENSIONS
        assert ".3mf" in MODEL_EXTENSIONS
        assert ".glb" in MODEL_EXTENSIONS
        assert ".zip" in MODEL_EXTENSIONS

    def test_site_hosts_has_www_variants(self):
        """Every site should have both www and non-www entries."""
        base_sites = {v for v in SITE_HOSTS.values()}
        for site in base_sites:
            hosts_for_site = [h for h, s in SITE_HOSTS.items() if s == site]
            assert len(hosts_for_site) >= 2, f"{site} missing www/non-www variant"
