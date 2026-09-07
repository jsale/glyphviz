"""
Point-cloud import, through the real dialog and the real MainWindow.

The import math is pinned in tests/test_point_cloud_loader.py. What's pinned
here is the wiring — the parts that were actually wrong the first time:

  * the classification tick list must gate on whether it was POPULATED, not
    on isVisible(); a dialog that has not been shown reports every widget
    invisible, which silently dropped the filter;
  * a dropped .laz must route to the point-cloud importer while a dropped
    .ply keeps routing to the mesh importer, as it has since mesh import
    shipped;
  * the window must absorb a cloud through the same merge Ctrl+M uses, so
    ids are rebased rather than colliding with the loaded scene.
"""
import os

import numpy as np
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

pytest.importorskip('PySide6.QtWidgets')
laspy = pytest.importorskip('laspy')

from PySide6.QtCore import Qt                                   # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog             # noqa: E402

from glyphviz_core import drop_router as dr                     # noqa: E402
from glyphviz_core import point_cloud_loader as pcl             # noqa: E402
from glyphviz_core.node import Node                             # noqa: E402
from glyphviz_core.topology import TOPO_POINTCLOUD              # noqa: E402
from glyphviz_gl import main_window as mw                       # noqa: E402
from glyphviz_gl import point_cloud_dialog as pcd               # noqa: E402


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
def classified_las(tmp_path):
    """A small file with the two properties the dialog reacts to: more points
    than a default import keeps, and real classification."""
    rng = np.random.default_rng(5)
    n = 4000
    xyz = np.stack([
        500_000.0 + rng.random(n) * 800.0,
        4_000_000.0 + rng.random(n) * 800.0,
        100.0 + rng.random(n) * 40.0,
    ], axis=1)
    cls = rng.choice([2, 5, 6], size=n, p=[0.7, 0.2, 0.1]).astype(np.uint8)
    header = laspy.LasHeader(point_format=2, version="1.2")
    header.scales = np.array([0.01, 0.01, 0.01])
    header.offsets = np.floor(xyz.min(axis=0))
    las = laspy.LasData(header)
    las.x, las.y, las.z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    las.classification = cls
    path = tmp_path / "tile.las"
    las.write(str(path))
    return str(path)


def _settled(qapp, dlg, attr, timeout=60.0):
    """Spin the event loop until a dialog worker has finished."""
    import time
    deadline = time.perf_counter() + timeout
    while getattr(dlg, attr) is None and time.perf_counter() < deadline:
        qapp.processEvents()
    assert getattr(dlg, attr) is not None, f"{attr} never arrived"


# ------------------------------------------------------------ file scan ---

def test_scan_reports_what_is_in_the_file(classified_las):
    info = pcd.scan_file(classified_las)
    assert info['points'] == 4000
    assert info['has_classification'] is True
    assert info['has_rgb'] is False          # point_format 2 has no colour
    assert set(info['classes']) == {2, 5, 6}
    assert info['span'][0] == pytest.approx(800.0, abs=5.0)


def test_scan_of_an_unreadable_file_raises_rather_than_lying(tmp_path):
    bad = tmp_path / "broken.las"
    bad.write_bytes(b"not a LAS file at all")
    with pytest.raises(Exception):
        pcd.scan_file(str(bad))


# --------------------------------------------------------------- dialog ---

def test_dialog_populates_the_class_list(qapp, classified_las):
    dlg = pcd.PointCloudImportDialog(classified_las)
    _settled(qapp, dlg, '_summary')
    codes = {dlg._class_list.item(i).data(Qt.ItemDataRole.UserRole)
             for i in range(dlg._class_list.count())}
    assert codes == {2, 5, 6}
    assert dlg._ok().isEnabled()
    dlg.close()


def test_class_filter_survives_an_unshown_dialog(qapp, classified_las):
    """The bug: _keep_classes gated on isVisible(), which is False for every
    widget in a dialog that has not been shown — so the filter the user set
    was silently dropped. It must gate on the list being populated instead."""
    dlg = pcd.PointCloudImportDialog(classified_las)
    _settled(qapp, dlg, '_summary')
    assert not dlg.isVisible()
    dlg._class_box.setChecked(True)
    for i in range(dlg._class_list.count()):
        item = dlg._class_list.item(i)
        if item.data(Qt.ItemDataRole.UserRole) == 2:
            item.setCheckState(Qt.CheckState.Unchecked)
    assert sorted(dlg._keep_classes()) == [5, 6]
    dlg.close()


def test_unchecking_the_group_means_no_filter(qapp, classified_las):
    dlg = pcd.PointCloudImportDialog(classified_las)
    _settled(qapp, dlg, '_summary')
    dlg._class_box.setChecked(False)
    assert dlg._keep_classes() is None
    dlg.close()


def test_ticking_nothing_is_treated_as_no_filter(qapp, classified_las):
    """An empty tick list would import an empty scene, which is never what
    anyone means by it."""
    dlg = pcd.PointCloudImportDialog(classified_las)
    _settled(qapp, dlg, '_summary')
    dlg._class_box.setChecked(True)
    dlg._check_none()
    assert dlg._keep_classes() is None
    dlg.close()


def test_dialog_import_honours_every_option(qapp, classified_las):
    dlg = pcd.PointCloudImportDialog(classified_las)
    _settled(qapp, dlg, '_summary')

    dlg._target.setValue(1000)
    modes = [dlg._color.itemData(i) for i in range(dlg._color.count())]
    dlg._color.setCurrentIndex(modes.index('classification'))
    dlg._exag.setValue(4.0)
    dlg._point_size.setValue(5.0)
    dlg._class_box.setChecked(True)
    for i in range(dlg._class_list.count()):
        item = dlg._class_list.item(i)
        if item.data(Qt.ItemDataRole.UserRole) == 2:
            item.setCheckState(Qt.CheckState.Unchecked)

    dlg._start_import()
    _settled(qapp, dlg, 'nodes')

    from glyphviz_core import point_cloud as pc
    assert dlg.report['color_mode'] == 'classification'
    assert dlg.report['points'] == 1000
    assert dlg.report['exaggeration'] == 4.0
    assert set(dlg.report['classes']) <= {5, 6}
    assert pc.point_size(dlg.nodes[0]) == pytest.approx(5.0)
    dlg.close()


def test_the_point_budget_is_spent_on_the_classes_asked_for(qapp,
                                                            classified_las):
    """Ground is 70% of this file. Dropping it and asking for 1000 points
    must give 1000 — filtering AFTER the sample would give about 300."""
    dlg = pcd.PointCloudImportDialog(classified_las)
    _settled(qapp, dlg, '_summary')
    dlg._target.setValue(1000)
    dlg._class_box.setChecked(True)
    for i in range(dlg._class_list.count()):
        item = dlg._class_list.item(i)
        if item.data(Qt.ItemDataRole.UserRole) == 2:
            item.setCheckState(Qt.CheckState.Unchecked)
    dlg._start_import()
    _settled(qapp, dlg, 'nodes')
    assert dlg.report['points'] == 1000
    dlg.close()


def test_a_failed_import_reports_and_stays_open(qapp, tmp_path):
    bad = tmp_path / "broken.laz"
    bad.write_bytes(b"nope")
    dlg = pcd.PointCloudImportDialog(str(bad))
    import time
    deadline = time.perf_counter() + 30
    while 'Could not read' not in dlg._info.text() and time.perf_counter() < deadline:
        qapp.processEvents()
    assert 'Could not read' in dlg._info.text()
    assert dlg.nodes is None
    assert not dlg._ok().isEnabled()
    dlg.close()


# --------------------------------------------------- the point-target box ---
#
# Jeff hit a hard lock-up here: clicking the up-arrow to raise the point
# target froze the app. The step size was part of it (10,000 across a range
# running to 500,000 meant ~34 clicks to reach a 442,767-point file), but the
# cause was worse -- valueChanged was connected from INSIDE the handler it
# fired, so every emission added another connection AND re-entered the
# handler. Measured before the fix: click 1 ran the handler once, click 8 ran
# it 128 times, click 12 ran it 2,048 times in 65 ms. Thirty-odd clicks is
# billions of passes.

def test_clicking_the_point_target_does_linear_work(qapp, classified_las):
    """The regression. N clicks must do N units of work, not 2^N."""
    dlg = pcd.PointCloudImportDialog(classified_las)
    _settled(qapp, dlg, '_summary')

    calls = []
    real = dlg._refresh_info
    dlg._target.valueChanged.disconnect()
    dlg._target.valueChanged.connect(lambda v: (calls.append(v), real(v)))

    # From the minimum, so every click really changes the value -- from the
    # 100,000 default the box reaches its ceiling in eight steps and the rest
    # correctly emit nothing.
    dlg._target.setValue(dlg._target.minimum())
    calls.clear()
    for _ in range(8):
        dlg._target.stepUp()
        qapp.processEvents()

    assert len(calls) == 8, f"expected one refresh per click, got {len(calls)}"
    dlg.close()


def test_the_scan_handler_never_re_enters(qapp, classified_las):
    """_scan_done is one-time setup: it stashes the summary, builds the class
    list and enables Import. Anything that has to re-run when an option
    changes belongs in _refresh_info, which is the only thing valueChanged is
    allowed to reach."""
    dlg = pcd.PointCloudImportDialog(classified_las)
    _settled(qapp, dlg, '_summary')

    hits = []
    real = dlg._scan_done
    dlg._scan_done = lambda summary, error: (hits.append(1),
                                             real(summary, error))[1]
    for _ in range(8):
        dlg._target.stepUp()
        qapp.processEvents()

    assert hits == [], "the spin box must not re-run the scan handler"
    # and the class list was built once, not once per click
    assert dlg._class_list.count() == 3
    dlg.close()


def test_the_class_ticks_survive_changing_the_point_target(qapp,
                                                           classified_las):
    """The re-entrant version rebuilt the class list on every tick, which
    silently re-checked every box the user had cleared."""
    dlg = pcd.PointCloudImportDialog(classified_las)
    _settled(qapp, dlg, '_summary')
    dlg._class_box.setChecked(True)
    for i in range(dlg._class_list.count()):
        item = dlg._class_list.item(i)
        if item.data(Qt.ItemDataRole.UserRole) == 2:
            item.setCheckState(Qt.CheckState.Unchecked)

    for _ in range(5):
        dlg._target.stepUp()
        qapp.processEvents()

    assert sorted(dlg._keep_classes()) == [5, 6]
    dlg.close()


def test_the_step_crosses_the_whole_range_in_a_few_clicks(qapp,
                                                          classified_las):
    dlg = pcd.PointCloudImportDialog(classified_las)
    _settled(qapp, dlg, '_summary')
    assert dlg._target.singleStep() == pcd.POINT_TARGET_STEP

    dlg._target.setValue(dlg._target.minimum())
    clicks = 0
    while dlg._target.value() < dlg._target.maximum() and clicks < 100:
        dlg._target.stepUp()
        clicks += 1
    assert dlg._target.value() == dlg._target.maximum()
    assert clicks <= 12, f"{clicks} clicks to cross the range is too many"
    dlg.close()


def test_typing_a_value_fires_one_refresh_not_one_per_keystroke(qapp,
                                                                classified_las):
    """With keyboard tracking on, typing "442767" emits at 4, 44, 442, 4427,
    44276 and 442767 — five nonsense intermediates, each recomputing a
    sampling ratio."""
    dlg = pcd.PointCloudImportDialog(classified_las)
    _settled(qapp, dlg, '_summary')
    assert dlg._target.keyboardTracking() is False

    calls = []
    real = dlg._refresh_info
    dlg._target.valueChanged.disconnect()
    dlg._target.valueChanged.connect(lambda v: (calls.append(v), real(v)))

    dlg._target.lineEdit().setText("442767")
    dlg._target.interpretText()
    qapp.processEvents()

    assert dlg._target.value() == 442767
    assert len(calls) == 1, calls
    dlg.close()


def test_the_summary_line_tracks_the_target(qapp, classified_las):
    """The file has 4,000 points, so the line has to say something different
    either side of that."""
    import re
    dlg = pcd.PointCloudImportDialog(classified_las)
    _settled(qapp, dlg, '_summary')

    def text():
        return re.sub('<[^>]+>', '', dlg._info.text())

    dlg._target.setValue(1_000)
    qapp.processEvents()
    assert '1,000' in text() and '1 in 4' in text()

    dlg._target.setValue(400_000)
    qapp.processEvents()
    assert 'every point in the file' in text()
    dlg.close()


# ---------------------------------------------------------- drop routing ---

@pytest.mark.parametrize('ext', ['.las', '.laz', '.xyz', '.pts'])
def test_point_cloud_extensions_route_to_the_importer(tmp_path, ext):
    p = tmp_path / f"scan{ext}"
    p.write_bytes(b"0 0 0\n")
    plan = dr.resolve_drop([str(p)])
    assert [a.kind for a in plan.actions] == [dr.ACTION_POINT_CLOUD]


def test_ply_still_routes_to_the_mesh_importer(tmp_path):
    """PLY has gone to the mesh importer since mesh import shipped, and a
    dropped PLY is far more often a model than a scan. File > Import Point
    Cloud accepts it explicitly for the other case."""
    p = tmp_path / "model.ply"
    p.write_bytes(b"ply\n")
    plan = dr.resolve_drop([str(p)])
    assert [a.kind for a in plan.actions] == [dr.ACTION_MESH]


def test_a_dropped_csv_is_still_treated_as_a_scene(tmp_path):
    """Node CSVs are identified by columns, not by name — claiming every .csv
    for the point-cloud importer would break that."""
    p = tmp_path / "gv_node.csv"
    p.write_text("id,type,parent_id,branch_level,translate_x,translate_y,"
                 "translate_z,rotate_x,rotate_y,rotate_z,scale_x,scale_y,"
                 "scale_z,color_r,color_g,color_b,color_a,geometry,hide,topo\n"
                 "1,5,0,0,0,0,0,0,0,0,1,1,1,9,9,9,255,7,0,0\n")
    plan = dr.resolve_drop([str(p)])
    assert [a.kind for a in plan.actions] == [dr.ACTION_OPEN_CSV]


def test_only_one_cloud_per_drop(tmp_path):
    """Importing opens a modal dialog; queueing several would stack them."""
    paths = []
    for i in range(3):
        p = tmp_path / f"scan{i}.xyz"
        p.write_bytes(b"0 0 0\n")
        paths.append(str(p))
    plan = dr.resolve_drop(paths)
    assert [a.kind for a in plan.actions] == [dr.ACTION_POINT_CLOUD]
    assert any('one point cloud at a time' in n for n in plan.notes)


# --------------------------------------------------------- window import ---

class _StubDialog:
    """Stands in for the import dialog so the window test is about the
    window, not about the form."""

    def __init__(self, nodes, report):
        self.nodes, self.report = nodes, report

    def exec(self):
        return QDialog.DialogCode.Accepted


def _glyph(nid):
    return Node(id=nid, type=5, parent_id=0, branch_level=0,
                translate_x=0.0, translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=9, color_g=9, color_b=9, color_a=255,
                geometry=7, hide=0, topo=0, text=f"existing {nid}")


def test_window_merges_a_cloud_without_colliding_ids(qapp, classified_las,
                                                     monkeypatch):
    nodes, report = pcl.import_to_nodes(classified_las, max_points=200)
    win = mw.MainWindow()
    # a loaded scene whose ids overlap the incoming cloud's exactly
    existing = [_glyph(i) for i in range(1, 6)]
    win.nodes = list(existing)
    win._viewport.set_nodes(win.nodes)
    win._table.set_nodes(win.nodes)

    monkeypatch.setattr(pcd, 'PointCloudImportDialog',
                        lambda p, parent=None: _StubDialog(nodes, report))
    assert win._load_point_cloud_path(classified_las)

    ids = [n.id for n in win.nodes]
    assert len(ids) == len(set(ids)), "id collision after import"
    assert len(win.nodes) == len(existing) + len(nodes)
    # the pre-existing nodes are untouched
    assert [n.id for n in win.nodes[:5]] == [1, 2, 3, 4, 5]

    clouds = [n for n in win.nodes if n.topo == TOPO_POINTCLOUD]
    assert len(clouds) == 1
    cloud = clouds[0]
    assert cloud.id > 5, "the cloud parent must be rebased past the scene"
    assert len([n for n in win.nodes if n.parent_id == cloud.id]) == 200


def test_window_import_reports_what_it_did(qapp, classified_las, monkeypatch):
    nodes, report = pcl.import_to_nodes(classified_las, max_points=200)
    win = mw.MainWindow()
    win.nodes = []
    win._viewport.set_nodes(win.nodes)
    win._table.set_nodes(win.nodes)
    monkeypatch.setattr(pcd, 'PointCloudImportDialog',
                        lambda p, parent=None: _StubDialog(nodes, report))
    win._load_point_cloud_path(classified_las)
    msg = win.statusBar().currentMessage()
    assert '200' in msg and 'tile.las' in msg
    assert '4,000' in msg          # honest about what it sampled from


def test_cancelling_the_dialog_changes_nothing(qapp, classified_las,
                                               monkeypatch):
    win = mw.MainWindow()
    win.nodes = [_glyph(1)]
    win._viewport.set_nodes(win.nodes)
    win._table.set_nodes(win.nodes)

    class _Cancelled:
        nodes = None
        report = None

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(pcd, 'PointCloudImportDialog',
                        lambda p, parent=None: _Cancelled())
    assert win._load_point_cloud_path(classified_las) is False
    assert len(win.nodes) == 1
