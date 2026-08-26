"""
Flat Ring (2026-08-26) — the torus with a rectangular cross-section.

Two contracts are pinned here, and they are the two reasons the shape exists
rather than being a squashed torus:

  * **It is the torus's own extents, restated as a box.** `ring_dims` and
    `torus_radii` agree, so Torus <-> Flat Ring is a change of look only:
    identical silhouette, identical bounding extents, and `_torus_offset`
    places a TOPO_TORUS parent's children identically whichever the parent
    wears. Anything that broke that would silently relocate children in every
    scene that swapped the geometry.

  * **No face is mirrored.** Each of the four faces carries a full 0..1 UV
    span of its own so a strip of degree markings lands undistorted on it, and
    each face's u runs in the direction that reads forwards from that face's
    natural viewing side. Expressed without pixels: (du x dv) points along the
    face normal on all four faces — the same handedness test
    tests/test_interior_geometry.py uses, and for the same reason.

Plus the ordinary structural guards: outward winding (so GL_CULL_FACE keeps
the visible surface), constant per-face normals (the crisp machined edge that
the smooth-shaded torus can't give), and membership in the id tables the
dropdowns and the picking pass build themselves from.

No GL context is involved. geometry.py pulls the GL entry points into its own
module namespace via `from OpenGL.GL import *`, so swapping the callables for
recorders captures the exact call stream each builder emits.
"""
import math

import pytest

from glyphviz_core.geometry_data import (
    GEO_COUNT, GEO_NAMES, GEO_RING, GEO_RING_WIRE, GEO_TORUS, GEO_TORUS_WIRE,
    RATIO_SHAPED_GEOMETRIES, TORUS_DEFAULT_RATIO, WIRE_TO_SOLID, _WIRE_IDS,
    ring_dims, torus_radii,
)

geometry = pytest.importorskip('glyphviz_gl.geometry')


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

    def strips(self):
        """One entry per GL_QUAD_STRIP, as the list of (uv, normal, xyz) it
        emitted — with the texcoord/normal latched when each vertex was sent,
        i.e. GL's own state semantics."""
        out, current, uv, nrm = [], None, None, None
        for call in self.calls:
            if call[0] == 'glBegin':
                current = []
            elif call[0] == 'glEnd':
                if current is not None:
                    out.append(current)
                current = None
            elif call[0] == 'glTexCoord2f':
                uv = call[1:]
            elif call[0] == 'glNormal3f':
                nrm = call[1:]
            elif call[0] == 'glVertex3f' and current is not None:
                current.append((uv, nrm, call[1:]))
        return out

    def loops(self):
        """The vertices of each GL_LINE_LOOP, in order."""
        out, current = [], None
        for call in self.calls:
            if call[0] == 'glBegin':
                current = []
            elif call[0] == 'glEnd':
                if current is not None:
                    out.append(current)
                current = None
            elif call[0] == 'glVertex3f' and current is not None:
                current.append(call[1:])
        return out


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


def _quads(strip):
    """A QUAD_STRIP's vertices regrouped into the quads GL actually forms:
    v0 v1 v2 v3 -> (v0, v1, v3, v2), which is the winding order that decides
    front/back facing."""
    return [(strip[i], strip[i+1], strip[i+3], strip[i+2])
            for i in range(0, len(strip) - 3, 2)]


def _face_normal(quad):
    """Geometric normal from the emitted winding (CCW-positive)."""
    p = [v[2] for v in quad]
    return _cross(_sub(p[1], p[0]), _sub(p[2], p[1]))


# ---------------------------------------------------------------------------
# The id table
# ---------------------------------------------------------------------------

def test_ring_ids_are_named_and_in_range():
    """An unnamed id would crash the Geometry dropdowns, which build
    themselves from range(GEO_COUNT) and index GEO_NAMES directly."""
    for geo_id in (GEO_RING, GEO_RING_WIRE):
        assert geo_id < GEO_COUNT
        assert GEO_NAMES[geo_id]


def test_ring_ids_sit_past_every_pre_existing_id():
    """Appended, never renumbered: ids 0-22 are ANTz's own enum and 23-32 are
    the earlier GlyphViz extensions, all of them written into saved files."""
    assert (GEO_RING, GEO_RING_WIRE) == (33, 34)


def test_wire_ring_is_registered_as_wire_and_picks_as_the_solid():
    """The pick pass draws solid silhouettes for wire glyphs so a click inside
    the shape registers; a wire id missing from either table would be
    unpickable except exactly on a drawn line."""
    assert GEO_RING_WIRE in _WIRE_IDS
    assert GEO_RING not in _WIRE_IDS
    assert WIRE_TO_SOLID[GEO_RING_WIRE] == GEO_RING


def test_both_ring_ids_are_ratio_shaped():
    """Membership is what routes them to the lazy per-ratio display list
    instead of setup()'s fixed-shape bake — and what the viewport's pre-warm
    (which must run BEFORE the scene list is compiled, since glNewList cannot
    nest) keys on."""
    assert {GEO_RING, GEO_RING_WIRE} <= RATIO_SHAPED_GEOMETRIES
    assert RATIO_SHAPED_GEOMETRIES == {
        GEO_TORUS, GEO_TORUS_WIRE, GEO_RING, GEO_RING_WIRE}


# ---------------------------------------------------------------------------
# ring_dims — the torus's extents, restated as a box
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('ratio', [0.02, 0.05, TORUS_DEFAULT_RATIO, 0.25, 0.49])
def test_ring_spans_exactly_what_the_torus_spans(ratio):
    """The load-bearing equivalence: swapping a Torus for a Flat Ring must not
    move anything. The torus tube runs radially major-minor .. major+minor and
    z +/-minor; the ring sweeps that same rectangle."""
    major, minor = torus_radii(ratio)
    r_out, r_in, half_h = ring_dims(ratio)
    assert r_out == pytest.approx(major + minor)
    assert r_in == pytest.approx(major - minor)
    assert half_h == pytest.approx(minor)


def test_outer_radius_is_always_the_overall_size():
    """Every glyph in geometry.py fits within radius ~1 at unit scale, which
    is what the framing hint, the selection box and Global Scale all assume."""
    for ratio in (0.01, 0.14, 0.4, 0.75):
        assert ring_dims(ratio)[0] == pytest.approx(1.0)
    assert ring_dims(0.14, size=7.0)[0] == pytest.approx(7.0)


def test_default_ratio_gives_a_square_cross_section():
    """Which is what makes Scale Z read as a straight multiplier on the band's
    height: at scale_z == scale_x the band is as tall as it is wide."""
    _, r_in, half_h = ring_dims(TORUS_DEFAULT_RATIO)
    assert (1.0 - r_in) / 2.0 == pytest.approx(half_h)


def test_a_wide_ratio_closes_the_hole_instead_of_inverting():
    for ratio in (0.5, 0.8, 1.0):
        r_out, r_in, _ = ring_dims(ratio)
        assert r_in == 0.0
        assert r_out == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# The solid shape
# ---------------------------------------------------------------------------

def test_solid_ring_draws_four_faces(rec):
    geometry._draw_ring(True, 0.2, rings=8, textured=True)
    strips = rec.strips()
    assert len(strips) == 4
    for strip in strips:
        assert len(strip) == 2 * (8 + 1)


def test_each_face_has_one_constant_normal(rec):
    """The crisp machined edge, expressed as data: a torus shades smoothly
    round its tube, a flat ring must not. Four distinct constant normals, two
    radial and two axial."""
    geometry._draw_ring(True, 0.2, rings=8)
    axial = 0
    for strip in rec.strips():
        normals = {v[1] for v in strip}
        if len(normals) == 1:                      # top / bottom annulus
            axial += 1
            assert next(iter(normals)) in ((0.0, 0.0, 1.0), (0.0, 0.0, -1.0))
        else:                                       # a wall: radial, so it
            for _uv, n, p in strip:                 # turns with the station
                assert n[2] == 0.0
                radial = math.hypot(p[0], p[1])
                if radial > 1e-9:                   # points along +/- r-hat
                    assert abs(abs(_dot(n, (p[0]/radial, p[1]/radial, 0.0)))
                               - 1.0) < 1e-6
    assert axial == 2


def test_every_face_winds_outward(rec):
    """GL_CULL_FACE(GL_BACK) is on for the whole scene, so a face wound the
    other way would simply vanish."""
    geometry._draw_ring(True, 0.2, rings=8)
    for strip in rec.strips():
        for quad in _quads(strip):
            emitted = _face_normal(quad)
            declared = quad[0][1]
            assert _dot(emitted, declared) > 0, (
                "winding disagrees with the declared normal")


def test_no_face_is_mirrored(rec):
    """The texture contract. On every face, walking +u then +v must turn the
    same way the face points — otherwise a legend, a scale or a strip of
    degree numbers reads backwards on that face, which is exactly the trap the
    interior geometries were built to avoid."""
    geometry._draw_ring(True, 0.2, rings=8, textured=True)
    for strip in rec.strips():
        for quad in _quads(strip):
            (uv0, n, p0), (uv1, _, p1), _, (uv3, _, p3) = quad
            # p1 shares uv0's u (same station, other edge of the band) and p3
            # shares it in v -- so these two edges are the local du and dv.
            dv = _sub(p1, p0)
            du = _sub(p3, p0)
            assert uv1[0] == pytest.approx(uv0[0])
            assert uv3[1] == pytest.approx(uv0[1])
            assert uv1[1] != pytest.approx(uv0[1])
            assert uv3[0] != pytest.approx(uv0[0])
            if uv1[1] < uv0[1]:                  # orient both along +u / +v
                dv = tuple(-c for c in dv)
            if uv3[0] < uv0[0]:
                du = tuple(-c for c in du)
            assert _dot(_cross(du, dv), n) > 0, "face is mirrored"


def test_every_face_carries_a_full_uv_span(rec):
    """Per-face 0..1 rather than v walking once around the cross-section
    perimeter: that is what puts one undistorted copy of a marking strip on the
    outer wall and another on the dial face, instead of smearing one image
    across all four and breaking it at the corners."""
    geometry._draw_ring(True, 0.2, rings=8, textured=True)
    for strip in rec.strips():
        us = sorted({v[0][0] for v in strip})
        vs = sorted({v[0][1] for v in strip})
        assert us[0] == pytest.approx(0.0) and us[-1] == pytest.approx(1.0)
        assert vs == [pytest.approx(0.0), pytest.approx(1.0)]


def test_untextured_ring_emits_no_texcoords(rec):
    geometry._draw_ring(True, 0.2, rings=8, textured=False)
    assert 'glTexCoord2f' not in rec.names()


def test_a_closed_ring_skips_its_inner_wall(rec):
    """At ratio >= 0.5 there is no hole; a zero-radius inner wall would be a
    degenerate strip down the axis."""
    geometry._draw_ring(True, 0.6, rings=8)
    assert len(rec.strips()) == 3


# ---------------------------------------------------------------------------
# The wire shape
# ---------------------------------------------------------------------------

def test_wire_ring_draws_four_edge_circles_and_its_rungs(rec):
    geometry._draw_ring(False, 0.2, rings=16, rungs=6)
    loops = rec.loops()
    assert len(loops) == 4 + 6
    for loop in loops[:4]:
        assert len(loop) == 16
        zs = {round(v[2], 9) for v in loop}
        radii = {round(math.hypot(v[0], v[1]), 6) for v in loop}
        assert len(zs) == 1 and len(radii) == 1     # a flat circle, not a helix
    for rung in loops[4:]:
        assert len(rung) == 4                       # the rectangular section


def test_wire_ring_restores_lighting(rec):
    """Wire glyphs draw unlit; leaving GL_LIGHTING off would flatten every
    node drawn after this one in the same pass."""
    geometry._draw_ring(False, 0.2, rings=8, rungs=4)
    names = rec.names()
    assert names[0] == 'glDisable' and names[-1] == 'glEnable'


# ---------------------------------------------------------------------------
# Renderer wiring
# ---------------------------------------------------------------------------

def test_setup_does_not_bake_a_fixed_ring_list(rec):
    """It can't: the shape depends on the node's ratio. If it ever did, every
    ring in every scene would render at one hardcoded band width."""
    r = geometry.GeoRenderer()
    r.setup()
    for geo_id in RATIO_SHAPED_GEOMETRIES:
        assert geo_id not in r._lists
        assert geo_id not in r._tex_lists


def test_ratio_lists_are_cached_per_quantized_ratio(rec):
    r = geometry.GeoRenderer()
    r.setup()
    a = r.ensure_ratio_list(GEO_RING, False, 0.20)
    b = r.ensure_ratio_list(GEO_RING, False, 0.204)   # same 1% bucket
    c = r.ensure_ratio_list(GEO_RING, False, 0.30)
    assert a == b != c
    # ...and never shared across the shapes, the wire/solid pair, or textures.
    assert len({a,
                r.ensure_ratio_list(GEO_RING_WIRE, False, 0.20),
                r.ensure_ratio_list(GEO_RING, True, 0.20),
                r.ensure_ratio_list(GEO_TORUS, False, 0.20)}) == 4


def test_draw_routes_a_ring_through_the_ratio_cache(rec):
    r = geometry.GeoRenderer()
    r.setup()
    rec.calls.clear()
    r.draw(GEO_RING, 1.0, 1.0, 0.1, ratio=0.25)
    assert 'glCallList' in rec.names()
    assert (GEO_RING, False, 0.25) in r._ratio_lists
