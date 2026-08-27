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

# Target triangle budget for the interactive preview. Higher = more detail;
# a ~500k GLB still parses in a few hundred ms on the main thread and stays
# reasonably small, and previews look much closer to the full mesh.
DEFAULT_MAX_FACES = 500_000

# Bump when the preview generation changes (e.g. face target) so cached
# GLBs regenerate instead of serving a stale, lower-detail version.
PREVIEW_CACHE_VERSION = 2


def preview_cache_name(model_id: int) -> str:
    """Filename for a model's cached preview GLB (version-tagged)."""
    return f"{model_id}.v{PREVIEW_CACHE_VERSION}.glb"


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


def _object_id_to_names(file_path: str) -> dict:
    """Map 3MF object id -> object name from 3D/3dmodel.model (trimesh geometry
    names may be de-duplicated, so build the id->name bridge from the raw XML)."""
    import xml.etree.ElementTree as ET
    import zipfile

    core = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
    out: dict[int, str] = {}
    try:
        with zipfile.ZipFile(file_path) as z:
            root = ET.fromstring(z.read("3D/3dmodel.model"))
            resources = root.find(f"{core}resources")
            if resources is not None:
                for obj in resources.findall(f"{core}object"):
                    oid = obj.get("id")
                    if oid and oid.isdigit():
                        out[int(oid)] = obj.get("name") or oid
    except Exception:  # noqa: BLE001 - best effort
        pass
    return out


def build_plate_glb(file_path: str, object_ids: list[int],
                    max_faces: int = DEFAULT_MAX_FACES) -> bytes:
    """Build a decimated GLB containing only the given 3MF object ids (one build
    plate), with instance transforms applied. Falls back to the whole model when
    the object->geometry mapping can't be resolved. Runs in a pool worker."""
    scene = None
    try:
        loaded = trimesh.load(file_path, force=None)
        if not isinstance(loaded, trimesh.Scene):
            # Single-mesh 3MF — nothing to split; return the whole thing.
            return build_preview_glb(file_path, max_faces)
        scene = loaded
        id2name = _object_id_to_names(file_path)
        want = {id2name[o] for o in (object_ids or []) if o in id2name}

        # `scene` is passed in rather than closed over: the finally block below
        # deletes it, and a closure that reads a deleted enclosing local is a
        # NameError waiting for someone to move the call site.
        def _collect(src, match_all: bool):
            out = []
            for node in src.graph.nodes_geometry:
                transform, gname = src.graph[node]
                base = gname.rsplit("_", 1)[0]
                hit = match_all or gname in want or base in want or gname.split(".")[0] in want
                if hit:
                    geom = src.geometry.get(gname)
                    if geom is not None and hasattr(geom, "faces"):
                        gm = geom.copy()
                        try:
                            gm.apply_transform(transform)
                        except Exception:  # noqa: BLE001
                            pass
                        out.append(gm)
            return out

        kept = _collect(scene, match_all=not want)
        if want and not kept:
            # Mapping failed for this file — show the whole project rather than
            # nothing (real Bambu files should map; synthetic/edge cases fall back).
            kept = _collect(scene, match_all=True)
        if not kept:
            raise ValueError("no mesh geometry for plate")

        mesh = kept[0] if len(kept) == 1 else trimesh.util.concatenate(tuple(kept))
        if hasattr(mesh, "faces") and len(mesh.faces) > max_faces:
            try:
                mesh = mesh.simplify_quadric_decimation(face_count=max_faces)
            except Exception:  # noqa: BLE001 - keep full on failure
                pass
        try:
            _ = mesh.vertex_normals
        except Exception:  # noqa: BLE001
            pass
        return mesh.export(file_type="glb")
    finally:
        if scene is not None and hasattr(scene, "_cache"):
            try:
                scene._cache.clear()
            except Exception:  # noqa: BLE001
                pass
        del scene
        gc.collect()
