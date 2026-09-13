"""
TOPO_PLOT polylines are retained in display lists (2026-09-12).

A Plot parent's line was emitted in Python immediate mode every frame: a
world_pos lookup plus two GL calls per vertex, twice (the line strip, then
one round-join point per vertex). The San Diego River's NHDPlus tributary
network — 484 lines, 10k vertices — cost 41 ms a frame that way with nothing
else in the scene. This is the same fix, keyed the same way, as the Surface
mesh cache in test_surface_texture.py.

What's pinned here:

  * a static line is emitted once and replayed as one glCallList, and the
    replay neither re-emits vertices nor walks the children;
  * the replayed stream is the one the immediate path emits — same vertices,
    colours, width, and round-join points — so the picture cannot change;
  * a line whose parent or any child is channel-bound is never cached, since
    playback moves those nodes without bumping the scene revision;
  * binding a channel AFTER the list was compiled stops the replay;
  * an edit rebuilds the list and frees the old one;
  * line width and point size are reset after the pass, so a replayed width
    cannot leak into later drawing.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication                          # noqa: E402

from glyphviz_core.node import Node                                 # noqa: E402
from glyphviz_core.topology import TOPO_PLOT                        # noqa: E402
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

    def names(self, since=0):
        return [c[0] for c in self.calls[since:]]


def _node(**overrides):
    base = dict(
        id=1, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=200, color_g=200, color_b=200, color_a=255,
        geometry=1, hide=0, topo=0,
    )
    base.update(overrides)
    return Node(**base)


def _plot_scene(n=5, ratio=0.2):
    nodes = [_node(id=1, topo=TOPO_PLOT, ratio=ratio)]
    for i in range(n):
        nodes.append(_node(id=2 + i, parent_id=1, branch_level=1,
                           translate_x=float(i), translate_y=float(i * i),
                           color_r=10 * i, color_g=3, color_b=40))
    return nodes


def _viewport(nodes, bound=()):
    view = vp.Viewport.__new__(vp.Viewport)
    view._scene = vp.Scene(nodes)
    view._scan_cache = None
    view._scan_cache_rev = -1
    view.show_hidden = False
    view._ch_dynamic_ids = set(bound)
    view._ch_transform_ids = set()
    view._ch_dynamic_rev = 0
    view._ch_cache_rev = None
    view._ch_dynamic_nodes = []
    view._ch_transform_rows = []
    view._assets_rev = 0
    view._surface_dls = {}
    view._plot_dls = {}
    return view


def _stream_of(calls):
    """The GL calls that define the picture — everything except the display
    list bookkeeping around it."""
    skip = {'glNewList', 'glEndList', 'glGenLists', 'glCallList',
            'glDeleteLists', 'glDisable', 'glEnable'}
    return [c for c in calls if c[0] not in skip]


# --- retained ----------------------------------------------------------------

def test_static_line_is_emitted_once_and_replayed(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _viewport(_plot_scene(n=5))

    view._draw_topology_overlays()
    assert rec.names().count('glVertex3f') == 10     # strip + join points
    assert rec.names().count('glNewList') == 1

    before = len(rec.calls)
    view._draw_topology_overlays()
    later = rec.names(before)
    assert 'glVertex3f' not in later, 'second frame re-emitted the line'
    assert 'glNewList' not in later
    assert later.count('glCallList') == 1


def test_compiled_stream_matches_the_immediate_stream(qapp, monkeypatch):
    """What goes into the list is exactly what the uncached path draws."""
    nodes = _plot_scene(n=6, ratio=0.35)

    rec_cached = _GLRecorder()
    rec_cached.install(monkeypatch)
    _viewport(nodes)._draw_topology_overlays()

    rec_live = _GLRecorder()
    rec_live.install(monkeypatch)
    _viewport(nodes, bound={nodes[0].id})._draw_topology_overlays()

    assert _stream_of(rec_cached.calls) == _stream_of(rec_live.calls)
    assert ('glLineWidth', 7.0) in rec_cached.calls   # ratio 0.35 x 20


def test_replay_does_not_walk_the_children(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _viewport(_plot_scene(n=5))
    view._draw_topology_overlays()

    class _Untouchable(list):
        def __iter__(self):
            raise AssertionError('replay iterated the child list')

    scan = view._scene_scan()
    real = scan.children_map(view._scene.nodes)
    monkeypatch.setattr(type(scan), 'children_map',
                        lambda self, nodes: {k: _Untouchable(v)
                                             for k, v in real.items()})
    view._draw_topology_overlays()


def test_width_and_point_size_are_reset_after_the_pass(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _viewport(_plot_scene(n=4, ratio=0.5))
    view._draw_topology_overlays()
    before = len(rec.calls)
    view._draw_topology_overlays()
    later = rec.calls[before:]
    call_at = next(i for i, c in enumerate(later) if c[0] == 'glCallList')
    assert ('glLineWidth', 1.0) in later[call_at:]
    assert ('glPointSize', 1.0) in later[call_at:]


# --- never frozen ------------------------------------------------------------

@pytest.mark.parametrize('which', ['parent', 'child'])
def test_channel_bound_line_is_never_cached(qapp, monkeypatch, which):
    nodes = _plot_scene(n=5)
    bound = {nodes[0].id if which == 'parent' else nodes[2].id}
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _viewport(nodes, bound=bound)

    view._draw_topology_overlays()
    before = len(rec.calls)
    view._draw_topology_overlays()
    later = rec.names(before)
    assert later.count('glVertex3f') == 10, 'animated line must re-emit'
    assert 'glNewList' not in later
    assert 'glCallList' not in later


def test_binding_a_channel_after_caching_stops_the_replay(qapp, monkeypatch):
    nodes = _plot_scene(n=5)
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _viewport(nodes)

    view._draw_topology_overlays()
    view._ch_dynamic_ids = {nodes[2].id}
    view._ch_dynamic_rev += 1
    before = len(rec.calls)
    view._draw_topology_overlays()
    later = rec.names(before)
    assert later.count('glVertex3f') == 10
    assert 'glCallList' not in later
    assert later.count('glDeleteLists') == 1


def test_editing_the_scene_rebuilds_the_line(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _viewport(_plot_scene(n=5))

    view._draw_topology_overlays()
    view._scene._revision += 1
    before = len(rec.calls)
    view._draw_topology_overlays()
    later = rec.names(before)
    assert later.count('glVertex3f') == 10
    assert later.count('glNewList') == 1
    assert later.count('glDeleteLists') == 1


def test_hidden_parent_draws_nothing_even_when_cached(qapp, monkeypatch):
    nodes = _plot_scene(n=5)
    rec = _GLRecorder()
    rec.install(monkeypatch)
    view = _viewport(nodes)
    view._draw_topology_overlays()
    nodes[0].hide = 1
    before = len(rec.calls)
    view._draw_topology_overlays()
    assert 'glCallList' not in rec.names(before)
