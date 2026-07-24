"""Vision auto-tagging (AI Phase 2).

Sends a model's rendered thumbnail (+ filename) to the configured vision model,
filters suggestions against the tag vocabulary, and stores accepted tags with
``source='ai'`` plus a description when one is missing. The API call and the DB
write are split so the bulk job can run the (slow, I/O-bound) vision calls
concurrently while serializing writes.
"""

import logging
from pathlib import Path

from app.database import update_fts_for_model
from app.services import ai_client

logger = logging.getLogger("yastl")


async def suggest_vision_tags(model: dict, vocab: list[str], vocab_mode: str) -> dict | None:
    """Call the vision model for one model and return accepted tags + description.

    Returns None when the model has no thumbnail on disk. Post-filters the
    model's suggestions against the vocabulary (controlled = existing tags only;
    open = allow up to a couple of new tags).
    """
    thumb = model.get("thumbnail_path")
    if not thumb or not Path(thumb).is_file():
        return None
    image_bytes = Path(thumb).read_bytes()
    filename = model.get("name") or Path(model.get("file_path") or "").name

    result = await ai_client.vision_tags(image_bytes, filename, vocab)

    vocab_lower = {v.lower(): v for v in vocab}
    accepted: list[str] = []
    new_count = 0
    for tag in result.get("tags", []):
        tl = tag.lower()
        if tl in vocab_lower:
            accepted.append(vocab_lower[tl])            # canonical existing casing
        elif vocab_mode == "open" and new_count < 2:
            accepted.append(tl)                          # new tag, lowercased
            new_count += 1
        # controlled + unknown -> dropped
    return {"tags": accepted, "description": result.get("description", "")}


async def store_ai_tags(db, model: dict, suggestion: dict) -> dict:
    """Persist accepted AI tags (source='ai', never overwriting an existing
    manual/auto link) and fill the description only if it is empty."""
    tags_added = 0
    for tag_name in suggestion.get("tags", []):
        cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
        row = await cursor.fetchone()
        if row is None:
            cursor = await db.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
            tag_id = cursor.lastrowid
        else:
            tag_id = dict(row)["id"]
        cursor = await db.execute(
            "INSERT INTO model_tags (model_id, tag_id, source) VALUES (?, ?, 'ai') "
            "ON CONFLICT(model_id, tag_id) DO NOTHING",
            (model["id"], tag_id),
        )
        tags_added += cursor.rowcount

    description_set = False
    desc = (suggestion.get("description") or "").strip()
    if desc and not (model.get("description") or "").strip():
        await db.execute(
            "UPDATE models SET description = ? WHERE id = ?", (desc, model["id"])
        )
        description_set = True

    await update_fts_for_model(db, model["id"])
    return {"tags_added": tags_added, "description_set": description_set}
