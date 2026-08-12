"""
Topology Scale wiring, through the real widgets.

The placement math is pinned in tests/test_topo_scale.py; what's pinned here
is that the GUI actually reaches it: the inspector's spin box and log slider
stay in agreement and write to every selected node, the preset buttons land on
the two values that mean something, a Move-drag under a retuned parent still
tracks the cursor instead of crawling at 1/180 speed, and the "your children
just flew away" hint fires on a topology change that scatters a subtree.

Qt is needed but a GL context is not — same arrangement as
tests/test_gizmo_viewport.py, so these keep running on a box with no
framebuffer, which is exactly where a regression would go unnoticed.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication              # noqa: E402

from glyphviz_core.node import (                        # noqa: E402
    DEFAULT_TOPO_SCALE, TOPO_SCALE_ANTZ, Node, NODE_TYPE_GRID,
)
from glyphviz_core import topology as tp                # noqa: E402
from glyphviz_gl import main_window as mw               # noqa: E402
from glyphviz_gl.viewport import Viewport               # noqa: E402


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
        geometry=3, hide=0, topo=0,
    )
    base.update(overrides)
    return Node(**base)


def _win(nodes, selected=None):
    """A MainWindow holding `nodes`, wired the way MainWindow's own load paths
    wire one (scene + table), with an optional selection.

    The selection goes through _refresh_inspector, not just the
    _selected_nodes list: that is what ENABLES the inspector group, and a
    disabled QPushButton silently ignores .click() — so a fixture that skipped
    it would quietly stop testing the preset buttons at all.
    """
    win = mw.MainWindow()
    win.nodes = nodes
    win._viewport.set_nodes(win.nodes)
    win._table.set_nodes(win.nodes)
    if selected:
        win._selected_nodes = selected
        if len(selected) == 1:
            win._refresh_inspector(selected[0])
        else:
            win._refresh_inspector_multi(selected)
    return win


def _degree_authored_subtree(parent_topo, **parent_kw):
    """A parent plus six children whose translate values are DEGREES — the
    layout that survives an angular topology and scatters under a linear one."""
    parent = _node(id=1, topo=parent_topo, **parent_kw)
    kids = [_node(id=10 + j, parent_id=1, branch_level=1,
                  translate_x=j * 30.0, translate_y=15.0) for j in range(6)]
    return [parent] + kids


# --- the log slider ---------------------------------------------------------

@pytest.mark.parametrize("value", [1e-4, 0.01, 0.1, 1.0, 10.0, 100.0])
def test_slider_round_trips_exact_decades(value):
    """A user who drags to the 1.0 tick must get exactly 1.0 — the value that
    keeps the column out of the saved CSV entirely."""
    pos = mw._topo_scale_to_slider(value)
    assert mw._slider_to_topo_scale(pos) == pytest.approx(value, rel=1e-12)


def test_slider_is_monotonic_and_clamped():
    assert mw._topo_scale_to_slider(1e-9) == 0
    assert mw._topo_scale_to_slider(1e9) == mw._TOPO_SCALE_SLIDER_MAX
    positions = [mw._topo_scale_to_slider(v)
                 for v in (0.001, 0.01, 0.1, 1.0, 10.0)]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)


def test_antz_preset_is_inside_the_slider_range():
    """The preset button has to land somewhere the slider can also express,
    or the two controls would disagree the moment it is pressed."""
    pos = mw._topo_scale_to_slider(TOPO_SCALE_ANTZ)
    assert 0 < pos < mw._TOPO_SCALE_SLIDER_MAX


# --- the inspector controls -------------------------------------------------

def test_spin_box_writes_to_every_selected_node(qapp):
    nodes = [_node(id=1, topo=tp.TOPO_CUBE), _node(id=2, topo=tp.TOPO_SPHERE)]
    win = _win(nodes, selected=nodes)
    win._insp_topo_scale.setValue(0.25)
    assert [n.topo_scale for n in nodes] == [0.25, 0.25]
    win.close()


def test_spin_box_and_slider_stay_in_sync(qapp):
    node = _node(id=1, topo=tp.TOPO_CUBE)
    win = _win([node], selected=[node])

    win._insp_topo_scale_slider.setValue(
        mw._topo_scale_to_slider(0.01))
    assert node.topo_scale == pytest.approx(0.01)
    assert win._insp_topo_scale.value() == pytest.approx(0.01)

    win._insp_topo_scale.setValue(1.0)
    assert win._insp_topo_scale_slider.value() == mw._topo_scale_to_slider(1.0)
    win.close()


def test_preset_buttons(qapp):
    node = _node(id=1, topo=tp.TOPO_CUBE)
    win = _win([node], selected=[node])

    win._insp_topo_scale_antz.click()
    assert node.topo_scale == pytest.approx(TOPO_SCALE_ANTZ, abs=1e-9)
    win._insp_topo_scale_one.click()
    assert node.topo_scale == DEFAULT_TOPO_SCALE
    win.close()


def test_inspector_shows_the_selected_nodes_value(qapp):
    node = _node(id=1, topo=tp.TOPO_CUBE, topo_scale=0.05)
    win = _win([node])
    win._refresh_inspector(node)
    assert win._insp_topo_scale.value() == pytest.approx(0.05)
    assert win._insp_topo_scale_slider.value() == mw._topo_scale_to_slider(0.05)
    win.close()


# --- the discovery hint -----------------------------------------------------

def test_topology_change_that_scatters_children_hints(qapp):
    """Sphere -> Cube on a parent whose children are authored in degrees: the
    status bar must name Topology Scale, since nothing on screen will."""
    nodes = _degree_authored_subtree(tp.TOPO_SPHERE)
    win = _win(nodes, selected=[nodes[0]])

    win._insp_topo.setCurrentIndex(win._insp_topo.findData(tp.TOPO_CUBE))
    assert nodes[0].topo == tp.TOPO_CUBE
    assert 'Topo Scale' in win.statusBar().currentMessage()
    win.close()


def test_no_hint_when_children_stay_close(qapp):
    nodes = _degree_authored_subtree(tp.TOPO_SPHERE)
    win = _win(nodes, selected=[nodes[0]])

    win._insp_topo_scale.setValue(TOPO_SCALE_ANTZ)
    win.statusBar().clearMessage()
    win._insp_topo.setCurrentIndex(win._insp_topo.findData(tp.TOPO_CUBE))
    assert 'Topo Scale' not in win.statusBar().currentMessage()
    win.close()


def test_no_hint_for_a_deliberately_retuned_parent(qapp):
    """A parent already carrying a non-default topo_scale has been tuned on
    purpose; nagging about it would be noise."""
    nodes = _degree_authored_subtree(tp.TOPO_SPHERE, topo_scale=40.0)
    win = _win(nodes, selected=[nodes[0]])
    win.statusBar().clearMessage()
    win._insp_topo.setCurrentIndex(win._insp_topo.findData(tp.TOPO_CUBE))
    assert 'Topo Scale' not in win.statusBar().currentMessage()
    win.close()


# --- drag sensitivity -------------------------------------------------------

def test_move_divisors_fold_in_topo_scale(qapp):
    """Without this a child under an ANTz-scaled parent would need 180x the
    mouse travel to move the same distance on screen."""
    vp = Viewport()
    parent = _node(id=1, topo=tp.TOPO_CUBE, topo_scale=0.01)
    child = _node(id=2, parent_id=1, branch_level=1)
    vp.set_nodes([parent, child])

    div = vp._move_axis_divisors(child)
    assert div == {'x': pytest.approx(0.01), 'y': pytest.approx(0.01),
                   'z': pytest.approx(0.01)}


def test_move_divisors_leave_angular_axes_alone(qapp):
    """Cylinder reads translate_x as an angle, so its divisor stays 1 however
    the parent is retuned — degrees are degrees."""
    vp = Viewport()
    parent = _node(id=1, topo=tp.TOPO_CYLINDER, topo_scale=0.01)
    child = _node(id=2, parent_id=1, branch_level=1)
    vp.set_nodes([parent, child])

    div = vp._move_axis_divisors(child)
    assert div['x'] == 1.0
    assert div['y'] == pytest.approx(0.01)
    assert div['z'] == pytest.approx(0.01)


def test_move_divisors_unchanged_at_default(qapp):
    """The pre-existing behavior for every untouched scene: a Cartesian parent
    divides by its cumulative scale and nothing else."""
    vp = Viewport()
    parent = _node(id=1, topo=tp.TOPO_PLANE, scale_x=4.0, scale_y=4.0,
                   scale_z=4.0)
    child = _node(id=2, parent_id=1, branch_level=1)
    vp.set_nodes([parent, child])

    div = vp._move_axis_divisors(child)
    assert div == {'x': pytest.approx(4.0), 'y': pytest.approx(4.0),
                   'z': pytest.approx(4.0)}


def test_move_divisors_grid_children_ignore_topo_scale(qapp):
    """Grid children are exempt from topo_scale, so their drag rate must be
    exempt too — otherwise the divisor would correct for a factor the
    placement never applied."""
    vp = Viewport()
    grid = _node(id=1, type=NODE_TYPE_GRID, topo=tp.TOPO_PLANE, topo_scale=0.01)
    child = _node(id=2, parent_id=1, branch_level=1)
    vp.set_nodes([grid, child])

    div = vp._move_axis_divisors(child)
    assert div == {'x': pytest.approx(1.0), 'y': pytest.approx(1.0),
                   'z': pytest.approx(1.0)}
