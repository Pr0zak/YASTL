"""Build decimated GLB previews for the interactive 3D viewer.

Large meshes freeze the browser: the client parses the raw mesh and
computes vertex normals on the main thread. Serving a decimated GLB
(fewer triangles, normals baked in) makes the transfer small and the
client-side parse trivial, so the viewer never blocks.

``build_preview_glb`` is a module-level function so it can run in the
shared ProcessPoolExecutor via ``workers.run_cpu_job`` — the same
OOM-protected path the scanner uses.
"""

import gc
import logging

import trimesh

logger = logging.getLogger("yastl")

# Target triangle budget for the interactive preview. ~200k triangles
# parse in well under 100 ms on the main thread and keep the GLB small.
DEFAULT_MAX_FACES = 200_000


def _as_single_mesh(loaded, file_path: str):
    """Return a single Trimesh from a load result (concatenating scenes)."""
    if isinstance(loaded, trimesh.Trimesh):
        return loaded
    if isinstance(loaded, trimesh.Scene):
        geoms = [g for g in loaded.geometry.values() if hasattr(g, "faces")]
        if not geoms:
            raise ValueError("scene has no mesh geometry")
        if len(geoms) == 1:
            return geoms[0]
        return trimesh.util.concatenate(tuple(geoms))
    raise ValueError(f"unsupported load type {type(loaded).__name__}")


def build_preview_glb(file_path: str, max_faces: int = DEFAULT_MAX_FACES) -> bytes:
    """Load ``file_path``, decimate if it exceeds ``max_faces``, return GLB bytes.

    Raises on unloadable input. Runs in a pool worker.
    """
    loaded = None
    load_err = None
    try:
        # Retry once: reads can fail transiently (NFS hiccups) and a load
        # can raise MemoryError if the worker is near RLIMIT_AS.
        for _ in range(2):
            try:
                loaded = trimesh.load(file_path, force=None)
                load_err = None
                break
            except Exception as e:  # noqa: BLE001 - retried / surfaced below
                load_err = e
                loaded = None

        if loaded is None or (
            isinstance(loaded, trimesh.Scene) and len(loaded.geometry) == 0
        ):
            from app.services.step_converter import is_step_file, load_step

            if is_step_file(file_path):
                mesh = load_step(file_path)
                if mesh is not None:
                    loaded = mesh

        if loaded is None:
            # Surface the underlying cause instead of a generic message so
            # failures (MemoryError, OSError, parse errors) are diagnosable.
            raise ValueError(
                f"Cannot load file for preview: {file_path}"
                + (f" ({type(load_err).__name__}: {load_err})" if load_err else "")
            ) from load_err

        mesh = _as_single_mesh(loaded, file_path)

        if hasattr(mesh, "faces") and len(mesh.faces) > max_faces:
            original = len(mesh.faces)
            try:
                mesh = mesh.simplify_quadric_decimation(face_count=max_faces)
                logger.info(
                    "Decimated preview %s: %d -> %d faces",
                    file_path, original, len(mesh.faces),
                )
            except Exception as e:  # noqa: BLE001 - keep full mesh on failure
                logger.warning(
                    "Decimation failed for %s (%d faces), serving full: %s",
                    file_path, original, e,
                )

        # Access vertex_normals so they bake into the GLB — the client then
        # skips its own (expensive, main-thread) computeVertexNormals.
        try:
            _ = mesh.vertex_normals
        except Exception:  # noqa: BLE001 - normals are best-effort
            pass

        return mesh.export(file_type="glb")
    finally:
        if loaded is not None:
            if hasattr(loaded, "_cache"):
                try:
                    loaded._cache.clear()
                except Exception:  # noqa: BLE001
                    pass
            del loaded
        gc.collect()
