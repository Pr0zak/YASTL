"""Rendering backends for 3D model thumbnail generation.

Provides multiple rendering strategies:
- trimesh built-in (pyrender/pyglet, requires GPU or osmesa)
- Pillow wireframe (edge projection, always works)
- Pillow solid fast (painter's algorithm with 2x supersampling)
- Pillow solid quality (numpy z-buffer with Gouraud shading)
"""

import logging
import math

import numpy as np
import trimesh
from PIL import Image, ImageDraw

from app.services.thumbnail_mesh import _simplify_for_thumbnail

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


def _render_wireframe(meshes: list[trimesh.Trimesh], output_path: str) -> bool:
    """
    Render a wireframe preview of the mesh(es) using Pillow.

    Draws edges of the mesh projected onto a 2D canvas with an isometric-style
    viewing angle. Returns True on success.
    """
    if not meshes:
        logger.warning("No meshes to render for wireframe")
        return False

    # Decimate high-poly meshes to keep edge count manageable
    meshes = _simplify_for_thumbnail(meshes)

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


def _render_solid_fast(meshes: list[trimesh.Trimesh], output_path: str) -> bool:
    """Fast solid rendering using Pillow painter's algorithm with 2x supersampling.

    Good quality for most models, very fast. May show minor artifacts on
    extremely high-poly meshes where faces are sub-pixel.
    """
    if not meshes:
        return False

    meshes = _simplify_for_thumbnail(meshes)

    all_vertices: list[np.ndarray] = []
    all_faces: list[np.ndarray] = []
    offset = 0
    for mesh in meshes:
        all_vertices.append(mesh.vertices)
        if hasattr(mesh, "faces") and len(mesh.faces) > 0:
            all_faces.append(mesh.faces + offset)
        offset += len(mesh.vertices)

    if not all_vertices or not all_faces:
        return False

    vertices_3d = np.vstack(all_vertices)
    faces = np.vstack(all_faces)
    if len(vertices_3d) == 0 or len(faces) == 0:
        return False

    centroid = vertices_3d.mean(axis=0)
    vertices_3d = vertices_3d - centroid

    pitch = math.radians(30)
    yaw = math.radians(45)
    cos_p, sin_p = math.cos(pitch), math.sin(pitch)
    cos_y, sin_y = math.cos(yaw), math.sin(yaw)
    rot_yaw = np.array([[cos_y, 0, sin_y], [0, 1, 0], [-sin_y, 0, cos_y]])
    rot_pitch = np.array([[1, 0, 0], [0, cos_p, -sin_p], [0, sin_p, cos_p]])
    rot = rot_pitch @ rot_yaw
    rotated = (rot @ vertices_3d.T).T

    projected_z = rotated[:, 2]

    # 2x supersampling
    ss = 2
    render_w = THUMBNAIL_WIDTH * ss
    render_h = THUMBNAIL_HEIGHT * ss
    padding = SOLID_PADDING * ss
    usable_w = render_w - 2 * padding
    usable_h = render_h - 2 * padding

    x_min, x_max = rotated[:, 0].min(), rotated[:, 0].max()
    y_min, y_max = rotated[:, 1].min(), rotated[:, 1].max()
    x_range = x_max - x_min
    y_range = y_max - y_min
    if x_range < 1e-9 and y_range < 1e-9:
        return False

    scale = min(
        usable_w / x_range if x_range > 1e-9 else float("inf"),
        usable_h / y_range if y_range > 1e-9 else float("inf"),
    )
    screen_x = (rotated[:, 0] - x_min) * scale + padding + (usable_w - x_range * scale) / 2
    screen_y = (y_max - rotated[:, 1]) * scale + padding + (usable_h - y_range * scale) / 2

    # Painter's algorithm
    face_z = projected_z[faces].mean(axis=1)
    sort_order = np.argsort(face_z)

    # Per-face lighting
    v0 = rotated[faces[:, 0]]
    v1 = rotated[faces[:, 1]]
    v2 = rotated[faces[:, 2]]
    normals = np.cross(v1 - v0, v2 - v0)
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    norms[norms < 1e-12] = 1.0
    normals = normals / norms
    light_dir = SOLID_LIGHT_DIR / np.linalg.norm(SOLID_LIGHT_DIR)
    dot = np.abs(np.dot(normals, light_dir))
    intensity = np.clip(SOLID_AMBIENT + SOLID_DIFFUSE * dot, 0.0, 1.0)

    img = Image.new("RGB", (render_w, render_h), SOLID_BG_COLOR)
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
        draw.polygon(polygon, fill=fill_color, outline=fill_color)

    img = img.resize((THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), Image.LANCZOS)
    img.save(output_path, "PNG")
    logger.debug("Rendered solid thumbnail (fast): %s", output_path)
    return True


def _render_solid(meshes: list[trimesh.Trimesh], output_path: str) -> bool:
    """High-quality solid rendering using a numpy z-buffer rasterizer.

    Uses per-pixel depth testing (no painter's algorithm gaps) and
    per-vertex normal interpolation for smooth Gouraud shading, matching
    the quality of GPU-based renderers like Three.js/WebGL.
    """
    if not meshes:
        logger.warning("No meshes to render for solid thumbnail")
        return False

    # Decimate high-poly meshes for performance
    meshes = _simplify_for_thumbnail(meshes)

    # Collect vertices, faces, and vertex normals with offset tracking
    all_vertices: list[np.ndarray] = []
    all_faces: list[np.ndarray] = []
    all_normals: list[np.ndarray] = []
    offset = 0

    for mesh in meshes:
        all_vertices.append(mesh.vertices)
        if hasattr(mesh, "faces") and len(mesh.faces) > 0:
            all_faces.append(mesh.faces + offset)
        # Compute smooth vertex normals for Gouraud shading
        try:
            all_normals.append(mesh.vertex_normals)
        except Exception:
            # Fallback: use face normals broadcast to vertices
            fn = np.zeros_like(mesh.vertices)
            if len(mesh.faces) > 0:
                face_normals = mesh.face_normals
                np.add.at(fn, mesh.faces[:, 0], face_normals)
                np.add.at(fn, mesh.faces[:, 1], face_normals)
                np.add.at(fn, mesh.faces[:, 2], face_normals)
                norms = np.linalg.norm(fn, axis=1, keepdims=True)
                norms[norms < 1e-12] = 1.0
                fn = fn / norms
            all_normals.append(fn)
        offset += len(mesh.vertices)

    if not all_vertices or not all_faces:
        logger.warning("No faces to render for solid thumbnail")
        return False

    vertices_3d = np.vstack(all_vertices)
    faces = np.vstack(all_faces)
    vert_normals = np.vstack(all_normals)

    if len(vertices_3d) == 0 or len(faces) == 0:
        return False

    # Center at origin
    centroid = vertices_3d.mean(axis=0)
    vertices_3d = vertices_3d - centroid

    # Camera rotation (same angles as wireframe for consistency)
    pitch = math.radians(30)
    yaw = math.radians(45)
    cos_p, sin_p = math.cos(pitch), math.sin(pitch)
    cos_y, sin_y = math.cos(yaw), math.sin(yaw)
    rot_yaw = np.array([[cos_y, 0, sin_y], [0, 1, 0], [-sin_y, 0, cos_y]])
    rot_pitch = np.array([[1, 0, 0], [0, cos_p, -sin_p], [0, sin_p, cos_p]])
    rot = rot_pitch @ rot_yaw

    rotated = (rot @ vertices_3d.T).T
    rot_normals = (rot @ vert_normals.T).T

    # Project to screen coordinates
    W, H = THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT
    padding = SOLID_PADDING
    usable_w = W - 2 * padding
    usable_h = H - 2 * padding

    x_min, x_max = rotated[:, 0].min(), rotated[:, 0].max()
    y_min, y_max = rotated[:, 1].min(), rotated[:, 1].max()
    x_range = x_max - x_min
    y_range = y_max - y_min

    if x_range < 1e-9 and y_range < 1e-9:
        return False

    scale = min(
        usable_w / x_range if x_range > 1e-9 else float("inf"),
        usable_h / y_range if y_range > 1e-9 else float("inf"),
    )

    sx = (rotated[:, 0] - x_min) * scale + padding + (usable_w - x_range * scale) / 2
    sy = (y_max - rotated[:, 1]) * scale + padding + (usable_h - y_range * scale) / 2
    sz = rotated[:, 2]  # depth for z-buffer

    # Per-vertex lighting (Gouraud shading)
    light_dir = SOLID_LIGHT_DIR / np.linalg.norm(SOLID_LIGHT_DIR)
    dot = np.abs(np.dot(rot_normals, light_dir))  # double-sided
    vert_intensity = np.clip(SOLID_AMBIENT + SOLID_DIFFUSE * dot, 0.0, 1.0)

    # --- Fully vectorized z-buffer rasterization (zero Python loops) ---
    #
    # At 256x256, high-poly meshes have faces smaller than a pixel. We use
    # a two-pass approach:
    #   Pass 1 (all faces): centroid rasterization -- one sample per face at
    #           the triangle centroid. Fully vectorized, handles sub-pixel
    #           triangles that dominate high-poly meshes.
    #   Pass 2 (large faces only): multi-sample rasterization for faces
    #           whose bounding box exceeds 2x2 pixels, ensuring large
    #           triangles are filled completely.

    i0 = faces[:, 0]
    i1 = faces[:, 1]
    i2 = faces[:, 2]

    # Face centroid screen coords and depth
    cx = (sx[i0] + sx[i1] + sx[i2]) / 3.0
    cy = (sy[i0] + sy[i1] + sy[i2]) / 3.0
    cz = (sz[i0] + sz[i1] + sz[i2]) / 3.0

    # Average vertex intensity per face (smooth approximation)
    c_int = (vert_intensity[i0] + vert_intensity[i1] + vert_intensity[i2]) / 3.0

    # Centroid pixel coordinates
    cix = np.clip(np.round(cx).astype(np.int32), 0, W - 1)
    ciy = np.clip(np.round(cy).astype(np.int32), 0, H - 1)

    # Sort by depth ascending so closest writes last (wins z-buffer)
    sort_idx = np.argsort(cz)

    color_buf = np.full((H, W, 3), SOLID_BG_COLOR, dtype=np.uint8)

    # Pass 1: write all face centroids -- last (closest) write wins
    sorted_iy = ciy[sort_idx]
    sorted_ix = cix[sort_idx]
    sorted_int = c_int[sort_idx]

    color_buf[sorted_iy, sorted_ix, 0] = np.clip(
        SOLID_BASE_COLOR[0] * sorted_int, 0, 255
    ).astype(np.uint8)
    color_buf[sorted_iy, sorted_ix, 1] = np.clip(
        SOLID_BASE_COLOR[1] * sorted_int, 0, 255
    ).astype(np.uint8)
    color_buf[sorted_iy, sorted_ix, 2] = np.clip(
        SOLID_BASE_COLOR[2] * sorted_int, 0, 255
    ).astype(np.uint8)

    z_buf = np.full((H, W), -np.inf, dtype=np.float64)
    z_buf[sorted_iy, sorted_ix] = cz[sort_idx]

    # Pass 2: fill large triangles (bounding box > 2x2 pixels)
    fx0 = sx[i0]
    fy0 = sy[i0]
    fz0 = sz[i0]
    fx1 = sx[i1]
    fy1 = sy[i1]
    fz1 = sz[i1]
    fx2 = sx[i2]
    fy2 = sy[i2]
    fz2 = sz[i2]
    fi0 = vert_intensity[i0]
    fi1 = vert_intensity[i1]
    fi2 = vert_intensity[i2]

    bb_x0 = np.clip(np.floor(np.minimum(np.minimum(fx0, fx1), fx2)).astype(np.int32), 0, W - 1)
    bb_x1 = np.clip(np.ceil(np.maximum(np.maximum(fx0, fx1), fx2)).astype(np.int32), 0, W - 1)
    bb_y0 = np.clip(np.floor(np.minimum(np.minimum(fy0, fy1), fy2)).astype(np.int32), 0, H - 1)
    bb_y1 = np.clip(np.ceil(np.maximum(np.maximum(fy0, fy1), fy2)).astype(np.int32), 0, H - 1)

    widths = bb_x1 - bb_x0 + 1
    heights = bb_y1 - bb_y0 + 1

    # Barycentric setup
    d00 = fx1 - fx0
    d01 = fx2 - fx0
    d10 = fy1 - fy0
    d11 = fy2 - fy0
    denom = d00 * d11 - d01 * d10

    # Only process faces that span more than 2 pixels in either dimension
    large = (np.abs(denom) > 1e-12) & ((widths > 2) | (heights > 2))
    large_idx = np.where(large)[0]

    if len(large_idx) > 0:
        # Sort large faces front-to-back for early z-rejection
        large_cz = cz[large_idx]
        large_idx = large_idx[np.argsort(-large_cz)]

        inv_denom_all = np.zeros(len(faces))
        inv_denom_all[large_idx] = 1.0 / denom[large_idx]

        for fi in large_idx:
            bx0 = bb_x0[fi]
            bx1 = bb_x1[fi]
            by0 = bb_y0[fi]
            by1 = bb_y1[fi]

            xs = np.arange(bx0, bx1 + 1, dtype=np.float64)
            ys = np.arange(by0, by1 + 1, dtype=np.float64)
            px, py = np.meshgrid(xs, ys)
            px = px.ravel()
            py = py.ravel()

            dx = px - fx0[fi]
            dy = py - fy0[fi]
            inv_d = inv_denom_all[fi]
            u = (dx * d11[fi] - d01[fi] * dy) * inv_d
            v = (d00[fi] * dy - dx * d10[fi]) * inv_d
            w = 1.0 - u - v

            mask = (u >= 0) & (v >= 0) & (w >= 0)
            if not np.any(mask):
                continue

            pxm = px[mask].astype(np.int32)
            pym = py[mask].astype(np.int32)
            um = u[mask]
            vm = v[mask]
            wm = w[mask]

            z = wm * fz0[fi] + um * fz1[fi] + vm * fz2[fi]
            closer = z > z_buf[pym, pxm]
            if not np.any(closer):
                continue

            pxc = pxm[closer]
            pyc = pym[closer]
            z_buf[pyc, pxc] = z[closer]

            inten = wm[closer] * fi0[fi] + um[closer] * fi1[fi] + vm[closer] * fi2[fi]
            color_buf[pyc, pxc, 0] = np.clip(SOLID_BASE_COLOR[0] * inten, 0, 255).astype(np.uint8)
            color_buf[pyc, pxc, 1] = np.clip(SOLID_BASE_COLOR[1] * inten, 0, 255).astype(np.uint8)
            color_buf[pyc, pxc, 2] = np.clip(SOLID_BASE_COLOR[2] * inten, 0, 255).astype(np.uint8)

    img = Image.fromarray(color_buf, "RGB")
    img.save(output_path, "PNG")
    logger.debug("Rendered solid thumbnail (z-buffer): %s", output_path)
    return True
