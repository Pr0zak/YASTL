"""
Server-side thumbnail generation for 3D model files.

Uses trimesh to load meshes and render preview images. Falls back to a
simple wireframe rendering with Pillow when trimesh's built-in rendering
(which depends on pyrender/pyglet) is unavailable.
"""

import logging
from pathlib import Path

import trimesh

from app.services.thumbnail_mesh import _collect_meshes, _simplify_for_thumbnail  # noqa: F401
from app.services.thumbnail_render import (  # noqa: F401
    THUMBNAIL_WIDTH,
    THUMBNAIL_HEIGHT,
    _try_trimesh_render,
    _render_wireframe,
    _render_solid,
    _render_solid_fast,
)

logger = logging.getLogger(__name__)


def generate_thumbnail(
    file_path: str,
    output_dir: str,
    model_id: int,
    render_mode: str = "wireframe",
    render_quality: str = "fast",
) -> str | None:
    """
    Generate a 256x256 PNG thumbnail for a 3D model file.

    Attempts to render using trimesh's built-in rendering first. If that fails
    (common in headless environments without pyrender), falls back to a
    Pillow-based rendering using the specified *render_mode* and *render_quality*.

    Args:
        file_path: Absolute path to the 3D model file.
        output_dir: Directory where thumbnails should be saved.
        model_id: Unique ID for the model, used as the output filename.
        render_mode: ``"wireframe"`` (default) or ``"solid"``.
        render_quality: ``"fast"`` (Pillow painter's algorithm) or
            ``"quality"`` (numpy z-buffer with Gouraud shading).

    Returns:
        Relative path to the generated thumbnail (e.g. "42.png"),
        or None if thumbnail generation fails entirely.
    """
    output_dir_path = Path(output_dir)
    output_filename = f"{model_id}.png"
    output_path = output_dir_path / output_filename

    # Ensure the output directory exists
    try:
        output_dir_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("Could not create thumbnail directory %s: %s", output_dir, e)
        return None

    # Load the 3D file
    try:
        loaded = trimesh.load(file_path, force=None)
    except Exception as e:
        # For STEP/STP files, try the dedicated converter
        from app.services.step_converter import is_step_file, load_step

        if is_step_file(file_path):
            logger.debug(
                "trimesh could not load STEP file %s, trying step converter", file_path
            )
            mesh = load_step(file_path)
            if mesh is not None:
                loaded = mesh
            else:
                logger.warning(
                    "Could not load STEP file for thumbnail: %s: %s", file_path, e
                )
                return None
        else:
            logger.warning(
                "Could not load 3D file for thumbnail: %s: %s", file_path, e
            )
            return None

    # Ensure we have a Scene for trimesh rendering attempt
    if isinstance(loaded, trimesh.Trimesh):
        scene = trimesh.Scene(loaded)
    elif isinstance(loaded, trimesh.Scene):
        scene = loaded
    else:
        logger.warning(
            "Unexpected trimesh type %s for thumbnail: %s",
            type(loaded).__name__,
            file_path,
        )
        return None

    # Check for empty scene
    if len(scene.geometry) == 0:
        logger.warning("Empty scene (no geometry) in file: %s", file_path)
        return None

    # Strategy 1: Try trimesh's built-in rendering (needs pyrender/pyglet)
    # Only attempt for wireframe mode -- the built-in renderer produces its own
    # shaded output which is effectively "solid", but we want consistent
    # user-controlled rendering when solid mode is explicitly chosen.
    if render_mode == "wireframe" and _try_trimesh_render(scene, str(output_path)):
        return output_filename

    # Strategy 2: Pillow-based rendering (wireframe or solid)
    logger.debug(
        "Rendering %s thumbnail for: %s", render_mode, file_path
    )
    meshes = _collect_meshes(loaded)

    if not meshes:
        logger.warning("No renderable meshes found in: %s", file_path)
        return None

    if render_mode == "solid":
        solid_fn = _render_solid if render_quality == "quality" else _render_solid_fast
        if solid_fn(meshes, str(output_path)):
            return output_filename
        # Fall back to wireframe if solid fails (e.g. no faces)
        logger.debug("Solid render failed, falling back to wireframe: %s", file_path)

    if _render_wireframe(meshes, str(output_path)):
        return output_filename

    logger.warning("All thumbnail rendering strategies failed for: %s", file_path)
    return None
