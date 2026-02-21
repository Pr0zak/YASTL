"""Tag suggestion service.

Generates tag suggestions for 3D models based on metadata:
- Filename words (split on separators, filter stop words)
- Category names from the model's category hierarchy
- File format as a tag
- Size classification based on dimensions (small/medium/large)
- Vertex count classification (low-poly/high-poly)
"""

import logging
import re

logger = logging.getLogger(__name__)

# Common stop words and noise to filter out when splitting filenames
STOP_WORDS: set[str] = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "is", "it", "by", "as", "with", "from", "that", "this", "be",
    "are", "was", "were", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should",
    "not", "no", "so", "if", "out", "up", "its",
    # Common file/3D noise words
    "file", "model", "stl", "obj", "gltf", "glb", "3mf", "ply", "step",
    "stp", "dae", "off", "fbx", "print", "3d", "final", "v1", "v2", "v3",
    "copy", "new", "old", "test", "tmp", "temp",
}

# Minimum tag length
MIN_TAG_LENGTH = 2

# Maximum number of suggestions to return
MAX_SUGGESTIONS = 15


def _split_filename(name: str) -> list[str]:
    """Split a filename stem into individual words.

    Handles:
    - snake_case, kebab-case, dot.separated
    - CamelCase splitting
    - Strips numbers-only tokens but keeps mixed (e.g. "mk2")
    """
    # Replace common separators with space
    s = re.sub(r"[_\-.\s]+", " ", name)

    # CamelCase split: insert space before uppercase sequences
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)

    words = []
    for w in s.split():
        w = w.strip().lower()
        # Skip pure numbers, too-short, and stop words
        if not w or len(w) < MIN_TAG_LENGTH:
            continue
        if w.isdigit():
            continue
        if w in STOP_WORDS:
            continue
        words.append(w)

    return words


def _classify_size(dims_x: float | None, dims_y: float | None, dims_z: float | None) -> str | None:
    """Classify model dimensions into a size tag.

    Uses the maximum extent in mm. Thresholds:
    - tiny: < 20mm
    - small: 20-80mm
    - medium: 80-200mm
    - large: > 200mm
    """
    vals = [d for d in (dims_x, dims_y, dims_z) if d is not None and d > 0]
    if not vals:
        return None
    max_dim = max(vals)
    if max_dim < 20:
        return "tiny"
    elif max_dim < 80:
        return "small"
    elif max_dim < 200:
        return "medium"
    else:
        return "large"


def _classify_complexity(vertex_count: int | None, face_count: int | None) -> str | None:
    """Classify mesh complexity.

    - low-poly: < 5,000 faces
    - mid-poly: 5,000-100,000 faces
    - high-poly: > 100,000 faces
    """
    count = face_count or vertex_count
    if count is None or count <= 0:
        return None
    if count < 5000:
        return "low-poly"
    elif count < 100000:
        return None  # mid-poly is too generic, skip
    else:
        return "high-poly"


def suggest_tags(model: dict) -> list[str]:
    """Generate tag suggestions for a model based on its metadata.

    Args:
        model: Dict with keys matching the models table columns, plus
               'tags' (existing tags), 'categories' (existing categories).

    Returns:
        Ordered list of suggested tag strings (not already on the model).
    """
    existing_tags = {t.lower() for t in (model.get("tags") or [])}
    suggestions: list[str] = []
    seen: set[str] = set()

    def _add(tag: str) -> None:
        tag = tag.strip().lower()
        if tag and len(tag) >= MIN_TAG_LENGTH and tag not in seen and tag not in existing_tags:
            seen.add(tag)
            suggestions.append(tag)

    # 1. Words from the model name / filename
    name = model.get("name") or ""
    for word in _split_filename(name):
        _add(word)

    # 2. Category names
    for cat in (model.get("categories") or []):
        for word in _split_filename(cat):
            _add(word)

    # 3. File format
    fmt = (model.get("file_format") or "").lower()
    if fmt and fmt not in STOP_WORDS:
        _add(fmt)

    # 4. Size classification
    size_tag = _classify_size(
        model.get("dimensions_x"),
        model.get("dimensions_y"),
        model.get("dimensions_z"),
    )
    if size_tag:
        _add(size_tag)

    # 5. Complexity classification
    complexity_tag = _classify_complexity(
        model.get("vertex_count"),
        model.get("face_count"),
    )
    if complexity_tag:
        _add(complexity_tag)

    # 6. Source site (from URL imports)
    source_url = model.get("source_url") or ""
    if "thingiverse" in source_url:
        _add("thingiverse")
    elif "printables" in source_url:
        _add("printables")
    elif "makerworld" in source_url:
        _add("makerworld")

    return suggestions[:MAX_SUGGESTIONS]
