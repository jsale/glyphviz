"""
Channel-bound nodes that only change how they LOOK are retained per channel
(2026-09-14).

The Channels playback fast path baked the static scene into one display list
and then drew every bound node immediate on top of it, every frame — playing
or paused. On the Burn Record fire-history example (4,960 tiles bound to hide
+ colour through 116 year channels) that cost ~60-80 ms a frame, against 8 ms
with the channel file unloaded; retained, it is ~11 ms while viewing and
~22 ms while playing, pixel-identical at six sampled frames.

What's pinned here:

  * grouping: only nodes whose bindings cannot move them are retained —
    transform-bound nodes and their descendants draw immediate, as do
    textured nodes, grids, links and channel groups too small to be worth a
    list; a channel splits by palette pair, since palette resolution writes
    RGB per node;
  * a group is recorded once and replayed while its values hold still;
  * a value change re-records THAT group only, and the re-recorded stream
    reflects the new values (hidden members drop out);
  * a scene edit (revision bump) re-records;
  * a group switched onto a texture draws immediate, never from a list;
  * end to end through the real ChannelEngine;
  * the per-frame topology re-derivation reads the transform subset only, so
    an appearance-bound Plot parent is still drawn exactly once.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

import numpy as np                                                  # noqa: E402
from PySide6.QtWidgets import QApplication                          # noqa: E402

from glyphviz_core.channel_engine import ChannelEngine              # noqa: E402
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
        self._next = 0

    def install(self, monkeypatch):
        for name in dir(vp):
            if name.startswith('gl') and callable(getattr(vp, name)):
                monkeypatch.setattr(vp, name, self._stub(name), raising=False)

    def _stub(self, name):
        def fn(*args):
            self.calls.append((name,) + args)
            if name == 'glGenLists':
                self._next += 1
                return self._next
            return None
        return fn

    def names(self, since=0):
        return [c[0] for c in self.calls[since:]]


def _node(id, ch=0, **kw):
    base = dict(id=id, type=5, parent_id=0, branch_level=0, geometry=1,
                translate_x=float(id), translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=100, color_g=100, color_b=100,
                color_a=255, hide=0, topo=0)
    base.update(kw)
    n = Node(**base)
    if ch:
        n.extras['ch_input_id'] = ch
    return n


def _viewport(nodes, bound, transform=()):
    view = vp.Viewport.__new__(vp.Viewport)
    view._scene = vp.Scene(nodes)
    view._scan_cache = None
    view._scan_cache_rev = -1
    view.show_hidden = False
    view._draw_limit = None
    view._assets_rev = 0
    view._ch_dynamic_ids = set(bound) | set(transform)
    view._ch_transform_ids = set(transform)
    view._ch_dynamic_rev = 1
    view._ch_cache_rev = None
    view._ch_groups = []
    view._surface_dls = {}
    view._plot_dls = {}
    view._geo = type('G', (), {'ensure_ratio_list': lambda self, *a: None})()
    view._tex_mgr = type('T', (), {'get_gl_name': lambda self, i: 0})()
    view._video_mgr = type('V', (), {'get_gl_name': lambda self, i: 0})()
    view.drawn = []
    view._draw_node = lambda node, m: view.drawn.append(
        (node.id, node.color_r, node.color_g, node.color_b))
    return view


def _frame(view):
    """The dynamic half of _draw_scene_content, as a playback frame runs it."""
    view._ch_ensure_playback_cache()
    view._draw_nodes_immediate(None, nodes=view._ch_immediate_nodes)
    view._draw_appearance_groups()


# --- grouping ------------------------------------------------------------------

def test_only_nodes_their_bindings_cannot_move_are_grouped():
    a = [_node(i, ch=1) for i in range(1, 11)]                 # colour channel, 10 nodes
    moving = [_node(i, ch=2) for i in range(11, 21)]           # transform-bound
    textured = [_node(i, ch=1, texture_id=3) for i in range(21, 23)]
    grid = [_node(23, ch=1, type=6)]
    unbound_child = [_node(24, parent_id=11)]                  # descendant of a mover
    nodes = a + moving + textured + grid + unbound_child
    transform = {n.id for n in moving} | {24}
    immediate, groups = vp.appearance_groups(nodes, transform, min_size=8)
    assert [[n.id for n in g] for g in groups] == [[n.id for n in a]]
    assert {n.id for n in immediate} == transform | {21, 22, 23}
    assert [n.id for n in immediate] == sorted(n.id for n in immediate)   # scene order


def test_small_channels_draw_immediate():
    nodes = [_node(i, ch=1) for i in range(1, 8)]              # 7 < 8
    immediate, groups = vp.appearance_groups(nodes, set(), min_size=8)
    assert groups == [] and len(immediate) == 7


def test_a_channel_splits_by_palette_pair():
    """Palette resolution writes RGB from each node's own pair, so members of
    one channel with different static pairs cannot share a representative."""
    nodes = ([_node(i, ch=1, palette_id=0) for i in range(1, 9)]
             + [_node(i, ch=1, palette_id=2) for i in range(9, 17)])
    _immediate, groups = vp.appearance_groups(nodes, set(), min_size=8)
    assert sorted(len(g) for g in groups) == [8, 8]
    assert all(len({n.palette_id for n in g}) == 1 for g in groups)


# --- retention --------------------------------------------------------------------

def test_a_group_is_recorded_once_and_replayed(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    nodes = [_node(i, ch=1) for i in range(1, 11)]
    view = _viewport(nodes, bound={n.id for n in nodes})

    _frame(view)
    assert rec.names().count('glNewList') == 1
    assert len(view.drawn) == 10

    before, drawn = len(rec.calls), len(view.drawn)
    _frame(view)
    later = rec.names(before)
    assert 'glNewList' not in later
    assert later.count('glCallList') == 1
    assert len(view.drawn) == drawn, 'replay walked the nodes again'


def test_a_value_change_re_records_that_group_only(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    ch1 = [_node(i, ch=1) for i in range(1, 11)]
    ch2 = [_node(i, ch=2) for i in range(11, 21)]
    view = _viewport(ch1 + ch2, bound={n.id for n in ch1 + ch2})
    _frame(view)

    for n in ch1:                      # what a colour track does to its channel
        n.color_r = 250
    before, drawn = len(rec.calls), len(view.drawn)
    _frame(view)
    assert rec.names(before).count('glNewList') == 1
    assert rec.names(before).count('glCallList') == 2
    assert view.drawn[drawn:] == [(n.id, 250, 100, 100) for n in ch1]


@pytest.mark.parametrize('field, value', [('color_g', 7), ('color_b', 7), ('color_a', 9),
                                          ('hide', 1), ('mesh_id', 2)])
def test_every_appearance_value_is_part_of_the_key(qapp, monkeypatch, field, value):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    nodes = [_node(i, ch=1) for i in range(1, 11)]
    view = _viewport(nodes, bound={n.id for n in nodes})
    _frame(view)
    for n in nodes:
        setattr(n, field, value)
    before = len(rec.calls)
    _frame(view)
    assert rec.names(before).count('glNewList') == 1, f'{field} change kept replaying'


def test_hidden_members_drop_out_of_the_re_recorded_list(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    nodes = [_node(i, ch=1) for i in range(1, 11)]
    view = _viewport(nodes, bound={n.id for n in nodes})
    _frame(view)
    for n in nodes:
        n.hide = 1
    drawn = len(view.drawn)
    _frame(view)
    assert view.drawn[drawn:] == []


def test_a_scene_edit_re_records(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    nodes = [_node(i, ch=1) for i in range(1, 11)]
    view = _viewport(nodes, bound={n.id for n in nodes})
    _frame(view)
    view._scene.touch()
    before = len(rec.calls)
    _frame(view)
    assert rec.names(before).count('glNewList') == 1


def test_a_group_switched_onto_a_texture_draws_immediate(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    nodes = [_node(i, ch=1) for i in range(1, 11)]
    view = _viewport(nodes, bound={n.id for n in nodes})
    _frame(view)
    for n in nodes:
        n.texture_id = 4               # a bound texture_id track
    for _ in range(2):
        before, drawn = len(rec.calls), len(view.drawn)
        _frame(view)
        assert 'glNewList' not in rec.names(before)
        assert 'glCallList' not in rec.names(before)
        assert len(view.drawn) - drawn == 10


def test_through_the_real_channel_engine(qapp, monkeypatch):
    """Twelve tiles on one channel: hidden on frame 0, white on frame 1, red
    from frame 2 on — the year-channel shape the Burn Record uses."""
    rec = _GLRecorder()
    rec.install(monkeypatch)
    nodes = [_node(i, ch=5) for i in range(1, 13)]
    ch_map = {5: [(1, 'hide'), (2, 'color_r'), (3, 'color_g'), (4, 'color_b')]}
    tracks = np.array([[1, 0, 0, 0], [0, 255, 255, 255], [0, 220, 40, 40], [0, 220, 40, 40]],
                      dtype=float)
    eng = ChannelEngine()
    eng.load(ch_map, tracks, {1: 0, 2: 1, 3: 2, 4: 3}, nodes)
    view = _viewport(nodes, bound=eng.bound_node_ids, transform=eng.transform_bound_node_ids)

    seen = []
    for k in range(4):
        eng.apply_frame(k)
        before, drawn = len(rec.calls), len(view.drawn)
        _frame(view)
        seen.append((rec.names(before).count('glNewList'),
                     sorted(set(d[1:] for d in view.drawn[drawn:]))))
    assert seen == [(1, []), (1, [(255, 255, 255)]), (1, [(220, 40, 40)]), (0, [])]


# --- re-derivation reads the transform subset --------------------------------------

def test_an_appearance_bound_plot_parent_is_drawn_once(qapp, monkeypatch):
    rec = _GLRecorder()
    rec.install(monkeypatch)
    nodes = [_node(1, ch=1, topo=TOPO_PLOT, ratio=0.2)]
    nodes += [_node(i, parent_id=1, branch_level=1) for i in range(2, 6)]
    view = _viewport(nodes, bound={1})
    view._draw_topology_overlays()
    assert rec.names().count('glBegin') == 2        # one strip + one join-point pass
