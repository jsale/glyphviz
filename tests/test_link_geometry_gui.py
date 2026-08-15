"""
Link geometry cycling and rendering, through the real window and viewport.

The transform math is pinned in tests/test_link_geometry.py; what's pinned
here is that the feature is reachable and that it routes correctly:

  * O / Shift+O steps a Link through every geometry (its two line modes
    included) rather than toggling between just Line and Prism;
  * the viewport dispatches each link to the right one of its three render
    paths, and every pre-existing file's links keep taking the path they took
    before this feature existed;
  * lighting is left the way _draw_topology_overlays found it, so a solid link
    doesn't leak lit shading into the flat-colored passes that follow it.

Qt is needed but a GL context is not — the GL entry points in viewport.py are
swapped for recorders, the same arrangement tests/test_geometry_textures.py
uses on geometry.py.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication                          # noqa: E402

from glyphviz_core.geometry_data import (                           # noqa: E402
    GEO_COUNT, GEO_CUBE, GEO_CYLINDER, GEO_LINE, GEO_LINE_PRISM, GEO_MESH,
    GEO_POINT, GEO_SPHERE,
)
from glyphviz_core.node import Node, NODE_TYPE_LINK                 # noqa: E402
from glyphviz_gl import main_window as mw                           # noqa: E402
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
        geometry=GEO_SPHERE, hide=0, topo=0,
    )
    base.update(overrides)
    return Node(**base)


def _linked_scene(link_geo=GEO_CUBE, ratio=0.2):
    """Two glyphs 10 units apart and a Link joining them."""
    a = _node(id=1, translate_x=0.0)
    b = _node(id=2, translate_x=10.0)
    link = _node(id=3, type=NODE_TYPE_LINK, parent_id=1, branch_level=1,
                 geometry=link_geo, ratio=ratio, extras={'child_id': 2})
    return [a, b, link]


# --- O-key cycling ---------------------------------------------------------

def _cycle_ids(win, link, step, count):
    seen = []
    for _ in range(count):
        win._cycle_selected_geometry(step)
        seen.append(link.geometry)
    return seen


def test_link_cycles_through_every_geometry(qapp):
    """It used to flip between Line and Prism and nothing else."""
    nodes = _linked_scene(link_geo=GEO_LINE)
    link = nodes[-1]
    win = mw.MainWindow()
    win.nodes = nodes
    win._viewport.set_nodes(nodes)
    win._table.set_nodes(nodes)
    win._selected_nodes = [link]

    seen = set(_cycle_ids(win, link, +1, GEO_COUNT * 2))
    assert GEO_CUBE in seen and GEO_SPHERE in seen and GEO_CYLINDER in seen
    # Both line modes stay in a Link's cycle -- they are its modes.
    assert GEO_LINE in seen and GEO_LINE_PRISM in seen
    # Mesh needs a mesh_id; Point renders as a plain line, a duplicate of the
    # Line mode rather than a look of its own.
    assert GEO_MESH not in seen and GEO_POINT not in seen
    assert seen == set(range(GEO_COUNT)) - {GEO_MESH, GEO_POINT}


def test_link_cycle_reverses(qapp):
    nodes = _linked_scene(link_geo=GEO_LINE)
    link = nodes[-1]
    win = mw.MainWindow()
    win.nodes = nodes
    win._viewport.set_nodes(nodes)
    win._table.set_nodes(nodes)
    win._selected_nodes = [link]

    forward = _cycle_ids(win, link, +1, 4)
    back = _cycle_ids(win, link, -1, 4)
    assert back[:3] == list(reversed(forward))[1:]


def test_ordinary_node_still_skips_the_link_only_line_modes(qapp):
    """A bare Line/Prism means nothing on a regular glyph — unchanged."""
    glyph = _node(id=1, geometry=GEO_SPHERE)
    win = mw.MainWindow()
    win.nodes = [glyph]
    win._viewport.set_nodes(win.nodes)
    win._table.set_nodes(win.nodes)
    win._selected_nodes = [glyph]

    seen = set(_cycle_ids(win, glyph, +1, GEO_COUNT * 2))
    assert seen == set(range(GEO_COUNT)) - {GEO_MESH, GEO_LINE, GEO_LINE_PRISM}


# --- render dispatch -------------------------------------------------------

class _GLRecorder:
    """Stands in for viewport.py's GL entry points, logging calls in order.
    Tracks GL_LIGHTING enable/disable so the state contract can be checked."""

    def __init__(self):
        self.calls: list[tuple] = []

    def install(self, monkeypatch):
        for name in dir(vp):
            if not name.startswith('gl') or name.startswith('GL'):
                continue
            if not callable(getattr(vp, name)):
                continue
            monkeypatch.setattr(vp, name, self._stub(name), raising=False)

    def _stub(self, name):
        def fn(*args):
            self.calls.append((name,) + args)
            if name == 'glGenLists':
                return 1
            if name == 'glIsEnabled':
                return False
            return None
        return fn

    def names(self):
        return [c[0] for c in self.calls]

    def lighting_events(self):
        """(enabled: bool) in order, for GL_LIGHTING only."""
        out = []
        for c in self.calls:
            if c[0] in ('glEnable', 'glDisable') and c[1:] == (vp.GL_LIGHTING,):
                out.append(c[0] == 'glEnable')
        return out


class _GeoSpy:
    """Stands in for GeoRenderer, recording what geometry got drawn."""

    def __init__(self):
        self.drawn: list[int] = []

    def draw(self, geo_id, rx, ry, rz, ratio=0.1, gl_tex_name=0, mesh_id=0):
        self.drawn.append(geo_id)


def _overlay_run(monkeypatch, link_geo):
    """Run _draw_topology_overlays over a two-node + one-link scene with the
    GL layer stubbed out, and report what happened."""
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = vp.Viewport.__new__(vp.Viewport)
    nodes = _linked_scene(link_geo=link_geo)
    view._scene = vp.Scene(nodes)
    view._scan_cache = None
    view._scan_cache_rev = -1
    view.show_hidden = False
    view._ch_dynamic_ids = set()
    view._tex_mgr = type('T', (), {'get_gl_name': lambda self, i: 0})()
    view._video_mgr = type('V', (), {'get_gl_name': lambda self, i: 0})()
    geo = _GeoSpy()
    view._geo = geo
    view._draw_topology_overlays()
    return rec, geo


def test_glyph_link_draws_its_geometry(monkeypatch):
    rec, geo = _overlay_run(monkeypatch, GEO_CYLINDER)
    assert geo.drawn == [GEO_CYLINDER]
    # A glyph link is a matrix + a display list, not a GL_LINES pair.
    assert 'glMultMatrixf' in rec.names()


def test_line_link_still_draws_a_line(monkeypatch):
    """Every pre-existing file's links (geometry 27) take the old path."""
    rec, geo = _overlay_run(monkeypatch, GEO_LINE)
    assert geo.drawn == []
    assert 'glLineWidth' in rec.names()


def test_point_link_still_draws_a_line(monkeypatch):
    """Geometry 22 has no extent to stretch, and the GTDB Org_Event_Network
    example parks 6400 links on it — it stays a line."""
    rec, geo = _overlay_run(monkeypatch, GEO_POINT)
    assert geo.drawn == []
    assert 'glLineWidth' in rec.names()


def test_prism_link_still_takes_the_prism_path(monkeypatch):
    rec, geo = _overlay_run(monkeypatch, GEO_LINE_PRISM)
    assert geo.drawn == []
    # The prism builds its tube by hand out of GL_QUADS.
    assert ('glBegin', vp.GL_QUADS) in rec.calls


def test_glyph_link_restores_the_unlit_baseline(monkeypatch):
    """_draw_topology_overlays runs unlit; a solid link needs lighting on to
    shade, so it must put it back before the Plot/Surface passes that follow —
    otherwise they inherit lit shading over their flat vertex colors. (The
    trailing True is the method's own closing restore for later passes.)"""
    rec, _ = _overlay_run(monkeypatch, GEO_CUBE)
    assert rec.lighting_events() == [False, True, False, True]


def test_line_link_never_touches_lighting(monkeypatch):
    """The unchanged path stays unchanged: the method's opening disable and
    its closing restore, and nothing in between."""
    rec, _ = _overlay_run(monkeypatch, GEO_LINE)
    assert rec.lighting_events() == [False, True]


# --- selection feedback ----------------------------------------------------

def _outline_run(monkeypatch, link_geo):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = vp.Viewport.__new__(vp.Viewport)
    nodes = _linked_scene(link_geo=link_geo)
    view._scene = vp.Scene(nodes)
    view._scan_cache = None
    view._scan_cache_rev = -1
    view.show_hidden = False
    view.show_selection_box = True
    view.selected_node_ids = {3}          # the link
    view._draw_limit = None
    view._draw_selected_outlines()
    return rec


def test_glyph_link_gets_a_selection_box(monkeypatch):
    """A link carrying a real glyph is indistinguishable from an ordinary node
    on screen, and cycling geometry with O is exactly the workflow that needs
    to show which link is selected."""
    rec = _outline_run(monkeypatch, GEO_CUBE)
    assert 'glMultMatrixf' in rec.names()
    assert ('glColor4f', 1.0, 0.95, 0.1, 1.0) in rec.calls


def test_line_link_gets_no_selection_box(monkeypatch):
    """Long-standing behavior — there is no box to speak of around a line."""
    rec = _outline_run(monkeypatch, GEO_LINE)
    assert 'glMultMatrixf' not in rec.names()
