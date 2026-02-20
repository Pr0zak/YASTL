"""
3D file metadata extraction service.

Uses trimesh to load 3D files and extract geometric metadata such as
vertex count, face count, bounding box dimensions, and file format.
"""

import logging
import os
from pathlib import Path

import trimesh

logger = logging.getLogger(__name__)

# Mapping of file extensions to canonical format names
FORMAT_MAP: dict[str, str] = {
    ".stl": "STL",
    ".obj": "OBJ",
    ".gltf": "glTF",
    ".glb": "GLB",
    ".3mf": "3MF",
    ".ply": "PLY",
    ".dae": "DAE",
    ".off": "OFF",
    ".step": "STEP",
    ".stp": "STEP",
    ".fbx": "FBX",
}

# Extensions that trimesh can load natively
TRIMESH_SUPPORTED: set[str] = {
    ".stl", ".obj", ".gltf", ".glb", ".3mf",
    ".ply", ".dae", ".off", ".fbx",
}

# Extensions that require special handling / fallback
FALLBACK_ONLY: set[str] = {
    ".step", ".stp",
}


def _extract_mesh_metadata(mesh: trimesh.Trimesh) -> dict:
    """Extract metadata from a single trimesh.Trimesh object."""
    bounds = mesh.bounds  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]
    dimensions = bounds[1] - bounds[0]

    return {
        "vertex_count": int(mesh.vertices.shape[0]),
        "face_count": int(mesh.faces.shape[0]),
        "dimensions_x": float(round(dimensions[0], 6)),
        "dimensions_y": float(round(dimensions[1], 6)),
        "dimensions_z": float(round(dimensions[2], 6)),
    }


def _extract_scene_metadata(scene: trimesh.Scene) -> dict:
    """Extract aggregated metadata from a trimesh.Scene containing multiple geometries."""
    total_vertices = 0
    total_faces = 0

    for geometry in scene.geometry.values():
        if isinstance(geometry, trimesh.Trimesh):
            total_vertices += int(geometry.vertices.shape[0])
            total_faces += int(geometry.faces.shape[0])
        elif hasattr(geometry, "vertices"):
            total_vertices += int(len(geometry.vertices))

    # Use the scene's overall bounding box
    try:
        bounds = scene.bounds  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]
        dimensions = bounds[1] - bounds[0]
        dims = {
            "dimensions_x": float(round(dimensions[0], 6)),
            "dimensions_y": float(round(dimensions[1], 6)),
            "dimensions_z": float(round(dimensions[2], 6)),
        }
    except Exception:
        logger.debug("Could not compute scene bounding box")
        dims = {
            "dimensions_x": None,
            "dimensions_y": None,
            "dimensions_z": None,
        }

    return {
        "vertex_count": total_vertices,
        "face_count": total_faces,
        **dims,
    }


def extract_metadata(file_path: str) -> dict:
    """
    Extract metadata from a 3D model file.

    Loads the file with trimesh and extracts geometric information including
    vertex count, face count, bounding box dimensions, file size, and format.

    For STEP/STP files, attempts trimesh first and falls back to basic file info
    if parsing fails.

    Args:
        file_path: Absolute path to the 3D model file.

    Returns:
        A dictionary containing extracted metadata. Keys include:
            - file_path (str): The original file path
            - file_format (str): Canonical format name (e.g. "STL", "OBJ")
            - file_size (int): File size in bytes
            - vertex_count (int | None): Number of vertices
            - face_count (int | None): Number of faces
            - dimensions_x (float | None): Bounding box X extent
            - dimensions_y (float | None): Bounding box Y extent
            - dimensions_z (float | None): Bounding box Z extent
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    # Base metadata that is always available
    metadata: dict = {
        "file_path": str(path),
        "file_format": FORMAT_MAP.get(ext, ext.lstrip(".").upper()),
        "file_size": None,
        "vertex_count": None,
        "face_count": None,
        "dimensions_x": None,
        "dimensions_y": None,
        "dimensions_z": None,
    }

    # File size
    try:
        metadata["file_size"] = os.path.getsize(file_path)
    except OSError as e:
        logger.warning("Could not determine file size for %s: %s", file_path, e)

    # Check if the format is recognized at all
    all_known = TRIMESH_SUPPORTED | FALLBACK_ONLY
    if ext not in all_known:
        logger.warning(
            "Unsupported or unrecognized 3D format '%s' for file: %s",
            ext,
            file_path,
        )
        return metadata

    # Attempt to load with trimesh
    try:
        logger.debug("Loading 3D file with trimesh: %s", file_path)
        loaded = trimesh.load(file_path, force=None)

        if isinstance(loaded, trimesh.Trimesh):
            mesh_meta = _extract_mesh_metadata(loaded)
            metadata.update(mesh_meta)
            logger.debug(
                "Extracted mesh metadata for %s: %d verts, %d faces",
                path.name,
                mesh_meta["vertex_count"],
                mesh_meta["face_count"],
            )
        elif isinstance(loaded, trimesh.Scene):
            scene_meta = _extract_scene_metadata(loaded)
            metadata.update(scene_meta)
            logger.debug(
                "Extracted scene metadata for %s: %d verts, %d faces across %d geometries",
                path.name,
                scene_meta["vertex_count"],
                scene_meta["face_count"],
                len(loaded.geometry),
            )
        else:
            logger.warning(
                "trimesh returned unexpected type %s for file: %s",
                type(loaded).__name__,
                file_path,
            )
    except Exception as e:
        if ext in FALLBACK_ONLY:
            logger.debug(
                "trimesh could not parse STEP/STP file %s (expected): %s. "
                "Returning basic file info only.",
                file_path,
                e,
            )
        else:
            logger.warning(
                "Failed to extract mesh data from %s: %s. Returning partial metadata.",
                file_path,
                e,
            )

    return metadata
