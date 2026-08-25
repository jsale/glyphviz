"""
Interior geometries — the shapes seen from WITHIN (2026-08-24).

Three shapes that enclose a volume gained an interior twin, so a video or
photo texture can be viewed from inside: a 360° sphere, a cylindrical
panorama (with or without end caps), and a video room.

The contract that matters — and the one this file pins — is that an interior
surface is NOT merely "back-face culling turned off". Viewing the inside of an
outward-mapped surface is inherently a MIRROR view, so a node that only
stopped culling would play every video backwards; the fix is mirrored
geometry, which lives in the compiled display list. Two consequences get
tested here:

  * faces wind CCW as seen from INSIDE and carry inward normals, so
    paintGL's GL_CULL_FACE(GL_BACK) keeps the interior surface;
  * the texture reads FORWARDS from inside — expressed as a handedness test
    on each face's (u, v) edges, which is exactly what "not mirrored" means
    without needing pixels.

No GL context is involved. geometry.py pulls the GL entry points into its own
module namespace via `from OpenGL.GL import *`, so swapping the callables for
recorders captures the exact call stream each builder emits — the same trick
tests/test_pin_geometry.py and tests/test_geometry_textures.py use.

The sphere and cylinder are reflections of the existing builders rather than
new shapes (see geometry._mirrored), so what is pinned for them is the
reflection itself plus the fact that they compile to lists of their own; their
tessellation is already covered by its exterior twin's tests. The rendered
result was verified separately against a chiral texture: an unmirrored
interior showed it reversed, these show it forwards.
"""
import pytest

from glyphviz_core.geometry_data import (
    CYLINDER_INTERIOR_BY_CAPS, GEO_COUNT, GEO_CUBE, GEO_CUBE_INTERIOR,
    GEO_CYLINDER, GEO_CYLINDER_INTERIOR, GEO_CYLINDER_INTERIOR_OPEN,
    GEO_NAMES, GEO_SPHERE, GEO_SPHERE_INTERIOR, INTERIOR_GEOMETRIES,
    has_caps, with_caps,
)

geometry = pytest.importorskip('glyphviz_gl.geometry')

INTERIORS = (GEO_CUBE_INTERIOR, GEO_SPHERE_INTERIOR,
             GEO_CYLINDER_INTERIOR, GEO_CYLINDER_INTERIOR_OPEN)


class _Recorder:
    """Stands in for the GL entry points, logging every call in order."""

    def __init__(self):
        self.calls: list[tuple] = []
        self._next_list = 1

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

    def vertices(self):
        return [c[1:] for c in self.calls if c[0] == 'glVertex3f']

    def quads(self):
        """The emitted vertices grouped four at a time, each paired with the
        texcoord latched when it was sent."""
        pairs, uv = [], None
        for call in self.calls:
            if call[0] == 'glTexCoord2f':
                uv = call[1:]
            elif call[0] == 'glVertex3f':
                pairs.append((uv, call[1:]))
        return [pairs[i:i + 4] for i in range(0, len(pairs), 4)]

    def normals(self):
        return [c[1:] for c in self.calls if c[0] == 'glNormal3f']


@pytest.fixture
def rec(monkeypatch):
    r = _Recorder()
    r.install(monkeypatch)
    return r


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _cross(a, b):
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0])


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _centre(verts):
    return tuple(sum(v[i] for v in verts) / len(verts) for i in range(3))


# ---------------------------------------------------------------------------
# The id table
# ---------------------------------------------------------------------------

def test_every_interior_id_is_named_and_in_range():
    """An unnamed id would crash the Geometry dropdowns, which build
    themselves from range(GEO_COUNT) and index GEO_NAMES directly."""
    for geo_id in INTERIORS:
        assert geo_id < GEO_COUNT
        assert GEO_NAMES[geo_id]
    assert set(INTERIOR_GEOMETRIES) == set(INTERIORS)


def test_interior_ids_sit_past_every_pre_existing_id():
    """Appended, never renumbered: ids 0-22 are ANTz's own enum and 23-28 are
    the earlier GlyphViz extensions, all of them written into saved files."""
    assert min(INTERIORS) == 29


def test_caps_helpers_pair_the_two_cylinder_ids():
    assert has_caps(GEO_CYLINDER_INTERIOR)
    assert not has_caps(GEO_CYLINDER_INTERIOR_OPEN)
    assert with_caps(GEO_CYLINDER_INTERIOR, False) == GEO_CYLINDER_INTERIOR_OPEN
    assert with_caps(GEO_CYLINDER_INTERIOR_OPEN, True) == GEO_CYLINDER_INTERIOR
    assert set(CYLINDER_INTERIOR_BY_CAPS.values()) == {
        GEO_CYLINDER_INTERIOR, GEO_CYLINDER_INTERIOR_OPEN}


@pytest.mark.parametrize('geo_id', [GEO_SPHERE, GEO_CUBE, GEO_CYLINDER,
                                    GEO_CUBE_INTERIOR])
def test_with_caps_leaves_other_geometries_alone(geo_id):
    """The checkbox runs over a whole selection; a mixed one must not have its
    spheres quietly turned into cylinders."""
    assert with_caps(geo_id, True) == geo_id
    assert with_caps(geo_id, False) == geo_id
    assert not has_caps(geo_id)


# ---------------------------------------------------------------------------
# The interior cube — built face by face, so every face is checkable
# ---------------------------------------------------------------------------

def test_cube_interior_draws_six_quads(rec):
    geometry._draw_cube_interior()
    assert len(rec.vertices()) == 24
    assert len(rec.quads()) == 6
    assert rec.names().count('glBegin') == 1     # one batch, not six


def test_cube_interior_faces_wind_ccw_from_inside(rec):
    """The whole point: paintGL culls GL_BACK, so an interior surface must
    present its front face to a viewer at the centre. Equivalently, each
    face's geometric normal points AT the origin."""
    geometry._draw_cube_interior()
    for quad in rec.quads():
        verts = [v for _uv, v in quad]
        n = _cross(_sub(verts[1], verts[0]), _sub(verts[2], verts[0]))
        assert _dot(n, _centre(verts)) < 0


def test_cube_interior_normals_point_inward(rec):
    """Lighting has to agree with the winding, or the interior renders as if
    lit from behind."""
    geometry._draw_cube_interior()
    for normal, quad in zip(rec.normals(), rec.quads()):
        assert _dot(normal, _centre([v for _uv, v in quad])) < 0
        assert _dot(normal, normal) == pytest.approx(1.0)


def test_cube_interior_faces_are_the_six_axis_directions(rec):
    geometry._draw_cube_interior()
    assert sorted(rec.normals()) == sorted([
        (1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, -1.0),
    ])


def test_cube_interior_texture_reads_forwards_from_inside(rec):
    """"Not mirrored", stated without pixels: a viewer inside sees u to their
    right and v upward, so (u_edge, v_edge, toward-the-viewer) must be a
    right-handed triple — i.e. u x v points at the origin. Run the same test
    on the exterior cube and it comes out the other way round, which is
    exactly the bug that back-face culling alone cannot fix."""
    geometry._draw_cube_interior(textured=True)
    for quad in rec.quads():
        by_uv = {uv: v for uv, v in quad}
        p00, p10, p01 = by_uv[(0.0, 0.0)], by_uv[(1.0, 0.0)], by_uv[(0.0, 1.0)]
        handed = _cross(_sub(p10, p00), _sub(p01, p00))
        assert _dot(handed, _centre([v for _uv, v in quad])) < 0


def test_exterior_cube_reads_forwards_from_OUTSIDE(rec):
    """The control for the test above — and the reason the interior cube is
    built by hand instead of reflecting this one: a reflection would fix four
    faces and leave the two perpendicular to the mirror axis backwards."""
    geometry._draw_cube(True, True)
    for quad in rec.quads():
        by_uv = {uv: v for uv, v in quad}
        p00, p10, p01 = by_uv[(0.0, 0.0)], by_uv[(1.0, 0.0)], by_uv[(0.0, 1.0)]
        handed = _cross(_sub(p10, p00), _sub(p01, p00))
        assert _dot(handed, _centre([v for _uv, v in quad])) > 0


def test_cube_interior_every_face_maps_the_whole_texture(rec):
    geometry._draw_cube_interior(textured=True)
    for quad in rec.quads():
        assert sorted(uv for uv, _v in quad) == [
            (0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)]


def test_untextured_cube_interior_emits_no_texcoords(rec):
    geometry._draw_cube_interior()
    assert rec.vertices()
    assert not [c for c in rec.calls if c[0] == 'glTexCoord2f']


def test_cube_interior_occupies_the_same_corners_as_the_cube(rec):
    """Same shape, turned outside in — not a differently-sized box."""
    geometry._draw_cube_interior()
    interior = {tuple(round(c, 9) for c in v) for v in rec.vertices()}
    assert interior == {
        tuple(round(c, 9) for c in v) for v in geometry._CUBE_VERTS}


# ---------------------------------------------------------------------------
# Sphere / cylinder — reflections of the existing builders
# ---------------------------------------------------------------------------

def test_mirrored_reflects_through_x_and_restores_the_matrix(rec):
    """A negative-determinant scale is what flips winding AND normals AND the
    texture's handedness in one operation. It is recorded into the display
    list like any other GL call, so the reflection costs nothing per frame."""
    geometry._mirrored(lambda: geometry.glVertex3f(1.0, 2.0, 3.0))
    assert rec.names() == ['glPushMatrix', 'glScalef', 'glVertex3f',
                           'glPopMatrix']
    scale = next(c for c in rec.calls if c[0] == 'glScalef')
    assert scale[1:] == (-1.0, 1.0, 1.0)
    assert scale[1] * scale[2] * scale[3] < 0        # determinant is negative


def test_cylinder_caps_are_two_disks(rec):
    geometry._draw_cylinder(True, caps=True)
    assert rec.names().count('gluDisk') == 2


def test_open_cylinder_draws_the_tube_and_nothing_else(rec):
    geometry._draw_cylinder(True, caps=False)
    assert rec.names().count('gluDisk') == 0
    assert rec.names().count('gluCylinder') == 1


def test_caps_default_leaves_the_existing_cylinder_untouched(rec):
    """Every pre-existing call site omits `caps`; the default has to keep
    drawing the closed cylinder those scenes already show."""
    geometry._draw_cylinder(True)
    assert rec.names().count('gluDisk') == 2


# ---------------------------------------------------------------------------
# The display-list tables draw() actually looks in
# ---------------------------------------------------------------------------

def test_setup_compiles_a_list_for_every_interior_geometry(rec):
    """draw() falls back to GEO_SPHERE's list on a miss, so a missing entry
    would silently render an ordinary sphere rather than raising."""
    r = geometry.GeoRenderer()
    r.setup()
    for geo_id in INTERIORS:
        assert geo_id in r._lists, GEO_NAMES[geo_id]
        assert r._lists[geo_id] != r._lists[GEO_SPHERE]


def test_setup_compiles_TEXTURED_lists_too(rec):
    """The textured table is the one that matters here — an interior shape
    exists to carry an image, and a miss falls back to the untextured list."""
    r = geometry.GeoRenderer()
    r.setup()
    for geo_id in INTERIORS:
        assert geo_id in r._tex_lists, GEO_NAMES[geo_id]
        assert r._tex_lists[geo_id] != r._lists[geo_id]


def test_capped_and_open_cylinders_are_separate_lists(rec):
    """The caps checkbox swaps ids; if both ids shared a list it would do
    nothing on screen."""
    r = geometry.GeoRenderer()
    r.setup()
    assert r._lists[GEO_CYLINDER_INTERIOR] != r._lists[GEO_CYLINDER_INTERIOR_OPEN]
    assert (r._tex_lists[GEO_CYLINDER_INTERIOR]
            != r._tex_lists[GEO_CYLINDER_INTERIOR_OPEN])


def test_interior_ids_do_not_disturb_the_exterior_ones(rec):
    r = geometry.GeoRenderer()
    r.setup()
    for geo_id in (GEO_CUBE, GEO_SPHERE, GEO_CYLINDER):
        assert geo_id in r._lists and geo_id in r._tex_lists
        assert r._lists[geo_id] != r._lists[
            {GEO_CUBE: GEO_CUBE_INTERIOR, GEO_SPHERE: GEO_SPHERE_INTERIOR,
             GEO_CYLINDER: GEO_CYLINDER_INTERIOR}[geo_id]]


@pytest.mark.parametrize('geo_id', INTERIORS)
def test_draw_binds_the_texture_and_calls_the_interior_list(rec, geo_id):
    r = geometry.GeoRenderer()
    r.setup()
    rec.calls.clear()
    r.draw(geo_id, 1.0, 1.0, 1.0, gl_tex_name=9)
    called = [c[1] for c in rec.calls if c[0] == 'glCallList']
    assert called == [r._tex_lists[geo_id]], GEO_NAMES[geo_id]
    assert ('glBindTexture', geometry.GL_TEXTURE_2D, 9) in rec.calls


# ---------------------------------------------------------------------------
# Brightness, and the GL_LIGHTING state contract
# ---------------------------------------------------------------------------

def test_unlit_saves_and_restores_rather_than_re_enabling(rec):
    """The colour-ID pick pass turns lighting off for its whole render and
    relies on it staying off, and interior ids are NOT covered by the
    wire→solid pick substitution, so they run in that pass too. A bare
    glEnable(GL_LIGHTING) at the end would bleed lit shading into every node
    picked afterwards and corrupt their ID colours — the GEO_POINT bug.

    It also has to be glPushAttrib and not a glIsEnabled/restore pair: these
    builders are compiled into display lists, where a query runs once at
    COMPILE time and would bake in whatever was true then."""
    geometry._unlit(lambda: geometry.glVertex3f(0.0, 0.0, 0.0))
    assert rec.names() == ['glPushAttrib', 'glDisable', 'glVertex3f',
                           'glPopAttrib']
    assert ('glPushAttrib', geometry.GL_LIGHTING_BIT) in rec.calls
    assert ('glDisable', geometry.GL_LIGHTING) in rec.calls
    assert ('glEnable', geometry.GL_LIGHTING) not in rec.calls


def _list_body(rec, display_list):
    """The calls compiled into *display_list*, i.e. between its glNewList and
    the glEndList that closes it."""
    start = None
    for i, call in enumerate(rec.calls):
        if call[0] == 'glNewList' and call[1] == display_list:
            start = i
            break
    assert start is not None, display_list
    end = next(i for i in range(start, len(rec.calls))
               if rec.calls[i][0] == 'glEndList')
    return rec.calls[start + 1:end]


@pytest.mark.parametrize('geo_id', INTERIORS)
def test_every_interior_list_is_compiled_unlit(rec, geo_id):
    """An interior surface exists to carry an image and has to carry it at
    full brightness — the same call the World Grid's globe makes. Lighting it
    is not on the table: normals survive the reflection still pointing
    outward (measured: a white interior sphere came back at 0.505 grey,
    exactly the two ambient terms with no diffuse at all), and flipping them
    would light it from GL_LIGHT0, whose position is set against an identity
    modelview and is therefore an eye-space headlight — a bright patch that
    would slide across the video as the viewer turned."""
    r = geometry.GeoRenderer()
    r.setup()
    for dl in (r._lists[geo_id], r._tex_lists[geo_id]):
        body = _list_body(rec, dl)
        names = [c[0] for c in body]
        assert ('glDisable', geometry.GL_LIGHTING) in body, GEO_NAMES[geo_id]
        assert names.count('glPushAttrib') == names.count('glPopAttrib') == 1
        assert ('glEnable', geometry.GL_LIGHTING) not in body


@pytest.mark.parametrize('geo_id', INTERIORS)
def test_interiors_stay_single_sided(rec, geo_id):
    """Interior is a reversed surface, not a two-sided one: culling stays ON,
    so there is still exactly one fragment per pixel and alpha blending on a
    translucent node keeps behaving. GEO_MESH is the only geometry that turns
    culling off, and it stays the only one."""
    r = geometry.GeoRenderer()
    r.setup()
    rec.calls.clear()
    r.draw(geo_id, 1.0, 1.0, 1.0, gl_tex_name=9)
    assert ('glDisable', geometry.GL_CULL_FACE) not in rec.calls
