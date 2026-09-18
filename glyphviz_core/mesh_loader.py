"""
Importer for arbitrary external 3D model files (OBJ, STL, ...) used by the
GEO_MESH geometry (see geometry_data.py). Pure data/numpy — no OpenGL/Qt
dependency, so this module is safe to import from anything, including a
future non-GL (e.g. OpenXR/three.js) presentation layer.

Backed by trimesh, which already handles OBJ/STL robustly (and several other
formats — PLY, glTF, ... — for free) without us hand-rolling parsers.
"""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

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


def _validate_without_winding(mesh) -> None:
    """trimesh's validate=True pass, minus the one repair that needs networkx.

    Keeps the part that matters most here -- dropping duplicate and degenerate
    faces, which is what removes the NaN-vertex spike hubs load_mesh_file
    documents -- and makes the winding/normal repair best effort.
    """
    if mesh.is_empty:
        return
    mesh.update_faces(mesh.unique_faces() & mesh.nondegenerate_faces())
    try:
        mesh.fix_normals()
    except (ImportError, ModuleNotFoundError):
        pass
    mesh.remove_infinite_values()
    mesh.merge_vertices()


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
    try:
        mesh = trimesh.load(path, force='mesh', validate=True)
    except (ImportError, ModuleNotFoundError):
        # trimesh's validate step repairs face WINDING as well, and that one
        # repair alone needs networkx -- an OPTIONAL trimesh dependency, which
        # this project now requires explicitly (requirements.txt, and named in
        # every PyInstaller spec's hiddenimports, since trimesh's import of it
        # is inside a try/except a static scan can miss).
        #
        # This branch is therefore the degraded path for an environment where
        # it is missing anyway -- an older install, a partial one, a build that
        # dropped it. It is reached only for a mesh whose winding is already
        # inconsistent (fix_winding returns early otherwise), which is why the
        # gap went unnoticed: most models never reach it, but those that did
        # died on ModuleNotFoundError and simply would not open.
        #
        # Losing the winding repair costs some faces their outward normal, so
        # they shade as if lit from behind. Losing the import costs the model.
        # Take the shading.
        mesh = trimesh.load(path, force='mesh', process=False)
        _validate_without_winding(mesh)
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


# --- Multi-material models ------------------------------------------------
#
# A model authored in a DCC tool is usually not one surface with one look: an
# OBJ carries usemtl groups naming materials in a companion .mtl, each with its
# own colour and (often) its own texture image. load_mesh_file deliberately
# flattens all of that into a single shape wearing the node's own colour and
# texture_id, which is right for a bolt or a tree trunk and wrong for a vehicle
# whose hull, cargo pods and engine glow are six different maps.
#
# The split below turns such a file into SCENE STRUCTURE instead: one part per
# material, each destined for its own node. That is the GlyphViz-shaped answer
# -- every part then selects, recolours, labels, animates and saves like any
# other node, and the renderer needs no new concept, because "one node, one
# geometry, one texture_id" already says everything a part needs.

# A material whose diffuse colour is at or below this is treated as "no usable
# colour" rather than as black paint. Renderer-specific exporters (V-Ray,
# Arnold, Redshift) routinely write Kd 0 0 0 because the real shading lived in
# a node graph the .mtl format cannot express; taking those at face value
# imports a silhouette instead of a model. Textures are unaffected -- this only
# governs the flat-colour fallback.
BLACK_KD_LEVEL = 0


@dataclass
class MaterialSpec:
    """One newmtl block, reduced to what GlyphViz can actually render."""
    name: str
    diffuse: tuple[int, int, int] | None = None   # Kd as 0-255, None when absent
    alpha: int = 255                              # from d / Tr
    texture: str | None = None                    # map_Kd, as a bare file name

    @property
    def is_black(self) -> bool:
        """True when Kd is absent or pure black -- see BLACK_KD_LEVEL."""
        if self.diffuse is None:
            return True
        return max(self.diffuse) <= BLACK_KD_LEVEL


@dataclass
class MeshPart:
    """One material's share of a multi-material model.

    The mesh is expressed in the WHOLE model's units -- every part of one
    import shares a single scale -- and re-centred on its own bounding box, so
    the part has a sensible local origin to rotate about. translate is where
    that origin sits relative to the whole model's centre, in the same units.

    Reassembly is therefore exact with the part node at scale 1:

        world = rig_pos + R @ ((translate + vertex) * rig_scale)

    which is the relation SceneBuilder/Model.assembly already relies on, and
    which tests/test_mesh_parts.py checks against the real transform code
    rather than against a restatement of it here.

    `radius` is the part's own extent in those same whole-model units, and it
    exists for the OTHER route a part can travel. Written out as its own file
    and reloaded through load_mesh_file/load_mesh_folder -- which is how a
    scene folder ships its models -- a part is re-normalized onto its OWN
    bounding box, discarding the shared scale. A node whose scale is set to
    `radius` undoes exactly that, so the two routes place a part identically:

        in memory   node scale = 1          (mesh already in model units)
        from a file node scale = radius     (mesh re-normalized to radius 1)

    Getting this wrong is the classic multi-part import bug -- every part
    arrives the same size, a cockpit as large as the hull it sits in.
    """
    material: str
    mesh: MeshData
    translate: tuple[float, float, float]
    radius: float = 1.0
    spec: MaterialSpec | None = None
    # Faces removed because another material already drew that surface; see
    # _dedupe_across_parts. Reported rather than silent -- a large number is a
    # fact about the FILE that its author should know.
    dropped_faces: int = 0

    @property
    def face_count(self) -> int:
        return len(self.mesh.faces)


def _is_number(tok: str) -> bool:
    try:
        float(tok)
    except ValueError:
        return False
    return True


def _mtl_texture_name(tokens: list[str]) -> str | None:
    """File name from a map_Kd argument list.

    The statement may carry options before the path (map_Kd -s 1 1 1 -o 0 0 0
    hull.png), and the path itself may contain spaces, be Windows-absolute, or
    point outside the model's folder. Only the base name is kept: GlyphViz
    resolves images from the scene's own media/ folder, so an absolute path
    from the author's machine is never useful and frequently misleading.
    """
    i = 0
    while i < len(tokens) and tokens[i].startswith('-'):
        i += 1                                   # the option flag itself
        while i < len(tokens) and _is_number(tokens[i]):
            i += 1                               # ...and its numeric values
    rest = ' '.join(tokens[i:]).strip()
    if not rest:
        return None
    return PurePosixPath(rest.replace(chr(92), '/')).name or None


def parse_mtl(path) -> dict[str, MaterialSpec]:
    """Read a .mtl into {material name: MaterialSpec}.

    Hand-parsed rather than taken from trimesh's loader because what the
    importer needs is the FILE NAME of map_Kd -- to copy the image beside the
    scene as media/ -- and not the decoded pixels trimesh hands back, and
    because the handful of statements that matter here are trivial while
    trimesh's material objects differ between its SimpleMaterial and
    PBRMaterial paths.

    Unknown statements (Ks, Ns, illum, the PBR extensions, ...) are skipped:
    GlyphViz's fixed-function renderer has nowhere to put them.
    """
    mats: dict[str, MaterialSpec] = {}
    cur: MaterialSpec | None = None
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        key, tokens = parts[0].lower(), parts[1:]
        if key == 'newmtl':
            name = ' '.join(tokens).strip()
            cur = MaterialSpec(name=name)
            mats[name] = cur
        elif cur is None:
            continue
        elif key == 'kd' and len(tokens) >= 3:
            try:
                rgb = [float(t) for t in tokens[:3]]
            except ValueError:
                continue
            cur.diffuse = tuple(int(round(max(0.0, min(1.0, c)) * 255)) for c in rgb)
        elif key in ('d', 'tr') and tokens:
            try:
                v = float(tokens[0])
            except ValueError:
                continue
            # d is opacity, Tr is transparency -- the same number inverted.
            cur.alpha = int(round(max(0.0, min(1.0, 1.0 - v if key == 'tr' else v)) * 255))
        elif key == 'map_kd' and tokens:
            cur.texture = _mtl_texture_name(tokens)
    return mats


def find_mtl(obj_path) -> Path | None:
    """Locate the .mtl an OBJ refers to, tolerating a drifted name.

    An exporter writes an mtllib statement, but the name recorded there and
    the file actually shipped disagree more often than one would like: spaces
    become underscores on the way through a zip, case changes across
    platforms, or the file is renamed alongside the .obj. A strict lookup then
    yields a silently untextured, uncoloured import with nothing to explain it
    -- which is exactly what a real V-Ray export was doing (it recorded
    "Cargo Spaceship.mtl" beside a file named Cargo_Spaceship.mtl).

    Resolution order: the recorded name; the same name compared loosely (case
    folded, spaces and underscores equivalent); the OBJ's own stem; and
    finally the only .mtl in the folder, when there is exactly one.
    """
    obj_path = Path(obj_path)
    folder = obj_path.parent
    if not folder.is_dir():
        return None

    recorded: list[str] = []
    try:
        with open(obj_path, 'r', errors='replace') as fh:
            for line in fh:
                if line.startswith('mtllib'):
                    recorded.extend(line.split()[1:])
                elif line.startswith(('v ', 'f ', 'vt ', 'vn ')):
                    break        # past the header; no more mtllib statements
    except OSError:
        return None

    for name in recorded:
        cand = folder / name
        if cand.is_file():
            return cand

    siblings = [p for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() == '.mtl']

    def loose(s: str) -> str:
        return s.lower().replace(' ', '_')

    for name in recorded:
        want = loose(Path(name).name)
        for p in siblings:
            if loose(p.name) == want:
                return p

    stem_match = folder / (obj_path.stem + '.mtl')
    if stem_match.is_file():
        return stem_match

    return siblings[0] if len(siblings) == 1 else None


class _LooseResolver(trimesh.resolvers.FilePathResolver):
    """A sibling-file resolver that also accepts a loosely-matching name.

    trimesh asks this for the mtllib it read; find_mtl's tolerance has to
    reach trimesh too, or the parts come back named material_0 and every
    material-to-part association is lost.
    """

    def get(self, name):
        try:
            return super().get(name)
        except Exception:
            pass
        want = Path(str(name)).name.lower().replace(' ', '_')
        base = Path(self.parent)
        if base.is_dir():
            for q in base.iterdir():
                if q.is_file() and q.name.lower().replace(' ', '_') == want:
                    return q.read_bytes()
        raise FileNotFoundError(name)


# Decimal places a vertex position is rounded to when deciding whether two
# triangles occupy the same place. Matches _crease_normals' own rounding, so
# "the same surface" means the same thing in both passes.
_COINCIDENT_DECIMALS = 5


def _dedupe_across_parts(geoms) -> dict:
    """Keep each distinct triangle SURFACE once, across every material.

    Some exports draw the same surface several times under different
    materials. A Maya scene that has both an object-level material and
    per-face-set materials writes out both assignments, so the model ships two
    or more overlapping copies of itself -- each with its own vertex indices,
    so no index-level duplicate check sees them.

    Rendered, the copies z-fight: the surface flickers between two textures in
    a dense rib pattern, and the copy that covers the whole model hides the
    correctly-textured one under a single wrong image. It also costs whatever
    the multiple is -- the cargo ship this was found on shipped 87,128
    triangles for 24,830 of actual surface.

    The copy kept is the one from the material with the FEWEST faces, on the
    reasoning that the narrow assignment is the specific intent and the
    catch-all is the leftover object-level one. Anything a broad material
    covers ALONE it still keeps, so no geometry is lost -- on that ship the
    catch-all material kept exactly the 3,340 engine triangles no per-material
    assignment claimed.

    Returns {geometry name: boolean face mask}.

    Note a triangle's key is its three positions SORTED, so a triangle and its
    reversed twin count as one surface. GlyphViz draws imported meshes with
    back-face culling off, so a deliberately double-sided pair renders the
    same after one of the two goes -- and stops z-fighting.
    """
    names = [n for n, _ in geoms]
    # Rank parts by specificity, smallest first. The rank is unique per part,
    # so a tie can never leave a triangle with two owners or none.
    order = sorted(range(len(geoms)),
                   key=lambda i: (len(geoms[i][1].faces), names[i]))
    rank = np.empty(len(geoms), dtype=np.int64)
    for r, i in enumerate(order):
        rank[i] = r

    # One global id per distinct vertex POSITION, so a copy carrying its own
    # indices still keys the same.
    all_v = np.vstack([np.round(np.asarray(g.vertices, dtype=np.float64),
                                _COINCIDENT_DECIMALS)
                       for _, g in geoms])
    _, vert_id = np.unique(all_v, axis=0, return_inverse=True)
    vert_id = np.asarray(vert_id).ravel()

    keys, part_of, local_of, offset = [], [], [], 0
    for i, (_, g) in enumerate(geoms):
        faces = np.asarray(g.faces, dtype=np.int64)
        tri = np.sort(vert_id[faces + offset], axis=1)
        keys.append(tri)
        part_of.append(np.full(len(faces), i, dtype=np.int64))
        local_of.append(np.arange(len(faces), dtype=np.int64))
        offset += len(g.vertices)

    keys = np.vstack(keys)
    part_of = np.concatenate(part_of)
    local_of = np.concatenate(local_of)

    _, group = np.unique(keys, axis=0, return_inverse=True)
    group = np.asarray(group).ravel()

    # Winning rank per surface, then the triangles holding it.
    best = np.full(group.max() + 1 if len(group) else 0, np.iinfo(np.int64).max,
                   dtype=np.int64)
    np.minimum.at(best, group, rank[part_of])
    winners = rank[part_of] == best[group]

    # A part may also repeat a surface within itself; keep the first only.
    widx = np.flatnonzero(winners)
    _, first = np.unique(group[widx], return_index=True)
    keep = np.zeros(len(group), dtype=bool)
    keep[widx[first]] = True

    return {names[i]: keep[part_of == i] for i in range(len(geoms))}


def _part_mesh_data(geom, name: str, whole_radius: float, crease_angle: float):
    """One trimesh geometry -> (MeshData in whole-model units, its centre).

    The same validate=True processing load_mesh_file documents at length is
    applied here, per part: without it a part carrying NaN/Inf vertices keeps
    the faces that referenced them, which remap onto vertex 0 and fan a hub of
    spikes across the model.
    """
    try:
        geom.process(validate=True)
    except (ImportError, ModuleNotFoundError):
        _validate_without_winding(geom)      # see load_mesh_file
    verts = np.asarray(geom.vertices, dtype=np.float64)
    if len(verts) == 0 or len(geom.faces) == 0:
        return None, None

    lo, hi = verts.min(axis=0), verts.max(axis=0)
    centre = (lo + hi) / 2.0
    # Re-centre on this part, but scale by the WHOLE model -- that is what
    # keeps one uniform scale across every part of an import, so the rig node
    # carries the model's size and no part needs a scale of its own.
    local = (verts - centre) / whole_radius

    faces = np.asarray(geom.faces, dtype=np.int32)
    data = MeshData(
        name=name,
        vertices=local.astype(np.float32),
        faces=faces,
        normals=np.asarray(geom.vertex_normals, dtype=np.float32),
        uvs=_extract_uvs(geom, len(local)),
        # Creases are found within a part, so a material boundary always reads
        # as a hard edge. That is nearly always what it is (different material,
        # different panel); a single smooth surface deliberately split across
        # two materials is the case this cannot shade as one.
        corner_normals=_crease_normals(local, faces, crease_angle),
    )
    return data, centre


def load_mesh_parts(path, crease_angle: float = DEFAULT_CREASE_ANGLE,
                    dedupe: bool = True) -> list[MeshPart]:
    """Split a multi-material model into one MeshPart per material.

    Returns [] when the file has no material split to exploit -- a single
    material, or a format that carries none -- so a caller can simply fall
    back to load_mesh_file rather than special-casing the common model.

    Parts come back largest first: the part order becomes node order, and a
    model reads far better in the node table when its hull is the first row
    rather than its running lights.

    With *dedupe* on (the default), a surface drawn under more than one
    material is kept once -- see _dedupe_across_parts for why that is common
    and what it costs to leave in. Each part records how many of its faces
    that dropped, in MeshPart.dropped_faces. Pass dedupe=False to import the
    file exactly as authored.
    """
    path = Path(path)
    scene = trimesh.load(
        str(path),
        resolver=_LooseResolver(str(path.parent)),
        process=False,          # per-part processing happens in _part_mesh_data
        skip_materials=False,
    )
    if not isinstance(scene, trimesh.Scene) or len(scene.geometry) < 2:
        return []

    geoms = [(name, g) for name, g in scene.geometry.items()
             if len(getattr(g, 'faces', ())) > 0]
    if len(geoms) < 2:
        return []

    # One centre and one radius for the whole model, measured before anything
    # is split: every part is then expressed in the same units, and the parts
    # reassemble into exactly the model load_mesh_file would have produced.
    allv = np.vstack([np.asarray(g.vertices, dtype=np.float64) for _, g in geoms])
    lo, hi = allv.min(axis=0), allv.max(axis=0)
    whole_centre = (lo + hi) / 2.0
    whole_radius = float(np.max(np.linalg.norm(allv - whole_centre, axis=1)))
    if whole_radius <= 1e-12:
        return []

    mtl_path = find_mtl(path) if path.suffix.lower() == '.obj' else None
    mats = parse_mtl(mtl_path) if mtl_path else {}

    # Drop overlapping copies BEFORE anything is measured per part: a part's
    # own bounding box, and so its translate and radius, must describe what it
    # will actually draw.
    masks = _dedupe_across_parts(geoms) if dedupe else {}
    dropped = {}
    for name, geom in geoms:
        mask = masks.get(name)
        if mask is None or mask.all():
            dropped[name] = 0
            continue
        dropped[name] = int((~mask).sum())
        geom.update_faces(mask)
    geoms = [(n, g) for n, g in geoms if len(g.faces) > 0]

    parts: list[MeshPart] = []
    for name, geom in geoms:
        data, centre = _part_mesh_data(geom, name, whole_radius, crease_angle)
        if data is None:
            continue
        verts = data.vertices
        parts.append(MeshPart(
            material=name,
            mesh=data,
            translate=tuple((centre - whole_centre) / whole_radius),
            # Measured the way load_mesh_file measures, so a part written out
            # and reloaded scales back to exactly this.
            radius=float(np.max(np.linalg.norm(verts, axis=1))) if len(verts) else 1.0,
            spec=mats.get(name),
            dropped_faces=dropped.get(name, 0),
        ))

    parts.sort(key=lambda p: p.face_count, reverse=True)
    return parts if len(parts) >= 2 else []
