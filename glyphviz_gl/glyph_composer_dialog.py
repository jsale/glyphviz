"""
Glyph Composer — interactive dialog for building hierarchical glyph templates.

Layout:
  Left  : QListWidget of branch levels + Add/Remove buttons
  Right : scrollable parameter form for the selected level
  Bottom: mini Viewport for live preview
  Footer: template name, Save/Load, Auto-preview, Insert into Scene, Close

Bug-fix notes:
  Optional dist-mode widgets (_w_tilt, _w_step, etc.) only exist for certain
  level types. They are reset to None at the top of every form rebuild so that
  _save_params can safely check ``is not None`` rather than ``hasattr``.
  Using hasattr on a stale reference to a destroyed QWidget raises RuntimeError
  in PySide6 and silently kills the preview / insert pipeline.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from glyphviz_core.geometry_data import GEO_NAMES, GEO_SPHERE
from glyphviz_core.glyph_recipe import (
    DIST_ANGULAR, DIST_CIRCULAR, DIST_GRID, DIST_LINEAR, DIST_RANDOM,
    DIST_LABELS, ROOT_DIST_MODES, NONROOT_DIST_MODES,
    GlyphRecipe, LevelSpec,
    default_recipe, generate_nodes, load_recipe, save_recipe,
)
from glyphviz_core.topology import TOPO_NAMES, TOPO_SPHERE, TOPO_NONE

from .viewport import Viewport


_GEO_ITEMS  = [(gid, name) for gid, name in sorted(GEO_NAMES.items()) if gid != 23]
_TOPO_ITEMS = sorted(TOPO_NAMES.items())


def _color_btn_style(r, g, b, a=255):
    return (
        f"background-color: rgba({r},{g},{b},{a}); "
        "border: 1px solid #555; border-radius: 3px; min-width: 60px;"
    )


class GlyphComposerDialog(QDialog):
    def __init__(self, main_win, parent=None):
        super().__init__(parent or main_win)
        self.setWindowTitle("Glyph Composer")
        self.resize(900, 700)
        self._main_win = main_win

        self._recipe: GlyphRecipe = default_recipe()
        self._current_level: int | None = None
        self._loading = False
        self._scale_locked = False   # persists across level switches

        # Optional dist-mode widgets — may or may not exist for a given level.
        # ALWAYS reset to None at the top of _build_param_form before rebuilding,
        # so _save_params / signal-wiring can safely test ``is not None`` and
        # never accidentally call methods on a destroyed PySide6 widget.
        self._w_tilt   = None   # Angular: translate_y tilt / latitude
        self._w_tz     = None   # Angular: translate_z altitude offset
        self._w_step   = None   # Linear: step size
        self._w_axis   = None   # Linear: axis combo (X/Y/Z)
        self._w_radius = None   # Circular: radius
        self._w_gcols  = None   # Grid: columns
        self._w_gsx    = None   # Grid: spacing X
        self._w_gsy    = None   # Grid: spacing Y
        self._w_bounds = None   # Random: bounding half-size

        # Always-present form widgets (set in _build_param_form)
        self._w_count  = None
        self._w_geo    = None
        self._w_topo   = None
        self._w_ratio  = None
        self._w_dist_mode = None
        self._w_sx = self._w_sy = self._w_sz = None
        self._w_rx = self._w_ry = self._w_rz = None
        self._w_lock_scale     = None
        self._w_color_start_btn = None
        self._w_color_end_btn   = None
        self._w_gradient_cb     = None

        self._color_start = [180, 100, 200, 255]
        self._color_end   = [80,  200, 180, 255]

        self._dist_panels: dict[str, QWidget] = {}

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._do_preview)

        self._build_ui()
        self._refresh_level_list()
        self._level_list.setCurrentRow(0)
        QTimer.singleShot(250, self._do_preview)

    # ------------------------------------------------------------------ #
    # UI skeleton                                                          #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # Top splitter: level list | param form
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left — level list
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel("<b>Branch Levels</b>"))
        self._level_list = QListWidget()
        self._level_list.setMaximumWidth(180)
        self._level_list.currentRowChanged.connect(self._on_level_row_changed)
        lv.addWidget(self._level_list)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add Level")
        add_btn.clicked.connect(self._add_level)
        rm_btn  = QPushButton("− Remove")
        rm_btn.clicked.connect(self._remove_level)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rm_btn)
        lv.addLayout(btn_row)

        # Right — scrollable param form
        self._param_scroll = QScrollArea()
        self._param_scroll.setWidgetResizable(True)
        self._param_scroll.setMinimumWidth(440)

        splitter.addWidget(left)
        splitter.addWidget(self._param_scroll)
        splitter.setSizes([180, 500])
        root.addWidget(splitter, stretch=3)

        # Mini viewport
        root.addWidget(QLabel("<b>Preview</b>"))
        self._mini_vp = Viewport()
        self._mini_vp.show_grid = False
        self._mini_vp.setMinimumHeight(240)
        self._mini_vp.setMaximumHeight(300)
        self._mini_vp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        root.addWidget(self._mini_vp, stretch=0)

        # Footer
        footer = QHBoxLayout()
        footer.addWidget(QLabel("Template name:"))
        self._name_edit = QLineEdit(self._recipe.name)
        self._name_edit.setMaximumWidth(180)
        self._name_edit.textChanged.connect(self._on_name_changed)
        footer.addWidget(self._name_edit)

        save_tpl = QPushButton("Save Template…")
        save_tpl.clicked.connect(self._save_template)
        footer.addWidget(save_tpl)

        load_tpl = QPushButton("Load Template…")
        load_tpl.clicked.connect(self._load_template)
        footer.addWidget(load_tpl)

        footer.addStretch()

        self._auto_preview_cb = QCheckBox("Auto-preview")
        self._auto_preview_cb.setChecked(True)
        footer.addWidget(self._auto_preview_cb)

        preview_btn = QPushButton("Preview Now")
        preview_btn.clicked.connect(self._do_preview)
        footer.addWidget(preview_btn)

        insert_btn = QPushButton("Insert into Scene")
        insert_btn.setDefault(True)
        insert_btn.clicked.connect(self._insert_into_scene)
        footer.addWidget(insert_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        footer.addWidget(close_btn)

        root.addLayout(footer)

    # ------------------------------------------------------------------ #
    # Level list                                                           #
    # ------------------------------------------------------------------ #

    def _level_label(self, idx: int) -> str:
        spec = self._recipe.levels[idx]
        geo  = GEO_NAMES.get(spec.geometry, str(spec.geometry))
        prefix = "Root" if idx == 0 else f"Level {idx}"
        return f"{prefix}  ×{spec.count}  {geo}"

    def _refresh_level_list(self):
        self._level_list.blockSignals(True)
        row = self._level_list.currentRow()
        self._level_list.clear()
        for i in range(len(self._recipe.levels)):
            self._level_list.addItem(QListWidgetItem(self._level_label(i)))
        self._level_list.blockSignals(False)
        if row < self._level_list.count():
            self._level_list.setCurrentRow(row)

    def _on_level_row_changed(self, row: int):
        if row < 0 or row >= len(self._recipe.levels):
            return
        if self._current_level is not None and not self._loading:
            self._save_params()
        self._build_param_form(row)

    def _add_level(self):
        if self._current_level is not None and not self._loading:
            self._save_params()
        idx = len(self._recipe.levels)
        spec = LevelSpec(
            count=6, geometry=GEO_SPHERE, topo=TOPO_NONE,
            dist_mode=DIST_LINEAR if idx == 0 else DIST_ANGULAR,
            scale_x=0.4, scale_y=0.4, scale_z=0.4,
            color_start=(100, 200, 160, 255),
            color_end=(200, 100, 160, 255),
        )
        self._recipe.levels.append(spec)
        self._level_list.addItem(QListWidgetItem(self._level_label(idx)))
        self._level_list.setCurrentRow(idx)

    def _remove_level(self):
        if len(self._recipe.levels) <= 1:
            return
        row = self._level_list.currentRow()
        if row < 0:
            return
        self._recipe.levels.pop(row)
        self._current_level = None
        self._refresh_level_list()
        new_row = min(row, len(self._recipe.levels) - 1)
        self._level_list.setCurrentRow(new_row)
        self._schedule_preview()

    # ------------------------------------------------------------------ #
    # Parameter form                                                       #
    # ------------------------------------------------------------------ #

    def _build_param_form(self, level_idx: int):
        self._loading = True

        # Reset ALL optional widget refs to None before rebuilding.
        # Without this, refs from a previous level survive as stale pointers to
        # destroyed Qt objects; calling .value() on them raises RuntimeError.
        self._w_tilt = self._w_tz = None
        self._w_step = self._w_axis = None
        self._w_radius = None
        self._w_gcols = self._w_gsx = self._w_gsy = None
        self._w_bounds = None
        self._dist_panels = {}

        self._current_level = level_idx
        spec    = self._recipe.levels[level_idx]
        is_root = (level_idx == 0)

        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(6)

        role = "Root placement" if is_root else f"Level {level_idx} — children of Level {level_idx-1}"
        vbox.addWidget(QLabel(f"<b>{role}</b>"))

        # ── Basic params ──────────────────────────────────────────────
        basic = QFormLayout()
        basic.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._w_count = QSpinBox()
        self._w_count.setRange(1, 200)
        self._w_count.setValue(spec.count)
        basic.addRow("Count:", self._w_count)

        self._w_geo = QComboBox()
        for gid, gname in _GEO_ITEMS:
            self._w_geo.addItem(gname, gid)
        self._w_geo.setCurrentIndex(self._w_geo.findData(spec.geometry))
        basic.addRow("Geometry:", self._w_geo)

        self._w_topo = QComboBox()
        for tid, tname in _TOPO_ITEMS:
            self._w_topo.addItem(tname, tid)
        self._w_topo.setCurrentIndex(self._w_topo.findData(spec.topo))
        self._w_topo.setToolTip("Topology of THIS node — determines how its children are placed.")
        basic.addRow("Topology\n(child layout):", self._w_topo)

        self._w_ratio = QDoubleSpinBox()
        self._w_ratio.setRange(0.01, 2.0)
        self._w_ratio.setSingleStep(0.05)
        self._w_ratio.setDecimals(3)
        self._w_ratio.setValue(spec.ratio)
        self._w_ratio.setToolTip("Torus tube ratio / other topology-specific size.")
        basic.addRow("Ratio:", self._w_ratio)

        vbox.addLayout(basic)

        # ── Placement ─────────────────────────────────────────────────
        place_box = QGroupBox("Placement")
        place_vbox = QVBoxLayout(place_box)

        modes   = ROOT_DIST_MODES if is_root else NONROOT_DIST_MODES
        cur_mode = spec.dist_mode if spec.dist_mode in modes else modes[0]

        self._w_dist_mode = QComboBox()
        for m in modes:
            self._w_dist_mode.addItem(DIST_LABELS[m], m)
        self._w_dist_mode.setCurrentIndex(self._w_dist_mode.findData(cur_mode))
        place_vbox.addWidget(self._w_dist_mode)

        def _dbl_sb(lo, hi, step, val, dec=2, tip=""):
            w = QDoubleSpinBox()
            w.setRange(lo, hi); w.setSingleStep(step); w.setDecimals(dec); w.setValue(val)
            if tip:
                w.setToolTip(tip)
            return w

        # Build a panel widget for each applicable distribution mode
        if DIST_ANGULAR in modes:
            p = self._dist_panels[DIST_ANGULAR] = QWidget()
            f = QFormLayout(p)
            self._w_tilt = _dbl_sb(-360, 360, 5,   spec.dist_tilt, tip="translate_y of children: latitude/tilt depending on parent topology")
            self._w_tz   = _dbl_sb(-100, 100, 0.1, spec.dist_tz,   tip="translate_z of children: altitude/radius offset")
            f.addRow("Tilt / Latitude Y:", self._w_tilt)
            f.addRow("Altitude Offset Z:", self._w_tz)
            place_vbox.addWidget(p)

        if DIST_LINEAR in modes:
            p = self._dist_panels[DIST_LINEAR] = QWidget()
            f = QFormLayout(p)
            self._w_step = _dbl_sb(0.01, 500, 0.5, spec.dist_step)
            self._w_axis = QComboBox()
            for a in ["X", "Y", "Z"]:
                self._w_axis.addItem(a)
            self._w_axis.setCurrentIndex(spec.dist_axis)
            f.addRow("Step:", self._w_step)
            f.addRow("Axis:", self._w_axis)
            place_vbox.addWidget(p)

        if DIST_CIRCULAR in modes:
            p = self._dist_panels[DIST_CIRCULAR] = QWidget()
            f = QFormLayout(p)
            self._w_radius = _dbl_sb(0.01, 500, 0.5, spec.dist_radius)
            f.addRow("Radius:", self._w_radius)
            place_vbox.addWidget(p)

        if DIST_GRID in modes:
            p = self._dist_panels[DIST_GRID] = QWidget()
            f = QFormLayout(p)
            self._w_gcols = QSpinBox(); self._w_gcols.setRange(1, 50); self._w_gcols.setValue(spec.dist_grid_cols)
            self._w_gsx   = _dbl_sb(0.01, 500, 0.5, spec.dist_grid_sx)
            self._w_gsy   = _dbl_sb(0.01, 500, 0.5, spec.dist_grid_sy)
            f.addRow("Columns:", self._w_gcols)
            f.addRow("Spacing X:", self._w_gsx)
            f.addRow("Spacing Y:", self._w_gsy)
            place_vbox.addWidget(p)

        if DIST_RANDOM in modes:
            p = self._dist_panels[DIST_RANDOM] = QWidget()
            f = QFormLayout(p)
            self._w_bounds = _dbl_sb(0.1, 1000, 1.0, spec.dist_bounds)
            f.addRow("Bounds (±):", self._w_bounds)
            place_vbox.addWidget(p)

        self._update_dist_panel(cur_mode)
        vbox.addWidget(place_box)

        # ── Transform ─────────────────────────────────────────────────
        xform_box = QGroupBox("Transform")
        xf = QFormLayout(xform_box)

        self._w_sx = _dbl_sb(0.001, 100, 0.1,  spec.scale_x)
        self._w_sy = _dbl_sb(0.001, 100, 0.1,  spec.scale_y)
        self._w_sz = _dbl_sb(0.001, 100, 0.1,  spec.scale_z)
        self._w_rx = _dbl_sb(-360,  360, 5.0,  spec.rotate_x, dec=1)
        self._w_ry = _dbl_sb(-360,  360, 5.0,  spec.rotate_y, dec=1)
        self._w_rz = _dbl_sb(-360,  360, 5.0,  spec.rotate_z, dec=1)

        self._w_lock_scale = QCheckBox("Lock X/Y/Z")
        self._w_lock_scale.setChecked(self._scale_locked)
        self._w_lock_scale.setToolTip("Keep X, Y, Z scale equal.")

        xf.addRow("Scale X:", self._w_sx)
        xf.addRow("Scale Y:", self._w_sy)
        xf.addRow("Scale Z:", self._w_sz)
        xf.addRow("", self._w_lock_scale)
        xf.addRow("Rotate X:", self._w_rx)
        xf.addRow("Rotate Y:", self._w_ry)
        xf.addRow("Rotate Z:", self._w_rz)
        vbox.addWidget(xform_box)

        # ── Color ─────────────────────────────────────────────────────
        color_box = QGroupBox("Color")
        cf = QFormLayout(color_box)

        self._color_start = list(spec.color_start)
        has_grad = spec.color_end is not None
        self._color_end   = list(spec.color_end) if has_grad else [80, 200, 180, 255]

        self._w_color_start_btn = QPushButton()
        self._w_color_start_btn.setStyleSheet(_color_btn_style(*self._color_start))
        self._w_color_start_btn.clicked.connect(self._pick_start_color)
        cf.addRow("Color:", self._w_color_start_btn)

        self._w_gradient_cb = QCheckBox("Enable gradient")
        self._w_gradient_cb.setChecked(has_grad)
        cf.addRow("", self._w_gradient_cb)

        self._w_color_end_btn = QPushButton()
        self._w_color_end_btn.setStyleSheet(_color_btn_style(*self._color_end))
        self._w_color_end_btn.setEnabled(has_grad)
        self._w_color_end_btn.clicked.connect(self._pick_end_color)
        cf.addRow("Gradient to:", self._w_color_end_btn)

        vbox.addWidget(color_box)
        vbox.addStretch()

        # ── Connect signals ────────────────────────────────────────────
        self._w_dist_mode.currentIndexChanged.connect(self._on_dist_mode_changed)

        # Basic params
        for w in [self._w_count, self._w_geo, self._w_topo, self._w_ratio]:
            if isinstance(w, QComboBox):
                w.currentIndexChanged.connect(self._on_any_change)
            else:
                w.valueChanged.connect(self._on_any_change)

        # Scale — route through lock handler
        self._w_sx.valueChanged.connect(lambda v, _s=self._w_sx: self._on_scale_changed(v, _s))
        self._w_sy.valueChanged.connect(lambda v, _s=self._w_sy: self._on_scale_changed(v, _s))
        self._w_sz.valueChanged.connect(lambda v, _s=self._w_sz: self._on_scale_changed(v, _s))
        self._w_lock_scale.toggled.connect(self._on_lock_toggled)

        # Rotate
        for w in [self._w_rx, self._w_ry, self._w_rz]:
            w.valueChanged.connect(self._on_any_change)

        # Optional dist widgets — safe because all are None-checked above
        for w in [self._w_tilt, self._w_tz, self._w_step,
                  self._w_radius, self._w_gcols, self._w_gsx, self._w_gsy, self._w_bounds]:
            if w is not None:
                if isinstance(w, QComboBox):
                    w.currentIndexChanged.connect(self._on_any_change)
                else:
                    w.valueChanged.connect(self._on_any_change)

        if self._w_axis is not None:
            self._w_axis.currentIndexChanged.connect(self._on_any_change)

        # Color
        self._w_gradient_cb.toggled.connect(self._on_gradient_toggled)

        self._param_scroll.setWidget(container)
        self._loading = False

    def _update_dist_panel(self, mode: str):
        for m, p in self._dist_panels.items():
            p.setVisible(m == mode)

    def _on_dist_mode_changed(self, _idx):
        if self._w_dist_mode is None:
            return
        mode = self._w_dist_mode.currentData()
        if mode:
            self._update_dist_panel(mode)
        self._on_any_change()

    # ------------------------------------------------------------------ #
    # Save / read params                                                   #
    # ------------------------------------------------------------------ #

    def _save_params(self):
        idx = self._current_level
        if idx is None or idx >= len(self._recipe.levels):
            return
        spec    = self._recipe.levels[idx]
        is_root = (idx == 0)
        modes   = ROOT_DIST_MODES if is_root else NONROOT_DIST_MODES

        spec.count    = self._w_count.value()
        spec.geometry = self._w_geo.currentData()
        spec.topo     = self._w_topo.currentData()
        spec.ratio    = self._w_ratio.value()
        spec.dist_mode = self._w_dist_mode.currentData() or modes[0]

        # Optional widgets — all reset to None at form-rebuild time,
        # so these checks never access a stale destroyed Qt object.
        if self._w_tilt   is not None:  spec.dist_tilt      = self._w_tilt.value()
        if self._w_tz     is not None:  spec.dist_tz        = self._w_tz.value()
        if self._w_step   is not None:  spec.dist_step       = self._w_step.value()
        if self._w_axis   is not None:  spec.dist_axis       = self._w_axis.currentIndex()
        if self._w_radius is not None:  spec.dist_radius     = self._w_radius.value()
        if self._w_gcols  is not None:  spec.dist_grid_cols  = self._w_gcols.value()
        if self._w_gsx    is not None:  spec.dist_grid_sx    = self._w_gsx.value()
        if self._w_gsy    is not None:  spec.dist_grid_sy    = self._w_gsy.value()
        if self._w_bounds is not None:  spec.dist_bounds     = self._w_bounds.value()

        spec.scale_x  = self._w_sx.value()
        spec.scale_y  = self._w_sy.value()
        spec.scale_z  = self._w_sz.value()
        spec.rotate_x = self._w_rx.value()
        spec.rotate_y = self._w_ry.value()
        spec.rotate_z = self._w_rz.value()

        spec.color_start = tuple(self._color_start)
        spec.color_end   = tuple(self._color_end) if self._w_gradient_cb.isChecked() else None

        item = self._level_list.item(idx)
        if item:
            item.setText(self._level_label(idx))

    # ------------------------------------------------------------------ #
    # Scale lock                                                           #
    # ------------------------------------------------------------------ #

    def _on_lock_toggled(self, checked: bool):
        self._scale_locked = checked

    def _on_scale_changed(self, val: float, source):
        if (not self._loading and self._scale_locked
                and self._w_sx is not None and self._w_sy is not None and self._w_sz is not None):
            for w in [self._w_sx, self._w_sy, self._w_sz]:
                if w is not source:
                    w.blockSignals(True)
                    w.setValue(val)
                    w.blockSignals(False)
        self._on_any_change()

    # ------------------------------------------------------------------ #
    # Color pickers                                                        #
    # ------------------------------------------------------------------ #

    def _pick_start_color(self):
        r, g, b, a = self._color_start
        c = QColorDialog.getColor(QColor(r, g, b, a), self, "Start Color",
                                  QColorDialog.ShowAlphaChannel)
        if c.isValid():
            self._color_start = [c.red(), c.green(), c.blue(), c.alpha()]
            self._w_color_start_btn.setStyleSheet(_color_btn_style(*self._color_start))
            self._on_any_change()

    def _pick_end_color(self):
        r, g, b, a = self._color_end
        c = QColorDialog.getColor(QColor(r, g, b, a), self, "Gradient End Color",
                                  QColorDialog.ShowAlphaChannel)
        if c.isValid():
            self._color_end = [c.red(), c.green(), c.blue(), c.alpha()]
            self._w_color_end_btn.setStyleSheet(_color_btn_style(*self._color_end))
            self._on_any_change()

    def _on_gradient_toggled(self, checked: bool):
        if self._w_color_end_btn is not None:
            self._w_color_end_btn.setEnabled(checked)
        self._on_any_change()

    # ------------------------------------------------------------------ #
    # Change handling / preview                                            #
    # ------------------------------------------------------------------ #

    def _on_name_changed(self, text: str):
        self._recipe.name = text

    def _on_any_change(self, *_):
        if self._loading:
            return
        self._schedule_preview()

    def _schedule_preview(self):
        if self._auto_preview_cb.isChecked():
            self._preview_timer.start(350)

    def _do_preview(self):
        try:
            self._save_params()
        except Exception:
            pass   # never let a save error kill the preview loop
        nodes = generate_nodes(self._recipe, start_id=1)
        self._mini_vp.base_scale = self._main_win._viewport.base_scale
        self._mini_vp.set_nodes(nodes)

    # ------------------------------------------------------------------ #
    # Template I/O                                                         #
    # ------------------------------------------------------------------ #

    def _save_template(self):
        self._save_params()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Glyph Template", self._recipe.name + ".json",
            "Glyph Template (*.json)"
        )
        if path:
            save_recipe(self._recipe, path)

    def _load_template(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Glyph Template", "", "Glyph Template (*.json)"
        )
        if not path:
            return
        try:
            recipe = load_recipe(path)
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Load failed", str(e))
            return
        self._recipe = recipe
        self._current_level = None
        self._name_edit.setText(recipe.name)
        self._refresh_level_list()
        self._level_list.setCurrentRow(0)
        self._do_preview()

    # ------------------------------------------------------------------ #
    # Insert into scene                                                    #
    # ------------------------------------------------------------------ #

    def _insert_into_scene(self):
        self._save_params()

        mw  = self._main_win
        sel = mw._selected_nodes
        parent_id    = sel[0].id           if sel else 0
        base_branch  = sel[0].branch_level + 1 if sel else 0
        start_id     = max((n.id for n in mw.nodes), default=0) + 1

        nodes = generate_nodes(self._recipe,
                               start_id=start_id,
                               parent_id=parent_id,
                               base_branch_level=base_branch)
        if not nodes:
            return

        for node in nodes:
            mw._add_node_to_scene(node, select_new=False)

        mw._table.select_by_id(nodes[0].id)
        mw.statusBar().showMessage(
            f"Glyph Composer: inserted {len(nodes)} nodes "
            f"(parent={parent_id}, ids {nodes[0].id}–{nodes[-1].id})"
        )
