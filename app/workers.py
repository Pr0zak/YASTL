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

Worker processes accumulate memory over time (trimesh, numpy arrays, etc.)
because Python's allocator doesn't return freed memory to the OS.  To prevent
OOM on memory-constrained hosts, call ``recycle_pool()`` periodically (e.g.
every 50 models during scans/thumbnail regen) or use ``maybe_recycle()``
which tracks job count automatically.
"""

import logging
import os
import resource
from concurrent.futures import ProcessPoolExecutor

logger = logging.getLogger("yastl")

_pool: ProcessPoolExecutor | None = None
_max_workers: int = 1

# Memory limit for each worker process (in MB).  When a worker exceeds
# this limit the OS kills it with SIGKILL, which surfaces as a
# BrokenProcessPool exception that callers can catch and recover from.
# Set to ~60% of container RAM to leave room for the main process and OS.
_WORKER_MEMORY_LIMIT_MB: int = 4096  # 4 GB

# Worker recycling: track how many CPU-bound jobs have been dispatched
# and recycle the pool after a threshold to shed accumulated memory.
_job_count: int = 0
_RECYCLE_EVERY: int = 25  # recycle worker after this many jobs


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


def _worker_init() -> None:
    """Initializer run in each worker process to set memory limits."""
    limit_bytes = _WORKER_MEMORY_LIMIT_MB * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
    except (ValueError, OSError):
        pass  # some systems don't support RLIMIT_AS


def init_pool(max_workers: int = 1) -> None:
    """Create the shared process pool."""
    global _pool, _max_workers, _job_count
    if _pool is not None:
        logger.warning("Process pool already initialised — skipping")
        return
    _max_workers = max_workers
    _job_count = 0
    _pool = ProcessPoolExecutor(
        max_workers=max_workers, initializer=_worker_init,
    )
    logger.info(
        "Process pool started (max_workers=%d, worker_mem_limit=%dMB)",
        max_workers,
        _WORKER_MEMORY_LIMIT_MB,
    )
    log_memory("pool_init")


def get_pool() -> ProcessPoolExecutor | None:
    """Return the shared process pool (or None if not initialised)."""
    return _pool


def recycle_pool() -> None:
    """Shut down the current pool and create a fresh one.

    This kills the worker process(es), releasing all accumulated memory
    back to the OS (numpy arrays, trimesh caches, etc.).  The new pool
    starts with a clean worker that only loads ~300 MB on first use.
    """
    global _pool, _job_count
    if _pool is None:
        return
    log_memory("recycle_before")
    _pool.shutdown(wait=True)
    _pool = ProcessPoolExecutor(
        max_workers=_max_workers, initializer=_worker_init,
    )
    _job_count = 0
    logger.info("Process pool recycled (max_workers=%d)", _max_workers)
    log_memory("recycle_after")


def tick_job() -> None:
    """Increment the job counter.  Called after each CPU-bound job completes."""
    global _job_count
    _job_count += 1


def maybe_recycle() -> None:
    """Recycle the pool if the job counter has reached the threshold.

    Call this after each CPU-bound job (metadata extraction, thumbnail
    generation, hashing) to automatically shed accumulated memory.
    """
    if _job_count >= _RECYCLE_EVERY:
        recycle_pool()


def recover_pool() -> None:
    """Replace a broken pool with a fresh one.

    Called when a ``BrokenProcessPool`` exception indicates the worker
    was killed (e.g. by RLIMIT_AS or OOM killer).
    """
    global _pool, _job_count
    logger.warning("Worker process crashed — recreating pool")
    try:
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass
    _pool = ProcessPoolExecutor(
        max_workers=_max_workers, initializer=_worker_init,
    )
    _job_count = 0
    log_memory("pool_recover")


def shutdown_pool() -> None:
    """Shut down the shared process pool."""
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False)
        logger.info("Process pool shut down")
        _pool = None
