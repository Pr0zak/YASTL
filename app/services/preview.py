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

# How much detail a preview keeps, and what that costs to produce and to load.
#
# Decimation time is driven mostly by the size of the mesh coming in, so a lower
# target saves less server time than it looks like it should. What it does save
# is everything after: bytes over the network and parse time in the browser,
# which is where a phone actually struggles. A 1.1M-face model here decimates to
# 500k in about 6 seconds and lands as a file several times the size of the same
# model at 150k.
#
# Only the 5% or so of a typical library above the threshold is affected at all;
# everything below it is served whole regardless of the setting.
PREVIEW_DETAIL_FACES: dict[str, int] = {
    "fast": 150_000,
    "balanced": 300_000,
    "detailed": DEFAULT_MAX_FACES,
}

PREVIEW_DETAIL_DEFAULT = "detailed"


def detail_max_faces(detail: str | None) -> int:
    """Face target for a detail level, falling back to the default."""
    return PREVIEW_DETAIL_FACES.get(
        detail or PREVIEW_DETAIL_DEFAULT, PREVIEW_DETAIL_FACES[PREVIEW_DETAIL_DEFAULT]
    )

# Bump when the preview generation changes — the face target, the attributes
# written, anything that alters the bytes — so cached GLBs regenerate instead of
# serving a stale version. Forgetting this is silent: the new code is deployed,
# the cache keeps answering, and the fix appears not to have worked.
#
# v3: normals are no longer written, so the client flat-shades instead of
#     rounding off every hard edge.
PREVIEW_CACHE_VERSION = 3


def preview_cache_name(model_id: int, detail: str | None = None) -> str:
    """Filename for a model's cached preview GLB (version- and detail-tagged).

    The detail level is part of the name, not just the version: changing the
    setting has to serve a differently decimated file, and a cache keyed only by
    version would keep answering with the previous one. Entries for other levels
    are left alone rather than deleted, so switching back is instant and the LRU
    eviction handles the rest.
    """
    level = detail or PREVIEW_DETAIL_DEFAULT
    if level not in PREVIEW_DETAIL_FACES:
        level = PREVIEW_DETAIL_DEFAULT
    return f"{model_id}.v{PREVIEW_CACHE_VERSION}-{level}.glb"


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

        # Do NOT touch mesh.vertex_normals here.
        #
        # Reading it makes trimesh average adjacent face normals at every shared
        # vertex, with no crease-angle threshold, and export the result as the
        # GLB's NORMAL attribute. On a hard-surface print model that is wrong by
        # a wide margin: measured on a real 10,768-face wall bracket, 89% of the
        # resulting normals pointed more than 30 degrees away from the face they
        # shaded, averaging 42 degrees. The mesh reads as soft and inflated —
        # the shading is describing a different surface from the geometry.
        #
        # Leaving NORMAL out entirely is both correct and cheaper. glTF requires
        # a client to flat-shade a primitive with no normals, which is what the
        # facets of a printed part actually look like and what YASTL already
        # shows for STL. It also drops a third of the file (259 KB -> 194 KB on
        # that bracket) and costs the GPU nothing, since it derives the normal
        # per fragment. An earlier comment here claimed baking them saved the
        # client an expensive computeVertexNormals; that call never ran for GLB.

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
        # No vertex_normals here either — see build_preview_glb above.
        return mesh.export(file_type="glb")
    finally:
        if scene is not None and hasattr(scene, "_cache"):
            try:
                scene._cache.clear()
            except Exception:  # noqa: BLE001
                pass
        del scene
        gc.collect()
