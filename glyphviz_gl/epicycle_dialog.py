"""
Epitrochoid Generator — a designer for epicycle chains.

One row per arm, a live preview that keeps moving, and a readout that says what
the design actually IS rather than what it looks like. All the math lives in
``glyphviz_core.epicycles`` (Qt-free, and shared with
``examples/Fourier_Epicycles_Example``), so this file is only the controls.

WHAT IT WRITES
--------------
Node CSVs, not a recipe JSON — the Tree Designer hands the Glyph Composer a
template because a tree IS a recipe, but an epicycle chain's whole point is the
traced path, which only exists once the curve has been walked. So Save Scene
writes a complete, loadable folder: node CSV + tag CSV, plus the ch-map /
ch-tracks pair when Self-drawing trail is on. Save Design is the small
secondary convenience that lets you reopen a hand-tuned design HERE; it is
never needed to view or share a result.

THE THREE KNOBS PER ARM, and what each does to the curve
--------------------------------------------------------
* **Rate X** sets the harmonic, through the ladder
  ``h_k = h_{k-1} + (-1)^(k-1) * r_k``. The sign alternates because each level's
  ``rotate = (90, 90, 0)`` cancels the Torus base rotation and flips the frame's
  handedness — so the MAGNITUDES add, and (1, -1, 1, -1) climbs 1, 2, 3, 4.
* **Length** is that arm's amplitude, in world units. It is produced by the
  SCALE of the node one level up (a node's torus is the circle its child
  rides), which the builder telescopes for you.
* **Phase X** rotates the term's starting angle: same spectrum, different shape.

and the two that leave the plane:

* **Tilt** leans this arm's orbit out of the previous arm's plane, exactly (it
  is written as the parent's ``rotate_y``). Inclined orbits, like an orrery.
* **Tube / Rate Y / Phase Y** give the arm a SECOND circle riding the first,
  around the torus tube. In the spectrum it is a sideband generator: an arm at
  harmonic h with tube rate r contributes h, h-r and h+r in the plane and pure
  out-of-plane motion at r. This is the one that makes torus knots.

The preview always runs on ``translate_rate`` with the trail fully drawn, even
when Self-drawing is checked — so the pen visibly rides a curve computed
independently of it, which is the correctness check, on screen. Self-drawing
changes only what Save Scene writes.
"""
from __future__ import annotations

import json
import os
import random

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QSizePolicy, QSpinBox, QSplitter, QTableWidget, QVBoxLayout, QWidget,
)

from glyphviz_core.epicycles import (
    Arm, EpicycleDesign, MAX_ARMS, MIN_ARMS, PRESETS, build_nodes,
    closure_frames, describe, frame_count, preset, random_design, trace_path,
    write_scene, _slug,
)

from .viewport import Viewport

#: (label, Arm attribute, minimum, maximum, decimals, step, tooltip)
#:
#: The decimals are the design's authoring precision, not a display choice:
#: ``_design_from_ui`` reads these widgets back on every preview, so whatever
#: they cannot represent is not in the design. 4 places on the lengths is what
#: keeps a 12/7 square-wave term exact enough to round-trip; the presets are
#: rounded to match, so opening one and reading it straight back changes
#: nothing. (The Glyph Composer has the same hazard the other way round — its
#: 6-decimal spin box silently rounds the ANTz Topo Scale preset.)
ARM_COLUMNS = [
    ("Length", "length", 0.01, 1000.0, 4, 0.5,
     "This arm's radius, in world units — the term's amplitude.\n"
     "Produced by the scale of the node one level up: a node's torus IS\n"
     "the circle its child rides."),
    ("Rate X", "rate_x", -60.0, 60.0, 2, 1.0,
     "Orbit angle, degrees per frame. This is what sets the harmonic,\n"
     "through h_k = h_(k-1) + (-1)^(k-1) * r_k — the frame flips at every\n"
     "level, so the MAGNITUDES add. Whole numbers close in 360 frames."),
    ("Phase X", "phase_x", -360.0, 360.0, 1, 15.0,
     "Starting orbit angle. Changes the SHAPE of the figure without\n"
     "changing its spectrum at all."),
    ("Tube", "tube", 0.0, 1000.0, 4, 0.5,
     "Radius of a second circle this arm rides, around the torus tube —\n"
     "world units, 0 = a flat arm. With Rate Y it is a sideband generator:\n"
     "harmonic h becomes h, h-rateY and h+rateY, plus out-of-plane motion."),
    ("Rate Y", "rate_y", -60.0, 60.0, 2, 1.0,
     "Tube angle, degrees per frame. Does nothing while Tube is 0."),
    ("Phase Y", "phase_y", -360.0, 360.0, 1, 15.0,
     "Starting tube angle."),
    ("Tilt", "tilt", -180.0, 180.0, 1, 5.0,
     "Degrees this arm's orbit plane leans out of the previous arm's.\n"
     "Exact — it is written as the parent node's rotate_y."),
]


class EpitrochoidGeneratorDialog(QDialog):
    def __init__(self, main_win, parent=None):
        super().__init__(parent or main_win)
        self.setWindowTitle("Epitrochoid Generator")
        self.resize(1240, 780)
        self._main_win = main_win

        self._design = preset("Jeff's ANTz original")
        self._nodes: list = []
        self._path: list = []
        self._loading = False          # suppress change signals while repopulating
        # False until the first preview has framed the scene; after that the
        # camera is the user's and survives every rebuild (see _do_preview).
        self._camera_framed = False

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._do_preview)

        self._build_ui()
        self._load_design_into_ui(self._design)
        QTimer.singleShot(200, lambda: self._do_preview(reset_camera=True))

    # ------------------------------------------------------------------ #
    # UI                                                                   #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        header = QLabel(
            "A chain of nested Torus-topology parents <b>is</b> a Fourier "
            "series: each arm is one term, and the pen traces their sum. "
            "Rate X sets the harmonic, Length its amplitude, Phase X its "
            "starting angle — and Tilt or Tube take the figure out of the "
            "plane."
        )
        header.setWordWrap(True)
        root.addWidget(header)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_controls())
        split.addWidget(self._build_preview())
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([620, 620])
        root.addWidget(split, stretch=1)

        root.addLayout(self._build_footer())

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)

        # -- presets + randomize ------------------------------------------
        top = QGroupBox("Start from")
        top_form = QFormLayout(top)

        preset_row = QHBoxLayout()
        self._w_preset = QComboBox()
        self._w_preset.addItems(list(PRESETS))
        preset_row.addWidget(self._w_preset, stretch=1)
        apply_btn = QPushButton("Apply")
        apply_btn.setToolTip("Replace the arms below with this preset.")
        apply_btn.clicked.connect(self._apply_preset)
        preset_row.addWidget(apply_btn)
        top_form.addRow("Preset:", preset_row)

        rnd_row = QHBoxLayout()
        self._w_seed = QSpinBox()
        self._w_seed.setRange(0, 2 ** 31 - 1)
        self._w_seed.setValue(1)
        self._w_seed.setToolTip(
            "The design's identity: the same seed and arm count always\n"
            "regenerate the identical design."
        )
        rnd_row.addWidget(self._w_seed, stretch=1)
        self._w_allow_3d = QCheckBox("3-D")
        self._w_allow_3d.setChecked(True)
        self._w_allow_3d.setToolTip(
            "Let Randomize use Tilt and Tube. Unchecked keeps every design\n"
            "flat in the z = 0 plane."
        )
        rnd_row.addWidget(self._w_allow_3d)
        rnd_btn = QPushButton("Randomize")
        rnd_btn.setToolTip(
            "Draw a fresh seed and build a new design from it.\n"
            "Rates stay small whole numbers so the curve closes and reads\n"
            "as a figure; arm lengths decay, because a series whose later\n"
            "terms are as long as its first is noise, not a curve."
        )
        rnd_btn.clicked.connect(self._randomize)
        rnd_row.addWidget(rnd_btn)
        top_form.addRow("Seed:", rnd_row)
        col.addWidget(top)

        # -- the arms table ------------------------------------------------
        arms_box = QGroupBox("Arms")
        arms_col = QVBoxLayout(arms_box)

        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("Arms:"))
        self._w_arm_count = QSpinBox()
        self._w_arm_count.setRange(MIN_ARMS, MAX_ARMS)
        self._w_arm_count.setValue(len(self._design.arms))
        self._w_arm_count.setToolTip(
            "Terms in the series. Adding one appends an arm continuing the\n"
            "existing pattern; removing one drops the last."
        )
        self._w_arm_count.valueChanged.connect(self._on_arm_count)
        count_row.addWidget(self._w_arm_count)
        count_row.addStretch()
        arms_col.addLayout(count_row)

        self._table = QTableWidget(0, len(ARM_COLUMNS))
        self._table.setHorizontalHeaderLabels([c[0] for c in ARM_COLUMNS])
        self._table.verticalHeader().setDefaultSectionSize(self._ROW_H)
        hh = self._table.horizontalHeader()
        for i, spec in enumerate(ARM_COLUMNS):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            self._table.horizontalHeaderItem(i).setToolTip(spec[6])
        arms_col.addWidget(self._table)
        col.addWidget(arms_box)

        # -- scene options -------------------------------------------------
        opts = QGroupBox("Scene")
        form = QFormLayout(opts)

        self._w_pen = QDoubleSpinBox()
        self._w_pen.setRange(0.05, 50.0)
        self._w_pen.setDecimals(2)
        self._w_pen.setSingleStep(0.1)
        self._w_pen.setToolTip("World radius of the pen sphere at the end of the chain.")
        self._w_pen.valueChanged.connect(self._on_change)
        form.addRow("Pen size:", self._w_pen)

        self._w_rings = QCheckBox("Orbit rings")
        self._w_rings.setToolTip(
            "Draw each arm's circle as a torus glyph. Off draws them as\n"
            "wireframe instead — lighter, and easier to see the trail through."
        )
        self._w_rings.toggled.connect(self._on_change)
        self._w_arms_vis = QCheckBox("Linkage rods")
        self._w_arms_vis.setToolTip(
            "Draw the arms as type-7 Link nodes wearing Cylinder geometry —\n"
            "real rods stretched between consecutive ring centres."
        )
        self._w_arms_vis.toggled.connect(self._on_change)
        vis_row = QHBoxLayout()
        vis_row.addWidget(self._w_rings)
        vis_row.addWidget(self._w_arms_vis)
        vis_row.addStretch()
        form.addRow("Show:", vis_row)

        self._w_trail = QCheckBox("Trail")
        self._w_trail.setToolTip(
            "The traced curve: a transparent Plot-topology parent holding one\n"
            "Point bead per sampled frame. Plot draws its polyline through\n"
            "them in row order, so the polyline IS the curve."
        )
        self._w_trail.toggled.connect(self._on_change)
        self._w_trail_points = QSpinBox()
        self._w_trail_points.setRange(30, 1440)
        self._w_trail_points.setSingleStep(30)
        self._w_trail_points.setToolTip(
            "Beads along the curve. More is smoother and heavier; the count\n"
            "is capped by the frame count, since one bead per frame is as\n"
            "fine as the path is sampled."
        )
        self._w_trail_points.valueChanged.connect(self._on_change)
        trail_row = QHBoxLayout()
        trail_row.addWidget(self._w_trail)
        trail_row.addWidget(QLabel("points:"))
        trail_row.addWidget(self._w_trail_points, stretch=1)
        form.addRow("", trail_row)

        self._w_self_draw = QCheckBox("Self-drawing trail (Channels)")
        self._w_self_draw.setToolTip(
            "Save Scene then also writes a ch-map/ch-tracks pair: the arms are\n"
            "driven by Channels instead of translate_rate, and each bead's\n"
            "alpha steps on as the pen arrives, so the curve draws itself.\n"
            "Press Space in the main window to play it.\n\n"
            "The preview here always shows the rate-driven version with the\n"
            "trail fully drawn, whichever way this is set."
        )
        self._w_self_draw.toggled.connect(self._on_change)
        form.addRow("", self._w_self_draw)

        self._w_frames = QSpinBox()
        self._w_frames.setRange(0, 3600)
        self._w_frames.setSpecialValueText("auto (closure)")
        self._w_frames.setSingleStep(30)
        self._w_frames.setToolTip(
            "Frames the trail is sampled over. 'auto' uses the exact period\n"
            "after which every angle is back where it started — the curve then\n"
            "closes instead of stopping mid-stroke."
        )
        self._w_frames.valueChanged.connect(self._on_change)
        form.addRow("Frames:", self._w_frames)

        col.addWidget(opts)
        col.addStretch()
        return panel

    def _build_preview(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout()
        row.addWidget(QLabel("<b>Preview</b>"))
        row.addStretch()
        self._w_auto = QCheckBox("Auto")
        self._w_auto.setChecked(True)
        self._w_auto.setToolTip("Rebuild shortly after every edit.")
        row.addWidget(self._w_auto)
        now_btn = QPushButton("Preview Now")
        now_btn.clicked.connect(lambda: self._do_preview())
        row.addWidget(now_btn)
        reset_btn = QPushButton("Reset View")
        reset_btn.setToolTip("Re-frame the camera on the whole figure.")
        reset_btn.clicked.connect(lambda: self._do_preview(reset_camera=True))
        row.addWidget(reset_btn)
        col.addLayout(row)

        self._mini_vp = Viewport()
        self._mini_vp.show_grid = False
        self._mini_vp.setMinimumHeight(320)
        self._mini_vp.setSizePolicy(QSizePolicy.Policy.Expanding,
                                    QSizePolicy.Policy.Expanding)
        col.addWidget(self._mini_vp, stretch=1)

        self._readout = QLabel("—")
        self._readout.setWordWrap(True)
        self._readout.setTextFormat(Qt.TextFormat.RichText)
        self._readout.setMinimumHeight(84)
        self._readout.setAlignment(Qt.AlignmentFlag.AlignTop)
        col.addWidget(self._readout)
        return panel

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        load_btn = QPushButton("Load Design…")
        load_btn.setToolTip("Reopen a design .json saved from this dialog.")
        load_btn.clicked.connect(self._load_design_file)
        footer.addWidget(load_btn)
        save_design_btn = QPushButton("Save Design…")
        save_design_btn.setToolTip(
            "Write the parameters as .json so this design can be reopened and\n"
            "tuned here later. Not needed to view or share the result — that\n"
            "is what Save Scene's CSVs are."
        )
        save_design_btn.clicked.connect(self._save_design_file)
        footer.addWidget(save_design_btn)
        footer.addStretch()

        save_btn = QPushButton("Save Scene (CSV)…")
        save_btn.setToolTip(
            "Write a complete, loadable scene folder: node CSV + tag CSV, plus\n"
            "the ch-map/ch-tracks pair when Self-drawing is on.\n\n"
            "One folder per scene is required, not tidiness: GlyphViz\n"
            "auto-loads Channels only when exactly one ch-map and one\n"
            "ch-tracks file sit beside the node CSV."
        )
        save_btn.clicked.connect(self._save_scene)
        footer.addWidget(save_btn)

        insert_btn = QPushButton("Insert into Scene")
        insert_btn.setDefault(True)
        insert_btn.setToolTip(
            "Add this design to the scene already open, as new root nodes."
        )
        insert_btn.clicked.connect(self._insert_into_scene)
        footer.addWidget(insert_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        footer.addWidget(close_btn)
        return footer

    # ------------------------------------------------------------------ #
    # Design <-> widgets                                                   #
    # ------------------------------------------------------------------ #

    def _load_design_into_ui(self, design: EpicycleDesign):
        self._loading = True
        try:
            self._design = design
            self._w_arm_count.setValue(len(design.arms))
            self._rebuild_table(design.arms)
            self._w_pen.setValue(design.pen_size)
            self._w_rings.setChecked(design.show_rings)
            self._w_arms_vis.setChecked(design.show_arms)
            self._w_trail.setChecked(design.trail)
            self._w_trail_points.setValue(int(design.trail_points))
            self._w_self_draw.setChecked(design.self_drawing)
            self._w_frames.setValue(int(design.frames or 0))
        finally:
            self._loading = False

    _ROW_H = 28

    def _rebuild_table(self, arms):
        self._table.setRowCount(len(arms))
        # Grow and shrink with the arm count: a fixed height sized for MAX_ARMS
        # leaves a field of blank rows under a 2-arm design, and one sized for
        # MIN_ARMS makes a 8-arm design scroll.
        height = self._ROW_H * len(arms) + 34
        self._table.setFixedHeight(height)
        for r, arm in enumerate(arms):
            for c, (_label, attr, lo, hi, dec, step, tip) in enumerate(ARM_COLUMNS):
                w = self._table.cellWidget(r, c)
                if w is None:
                    w = QDoubleSpinBox()
                    w.setRange(lo, hi)
                    w.setDecimals(dec)
                    w.setSingleStep(step)
                    w.setToolTip(tip)
                    w.setKeyboardTracking(False)   # one signal per commit, not per digit
                    w.valueChanged.connect(self._on_change)
                    self._table.setCellWidget(r, c, w)
                w.blockSignals(True)
                w.setValue(float(getattr(arm, attr)))
                w.blockSignals(False)

    def _design_from_ui(self) -> EpicycleDesign:
        arms = []
        for r in range(self._table.rowCount()):
            kw = {}
            for c, (_l, attr, *_rest) in enumerate(ARM_COLUMNS):
                w = self._table.cellWidget(r, c)
                kw[attr] = float(w.value()) if w is not None else 0.0
            arms.append(Arm(**kw))
        return EpicycleDesign(
            name=self._design.name,
            arms=arms,
            pen_size=self._w_pen.value(),
            ring_ratio=self._design.ring_ratio,
            show_rings=self._w_rings.isChecked(),
            show_arms=self._w_arms_vis.isChecked(),
            arm_ratio=self._design.arm_ratio,
            trail=self._w_trail.isChecked(),
            trail_points=self._w_trail_points.value(),
            self_drawing=self._w_self_draw.isChecked(),
            bead_group=self._design.bead_group,
            frames=self._w_frames.value() or None,
        )

    # ------------------------------------------------------------------ #
    # Events                                                               #
    # ------------------------------------------------------------------ #

    def _on_change(self, *_):
        if self._loading:
            return
        if self._w_auto.isChecked():
            self._preview_timer.start(350)

    def _on_arm_count(self, n: int):
        if self._loading:
            return
        arms = list(self._design_from_ui().arms)
        while len(arms) > n:
            arms.pop()
        while len(arms) < n:
            # Continue the pattern rather than appending a default: a new arm
            # half the length of the last, spinning the other way, is the next
            # term of a series — a length-10 arm on the end of a decaying chain
            # would swamp everything before it.
            last = arms[-1]
            arms.append(Arm(length=max(0.05, last.length * 0.6),
                            rate_x=-last.rate_x if last.rate_x else 1.0))
        self._loading = True
        try:
            self._rebuild_table(arms)
        finally:
            self._loading = False
        self._on_change()

    def _apply_preset(self):
        design = preset(self._w_preset.currentText())
        self._load_design_into_ui(design)
        self._do_preview(reset_camera=True)

    def _randomize(self):
        seed = random.randrange(2 ** 31)
        self._w_seed.blockSignals(True)
        self._w_seed.setValue(seed)
        self._w_seed.blockSignals(False)
        design = random_design(random.Random(seed),
                               n_arms=self._w_arm_count.value(),
                               allow_3d=self._w_allow_3d.isChecked(),
                               name=f"Epitrochoid_{seed}")
        # Keep the scene-dressing choices the user has made; only the arms and
        # the pen are what Randomize is for.
        current = self._design_from_ui()
        design.show_rings = current.show_rings
        design.show_arms = current.show_arms
        design.trail = current.trail
        design.trail_points = current.trail_points
        design.self_drawing = current.self_drawing
        self._load_design_into_ui(design)
        self._do_preview(reset_camera=True)

    # ------------------------------------------------------------------ #
    # Preview                                                              #
    # ------------------------------------------------------------------ #

    def _do_preview(self, reset_camera: bool = False):
        """Rebuild and redraw, holding the camera where the user put it.

        Viewport.set_nodes() auto-frames, which is right on the first build and
        wrong on every keystroke afterwards — zooming into a cusp and being
        yanked back to an overview on the next edit makes close-up work
        impossible (the same fix the Glyph Composer's preview needed).
        """
        design = self._design_from_ui()
        design.name = self._design.name
        self._design = design

        frames = frame_count(design)
        try:
            self._path = trace_path(design, frames)
            # The preview is ALWAYS the rate-driven build: it moves on its own,
            # and its trail is fully drawn, so the pen can be seen riding a
            # curve that was computed independently of it.
            self._nodes = build_nodes(replace_self_drawing(design, False),
                                      include_world=False, path=self._path)
        except Exception as exc:                      # pragma: no cover - guard
            self._readout.setText(f"<span style='color:#e57'>{exc}</span>")
            return

        keep = self._camera_framed and not reset_camera
        state = self._mini_vp.camera_state() if keep else None
        self._mini_vp.base_scale = self._main_win._viewport.base_scale
        self._mini_vp.set_nodes(self._nodes)
        if state is not None:
            self._mini_vp.restore_camera_state(state)
        else:
            self._camera_framed = True

        self._update_readout(design, frames)

    def _update_readout(self, design: EpicycleDesign, frames: int):
        info = describe(design, path=self._path, frames=frames)
        ladder = " → ".join(f"{h:g}" for h in info["harmonics"])
        spec = ", ".join(f"{h:g}<span style='opacity:.6'>×{a:.2f}</span>"
                         for h, a in info["spectrum"][:8])
        closes = info["closes"]
        close_txt = (f"closes in <b>{closes}</b> frames"
                     if closes else
                     f"<span style='color:#e9a'>does not close within "
                     f"3600 frames</span> — sampled over {frames}")
        shape = ("planar (z = 0)" if info["planar"]
                 else f"3-D, {info['z_extent']:.1f} units deep")
        self._readout.setText(
            f"<b>Harmonic ladder</b> {ladder} &nbsp;|&nbsp; {close_txt}<br>"
            f"<b>Spectrum</b> {spec or '—'}<br>"
            f"<b>Figure</b> {shape}, half-span {info['half_span']:.1f} "
            f"&nbsp;|&nbsp; {len(self._nodes)} nodes"
        )

    # ------------------------------------------------------------------ #
    # Output                                                              #
    # ------------------------------------------------------------------ #

    def _save_scene(self):
        design = self._design_from_ui()
        folder = QFileDialog.getExistingDirectory(
            self, "Choose a folder for the scene (a subfolder will be created)")
        if not folder:
            return
        stem = _slug(design.name or "epitrochoid")
        out_dir = os.path.join(folder, stem)
        if os.path.isdir(out_dir) and os.listdir(out_dir):
            btn = QMessageBox.question(
                self, "Folder exists",
                f"{out_dir}\n\nalready exists. Overwrite the scene files in it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            if btn != QMessageBox.StandardButton.Yes:
                return
        try:
            paths = write_scene(design, out_dir, stem)
        except OSError as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return
        kinds = ", ".join(sorted(paths))
        self._main_win.statusBar().showMessage(
            f"Epitrochoid Generator: wrote {kinds} to {out_dir} — "
            f"open {os.path.basename(paths['node'])} there, or drop the folder "
            f"on the window"
        )

    def _save_design_file(self):
        design = self._design_from_ui()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Epitrochoid Design",
            f"{_slug(design.name or 'epitrochoid')}_design.json",
            "Epitrochoid Design (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(design.to_dict(), fh, indent=2)
        except OSError as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return
        self._main_win.statusBar().showMessage(
            f"Epitrochoid Generator: saved design to {path}")

    def _load_design_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Epitrochoid Design", "", "Epitrochoid Design (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                design = EpicycleDesign.from_dict(json.load(fh))
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Load failed", str(exc))
            return
        self._load_design_into_ui(design)
        self._do_preview(reset_camera=True)

    def _insert_into_scene(self):
        mw = self._main_win
        design = self._design_from_ui()
        start_id = max((n.id for n in mw.nodes), default=0) + 1
        # Roots, deliberately: the hub and the trail parent are two independent
        # roots, and the trail's beads are Cartesian world positions that only
        # mean anything at the top level.
        nodes = build_nodes(design, start_id=start_id, parent_id=0,
                            include_world=False, path=self._path or None)
        if not nodes:
            return
        for node in nodes:
            mw._add_node_to_scene(node, select_new=False)
        mw._table.select_by_id(nodes[0].id)
        mw.statusBar().showMessage(
            f"Epitrochoid Generator: inserted {len(nodes)} nodes "
            f"(ids {nodes[0].id}-{nodes[-1].id})"
        )


def replace_self_drawing(design: EpicycleDesign, value: bool) -> EpicycleDesign:
    """A copy with self_drawing forced — the preview needs the rate-driven
    build even when the saved scene will be Channels-driven."""
    from dataclasses import replace
    return replace(design, self_drawing=value)
