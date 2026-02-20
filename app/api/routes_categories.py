"""API routes for category management (tree-structured)."""

from fastapi import APIRouter, HTTPException, Request
import aiosqlite

router = APIRouter(prefix="/api/categories", tags=["categories"])


def _get_db_path(request: Request) -> str:
    """Retrieve the database path from FastAPI app state."""
    return request.app.state.db_path


# ---------------------------------------------------------------------------
# Helper: build a nested tree from flat category rows
# ---------------------------------------------------------------------------


def _build_tree(categories: list[dict]) -> list[dict]:
    """Convert a flat list of category dicts into a nested tree structure.

    Each category dict gets a ``children`` key containing its direct children.
    Returns only the root-level nodes (those with parent_id == None).
    """
    by_id: dict[int, dict] = {}
    for cat in categories:
        cat["children"] = []
        by_id[cat["id"]] = cat

    roots: list[dict] = []
    for cat in categories:
        parent_id = cat.get("parent_id")
        if parent_id is not None and parent_id in by_id:
            by_id[parent_id]["children"].append(cat)
        else:
            roots.append(cat)

    return roots


# ---------------------------------------------------------------------------
# List all categories as tree
# ---------------------------------------------------------------------------


@router.get("")
async def list_categories(request: Request):
    """List all categories as a nested tree structure.

    Categories with ``parent_id = NULL`` are returned as root nodes, with
    their descendants nested inside a ``children`` array.
    """
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT c.id, c.name, c.parent_id, COUNT(mc.model_id) as model_count
            FROM categories c
            LEFT JOIN model_categories mc ON mc.category_id = c.id
            GROUP BY c.id, c.name, c.parent_id
            ORDER BY c.name
            """
        )
        rows = await cursor.fetchall()

    categories = [dict(r) for r in rows]
    tree = _build_tree(categories)

    return {"categories": tree}


# ---------------------------------------------------------------------------
# Create category
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_category(request: Request):
    """Create a new category.

    Expects JSON body: {"name": "category_name", "parent_id": null}
    ``parent_id`` is optional; when omitted the category becomes a root node.
    """
    db_path = _get_db_path(request)
    body = await request.json()
    name = body.get("name")
    parent_id = body.get("parent_id")

    if not name or not isinstance(name, str) or not name.strip():
        raise HTTPException(
            status_code=400,
            detail="'name' is required and must be a non-empty string",
        )

    name = name.strip()

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # If a parent_id was provided, verify it exists
        if parent_id is not None:
            cursor = await db.execute(
                "SELECT id FROM categories WHERE id = ?", (parent_id,)
            )
            if await cursor.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Parent category {parent_id} not found",
                )

        # Check for duplicate (name + parent_id must be unique)
        cursor = await db.execute(
            """
            SELECT id FROM categories
            WHERE name = ? AND (parent_id IS ? OR parent_id = ?)
            """,
            (name, parent_id, parent_id),
        )
        if await cursor.fetchone() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Category '{name}' already exists under this parent",
            )

        cursor = await db.execute(
            "INSERT INTO categories (name, parent_id) VALUES (?, ?)",
            (name, parent_id),
        )
        category_id = cursor.lastrowid
        await db.commit()

    return {"id": category_id, "name": name, "parent_id": parent_id}


# ---------------------------------------------------------------------------
# Update category
# ---------------------------------------------------------------------------


@router.put("/{category_id}")
async def update_category(request: Request, category_id: int):
    """Update a category's name and/or parent_id.

    Expects JSON body with at least one of: {"name": "new_name", "parent_id": 123}
    Set ``parent_id`` to ``null`` to make the category a root node.
    """
    db_path = _get_db_path(request)
    body = await request.json()

    name = body.get("name")
    parent_id = body.get("parent_id", "__unset__")

    if name is None and parent_id == "__unset__":
        raise HTTPException(
            status_code=400,
            detail="At least one of 'name' or 'parent_id' is required",
        )

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Verify category exists
        cursor = await db.execute(
            "SELECT id, name, parent_id FROM categories WHERE id = ?",
            (category_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Category {category_id} not found"
            )

        current = dict(row)

        # Build dynamic UPDATE
        set_clauses: list[str] = []
        params: list = []

        if name is not None:
            name = name.strip()
            if not name:
                raise HTTPException(
                    status_code=400,
                    detail="'name' must be a non-empty string",
                )
            set_clauses.append("name = ?")
            params.append(name)

        if parent_id != "__unset__":
            # Prevent setting parent to self
            if parent_id == category_id:
                raise HTTPException(
                    status_code=400,
                    detail="A category cannot be its own parent",
                )

            # Verify new parent exists (if not null)
            if parent_id is not None:
                cursor = await db.execute(
                    "SELECT id FROM categories WHERE id = ?", (parent_id,)
                )
                if await cursor.fetchone() is None:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Parent category {parent_id} not found",
                    )

            set_clauses.append("parent_id = ?")
            params.append(parent_id)

        if not set_clauses:
            # Nothing to update, return current state
            return current

        params.append(category_id)
        await db.execute(
            f"UPDATE categories SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )
        await db.commit()

        # Fetch updated row
        cursor = await db.execute(
            "SELECT id, name, parent_id FROM categories WHERE id = ?",
            (category_id,),
        )
        updated = await cursor.fetchone()

    return dict(updated)


# ---------------------------------------------------------------------------
# Delete category
# ---------------------------------------------------------------------------


@router.delete("/{category_id}")
async def delete_category(request: Request, category_id: int):
    """Delete a category and reassign its children to its parent.

    Children of the deleted category are moved up to the deleted category's
    parent (or become root nodes if the deleted category had no parent).
    Model-category associations for the deleted category are also removed.
    """
    db_path = _get_db_path(request)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")

        # Verify category exists and get its parent
        cursor = await db.execute(
            "SELECT id, name, parent_id FROM categories WHERE id = ?",
            (category_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"Category {category_id} not found"
            )

        cat_dict = dict(row)
        parent_id = cat_dict["parent_id"]
        cat_name = cat_dict["name"]

        # Reassign children to the deleted category's parent
        await db.execute(
            "UPDATE categories SET parent_id = ? WHERE parent_id = ?",
            (parent_id, category_id),
        )

        # Remove model-category associations
        await db.execute(
            "DELETE FROM model_categories WHERE category_id = ?",
            (category_id,),
        )

        # Delete the category
        await db.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        await db.commit()

    return {"detail": f"Category '{cat_name}' (id={category_id}) deleted"}
