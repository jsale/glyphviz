"""
Tag text font size — the World-node setting, the CSV column, and the panel.

Three things are pinned here:

  * The DEFAULT is what a file with no tag_font_size column loads as, so
    raising it is what makes every existing scene's labels bigger. It is also
    what keeps those files byte-stable through a load/save round trip — the
    column is only written when someone actually changed the size.
  * The viewport reads the size off the World node (type=0), like the tag
    colors, and clamps it — a Channels track or a hand-edited CSV can put any
    number in the field.
  * The Properties panel slider writes it, and loading a scene syncs the
    slider back WITHOUT synthesizing a World row into files that have none.

Qt is needed for the last group but a GL context is not, the same arrangement
as tests/test_camera_smoothing_viewport.py.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from glyphviz_core.csv_reader import load_node_csv, save_node_csv
from glyphviz_core.node import (
    Node, NODE_TYPE_WORLD,
    TAG_DEFAULT_FONT_SIZE, TAG_FONT_SIZE_MIN, TAG_FONT_SIZE_MAX,
)


def _node(node_id=1, node_type=5, **overrides):
    base = dict(
        id=node_id, type=node_type, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=255, color_g=0, color_b=0, color_a=255,
        geometry=3, hide=0, topo=1,
    )
    base.update(overrides)
    return Node(**base)


# --- the default -------------------------------------------------------------

def test_default_is_larger_than_the_old_hardcoded_nine():
    # The whole point of the setting having a default at all: labels used to
    # be painted at a hardcoded 9 pt, which read too small.
    assert TAG_DEFAULT_FONT_SIZE > 9
    assert TAG_FONT_SIZE_MIN < TAG_DEFAULT_FONT_SIZE < TAG_FONT_SIZE_MAX


def test_fresh_node_gets_the_default():
    assert _node().tag_font_size == TAG_DEFAULT_FONT_SIZE


# --- CSV ---------------------------------------------------------------------

def test_missing_column_loads_as_the_default(tmp_path):
    path = tmp_path / 'gv_node.csv'
    # The 20 columns the loader requires, and nothing else.
    path.write_text(
        'id,type,parent_id,branch_level,translate_x,translate_y,translate_z,'
        'rotate_x,rotate_y,rotate_z,scale_x,scale_y,scale_z,'
        'color_r,color_g,color_b,color_a,geometry,hide,topo\n'
        '1,5,0,0,0,0,0,0,0,0,1,1,1,255,0,0,255,3,0,1\n',
        encoding='utf-8')
    nodes = load_node_csv(str(path))
    assert [n.tag_font_size for n in nodes] == [TAG_DEFAULT_FONT_SIZE]


def test_default_size_writes_no_column(tmp_path):
    path = tmp_path / 'out.csv'
    save_node_csv([_node(1, NODE_TYPE_WORLD), _node(2)], str(path))
    header = path.read_text(encoding='utf-8').splitlines()[0]
    assert 'tag_font_size' not in header


def test_custom_size_round_trips(tmp_path):
    world = _node(1, NODE_TYPE_WORLD, tag_font_size=22)
    path = tmp_path / 'out.csv'
    save_node_csv([world, _node(2)], str(path))
    assert 'tag_font_size' in path.read_text(encoding='utf-8').splitlines()[0]

    back = load_node_csv(str(path))
    assert back[0].tag_font_size == 22
    # Only the World row carries the setting; the rest stay at the default,
    # which is what the viewport falls back to if the World row goes away.
    assert back[1].tag_font_size == TAG_DEFAULT_FONT_SIZE


# The "a shipped example must not grow a column when re-saved" guard used to
# live here, and only ever audited sorted(examples)[0] -- any new scene sorting
# earlier silently took over the slot. It now covers every scene, and every
# optional column rather than just this one:
# tests/test_compact_csv_save.py::test_every_example_scene_stays_column_stable.


# --- channel binding ---------------------------------------------------------

def test_bindable_as_a_channel_attribute():
    from glyphviz_core.channel_engine import (
        _ATTR_TO_FIELD, _FIELD_RANGE, _INT_FIELDS, _TRANSFORM_FIELDS,
    )
    assert _ATTR_TO_FIELD['tag_font_size'] == 'tag_font_size'
    assert 'tag_font_size' in _INT_FIELDS          # point sizes are whole numbers
    assert _FIELD_RANGE['tag_font_size'] == (TAG_FONT_SIZE_MIN, TAG_FONT_SIZE_MAX)
    # Label size changes what is drawn, never where anything sits.
    assert 'tag_font_size' not in _TRANSFORM_FIELDS


# --- viewport ----------------------------------------------------------------

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtWidgets import QApplication          # noqa: E402

from glyphviz_gl.viewport import Viewport           # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                    # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')
    return app


def test_viewport_falls_back_to_the_default_with_no_world_node(qapp):
    vp = Viewport()
    vp.set_nodes([_node(1)])
    assert vp._tag_font_size() == TAG_DEFAULT_FONT_SIZE


def test_viewport_reads_the_world_node(qapp):
    vp = Viewport()
    vp.set_nodes([_node(1, NODE_TYPE_WORLD, tag_font_size=20), _node(2)])
    assert vp._tag_font_size() == 20


@pytest.mark.parametrize('stored,expected', [
    (0, TAG_FONT_SIZE_MIN),
    (-4, TAG_FONT_SIZE_MIN),
    (500, TAG_FONT_SIZE_MAX),
])
def test_viewport_clamps_out_of_range_values(qapp, stored, expected):
    vp = Viewport()
    vp.set_nodes([_node(1, NODE_TYPE_WORLD, tag_font_size=stored), _node(2)])
    assert vp._tag_font_size() == expected


# --- Properties panel --------------------------------------------------------

from glyphviz_gl import main_window as mw           # noqa: E402


@pytest.fixture
def win(qapp):
    w = mw.MainWindow()
    yield w
    w.close()


def test_slider_starts_at_the_default(win):
    assert win._tag_font_slider.value() == TAG_DEFAULT_FONT_SIZE
    assert win._tag_font_slider.minimum() == TAG_FONT_SIZE_MIN
    assert win._tag_font_slider.maximum() == TAG_FONT_SIZE_MAX
    assert str(TAG_DEFAULT_FONT_SIZE) in win._tag_font_label.text()


def test_dragging_the_slider_sets_the_world_node(win):
    win._viewport.set_nodes(win.nodes)
    win._tag_font_slider.setValue(18)
    world = [n for n in win.nodes if n.type == NODE_TYPE_WORLD]
    assert len(world) == 1
    assert world[0].tag_font_size == 18
    assert '18' in win._tag_font_label.text()
    assert win._viewport._tag_font_size() == 18


def test_loading_a_scene_syncs_the_slider(win):
    world = _node(1, NODE_TYPE_WORLD, tag_font_size=26)
    win.nodes[:] = [world, _node(2)]
    win._viewport.set_nodes(win.nodes)
    win._refresh_scene_settings()
    assert win._tag_font_slider.value() == 26
    assert '26' in win._tag_font_label.text()


def test_refresh_does_not_synthesize_a_world_node(win):
    # The slider's handler calls _ensure_world_node(); syncing the panel on
    # load must not go through it, or merely opening a file would add a row.
    win.nodes[:] = [_node(2)]
    win._viewport.set_nodes(win.nodes)
    win._refresh_scene_settings()
    assert [n.type for n in win.nodes] == [5]
    assert win._tag_font_slider.value() == TAG_DEFAULT_FONT_SIZE


def test_the_setting_reaches_real_painted_ink(qapp):
    """End to end through the actual painting code: bigger setting, bigger
    pixels. Everything above pins a number moving between objects — this pins
    that the number is the one _paint_tags draws with."""
    import numpy as np
    from PySide6.QtGui import QColor, QImage, QPainter

    def ink_height(stored):
        vp = Viewport()
        vp.set_nodes([_node(1, NODE_TYPE_WORLD, tag_font_size=stored), _node(2)])
        img = QImage(400, 120, QImage.Format.Format_RGB32)
        img.fill(QColor(0, 0, 0))
        painter = QPainter(img)
        font = painter.font()
        font.setPointSize(vp._tag_font_size())
        painter.setFont(font)
        vp._paint_tags(painter, [("Station Alpha", 30, 80, None)])
        painter.end()
        buf = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(120, -1, 4)
        rows = np.flatnonzero(buf[:, :, :3].max(axis=(1, 2)) > 40)
        return rows[-1] - rows[0] + 1 if len(rows) else 0

    small, default, large = ink_height(9), ink_height(TAG_DEFAULT_FONT_SIZE), ink_height(28)
    assert 0 < small < default < large
    # And the clamp is enforced on the way to the paint, not just in the panel.
    assert ink_height(500) == ink_height(TAG_FONT_SIZE_MAX)
