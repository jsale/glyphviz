"""
Importer for arbitrary external 3D model files (OBJ, STL, ...) used by the
GEO_MESH geometry (see geometry_data.py). Pure data/numpy — no OpenGL/Qt
dependency, so this module is safe to import from anything, including a
future non-GL (e.g. OpenXR/three.js) presentation layer.

Backed by trimesh, which already handles OBJ/STL robustly (and several other
formats — PLY, glTF, ... — for free) without us hand-rolling parsers.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh

# Formats trimesh/its optional dependencies parse reliably without extra
# native libraries (assimp, etc.). 3DS and DXF are deliberately not offered
# yet: both need assimp, which isn't a project dependency today.
SUPPORTED_EXTENSIONS = ('.obj', '.stl', '.ply', '.glb', '.gltf')


@dataclass
class MeshData:
    name: str
    vertices: np.ndarray   # (N, 3) float32, normalized to fit radius ~1
    faces: np.ndarray      # (M, 3) int32
    normals: np.ndarray    # (N, 3) float32, per-vertex


def load_mesh_file(path: str) -> MeshData:
    """Load *path* and normalize it to the same unit-scale convention every
    other GEO_* shape uses (geometry.py: "fits within radius ~1"), so it
    composes with a node's scale_x/y/z exactly like the built-in glyphs."""
    mesh = trimesh.load(path, force='mesh')
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.vertices) == 0:
        raise ValueError(f"No usable triangle mesh found in {path!r}")

    verts = np.asarray(mesh.vertices, dtype=np.float64)
    center = mesh.bounding_box.centroid
    verts = verts - center
    radius = float(np.max(np.linalg.norm(verts, axis=1)))
    if radius > 1e-12:
        verts = verts / radius

    return MeshData(
        name=Path(path).stem,
        vertices=verts.astype(np.float32),
        faces=np.asarray(mesh.faces, dtype=np.int32),
        normals=np.asarray(mesh.vertex_normals, dtype=np.float32),
    )
