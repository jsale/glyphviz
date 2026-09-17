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

# Two faces meeting at a sharper angle than this are a CREASE: the edge
# between them stays hard instead of being shaded as one smooth surface. 40
# degrees keeps a cube's corners square and a cylinder's 24-sided barrel round
# (its facets meet at 15 degrees), which is the split every DCC tool draws by
# default. Raise it towards 180 for everything-smooth, drop it to 0 for
# everything-faceted.
DEFAULT_CREASE_ANGLE = 40.0


@dataclass
class MeshData:
    name: str
    vertices: np.ndarray   # (N, 3) float32, normalized to fit radius ~1
    faces: np.ndarray      # (M, 3) int32
    normals: np.ndarray    # (N, 3) float32, per-vertex
    uvs: np.ndarray | None = None   # (N, 2) float32 texture coords, or None
    # (M, 3, 3) float32: one normal per face CORNER, so an edge can be hard on
    # one side and smooth on the other. None falls back to `normals`.
    corner_normals: np.ndarray | None = None

    @property
    def has_uvs(self) -> bool:
        return self.uvs is not None

    def normal_for(self, face_i: int, corner_k: int, vert_i: int):
        """The normal to emit for one corner of one face — crease-aware when
        the import produced corner normals, else the smoothed per-vertex one."""
        if self.corner_normals is not None:
            return self.corner_normals[face_i][corner_k]
        return self.normals[vert_i]


def _crease_normals(verts, faces, angle_deg: float):
    """Per-corner normals that keep sharp edges sharp.

    Why this exists: load_mesh_file welds duplicate vertices (validate=True,
    for reasons documented there), and trimesh's `vertex_normals` then average
    every face meeting at a vertex. A cube therefore arrives as 8 vertices
    whose normals all point diagonally outward (0.577, 0.577, 0.577) — so it
    shades like a beach ball, and so does every building, vehicle and
    mechanical part anyone imports. STL is worst hit, being per-face by nature.

    The fix is the standard one: a corner's normal averages only those
    incident faces within `angle_deg` of its OWN face, so a smooth surface
    still shades smooth while a crease stays crisp. Faces are area-weighted,
    which keeps a large panel from being dragged around by the slivers along
    its edge.

    Returns (M, 3, 3) float32, or None when the mesh is degenerate enough that
    per-vertex normals are the safer answer.
    """
    faces = np.asarray(faces)
    if len(faces) == 0:
        return None

    tri = verts[faces]                                     # (M, 3, 3)
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area2 = np.linalg.norm(cross, axis=1)                  # 2x area
    live = area2 > 1e-20
    if not live.any():
        return None
    fnorm = np.zeros_like(cross)
    fnorm[live] = cross[live] / area2[live][:, None]

    n_faces = len(faces)
    corner_face = np.repeat(np.arange(n_faces), 3)

    # Group corners by POSITION, not by vertex index.
    #
    # The two sides of a texture seam are separate vertices — that is what a
    # seam IS, and load_mesh_file keeps them apart on purpose so the UVs
    # survive. But they are not separate *geometry*: indexing the incidence
    # table by vertex would give each side only its own faces to average, and
    # shade a hard crease down a surface that is perfectly smooth. A lofted
    # tube would wear a visible stripe along its seam.
    #
    # So a crease is decided on position alone. GlyphViz Web merges by
    # position here too, and the two agreed to within 0.13 degrees mean /
    # 0 degrees median across a 1,812-triangle airframe once this matched;
    # before it, the seam corners differed by up to 14 degrees.
    rep_keys, rep_index = np.unique(np.round(verts, 6), axis=0,
                                    return_inverse=True)
    rep_index = np.asarray(rep_index).ravel()
    corner_vert = rep_index[faces.ravel()]                 # (3M,)

    # Group corners by vertex into a padded (V, K) table, so the per-corner
    # masked average below is one vectorized gather rather than a Python loop
    # over vertices (which costs minutes on a 100k-face import).
    order = np.argsort(corner_vert, kind='stable')
    sorted_vert = corner_vert[order]
    n_verts = len(rep_keys)
    counts = np.bincount(sorted_vert, minlength=n_verts)
    k_max = int(counts.max()) if len(counts) else 0
    if k_max == 0:
        return None
    # A pathological vertex (a fan hub joining thousands of faces) would blow
    # the padded table up to V x K; fall back rather than allocate that.
    if n_verts * k_max > 40_000_000:
        return None

    starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
    slot = np.arange(len(sorted_vert)) - np.repeat(starts, counts)
    table = np.zeros((n_verts, k_max), dtype=np.int64)     # -> face index
    valid = np.zeros((n_verts, k_max), dtype=bool)
    table[sorted_vert, slot] = corner_face[order]
    valid[sorted_vert, slot] = True

    inc_n = fnorm[table]                                   # (V, K, 3)
    inc_w = np.where(valid, area2[table], 0.0)             # (V, K)

    own_n = fnorm[corner_face]                             # (3M, 3)
    nbr_n = inc_n[corner_vert]                             # (3M, K, 3)
    nbr_w = inc_w[corner_vert]                             # (3M, K)

    cos_t = np.cos(np.radians(float(angle_deg)))
    aligned = np.einsum('ckj,cj->ck', nbr_n, own_n) >= cos_t
    weight = np.where(aligned, nbr_w, 0.0)
    out = np.einsum('ck,ckj->cj', weight, nbr_n)           # (3M, 3)

    length = np.linalg.norm(out, axis=1)
    # A corner whose neighbourhood cancelled out (a zero-area face, or two
    # coincident faces wound oppositely) keeps its own face normal.
    thin = length <= 1e-12
    out[thin] = own_n[thin]
    length[thin] = np.linalg.norm(out[thin], axis=1)
    safe = length > 1e-12
    out[safe] /= length[safe][:, None]

    return out.reshape(n_faces, 3, 3).astype(np.float32)


def _extract_uvs(mesh, n_verts: int):
    """Per-vertex (N, 2) UVs from a trimesh visual, or None when the file
    carried no texture coordinates.

    Only the *coordinates* are taken: a mesh's own material (its texture
    image, diffuse color, ...) is deliberately ignored, because in GlyphViz
    the image a mesh samples is the node's `texture_id`, i.e. a file in the
    scene's media/ folder, exactly as for every built-in geometry. That keeps
    one texture rule for the whole app and lets a single mesh be re-skinned
    per node without touching the file on disk.

    Note UV seams survive load_mesh_file's validate=True: trimesh's
    merge_vertices does not weld two co-located vertices that carry different
    UVs, so a vertex position may legitimately appear more than once (verified
    against a two-triangle seam fixture).
    """
    uv = getattr(getattr(mesh, 'visual', None), 'uv', None)
    if uv is None:
        return None
    uv = np.asarray(uv, dtype=np.float32)
    # A visual whose UV array doesn't line up 1:1 with the processed vertices
    # can't be indexed by the face arrays, so treat it as absent rather than
    # risk an out-of-range read mid-display-list.
    if uv.ndim != 2 or uv.shape[0] != n_verts or uv.shape[1] < 2:
        return None
    return np.ascontiguousarray(uv[:, :2], dtype=np.float32)


def load_mesh_file(path: str, crease_angle: float = DEFAULT_CREASE_ANGLE) -> MeshData:
    """Load *path* and normalize it to the same unit-scale convention every
    other GEO_* shape uses (geometry.py: "fits within radius ~1"), so it
    composes with a node's scale_x/y/z exactly like the built-in glyphs."""
    # validate=True is required, not just process's default True: process()
    # alone (validate=False) runs remove_infinite_values(), but that drops
    # NaN/Inf *vertices* without dropping the faces that referenced them --
    # update_vertices() remaps those faces onto whatever vertex now sits at
    # the old index (often vertex 0), leaving a "hub" of degenerate spike
    # triangles fanning out from real geometry to that one point. validate=True
    # additionally runs nondegenerate_faces()/fix_normals(), which removes
    # exactly those spikes. Confirmed on Jeff's isosurface5.stl: vertex 0 was
    # referenced by 73,862 of 126,846 faces (vs. ~10 for a normal vertex)
    # without validate=True, rendering as radial lines converging on one point.
    mesh = trimesh.load(path, force='mesh', validate=True)
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.vertices) == 0:
        raise ValueError(f"No usable triangle mesh found in {path!r}")

    verts = np.asarray(mesh.vertices, dtype=np.float64)
    center = mesh.bounding_box.centroid
    verts = verts - center
    radius = float(np.max(np.linalg.norm(verts, axis=1)))
    if radius > 1e-12:
        verts = verts / radius

    faces = np.asarray(mesh.faces, dtype=np.int32)
    return MeshData(
        name=Path(path).stem,
        vertices=verts.astype(np.float32),
        faces=faces,
        normals=np.asarray(mesh.vertex_normals, dtype=np.float32),
        uvs=_extract_uvs(mesh, len(verts)),
        corner_normals=_crease_normals(verts, faces, crease_angle),
    )
