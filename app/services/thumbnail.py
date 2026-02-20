"""
Server-side thumbnail generation for 3D model files.

Uses trimesh to load meshes and render preview images. Falls back to a
simple wireframe rendering with Pillow when trimesh's built-in rendering
(which depends on pyrender/pyglet) is unavailable.
"""

import logging
import math
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# Thumbnail dimensions
THUMBNAIL_WIDTH = 256
THUMBNAIL_HEIGHT = 256

# Wireframe rendering settings
WIREFRAME_BG_COLOR = (45, 45, 48)
WIREFRAME_LINE_COLOR = (0, 180, 220)
WIREFRAME_EDGE_COLOR = (0, 120, 160)
WIREFRAME_PADDING = 20

# Solid rendering settings
SOLID_BG_COLOR = (45, 45, 48)
SOLID_BASE_COLOR = np.array([0, 150, 200], dtype=np.float64)
SOLID_AMBIENT = 0.25
SOLID_DIFFUSE = 0.75
SOLID_LIGHT_DIR = np.array([0.3, 0.8, 0.5])  # normalised at use-time
SOLID_PADDING = 20


def _try_trimesh_render(scene: trimesh.Scene, output_path: str) -> bool:
    """
    Attempt to render a thumbnail using trimesh's built-in save_image.

    This relies on pyrender/pyglet being available with offscreen rendering
    support (e.g., via EGL or osmesa). Returns True on success, False on failure.
    """
    try:
        # Set up the scene window size for the render
        png_data = scene.save_image(resolution=(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT))
        if png_data and len(png_data) > 0:
            with open(output_path, "wb") as f:
                f.write(png_data)
            logger.debug("Rendered thumbnail via trimesh scene: %s", output_path)
            return True
    except Exception as e:
        logger.debug(
            "trimesh save_image failed (pyrender/pyglet likely unavailable): %s", e
        )
    return False


def _project_vertices(
    vertices: np.ndarray,
    width: int,
    height: int,
    padding: int,
) -> np.ndarray:
    """
    Project 3D vertices to 2D screen coordinates using an isometric-like projection.

    Applies a rotation to give a 3/4 view, then scales and centers the result
    within the given width x height canvas.
    """
    # Rotation angles for a pleasant viewing angle (30 degrees pitch, 45 degrees yaw)
    pitch = math.radians(30)
    yaw = math.radians(45)

    cos_p, sin_p = math.cos(pitch), math.sin(pitch)
    cos_y, sin_y = math.cos(yaw), math.sin(yaw)

    # Yaw rotation (around Y axis)
    rot_yaw = np.array([
        [cos_y, 0, sin_y],
        [0, 1, 0],
        [-sin_y, 0, cos_y],
    ])

    # Pitch rotation (around X axis)
    rot_pitch = np.array([
        [1, 0, 0],
        [0, cos_p, -sin_p],
        [0, sin_p, cos_p],
    ])

    rotated = (rot_pitch @ rot_yaw @ vertices.T).T

    # Project to 2D by dropping the Z coordinate (orthographic projection)
    projected_x = rotated[:, 0]
    projected_y = rotated[:, 1]

    # Scale to fit within the canvas with padding
    usable_w = width - 2 * padding
    usable_h = height - 2 * padding

    x_min, x_max = projected_x.min(), projected_x.max()
    y_min, y_max = projected_y.min(), projected_y.max()

    x_range = x_max - x_min
    y_range = y_max - y_min

    if x_range < 1e-9 and y_range < 1e-9:
        # Degenerate case: all vertices project to the same point
        return np.full((len(vertices), 2), [width / 2, height / 2])

    # Uniform scale to preserve aspect ratio
    scale = min(
        usable_w / x_range if x_range > 1e-9 else float("inf"),
        usable_h / y_range if y_range > 1e-9 else float("inf"),
    )

    screen_x = (projected_x - x_min) * scale + padding + (usable_w - x_range * scale) / 2
    # Flip Y axis for screen coordinates (origin at top-left)
    screen_y = (y_max - projected_y) * scale + padding + (usable_h - y_range * scale) / 2

    return np.column_stack([screen_x, screen_y])


def _collect_meshes(loaded: trimesh.Trimesh | trimesh.Scene) -> list[trimesh.Trimesh]:
    """Collect all Trimesh objects from a loaded model or scene."""
    meshes: list[trimesh.Trimesh] = []

    if isinstance(loaded, trimesh.Trimesh):
        meshes.append(loaded)
    elif isinstance(loaded, trimesh.Scene):
        for geometry in loaded.geometry.values():
            if isinstance(geometry, trimesh.Trimesh):
                meshes.append(geometry)
    return meshes


def _render_wireframe(meshes: list[trimesh.Trimesh], output_path: str) -> bool:
    """
    Render a wireframe preview of the mesh(es) using Pillow.

    Draws edges of the mesh projected onto a 2D canvas with an isometric-style
    viewing angle. Returns True on success.
    """
    if not meshes:
        logger.warning("No meshes to render for wireframe")
        return False

    # Concatenate all vertices and collect edges with vertex offset
    all_vertices = []
    all_edges = []
    offset = 0

    for mesh in meshes:
        all_vertices.append(mesh.vertices)
        # Use the unique edges of the mesh
        if hasattr(mesh, "edges_unique") and len(mesh.edges_unique) > 0:
            all_edges.append(mesh.edges_unique + offset)
        elif hasattr(mesh, "faces") and len(mesh.faces) > 0:
            # Derive edges from faces
            faces = mesh.faces
            e0 = np.column_stack([faces[:, 0], faces[:, 1]])
            e1 = np.column_stack([faces[:, 1], faces[:, 2]])
            e2 = np.column_stack([faces[:, 2], faces[:, 0]])
            edges = np.vstack([e0, e1, e2]) + offset
            all_edges.append(edges)
        offset += len(mesh.vertices)

    if not all_vertices:
        return False

    vertices_3d = np.vstack(all_vertices)

    if len(vertices_3d) == 0:
        logger.warning("Empty mesh - no vertices to render")
        return False

    # Center the model at origin
    centroid = vertices_3d.mean(axis=0)
    vertices_3d = vertices_3d - centroid

    projected = _project_vertices(
        vertices_3d, THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT, WIREFRAME_PADDING
    )

    # Create the image
    img = Image.new("RGB", (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), WIREFRAME_BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Draw edges
    if all_edges:
        edges = np.vstack(all_edges)

        # If there are too many edges, subsample for performance
        max_edges = 50000
        if len(edges) > max_edges:
            indices = np.random.default_rng(42).choice(
                len(edges), size=max_edges, replace=False
            )
            edges = edges[indices]

        for v0_idx, v1_idx in edges:
            x0, y0 = projected[v0_idx]
            x1, y1 = projected[v1_idx]
            draw.line(
                [(float(x0), float(y0)), (float(x1), float(y1))],
                fill=WIREFRAME_EDGE_COLOR,
                width=1,
            )
    else:
        # No edges available - just draw vertices as dots
        for x, y in projected:
            draw.ellipse(
                [float(x) - 1, float(y) - 1, float(x) + 1, float(y) + 1],
                fill=WIREFRAME_LINE_COLOR,
            )

    img.save(output_path, "PNG")
    logger.debug("Rendered wireframe thumbnail: %s", output_path)
    return True


def _render_solid(meshes: list[trimesh.Trimesh], output_path: str) -> bool:
    """
    Render a solid (filled-face) preview of the mesh(es) using Pillow.

    Uses a painter's-algorithm approach: faces are sorted back-to-front by
    their average Z depth (after rotation) and drawn as filled polygons with
    simple directional lighting.  Returns True on success.
    """
    if not meshes:
        logger.warning("No meshes to render for solid thumbnail")
        return False

    # Collect all vertices and faces with vertex offset
    all_vertices: list[np.ndarray] = []
    all_faces: list[np.ndarray] = []
    offset = 0

    for mesh in meshes:
        all_vertices.append(mesh.vertices)
        if hasattr(mesh, "faces") and len(mesh.faces) > 0:
            all_faces.append(mesh.faces + offset)
        offset += len(mesh.vertices)

    if not all_vertices or not all_faces:
        logger.warning("No faces to render for solid thumbnail")
        return False

    vertices_3d = np.vstack(all_vertices)
    faces = np.vstack(all_faces)

    if len(vertices_3d) == 0 or len(faces) == 0:
        return False

    # Center the model at origin
    centroid = vertices_3d.mean(axis=0)
    vertices_3d = vertices_3d - centroid

    # Rotation angles (same as wireframe for consistency)
    pitch = math.radians(30)
    yaw = math.radians(45)

    cos_p, sin_p = math.cos(pitch), math.sin(pitch)
    cos_y, sin_y = math.cos(yaw), math.sin(yaw)

    rot_yaw = np.array([
        [cos_y, 0, sin_y],
        [0, 1, 0],
        [-sin_y, 0, cos_y],
    ])
    rot_pitch = np.array([
        [1, 0, 0],
        [0, cos_p, -sin_p],
        [0, sin_p, cos_p],
    ])
    rot = rot_pitch @ rot_yaw
    rotated = (rot @ vertices_3d.T).T

    # Project to 2D (same as _project_vertices but we also need Z for sorting)
    projected_x = rotated[:, 0]
    projected_y = rotated[:, 1]
    projected_z = rotated[:, 2]

    padding = SOLID_PADDING
    usable_w = THUMBNAIL_WIDTH - 2 * padding
    usable_h = THUMBNAIL_HEIGHT - 2 * padding

    x_min, x_max = projected_x.min(), projected_x.max()
    y_min, y_max = projected_y.min(), projected_y.max()
    x_range = x_max - x_min
    y_range = y_max - y_min

    if x_range < 1e-9 and y_range < 1e-9:
        return False

    scale = min(
        usable_w / x_range if x_range > 1e-9 else float("inf"),
        usable_h / y_range if y_range > 1e-9 else float("inf"),
    )

    screen_x = (projected_x - x_min) * scale + padding + (usable_w - x_range * scale) / 2
    screen_y = (y_max - projected_y) * scale + padding + (usable_h - y_range * scale) / 2

    # Compute per-face average Z depth for painter's algorithm
    face_z = projected_z[faces].mean(axis=1)

    # Sort faces back-to-front (lowest Z first = furthest from camera)
    sort_order = np.argsort(face_z)

    # Compute face normals in rotated space for lighting
    v0 = rotated[faces[:, 0]]
    v1 = rotated[faces[:, 1]]
    v2 = rotated[faces[:, 2]]
    edge1 = v1 - v0
    edge2 = v2 - v0
    normals = np.cross(edge1, edge2)
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    norms[norms < 1e-12] = 1.0
    normals = normals / norms

    # Normalise light direction
    light_dir = SOLID_LIGHT_DIR / np.linalg.norm(SOLID_LIGHT_DIR)

    # Compute per-face diffuse intensity
    dot = np.abs(np.dot(normals, light_dir))  # abs for double-sided lighting
    intensity = np.clip(SOLID_AMBIENT + SOLID_DIFFUSE * dot, 0.0, 1.0)

    # Limit face count for performance
    max_faces = 80000
    if len(sort_order) > max_faces:
        # Keep a uniform subsample but maintain sort order
        step = len(sort_order) / max_faces
        indices = np.round(np.arange(0, len(sort_order), step)).astype(int)[:max_faces]
        sort_order = sort_order[indices]

    # Create image and draw
    img = Image.new("RGB", (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), SOLID_BG_COLOR)
    draw = ImageDraw.Draw(img)

    for fi in sort_order:
        i0, i1, i2 = faces[fi]
        polygon = [
            (float(screen_x[i0]), float(screen_y[i0])),
            (float(screen_x[i1]), float(screen_y[i1])),
            (float(screen_x[i2]), float(screen_y[i2])),
        ]
        c = (SOLID_BASE_COLOR * intensity[fi]).astype(int)
        fill_color = (int(c[0]), int(c[1]), int(c[2]))
        draw.polygon(polygon, fill=fill_color)

    img.save(output_path, "PNG")
    logger.debug("Rendered solid thumbnail: %s", output_path)
    return True


def generate_thumbnail(
    file_path: str,
    output_dir: str,
    model_id: int,
    render_mode: str = "wireframe",
) -> str | None:
    """
    Generate a 256x256 PNG thumbnail for a 3D model file.

    Attempts to render using trimesh's built-in rendering first. If that fails
    (common in headless environments without pyrender), falls back to a
    Pillow-based rendering using the specified *render_mode*.

    Args:
        file_path: Absolute path to the 3D model file.
        output_dir: Directory where thumbnails should be saved.
        model_id: Unique ID for the model, used as the output filename.
        render_mode: ``"wireframe"`` (default) or ``"solid"``.

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
        logger.warning("Could not load 3D file for thumbnail: %s: %s", file_path, e)
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
    # Only attempt for wireframe mode — the built-in renderer produces its own
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
        if _render_solid(meshes, str(output_path)):
            return output_filename
        # Fall back to wireframe if solid fails (e.g. no faces)
        logger.debug("Solid render failed, falling back to wireframe: %s", file_path)

    if _render_wireframe(meshes, str(output_path)):
        return output_filename

    logger.warning("All thumbnail rendering strategies failed for: %s", file_path)
    return None
