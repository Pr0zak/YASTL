"""Mesh processing utilities for thumbnail generation.

Provides functions to collect meshes from trimesh objects (handling both
single Trimesh and Scene objects) and to simplify high-poly meshes via
quadric decimation for efficient thumbnail rendering.
"""

import logging

import numpy as np
import trimesh

logger = logging.getLogger(__name__)

# Maximum face count for thumbnail rendering. Meshes exceeding this are
# simplified via quadric decimation to avoid holes from face subsampling.
# Kept low so each projected triangle covers more pixels at 256x256.
_MAX_THUMBNAIL_FACES = 50000


def _collect_meshes(loaded: trimesh.Trimesh | trimesh.Scene) -> list[trimesh.Trimesh]:
    """Collect all Trimesh objects from a loaded model or scene.

    For Scene objects, applies scene graph transforms so multi-part models
    (e.g. 3MF assemblies) are properly positioned in world space.
    """
    meshes: list[trimesh.Trimesh] = []

    if isinstance(loaded, trimesh.Trimesh):
        meshes.append(loaded)
    elif isinstance(loaded, trimesh.Scene):
        try:
            # dump() returns geometry in world coordinates with transforms applied
            for geom in loaded.dump():
                if isinstance(geom, trimesh.Trimesh):
                    meshes.append(geom)
        except Exception:
            # Fallback: collect raw geometry without transforms
            for geometry in loaded.geometry.values():
                if isinstance(geometry, trimesh.Trimesh):
                    meshes.append(geometry)
    return meshes


def _simplify_mesh(mesh: trimesh.Trimesh, target_faces: int) -> trimesh.Trimesh:
    """Simplify a single mesh to the target face count.

    Uses fast_simplification (quadric decimation) if available, which
    preserves surface shape far better than randomly dropping faces.
    """
    if len(mesh.faces) <= target_faces:
        return mesh

    try:
        import fast_simplification
        reduction = 1.0 - (target_faces / len(mesh.faces))
        reduction = max(0.0, min(reduction, 0.99))
        verts_out, faces_out = fast_simplification.simplify(
            mesh.vertices.astype(np.float32),
            mesh.faces,
            target_reduction=reduction,
        )
        simplified = trimesh.Trimesh(vertices=verts_out, faces=faces_out, process=False)
        if len(simplified.faces) > 0:
            return simplified
    except ImportError:
        logger.debug("fast_simplification not installed, skipping mesh decimation")
    except Exception:
        logger.debug("Mesh simplification failed (%d faces), using original", len(mesh.faces))

    return mesh


def _simplify_for_thumbnail(meshes: list[trimesh.Trimesh]) -> list[trimesh.Trimesh]:
    """Decimate meshes that exceed the face budget for thumbnail rendering.

    Uses quadric decimation to reduce face count while preserving surface
    shape, which is far better than randomly dropping faces.
    """
    total_faces = sum(len(m.faces) for m in meshes)
    if total_faces <= _MAX_THUMBNAIL_FACES:
        return meshes

    # Compute per-mesh target proportional to its share of total faces
    ratio = _MAX_THUMBNAIL_FACES / total_faces
    return [_simplify_mesh(m, max(int(len(m.faces) * ratio), 100)) for m in meshes]
