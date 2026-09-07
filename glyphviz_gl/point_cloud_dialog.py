"""
Import Point Cloud dialog — LAS/LAZ/PLY/XYZ into a TOPO_POINTCLOUD scene.

The dialog's real job is not collecting options; it is showing the user what
is actually in the file BEFORE they commit. A LIDAR tile arrives with 10
million points, coordinates in the hundreds of thousands, and colour that may
or may not exist — and every one of those facts changes what a sensible
import looks like. So the flow is: scan the header, report, then offer the
choices that report makes meaningful.

Reading runs SYNCHRONOUSLY, under a wait cursor. It was on a worker thread
first, on the reasoning that decompressing a 10M-point LAZ shouldn't freeze
the window -- but measured, that file scans in 0.9 s and imports in 1.4 s,
and the threading bought a class of bug worth far more than a second: a
QThread destroyed with its dialog aborts the process outright, and every
arrangement of parenting, joining and retiring traded that crash for a hang
somewhere else. A modal dialog that is briefly busy is the honest trade.

All the actual work is in glyphviz_core/point_cloud_loader.py, which is
Qt-free — this file is only the form around it.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QProgressBar, QPushButton, QSpinBox, QVBoxLayout,
)

from glyphviz_core import point_cloud_loader as pcl

# Point counts the target spin box steps through. The top of the range is
# deliberately reachable but signposted: 100k is comfortable, 250k works and
# is slow to load, past that the node model (not the renderer) gives out.
POINT_TARGET_MIN = 1_000
POINT_TARGET_MAX = 500_000
# One click of the arrows. 10,000 was the first choice and it is too fine for
# a range that runs to half a million -- Jeff's report: climbing from the
# 100,000 default toward a 442,767-point file meant ~34 clicks. 50,000 crosses
# the whole range in ten, and an exact count is typed rather than clicked.
POINT_TARGET_STEP = 50_000


def scan_file(path: str) -> dict:
    """Describe a point-cloud file without loading all of it.

    LAS/LAZ carry point count, extents and the dimension list in the header,
    so a scan is nearly free however large the file — which is the whole
    point, since the file may be gigabytes. Classification counts are the one
    thing worth reading points for, and that is why the LAS branch takes a
    small sample rather than the header alone.

    Other formats have no header worth the name, so they are read in full at
    a decimated count; those files are small enough for that to be fine.
    """
    ext = Path(path).suffix.lower()
    if ext in pcl.LAS_EXTENSIONS:
        import laspy
        with laspy.open(path) as reader:
            header = reader.header
            dims = {d.name.lower() for d in header.point_format.dimensions}
            span = header.maxs - header.mins
            info = {
                'points': int(header.point_count),
                'span': [float(v) for v in span],
                'has_rgb': {'red', 'green', 'blue'} <= dims,
                'has_classification': 'classification' in dims,
                'has_intensity': 'intensity' in dims,
                'version': str(header.version),
                'classes': {},
            }
        if info['has_classification']:
            # A sample, not the file: class PROPORTIONS are what the user is
            # deciding from, and 200k points settle those long before the
            # remaining millions would change them.
            sample = pcl.load_point_cloud(path, max_points=200_000,
                                          method='random')
            info['classes'] = {c: (pcl.class_name(c), n)
                               for c, n in sample.class_counts().items()}
            if sample.colors is None:
                info['has_rgb'] = False     # column present but all zero
        return info

    data = pcl.load_point_cloud(path, max_points=200_000, method='random')
    return {
        'points': data.total_points,
        'span': [float(v) for v in data.span()],
        'has_rgb': data.colors is not None,
        'has_classification': data.classification is not None,
        'has_intensity': data.intensity is not None,
        'version': ext.lstrip('.').upper(),
        'classes': {c: (pcl.class_name(c), n)
                    for c, n in data.class_counts().items()},
    }


class PointCloudImportDialog(QDialog):
    """Options for importing one point-cloud file.

    On accept, `self.nodes` holds the scene-ready node list and `self.report`
    the import summary; both are None if the user cancelled or the read
    failed.
    """

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Point Cloud")
        self._path = path
        self.nodes = None
        self.report = None
        self._summary: dict | None = None

        root = QVBoxLayout(self)

        self._file_label = QLabel(f"<b>{Path(path).name}</b>")
        self._file_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self._file_label)

        self._info = QLabel("Reading file…")
        self._info.setWordWrap(True)
        self._info.setStyleSheet("color: #888;")
        root.addWidget(self._info)

        # --- points ---
        pts_box = QGroupBox("Points")
        pts_form = QFormLayout(pts_box)
        self._target = QSpinBox()
        self._target.setRange(POINT_TARGET_MIN, POINT_TARGET_MAX)
        self._target.setSingleStep(POINT_TARGET_STEP)
        self._target.setGroupSeparatorShown(True)
        # Without this, typing "442767" emits valueChanged six times -- once
        # per keystroke, at 4, 44, 442, 4427, 44276 and finally 442767 -- and
        # every one of those is a nonsense intermediate value that the info
        # line would dutifully recompute a sampling ratio for.
        self._target.setKeyboardTracking(False)
        self._target.setValue(pcl.DEFAULT_MAX_POINTS)
        # Connected ONCE, here, and to the cheap label refresh rather than to
        # the whole scan handler. Connecting it from inside _scan_done (which
        # is what this used to do) made every emission add another connection
        # AND re-enter the handler, so click N did 2^N passes: the eighth
        # click ran 128 times, the twelfth 2,048, and a climb of thirty-odd
        # clicks locked the app up hard. Jeff hit exactly that.
        self._target.valueChanged.connect(self._refresh_info)
        self._target.setToolTip(
            "How many points to keep.\n\n"
            "Every point becomes a real node — clickable, taggable, "
            "animatable. The renderer is not the limit: it draws a million "
            "points in 0.6 ms, and a 442,000-point cloud runs at about "
            "400 fps. The cost is memory and disk — roughly 2 KB and 550 "
            "bytes per point.\n\n"
            "100,000 points saves as a 55 MB scene that reopens in under "
            "2 seconds. 442,000 saves as 244 MB and reopens in 9. Importing "
            "is much cheaper than saving either way: 442,000 points come out "
            "of a compressed LAZ in about 4 seconds.")
        pts_form.addRow("Keep at most:", self._target)

        self._method = QComboBox()
        for key, label in (
            ('random', 'Random sample (even, unbiased)'),
            ('voxel', 'Voxel grid (even spatial density)'),
            ('stride', 'Every Nth point (fastest)'),
        ):
            self._method.addItem(label, key)
        self._method.setToolTip(
            "How to choose which points to keep.\n\n"
            "Random is reproducible and unbiased — the safe default.\n"
            "Voxel evens out density in 3-D, so it reaches more of the "
            "cloud's occupied volume than a random sample of the same "
            "size (85% against 74%, measured on a real 10-million-point "
            "tile). Because the grid is volumetric it shifts points off "
            "flat ground and onto structure — trees, buildings — which "
            "is usually what you want to look at. Takes about twice as "
            "long.\n"
            "Every Nth is fastest, but a file written in acquisition order "
            "can alias against the scan pattern and sample stripes.")
        pts_form.addRow("Method:", self._method)
        root.addWidget(pts_box)

        # --- appearance ---
        look_box = QGroupBox("Appearance")
        look_form = QFormLayout(look_box)
        self._color = QComboBox()
        for key, label in (
            ('auto', 'Automatic'),
            ('rgb', 'File RGB colour'),
            ('classification', 'Classification (ground/vegetation/building…)'),
            ('elevation', 'Elevation ramp'),
            ('intensity', 'Return intensity'),
        ):
            self._color.addItem(label, key)
        self._color.setToolTip(
            "Automatic picks the file's own RGB when it has any, then "
            "classification when the file is genuinely classified, then an "
            "elevation ramp. Most public LIDAR has no RGB at all.")
        look_form.addRow("Colour by:", self._color)

        self._point_size = QDoubleSpinBox()
        self._point_size.setRange(1.0, 64.0)
        self._point_size.setSingleStep(0.5)
        self._point_size.setValue(2.0)
        self._point_size.setSuffix(" px")
        self._point_size.setToolTip(
            "Rendered size of every point in the cloud.\n\n"
            "Stored on the cloud's parent node as ratio = size / 20, and "
            "editable there afterwards. One size per cloud: fixed-function "
            "OpenGL has no per-point size.")
        look_form.addRow("Point size:", self._point_size)

        self._span = QDoubleSpinBox()
        self._span.setRange(1.0, 100_000.0)
        self._span.setSingleStep(10.0)
        self._span.setValue(pcl.DEFAULT_WORLD_SPAN)
        self._span.setToolTip(
            "World-space width the scan is scaled to, measured across its "
            "larger horizontal axis.\n\n"
            "360 is GlyphViz's own 1:1 frame — the width of a default World "
            "Grid — so the scan lands at the same scale as everything else. "
            "The scale is uniform across all three axes; the scan is never "
            "stretched.")
        look_form.addRow("Fit to width:", self._span)

        self._exag = QDoubleSpinBox()
        self._exag.setRange(0.1, 50.0)
        self._exag.setSingleStep(0.5)
        self._exag.setValue(1.0)
        self._exag.setSuffix(" x")
        self._exag.setToolTip(
            "Vertical exaggeration, applied to Z only.\n\n"
            "1.0 is truthful. Terrain work routinely uses 2-3x because a "
            "200 m relief spread over 4 km reads as flat otherwise — but it "
            "IS a distortion, so it is off by default.")
        look_form.addRow("Vertical exaggeration:", self._exag)
        root.addWidget(look_box)

        # --- classification filter ---
        self._class_box = QGroupBox("Keep classifications")
        self._class_box.setCheckable(True)
        self._class_box.setChecked(False)
        self._class_box.setToolTip(
            "Import only the ticked classes.\n\n"
            "Dropping ground (class 2) is the usual first move on an aerial "
            "tile: it is most of the points, and removing it reveals the "
            "buildings and canopy underneath.")
        cbox = QVBoxLayout(self._class_box)
        self._class_list = QListWidget()
        self._class_list.setMaximumHeight(150)
        cbox.addWidget(self._class_list)
        btn_row = QHBoxLayout()
        for label, fn in (("All", self._check_all), ("None", self._check_none)):
            b = QPushButton(label)
            b.setMaximumWidth(70)
            b.clicked.connect(fn)
            btn_row.addWidget(b)
        btn_row.addStretch()
        cbox.addLayout(btn_row)
        self._class_box.setVisible(False)
        root.addWidget(self._class_box)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        self._buttons.button(
            QDialogButtonBox.StandardButton.Ok).setText("Import")
        self._buttons.accepted.connect(self._start_import)
        self._buttons.rejected.connect(self.reject)
        root.addWidget(self._buttons)
        self._ok().setEnabled(False)

        self._start_scan()

    # --- helpers ---

    def _ok(self):
        return self._buttons.button(QDialogButtonBox.StandardButton.Ok)

    def _check_all(self):
        for i in range(self._class_list.count()):
            self._class_list.item(i).setCheckState(Qt.CheckState.Checked)

    def _check_none(self):
        for i in range(self._class_list.count()):
            self._class_list.item(i).setCheckState(Qt.CheckState.Unchecked)

    # --- scan ---

    def _start_scan(self):
        """Read the file's header and describe it. Blocking, under a wait
        cursor -- a LAS/LAZ header scan is header-only and effectively free
        however large the file; the sample it takes for class proportions is
        capped at 200k points."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._progress.setVisible(True)
        self._progress.repaint()
        try:
            self._scan_done(scan_file(self._path), None)
        except Exception as exc:                        # noqa: BLE001
            self._scan_done(None, str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def _scan_done(self, summary, error):
        """The scan worker landed. Runs ONCE per dialog.

        Everything here is one-time setup: stash the summary, build the class
        tick list, enable Import. The part that has to re-run when an option
        changes is _refresh_info, and it is deliberately the only thing wired
        to valueChanged -- see the note at that connection.
        """
        self._progress.setVisible(False)
        if error is not None:
            self._info.setText(f"<span style='color:#c66'>Could not read this "
                               f"file:<br>{error}</span>")
            return
        self._summary = summary

        if summary['classes']:
            self._class_list.clear()
            for code, (name, count) in sorted(summary['classes'].items()):
                item = QListWidgetItem(f"{code}  {name}  ({count:,} sampled)")
                item.setData(Qt.ItemDataRole.UserRole, code)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self._class_list.addItem(item)
            self._class_box.setVisible(True)

        self._refresh_info()
        self._ok().setEnabled(True)

    def _refresh_info(self, _value=None):
        """Redraw the one-line file summary. Cheap by construction: it reads
        the cached scan result and sets a label, and touches nothing else.

        It is called on every tick of the point-target spin box, so anything
        that rebuilds a widget, re-reads the file, or reconnects a signal does
        NOT belong here."""
        summary = self._summary
        if summary is None:
            return
        n = summary['points']
        sx, sy, sz = summary['span']
        have = [k for k, present in (('RGB', summary['has_rgb']),
                                     ('classification',
                                      summary['has_classification']),
                                     ('intensity', summary['has_intensity']))
                if present]
        target = self._target.value()
        keeping = ""
        if n > target:
            keeping = (f"<br><span style='color:#c90'>Will keep "
                       f"{target:,} — about "
                       f"1 in {max(1, round(n / max(1, target))):,}</span>")
        else:
            keeping = ("<br><span style='color:#7a9'>Will keep every "
                       "point in the file</span>")
        self._info.setText(
            f"{summary['version']} · <b>{n:,}</b> points · "
            f"extent {sx:,.0f} × {sy:,.0f} × {sz:,.0f} source units<br>"
            f"Carries: {', '.join(have) if have else 'positions only'}"
            + keeping)

    # --- import ---

    def _keep_classes(self):
        # Gate on whether the list was POPULATED, not on isVisible(): a
        # widget in a dialog that has not been shown yet reports invisible,
        # and so does one inside a hidden parent, which would silently drop
        # the filter the user set. `count()` answers the question actually
        # being asked -- does this file have classifications to filter by.
        if not self._class_box.isChecked() or self._class_list.count() == 0:
            return None
        keep = [self._class_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self._class_list.count())
                if self._class_list.item(i).checkState() == Qt.CheckState.Checked]
        # An empty tick list would import nothing at all, which is never what
        # anyone means — treat it as "no filter" rather than an empty scene.
        return keep or None

    def _start_import(self):
        self._ok().setEnabled(False)
        self._progress.setVisible(True)
        self._info.setText("Importing…")
        self._info.repaint()
        self._progress.repaint()
        kwargs = dict(
            max_points=self._target.value(),
            method=self._method.currentData(),
            color_mode=self._color.currentData(),
            span=self._span.value(),
            exaggeration=self._exag.value(),
            point_size=self._point_size.value(),
            keep_classes=self._keep_classes(),
        )
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            nodes, report = pcl.import_to_nodes(self._path, **kwargs)
            self._import_done(nodes, report, None)
        except Exception as exc:                        # noqa: BLE001
            self._import_done(None, None, str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def _import_done(self, nodes, report, error):
        self._progress.setVisible(False)
        if error is not None:
            self._info.setText(f"<span style='color:#c66'>Import failed:<br>"
                               f"{error}</span>")
            self._ok().setEnabled(True)
            return
        self.nodes = nodes
        self.report = report
        self.accept()
