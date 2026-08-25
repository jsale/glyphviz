"""
The End caps checkbox, through the real widgets.

Caps are not a node field — the capped and open interior cylinders are two
geometry ids, and the checkbox swaps between them. That is the whole design
(no new column, so the choice saves, loads, cycles on O and animates through
Channels like any other geometry decision), and it means the thing worth
testing is that the checkbox and the Geometry dropdown never disagree about
which id a node is on.

Qt is needed but a GL context is not — same arrangement as
tests/test_topo_scale_gui.py.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication                  # noqa: E402

from glyphviz_core.geometry_data import (                   # noqa: E402
    GEO_CUBE_INTERIOR, GEO_CYLINDER_INTERIOR,
    GEO_CYLINDER_INTERIOR_OPEN, GEO_NAMES, GEO_SPHERE, GEO_SPHERE_INTERIOR,
)
from glyphviz_core.node import Node                         # noqa: E402
from glyphviz_gl import main_window as mw                   # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                            # pragma: no cover
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


def _win(nodes, selected=None):
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


# --- when the row is live ---------------------------------------------------

def test_checkbox_is_disabled_for_shapes_with_no_caps(qapp):
    for geo in (GEO_SPHERE, GEO_SPHERE_INTERIOR, GEO_CUBE_INTERIOR):
        node = _node(geometry=geo)
        win = _win([node], [node])
        assert not win._insp_caps.isEnabled(), GEO_NAMES[geo]


def test_checkbox_reflects_which_cylinder_the_node_is_on(qapp):
    for geo, expected in ((GEO_CYLINDER_INTERIOR, True),
                          (GEO_CYLINDER_INTERIOR_OPEN, False)):
        node = _node(geometry=geo)
        win = _win([node], [node])
        assert win._insp_caps.isEnabled()
        assert win._insp_caps.isChecked() is expected


# --- toggling it ------------------------------------------------------------

def test_unchecking_opens_the_cylinder(qapp):
    node = _node(geometry=GEO_CYLINDER_INTERIOR)
    win = _win([node], [node])
    win._insp_caps.setChecked(False)
    assert node.geometry == GEO_CYLINDER_INTERIOR_OPEN


def test_checking_closes_it_again(qapp):
    node = _node(geometry=GEO_CYLINDER_INTERIOR_OPEN)
    win = _win([node], [node])
    win._insp_caps.setChecked(True)
    assert node.geometry == GEO_CYLINDER_INTERIOR


def test_the_geometry_dropdown_follows_the_checkbox(qapp):
    """Two controls over one field: if the combo kept showing the old id, the
    next edit anywhere in the panel would put the node back on it."""
    node = _node(geometry=GEO_CYLINDER_INTERIOR)
    win = _win([node], [node])
    win._insp_caps.setChecked(False)
    assert win._insp_geo.currentData() == GEO_CYLINDER_INTERIOR_OPEN


def test_the_checkbox_follows_the_geometry_dropdown(qapp):
    """...and the other way round: picking the open cylinder from the combo
    has to clear the tick, not leave a checkbox contradicting the shape."""
    node = _node(geometry=GEO_SPHERE)
    win = _win([node], [node])
    win._insp_geo.setCurrentIndex(win._insp_geo.findData(GEO_CYLINDER_INTERIOR_OPEN))
    assert node.geometry == GEO_CYLINDER_INTERIOR_OPEN
    assert win._insp_caps.isEnabled()
    assert not win._insp_caps.isChecked()


def test_cycling_geometry_with_O_updates_the_row(qapp):
    """O/Shift+O steps the id directly; the panel is re-synced from the node
    afterwards (_after_attr_cycle), and the caps row rides along."""
    node = _node(geometry=GEO_CYLINDER_INTERIOR)
    win = _win([node], [node])
    win._cycle_selected_geometry(+1)
    assert node.geometry == GEO_CYLINDER_INTERIOR_OPEN
    assert win._insp_caps.isEnabled() and not win._insp_caps.isChecked()


# --- selections -------------------------------------------------------------

def test_toggle_applies_to_every_selected_cylinder(qapp):
    nodes = [_node(id=1, geometry=GEO_CYLINDER_INTERIOR),
             _node(id=2, geometry=GEO_CYLINDER_INTERIOR)]
    win = _win(nodes, nodes)
    win._insp_caps.setChecked(False)
    assert [n.geometry for n in nodes] == [GEO_CYLINDER_INTERIOR_OPEN] * 2


def test_a_mixed_selection_only_touches_the_cylinders(qapp):
    """The panel's other controls write one value to the whole selection; this
    one must not, or ticking a box would turn spheres into cylinders."""
    cyl = _node(id=1, geometry=GEO_CYLINDER_INTERIOR)
    sphere = _node(id=2, geometry=GEO_SPHERE_INTERIOR)
    win = _win([cyl, sphere], [cyl, sphere])
    win._insp_caps.setChecked(False)
    assert cyl.geometry == GEO_CYLINDER_INTERIOR_OPEN
    assert sphere.geometry == GEO_SPHERE_INTERIOR


def test_toggling_with_nothing_selected_is_harmless(qapp):
    node = _node(geometry=GEO_CYLINDER_INTERIOR)
    win = _win([node])
    win._insp_caps.setChecked(False)
    assert node.geometry == GEO_CYLINDER_INTERIOR


# --- the dropdowns ----------------------------------------------------------

def test_both_geometry_dropdowns_offer_every_interior_shape(qapp):
    """They build from range(GEO_COUNT), so this is really a guard against a
    new id being added to the renderer but not to GEO_NAMES/GEO_COUNT."""
    win = _win([_node()])
    for combo in (win._insp_geo, win._new_geo):
        for geo in (GEO_CUBE_INTERIOR, GEO_SPHERE_INTERIOR,
                    GEO_CYLINDER_INTERIOR, GEO_CYLINDER_INTERIOR_OPEN):
            assert combo.findData(geo) >= 0, GEO_NAMES[geo]
