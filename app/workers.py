"""Shared ProcessPoolExecutor for CPU-bound work.

Provides a process pool that bypasses the GIL, allowing CPU-bound operations
(thumbnail rendering, metadata extraction, file hashing) to run on a separate
core from the asyncio event loop.

Usage::

    from app.workers import get_pool

    await loop.run_in_executor(get_pool(), some_cpu_bound_fn, arg1, arg2)

The pool is initialised at app startup via ``init_pool()`` and shut down
gracefully via ``shutdown_pool()`` — both called from the FastAPI lifespan
in ``main.py``.
"""

import logging
import os
import resource
from concurrent.futures import ProcessPoolExecutor

logger = logging.getLogger("yastl")

_pool: ProcessPoolExecutor | None = None


def _get_memory_mb() -> float:
    """Return current process RSS in MB (Linux only)."""
    try:
        # maxrss is in KB on Linux
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        return 0.0


def _get_system_memory_mb() -> dict[str, float]:
    """Read /proc/meminfo and return available/total in MB."""
    try:
        info: dict[str, float] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if parts[0] == "MemTotal:":
                    info["total"] = int(parts[1]) / 1024
                elif parts[0] == "MemAvailable:":
                    info["available"] = int(parts[1]) / 1024
                elif parts[0] == "SwapTotal:":
                    info["swap_total"] = int(parts[1]) / 1024
                elif parts[0] == "SwapFree:":
                    info["swap_free"] = int(parts[1]) / 1024
        return info
    except Exception:
        return {}


def log_memory(context: str = "") -> None:
    """Log current memory usage for diagnostics."""
    rss = _get_memory_mb()
    sys_mem = _get_system_memory_mb()
    parts = [f"pid={os.getpid()} RSS={rss:.0f}MB"]
    if sys_mem:
        avail = sys_mem.get("available", 0)
        total = sys_mem.get("total", 0)
        swap_used = sys_mem.get("swap_total", 0) - sys_mem.get("swap_free", 0)
        parts.append(f"system={total:.0f}MB avail={avail:.0f}MB swap_used={swap_used:.0f}MB")
    prefix = f"[{context}] " if context else ""
    logger.info("%sMemory: %s", prefix, ", ".join(parts))


def init_pool(max_workers: int = 1) -> None:
    """Create the shared process pool."""
    global _pool
    if _pool is not None:
        logger.warning("Process pool already initialised — skipping")
        return
    _pool = ProcessPoolExecutor(max_workers=max_workers)
    logger.info("Process pool started (max_workers=%d)", max_workers)
    log_memory("pool_init")


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
