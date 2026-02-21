"""Tests for app.services.import_credentials — credential CRUD and masking."""

import json
from unittest.mock import AsyncMock, patch

from app.services.import_credentials import (
    delete_credentials,
    get_credentials,
    mask_credentials,
    set_credentials,
)


# ---------------------------------------------------------------------------
# get_credentials()
# ---------------------------------------------------------------------------


class TestGetCredentials:
    """Tests for credential retrieval from the settings table."""

    async def test_returns_stored_credentials(self):
        """When credentials exist, they should be returned as a dict."""
        stored = json.dumps({"thingiverse": {"api_key": "abc123"}})

        with patch(
            "app.services.import_credentials.get_setting",
            new_callable=AsyncMock,
            return_value=stored,
        ):
            result = await get_credentials()

        assert result == {"thingiverse": {"api_key": "abc123"}}

    async def test_returns_empty_dict_when_no_credentials(self):
        """When no credentials stored, should return empty dict."""
        with patch(
            "app.services.import_credentials.get_setting",
            new_callable=AsyncMock,
            return_value="{}",
        ):
            result = await get_credentials()

        assert result == {}

    async def test_handles_malformed_json(self):
        """Malformed JSON should return empty dict instead of raising."""
        with patch(
            "app.services.import_credentials.get_setting",
            new_callable=AsyncMock,
            return_value="not valid json {{{",
        ):
            result = await get_credentials()

        assert result == {}

    async def test_handles_none_setting(self):
        """None value from get_setting should return empty dict."""
        with patch(
            "app.services.import_credentials.get_setting",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await get_credentials()

        assert result == {}

    async def test_multiple_sites(self):
        """Credentials for multiple sites should all be returned."""
        stored = json.dumps({
            "thingiverse": {"api_key": "tv_key"},
            "makerworld": {"token": "mw_token"},
        })

        with patch(
            "app.services.import_credentials.get_setting",
            new_callable=AsyncMock,
            return_value=stored,
        ):
            result = await get_credentials()

        assert "thingiverse" in result
        assert "makerworld" in result
        assert result["thingiverse"]["api_key"] == "tv_key"


# ---------------------------------------------------------------------------
# set_credentials()
# ---------------------------------------------------------------------------


class TestSetCredentials:
    """Tests for storing credentials."""

    async def test_set_new_credentials(self):
        """Setting credentials for a new site should store them."""
        with (
            patch(
                "app.services.import_credentials.get_setting",
                new_callable=AsyncMock,
                return_value="{}",
            ),
            patch(
                "app.database.set_setting",
                new_callable=AsyncMock,
            ) as mock_set,
        ):
            await set_credentials("thingiverse", {"api_key": "new_key"})

        mock_set.assert_called_once()
        stored_json = mock_set.call_args.args[1]
        stored = json.loads(stored_json)
        assert stored["thingiverse"]["api_key"] == "new_key"

    async def test_update_existing_credentials(self):
        """Updating credentials for an existing site should replace them."""
        existing = json.dumps({"thingiverse": {"api_key": "old_key"}})

        with (
            patch(
                "app.services.import_credentials.get_setting",
                new_callable=AsyncMock,
                return_value=existing,
            ),
            patch(
                "app.database.set_setting",
                new_callable=AsyncMock,
            ) as mock_set,
        ):
            await set_credentials("thingiverse", {"api_key": "updated_key"})

        stored_json = mock_set.call_args.args[1]
        stored = json.loads(stored_json)
        assert stored["thingiverse"]["api_key"] == "updated_key"

    async def test_set_preserves_other_sites(self):
        """Setting one site's credentials should not affect other sites."""
        existing = json.dumps({"thingiverse": {"api_key": "tv_key"}})

        with (
            patch(
                "app.services.import_credentials.get_setting",
                new_callable=AsyncMock,
                return_value=existing,
            ),
            patch(
                "app.database.set_setting",
                new_callable=AsyncMock,
            ) as mock_set,
        ):
            await set_credentials("makerworld", {"token": "mw_token"})

        stored_json = mock_set.call_args.args[1]
        stored = json.loads(stored_json)
        assert stored["thingiverse"]["api_key"] == "tv_key"
        assert stored["makerworld"]["token"] == "mw_token"


# ---------------------------------------------------------------------------
# delete_credentials()
# ---------------------------------------------------------------------------


class TestDeleteCredentials:
    """Tests for removing credentials."""

    async def test_delete_existing_site(self):
        """Deleting credentials for an existing site should remove them."""
        existing = json.dumps({
            "thingiverse": {"api_key": "tv_key"},
            "makerworld": {"token": "mw_token"},
        })

        with (
            patch(
                "app.services.import_credentials.get_setting",
                new_callable=AsyncMock,
                return_value=existing,
            ),
            patch(
                "app.database.set_setting",
                new_callable=AsyncMock,
            ) as mock_set,
        ):
            await delete_credentials("thingiverse")

        stored_json = mock_set.call_args.args[1]
        stored = json.loads(stored_json)
        assert "thingiverse" not in stored
        assert "makerworld" in stored

    async def test_delete_nonexistent_site_no_error(self):
        """Deleting a site that doesn't exist should not raise."""
        existing = json.dumps({"thingiverse": {"api_key": "tv_key"}})

        with (
            patch(
                "app.services.import_credentials.get_setting",
                new_callable=AsyncMock,
                return_value=existing,
            ),
            patch(
                "app.database.set_setting",
                new_callable=AsyncMock,
            ) as mock_set,
        ):
            await delete_credentials("nonexistent")

        stored_json = mock_set.call_args.args[1]
        stored = json.loads(stored_json)
        # Original credentials should still be there
        assert stored["thingiverse"]["api_key"] == "tv_key"


# ---------------------------------------------------------------------------
# mask_credentials()
# ---------------------------------------------------------------------------


class TestMaskCredentials:
    """Tests for credential masking in API responses."""

    def test_masks_long_strings(self):
        """Strings longer than 4 chars should show last 4 chars only."""
        creds = {"thingiverse": {"api_key": "abcdef123456"}}
        masked = mask_credentials(creds)

        assert masked["thingiverse"]["api_key"] == "****3456"

    def test_masks_short_strings(self):
        """Strings 4 chars or shorter should be fully masked."""
        creds = {"site": {"key": "ab"}}
        masked = mask_credentials(creds)

        assert masked["site"]["key"] == "****"

    def test_masks_exactly_four_chars(self):
        """Exactly 4-char strings should be fully masked."""
        creds = {"site": {"key": "abcd"}}
        masked = mask_credentials(creds)

        assert masked["site"]["key"] == "****"

    def test_non_string_values_preserved(self):
        """Non-string values (booleans, ints) should be passed through."""
        creds = {"site": {"enabled": True, "count": 42}}
        masked = mask_credentials(creds)

        assert masked["site"]["enabled"] is True
        assert masked["site"]["count"] == 42

    def test_empty_credentials(self):
        """Empty credential dict should return empty dict."""
        assert mask_credentials({}) == {}

    def test_multiple_sites(self):
        """All sites should be masked independently."""
        creds = {
            "thingiverse": {"api_key": "long_tv_key_12345"},
            "makerworld": {"token": "long_mw_token_678"},
        }
        masked = mask_credentials(creds)

        assert masked["thingiverse"]["api_key"] == "****2345"
        assert masked["makerworld"]["token"] == "****_678"

    def test_five_char_string_shows_last_four(self):
        """A 5-char string should show last 4 chars with mask prefix."""
        creds = {"site": {"key": "12345"}}
        masked = mask_credentials(creds)

        assert masked["site"]["key"] == "****2345"

    def test_empty_string_fully_masked(self):
        """An empty string should be fully masked."""
        creds = {"site": {"key": ""}}
        masked = mask_credentials(creds)

        assert masked["site"]["key"] == "****"
