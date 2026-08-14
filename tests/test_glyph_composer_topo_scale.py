"""
Glyph Composer: Topology Scale auto-fit, and a preview camera that stays put.

Two problems Jeff hit composing glyphs, both fixed here:

  * picking a topology that reads translate_x as a DISTANCE (Cube, Pin, Plane,
    None) sent the children ~300x the parent's own radius away — off screen
    with no clue where they went — because the Composer's Angular distribution
    always hands the next level 0..360, which only means "a revolution" under
    an angular topology. A level whose Topo Scale the user hasn't touched now
    fits itself to what its children are about to be handed;

  * every edit rebuilt the preview through Viewport.set_nodes(), which
    auto-frames, yanking the camera back to a distant overview and making
    close-up work impossible.

Qt is needed but a GL context is not — same arrangement as
tests/test_topo_scale_gui.py, so these keep running headless.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication                # noqa: E402

from glyphviz_core import glyph_recipe as gr              # noqa: E402
from glyphviz_core import topology as tp                  # noqa: E402
from glyphviz_core.node import (                          # noqa: E402
    DEFAULT_TOPO_SCALE, TOPO_SCALE_ANTZ,
)
from glyphviz_core.scene import Scene                     # noqa: E402
from glyphviz_gl import main_window as mw                 # noqa: E402
from glyphviz_gl.glyph_composer_dialog import (           # noqa: E402
    GlyphComposerDialog,
)
from glyphviz_gl.topo_scale_ui import (                   # noqa: E402
    topo_scale_to_slider, slider_to_topo_scale,
)


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                          # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')
    return app


@pytest.fixture
def dlg(qapp):
    """A Composer over a real MainWindow — the dialog reads the main
    viewport's base_scale on every preview, so a stub would not exercise the
    path that actually runs."""
    win = mw.MainWindow()
    d = GlyphComposerDialog(win)
    yield d
    d.close()
    win.close()


def _recipe(root_topo, child_dist=gr.DIST_ANGULAR):
    """A one-parent / six-children glyph — the shape the Composer opens with,
    which is also the shape that scatters under a linear topology."""
    r = gr.default_recipe()
    r.levels[0].topo = root_topo
    r.levels[1].dist_mode = child_dist
    return r


def _worst_ratio(recipe):
    """How far the generated children land from their parent, in multiples of
    the parent's own rendered radius — the same measure the main window's
    scattered-children hint uses."""
    nodes = gr.generate_nodes(recipe, start_id=1)
    scene = Scene(nodes, 1.0)
    scene._ensure()
    return scene.worst_child_placement_ratio([nodes[0].id])[0]


# --- the auto-fit rule ------------------------------------------------------

# Every topology, classified by whether it reads a child's translate_x as a
# distance — read straight off the table the placement math itself uses, so a
# newly-added topology can't quietly skip the fit.
LINEAR_X_TOPOS = sorted(
    t for t in tp.TOPO_NAMES
    if tp.LINEAR_PLACEMENT_AXES.get(t, (True, True, True))[0])
ANGULAR_X_TOPOS = sorted(set(tp.TOPO_NAMES) - set(LINEAR_X_TOPOS))


@pytest.mark.parametrize("topo", LINEAR_X_TOPOS)
def test_angular_children_under_a_linear_topology_fit_to_antz(topo):
    """The reported bug: 0..360 read as world units. ANTz is the convention
    under which those same degrees span the parent's own extent instead."""
    assert gr.suggested_topo_scale(_recipe(topo), 0) == TOPO_SCALE_ANTZ


@pytest.mark.parametrize("topo", ANGULAR_X_TOPOS)
def test_angular_topologies_are_left_at_one_to_one(topo):
    """A Sphere/Torus/Cylinder already reads 0..360 as a revolution, so there
    is nothing to fit — and scaling it would be the regression."""
    assert gr.suggested_topo_scale(_recipe(topo), 0) == DEFAULT_TOPO_SCALE


@pytest.mark.parametrize("topo", LINEAR_X_TOPOS)
def test_non_angular_children_are_left_alone(topo):
    """Linear/Grid/Circular children are authored in world units already —
    shrinking them 180x would collapse the glyph, the opposite mistake."""
    for mode in (gr.DIST_LINEAR, gr.DIST_CIRCULAR, gr.DIST_GRID):
        assert gr.suggested_topo_scale(_recipe(topo, mode), 0) == \
            DEFAULT_TOPO_SCALE


def test_a_leaf_level_has_nothing_to_fit():
    r = _recipe(tp.TOPO_CUBE)
    assert gr.suggested_topo_scale(r, len(r.levels) - 1) == DEFAULT_TOPO_SCALE


@pytest.mark.parametrize("topo", [tp.TOPO_CUBE, tp.TOPO_PIN, tp.TOPO_PLANE,
                                  tp.TOPO_NONE])
def test_auto_fit_reels_the_children_back_in(topo):
    """End to end through real placement: the fit is what separates 'children
    somewhere off in the distance' from 'children on the parent'."""
    r = _recipe(topo)
    for lvl in r.levels:
        lvl.topo_scale_auto = False
    assert _worst_ratio(r) > 100.0            # the bug

    for lvl in r.levels:
        lvl.topo_scale_auto = True
    assert _worst_ratio(r) < 5.0              # the fix


def test_manual_value_wins_over_the_suggestion():
    r = _recipe(tp.TOPO_CUBE)
    r.levels[0].topo_scale_auto = False
    r.levels[0].topo_scale = 0.25
    assert gr.effective_topo_scale(r, 0) == 0.25
    assert gr.generate_nodes(r, start_id=1)[0].topo_scale == 0.25


def test_generated_nodes_carry_the_scale():
    nodes = gr.generate_nodes(_recipe(tp.TOPO_CUBE), start_id=1)
    assert nodes[0].topo_scale == TOPO_SCALE_ANTZ
    # The leaf level has no children to place, so it stays neutral — and a
    # neutral value is the one that omits the CSV column entirely.
    assert nodes[1].topo_scale == DEFAULT_TOPO_SCALE


# --- template round-trip ----------------------------------------------------

def test_topo_scale_survives_a_template_round_trip():
    r = _recipe(tp.TOPO_CUBE)
    r.levels[0].topo_scale_auto = False
    r.levels[0].topo_scale = TOPO_SCALE_ANTZ
    back = gr.recipe_from_dict(gr.recipe_to_dict(r))
    assert back.levels[0].topo_scale_auto is False
    assert back.levels[0].topo_scale == TOPO_SCALE_ANTZ


def test_a_pre_feature_template_loads_onto_auto():
    """Templates saved before Topology Scale existed carry neither key. They
    load onto auto — which is what rescues the ones whose children were flying
    off, and a no-op for the ones that were already fine."""
    d = gr.recipe_to_dict(_recipe(tp.TOPO_CUBE))
    for lvl in d['levels']:
        lvl.pop('topo_scale')
        lvl.pop('topo_scale_auto')
    back = gr.recipe_from_dict(d)
    assert back.levels[0].topo_scale_auto is True
    assert gr.generate_nodes(back, start_id=1)[0].topo_scale == TOPO_SCALE_ANTZ


# --- the Hyperglyph Generator takes the same fit -----------------------------

def _hyperglyph_generator():
    import sys
    from pathlib import Path

    lab = Path(__file__).resolve().parent.parent / 'hyperglyph_lab'
    sys.path.insert(0, str(lab))
    try:
        import hyperglyph_generator as hg
    finally:
        sys.path.remove(str(lab))
    return hg


def test_hyperglyph_generator_levels_are_fitted():
    """random_recipe's trunk pool is named ANGULAR_SAFE_TOPOS but includes Pin,
    which reads translate_x as HEIGHT — so an angular level under a Pin trunk
    used to become a 360-unit vertical smear instead of a ring. The Generator
    now takes the same per-level fit the Composer does (Jeff, 2026-08-13),
    which is what finally makes that pool's name true."""
    import random

    hg = _hyperglyph_generator()
    recipe, _ = hg.random_recipe(4, 2000, random.Random(1))
    assert all(lvl.topo_scale_auto for lvl in recipe.levels)

    # A mutated design carries the fit forward rather than dropping back to
    # the smear on the next generation.
    variant = hg.mutate_recipe(recipe, random.Random(1), 2000)
    assert all(lvl.topo_scale_auto for lvl in variant.levels)


def test_pin_trunks_no_longer_smear():
    """The concrete win, measured the way the main window measures it. Every
    trunk topology in the pool now keeps its children near it; before the fit,
    Pin was the outlier by two orders of magnitude."""
    hg = _hyperglyph_generator()
    for topo in hg.ANGULAR_SAFE_TOPOS:
        r = _recipe(topo)
        assert _worst_ratio(r) < 20.0, tp.TOPO_NAMES[topo]

    # ...and Pin specifically is the one that needed it.
    pinned = _recipe(tp.TOPO_PIN)
    for lvl in pinned.levels:
        lvl.topo_scale_auto = False
    assert _worst_ratio(pinned) > 100.0


# --- the dialog's Topo Scale row --------------------------------------------

def test_row_shows_the_fitted_value_when_the_topology_changes(dlg):
    dlg._w_topo.setCurrentIndex(dlg._w_topo.findData(tp.TOPO_CUBE))
    assert dlg._recipe.levels[0].topo == tp.TOPO_CUBE
    assert dlg._w_topo_scale.value() == pytest.approx(TOPO_SCALE_ANTZ, abs=1e-6)
    assert dlg._w_topo_scale_auto.isChecked()

    dlg._w_topo.setCurrentIndex(dlg._w_topo.findData(tp.TOPO_SPHERE))
    assert dlg._w_topo_scale.value() == DEFAULT_TOPO_SCALE


def test_spin_and_slider_stay_in_agreement(dlg):
    dlg._w_topo_scale_slider.setValue(topo_scale_to_slider(0.01))
    assert dlg._w_topo_scale.value() == pytest.approx(0.01)
    assert dlg._recipe.levels[0].topo_scale == pytest.approx(0.01)

    dlg._w_topo_scale.setValue(0.5)
    assert dlg._w_topo_scale_slider.value() == topo_scale_to_slider(0.5)


def test_touching_the_value_takes_the_level_off_auto(dlg):
    """The control the user reached for IS the decision — making them find a
    checkbox first would just mean their number gets overwritten."""
    assert dlg._w_topo_scale_auto.isChecked()
    dlg._w_topo_scale.setValue(0.02)
    assert not dlg._w_topo_scale_auto.isChecked()
    assert dlg._recipe.levels[0].topo_scale_auto is False

    # ...and the manual value now survives a topology change.
    dlg._w_topo.setCurrentIndex(dlg._w_topo.findData(tp.TOPO_CUBE))
    assert dlg._recipe.levels[0].topo_scale == pytest.approx(0.02)


def test_antz_preset_stores_the_exact_constant(dlg):
    """The spin box shows 6 decimals; storing what it displays would turn
    1/180 into 0.005556 — and a preview tick reading the box back would do it
    silently, which is why _save_params leaves this field alone."""
    dlg._set_topo_scale(TOPO_SCALE_ANTZ)
    assert dlg._recipe.levels[0].topo_scale == TOPO_SCALE_ANTZ
    dlg._do_preview()
    assert dlg._recipe.levels[0].topo_scale == TOPO_SCALE_ANTZ


def test_auto_checkbox_hands_control_back(dlg):
    dlg._w_topo.setCurrentIndex(dlg._w_topo.findData(tp.TOPO_CUBE))
    dlg._w_topo_scale.setValue(3.0)
    assert dlg._recipe.levels[0].topo_scale == pytest.approx(3.0)

    dlg._w_topo_scale_auto.setChecked(True)
    assert dlg._w_topo_scale.value() == pytest.approx(TOPO_SCALE_ANTZ, abs=1e-6)
    assert gr.generate_nodes(dlg._recipe, start_id=1)[0].topo_scale == \
        TOPO_SCALE_ANTZ


def test_leaving_auto_keeps_what_was_on_screen(dlg):
    """Unchecking Auto shouldn't make the glyph jump — the displayed value
    becomes the stored one."""
    dlg._w_topo.setCurrentIndex(dlg._w_topo.findData(tp.TOPO_CUBE))
    dlg._w_topo_scale_auto.setChecked(False)
    assert dlg._recipe.levels[0].topo_scale == \
        pytest.approx(TOPO_SCALE_ANTZ, abs=1e-6)


def test_the_row_follows_the_selected_level(dlg):
    dlg._w_topo.setCurrentIndex(dlg._w_topo.findData(tp.TOPO_CUBE))
    dlg._w_topo_scale.setValue(0.04)

    dlg._level_list.setCurrentRow(1)          # leaf: nothing to place
    assert dlg._w_topo_scale.value() == DEFAULT_TOPO_SCALE
    assert dlg._w_topo_scale_auto.isChecked()

    dlg._level_list.setCurrentRow(0)
    assert dlg._w_topo_scale.value() == pytest.approx(0.04)
    assert not dlg._w_topo_scale_auto.isChecked()


# --- the preview camera -----------------------------------------------------

def _cam(dlg):
    vp = dlg._mini_vp
    return (vp._cam_azimuth, vp._cam_elevation, vp._cam_distance,
            tuple(vp._cam_target))


def test_first_preview_frames_the_glyph(dlg):
    dlg._do_preview()
    assert dlg._camera_framed
    assert dlg._mini_vp._cam_distance > 0.0


def test_a_small_glyph_is_framed_close_up(dlg):
    """Viewport.set_nodes() floors its framing distance at 50 world units,
    which would leave the default ~3-unit glyph — and every well-formed one
    the Topo Scale fit produces — a speck. The preview frames off the real
    extent instead."""
    dlg._do_preview(reset_camera=True)
    span = 2.0 * max(
        max(abs(c) for c in dlg._mini_vp.world_position(n.id))
        for n in dlg._mini_vp.scene.nodes)
    assert dlg._mini_vp._cam_distance < 50.0
    assert dlg._mini_vp._cam_distance == pytest.approx(
        max(span * 1.6, 1.0), rel=0.6)


def test_edits_leave_the_camera_where_the_user_put_it(dlg):
    """The frustration this fixes: zoom in on a detail, change one field, and
    the old code threw you back out to a distant overview."""
    dlg._do_preview()
    dlg._mini_vp._cam_distance = 7.5
    dlg._mini_vp._cam_azimuth = 123.0
    dlg._mini_vp._cam_target = [1.0, 2.0, 3.0]
    before = _cam(dlg)

    dlg._w_count.setValue(dlg._w_count.value() + 3)
    dlg._do_preview()
    assert _cam(dlg) == before

    # Even a change that resizes the glyph enormously — framing would move a
    # long way, so this is where a silent re-frame would show up.
    dlg._w_sx.setValue(20.0)
    dlg._do_preview()
    assert _cam(dlg) == before


def test_reset_view_reframes(dlg):
    dlg._do_preview()
    dlg._mini_vp._cam_distance = 7.5
    dlg._mini_vp._cam_target = [50.0, 50.0, 50.0]

    dlg._reset_preview_camera()
    assert dlg._mini_vp._cam_distance != 7.5
    assert tuple(dlg._mini_vp._cam_target) != (50.0, 50.0, 50.0)
    assert dlg._camera_framed          # and it holds still again afterwards


def test_loading_a_template_reframes(dlg, tmp_path):
    path = tmp_path / "tpl.json"
    gr.save_recipe(_recipe(tp.TOPO_SPHERE), str(path))

    dlg._do_preview()
    dlg._mini_vp._cam_distance = 7.5
    dlg._mini_vp._cam_target = [50.0, 50.0, 50.0]

    dlg._recipe = gr.load_recipe(str(path))
    dlg._current_level = None
    dlg._refresh_level_list()
    dlg._level_list.setCurrentRow(0)
    dlg._reset_preview_camera()               # what _load_template does
    assert dlg._mini_vp._cam_distance != 7.5
