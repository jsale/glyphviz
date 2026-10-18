"""
Hyperglyph Generator — single-glyph GUI wrapper around hyperglyph_lab's
procedural generator (hyperglyph_lab/hyperglyph_generator.py), so a
randomized multi-level "hyperglyph" can be previewed and dropped into the
live scene without leaving the app. For generating and rating many designs
at once, use the standalone hyperglyph_lab/ CLI/notebook instead — this
dialog is intentionally one-glyph-at-a-time. The one file it writes is a
recipe .json (Save Recipe), the same format Tools > Glyph Composer loads —
so a design worth keeping can be reopened there and edited level by level.
Node CSVs still come from Save/Save As on the main window once a design is
inserted, same as any other node.

Randomize off = fully deterministic, not a separate non-random code path —
the same tuned uniform() ranges just start from the Seed field's value
instead of a fresh one, so Seed/Max Nodes/Branch Levels together determine
the result (same inputs -> same design, always). While Randomize is checked
each Regenerate draws a fresh seed and displays it in the Seed field;
unchecking afterward locks in that exact seed for further tweaking.

Idle Motion (rotate_rate) is the same optional per-level counter-rotating
spin hyperglyph_lab applies; the static (unanimated) recipe underneath is
already a complete design on its own — see View > Pause Rate Animation [P]
in the main window to freeze a live hyperglyph in place (zeroing its rate
fields for real, not just visually) before Save, then resume. A recipe has
no rate fields at all, so a saved one is always static: what "Capture live
orientation" preserves is the POSE the preview had reached when you clicked
Save, not the motion itself.
"""
from __future__ import annotations

import random

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QSizePolicy, QSpinBox, QVBoxLayout,
)

from glyphviz_core.glyph_recipe import (
    COMPOSER_EDIT_NODE_WARN, generate_nodes, recipe_node_count, save_recipe,
    snapshot_level_rotations,
)
from hyperglyph_lab.hyperglyph_generator import (
    random_recipe, apply_idle_motion, assign_color_index, DETERMINISTIC_SEED,
)

from .viewport import Viewport


class HyperglyphGeneratorDialog(QDialog):
    def __init__(self, main_win, parent=None):
        super().__init__(parent or main_win)
        self.setWindowTitle("Hyperglyph Generator")
        self.resize(640, 660)
        self._main_win = main_win

        self._recipe = None
        self._rng_seed: int | None = None
        # Captured at the moment of the last Regenerate — Insert into Scene
        # uses THIS, not the live checkbox, so what got previewed is exactly
        # what gets inserted even if Idle Motion is toggled afterward without
        # clicking Regenerate again.
        self._idle_motion_applied: bool = False

        # Regeneration only ever happens on an explicit Regenerate click —
        # not on dialog open, not on any param change. It used to auto-reroll
        # on every checkbox/spinbox edit (and even on open), which made
        # "Randomize" impossible to inspect before committing to a design and
        # produced a hyperglyph that was already mid-animation before the
        # user had done anything.
        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI                                                                    #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        header = QLabel(
            "One randomized multi-level hyperglyph at a time. For batches of "
            "many designs with ratings/mutation, use hyperglyph_lab/ instead."
        )
        header.setWordWrap(True)
        root.addWidget(header)

        params_box = QGroupBox("Parameters")
        form = QFormLayout(params_box)

        self._w_max_nodes = QSpinBox()
        self._w_max_nodes.setRange(2, 20000)
        self._w_max_nodes.setSingleStep(50)
        self._w_max_nodes.setValue(500)
        self._w_max_nodes.setToolTip("Upper bound on total node count (a cap, not a target).")
        form.addRow("Max Nodes:", self._w_max_nodes)

        self._w_branch_levels = QSpinBox()
        self._w_branch_levels.setRange(1, 10)
        self._w_branch_levels.setValue(5)
        self._w_branch_levels.setToolTip("Number of branch levels, including the trunk (root).")
        form.addRow("Branch Levels:", self._w_branch_levels)

        self._w_randomize = QCheckBox("Randomize")
        self._w_randomize.setChecked(True)
        self._w_randomize.setToolTip(
            "Checked: every Regenerate draws a new random seed (shown below).\n"
            "Unchecked: Regenerate reuses the Seed field's value exactly —\n"
            "the same Seed/Max Nodes/Branch Levels always regenerate the\n"
            "identical design. Uncheck right after a Randomize result you like\n"
            "to lock in that exact seed for further tweaking."
        )
        self._w_randomize.toggled.connect(self._on_randomize_toggled)
        form.addRow("", self._w_randomize)

        self._w_seed = QSpinBox()
        self._w_seed.setRange(0, 2 ** 31 - 1)
        self._w_seed.setValue(DETERMINISTIC_SEED)
        self._w_seed.setEnabled(False)   # Randomize starts checked -> seed field unused until unchecked
        self._w_seed.setToolTip(
            "Only used when Randomize is unchecked. While Randomize is checked,\n"
            "each Regenerate draws a new seed and displays it here."
        )
        form.addRow("Seed:", self._w_seed)

        self._w_idle_motion = QCheckBox("Idle Motion (rotate_rate)")
        self._w_idle_motion.setChecked(True)
        self._w_idle_motion.setToolTip(
            "Gentle counter-rotating spin per branch level, evolving the\n"
            "hyperglyph through new orientations continuously. The static\n"
            "design underneath is already complete without it.\n"
            "View > Pause Rate Animation [P] freezes it in place for a Save."
        )
        form.addRow("", self._w_idle_motion)

        root.addWidget(params_box)

        regen_row = QHBoxLayout()
        regen_btn = QPushButton("Regenerate")
        regen_btn.clicked.connect(self._regenerate)
        regen_row.addWidget(regen_btn)
        regen_row.addStretch()
        root.addLayout(regen_row)

        self._info_label = QLabel("No hyperglyph generated yet — click Regenerate.")
        self._info_label.setWordWrap(True)
        # The readout is built with &nbsp; separators. Qt only auto-detects
        # rich text from a tag, and the common readout has none, so without
        # this the entities showed literally ("389 nodes &nbsp;|&nbsp; ...").
        self._info_label.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self._info_label)

        root.addWidget(QLabel("<b>Preview</b>"))
        self._mini_vp = Viewport()
        self._mini_vp.show_grid = False
        self._mini_vp.setMinimumHeight(280)
        self._mini_vp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self._mini_vp, stretch=1)

        footer = QHBoxLayout()
        # Left of the buttons, because it modifies what Save Recipe writes
        # rather than how the design is generated.
        self._w_capture_live = QCheckBox("Capture live orientation")
        self._w_capture_live.setChecked(True)
        self._w_capture_live.setToolTip(
            "Save the pose the preview has spun into, instead of the\n"
            "orientation the design was generated with.\n\n"
            "A recipe holds one rotation per LEVEL while Idle Motion gives\n"
            "every node its own axis and speed, so siblings drift apart: the\n"
            "trunk is captured exactly, and each deeper level takes its first\n"
            "node's current orientation as the representative.\n\n"
            "No effect when Idle Motion is off — nothing has moved."
        )
        footer.addWidget(self._w_capture_live)
        footer.addStretch()

        self._save_btn = QPushButton("Save Recipe…")
        self._save_btn.setEnabled(False)
        self._save_btn.setToolTip(
            "Write this design as a Glyph Template .json — the format\n"
            "Tools > Glyph Composer opens, for editing it level by level."
        )
        self._save_btn.clicked.connect(self._save_recipe_json)
        footer.addWidget(self._save_btn)

        self._insert_btn = QPushButton("Insert into Scene")
        self._insert_btn.setDefault(True)
        self._insert_btn.setEnabled(False)
        self._insert_btn.clicked.connect(self._insert_into_scene)
        footer.addWidget(self._insert_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    # ------------------------------------------------------------------ #
    # Generation — only ever called from the Regenerate button            #
    # ------------------------------------------------------------------ #

    def _on_randomize_toggled(self, checked: bool):
        # Purely a UI-state update (which field is live), not a regeneration
        # — toggling Randomize must not itself reroll the design.
        self._w_seed.setEnabled(not checked)

    def _regenerate(self):
        branch_levels = self._w_branch_levels.value()
        max_nodes = self._w_max_nodes.value()
        randomize = self._w_randomize.isChecked()

        if randomize:
            seed = random.randrange(2 ** 31)
            self._w_seed.blockSignals(True)
            self._w_seed.setValue(seed)
            self._w_seed.blockSignals(False)
        else:
            seed = self._w_seed.value()
        # The seed IS the design's identity (same seed + Max Nodes + Branch
        # Levels always regenerates it), so it goes in the name — that is what
        # a saved recipe carries into the Composer's Name field, and what the
        # default filename is built from.
        recipe, meta = random_recipe(branch_levels, max_nodes, random.Random(seed),
                                      name=f"Hyperglyph_{seed}")

        # Recipe placement is deterministic given its LevelSpecs (no
        # DIST_RANDOM is ever chosen by random_recipe), so re-running
        # generate_nodes() later with a different start_id/parent_id for
        # Insert into Scene reproduces this exact same structure — what you
        # see in the preview is what gets inserted.
        nodes = generate_nodes(recipe, start_id=1)
        assign_color_index(nodes)
        self._idle_motion_applied = self._w_idle_motion.isChecked()
        if self._idle_motion_applied:
            apply_idle_motion(nodes, random.Random(seed))

        self._recipe = recipe
        self._rng_seed = seed
        self._insert_btn.setEnabled(True)
        self._save_btn.setEnabled(True)

        self._mini_vp.base_scale = self._main_win._viewport.base_scale
        self._mini_vp.set_nodes(nodes)

        seed_desc = "random seed" if randomize else "fixed seed (Randomize off)"
        info = (
            f"{len(nodes)} nodes &nbsp;|&nbsp; family={meta.get('geometry_family')} "
            f"&nbsp;|&nbsp; palette={meta.get('palette_scheme')} "
            f"&nbsp;|&nbsp; {seed_desc}: {seed}"
        )
        # Said up front, not only in the Save dialog — a design this large is
        # worth knowing about while there is still a cheap Regenerate away.
        if len(nodes) > COMPOSER_EDIT_NODE_WARN:
            info += (
                f"<br><i>Over {COMPOSER_EDIT_NODE_WARN:,} nodes — fine here and "
                f"in the scene, but heavy to edit in the Glyph Composer.</i>"
            )
        self._info_label.setText(info)

    # ------------------------------------------------------------------ #
    # Save recipe (Glyph Composer .json)                                   #
    # ------------------------------------------------------------------ #

    def _recipe_to_save(self):
        """The recipe Save Recipe would write right now: the design as
        generated, or — while Capture live orientation is checked — the same
        design re-posed to where the preview has spun to.

        Reads the PREVIEW's node objects, which are the ones the viewport has
        been integrating rotate_rate into every frame, so the pose is the one
        on screen at the instant of the click. Harmless with Idle Motion off:
        nothing has moved, so the capture returns the authored values
        unchanged (see snapshot_level_rotations)."""
        if self._recipe is None:
            return None
        if not self._w_capture_live.isChecked():
            return self._recipe
        return snapshot_level_rotations(self._recipe, self._mini_vp.nodes)

    def _confirm_large_recipe(self, recipe) -> bool:
        """Warn — once, and only when it applies — that a big hyperglyph is an
        awkward thing to hand the Composer. The .json is tiny either way; what
        gets heavy is the Composer's Auto Preview, which regenerates the whole
        tree 350 ms after every keystroke. Returns False if the user backs out."""
        n = recipe_node_count(recipe)
        if n <= COMPOSER_EDIT_NODE_WARN:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Large hyperglyph")
        box.setText(f"This design expands to about {n:,} nodes.")
        box.setInformativeText(
            "The recipe file itself stays small, and the glyph renders fine in "
            "the scene — but the Glyph Composer rebuilds the entire tree after "
            "every edit, so it will feel sluggish above a few thousand nodes.\n\n"
            "In the Composer, turn off Auto Preview and use Preview Now, or "
            "lower the per-level Count values, to keep editing responsive."
        )
        box.setStandardButtons(QMessageBox.StandardButton.Save
                               | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        return box.exec() == QMessageBox.StandardButton.Save

    def _save_recipe_json(self):
        recipe = self._recipe_to_save()
        if recipe is None:
            return
        if not self._confirm_large_recipe(recipe):
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Glyph Recipe", recipe.name + ".json",
            "Glyph Template (*.json)"
        )
        if not path:
            return
        try:
            save_recipe(recipe, path)
        except OSError as e:
            QMessageBox.warning(self, "Save failed", str(e))
            return

        posed = " (live orientation)" if self._w_capture_live.isChecked() else ""
        self._main_win.statusBar().showMessage(
            f"Hyperglyph Generator: saved recipe{posed} to {path} — "
            f"open it with Tools > Glyph Composer > Load Template"
        )

    # ------------------------------------------------------------------ #
    # Insert into scene                                                    #
    # ------------------------------------------------------------------ #

    def _insert_into_scene(self):
        if self._recipe is None:
            return

        mw = self._main_win
        sel = mw._selected_nodes
        parent_id = sel[0].id if sel else 0
        base_branch = sel[0].branch_level + 1 if sel else 0
        start_id = max((n.id for n in mw.nodes), default=0) + 1

        nodes = generate_nodes(self._recipe, start_id=start_id,
                                parent_id=parent_id, base_branch_level=base_branch)
        if not nodes:
            return
        assign_color_index(nodes)
        if self._idle_motion_applied:
            apply_idle_motion(nodes, random.Random(self._rng_seed))

        for node in nodes:
            mw._add_node_to_scene(node, select_new=False)

        mw._table.select_by_id(nodes[0].id)
        mw.statusBar().showMessage(
            f"Hyperglyph Generator: inserted {len(nodes)} nodes "
            f"(parent={parent_id}, ids {nodes[0].id}-{nodes[-1].id})"
        )
