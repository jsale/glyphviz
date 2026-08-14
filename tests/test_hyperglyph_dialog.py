"""
Hyperglyph Generator dialog wiring, through the real widgets.

The capture math is pinned in tests/test_hyperglyph_recipe_export.py; what's
pinned here is that the dialog reaches it — that Save Recipe writes what the
PREVIEW currently looks like rather than what was generated a minute ago, that
the checkbox actually switches between the two, and that the large-hyperglyph
prompt can turn a save away.

Qt is needed but a GL context is not — same arrangement as
tests/test_topo_scale_gui.py, so these keep running on a box with no
framebuffer.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication, QMessageBox     # noqa: E402

from glyphviz_core.glyph_recipe import (                    # noqa: E402
    COMPOSER_EDIT_NODE_WARN, load_recipe, recipe_node_count,
)
from glyphviz_gl import main_window as mw                   # noqa: E402
from glyphviz_gl.hyperglyph_dialog import (                 # noqa: E402
    HyperglyphGeneratorDialog,
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


@pytest.fixture
def dialog(qapp):
    win = mw.MainWindow()
    dlg = HyperglyphGeneratorDialog(win)
    yield dlg
    dlg.close()
    win.close()


def _regenerate(dlg, seed=7, branch_levels=4, max_nodes=500, idle=True):
    dlg._w_randomize.setChecked(False)
    dlg._w_seed.setValue(seed)
    dlg._w_branch_levels.setValue(branch_levels)
    dlg._w_max_nodes.setValue(max_nodes)
    dlg._w_idle_motion.setChecked(idle)
    dlg._regenerate()


def _spin_preview(dlg, cycles=6000.0):
    """Wind the preview's live nodes forward the way the viewport's repaint
    tick does, without needing one."""
    for n in dlg._mini_vp.nodes:
        n.rotate_x += n.rotate_rate_x * cycles
        n.rotate_y += n.rotate_rate_y * cycles
        n.rotate_z += n.rotate_rate_z * cycles


# --- button state -------------------------------------------------------------

def test_save_is_disabled_until_a_design_exists(dialog):
    """There is nothing to write before the first Regenerate — the same rule
    Insert into Scene already follows."""
    assert not dialog._save_btn.isEnabled()
    assert dialog._recipe_to_save() is None
    _regenerate(dialog)
    assert dialog._save_btn.isEnabled()


def test_recipe_name_carries_the_seed(dialog):
    """The seed is the design's identity, and it is what the Composer's Name
    field and the default filename are built from."""
    _regenerate(dialog, seed=1234)
    assert dialog._recipe.name == 'Hyperglyph_1234'


# --- what Save Recipe would write ---------------------------------------------

def test_capture_off_writes_the_generated_orientation(dialog):
    _regenerate(dialog)
    _spin_preview(dialog)
    dialog._w_capture_live.setChecked(False)
    assert dialog._recipe_to_save() is dialog._recipe


def test_capture_on_reads_the_live_preview_nodes(dialog):
    """The pose has to come from the nodes the viewport has been animating,
    not from a fresh generate_nodes() — otherwise the option would look
    plumbed and capture nothing."""
    _regenerate(dialog)
    authored = [(l.rotate_x, l.rotate_y, l.rotate_z) for l in dialog._recipe.levels]
    _spin_preview(dialog)

    saved = dialog._recipe_to_save()
    posed = [(l.rotate_x, l.rotate_y, l.rotate_z) for l in saved.levels]
    assert posed != authored
    assert [(l.rotate_x, l.rotate_y, l.rotate_z) for l in dialog._recipe.levels] == authored

    live = dialog._mini_vp.nodes[0]
    assert saved.levels[0].rotate_x % 360.0 == pytest.approx(live.rotate_x % 360.0)


def test_capture_on_is_a_no_op_without_idle_motion(dialog):
    """Nothing has moved, so the checkbox must not silently alter the design
    — that is why it can stay checked by default."""
    _regenerate(dialog, idle=False)
    saved = dialog._recipe_to_save()
    for before, after in zip(dialog._recipe.levels, saved.levels):
        assert (after.rotate_x, after.rotate_y, after.rotate_z) == \
               (before.rotate_x, before.rotate_y, before.rotate_z)


def test_saved_file_reloads_as_the_posed_design(dialog, tmp_path, monkeypatch):
    """The whole point, end to end: spin the preview, click Save, and get a
    file the Glyph Composer opens holding the pose that was on screen."""
    _regenerate(dialog)
    _spin_preview(dialog)
    expected = dialog._recipe_to_save()

    path = tmp_path / 'design.json'
    monkeypatch.setattr('glyphviz_gl.hyperglyph_dialog.QFileDialog.getSaveFileName',
                        staticmethod(lambda *a, **k: (str(path), '')))
    dialog._save_recipe_json()

    reloaded = load_recipe(str(path))
    assert len(reloaded.levels) == len(expected.levels)
    for got, want in zip(reloaded.levels, expected.levels):
        assert (got.rotate_x, got.rotate_y, got.rotate_z) == \
               (want.rotate_x, want.rotate_y, want.rotate_z)
        assert got.count == want.count and got.topo == want.topo


def test_cancelling_the_file_dialog_writes_nothing(dialog, tmp_path, monkeypatch):
    _regenerate(dialog)
    monkeypatch.setattr('glyphviz_gl.hyperglyph_dialog.QFileDialog.getSaveFileName',
                        staticmethod(lambda *a, **k: ('', '')))
    dialog._save_recipe_json()
    assert not list(tmp_path.iterdir())


# --- the large-hyperglyph warning ---------------------------------------------

def test_ordinary_design_is_not_questioned(dialog, monkeypatch):
    """A prompt on every save would just be trained away. The dialog's default
    budget must clear it silently."""
    _regenerate(dialog, max_nodes=500)
    monkeypatch.setattr(QMessageBox, 'exec',
                        lambda self: pytest.fail('prompted for a small design'))
    assert dialog._confirm_large_recipe(dialog._recipe)


def test_large_design_warns_and_cancel_aborts_the_save(dialog, monkeypatch):
    _regenerate(dialog, branch_levels=5, max_nodes=20000)
    assert recipe_node_count(dialog._recipe) > COMPOSER_EDIT_NODE_WARN

    monkeypatch.setattr(QMessageBox, 'exec',
                        lambda self: QMessageBox.StandardButton.Cancel)
    monkeypatch.setattr('glyphviz_gl.hyperglyph_dialog.QFileDialog.getSaveFileName',
                        staticmethod(lambda *a, **k: pytest.fail('asked for a path after Cancel')))
    dialog._save_recipe_json()


def test_large_design_is_flagged_in_the_info_line(dialog):
    """Said while Regenerate is still one cheap click away, not only once the
    user has committed to saving."""
    _regenerate(dialog, branch_levels=5, max_nodes=20000)
    assert 'Glyph Composer' in dialog._info_label.text()

    _regenerate(dialog, max_nodes=500)
    assert 'Glyph Composer' not in dialog._info_label.text()
