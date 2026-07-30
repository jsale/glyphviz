"""
Drag-and-drop Qt plumbing tests.

test_drop_router.py covers the routing decisions without Qt; this file covers
the part that can only be checked with real events — that MainWindow accepts
the right drags, refuses the wrong ones, reads Shift as "merge", and defers the
actual load out of dropEvent (the drag SOURCE stays blocked until dropEvent
returns, so unzipping must not happen inside it).

Needs a QApplication, so it runs offscreen and is skipped if Qt can't start.
"""
import csv
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl      # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDropEvent        # noqa: E402
from PySide6.QtWidgets import QApplication                   # noqa: E402

_NODE_COLS = [
    'id', 'type', 'parent_id', 'branch_level',
    'translate_x', 'translate_y', 'translate_z',
    'rotate_x', 'rotate_y', 'rotate_z',
    'scale_x', 'scale_y', 'scale_z',
    'color_r', 'color_g', 'color_b', 'color_a',
    'geometry', 'hide', 'topo',
]


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                       # pragma: no cover
            pytest.skip(f"Qt unavailable: {exc}")
    return app


@pytest.fixture
def win(qapp):
    from glyphviz_gl.main_window import MainWindow
    w = MainWindow()
    yield w
    w.close()


def _write_node_csv(path, rows=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(_NODE_COLS)
        for i in range(rows):
            w.writerow([i + 1, 5, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1,
                        255, 255, 255, 255, 3, 0, 0])
    return path


def _mime(*paths):
    """Build drop mime data.

    Callers MUST hold the returned object in a local for as long as the event
    is used: the event only stores a C++ pointer, so letting the Python wrapper
    be collected leaves event.mimeData() re-wrapped as a bare QObject. Real
    drops don't have this problem — Qt's drag manager owns the mime data — it's
    purely an artifact of synthesising events.
    """
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return m


def _drag_enter(mime, modifiers=Qt.KeyboardModifier.NoModifier):
    return QDragEnterEvent(
        QPointF(10, 10).toPoint(), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, modifiers,
    )


def _drop(mime, modifiers=Qt.KeyboardModifier.NoModifier):
    return QDropEvent(
        QPointF(10, 10), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, modifiers,
    )


def test_window_accepts_drops(win):
    assert win.acceptDrops()


def test_drag_enter_accepts_a_node_csv(win, tmp_path):
    mime = _mime(_write_node_csv(tmp_path / 'gv_node.csv'))
    ev = _drag_enter(mime)
    win.dragEnterEvent(ev)
    assert ev.isAccepted()


def test_drag_enter_refuses_an_unsupported_file(win, tmp_path):
    junk = tmp_path / 'notes.docx'
    junk.write_text('x', encoding='utf-8')
    mime = _mime(junk)
    ev = _drag_enter(mime)
    win.dragEnterEvent(ev)
    assert not ev.isAccepted()


def test_drag_enter_refuses_a_non_file_url(win):
    """A link dragged out of a browser has URLs but no local path."""
    mime = QMimeData()
    mime.setUrls([QUrl('https://example.com/page')])
    ev = _drag_enter(mime)
    win.dragEnterEvent(ev)
    assert not ev.isAccepted()


def test_drop_defers_the_load_out_of_drop_event(win, qapp, tmp_path):
    """dropEvent must return before loading — the drag source is blocked
    until it does."""
    csv_path = _write_node_csv(tmp_path / 'gv_node.csv', rows=3)
    mime = _mime(csv_path)
    ev = _drop(mime)
    win.dropEvent(ev)
    assert ev.isAccepted()
    assert win.nodes == [], "load happened inside dropEvent instead of after it"
    qapp.processEvents()
    assert len(win.nodes) == 3


def test_shift_drop_merges(win, qapp, tmp_path):
    csv_path = _write_node_csv(tmp_path / 'gv_node.csv', rows=3)
    mime = _mime(csv_path)

    win.dropEvent(_drop(mime))
    qapp.processEvents()
    assert len(win.nodes) == 3

    win.dropEvent(_drop(mime, Qt.KeyboardModifier.ShiftModifier))
    qapp.processEvents()
    assert len(win.nodes) == 6, "Shift+drop replaced the scene instead of merging"


def test_plain_drop_replaces(win, qapp, tmp_path):
    csv_path = _write_node_csv(tmp_path / 'gv_node.csv', rows=3)
    mime = _mime(csv_path)
    for _ in range(2):
        win.dropEvent(_drop(mime))
        qapp.processEvents()
    assert len(win.nodes) == 3, "a plain drop should replace, not accumulate"


def test_drop_with_no_urls_is_ignored(win):
    mime = QMimeData()
    ev = _drop(mime)
    win.dropEvent(ev)
    assert not ev.isAccepted()
