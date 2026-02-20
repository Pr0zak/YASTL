"""STEP/STP file conversion to triangle mesh.

Provides STEP → trimesh conversion using available backends:
1. OCP (cadquery-ocp / opencascade) — high-quality BRep tessellation
2. gmsh — mesh generation from CAD geometry

If no suitable backend is installed the helper returns ``None`` so that
callers can fall back gracefully.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import trimesh

logger = logging.getLogger(__name__)

# Cache which backend (if any) is available so we only probe once.
_backend: str | None = None
_backend_checked: bool = False


def _detect_backend() -> str | None:
    """Return the name of the first usable STEP backend, or ``None``."""
    global _backend, _backend_checked
    if _backend_checked:
        return _backend
    _backend_checked = True

    # 1. Try OCP (cadquery-ocp)
    try:
        from OCP.STEPControl import STEPControl_Reader  # noqa: F401
        from OCP.BRepMesh import BRepMesh_IncrementalMesh  # noqa: F401

        _backend = "ocp"
        logger.info("STEP support: using OCP (OpenCASCADE) backend")
        return _backend
    except Exception:
        pass

    # 2. Try gmsh
    try:
        import gmsh  # noqa: F401

        _backend = "gmsh"
        logger.info("STEP support: using gmsh backend")
        return _backend
    except Exception:
        pass

    logger.warning(
        "No STEP backend available. Install 'cadquery-ocp' or 'gmsh' "
        "for STEP/STP file support."
    )
    _backend = None
    return _backend


# ---------------------------------------------------------------------------
# OCP (OpenCASCADE) backend
# ---------------------------------------------------------------------------


def _load_step_ocp(file_path: str) -> trimesh.Trimesh | None:
    """Tessellate a STEP file using OCP (OpenCASCADE Python bindings)."""
    import trimesh
    from OCP.STEPControl import STEPControl_Reader
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Pnt

    reader = STEPControl_Reader()
    status = reader.ReadFile(file_path)
    if status != IFSelect_RetDone:
        logger.warning("OCP: failed to read STEP file: %s", file_path)
        return None

    reader.TransferRoots()
    shape = reader.OneShape()

    # Tessellate the shape
    mesh_algo = BRepMesh_IncrementalMesh(shape, 0.1, False, 0.5, True)
    mesh_algo.Perform()

    all_vertices: list[list[float]] = []
    all_faces: list[list[int]] = []
    offset = 0

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = explorer.Current()
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)

        if triangulation is not None:
            nb_nodes = triangulation.NbNodes()
            nb_tris = triangulation.NbTriangles()

            # Extract vertices
            for i in range(1, nb_nodes + 1):
                pnt: gp_Pnt = triangulation.Node(i)
                if not location.IsIdentity():
                    pnt = pnt.Transformed(location.Transformation())
                all_vertices.append([pnt.X(), pnt.Y(), pnt.Z()])

            # Extract triangles
            for i in range(1, nb_tris + 1):
                tri = triangulation.Triangle(i)
                n1, n2, n3 = tri.Get()
                all_faces.append([
                    n1 - 1 + offset,
                    n2 - 1 + offset,
                    n3 - 1 + offset,
                ])

            offset += nb_nodes

        explorer.Next()

    if not all_vertices or not all_faces:
        logger.warning("OCP: no triangulation produced for: %s", file_path)
        return None

    vertices = np.array(all_vertices, dtype=np.float64)
    faces = np.array(all_faces, dtype=np.int64)

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    logger.debug(
        "OCP: tessellated %s → %d verts, %d faces",
        file_path,
        len(vertices),
        len(faces),
    )
    return mesh


# ---------------------------------------------------------------------------
# gmsh backend
# ---------------------------------------------------------------------------


def _load_step_gmsh(file_path: str) -> trimesh.Trimesh | None:
    """Tessellate a STEP file using the gmsh mesher."""
    import gmsh
    import trimesh

    gmsh.initialize()
    gmsh.option.setNumber("General.Verbosity", 0)

    try:
        gmsh.model.occ.importShapes(file_path)
        gmsh.model.occ.synchronize()
        gmsh.model.mesh.generate(2)

        # Get all nodes
        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        if len(coords) == 0:
            logger.warning("gmsh: no mesh nodes produced for: %s", file_path)
            return None

        # Build tag → index map
        tag_to_idx = {int(tag): idx for idx, tag in enumerate(node_tags)}
        vertices = np.array(coords, dtype=np.float64).reshape(-1, 3)

        # Get triangular elements (type 2 = 3-node triangle)
        elem_types, elem_tags, elem_node_tags = gmsh.model.mesh.getElements()
        all_faces: list[list[int]] = []

        for etype, enodes in zip(elem_types, elem_node_tags):
            if etype == 2:  # triangles
                nodes_per_elem = 3
                for i in range(0, len(enodes), nodes_per_elem):
                    n1 = tag_to_idx.get(int(enodes[i]))
                    n2 = tag_to_idx.get(int(enodes[i + 1]))
                    n3 = tag_to_idx.get(int(enodes[i + 2]))
                    if n1 is not None and n2 is not None and n3 is not None:
                        all_faces.append([n1, n2, n3])

        if not all_faces:
            logger.warning("gmsh: no triangles produced for: %s", file_path)
            return None

        faces = np.array(all_faces, dtype=np.int64)
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
        logger.debug(
            "gmsh: meshed %s → %d verts, %d faces",
            file_path,
            len(vertices),
            len(faces),
        )
        return mesh
    except Exception as e:
        logger.warning("gmsh: failed to process %s: %s", file_path, e)
        return None
    finally:
        gmsh.finalize()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_step(file_path: str) -> trimesh.Trimesh | None:
    """Load a STEP/STP file and return a ``trimesh.Trimesh``.

    Tries available backends in order.  Returns ``None`` when no backend
    can handle the file.
    """
    backend = _detect_backend()

    if backend == "ocp":
        try:
            return _load_step_ocp(file_path)
        except Exception as e:
            logger.warning("OCP backend failed for %s: %s", file_path, e)
            return None

    if backend == "gmsh":
        try:
            return _load_step_gmsh(file_path)
        except Exception as e:
            logger.warning("gmsh backend failed for %s: %s", file_path, e)
            return None

    return None


def is_step_file(file_path: str) -> bool:
    """Check whether a file path has a STEP/STP extension."""
    return Path(file_path).suffix.lower() in {".step", ".stp"}


def has_step_support() -> bool:
    """Return True if a STEP conversion backend is available."""
    return _detect_backend() is not None
