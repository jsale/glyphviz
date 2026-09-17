"""
Textured meshes, and the meshes/ folder convention (2026-09-17).

Two gaps closed together, because neither is much use alone:

  * An imported GEO_MESH carried vertices, faces and normals and nothing
    else, so `texture_id` did nothing on a mesh node -- draw() returned before
    it even computed `textured`. A mesh's only "material" was its flat
    color_r/g/b. UVs now survive the import and get baked into the display
    list, and a mesh with UVs takes the textured path.

  * A mesh_id only ever meant "the Nth file imported by hand this session",
    which is not a property of the scene file -- so a CSV using GEO_MESH could
    not be reopened, let alone shipped to anyone. mesh_id is now the file's
    1-based position in a sorted meshes/ folder beside the node CSV, exactly
    the rule texture_id already uses for media/.

The UV-less case is pinned as hard as the UV case: a mesh with no texture
coordinates must stay UNtextured even when its node names a texture, because
every vertex would otherwise inherit whatever texcoord happened to be current
and smear a single texel over the whole model -- visibly worse than the flat
color it replaced.

No GL context is involved; the GL entry points are swapped for recorders, the
same trick tests/test_interior_geometry.py and tests/test_pin_geometry.py use.
"""
import numpy as np
import pytest

from glyphviz_core.geometry_data import GEO_MESH, GEO_SPHERE
from glyphviz_core.mesh_loader import MeshData, load_mesh_file

geometry = pytest.importorskip('glyphviz_gl.geometry')


# --- a GL recorder ----------------------------------------------------------

class _Recorder:
    def __init__(self):
        self.calls: list[tuple] = []
        self._next_list = 1
        self.enabled: set = set()

    def install(self, monkeypatch):
        for name in dir(geometry):
            if not name.startswith('gl') or name.startswith('GL'):
                continue
            if not callable(getattr(geometry, name)):
                continue
            monkeypatch.setattr(geometry, name, self._stub(name), raising=False)

    def _stub(self, name):
        def fn(*args):
            self.calls.append((name,) + args)
            if name == 'glGenLists':
                dl = self._next_list
                self._next_list += 1
                return dl
            if name == 'glIsEnabled':
                return False
            if name == 'gluNewQuadric':
                return object()
            return None
        return fn

    def names(self):
        return [c[0] for c in self.calls]

    def reset(self):
        self.calls.clear()

    def pairs(self):
        """Each emitted vertex paired with the texcoord latched before it."""
        out, uv = [], None
        for call in self.calls:
            if call[0] == 'glTexCoord2f':
                uv = call[1:]
            elif call[0] == 'glVertex3f':
                out.append((uv, call[1:]))
        return out


@pytest.fixture
def rec(monkeypatch):
    r = _Recorder()
    r.install(monkeypatch)
    return r


# --- fixtures ---------------------------------------------------------------

def _quad_mesh(with_uvs: bool) -> MeshData:
    """Two triangles in the z=0 plane, optionally UV-mapped 0..1."""
    verts = np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]],
                     dtype=np.float32)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    normals = np.tile(np.array([0, 0, 1], dtype=np.float32), (4, 1))
    uvs = np.array([[0, 0], [1, 0], [1, 1], [0, 1]],
                   dtype=np.float32) if with_uvs else None
    return MeshData(name='quad', vertices=verts, faces=faces,
                    normals=normals, uvs=uvs)


OBJ_UV = """\
v -1 -1 0
v  1 -1 0
v  1  1 0
v -1  1 0
vt 0 0
vt 1 0
vt 1 1
vt 0 1
vn 0 0 1
f 1/1/1 2/2/1 3/3/1
f 1/1/1 3/3/1 4/4/1
"""

OBJ_NO_UV = """\
v -1 -1 0
v  1 -1 0
v  1  1 0
vn 0 0 1
f 1//1 2//1 3//1
"""


# --- the loader keeps UVs ---------------------------------------------------

def test_loader_extracts_uvs(tmp_path):
    path = tmp_path / 'uv.obj'
    path.write_text(OBJ_UV)
    mesh = load_mesh_file(str(path))
    assert mesh.has_uvs
    assert mesh.uvs.shape == (len(mesh.vertices), 2)
    # the corners of a 0..1 map, in some order
    corners = {tuple(np.round(uv, 5)) for uv in mesh.uvs}
    assert corners == {(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)}


def test_loader_reports_no_uvs_when_file_has_none(tmp_path):
    path = tmp_path / 'plain.obj'
    path.write_text(OBJ_NO_UV)
    mesh = load_mesh_file(str(path))
    assert not mesh.has_uvs
    assert mesh.uvs is None


def test_loader_keeps_uv_seams(tmp_path):
    """A position that carries two different UVs must NOT be welded into one
    vertex -- that is what a texture seam is, and welding it would drag the
    map across the cut. (trimesh's merge_vertices honors this; the test exists
    so a future change to load_mesh_file's processing flags can't lose it.)"""
    path = tmp_path / 'seam.obj'
    path.write_text(
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 2 0 0\nv 2 1 0\n"
        "vt 0 0\nvt 1 0\nvt 1 1\nvt 0 0\nvt 0 1\n"
        "f 1/1 2/2 3/3\nf 2/4 4/4 5/5\n"
    )
    mesh = load_mesh_file(str(path))
    assert mesh.has_uvs
    # the shared position appears twice, once per UV
    rounded = [tuple(np.round(v, 5)) for v in mesh.vertices]
    doubled = [p for p in set(rounded) if rounded.count(p) > 1]
    assert doubled, "the seam vertex was welded away"


def test_loader_ignores_uvs_that_do_not_match_the_vertices():
    """A visual whose UV array is the wrong length can't be indexed by the
    face arrays, so it is dropped rather than risking an out-of-range read
    inside glNewList (where there is no way to recover)."""
    from glyphviz_core.mesh_loader import _extract_uvs

    class _Visual:
        uv = np.zeros((3, 2), dtype=np.float32)

    class _Mesh:
        visual = _Visual()

    assert _extract_uvs(_Mesh(), 4) is None
    assert _extract_uvs(_Mesh(), 3) is not None


# --- the display list carries the coordinates -------------------------------

def test_register_mesh_emits_texcoords(rec):
    geo = geometry.GeoRenderer()
    geo.register_mesh(7, _quad_mesh(with_uvs=True))
    pairs = rec.pairs()
    assert len(pairs) == 6            # 2 triangles
    assert all(uv is not None for uv, _ in pairs)
    # every vertex got ITS OWN uv, not a latched neighbour's
    expected = {(-1.0, -1.0, 0.0): (0.0, 0.0), (1.0, -1.0, 0.0): (1.0, 0.0),
                (1.0, 1.0, 0.0): (1.0, 1.0), (-1.0, 1.0, 0.0): (0.0, 1.0)}
    for uv, v in pairs:
        assert uv == expected[v]


def test_register_mesh_without_uvs_emits_no_texcoords(rec):
    geo = geometry.GeoRenderer()
    geo.register_mesh(7, _quad_mesh(with_uvs=False))
    assert 'glTexCoord2f' not in rec.names()


# --- draw() takes the textured path ----------------------------------------

def _draw(rec, geo, mesh_id, tex):
    rec.reset()
    geo.draw(GEO_MESH, 1.0, 1.0, 1.0, gl_tex_name=tex, mesh_id=mesh_id)
    return rec


def _binds(rec):
    return [c for c in rec.calls if c[0] == 'glBindTexture']


def test_uv_mesh_binds_its_texture(rec):
    geo = geometry.GeoRenderer()
    geo._ready = True
    geo.register_mesh(1, _quad_mesh(with_uvs=True))
    _draw(rec, geo, 1, tex=42)
    assert ('glBindTexture', geometry.GL_TEXTURE_2D, 42) in rec.calls
    # and releases it again, so the next node doesn't inherit the binding
    assert _binds(rec)[-1][2] == 0
    names = rec.names()
    assert names.index('glEnable') < names.index('glCallList')


def test_uv_mesh_untextured_when_node_names_no_texture(rec):
    geo = geometry.GeoRenderer()
    geo._ready = True
    geo.register_mesh(1, _quad_mesh(with_uvs=True))
    _draw(rec, geo, 1, tex=0)
    assert not _binds(rec)
    assert 'glCallList' in rec.names()


def test_mesh_without_uvs_stays_untextured(rec):
    """The load-bearing one: no coordinates means no texturing, even with a
    texture_id set. One smeared texel would be worse than the flat color."""
    geo = geometry.GeoRenderer()
    geo._ready = True
    geo.register_mesh(1, _quad_mesh(with_uvs=False))
    _draw(rec, geo, 1, tex=42)
    assert not _binds(rec)
    assert 'glCallList' in rec.names()


def test_mesh_still_disables_culling(rec):
    """Pre-existing contract: imported files can't be trusted to wind CCW, so
    the cull is off around a mesh -- and must be restored afterwards."""
    geo = geometry.GeoRenderer()
    geo._ready = True
    geo.register_mesh(1, _quad_mesh(with_uvs=True))
    _draw(rec, geo, 1, tex=42)
    assert ('glDisable', geometry.GL_CULL_FACE) in rec.calls
    assert ('glEnable', geometry.GL_CULL_FACE) in rec.calls
    # the cull is restored after the draw, not before it
    names = rec.names()
    last_enable = max(i for i, c in enumerate(rec.calls)
                      if c == ('glEnable', geometry.GL_CULL_FACE))
    assert last_enable > names.index('glCallList')


def test_unknown_mesh_id_falls_back_to_sphere(rec):
    """Pre-existing contract, re-pinned because the textured branch sits in
    front of it: a CSV naming a mesh nobody has loaded draws the sphere
    fallback rather than nothing at all."""
    geo = geometry.GeoRenderer()
    geo._ready = True
    geo._lists[GEO_SPHERE] = 99
    _draw(rec, geo, 404, tex=0)
    assert ('glCallList', 99) in rec.calls


# --- crease-angle normals ---------------------------------------------------
#
# The third gap, and the one that made every imported hard-surface model look
# wrong: load_mesh_file welds duplicate vertices (validate=True), so trimesh's
# per-vertex normals averaged every face at a corner. A cube arrived as 8
# vertices all pointing diagonally outward and shaded like a beach ball.

def test_cube_keeps_its_corners_square(tmp_path):
    trimesh = pytest.importorskip('trimesh')
    path = tmp_path / 'cube.obj'
    trimesh.creation.box(extents=(2, 2, 2)).export(str(path))

    mesh = load_mesh_file(str(path))
    assert mesh.corner_normals is not None
    got = np.unique(np.round(mesh.corner_normals.reshape(-1, 3), 3), axis=0)
    want = np.array([[-1, 0, 0], [0, -1, 0], [0, 0, -1],
                     [0, 0, 1], [0, 1, 0], [1, 0, 0]], dtype=float)
    assert np.array_equal(got, want), "cube corners were smoothed"

    # the control: the per-vertex normals it replaces really are the diagonal
    # averages, i.e. this test would fail without the feature
    assert np.allclose(np.abs(mesh.normals), 0.5774, atol=1e-3)


def test_smooth_surface_stays_smooth(tmp_path):
    """A crease angle that squared off a sphere would be no better than the
    bug it fixes -- 40 degrees is well above an icosphere's facet angle, so
    corner normals must track the smoothed per-vertex ones."""
    trimesh = pytest.importorskip('trimesh')
    path = tmp_path / 'sphere.obj'
    trimesh.creation.icosphere(subdivisions=3).export(str(path))

    mesh = load_mesh_file(str(path))
    corner = mesh.corner_normals.reshape(-1, 3)
    vertex = mesh.normals[mesh.faces.ravel()]
    assert np.abs(corner - vertex).max() < 0.02


def test_cylinder_is_round_with_hard_caps(tmp_path):
    """Both behaviours on one model, which is the whole point of doing this
    per corner rather than per vertex: the rim vertices are shared between a
    flat cap and a curved barrel and must shade differently on each side."""
    trimesh = pytest.importorskip('trimesh')
    path = tmp_path / 'cyl.obj'
    trimesh.creation.cylinder(radius=1.0, height=2.0, sections=24).export(str(path))

    corner = load_mesh_file(str(path)).corner_normals.reshape(-1, 3)
    # caps: exactly axial, not tilted by the barrel next to them
    assert (np.abs(corner - [0, 0, 1]).max(axis=1) < 1e-4).any()
    assert (np.abs(corner - [0, 0, -1]).max(axis=1) < 1e-4).any()
    # barrel: purely radial, not tilted by the cap next to it
    assert (np.abs(corner[:, 2]) < 1e-4).sum() > 0


def test_crease_angle_is_adjustable(tmp_path):
    trimesh = pytest.importorskip('trimesh')
    path = tmp_path / 'cube.obj'
    trimesh.creation.box(extents=(2, 2, 2)).export(str(path))

    # 180 degrees smooths everything: every corner sharing a vertex agrees,
    # which is exactly what "one smoothing group" means. (The values are NOT
    # trimesh's 0.577 diagonals -- this average is area-weighted and trimesh's
    # is not -- so the property, not the number, is what gets pinned.)
    smooth = load_mesh_file(str(path), crease_angle=180.0)
    corner = smooth.corner_normals.reshape(-1, 3)
    for vert in np.unique(smooth.faces):
        at_vert = corner[smooth.faces.ravel() == vert]
        assert np.allclose(at_vert, at_vert[0], atol=1e-5)
    assert len(np.unique(np.round(corner, 4), axis=0)) == 8   # one per cube corner
    # 0 degrees facets everything: each corner takes its own face normal
    faceted = load_mesh_file(str(path), crease_angle=0.0)
    per_face = faceted.corner_normals
    assert np.allclose(per_face[:, 0], per_face[:, 1])
    assert np.allclose(per_face[:, 0], per_face[:, 2])


def test_degenerate_mesh_falls_back_to_vertex_normals():
    """A zero-area face has no direction to contribute; the corner keeps its
    own face normal rather than a NaN."""
    from glyphviz_core.mesh_loader import _crease_normals
    verts = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=float)
    faces = np.array([[0, 1, 2]], dtype=np.int32)   # collinear -> zero area
    assert _crease_normals(verts, faces, 40.0) is None
    assert _crease_normals(verts, np.zeros((0, 3), dtype=np.int32), 40.0) is None


def test_register_mesh_emits_corner_normals(rec):
    """The renderer must actually send the crease normals, not the per-vertex
    array sitting next to them."""
    mesh = _quad_mesh(with_uvs=True)
    mesh.corner_normals = np.tile(
        np.array([0.0, 1.0, 0.0], dtype=np.float32), (2, 3, 1))
    geo = geometry.GeoRenderer()
    geo.register_mesh(3, mesh)
    sent = [c[1:] for c in rec.calls if c[0] == 'glNormal3f']
    assert sent and all(n == (0.0, 1.0, 0.0) for n in sent)


def test_a_texture_seam_is_not_a_geometric_crease(tmp_path):
    """Two triangles forming one flat surface, split by a UV seam.

    The seam makes the shared edge two separate VERTICES — that is what a seam
    is, and load_mesh_file keeps them apart so the UVs survive. They are not
    separate geometry though, and indexing the crease pass by vertex gave each
    side only its own face to average, shading a hard line down a perfectly
    flat surface. On a lofted tube that is a visible stripe from end to end.

    Creases are therefore decided on POSITION. GlyphViz Web merges by position
    here too; once this matched, the two apps agreed on a 1,812-triangle
    airframe to 0.05 degrees mean (0 median, 0.21 max — float32 noise). Before
    it, the seam corners disagreed by up to 14 degrees.
    """
    path = tmp_path / 'seam.obj'
    path.write_text(
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n"
        # the shared edge carries u=1 on one side and u=0 on the other
        "vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nvt 0 0\nvt 0 1\n"
        "f 1/1 2/2 3/3\n"
        "f 1/5 3/6 4/4\n"
    )
    mesh = load_mesh_file(str(path))
    corner = mesh.corner_normals.reshape(-1, 3)
    # One flat surface: every corner points the same way, seam or no seam.
    assert np.allclose(np.abs(corner), np.abs(corner[0]), atol=1e-5), \
        "a texture seam shaded as a crease"
