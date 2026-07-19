"""Outbound webhook notifications (e.g. Home Assistant automations).

Fires a JSON POST to the configured ``webhook_url`` on library events.
Failures are logged, never raised — notifications are best-effort.
"""

import logging

import httpx

from app.database import get_setting

logger = logging.getLogger("yastl")


async def notify_webhook(event: str, payload: dict | None = None) -> bool:
    """POST ``{event, **payload}`` to the configured webhook URL.

    Returns True if delivered (2xx), False if disabled or on any error.
    """
    url = (await get_setting("webhook_url", "") or "").strip()
    if not url:
        return False

    body = {"event": event}
    if payload:
        body.update(payload)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
        logger.info("Webhook '%s' delivered to %s", event, url)
        return True
    except Exception as e:  # noqa: BLE001 - notifications are best-effort
        logger.warning("Webhook '%s' delivery failed: %s", event, e)
        return False
