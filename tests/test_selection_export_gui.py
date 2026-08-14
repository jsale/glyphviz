"""
Save Selection As…, through the real window and the real options dialog.

The export rules are pinned in tests/test_selection_export.py; what's pinned
here is the wiring — that the menu action tracks the selection, that the
dialog's controls map onto ExportOptions, that its live preview counts the
same rows the write produces, and that the write puts a node CSV and its tag
companion on disk under names that still pair up.

Qt is needed but a GL context is not — same arrangement as
tests/test_placement_gui.py, so these keep running headless.
"""
import os

import numpy as np
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication                  # noqa: E402

from glyphviz_core.channel_loader import find_channel_files  # noqa: E402
from glyphviz_core.csv_reader import load_node_csv          # noqa: E402
from glyphviz_core.node import Node, NODE_TYPE_WORLD        # noqa: E402
from glyphviz_core.scene import Scene, node_world_matrix    # noqa: E402
from glyphviz_core.selection_export import (                # noqa: E402
    DETACH_ANCESTORS, DETACH_BAKE, DETACH_RAW,
)
from glyphviz_core.topology import TOPO_SPHERE              # noqa: E402
from glyphviz_gl import main_window as mw                   # noqa: E402
from glyphviz_gl.save_selection_dialog import (             # noqa: E402
    SaveSelectionDialog, describe_plan,
)


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                            # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')
    return app


def _node(node_id, **overrides):
    base = dict(
        id=node_id, type=5, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=200, color_g=200, color_b=200, color_a=255,
        geometry=3, hide=0, topo=0,
    )
    base.update(overrides)
    return Node(**base)


def _scene_nodes():
    """World row, a Sphere-topology root, a tagged child of it, a grandchild."""
    return [
        _node(1, type=NODE_TYPE_WORLD),
        _node(2, topo=TOPO_SPHERE, translate_x=20.0, translate_y=5.0,
              rotate_z=30.0, scale_x=1.5, scale_y=1.5, scale_z=1.5),
        _node(3, parent_id=2, branch_level=1, topo=TOPO_SPHERE,
              translate_x=45.0, translate_y=30.0, translate_z=4.0,
              text="Station 7", link="https://example.org/s7"),
        _node(4, parent_id=3, branch_level=2, translate_x=90.0, translate_y=0.0),
    ]


def _win(nodes=None, selected=None):
    win = mw.MainWindow()
    win.nodes = list(nodes or [])
    win._viewport.set_nodes(win.nodes)
    win._table.set_nodes(win.nodes)
    if selected:
        win._selected_nodes = list(selected)
    return win


def test_menu_action_follows_the_selection(qapp):
    nodes = _scene_nodes()
    win = _win(nodes)
    assert not win._save_sel_act.isEnabled()
    win._table.select_by_ids({3})
    assert win._save_sel_act.isEnabled()
    win._table.select_by_ids(set())
    assert not win._save_sel_act.isEnabled()


def test_dialog_controls_map_onto_export_options(qapp):
    nodes = _scene_nodes()
    dlg = SaveSelectionDialog(Scene(nodes), {3})

    opts = dlg.current_options()
    assert (opts.detach, opts.include_descendants, opts.include_world_row) == \
           (DETACH_BAKE, True, True)

    dlg._ancestors.setChecked(True)
    assert dlg.current_options().detach == DETACH_ANCESTORS
    dlg._raw.setChecked(True)
    assert dlg.current_options().detach == DETACH_RAW
    dlg._descendants.setChecked(False)
    dlg._world.setChecked(False)
    opts = dlg.current_options()
    assert not opts.include_descendants and not opts.include_world_row
    dlg.deleteLater()


def test_dialog_preview_tracks_the_options(qapp):
    """The preview is the promise the Save button makes, so it has to move
    when the options do: child 3 alone is 3 rows (itself, its grandchild,
    the World row); with its parents it is 4."""
    nodes = _scene_nodes()
    dlg = SaveSelectionDialog(Scene(nodes), {3})
    assert dlg.plan.count == 3
    assert dlg.plan.detached_ids == [3]

    dlg._descendants.setChecked(False)
    assert dlg.plan.count == 2

    dlg._descendants.setChecked(True)
    dlg._ancestors.setChecked(True)
    assert dlg.plan.count == 4
    assert dlg.plan.detached_ids == []

    dlg._world.setChecked(False)
    assert dlg.plan.count == 3
    assert not dlg.plan.world_row
    dlg.deleteLater()


def test_describe_plan_mentions_what_was_decided(qapp):
    nodes = _scene_nodes()
    dlg = SaveSelectionDialog(Scene(nodes), {3})
    text = describe_plan(dlg.plan, 1)
    assert "3 row(s)" in text and "descendant" in text and "re-rooted" in text
    dlg.deleteLater()


def test_save_writes_node_and_tag_files(qapp, tmp_path, monkeypatch):
    """The whole path: select, accept the dialog, choose a filename, and get
    a loadable node CSV plus a tag companion whose name still pairs with it."""
    nodes = _scene_nodes()
    win = _win(nodes)
    win._table.select_by_ids({3})

    out = tmp_path / "fragment_gv_node.csv"
    monkeypatch.setattr(mw.QDialog, 'exec', lambda self: mw.QDialog.DialogCode.Accepted)
    monkeypatch.setattr(mw.QFileDialog, 'getSaveFileName',
                        staticmethod(lambda *a, **k: (str(out), '')))
    win._save_selection_as()

    assert out.exists()
    tag = tmp_path / "fragment_gv_tag.csv"
    assert tag.exists()
    assert "Station 7" in tag.read_text(encoding='utf-8')

    saved = load_node_csv(str(out))
    assert {n.id for n in saved} == {1, 3, 4}
    assert saved[0].type == NODE_TYPE_WORLD

    # ...and it is still where it was drawn (the whole point of the feature).
    # Both scenes must share the window's base_scale: a topology offset is
    # proportional to it, while a root's translate is a literal world
    # position, so the bake is only exact at the Global Scale it was made at.
    src = win._viewport.scene
    reloaded = Scene(saved, base_scale=src.base_scale)
    for i in (3, 4):
        assert np.allclose(node_world_matrix(src.node_by_id(i), src),
                           node_world_matrix(reloaded.node_by_id(i), reloaded),
                           atol=1e-5)

    assert "Saved 3 node(s)" in win.statusBar().currentMessage()
    assert "re-rooted" in win.statusBar().currentMessage()


def test_channel_companions_travel_with_the_selection(qapp, tmp_path, monkeypatch):
    """An animated scene's fragment keeps its animation: the ch-map/ch-tracks
    pair is filtered to the exported nodes' channels and named so
    find_channel_files will pick it up next to the new node CSV."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "src_gv_ch-map.csv").write_text(
        "id,channel_id,track_id,attribute,track_table_id,ch_map_table_id,record_id\n"
        "0,1,1,translate_z,0,0,0\n"
        "1,2,2,translate_z,0,0,0\n", encoding='utf-8')
    (src_dir / "src_gv_ch-tracks.csv").write_text(
        "cyclecount,ch1,ch2\n0,0.5,0.9\n1,1.5,1.9\n", encoding='utf-8')

    nodes = _scene_nodes()
    next(n for n in nodes if n.id == 3).extras['ch_input_id'] = 2
    win = _win(nodes)
    win._current_path = str(src_dir / "src_gv_node.csv")
    win._table.select_by_ids({3})

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out = out_dir / "frag_gv_node.csv"
    monkeypatch.setattr(mw.QDialog, 'exec', lambda self: mw.QDialog.DialogCode.Accepted)
    monkeypatch.setattr(mw.QFileDialog, 'getSaveFileName',
                        staticmethod(lambda *a, **k: (str(out), '')))
    win._save_selection_as()

    assert (out_dir / "frag_gv_ch-map.csv").exists()
    assert (out_dir / "frag_gv_ch-tracks.csv").exists()
    map_text = (out_dir / "frag_gv_ch-map.csv").read_text(encoding='utf-8')
    assert ",2,2,translate_z" in map_text and ",1,1,translate_z" not in map_text
    assert find_channel_files(str(out)) == (out_dir / "frag_gv_ch-map.csv",
                                            out_dir / "frag_gv_ch-tracks.csv")
    assert "1 channel(s), 1 track(s)" in win.statusBar().currentMessage()


def test_channel_checkbox_is_off_when_the_scene_has_none(qapp):
    dlg = SaveSelectionDialog(Scene(_scene_nodes()), {3}, has_channels=False)
    assert not dlg.include_channels
    assert not dlg._channels.isEnabled()
    dlg.deleteLater()


def test_save_with_no_selection_says_so(qapp):
    win = _win(_scene_nodes())
    win._save_selection_as()
    assert "Select one or more nodes" in win.statusBar().currentMessage()


def test_cancelling_the_file_dialog_writes_nothing(qapp, tmp_path, monkeypatch):
    win = _win(_scene_nodes())
    win._table.select_by_ids({3})
    monkeypatch.setattr(mw.QDialog, 'exec', lambda self: mw.QDialog.DialogCode.Accepted)
    monkeypatch.setattr(mw.QFileDialog, 'getSaveFileName',
                        staticmethod(lambda *a, **k: ('', '')))
    win._save_selection_as()
    assert not list(tmp_path.iterdir())


def test_default_name_keeps_the_node_tag_convention(qapp):
    win = _win(_scene_nodes())
    win._current_path = str(r"C:\scenes\Cyclone_gv_node20260814101010.csv")
    name = win._selection_default_name()
    assert name.endswith("Cyclone_gv_selection_node.csv")

    win._current_path = None
    assert win._selection_default_name().endswith("gv_selection_node.csv")
