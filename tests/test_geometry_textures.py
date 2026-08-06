"""
Texture-coordinate coverage for the flat 2-D marker glyphs (Circle, Cross,
Star), which gained UVs alongside the Grid/Cube/Sphere/... family.

No GL context is involved. geometry.py pulls the GL entry points into its own
module namespace via `from OpenGL.GL import *`, so swapping the callables for
recorders captures the exact vertex/texcoord stream each _draw_* helper emits
— which is the whole contract here. That also lets GeoRenderer.setup() run to
completion, pinning the other half of the feature: that the three markers now
have entries in the textured display-list table, since a geometry missing
from it silently falls back to its untextured list in draw() rather than
erroring.

Note setup() wraps each shape in `except Exception: _draw_sphere(...)`, so a
broken builder would be masked into a sphere rather than raising. The stream
assertions below check the recorded primitive/vertex counts, which a sphere
fallback would not satisfy.
"""
import math

import pytest

from glyphviz_core.geometry_data import (
    GEO_CIRCLE, GEO_CROSS, GEO_STAR, GEO_GRID, GEO_CUBE, GEO_SPHERE,
    GEO_POINT, GEO_TORUS, GEO_TORUS_WIRE, _WIRE_IDS,
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

    def vertices(self):
        return [c[1:] for c in self.calls if c[0] == 'glVertex3f']

    def texcoords(self):
        return [c[1:] for c in self.calls if c[0] == 'glTexCoord2f']

    def pairs(self):
        """(texcoord, vertex) for every vertex, with the texcoord that was in
        effect when it was emitted -- i.e. GL's own latched-state semantics.
        A vertex emitted with no preceding texcoord pairs with None."""
        out, current = [], None
        for call in self.calls:
            if call[0] == 'glTexCoord2f':
                current = call[1:]
            elif call[0] == 'glVertex3f':
                out.append((current, call[1:]))
        return out


@pytest.fixture
def rec(monkeypatch):
    r = _Recorder()
    r.install(monkeypatch)
    return r


# ---------------------------------------------------------------------------
# The UV mapping itself
# ---------------------------------------------------------------------------

def test_uv_maps_the_unit_square_like_the_grid():
    """[-1,1]^2 -> [0,1]^2, same corner convention as _draw_grid_solid: the
    -X/-Y corner is (0,0) and +X/+Y is (1,1)."""
    assert geometry._flat_marker_uv(-1.0, -1.0) == (0.0, 0.0)
    assert geometry._flat_marker_uv(1.0, -1.0) == (1.0, 0.0)
    assert geometry._flat_marker_uv(1.0, 1.0) == (1.0, 1.0)
    assert geometry._flat_marker_uv(-1.0, 1.0) == (0.0, 1.0)
    assert geometry._flat_marker_uv(0.0, 0.0) == (0.5, 0.5)


def test_grid_and_markers_agree_on_the_mapping(rec):
    """The markers crop the same image window the Grid does, so a texture
    swapped between a Grid and a Circle keeps its orientation and framing."""
    geometry._draw_grid_solid(True)
    grid = {v[:2]: uv for uv, v in rec.pairs()}
    s = geometry.GRID_HALF_EXTENT
    for (x, y), uv in grid.items():
        assert uv == pytest.approx(geometry._flat_marker_uv(x / s, y / s))


# ---------------------------------------------------------------------------
# Per-shape emission
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('draw', [
    lambda: geometry._draw_circle(),
    lambda: geometry._draw_star(),
    lambda: geometry._draw_cross(),
])
def test_untextured_markers_emit_no_texcoords(rec, draw):
    """The default path is unchanged -- no stray texture coordinates leak
    into the plain display lists."""
    draw()
    assert rec.vertices()
    assert rec.texcoords() == []


@pytest.mark.parametrize('draw', [
    lambda: geometry._draw_circle(textured=True),
    lambda: geometry._draw_star(textured=True),
    lambda: geometry._draw_cross(textured=True),
])
def test_textured_markers_give_every_vertex_a_cropping_uv(rec, draw):
    """Every vertex carries its own texcoord, and that texcoord is exactly
    the crop mapping of its position -- no unset/stale latched coords."""
    draw()
    pairs = rec.pairs()
    assert pairs
    for uv, (x, y, z) in pairs:
        assert z == 0.0
        assert uv is not None
        assert uv == pytest.approx(geometry._flat_marker_uv(x, y))


def test_textured_circle_keeps_its_double_sided_fan_shape(rec):
    """Adding UVs didn't change the geometry: still two 24-segment fans
    (center + closed 25-point loop each), one per facing."""
    geometry._draw_circle(textured=True)
    begins = [c[1] for c in rec.calls if c[0] == 'glBegin']
    assert begins == [geometry.GL_TRIANGLE_FAN] * 2
    assert len(rec.vertices()) == 2 * (1 + 25)
    normals = [c[1:] for c in rec.calls if c[0] == 'glNormal3f']
    assert normals == [(0.0, 0.0, 1.0), (0.0, 0.0, -1.0)]


def test_textured_star_and_cross_match_their_untextured_geometry(rec,
                                                                 monkeypatch):
    """Vertex positions are identical with and without UVs, for both shapes."""
    for draw in (geometry._draw_star, geometry._draw_cross):
        plain = _Recorder()
        plain.install(monkeypatch)
        draw()
        tex = _Recorder()
        tex.install(monkeypatch)
        draw(textured=True)
        assert plain.vertices() == tex.vertices()


def test_cross_center_samples_the_image_center(rec):
    """The plus shows the image's central strips: its bars span the full
    U range at mid-V and the full V range at mid-U."""
    geometry._draw_cross(textured=True)
    uvs = {uv for uv, _ in rec.pairs()}
    w = 0.3                      # _draw_cross default half_width
    lo, hi = geometry._flat_marker_uv(-w, -w)[0], geometry._flat_marker_uv(w, w)[0]
    assert (0.0, lo) in uvs and (1.0, hi) in uvs      # horizontal bar
    assert (lo, 0.0) in uvs and (hi, 1.0) in uvs      # vertical bar


# ---------------------------------------------------------------------------
# The display-list table draw() actually looks in
# ---------------------------------------------------------------------------

def test_setup_compiles_textured_lists_for_the_flat_markers(rec):
    """draw() does `self._tex_lists.get(geo_id)` and silently falls back to
    the untextured list on a miss, so the entry's presence IS the feature."""
    r = geometry.GeoRenderer()
    r.setup()
    for geo_id in (GEO_CIRCLE, GEO_CROSS, GEO_STAR):
        assert geo_id in r._tex_lists, geometry.GEO_NAMES[geo_id]
        assert r._tex_lists[geo_id] != r._lists[geo_id]


def test_setup_still_textures_the_shapes_that_already_did(rec):
    """Guard against the new entries displacing existing ones."""
    r = geometry.GeoRenderer()
    r.setup()
    for geo_id in (GEO_CUBE, GEO_SPHERE, GEO_GRID):
        assert geo_id in r._tex_lists


def test_wire_and_point_geometries_stay_untextured(rec):
    """draw() gates on `geo_id not in _WIRE_IDS`, and Point is a GL_POINTS
    sprite drawn outside the display-list system entirely."""
    r = geometry.GeoRenderer()
    r.setup()
    for geo_id in _WIRE_IDS:
        assert geo_id not in r._tex_lists
    assert GEO_POINT not in r._tex_lists
    assert GEO_POINT not in r._lists


def test_marker_textures_survive_a_draw_call(rec):
    """End to end through draw(): a marker with a bound texture takes the
    textured list and brackets it with the enable/bind pair, exactly as the
    Grid does."""
    r = geometry.GeoRenderer()
    r.setup()
    for geo_id in (GEO_CIRCLE, GEO_CROSS, GEO_STAR, GEO_GRID):
        rec.calls.clear()
        r.draw(geo_id, 1.0, 1.0, 1.0, gl_tex_name=7)
        called = [c[1] for c in rec.calls if c[0] == 'glCallList']
        assert called == [r._tex_lists[geo_id]], geometry.GEO_NAMES[geo_id]
        assert ('glBindTexture', geometry.GL_TEXTURE_2D, 7) in rec.calls
        assert ('glEnable', geometry.GL_TEXTURE_2D) in rec.calls
        assert ('glDisable', geometry.GL_TEXTURE_2D) in rec.calls


def test_untextured_marker_draw_uses_the_plain_list(rec):
    """No texture bound (gl_tex_name=0) -> the original list, no GL_TEXTURE_2D
    state touched."""
    r = geometry.GeoRenderer()
    r.setup()
    for geo_id in (GEO_CIRCLE, GEO_CROSS, GEO_STAR):
        rec.calls.clear()
        r.draw(geo_id, 1.0, 1.0, 1.0, gl_tex_name=0)
        called = [c[1] for c in rec.calls if c[0] == 'glCallList']
        assert called == [r._lists[geo_id]], geometry.GEO_NAMES[geo_id]
        assert not [c for c in rec.calls if c[0] == 'glBindTexture']
