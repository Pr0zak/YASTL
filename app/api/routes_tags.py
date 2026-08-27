"""API routes for tag management."""

from fastapi import APIRouter, HTTPException, Request
import aiosqlite

from app.api._helpers import open_db

from app.database import update_fts_for_model


async def _refresh_fts_for_tag(db: aiosqlite.Connection, tag_id: int) -> list[int]:
    """Return model ids linked to a tag (call BEFORE mutating the tag)."""
    cursor = await db.execute(
        "SELECT model_id FROM model_tags WHERE tag_id = ?", (tag_id,)
    )
    return [row["model_id"] for row in await cursor.fetchall()]

router = APIRouter(prefix="/api/tags", tags=["tags"])


def _get_db_path(request: Request) -> str:
    """Retrieve the database path from FastAPI app state."""
    return request.app.state.db_path


# ---------------------------------------------------------------------------
# List all tags (with model count)
# ---------------------------------------------------------------------------


@router.get("")
async def list_tags(request: Request):
    """List all tags with the number of models associated with each."""
    db_path = _get_db_path(request)

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT t.id, t.name, COUNT(mt.model_id) as model_count
            FROM tags t
            LEFT JOIN model_tags mt ON mt.tag_id = t.id
            GROUP BY t.id, t.name
            ORDER BY t.name
            """
        )
        rows = await cursor.fetchall()

    return {"tags": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# Create tag
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_tag(request: Request):
    """Create a new tag.

    Expects JSON body: {"name": "tag_name"}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    name = body.get("name")

    if not name or not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=400, detail="'name' is required and must be a non-empty string")

    name = name.strip()

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Check if tag already exists (case-insensitive due to COLLATE NOCASE)
        cursor = await db.execute("SELECT id, name FROM tags WHERE name = ?", (name,))
        existing = await cursor.fetchone()
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Tag '{name}' already exists",
            )

        cursor = await db.execute("INSERT INTO tags (name) VALUES (?)", (name,))
        tag_id = cursor.lastrowid
        await db.commit()

    return {"id": tag_id, "name": name}


# ---------------------------------------------------------------------------
# Delete tag
# ---------------------------------------------------------------------------


@router.delete("/{tag_id}")
async def delete_tag(request: Request, tag_id: int):
    """Delete a tag by ID. Also removes all model-tag associations."""
    db_path = _get_db_path(request)

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Verify tag exists
        cursor = await db.execute("SELECT id, name FROM tags WHERE id = ?", (tag_id,))
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")

        tag_name = dict(row)["name"]

        affected_models = await _refresh_fts_for_tag(db, tag_id)

        # Delete the tag (model_tags entries cascade)
        await db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        for model_id in affected_models:
            await update_fts_for_model(db, model_id)
        await db.commit()

    return {"detail": f"Tag '{tag_name}' (id={tag_id}) deleted"}


# ---------------------------------------------------------------------------
# Rename tag
# ---------------------------------------------------------------------------


@router.put("/{tag_id}")
async def rename_tag(request: Request, tag_id: int):
    """Rename a tag.

    Expects JSON body: {"name": "new_name"}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    new_name = body.get("name")

    if not new_name or not isinstance(new_name, str) or not new_name.strip():
        raise HTTPException(status_code=400, detail="'name' is required and must be a non-empty string")

    new_name = new_name.strip()

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify tag exists
        cursor = await db.execute("SELECT id FROM tags WHERE id = ?", (tag_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Tag {tag_id} not found")

        # Check if new name conflicts with an existing tag
        cursor = await db.execute(
            "SELECT id FROM tags WHERE name = ? AND id != ?", (new_name, tag_id)
        )
        if await cursor.fetchone() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Tag '{new_name}' already exists",
            )

        await db.execute(
            "UPDATE tags SET name = ? WHERE id = ?", (new_name, tag_id)
        )
        for model_id in await _refresh_fts_for_tag(db, tag_id):
            await update_fts_for_model(db, model_id)
        await db.commit()

    return {"id": tag_id, "name": new_name}


# ---------------------------------------------------------------------------
# Merge tags
# ---------------------------------------------------------------------------


@router.post("/merge")
async def merge_tags(request: Request):
    """Merge one or more source tags into a target tag.

    Every model tagged with a source tag is retargeted to the target tag
    (deduplicated), then the source tags are deleted. FTS is refreshed
    for all affected models.

    Body: {"source_ids": [2, 3], "target_id": 1}
    """
    db_path = _get_db_path(request)
    body = await request.json()
    source_ids = body.get("source_ids") or []
    target_id = body.get("target_id")

    if not isinstance(source_ids, list) or not source_ids:
        raise HTTPException(status_code=400, detail="'source_ids' must be a non-empty list")
    if target_id is None:
        raise HTTPException(status_code=400, detail="'target_id' is required")
    source_ids = [s for s in source_ids if s != target_id]
    if not source_ids:
        raise HTTPException(status_code=400, detail="No source tags distinct from target")

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        cursor = await db.execute("SELECT id FROM tags WHERE id = ?", (target_id,))
        if await cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Target tag {target_id} not found")

        ph = ", ".join("?" for _ in source_ids)
        cursor = await db.execute(
            f"SELECT DISTINCT model_id FROM model_tags WHERE tag_id IN ({ph})",
            source_ids,
        )
        affected_models = [r["model_id"] for r in await cursor.fetchall()]

        # Retarget links to the target tag (ignore rows that already have it)
        await db.execute(
            f"UPDATE OR IGNORE model_tags SET tag_id = ? WHERE tag_id IN ({ph})",
            [target_id, *source_ids],
        )
        # Any leftover duplicate links (UPDATE OR IGNORE skipped them) are
        # removed with the source tags via cascade.
        await db.execute(f"DELETE FROM tags WHERE id IN ({ph})", source_ids)

        for model_id in affected_models:
            await update_fts_for_model(db, model_id)
        await db.commit()

    return {
        "detail": f"Merged {len(source_ids)} tag(s) into target",
        "target_id": target_id,
        "models_updated": len(affected_models),
    }


# ---------------------------------------------------------------------------
# Delete unused (zero-count) tags
# ---------------------------------------------------------------------------


@router.post("/cleanup")
async def cleanup_unused_tags(request: Request):
    """Delete all tags not attached to any model."""
    db_path = _get_db_path(request)

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        cursor = await db.execute(
            "DELETE FROM tags WHERE id NOT IN "
            "(SELECT DISTINCT tag_id FROM model_tags)"
        )
        removed = cursor.rowcount
        await db.commit()

    return {"detail": f"Removed {removed} unused tag(s)", "removed": removed}


# ---------------------------------------------------------------------------
# Normalise punctuation-damaged tags
# ---------------------------------------------------------------------------


@router.post("/normalize")
async def normalize_tags(request: Request, dry_run: bool = False):
    """Repair tags that carry filename punctuation, merging them where they collide.

    The auto-tagger used to tokenise filenames without stripping punctuation, so
    a library accumulated tags like ``(bishop)``, ``(3``, ``+0`` and ``80%)`` —
    each one matching only the files whose names happened to be punctuated the
    same way, and each one occupying a row in the sidebar ahead of every useful
    tag, because ``(`` sorts before every letter.

    A tag that is already well formed is never touched, which is what protects
    real hyphenated tags like ``low-poly``. Everything else has digit-only
    bracket groups removed (a ``(2)`` copy suffix), remaining punctuation
    stripped, and the rest tokenised: exactly one usable word is a repair,
    anything more was a mangled filename rather than a tag —
    ``+beer+mug+(two+types)`` — and is deleted along with its links.

    Repair can collide with a tag that already exists (``(bishop)`` and
    ``bishop``). Those are merged: every model on the damaged tag moves to the
    clean one, duplicates are dropped, and the damaged row is deleted.

    Pass ``dry_run=true`` to see the plan without writing anything.
    """
    import re

    from app.services.tagger import MIN_TAG_LENGTH

    db_path = _get_db_path(request)
    renamed: list[dict] = []
    merged: list[dict] = []
    dropped: list[str] = []

    async with open_db(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        cursor = await db.execute("SELECT id, name FROM tags")
        rows = [dict(r) for r in await cursor.fetchall()]
        by_name = {r["name"].lower(): r["id"] for r in rows}

        # A tag that already looks like a tag: letters and digits, optionally
        # joined by single hyphens or underscores. Left strictly alone.
        well_formed = re.compile(r"^[a-z0-9]+([-_][a-z0-9]+)*$")

        def repair(name: str) -> str:
            low = name.strip().lower()
            if well_formed.match(low):
                return low
            # A "(2)" or "[3]" is a copy suffix, not part of the name.
            low = re.sub(r"[([{]\s*\d*\s*[)\]}]", " ", low)
            # Everything else that is not a word character, hyphen or space is
            # filename punctuation; "+" is how model sites encode a space.
            low = re.sub(r"[^a-z0-9\-\s]+", " ", low)
            words = [w.strip("-") for w in low.split() if w.strip("-")]
            words = [w for w in words if len(w) >= MIN_TAG_LENGTH and not w.isdigit()]
            return words[0] if len(words) == 1 else ""

        for row in rows:
            original = row["name"]
            cleaned = repair(original)
            if cleaned == original.lower():
                continue

            if not cleaned:
                dropped.append(original)
                if not dry_run:
                    await db.execute("DELETE FROM model_tags WHERE tag_id = ?", (row["id"],))
                    await db.execute("DELETE FROM tags WHERE id = ?", (row["id"],))
                continue

            target_id = by_name.get(cleaned)
            if target_id is not None and target_id != row["id"]:
                merged.append({"from": original, "into": cleaned})
                if not dry_run:
                    await db.execute(
                        "UPDATE OR IGNORE model_tags SET tag_id = ? WHERE tag_id = ?",
                        (target_id, row["id"]),
                    )
                    await db.execute("DELETE FROM model_tags WHERE tag_id = ?", (row["id"],))
                    await db.execute("DELETE FROM tags WHERE id = ?", (row["id"],))
            else:
                renamed.append({"from": original, "to": cleaned})
                if not dry_run:
                    await db.execute(
                        "UPDATE tags SET name = ? WHERE id = ?", (cleaned, row["id"])
                    )
                    by_name[cleaned] = row["id"]

        if not dry_run:
            await db.commit()

    return {
        "dry_run": dry_run,
        "renamed": len(renamed),
        "merged": len(merged),
        "dropped": len(dropped),
        "detail": (
            f"{len(renamed)} renamed, {len(merged)} merged into an existing tag, "
            f"{len(dropped)} removed as unusable"
        ),
        "examples": {
            "renamed": renamed[:20],
            "merged": merged[:20],
            "dropped": dropped[:20],
        },
    }
