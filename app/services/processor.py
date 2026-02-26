"""
3D file metadata extraction service.

Uses trimesh to load 3D files and extract geometric metadata such as
vertex count, face count, bounding box dimensions, and file format.
"""

import gc
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
    loaded = None
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
                "Trying dedicated STEP converter.",
                file_path,
                e,
            )
            # Try the dedicated STEP converter
            mesh = None
            try:
                from app.services.step_converter import load_step

                mesh = load_step(file_path)
                if mesh is not None and isinstance(mesh, trimesh.Trimesh):
                    mesh_meta = _extract_mesh_metadata(mesh)
                    metadata.update(mesh_meta)
                    logger.debug(
                        "STEP converter extracted metadata for %s: %d verts, %d faces",
                        path.name,
                        mesh_meta["vertex_count"],
                        mesh_meta["face_count"],
                    )
                else:
                    logger.debug(
                        "STEP converter unavailable or failed for %s. "
                        "Returning basic file info only.",
                        file_path,
                    )
            except Exception as conv_err:
                logger.debug(
                    "STEP converter failed for %s: %s", file_path, conv_err
                )
            finally:
                del mesh
        else:
            logger.warning(
                "Failed to extract mesh data from %s: %s. Returning partial metadata.",
                file_path,
                e,
            )
    finally:
        # Explicitly free trimesh objects and numpy arrays to prevent
        # memory accumulation in the long-running worker process.
        if loaded is not None:
            if hasattr(loaded, '_cache'):
                loaded._cache.clear()
            if isinstance(loaded, trimesh.Scene):
                for geom in loaded.geometry.values():
                    if hasattr(geom, '_cache'):
                        geom._cache.clear()
            del loaded
        gc.collect()

    return metadata


def process_and_thumbnail(
    file_path: str,
    output_dir: str,
    model_id: int,
    render_mode: str = "wireframe",
    render_quality: str = "fast",
    skip_thumbnail: bool = False,
) -> dict:
    """Extract metadata and generate thumbnail from a single trimesh.load().

    Combines the work of ``extract_metadata()`` and
    ``thumbnail.generate_thumbnail()`` into one load to halve peak memory
    usage in the scanner worker process.

    Returns:
        ``{"metadata": dict, "thumbnail_filename": str | None}``
    """
    from pathlib import Path as _Path

    from app.services.thumbnail_mesh import _collect_meshes
    from app.services.thumbnail_render import (
        _try_trimesh_render,
        _render_wireframe,
        _render_solid,
        _render_solid_fast,
    )

    path = _Path(file_path)
    ext = path.suffix.lower()

    # ---- base metadata (no trimesh needed) ----
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

    try:
        metadata["file_size"] = os.path.getsize(file_path)
    except OSError as e:
        logger.warning("Could not determine file size for %s: %s", file_path, e)

    thumb_filename: str | None = None
    all_known = TRIMESH_SUPPORTED | FALLBACK_ONLY
    if ext not in all_known:
        logger.warning(
            "Unsupported or unrecognized 3D format '%s' for file: %s", ext, file_path
        )
        return {"metadata": metadata, "thumbnail_filename": None}

    # ---- single trimesh load ----
    loaded = None
    scene = None
    meshes = None
    try:
        logger.debug("Combined load (metadata+thumb) for: %s", file_path)
        loaded = trimesh.load(file_path, force=None)

        # --- extract metadata from loaded object ---
        if isinstance(loaded, trimesh.Trimesh):
            metadata.update(_extract_mesh_metadata(loaded))
        elif isinstance(loaded, trimesh.Scene):
            metadata.update(_extract_scene_metadata(loaded))
        else:
            logger.warning(
                "trimesh returned unexpected type %s for file: %s",
                type(loaded).__name__, file_path,
            )

        # --- generate thumbnail from same loaded object ---
        if not skip_thumbnail and loaded is not None:
            output_dir_path = _Path(output_dir)
            output_filename = f"{model_id}.png"
            output_path = output_dir_path / output_filename

            try:
                output_dir_path.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

            # Build scene wrapper for trimesh native render
            if isinstance(loaded, trimesh.Trimesh):
                scene = trimesh.Scene(loaded)
            elif isinstance(loaded, trimesh.Scene):
                scene = loaded

            rendered = False
            if scene is not None and len(scene.geometry) > 0:
                # Try trimesh built-in render
                if render_mode == "wireframe" and _try_trimesh_render(scene, str(output_path)):
                    rendered = True
                    thumb_filename = output_filename

                if not rendered:
                    meshes = _collect_meshes(loaded)
                    if meshes:
                        if render_mode == "solid":
                            solid_fn = _render_solid if render_quality == "quality" else _render_solid_fast
                            if solid_fn(meshes, str(output_path)):
                                rendered = True
                                thumb_filename = output_filename
                        if not rendered and _render_wireframe(meshes, str(output_path)):
                            rendered = True
                            thumb_filename = output_filename

            if not rendered:
                logger.debug("Thumbnail rendering failed for: %s", file_path)

    except Exception as e:
        # Handle STEP/STP fallback
        if ext in FALLBACK_ONLY:
            logger.debug(
                "trimesh could not parse STEP/STP file %s: %s. Trying STEP converter.",
                file_path, e,
            )
            step_mesh = None
            try:
                from app.services.step_converter import load_step

                step_mesh = load_step(file_path)
                if step_mesh is not None and isinstance(step_mesh, trimesh.Trimesh):
                    metadata.update(_extract_mesh_metadata(step_mesh))

                    # Also generate thumbnail from STEP mesh
                    if not skip_thumbnail:
                        output_dir_path = _Path(output_dir)
                        output_filename = f"{model_id}.png"
                        output_path = output_dir_path / output_filename
                        try:
                            output_dir_path.mkdir(parents=True, exist_ok=True)
                        except OSError:
                            pass
                        step_meshes = [step_mesh]
                        if render_mode == "solid":
                            solid_fn = _render_solid if render_quality == "quality" else _render_solid_fast
                            if solid_fn(step_meshes, str(output_path)):
                                thumb_filename = output_filename
                        if thumb_filename is None and _render_wireframe(step_meshes, str(output_path)):
                            thumb_filename = output_filename
            except Exception as conv_err:
                logger.debug("STEP converter failed for %s: %s", file_path, conv_err)
            finally:
                del step_mesh
        else:
            logger.warning(
                "Failed to process %s: %s. Returning partial metadata.",
                file_path, e,
            )
    finally:
        if loaded is not None:
            if hasattr(loaded, "_cache"):
                loaded._cache.clear()
            if isinstance(loaded, trimesh.Scene):
                for geom in loaded.geometry.values():
                    if hasattr(geom, "_cache"):
                        geom._cache.clear()
        del loaded, scene, meshes
        gc.collect()

    return {"metadata": metadata, "thumbnail_filename": thumb_filename}
