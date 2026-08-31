"""
The Epitrochoid Generator dialog, through the real window.

The math is pinned in tests/test_epicycles.py; what is pinned here is the
wiring — that the table rows really are the design, that the preview holds the
camera the user set, that Insert into Scene lands ids that do not collide, and
that Save Scene writes a folder GlyphViz can actually open.

Qt is needed but a GL context is not — same arrangement as
tests/test_placement_gui.py, so these keep running headless.
"""
import math
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication              # noqa: E402

from glyphviz_core import epicycles as ep               # noqa: E402
from glyphviz_core.csv_reader import load_node_csv      # noqa: E402
from glyphviz_core.node import Node                     # noqa: E402
from glyphviz_core.scene import Scene                   # noqa: E402
from glyphviz_gl import main_window as mw               # noqa: E402
from glyphviz_gl.epicycle_dialog import (               # noqa: E402
    ARM_COLUMNS, EpitrochoidGeneratorDialog,
)


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


def _dlg(qapp, nodes=None):
    win = mw.MainWindow()
    win.nodes = list(nodes or [])
    win._viewport.set_nodes(win.nodes)
    win._table.set_nodes(win.nodes)
    dlg = EpitrochoidGeneratorDialog(win, parent=win)
    dlg._do_preview(reset_camera=True)      # the dialog defers this by a timer
    return win, dlg


def _col(attr: str) -> int:
    return next(i for i, spec in enumerate(ARM_COLUMNS) if spec[1] == attr)


# --- the table IS the design ----------------------------------------------

def test_table_round_trips_the_design(qapp):
    _win, dlg = _dlg(qapp)
    design = ep.preset("Rose in space")
    dlg._load_design_into_ui(design)
    got = dlg._design_from_ui()
    assert got.n_arms == design.n_arms
    for a, b in zip(got.arms, design.arms):
        for _label, attr, *_rest in ARM_COLUMNS:
            assert getattr(a, attr) == pytest.approx(getattr(b, attr), abs=1e-6)


def test_editing_a_cell_changes_the_curve(qapp):
    """Rate X is the harmonic knob, so a change to it must reach the readout's
    ladder — not just the widget."""
    _win, dlg = _dlg(qapp)
    dlg._load_design_into_ui(ep.preset("Cardioid (2 terms)"))
    assert ep.harmonics_of([a.rate_x for a in dlg._design_from_ui().arms]) == [1, 2]

    dlg._table.cellWidget(1, _col("rate_x")).setValue(-4.0)
    dlg._do_preview()
    assert ep.harmonics_of([a.rate_x for a in dlg._design_from_ui().arms]) == [1, 5]


def test_arm_count_grows_by_continuing_the_pattern(qapp):
    """A new arm has to be a plausible next TERM. Appending a default length-10
    arm to a decaying chain would swamp everything before it."""
    _win, dlg = _dlg(qapp)
    dlg._load_design_into_ui(ep.preset("Cardioid (2 terms)"))
    dlg._w_arm_count.setValue(4)
    arms = dlg._design_from_ui().arms
    assert len(arms) == 4
    for prev, nxt in zip(arms, arms[1:]):
        assert nxt.length < prev.length or nxt.length == pytest.approx(prev.length)
    assert arms[-1].length < arms[0].length

    dlg._w_arm_count.setValue(2)
    assert len(dlg._design_from_ui().arms) == 2


# --- preview ---------------------------------------------------------------

def test_preview_holds_the_camera_across_edits(qapp):
    """set_nodes() auto-frames, which is right on the first build and wrong on
    every keystroke after it — the Glyph Composer needed exactly this fix."""
    _win, dlg = _dlg(qapp)
    dlg._mini_vp._cam_azimuth = 123.0
    dlg._mini_vp._cam_elevation = 41.0
    dlg._mini_vp._cam_distance = 17.0
    before = dlg._mini_vp.camera_state()

    dlg._table.cellWidget(0, _col("length")).setValue(13.0)
    dlg._do_preview()

    assert dlg._mini_vp._cam_azimuth == pytest.approx(before['azimuth'])
    assert dlg._mini_vp._cam_elevation == pytest.approx(before['elevation'])
    assert dlg._mini_vp._cam_distance == pytest.approx(before['distance'])

    dlg._do_preview(reset_camera=True)       # ... and Reset View re-frames
    assert dlg._mini_vp._cam_distance != pytest.approx(before['distance'])


def test_preview_is_always_rate_driven_even_when_saving_channels(qapp):
    """Self-drawing changes what Save Scene writes, not what the preview does:
    a preview with alpha-0 beads and no rates would look like an empty scene."""
    _win, dlg = _dlg(qapp)
    dlg._w_self_draw.setChecked(True)
    dlg._do_preview()
    assert dlg._design_from_ui().self_drawing is True

    chain = [n for n in dlg._nodes if n.type == 5 and n.topo == ep.T_TORUS]
    assert any(n.translate_rate_x for n in chain), "preview should animate"
    plot = next(n for n in dlg._nodes if n.topo == ep.T_PLOT)
    beads = [n for n in dlg._nodes if n.parent_id == plot.id]
    assert beads and all(b.color_a > 0 for b in beads), "trail should be drawn"


def test_readout_reports_the_measured_spectrum(qapp):
    _win, dlg = _dlg(qapp)
    dlg._load_design_into_ui(ep.preset("Jeff's ANTz original"))
    dlg._do_preview()
    text = dlg._readout.text()
    assert "1 → 2 → 3 → 4" in text
    assert "closes in <b>360</b> frames" in text
    assert "planar" in text


def test_randomize_is_reproducible_and_keeps_scene_options(qapp):
    _win, dlg = _dlg(qapp)
    dlg._w_trail_points.setValue(180)
    dlg._w_rings.setChecked(False)
    dlg._randomize()
    seed = dlg._w_seed.value()
    first = dlg._design_from_ui().to_dict()

    assert dlg._w_trail_points.value() == 180
    assert dlg._w_rings.isChecked() is False

    dlg._w_seed.setValue(seed)
    import random
    design = ep.random_design(random.Random(seed),
                              n_arms=dlg._w_arm_count.value(),
                              allow_3d=dlg._w_allow_3d.isChecked())
    assert [a.rate_x for a in design.arms] == \
        [a.rate_x for a in dlg._design_from_ui().arms]
    assert first["arms"]


# --- output ----------------------------------------------------------------

def test_insert_into_scene_allocates_non_colliding_ids(qapp):
    existing = [_node(id=7), _node(id=42)]
    win, dlg = _dlg(qapp, nodes=existing)
    dlg._load_design_into_ui(ep.preset("Cardioid (2 terms)"))
    dlg._do_preview()
    before = {n.id for n in win.nodes}

    dlg._insert_into_scene()

    added = [n for n in win.nodes if n.id not in before]
    assert added
    assert len(before | {n.id for n in added}) == len(win.nodes)
    assert min(n.id for n in added) == 43
    # The chain and the trail parent both land as roots.
    assert sum(1 for n in added if n.parent_id == 0) == 2


def test_save_scene_writes_a_loadable_folder(qapp, tmp_path, monkeypatch):
    _win, dlg = _dlg(qapp)
    dlg._load_design_into_ui(ep.preset("Inclined orrery (tilt)"))
    dlg._do_preview()
    monkeypatch.setattr(
        "glyphviz_gl.epicycle_dialog.QFileDialog.getExistingDirectory",
        staticmethod(lambda *a, **k: str(tmp_path)))

    dlg._save_scene()

    folder = tmp_path / ep._slug(dlg._design.name)
    node_csv = folder / f"{ep._slug(dlg._design.name)}_gv_node.csv"
    assert node_csv.exists()
    assert (folder / f"{ep._slug(dlg._design.name)}_gv_tag.csv").exists()

    nodes = load_node_csv(str(node_csv))
    assert any(n.type == 0 for n in nodes), "standalone scene needs a World row"
    assert any(n.text for n in nodes), "tag file should have loaded"

    # The trail really is the curve, straight off disk.
    by_id = {n.id: n for n in nodes}
    chain = [n for n in nodes if n.type == 5 and n.topo == ep.T_TORUS]
    plot = next(n for n in nodes if n.topo == ep.T_PLOT)
    beads = [n for n in nodes if n.parent_id == plot.id]
    scene = Scene(nodes, base_scale=1.0)
    design = dlg._design_from_ui()
    step, _ = ep.trail_sampling(design, ep.frame_count(design))
    worst = 0.0
    for i, bead in enumerate(beads):
        f = i * step
        for arm, node in zip(design.arms, chain[1:]):
            by_id[node.id].translate_x = arm.phase_x + arm.rate_x * f
            by_id[node.id].translate_y = arm.phase_y + arm.rate_y * f
        scene.invalidate()
        worst = max(worst, math.dist(scene.world_pos(chain[-1].id),
                                     scene.world_pos(bead.id)))
    assert worst < 1e-4


def test_save_scene_with_self_drawing_writes_the_channel_pair(qapp, tmp_path,
                                                              monkeypatch):
    """Exactly one ch-map and one ch-tracks beside the node CSV — two
    candidates in a folder disable Channels entirely, and silently."""
    _win, dlg = _dlg(qapp)
    dlg._w_self_draw.setChecked(True)
    dlg._do_preview()
    monkeypatch.setattr(
        "glyphviz_gl.epicycle_dialog.QFileDialog.getExistingDirectory",
        staticmethod(lambda *a, **k: str(tmp_path)))

    dlg._save_scene()

    folder = tmp_path / ep._slug(dlg._design.name)
    assert len(list(folder.glob("*_gv_ch-map.csv"))) == 1
    assert len(list(folder.glob("*_gv_ch-tracks.csv"))) == 1
    assert len(list(folder.glob("*_gv_node.csv"))) == 1


def test_design_json_round_trips_through_the_dialog(qapp, tmp_path, monkeypatch):
    _win, dlg = _dlg(qapp)
    dlg._load_design_into_ui(ep.preset("Torus knot (tube)"))
    before = dlg._design_from_ui().to_dict()

    path = tmp_path / "design.json"
    monkeypatch.setattr(
        "glyphviz_gl.epicycle_dialog.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: (str(path), "")))
    dlg._save_design_file()
    assert path.exists()

    dlg._load_design_into_ui(ep.preset("Cardioid (2 terms)"))
    monkeypatch.setattr(
        "glyphviz_gl.epicycle_dialog.QFileDialog.getOpenFileName",
        staticmethod(lambda *a, **k: (str(path), "")))
    dlg._load_design_file()

    after = dlg._design_from_ui().to_dict()
    assert after["arms"] == before["arms"]


def test_tools_menu_action_exists(qapp):
    win = mw.MainWindow()
    actions = {}
    for menu in win.menuBar().findChildren(type(win.menuBar().addMenu("x"))):
        for act in menu.actions():
            actions[act.text()] = act
    assert any("Epitrochoid" in text for text in actions), sorted(actions)
