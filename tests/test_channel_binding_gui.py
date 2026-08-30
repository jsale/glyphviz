"""
The Properties panel's "Channel In" row, and the tag-label display defaults.

Two unrelated features share this file because they share the harness: a real
MainWindow with a real scene, offscreen and with no GL context needed — the
same arrangement as tests/test_topo_scale_gui.py.

What's pinned for Channel In:
  - a scene whose channel files bind NOTHING still loads its transport and
    keeps its ch-map, since that is exactly the scene the field exists to fix;
  - setting the spin box binds every selected node and the animation drives
    them on the next frame, with no file reload;
  - clearing it mid-animation restores the SAVED values rather than freezing
    whatever frame was on screen;
  - the hint text says what the chosen channel drives, and what ids exist.

The binding math itself is in tests/test_channel_binding.py.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication              # noqa: E402

from glyphviz_core.channel_engine import channel_id_of  # noqa: E402
from glyphviz_core.csv_reader import (                  # noqa: E402
    load_node_csv, save_node_csv,
)
from glyphviz_gl import main_window as mw               # noqa: E402
from glyphviz_gl.viewport import Viewport               # noqa: E402


NODE_CSV = (
    "id,type,parent_id,branch_level,translate_x,translate_y,translate_z,"
    "rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,"
    "color_r,color_g,color_b,color_a,geometry,hide,topo,text\n"
    "1,5,0,0,0,0,0,0,0,0,1,1,1,242,121,61,255,7,0,0,Alpha\n"
    "2,5,0,0,6,0,0,0,0,0,1,1,1,90,200,255,255,7,0,0,Beta\n"
)
CH_MAP = (
    "channel_id,track_id,attribute\n"
    "3,1,translate_z\n"
    "3,2,color_r\n"
    "7,3,scale_x\n"
)
CH_TRACKS = (
    "cyclecount,ch1,ch2,ch3\n"
    "0,0,10,1\n"
    "1,5,20,2\n"
    "2,9,30,3\n"
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


@pytest.fixture
def scene(tmp_path, qapp):
    """A MainWindow with the scene above open, through the real load path —
    so the ch-map/ch-tracks companions are discovered the way they are in the
    app, not injected."""
    (tmp_path / 'gv_node.csv').write_text(NODE_CSV, encoding='utf-8')
    (tmp_path / 'gv_ch-map.csv').write_text(CH_MAP, encoding='utf-8')
    (tmp_path / 'gv_ch-tracks.csv').write_text(CH_TRACKS, encoding='utf-8')
    win = mw.MainWindow()
    assert win._load_csv_path(str(tmp_path / 'gv_node.csv'))
    yield win
    win.close()


def _select(win, ids):
    win._table.select_by_ids(set(ids))
    assert {n.id for n in win._selected_nodes} == set(ids)


# --- tag label defaults -----------------------------------------------------

def test_tags_default_on_and_scoped_to_the_selection(qapp):
    """Both checkboxes ship checked (2026-08-28). Either alone is a poor
    default: off hides the labels a scene's author wrote, all-on buries a
    large scene in text."""
    vp = Viewport()
    assert vp.show_tags is True
    assert vp.show_tags_selected_only is True


def test_tag_checkboxes_and_menu_start_agreeing_with_the_viewport(qapp):
    win = mw.MainWindow()
    try:
        assert win._cb_tags.isChecked() == win._viewport.show_tags is True
        assert win._tags_act.isChecked() is True
        assert win._cb_tags_selected.isChecked() is True
        assert win._viewport.show_tags_selected_only is True
    finally:
        win.close()


def test_tag_toggle_still_syncs_all_three_surfaces(qapp):
    """The T key, the menu item and the checkbox route through _set_tags; the
    new default must not leave one of them stuck."""
    win = mw.MainWindow()
    try:
        win._set_tags(False)
        assert not win._viewport.show_tags
        assert not win._cb_tags.isChecked()
        assert not win._tags_act.isChecked()
        win._set_tags(True)
        assert win._viewport.show_tags
        assert win._cb_tags.isChecked()
        assert win._tags_act.isChecked()
    finally:
        win.close()


# --- Channel In: the scene that has channels but binds nothing --------------

def test_channels_load_even_when_no_node_references_one(scene):
    """Before this feature that scene hid the transport and dropped the
    engine, leaving nothing to bind a node against — which is precisely the
    case the Channel In field exists to fix."""
    assert scene._ch_engine is not None
    assert not scene._ch_engine.has_bindings
    assert sorted(scene._ch_map) == [3, 7]
    assert scene._ch_tracks is not None
    assert scene._ch_grp.isVisibleTo(scene)


def test_hint_names_the_available_channels_when_unbound(scene):
    _select(scene, {1})
    text = scene._insp_ch_in_hint.text()
    assert '2 channels available' in text
    assert '3, 7' in text


# --- Channel In: binding ----------------------------------------------------

def test_setting_the_spin_box_binds_and_animates_the_selection(scene):
    node = scene._node_by_id(1)
    _select(scene, {1})
    scene._insp_ch_in.setValue(3)

    assert channel_id_of(node) == 3
    assert scene._ch_engine.bound_node_ids == {1}
    # translate_z is a transform field, so the node also joins the playback
    # fast path rather than staying baked into the static display list.
    assert scene._ch_engine.transform_bound_node_ids == {1}
    assert scene._viewport._ch_dynamic_ids == {1}

    scene._ch_apply_and_show_frame(2)
    assert node.translate_z == 9.0
    assert node.color_r == 30


def test_an_unselected_sibling_is_left_alone(scene):
    other = scene._node_by_id(2)
    _select(scene, {1})
    scene._insp_ch_in.setValue(3)
    scene._ch_apply_and_show_frame(2)
    assert other.translate_z == 0.0
    assert other.color_r == 90


def test_hint_says_what_the_chosen_channel_drives(scene):
    _select(scene, {1})
    scene._insp_ch_in.setValue(3)
    assert scene._insp_ch_in_hint.text() == 'drives translate_z, color_r'


def test_clearing_mid_animation_restores_the_saved_values(scene):
    """Not the frame that happened to be on screen — see _ch_rebind's
    reset-then-reload ordering."""
    node = scene._node_by_id(1)
    saved = (node.translate_z, node.color_r)
    _select(scene, {1})
    scene._insp_ch_in.setValue(3)
    scene._ch_apply_and_show_frame(2)
    assert (node.translate_z, node.color_r) != saved

    scene._insp_ch_in.setValue(0)
    assert (node.translate_z, node.color_r) == saved
    assert not scene._ch_engine.has_bindings
    assert scene._viewport._ch_dynamic_ids == set()


def test_multi_select_binds_every_selected_node(scene):
    _select(scene, {1, 2})
    scene._insp_ch_in.setValue(7)
    assert channel_id_of(scene._node_by_id(1)) == 7
    assert channel_id_of(scene._node_by_id(2)) == 7
    assert scene._ch_engine.bound_node_ids == {1, 2}


def test_a_channel_the_file_does_not_have_is_reported_not_bound(scene):
    _select(scene, {1})
    scene._insp_ch_in.setValue(99)
    assert channel_id_of(scene._node_by_id(1)) == 99   # the id is still the node's
    assert not scene._ch_engine.has_bindings
    assert 'no channel 99' in scene._insp_ch_in_hint.text()


def test_the_row_reads_back_from_the_selection(scene):
    _select(scene, {1})
    scene._insp_ch_in.setValue(3)
    _select(scene, {2})
    assert scene._insp_ch_in.value() == 0
    _select(scene, {1})
    assert scene._insp_ch_in.value() == 3
    _select(scene, {1, 2})
    assert 'selection differs' in scene._insp_ch_in_hint.text()


def test_binding_survives_save_and_reload(scene, tmp_path):
    _select(scene, {1})
    scene._insp_ch_in.setValue(3)
    out = tmp_path / 'saved_node.csv'
    save_node_csv(scene.nodes, str(out))
    reloaded = {n.id: channel_id_of(n) for n in load_node_csv(str(out))}
    assert reloaded[1] == 3
    assert reloaded[2] == 0


def test_no_channel_file_still_records_the_id(tmp_path, qapp):
    """The field is a node property, not a viewer setting: it has to be
    settable (and saveable) before the animation exists."""
    (tmp_path / 'gv_node.csv').write_text(NODE_CSV, encoding='utf-8')
    win = mw.MainWindow()
    try:
        assert win._load_csv_path(str(tmp_path / 'gv_node.csv'))
        assert win._ch_engine is None
        _select(win, {1})
        assert win._insp_ch_in_hint.text() == 'no channel file loaded'
        win._insp_ch_in.setValue(4)
        assert channel_id_of(win._node_by_id(1)) == 4
    finally:
        win.close()
