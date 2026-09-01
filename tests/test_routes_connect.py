"""Tests for the YASTL Connect browser-extension API."""

import pytest


async def _enable_connect(client, token: str = "test-token-123") -> str:
    """Turn Connect on and pin a known token, returning it."""
    resp = await client.put(
        "/api/settings", json={"connect_enabled": "true", "connect_token": token}
    )
    assert resp.status_code == 200
    return token


async def _make_library(client, path) -> int:
    resp = await client.post("/api/libraries", json={"name": "lib", "path": str(path)})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


class TestConnectInfo:
    """The unauthenticated handshake endpoint."""

    async def test_info_reachable_without_token(self, client):
        resp = await client.get("/api/connect/info")
        assert resp.status_code == 200
        body = resp.json()
        assert body["app"] == "yastl"
        assert body["protocol"] >= 1

    async def test_info_reports_disabled_by_default(self, client):
        """Connect must be off until explicitly enabled."""
        body = (await client.get("/api/connect/info")).json()
        assert body["connect_enabled"] is False
        assert body["token_configured"] is False

    async def test_info_reflects_enabled_state(self, client):
        await _enable_connect(client)
        body = (await client.get("/api/connect/info")).json()
        assert body["connect_enabled"] is True
        assert body["token_configured"] is True

    async def test_info_never_leaks_the_token(self, client):
        token = await _enable_connect(client, "super-secret-value")
        text = (await client.get("/api/connect/info")).text
        assert token not in text


class TestConnectAuth:
    """Token gating on the authenticated endpoints."""

    async def test_targets_rejected_when_connect_disabled(self, client):
        resp = await client.get("/api/connect/targets")
        assert resp.status_code == 403
        assert "disabled" in resp.json()["detail"].lower()

    async def test_targets_rejected_without_token_header(self, client):
        await _enable_connect(client)
        resp = await client.get("/api/connect/targets")
        assert resp.status_code == 401

    async def test_targets_rejected_with_wrong_token(self, client):
        await _enable_connect(client)
        resp = await client.get(
            "/api/connect/targets", headers={"X-YASTL-Token": "nope"}
        )
        assert resp.status_code == 401

    async def test_targets_accepted_with_correct_token(self, client):
        token = await _enable_connect(client)
        resp = await client.get(
            "/api/connect/targets", headers={"X-YASTL-Token": token}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "libraries" in body
        assert "collections" in body
        assert ".stl" in body["extensions"]

    async def test_enabled_but_no_token_is_rejected(self, client):
        """Enabling Connect without generating a token must not open the door."""
        await client.put(
            "/api/settings", json={"connect_enabled": "true", "connect_token": ""}
        )
        resp = await client.get(
            "/api/connect/targets", headers={"X-YASTL-Token": "anything"}
        )
        assert resp.status_code == 403


class TestConnectToken:
    """Token generation and masking."""

    async def test_rotate_returns_a_usable_token(self, client):
        await client.put("/api/settings", json={"connect_enabled": "true"})
        resp = await client.post("/api/connect/token")
        assert resp.status_code == 200
        token = resp.json()["token"]
        assert len(token) >= 32

        ok = await client.get("/api/connect/targets", headers={"X-YASTL-Token": token})
        assert ok.status_code == 200

    async def test_rotation_invalidates_the_previous_token(self, client):
        old = await _enable_connect(client)
        await client.post("/api/connect/token")
        resp = await client.get("/api/connect/targets", headers={"X-YASTL-Token": old})
        assert resp.status_code == 401

    async def test_settings_read_masks_the_token(self, client):
        token = await _enable_connect(client, "abcdefghijklmnop")
        settings = (await client.get("/api/settings")).json()
        assert settings["connect_token"] != token
        assert "•" in settings["connect_token"]

    async def test_masked_value_is_not_written_back(self, client):
        """Saving the settings form must not clobber the token with its mask."""
        token = await _enable_connect(client, "abcdefghijklmnop")
        masked = (await client.get("/api/settings")).json()["connect_token"]
        await client.put("/api/settings", json={"connect_token": masked})

        resp = await client.get("/api/connect/targets", headers={"X-YASTL-Token": token})
        assert resp.status_code == 200


class TestConnectCapture:
    """The capture endpoint — the one that actually writes to the library."""

    @pytest.fixture
    def stl_bytes(self, tmp_path, create_stl):
        p = tmp_path / "src.stl"
        create_stl(p)
        return p.read_bytes()

    async def test_capture_requires_token(self, client, stl_bytes):
        await _enable_connect(client)
        resp = await client.post(
            "/api/connect/capture",
            files={"file": ("thing.stl", stl_bytes, "model/stl")},
            data={"library_id": "1"},
        )
        assert resp.status_code == 401

    async def test_capture_imports_a_model_with_metadata(
        self, client, stl_bytes, tmp_path
    ):
        token = await _enable_connect(client)
        lib_dir = tmp_path / "library"
        lib_dir.mkdir()
        library_id = await _make_library(client, lib_dir)

        resp = await client.post(
            "/api/connect/capture",
            headers={"X-YASTL-Token": token},
            files={"file": ("widget.stl", stl_bytes, "model/stl")},
            data={
                "library_id": str(library_id),
                "name": "Captured Widget",
                "description": "From the source page.",
                "source_url": "https://www.printables.com/model/12345-widget",
                "tags": "printables, functional, printables",
                "author": "Someone",
                "license": "CC-BY-4.0",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_ids"], body

        model_id = body["model_ids"][0]
        model = (await client.get(f"/api/models/{model_id}")).json()
        assert model["name"] == "Captured Widget"
        assert model["description"] == "From the source page."
        assert model["source_url"].endswith("12345-widget")
        assert model["license"] == "CC-BY-4.0"

        tags = {t["name"] if isinstance(t, dict) else t for t in model["tags"]}
        assert "functional" in tags
        assert "author:Someone" in tags
        # The duplicate "printables" in the input must not produce two tags.
        assert sum(1 for t in tags if t == "printables") == 1

    async def test_capture_rejects_unsupported_format(
        self, client, tmp_path
    ):
        token = await _enable_connect(client)
        lib_dir = tmp_path / "library"
        lib_dir.mkdir()
        library_id = await _make_library(client, lib_dir)

        resp = await client.post(
            "/api/connect/capture",
            headers={"X-YASTL-Token": token},
            files={"file": ("notes.txt", b"hello", "text/plain")},
            data={"library_id": str(library_id)},
        )
        assert resp.status_code == 400
        assert "Unsupported format" in resp.json()["detail"]

    async def test_capture_rejects_unknown_library(self, client, stl_bytes):
        token = await _enable_connect(client)
        resp = await client.post(
            "/api/connect/capture",
            headers={"X-YASTL-Token": token},
            files={"file": ("widget.stl", stl_bytes, "model/stl")},
            data={"library_id": "99999"},
        )
        assert resp.status_code == 404

    async def test_capture_rejects_subfolder_escape(
        self, client, stl_bytes, tmp_path
    ):
        """A traversing subfolder must not write outside the library root."""
        token = await _enable_connect(client)
        lib_dir = tmp_path / "library"
        lib_dir.mkdir()
        library_id = await _make_library(client, lib_dir)

        resp = await client.post(
            "/api/connect/capture",
            headers={"X-YASTL-Token": token},
            files={"file": ("widget.stl", stl_bytes, "model/stl")},
            data={"library_id": str(library_id), "subfolder": "../../escaped"},
        )
        assert resp.status_code == 400
        assert not (tmp_path.parent / "escaped").exists()

    async def test_capture_rejects_non_http_source_url(
        self, client, stl_bytes, tmp_path
    ):
        token = await _enable_connect(client)
        lib_dir = tmp_path / "library"
        lib_dir.mkdir()
        library_id = await _make_library(client, lib_dir)

        resp = await client.post(
            "/api/connect/capture",
            headers={"X-YASTL-Token": token},
            files={"file": ("widget.stl", stl_bytes, "model/stl")},
            data={
                "library_id": str(library_id),
                "source_url": "javascript:alert(1)",
            },
        )
        assert resp.status_code == 400


class TestConnectCors:
    """Cross-origin access for the browser extension.

    These exist because the first version of Connect shipped without CORS on the
    belief that an MV3 service worker is exempt for hosts it holds a permission
    for. It is not: Chrome sent the request, the server logged a clean 200, and
    the response was discarded before the extension could read it.
    """

    EXT = "chrome-extension://" + "a" * 32
    FIREFOX = "moz-extension://12345678-1234-1234-1234-123456789abc"

    async def test_preflight_is_answered_without_a_token(self, client):
        """The preflight carries no custom headers, so it must pass auth-free."""
        resp = await client.request(
            "OPTIONS",
            "/api/connect/capture",
            headers={
                "Origin": self.EXT,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-yastl-token",
            },
        )
        assert resp.status_code == 204
        assert resp.headers["access-control-allow-origin"] == self.EXT
        assert "x-yastl-token" in resp.headers["access-control-allow-headers"].lower()

    async def test_response_carries_the_allow_origin_header(self, client):
        resp = await client.get("/api/connect/info", headers={"Origin": self.EXT})
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == self.EXT

    async def test_firefox_extension_origin_is_allowed(self, client):
        resp = await client.get("/api/connect/info", headers={"Origin": self.FIREFOX})
        assert resp.headers["access-control-allow-origin"] == self.FIREFOX

    async def test_authenticated_route_is_also_stamped(self, client):
        token = await _enable_connect(client)
        resp = await client.get(
            "/api/connect/targets",
            headers={"Origin": self.EXT, "X-YASTL-Token": token},
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == self.EXT

    async def test_a_rejected_request_is_still_stamped(self, client):
        """Without the header the extension sees a CORS error, not the 401.

        A misconfigured token has to surface as "wrong token", so even the
        failure response needs to be readable cross-origin.
        """
        await _enable_connect(client)
        resp = await client.get(
            "/api/connect/targets",
            headers={"Origin": self.EXT, "X-YASTL-Token": "wrong"},
        )
        assert resp.status_code == 401
        assert resp.headers["access-control-allow-origin"] == self.EXT

    async def test_ordinary_web_origins_are_refused(self, client):
        resp = await client.get(
            "/api/connect/info", headers={"Origin": "https://evil.example.com"}
        )
        assert "access-control-allow-origin" not in resp.headers

    async def test_extension_shaped_but_invalid_origin_is_refused(self, client):
        resp = await client.get(
            "/api/connect/info", headers={"Origin": "chrome-extension://short"}
        )
        assert "access-control-allow-origin" not in resp.headers

    async def test_cors_does_not_leak_onto_the_rest_of_the_api(self, client):
        """YASTL has no auth, so any other route must stay closed to extensions."""
        for path in ("/api/libraries", "/api/settings", "/api/status"):
            resp = await client.get(path, headers={"Origin": self.EXT})
            assert "access-control-allow-origin" not in resp.headers, path


class TestExtensionDownload:
    """Serving the extension itself.

    The download is deliberately unauthenticated: it is a plain <a download>
    link from the Settings page, which cannot attach a token header, and the
    archive holds only what is already public in the repository.
    """

    async def test_download_returns_a_zip(self, client):
        resp = await client.get("/api/connect/extension.zip")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.content[:2] == b"PK"

    async def test_download_needs_no_token(self, client):
        """Requiring one would be circular — the extension is what it is for."""
        resp = await client.get("/api/connect/extension.zip")
        assert resp.status_code == 200

    async def test_zip_contains_a_loadable_extension(self, client):
        import io
        import zipfile

        resp = await client.get("/api/connect/extension.zip")
        names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()

        # A browser refuses an unpacked directory whose manifest is not at the
        # root, so the archive must not be nested inside a folder.
        assert "manifest.json" in names
        assert "src/background.js" in names
        assert "icons/icon-128.png" in names

    async def test_zip_excludes_the_test_suite(self, client):
        import io
        import zipfile

        resp = await client.get("/api/connect/extension.zip")
        names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
        assert not any(n.startswith("tests/") for n in names), names

    async def test_filename_carries_the_version(self, client):
        resp = await client.get("/api/connect/extension.zip")
        assert "yastl-connect-" in resp.headers["content-disposition"]

    async def test_info_advertises_the_packaged_version(self, client):
        """So an installed copy can notice it is stale — it never self-updates."""
        body = (await client.get("/api/connect/info")).json()
        assert body["extension_version"]
        assert body["extension_download"] == "/api/connect/extension.zip"

    async def test_advertised_version_matches_the_manifest(self, client):
        import io
        import json
        import zipfile

        info = (await client.get("/api/connect/info")).json()
        resp = await client.get("/api/connect/extension.zip")
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert manifest["version"] == info["extension_version"]
