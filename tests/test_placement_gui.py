"""
Wrapped new-object placement, through the real window.

The lattice math is pinned in tests/test_placement.py; what's pinned here is
that pressing the keys actually walks it — repeated Shift+N wraps a row of
children instead of running off in a line, repeated N does the same for
roots, and the Placement Step spin box is what both of them read.

Qt is needed but a GL context is not — same arrangement as
tests/test_topo_scale_gui.py, so these keep running headless.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication                # noqa: E402

from glyphviz_core.node import Node, NODE_TYPE_GRID, NODE_TYPE_LINK  # noqa: E402
from glyphviz_core.placement import (                                # noqa: E402
    DEFAULT_CHILD_Z, DEFAULT_PLACEMENT_STEP, DEFAULT_ROOT_Z,
)
from glyphviz_gl import main_window as mw                 # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                          # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')
    return app


def _node(**overrides):
    base = dict(
        id=1, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=200, color_g=200, color_b=200, color_a=255,
        geometry=3, hide=0, topo=0,
    )
    base.update(overrides)
    return Node(**base)


def _win(nodes=None, selected=None, step=None, root_z=None, child_z=None):
    win = mw.MainWindow()
    win.nodes = list(nodes or [])
    win._viewport.set_nodes(win.nodes)
    win._table.set_nodes(win.nodes)
    if step is not None:
        win._new_step.setValue(step)
    if root_z is not None:
        win._new_root_z.setValue(root_z)
    if child_z is not None:
        win._new_child_z.setValue(child_z)
    if selected:
        win._selected_nodes = list(selected)
        if len(selected) == 1:
            win._refresh_inspector(selected[0])
    return win


def _xy(node):
    return (node.translate_x, node.translate_y)


# --- the control itself ----------------------------------------------------

def test_step_defaults_to_the_historical_spacing(qapp):
    """5.0 — the value the guided tour's screenshots were taken at."""
    win = _win()
    assert win._new_step.value() == pytest.approx(DEFAULT_PLACEMENT_STEP)
    assert win._placement_step() == pytest.approx(DEFAULT_PLACEMENT_STEP)


def test_placement_z_defaults_preserve_the_historical_heights(qapp):
    """Separate numbers on purpose: a root at 5 would hover off the world
    plane, a child at 0 would sit inside a topology-None parent."""
    win = _win()
    assert win._new_root_z.value() == pytest.approx(DEFAULT_ROOT_Z)
    assert win._new_child_z.value() == pytest.approx(DEFAULT_CHILD_Z)
    assert win._placement_z(is_child=False) == pytest.approx(0.0)
    assert win._placement_z(is_child=True) == pytest.approx(5.0)


def test_step_tooltip_reports_the_current_row_width(qapp):
    win = _win()
    win._new_step.setValue(15.0)
    assert '24 object(s)' in win._new_step.toolTip()
    win._new_step.setValue(5.0)
    assert '72 object(s)' in win._new_step.toolTip()


# --- Shift+N (children) ----------------------------------------------------

def test_children_step_then_wrap_to_a_new_row(qapp):
    """Step 120 -> 3 per row, so the 4th child is the one that would land on
    the first and instead starts a new row."""
    parent = _node(id=1)
    win = _win([parent], selected=[parent], step=120.0)
    for _ in range(5):
        win._create_child_node()
    kids = [n for n in win.nodes if n.parent_id == 1]
    assert [_xy(n) for n in kids] == [
        (0.0, 0.0), (120.0, 0.0), (240.0, 0.0), (0.0, 120.0), (120.0, 120.0),
    ]


def test_child_placement_follows_the_step_box(qapp):
    parent = _node(id=1)
    win = _win([parent], selected=[parent], step=20.0)
    win._create_child_node()
    win._create_child_node()
    kids = [n for n in win.nodes if n.parent_id == 1]
    assert [_xy(n) for n in kids] == [(0.0, 0.0), (20.0, 0.0)]


def test_default_step_still_lays_children_out_5_apart(qapp):
    """The pre-existing behavior the guided tour documents, unchanged for any
    run short of a full lap."""
    parent = _node(id=1)
    win = _win([parent], selected=[parent])
    for _ in range(4):
        win._create_child_node()
    kids = [n for n in win.nodes if n.parent_id == 1]
    assert [_xy(n) for n in kids] == [
        (0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (15.0, 0.0)]
    assert all(n.translate_z == 5.0 for n in kids)


def test_parent_stays_selected_across_a_run(qapp):
    parent = _node(id=1)
    win = _win([parent], selected=[parent], step=120.0)
    for _ in range(4):
        win._create_child_node()
    assert [n.id for n in win._selected_nodes] == [1]


def test_links_do_not_consume_a_placement_slot(qapp):
    """A type-7 link parented to the node renders between its two ends and
    ignores translate — counting it would leave a hole in the array."""
    parent = _node(id=1)
    link = _node(id=2, type=NODE_TYPE_LINK, parent_id=1, branch_level=1)
    win = _win([parent, link], selected=[parent], step=10.0)
    win._create_child_node()
    win._create_child_node()
    kids = [n for n in win.nodes if n.parent_id == 1 and n.type != NODE_TYPE_LINK]
    assert [_xy(n) for n in kids] == [(0.0, 0.0), (10.0, 0.0)]


# --- N (roots) -------------------------------------------------------------

def test_roots_step_then_wrap_to_a_new_row(qapp):
    win = _win(step=150.0)
    for _ in range(4):
        win._create_root_node()
    roots = [n for n in win.nodes if n.branch_level == 0 and n.type == 5]
    assert [_xy(n) for n in roots] == [
        (0.0, 0.0), (150.0, 0.0), (300.0, 0.0), (0.0, 150.0)]


def test_first_root_of_an_empty_scene_lands_at_the_origin(qapp):
    win = _win(step=25.0)
    win._create_root_node()
    assert _xy(win.nodes[0]) == (0.0, 0.0)


def test_root_steps_on_from_the_last_one_created(qapp):
    """Not from the largest translate_x: after a wrap that would be back in
    the previous row."""
    win = _win(step=150.0)
    for _ in range(4):
        win._create_root_node()
    win._create_root_node()
    assert _xy(win.nodes[-1]) == (150.0, 150.0)


def test_a_world_grid_is_not_part_of_the_root_array(qapp):
    """The grid is the surface the array sits on; a new object should step on
    from the last real object, not from the grid."""
    win = _win(step=10.0)
    win._create_root_node()
    win._create_world_grid()
    win._selected_nodes = []
    win._create_root_node()
    glyphs = [n for n in win.nodes if n.type == 5]
    assert [_xy(n) for n in glyphs] == [(0.0, 0.0), (10.0, 0.0)]
    assert any(n.type == NODE_TYPE_GRID for n in win.nodes)


def test_n_key_handler_routes_root_vs_child(qapp):
    """_on_create_node: a child-level selection extends that branch (a child
    of the selection, selection unchanged), no selection starts a new root —
    both through the same lattice."""
    parent = _node(id=1)
    child = _node(id=2, parent_id=1, branch_level=1)
    win = _win([parent, child], selected=[child], step=30.0)
    win._on_create_node()
    win._on_create_node()
    grandkids = [n for n in win.nodes if n.parent_id == 2]
    assert [_xy(n) for n in grandkids] == [(0.0, 0.0), (30.0, 0.0)]

    win._selected_nodes = []
    win._on_create_node()
    new_root = win.nodes[-1]
    assert new_root.parent_id == 0 and _xy(new_root) == (30.0, 0.0)


# --- Placement Z -----------------------------------------------------------

def test_child_z_reaches_every_new_child(qapp):
    parent = _node(id=1)
    win = _win([parent], selected=[parent], step=10.0, child_z=-2.5)
    win._create_child_node()
    win._create_child_node()
    kids = [n for n in win.nodes if n.parent_id == 1]
    assert [n.translate_z for n in kids] == [-2.5, -2.5]
    # ...and the X/Y lattice is untouched by it
    assert [_xy(n) for n in kids] == [(0.0, 0.0), (10.0, 0.0)]


def test_root_z_reaches_every_new_root(qapp):
    win = _win(step=10.0, root_z=12.0)
    win._create_root_node()
    win._create_root_node()
    roots = [n for n in win.nodes if n.type == 5]
    assert [n.translate_z for n in roots] == [12.0, 12.0]


def test_the_two_z_boxes_stay_independent(qapp):
    """A root creation must not pick up the child height, or vice versa —
    that's the whole reason they're two boxes."""
    parent = _node(id=1)
    win = _win([parent], selected=[parent], root_z=7.0, child_z=3.0)
    win._create_child_node()
    child = win.nodes[-1]
    win._selected_nodes = []
    win._create_root_node()
    root = win.nodes[-1]
    assert (child.translate_z, root.translate_z) == (3.0, 7.0)


def test_paste_takes_the_placement_z_of_its_destination_level(qapp):
    parent = _node(id=1)
    win = _win([parent], selected=[parent], root_z=9.0, child_z=4.0)
    win._create_child_node()
    win._selected_nodes = [win.nodes[-1]]
    win._copy_selected()

    win._selected_nodes = [parent]
    win._refresh_inspector(parent)
    win._paste_clipboard()
    assert win.nodes[-1].translate_z == 4.0

    win._selected_nodes = []
    win._paste_clipboard()
    assert win.nodes[-1].translate_z == 9.0


# --- paste walks the same lattice -----------------------------------------

def test_paste_lands_in_the_next_free_slot(qapp):
    parent = _node(id=1)
    child = _node(id=2, parent_id=1, branch_level=1)
    win = _win([parent, child], selected=[child], step=100.0)
    win._copy_selected()
    win._selected_nodes = [parent]
    win._refresh_inspector(parent)
    for _ in range(3):
        win._paste_clipboard()
        win._selected_nodes = [parent]
    pasted = [n for n in win.nodes if n.parent_id == 1]
    assert [_xy(n) for n in pasted] == [
        (0.0, 0.0), (100.0, 0.0), (200.0, 0.0), (300.0, 0.0)]
