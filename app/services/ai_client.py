"""Optional bring-your-own-key AI client: chat/vision + text embeddings.

Uses raw ``httpx`` (no provider SDKs) to keep a self-hosted install
dependency-light. Supports OpenAI-compatible endpoints (OpenAI, OpenRouter)
and Anthropic for chat/vision; OpenAI-compatible + Voyage for embeddings.
Everything is opt-in (``ai_enabled``) and raises :class:`AINotConfigured`
when no key is set so callers can degrade gracefully.

Config is read from the settings table, with ``YASTL_AI_API_KEY`` /
``YASTL_AI_EMBED_KEY`` env vars taking precedence (recommended for secrets).
"""

import base64
import json
import logging
import os
import re

import httpx

from app.database import get_all_settings

logger = logging.getLogger("yastl")


class AINotConfigured(Exception):
    """AI feature invoked while disabled or without a key."""


class AIError(Exception):
    """A provider call failed."""


# Sensible cheap defaults per provider (overridable via settings).
_DEFAULT_VISION = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
    "openrouter": "anthropic/claude-haiku-4.5",
}
_DEFAULT_EMBED = {
    "openai": "text-embedding-3-small",
    "openrouter": "openai/text-embedding-3-small",
    "voyage": "voyage-3.5-lite",
}
_OPENAI_COMPAT_BASE = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}
_ANTHROPIC_BASE = "https://api.anthropic.com/v1"
_VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
_ANTHROPIC_VERSION = "2023-06-01"
_TIMEOUT = 60.0


async def get_ai_config() -> dict:
    """Resolve the effective AI configuration from settings + env."""
    s = await get_all_settings()
    provider = s.get("ai_provider", "openrouter")
    embed_provider = s.get("ai_embed_provider", "openrouter")

    api_key = os.getenv("YASTL_AI_API_KEY") or s.get("ai_api_key", "") or ""
    embed_key = os.getenv("YASTL_AI_EMBED_KEY") or s.get("ai_embed_key", "") or ""
    # An OpenAI-compatible embed provider can reuse the chat key when the chat
    # provider is also OpenAI-compatible (same account). Voyage always needs its own.
    if not embed_key and embed_provider in _OPENAI_COMPAT_BASE and provider in _OPENAI_COMPAT_BASE:
        embed_key = api_key

    return {
        "enabled": s.get("ai_enabled", "false") == "true",
        "provider": provider,
        "api_key": api_key,
        "vision_model": s.get("ai_vision_model") or _DEFAULT_VISION.get(provider, ""),
        "embed_provider": embed_provider,
        "embed_key": embed_key,
        "embed_model": s.get("ai_embed_model") or _DEFAULT_EMBED.get(embed_provider, ""),
        "vocab_mode": s.get("ai_autotag_vocab_mode", "controlled"),
    }


def _require(cfg: dict, *, embed: bool = False) -> None:
    if not cfg["enabled"]:
        raise AINotConfigured("AI features are disabled")
    if not (cfg["embed_key"] if embed else cfg["api_key"]):
        raise AINotConfigured("No API key configured")


async def _post_json(url: str, headers: dict, payload: dict) -> dict:
    """POST JSON and return the parsed response, raising AIError on failure."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:  # network/timeout
        raise AIError(f"request failed: {e}") from e
    if resp.status_code >= 400:
        snippet = resp.text[:300].replace("\n", " ")
        raise AIError(f"HTTP {resp.status_code}: {snippet}")
    try:
        return resp.json()
    except ValueError as e:
        raise AIError("provider returned non-JSON response") from e


def _extract_json_obj(text: str) -> dict:
    """Parse the first JSON object out of a model's text response."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except ValueError:
            pass
    raise AIError("could not parse JSON from model response")


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------
async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts; returns one vector per input (order preserved)."""
    if not texts:
        return []
    cfg = await get_ai_config()
    _require(cfg, embed=True)
    provider, model, key = cfg["embed_provider"], cfg["embed_model"], cfg["embed_key"]

    if provider in _OPENAI_COMPAT_BASE:
        url = _OPENAI_COMPAT_BASE[provider] + "/embeddings"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        data = await _post_json(url, headers, {"model": model, "input": texts})
        items = sorted(data["data"], key=lambda d: d.get("index", 0))
        return [d["embedding"] for d in items]

    if provider == "voyage":
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        data = await _post_json(_VOYAGE_URL, headers, {"model": model, "input": texts})
        items = sorted(data["data"], key=lambda d: d.get("index", 0))
        return [d["embedding"] for d in items]

    raise AIError(f"unknown embed provider: {provider}")


# ---------------------------------------------------------------------------
# Vision auto-tagging
# ---------------------------------------------------------------------------
_VISION_SYSTEM = (
    "You tag 3D-printable model files for a hobbyist print library. Given a "
    "rendered thumbnail and the file's name/path, output a few concrete search "
    "tags and a one-line factual description of the object.\n"
    "Rules:\n"
    "- tags: lowercase, 1-3 words, concrete nouns/attributes a user would search "
    "(subject, category, style, articulated/etc). 3-8 tags.\n"
    "- description: one plain sentence, <=120 chars, no marketing language.\n"
    "- Prefer tags from the VOCABULARY when they fit.\n"
    "{vocab_rule}\n"
    "Respond with ONLY a JSON object: "
    '{{"tags": ["..."], "description": "..."}}.'
)


def _build_vision_prompt(vocab: list[str], vocab_mode: str, filename: str) -> tuple[str, str]:
    rule = (
        "- Do NOT invent tags outside the vocabulary."
        if vocab_mode == "controlled"
        else "- You may add up to 2 new tags if nothing in the vocabulary fits."
    )
    system = _VISION_SYSTEM.format(vocab_rule=rule)
    vocab_str = ", ".join(vocab[:400]) if vocab else "(none yet)"
    user = f"File: {filename}\nVOCABULARY: {vocab_str}"
    return system, user


async def vision_tags(image_bytes: bytes, filename: str, vocab: list[str]) -> dict:
    """Suggest {tags: [...], description: str} from a thumbnail + filename."""
    cfg = await get_ai_config()
    _require(cfg)
    provider, model, key = cfg["provider"], cfg["vision_model"], cfg["api_key"]
    system, user = _build_vision_prompt(vocab, cfg["vocab_mode"], filename)
    b64 = base64.b64encode(image_bytes).decode("ascii")

    if provider == "anthropic":
        raw = await _anthropic_vision(key, model, b64, system, user)
    else:
        raw = await _openai_vision(_OPENAI_COMPAT_BASE[provider], key, model, b64, system, user)

    obj = _extract_json_obj(raw)
    tags = [str(t).strip().lower() for t in (obj.get("tags") or []) if str(t).strip()]
    desc = str(obj.get("description") or "").strip()
    return {"tags": tags[:8], "description": desc[:200]}


async def _openai_vision(base: str, key: str, model: str, b64: str,
                         system: str, user: str) -> str:
    url = base + "/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "text", "text": user},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]},
        ],
    }
    data = await _post_json(url, headers, payload)
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise AIError("unexpected chat response shape") from e


async def _anthropic_vision(key: str, model: str, b64: str,
                            system: str, user: str) -> str:
    url = _ANTHROPIC_BASE + "/messages"
    headers = {
        "x-api-key": key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 300,
        "system": system,
        "messages": [
            {"role": "user", "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": user},
            ]},
        ],
    }
    data = await _post_json(url, headers, payload)
    try:
        return data["content"][0]["text"]
    except (KeyError, IndexError) as e:
        raise AIError("unexpected messages response shape") from e


# ---------------------------------------------------------------------------
# Connectivity test (used by POST /api/settings/ai/test)
# ---------------------------------------------------------------------------
async def test_connection() -> dict:
    """Validate the configured chat key with a tiny request. Returns {ok, detail}."""
    cfg = await get_ai_config()
    if not cfg["enabled"]:
        return {"ok": False, "detail": "AI is disabled (enable it first)"}
    if not cfg["api_key"]:
        return {"ok": False, "detail": "No chat API key configured"}
    try:
        provider, model, key = cfg["provider"], cfg["vision_model"], cfg["api_key"]
        if provider == "anthropic":
            headers = {"x-api-key": key, "anthropic-version": _ANTHROPIC_VERSION,
                       "Content-Type": "application/json"}
            await _post_json(_ANTHROPIC_BASE + "/messages", headers, {
                "model": model, "max_tokens": 1,
                "messages": [{"role": "user", "content": "ping"}],
            })
        else:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            await _post_json(_OPENAI_COMPAT_BASE[provider] + "/chat/completions", headers, {
                "model": model, "max_tokens": 1,
                "messages": [{"role": "user", "content": "ping"}],
            })
        return {"ok": True, "detail": f"{provider} / {model} reachable"}
    except (AINotConfigured, AIError) as e:
        return {"ok": False, "detail": str(e)}
