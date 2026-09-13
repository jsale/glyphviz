"""
Zero-scale glyphs are skipped by the draw and pick passes (2026-09-12).

A glyph whose RENDERED scale is zero on all three axes collapses to a point
and covers no pixels, so the per-node push/multiply/call/pop it costs buys
nothing. That cost was not academic: the vertices of a TOPO_SURFACE terrain
must stay visible and opaque (the mesh is built from them and takes their
alpha), so every one of them drew its own invisible glyph, and on a
58k-vertex watershed terrain those draws were ~70% of the frame (measured
through the real renderer: 35.6 -> 10.4 ms, with 0 of 1,440,000 pixels
different).

What's pinned here:

  * the rule is narrow enough to keep the picture identical — GEO_POINT is a
    fixed-pixel sprite, wire geometry is lines that can rasterise a pixel at
    zero length, and a textured node may be a video that pauses when no draw
    call asks for it, so all three keep drawing;
  * "zero" means the rendered scale, so the opt-in minimum-glyph-size floor
    lifts a zero-scale node back into the draw list;
  * a skipped node still counts toward the backslash draw limit, so the draw
    and pick passes' decimation stays aligned;
  * a Surface whose vertices are authored at scale 0 still builds its mesh.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication                          # noqa: E402

from glyphviz_core.geometry_data import (                           # noqa: E402
    GEO_CUBE, GEO_CUBE_WIRE, GEO_POINT, GEO_SPHERE,
)
from glyphviz_core.node import Node                                 # noqa: E402
from glyphviz_core.topology import TOPO_SURFACE                     # noqa: E402
from glyphviz_gl import viewport as vp                              # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                        # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')
    return app


def _node(**overrides):
    base = dict(
        id=1, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=200, color_g=200, color_b=200, color_a=255,
        geometry=GEO_CUBE, hide=0, topo=0,
    )
    base.update(overrides)
    return Node(**base)


def _zero(**overrides):
    return _node(scale_x=0.0, scale_y=0.0, scale_z=0.0, **overrides)


def _viewport(nodes, scale_floor=0.0):
    view = vp.Viewport.__new__(vp.Viewport)
    view._scene = vp.Scene(nodes, scale_floor=scale_floor)
    view._scan_cache = None
    view._scan_cache_rev = -1
    view.show_hidden = False
    view._draw_limit = None
    view._ch_dynamic_ids = set()
    view.drawn = []
    view._draw_node = lambda node, m: view.drawn.append(node.id)
    return view


def _drawn(nodes, **kw):
    view = _viewport(nodes, **kw)
    view._draw_nodes_immediate(planes=None)
    return view.drawn


# --- the rule ---------------------------------------------------------------

def test_zero_scale_solid_glyph_is_skipped(qapp):
    assert _drawn([_node(id=1), _zero(id=2)]) == [1]


def test_zero_on_only_some_axes_still_draws(qapp):
    """A flat disc (scale_z = 0) is plainly visible from above."""
    assert _drawn([_node(id=1, scale_z=0.0), _node(id=2, scale_x=0.0, scale_y=0.0)]) == [1, 2]


def test_tiny_but_nonzero_still_draws(qapp):
    """Only exact zero is provably invisible; a small glyph can be zoomed to."""
    assert _drawn([_node(id=1, scale_x=1e-6, scale_y=1e-6, scale_z=1e-6)]) == [1]


@pytest.mark.parametrize('geometry', [GEO_POINT, GEO_CUBE_WIRE])
def test_geometries_that_can_still_paint_are_kept(qapp, geometry):
    """A Point sprite ignores the matrix and a zero-length line can rasterise
    a pixel, so neither is provably invisible."""
    assert _drawn([_zero(id=1, geometry=geometry)]) == [1]


def test_textured_node_is_kept(qapp):
    """A video texture that no draw call asks for is paused, so skipping the
    draw would change playback even though no pixel is lost."""
    assert _drawn([_zero(id=1, geometry=GEO_SPHERE, texture_id=4)]) == [1]


def test_scale_floor_lifts_zero_scale_back_into_view(qapp):
    """"Zero" is the RENDERED scale. With the minimum-size floor on, a
    zero-scale node renders at the floor and must draw."""
    assert _drawn([_zero(id=1)], scale_floor=0.2) == [1]


def test_zero_scale_parent_makes_its_subtree_invisible_too(qapp):
    """The radius comes from the composed matrix, so a unit child under a
    zero-scale Cartesian parent collapses exactly as the parent does."""
    nodes = [_zero(id=1), _node(id=2, parent_id=1, branch_level=1)]
    assert _viewport(nodes)._scene.node_draw_data(nodes[1])[2] == 0.0
    assert _drawn(nodes) == []


def test_skipped_node_still_counts_toward_the_draw_limit(qapp):
    """The pick pass mirrors the draw loop's decimation count. If a skipped
    node stopped counting, the two passes would cut off at different nodes."""
    nodes = [_zero(id=1), _node(id=2), _node(id=3)]
    view = _viewport(nodes)
    view._draw_limit = 2
    view._draw_nodes_immediate(planes=None)
    assert view.drawn == [2]


# --- the case it exists for ------------------------------------------------

class _GLRecorder:
    def __init__(self):
        self.calls: list[tuple] = []

    def install(self, monkeypatch):
        for name in dir(vp):
            if name.startswith('gl') and callable(getattr(vp, name)):
                monkeypatch.setattr(vp, name, self._stub(name), raising=False)

    def _stub(self, name):
        def fn(*args):
            self.calls.append((name,) + args)
            return 1 if name == 'glGenLists' else None
        return fn


def test_surface_with_zero_scale_vertices_still_builds_its_mesh(qapp, monkeypatch):
    parent = _node(id=1, topo=TOPO_SURFACE, geometry=GEO_POINT)
    nodes = [parent]
    nid = 2
    for j in range(3):
        for i in range(3):
            nodes.append(_zero(id=nid, parent_id=1, branch_level=1,
                               translate_x=float(i), translate_y=float(j),
                               translate_z=0.5 * i))
            nid += 1

    # No vertex glyph is drawn...
    assert _drawn(nodes) == [1]

    # ...and the mesh over them is complete: 2x2 cells x 4 corners.
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _viewport(nodes)
    view._ch_transform_ids = set()
    view._ch_dynamic_rev = 0
    view._assets_rev = 0
    view._surface_dls = {}
    view._tex_mgr = type('T', (), {'get_gl_name': lambda self, i: 0})()
    view._video_mgr = type('V', (), {'get_gl_name': lambda self, i: 0})()
    view._draw_topology_overlays()
    assert [c[0] for c in rec.calls].count('glVertex3f') == 16
