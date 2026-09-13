"""
The tag pass walks only nodes that carry text (2026-09-12).

_project_tagged_nodes runs every frame, and it used to visit every node in the
scene to ask each one whether it had a label. On the San Diego River watershed
scene — 69,677 nodes, 15 of them pinned labels, the rest terrain and river
vertices — that walk was 35 ms of a 34-40 ms frame while the scene itself drew
in about 4.

The candidates are now a cached list of the nodes with text. What's pinned:

  * the walk touches only labelled nodes, and the labels drawn are unchanged;
  * text typed onto a node in place (which deliberately does NOT bump the
    scene revision, so a keystroke never rebakes the scene) shows as soon as
    tags_touch() is called — and the Properties panel's text field calls it;
  * clearing a label's text removes it the same way;
  * with the backslash draw limit on, the pass still walks everything, since
    that cutoff counts every visible node in scene order.
"""
import os

import numpy as np
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication                          # noqa: E402

from glyphviz_core.node import Node                                 # noqa: E402
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


def _node(nid, text='', show_text=0, x=0.0):
    return Node(id=nid, type=5, parent_id=0, branch_level=0,
                translate_x=x, translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=1, color_g=1, color_b=1, color_a=255,
                geometry=1, hide=0, topo=0, text=text, show_text=show_text)


def _scene(n_plain=2000):
    nodes = [_node(i + 1, x=(i % 40) * 0.1) for i in range(n_plain)]
    nodes.append(_node(n_plain + 1, 'pinned A', show_text=1, x=1.0))
    nodes.append(_node(n_plain + 2, 'pinned B', show_text=1, x=2.0))
    nodes.append(_node(n_plain + 3, 'unpinned C', x=3.0))
    return nodes


def _view(nodes, draw_limit=None):
    view = vp.Viewport.__new__(vp.Viewport)
    view._scene = vp.Scene(nodes, base_scale=1.0)
    view._scan_cache = None
    view._scan_cache_rev = -1
    view.show_hidden = False
    view._draw_limit = draw_limit
    view._ch_dynamic_ids = set()
    view.selected_node_ids = set()
    view.show_tags = False                      # pinned labels only
    view.show_tags_selected_only = True
    view._tag_text_rev = 0
    view.update = lambda: None
    return view


def _labels(view):
    mvp = np.diag([0.1, 0.1, 0.1, 1.0])
    return [t[0] for t in view._project_tagged_nodes(mvp, np.eye(4), 0, 0, 400, 400)]


def test_walk_visits_only_labelled_nodes(qapp, monkeypatch):
    view = _view(_scene())
    seen = []
    real = vp.Viewport._tag_pin_state
    monkeypatch.setattr(vp.Viewport, '_tag_pin_state',
                        lambda self, n: (seen.append(n.id), real(self, n))[1])
    assert _labels(view) == ['pinned A', 'pinned B']
    assert len(seen) == 3, f'walked {len(seen)} nodes for 3 labels'


def test_text_typed_in_place_shows_after_tags_touch(qapp):
    nodes = _scene()
    view = _view(nodes)
    assert _labels(view) == ['pinned A', 'pinned B']
    nodes[5].text = 'typed'
    nodes[5].show_text = 1                      # already pinned, text arrives
    view.tags_touch()
    assert 'typed' in _labels(view)


def test_cleared_text_disappears_after_tags_touch(qapp):
    nodes = _scene()
    view = _view(nodes)
    nodes[-3].text = ''
    view.tags_touch()
    assert _labels(view) == ['pinned B']


def test_draw_limit_still_walks_the_whole_scene(qapp):
    """With a limit of 1000, the pinned labels sit past the cutoff and must
    not draw — which only a full, in-order walk can know."""
    view = _view(_scene(), draw_limit=1000)
    assert _labels(view) == []
    assert _labels(_view(_scene(), draw_limit=5000)) == ['pinned A', 'pinned B']


def test_properties_text_field_calls_tags_touch(qapp):
    """The only place text is edited on a live scene."""
    import inspect
    from glyphviz_gl import main_window
    src = inspect.getsource(main_window.MainWindow._on_insp_text_changed)
    assert 'tags_touch()' in src
