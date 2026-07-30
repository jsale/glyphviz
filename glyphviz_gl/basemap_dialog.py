"""
Fetch Basemap — GUI wrapper around glyphviz_core.basemap for the World Grid
panel. Prefills the lon/lat window from the selected grid's children (falling
back to the grid's current extents), previews exactly what a fetch will do
(provider, zoom, tile count, output size) live as the window is edited, and
runs the actual tile fetch on a worker thread so a slow server never freezes
the UI. The dialog only downloads and writes the PNG; wiring the image into
the scene (grid extents, texture_id bookkeeping, media reload) stays in
MainWindow, which owns those structures.

The map that comes back covers *exactly* the previewed window — MainWindow
sets the grid extents to the dialog's result_bbox, never to what the user
typed, so texture and child placement can't drift apart.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from glyphviz_core.basemap import (
    MERCATOR_LAT_LIMIT, PROVIDERS, BasemapError, BBox, bbox_from_nodes,
    build_basemap, plan_basemap,
)


class _FetchWorker(QThread):
    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, plan, out_path: Path, parent=None):
        super().__init__(parent)
        self._plan = plan
        self._out_path = out_path
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        def on_tile(done, total):
            if self._cancelled:
                raise BasemapError("Cancelled.")
            self.progress.emit(done, total)

        try:
            path = build_basemap(self._plan, self._out_path, progress=on_tile)
        except BasemapError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:   # requests/PIL surprises → message, not traceback
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.done.emit(str(path))


class BasemapFetchDialog(QDialog):
    """Modal fetch dialog. On accept, `result_path` is the written PNG and
    `result_bbox` the exact lon/lat window it covers."""

    def __init__(self, grid, nodes, out_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Fetch Basemap — World Grid {grid.id}")
        self._grid = grid
        self._nodes = nodes
        self._out_path = Path(out_path)
        self._worker: _FetchWorker | None = None
        self._plan = None
        self.result_path: Path | None = None
        self.result_bbox: BBox | None = None
        self.result_attribution: str = ""

        self._build_ui()
        self._prefill()
        self._refresh_plan()

    # ------------------------------------------------------------------ #
    # UI                                                                 #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QVBoxLayout(self)
        form = QFormLayout()

        self._provider = QComboBox()
        for p in PROVIDERS.values():
            self._provider.addItem(p.label, p.key)
        self._provider.setToolTip(
            "All providers are free and key-less. The required attribution is\n"
            "baked into the image corner, so it travels with the saved scene.")
        self._provider.currentIndexChanged.connect(self._refresh_plan)
        form.addRow("Map style:", self._provider)

        def spin(lo, hi):
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setDecimals(3)
            sb.setSingleStep(1.0)
            sb.valueChanged.connect(self._refresh_plan)
            return sb

        self._lon_min = spin(-180.0, 180.0)
        self._lon_max = spin(-180.0, 180.0)
        self._lat_min = spin(-MERCATOR_LAT_LIMIT, MERCATOR_LAT_LIMIT)
        self._lat_max = spin(-MERCATOR_LAT_LIMIT, MERCATOR_LAT_LIMIT)
        lon_row, lat_row = QWidget(), QWidget()
        for row, (a, b) in ((lon_row, (self._lon_min, self._lon_max)),
                            (lat_row, (self._lat_min, self._lat_max))):
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(4)
            lay.addWidget(a)
            lay.addWidget(b)
        form.addRow("Lon Min/Max:", lon_row)
        form.addRow("Lat Min/Max:", lat_row)

        self._fit_btn = QPushButton("Fit to Children")
        self._fit_btn.setToolTip(
            "Recompute the window from the lon/lat of the grid's children,\n"
            "with a little padding around the data.")
        self._fit_btn.clicked.connect(self._fit_to_children)
        form.addRow("", self._fit_btn)

        root.addLayout(form)

        # What the fetch will do — recomputed live, no network involved.
        self._preview = QLabel()
        self._preview.setWordWrap(True)
        root.addWidget(self._preview)

        self._status = QLabel(
            "The grid's extents will be set to this window so the map and\n"
            "child placement line up exactly. Tiles are cached on disk —\n"
            "refetching the same region is free.")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Fetch")
        self._buttons.accepted.connect(self._start_fetch)
        self._buttons.rejected.connect(self.reject)
        root.addWidget(self._buttons)

    def _prefill(self):
        bbox = bbox_from_nodes(self._nodes, self._grid.id)
        if bbox is None:
            lon_lo, lon_hi, lat_lo, lat_hi = self._grid.grid_extents()
            bbox = BBox(lon_lo, lon_hi, lat_lo, lat_hi).clamped()
            self._fit_btn.setEnabled(False)
            self._fit_btn.setToolTip("This grid has no children yet.")
        self._set_bbox(bbox)

    def _set_bbox(self, bbox: BBox):
        for sb, val in ((self._lon_min, bbox.lon_min), (self._lon_max, bbox.lon_max),
                        (self._lat_min, bbox.lat_min), (self._lat_max, bbox.lat_max)):
            sb.blockSignals(True)
            sb.setValue(val)
            sb.blockSignals(False)
        self._refresh_plan()

    def _fit_to_children(self):
        bbox = bbox_from_nodes(self._nodes, self._grid.id)
        if bbox is not None:
            self._set_bbox(bbox)

    def _current_bbox(self) -> BBox:
        return BBox(self._lon_min.value(), self._lon_max.value(),
                    self._lat_min.value(), self._lat_max.value())

    def _refresh_plan(self, *_):
        try:
            self._plan = plan_basemap(self._current_bbox(),
                                      self._provider.currentData())
        except BasemapError as exc:
            self._plan = None
            self._preview.setText(f"⚠ {exc}")
        else:
            p = self._plan
            self._preview.setText(
                f"Will fetch {p.tile_count} tile(s) at zoom {p.zoom} → "
                f"{p.out_w}×{p.out_h} px map.  {p.provider.attribution}")
        ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setEnabled(self._plan is not None)

    # ------------------------------------------------------------------ #
    # fetch                                                              #
    # ------------------------------------------------------------------ #

    def _start_fetch(self):
        if self._plan is None or self._worker is not None:
            return
        self._set_busy(True)
        self._status.setText("Contacting tile server…")
        self._worker = _FetchWorker(self._plan, self._out_path, parent=self)
        self._worker.progress.connect(
            lambda done, total: self._status.setText(f"Fetching tile {done} / {total}…"))
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _set_busy(self, busy: bool):
        for w in (self._provider, self._lon_min, self._lon_max,
                  self._lat_min, self._lat_max, self._fit_btn):
            w.setEnabled(not busy)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not busy)
        if busy:
            self.setCursor(Qt.CursorShape.BusyCursor)
        else:
            self.unsetCursor()

    def _on_done(self, path: str):
        self.result_path = Path(path)
        self.result_bbox = self._plan.bbox
        self.result_attribution = self._plan.provider.attribution
        self._finish_worker()
        self.accept()

    def _on_failed(self, message: str):
        self._finish_worker()
        self._set_busy(False)
        self._status.setText(f"⚠ Fetch failed: {message}\nNothing was changed — "
                             "adjust the window or try again.")
        self._refresh_plan()

    def _finish_worker(self):
        if self._worker is not None:
            self._worker.wait()
            self._worker = None

    def reject(self):
        # Cancel mid-fetch: flag the worker (its next tile callback aborts the
        # build; a stuck request still times out on its own) and close.
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait(30_000)
            self._worker = None
        super().reject()
