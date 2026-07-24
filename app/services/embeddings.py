"""In-memory semantic-search vector store (AI Phase 1).

Embeddings are persisted as float32 BLOBs in ``model_embeddings`` and mirrored
in a normalized numpy matrix held in the web process for fast brute-force cosine
search (~ms at tens of thousands of vectors, no SQLite extension needed).
Hybrid search fuses this with FTS5 via reciprocal rank fusion.
"""

import hashlib
import logging
import posixpath
from collections import Counter

import numpy as np

logger = logging.getLogger("yastl")

# ---- Module-level store (single web/event-loop process) ----
_ids: list[int] = []
_id_to_row: dict[int, int] = {}
_matrix: np.ndarray | None = None  # (N, dim) L2-normalized float32
_dim: int | None = None


def is_ready() -> bool:
    return _matrix is not None and len(_ids) > 0


def count() -> int:
    return len(_ids)


def current_dim() -> int | None:
    return _dim


# ---- (de)serialization ----
def pack_vec(vec) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def unpack_vec(blob: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32, count=dim).astype(np.float32)


# ---- text composition + staleness ----
def compose_text(model: dict, tags: list[str] | None = None) -> str:
    """Build the text embedded for a model: name + folder + tags + description.

    The folder segments are where searches like "articulated dragon" match a
    file literally named ``dragon_v2_final.stl`` inside ``.../Articulated Dragons/``.
    """
    parts: list[str] = []
    name = (model.get("name") or "").strip()
    if name:
        parts.append(name)
    path = (model.get("file_path") or model.get("zip_entry") or "").replace("\\", "/")
    folder = posixpath.dirname(path)
    segs = [s for s in folder.split("/") if s][-2:]
    if segs:
        parts.append("Folder: " + " / ".join(segs))
    tag_list = tags if tags is not None else (model.get("tags") or [])
    if tag_list:
        parts.append("Tags: " + ", ".join(tag_list))
    desc = (model.get("description") or "").strip()
    if desc:
        parts.append(desc)
    return "\n".join(parts)[:2000]


def source_hash(text: str, embed_model: str) -> str:
    """Hash of (embed_model, text) — changes when either the text or the
    embedding model changes, so stale vectors can be detected and refreshed."""
    return hashlib.sha256(f"{embed_model}\x00{text}".encode("utf-8")).hexdigest()


# ---- store management ----
def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (m / norms).astype(np.float32)


def set_store(ids: list[int], matrix: np.ndarray | None, dim: int | None) -> None:
    global _ids, _id_to_row, _matrix, _dim
    _ids = list(ids)
    _id_to_row = {mid: i for i, mid in enumerate(_ids)}
    _matrix = matrix
    _dim = dim


def clear() -> None:
    set_store([], None, None)


async def load_matrix_from_db(db) -> None:
    """Load all stored embeddings into the in-memory matrix (call at startup and
    after a backfill). Handles a transient mix of dims (after an embed-model
    switch) by keeping only the majority dimension."""
    cursor = await db.execute("SELECT model_id, embedding, dim FROM model_embeddings")
    rows = [dict(r) for r in await cursor.fetchall()]
    if not rows:
        clear()
        return
    dim = Counter(r["dim"] for r in rows).most_common(1)[0][0]
    kept = [r for r in rows if r["dim"] == dim]
    ids = [r["model_id"] for r in kept]
    mat = np.stack([unpack_vec(r["embedding"], dim) for r in kept]).astype(np.float32)
    set_store(ids, _normalize(mat), dim)
    skipped = len(rows) - len(kept)
    logger.info(
        "Embeddings: loaded %d vectors (dim=%d) into memory%s",
        len(ids), dim, f"; skipped {skipped} stale-dim" if skipped else "",
    )


# ---- search ----
def search(query_vec, k: int = 100) -> list[int]:
    """Return up to k model_ids most cosine-similar to query_vec (best first)."""
    if not is_ready():
        return []
    q = np.asarray(query_vec, dtype=np.float32)
    if q.ndim != 1 or q.shape[0] != _dim:
        return []
    n = np.linalg.norm(q)
    if n:
        q = q / n
    sims = _matrix @ q
    k = min(k, len(_ids))
    if k <= 0:
        return []
    top = np.argpartition(-sims, k - 1)[:k]
    top = top[np.argsort(-sims[top])]
    return [_ids[int(i)] for i in top]


def rrf_fuse(*ranked_lists: list[int], k: int = 60) -> list[int]:
    """Reciprocal rank fusion: combine ranked id lists by rank, not score.

    RRF_score(id) = sum over lists of 1 / (k + rank_in_list). Sidesteps the
    incomparable scales of BM25 vs cosine. Missing from a list contributes 0.
    """
    scores: dict[int, float] = {}
    for lst in ranked_lists:
        for rank, mid in enumerate(lst):
            scores[mid] = scores.get(mid, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda m: scores[m], reverse=True)
