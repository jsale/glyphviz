"""
Geometry coverage for the Pin glyph, rebuilt 2026-08-14 to ANTz's shape.

The version this replaces was assembled from GLU quadrics and had two holes in
it: gluCylinder draws a lateral surface and *never* end caps, so its cone was
open at the narrow end (which also never reached a point — it stopped at
radius 0.03), and the ball sat a full radius above the wide rim, leaving an
open annulus you could see straight down. Neither was a rendering trade-off;
_draw_cone and _draw_cylinder in the same module both pay for gluDisk caps.

No GL context is involved. geometry.py pulls the GL entry points into its own
module namespace via `from OpenGL.GL import *`, so swapping the callables for
recorders captures the exact vertex/normal/texcoord stream _draw_pin emits —
which is the whole contract here, and is only possible because the shape is
now built by hand instead of delegating to opaque gluSphere/gluCylinder calls.

Note GeoRenderer.setup() wraps each shape in `except Exception:
_draw_sphere(...)`, so a broken builder is masked into a sphere rather than
raising; test_setup_compiles_the_pin_itself guards that.
"""
import math

import pytest

from glyphviz_core.geometry_data import (
    GEO_PIN, GEO_PIN_WIRE, PIN_HEIGHT, PIN_RADIUS,
)

geometry = pytest.importorskip('glyphviz_gl.geometry')

TOP = PIN_HEIGHT + PIN_RADIUS       # the pole of the dome
TOL = 1e-9


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

    def vertices(self):
        return [c[1:] for c in self.calls if c[0] == 'glVertex3f']

    def normals_with_vertices(self):
        """(normal, vertex) per vertex, using GL's latched-state semantics."""
        out, current = [], None
        for call in self.calls:
            if call[0] == 'glNormal3f':
                current = call[1:]
            elif call[0] == 'glVertex3f':
                out.append((current, call[1:]))
        return out

    def uvs_with_vertices(self):
        out, current = [], None
        for call in self.calls:
            if call[0] == 'glTexCoord2f':
                current = call[1:]
            elif call[0] == 'glVertex3f':
                out.append((current, call[1:]))
        return out

    def primitives(self):
        """[(mode, [vertex, ...]), ...] — one entry per glBegin/glEnd pair."""
        out, mode, verts = [], None, None
        for call in self.calls:
            if call[0] == 'glBegin':
                mode, verts = call[1], []
            elif call[0] == 'glEnd':
                out.append((mode, verts))
                mode, verts = None, None
            elif call[0] == 'glVertex3f' and verts is not None:
                verts.append(call[1:])
        return out


@pytest.fixture
def rec(monkeypatch):
    r = _Recorder()
    r.install(monkeypatch)
    return r


# ---------------------------------------------------------------------------
# Helpers describing the intended solid
# ---------------------------------------------------------------------------

def _radius(v):
    return math.hypot(v[0], v[1])


def _on_surface(v, tol=1e-9):
    """Is this vertex on the pin's actual surface — the cone's lateral
    surface, or the dome? A full ball (the old shape) would put vertices
    *inside* the cone's z range at radii the cone never reaches there."""
    rad, z = _radius(v), v[2]
    if -tol <= z <= PIN_HEIGHT + tol:
        if abs(rad - PIN_RADIUS * z / PIN_HEIGHT) <= tol:
            return True
    if z >= PIN_HEIGHT - tol:
        d = math.sqrt(rad * rad + (z - PIN_HEIGHT) ** 2)
        if abs(d - PIN_RADIUS) <= tol:
            return True
    return False


def _inside(p, slack=0.0):
    """Is this point strictly within the closed solid?"""
    rad, z = _radius(p), p[2]
    if z < -slack:
        return False
    if z <= PIN_HEIGHT and rad <= PIN_RADIUS * z / PIN_HEIGHT + slack:
        return True
    if z >= PIN_HEIGHT:
        d = math.sqrt(rad * rad + (z - PIN_HEIGHT) ** 2)
        return d <= PIN_RADIUS + slack
    return False


def _face_normal(a, b, c):
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    return (u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0])


# ---------------------------------------------------------------------------
# The two defects this rebuild fixes
# ---------------------------------------------------------------------------

def test_the_tip_is_a_true_point(rec):
    """The old cone stopped at radius 0.03 and was left uncapped, so the tip
    was an open hole. Nothing may sit at the bottom except the apex itself."""
    geometry._draw_pin(True)
    bottom = [v for v in rec.vertices() if v[2] < PIN_HEIGHT * 0.5]
    assert bottom, 'no lower cone at all'
    assert min(v[2] for v in bottom) == pytest.approx(0.0, abs=TOL)
    for v in bottom:
        if v[2] < TOL:
            assert _radius(v) == pytest.approx(0.0, abs=TOL), \
                f'vertex {v} sits at the tip but off-axis — the tip is a hole'


def test_the_dome_closes_the_cone_with_no_gap(rec):
    """The old ball's *bottom pole* was level with the cone's rim, so the rim
    (radius 0.12) was an open annulus around a point. Here the dome's rim IS
    the cone's rim: same radius, same z, so the join is watertight."""
    geometry._draw_pin(True)
    at_rim = [v for v in rec.vertices() if abs(v[2] - PIN_HEIGHT) < TOL]
    assert at_rim, 'nothing at the junction height'
    for v in at_rim:
        assert _radius(v) == pytest.approx(PIN_RADIUS, abs=TOL)
    # Both sides must actually reach it — a gap would show up as one side
    # contributing no vertices at that height.
    prims = rec.primitives()
    touching = [i for i, (_mode, verts) in enumerate(prims)
                if any(abs(v[2] - PIN_HEIGHT) < TOL for v in verts)]
    assert len(touching) >= 2, 'only one band reaches the rim — the pin is open there'


def test_every_vertex_lies_on_the_surface(rec):
    """No stray geometry: in particular no lower hemisphere buried in the
    cone, and no base disk. Both were what the old shape needed and this one
    does not."""
    geometry._draw_pin(True)
    for v in rec.vertices():
        assert _on_surface(v), f'vertex {v} is off the pin surface'


def test_the_lower_hemisphere_is_not_drawn(rec):
    """Jeff's question: with the ball's equator flush against the cone rim,
    half its facets are sealed inside and need not exist. Nothing may sit
    below the rim at a radius the cone does not have there."""
    geometry._draw_pin(True)
    for v in rec.vertices():
        if v[2] < PIN_HEIGHT - TOL:
            cone_r = PIN_RADIUS * v[2] / PIN_HEIGHT
            assert _radius(v) <= cone_r + TOL, \
                f'vertex {v} bulges past the cone — lower hemisphere is being drawn'


# ---------------------------------------------------------------------------
# Placement — the half of the job that makes children ride the shaft
# ---------------------------------------------------------------------------

def test_the_pin_stands_on_its_own_origin(rec):
    """ANTz's DrawPinDL puts the apex at the local origin with the shaft
    rising along +Z. GlyphViz's old pin hung the other way, below the origin,
    which is what left TOPO_PIN children floating off the glyph."""
    geometry._draw_pin(True)
    zs = [v[2] for v in rec.vertices()]
    assert min(zs) == pytest.approx(0.0, abs=TOL)
    assert max(zs) == pytest.approx(TOP, abs=TOL)


def test_pin_topology_children_ride_the_shaft():
    """The cross-module pin: topology._pin_offset places a child at
    `base_radius + translate_x` along +Z, so with the glyph standing on its
    origin a child at translate_x = 0 lands exactly at the dome's centre —
    ANTz's arrangement — and the usable translate_x range walks the shaft
    instead of hovering above the whole glyph."""
    from glyphviz_core import topology

    at_zero = topology._pin_offset(0.0, 0.0, 0.0, 1.0, 0.0)
    assert at_zero == pytest.approx((0.0, 0.0, PIN_HEIGHT))

    # Sliding down from there stays on the drawn glyph rather than leaving it.
    on_tip = topology._pin_offset(-PIN_HEIGHT, 0.0, 0.0, 1.0, 0.0)
    assert on_tip[2] == pytest.approx(0.0, abs=TOL)
    midway = topology._pin_offset(-PIN_HEIGHT / 2.0, 0.0, 0.0, 1.0, 0.0)
    assert 0.0 < midway[2] < PIN_HEIGHT


# ---------------------------------------------------------------------------
# Shading and winding
# ---------------------------------------------------------------------------

def test_normals_point_out_of_the_solid(rec):
    """Stepping off each vertex along its normal must leave the solid, and
    stepping against it must stay inside — the definition of an outward
    normal, checked against the shape rather than against a formula."""
    geometry._draw_pin(True)
    eps = PIN_RADIUS * 1e-3
    for n, v in rec.normals_with_vertices():
        assert n is not None, f'vertex {v} emitted with no normal'
        assert math.hypot(math.hypot(n[0], n[1]), n[2]) == pytest.approx(1.0, abs=1e-6)
        out = tuple(v[i] + eps * n[i] for i in range(3))
        inn = tuple(v[i] - eps * n[i] for i in range(3))
        if _radius(v) < TOL and v[2] < TOL:
            continue                      # the apex: every direction is an edge
        assert not _inside(out, -eps * 0.1), f'normal at {v} points into the solid'
        assert _inside(inn, eps * 0.1), f'normal at {v} does not face outward'


def test_faces_wind_outward_ccw(rec):
    """paintGL culls back faces, so a reversed strip would render as holes.
    Reconstruct each quad strip's faces and check they agree with the emitted
    normals."""
    geometry._draw_pin(True)
    checked = 0
    for mode, verts in rec.primitives():
        assert mode == geometry.GL_QUAD_STRIP
        for i in range(0, len(verts) - 3, 2):
            a, b, c = verts[i], verts[i + 1], verts[i + 3]
            fn = _face_normal(a, b, c)
            if math.hypot(math.hypot(fn[0], fn[1]), fn[2]) < 1e-12:
                continue                  # degenerate sliver at the apex
            centre = tuple((a[j] + b[j] + c[j]) / 3.0 for j in range(3))
            axis = (0.0, 0.0, centre[2])
            outward = tuple(centre[j] - axis[j] for j in range(3))
            if math.hypot(outward[0], outward[1]) < 1e-9:
                continue
            assert sum(fn[j] * outward[j] for j in range(3)) > 0, \
                f'face {a},{b},{c} winds inward'
            checked += 1
    assert checked > 20, 'too few faces checked to be meaningful'


# ---------------------------------------------------------------------------
# Texturing
# ---------------------------------------------------------------------------

def test_textured_pin_gives_every_vertex_a_continuous_uv(rec):
    """One mapping across cone and dome alike — v runs 0 at the tip to 1 at
    the pole. Two separately-textured quadrics could not do this."""
    geometry._draw_pin(True, textured=True)
    pairs = rec.uvs_with_vertices()
    assert pairs
    for uv, v in pairs:
        assert uv is not None, f'vertex {v} emitted with no texcoord'
        u, tv = uv
        assert 0.0 - TOL <= u <= 1.0 + TOL
        assert tv == pytest.approx(v[2] / TOP, abs=1e-9)
    assert min(uv[1] for uv, _ in pairs) == pytest.approx(0.0, abs=TOL)
    assert max(uv[1] for uv, _ in pairs) == pytest.approx(1.0, abs=TOL)
    assert max(uv[0] for uv, _ in pairs) == pytest.approx(1.0, abs=TOL)


def test_untextured_pin_emits_no_texcoords(rec):
    geometry._draw_pin(True)
    assert not [c for c in rec.calls if c[0] == 'glTexCoord2f']


# ---------------------------------------------------------------------------
# Wireframe
# ---------------------------------------------------------------------------

def test_wire_pin_traces_the_same_shape(rec):
    """The wire pin is generated from the same meridian as the solid, so it
    cannot drift into being a different shape."""
    geometry._draw_pin(False)
    verts = rec.vertices()
    assert verts
    for v in verts:
        assert _on_surface(v), f'wire vertex {v} is off the pin surface'
    assert min(v[2] for v in verts) == pytest.approx(0.0, abs=TOL)
    assert max(v[2] for v in verts) == pytest.approx(TOP, abs=TOL)


def test_wire_pin_draws_lines_and_restores_lighting(rec):
    """Meridians run apex-to-pole in one strip each (so the silhouette reads
    as one object), latitudes are closed loops, and lighting is left as it
    was found — the convention every other wire shape in the module follows."""
    geometry._draw_pin(False)
    modes = [m for m, _ in rec.primitives()]
    assert set(modes) == {geometry.GL_LINE_STRIP, geometry.GL_LINE_LOOP}

    strips = [v for m, v in rec.primitives() if m == geometry.GL_LINE_STRIP]
    for verts in strips:
        assert verts[0][2] == pytest.approx(0.0, abs=TOL), 'meridian must start at the tip'
        assert verts[-1][2] == pytest.approx(TOP, abs=TOL), 'meridian must end at the pole'

    loops = [v for m, v in rec.primitives() if m == geometry.GL_LINE_LOOP]
    assert loops, 'no latitude rings'
    for verts in loops:
        zs = {round(v[2], 12) for v in verts}
        assert len(zs) == 1, 'a latitude ring must be level'
        rads = {round(_radius(v), 12) for v in verts}
        assert len(rads) == 1, 'a latitude ring must be circular'
        assert rads.pop() > TOL, 'degenerate ring at a pole should be skipped'

    order = [c[0] for c in rec.calls if c[0] in ('glDisable', 'glEnable')]
    assert order[0] == 'glDisable' and order[-1] == 'glEnable'


def test_wire_pin_includes_the_rim(rec):
    """The junction circle is the pin's widest point and its most
    recognisable feature in wireframe."""
    geometry._draw_pin(False)
    loops = [v for m, v in rec.primitives() if m == geometry.GL_LINE_LOOP]
    assert any(abs(verts[0][2] - PIN_HEIGHT) < TOL
               and abs(_radius(verts[0]) - PIN_RADIUS) < TOL
               for verts in loops)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_setup_compiles_the_pin_itself(rec):
    """setup() masks a raising builder into a sphere, so confirm the pin's
    own geometry is what landed in all three lists."""
    r = geometry.GeoRenderer()
    r.setup()
    assert GEO_PIN in r._lists
    assert GEO_PIN_WIRE in r._lists
    assert GEO_PIN in r._tex_lists

    # A sphere fallback would reach radius 1 and dip below z=0; the pin does
    # neither, so the recorded stream distinguishes them.
    rec.calls.clear()
    geometry._draw_pin(True)
    verts = rec.vertices()
    assert max(_radius(v) for v in verts) == pytest.approx(PIN_RADIUS, abs=1e-6)
    assert min(v[2] for v in verts) == pytest.approx(0.0, abs=TOL)
