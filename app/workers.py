"""Shared ProcessPoolExecutor for CPU-bound work.

Provides a process pool that bypasses the GIL, allowing CPU-bound operations
(thumbnail rendering, metadata extraction, file hashing) to run on multiple
cores simultaneously.

Usage::

    from app.workers import get_pool

    await loop.run_in_executor(get_pool(), some_cpu_bound_fn, arg1, arg2)

The pool is initialised at app startup via ``init_pool()`` and shut down
gracefully via ``shutdown_pool()`` — both called from the FastAPI lifespan
in ``main.py``.
"""

import logging
from concurrent.futures import ProcessPoolExecutor

logger = logging.getLogger("yastl")

_pool: ProcessPoolExecutor | None = None


def init_pool(max_workers: int = 2) -> None:
    """Create the shared process pool."""
    global _pool
    if _pool is not None:
        logger.warning("Process pool already initialised — skipping")
        return
    _pool = ProcessPoolExecutor(max_workers=max_workers)
    logger.info("Process pool started (max_workers=%d)", max_workers)


def get_pool() -> ProcessPoolExecutor | None:
    """Return the shared process pool (or None if not initialised)."""
    return _pool


def shutdown_pool() -> None:
    """Shut down the shared process pool."""
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False)
        logger.info("Process pool shut down")
        _pool = None
