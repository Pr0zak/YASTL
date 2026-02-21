"""Credential management for site-specific import authentication.

Stores and retrieves API keys, tokens, and other credentials needed
to access 3D model hosting sites (Thingiverse API key, MakerWorld
Bambu Lab token, etc.) in the application settings table.
"""

import json
import logging

from app.database import get_setting

logger = logging.getLogger(__name__)

CREDENTIAL_SETTINGS_KEY = "import_credentials"


async def get_credentials() -> dict:
    """Load stored import credentials from the settings table."""
    raw = await get_setting(CREDENTIAL_SETTINGS_KEY, "{}")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


async def set_credentials(site: str, creds: dict) -> None:
    """Store credentials for a specific site."""
    all_creds = await get_credentials()
    all_creds[site] = creds
    from app.database import set_setting
    await set_setting(CREDENTIAL_SETTINGS_KEY, json.dumps(all_creds))


async def delete_credentials(site: str) -> None:
    """Remove credentials for a specific site."""
    all_creds = await get_credentials()
    all_creds.pop(site, None)
    from app.database import set_setting
    await set_setting(CREDENTIAL_SETTINGS_KEY, json.dumps(all_creds))


def mask_credentials(creds: dict) -> dict:
    """Mask credential values for API responses (show last 4 chars)."""
    masked: dict = {}
    for site, site_creds in creds.items():
        masked[site] = {}
        for key, value in site_creds.items():
            if isinstance(value, str) and len(value) > 4:
                masked[site][key] = "****" + value[-4:]
            elif isinstance(value, str):
                masked[site][key] = "****"
            else:
                masked[site][key] = value
    return masked
