"""
Hyperglyph Generator — single-glyph GUI wrapper around hyperglyph_lab's
procedural generator (hyperglyph_lab/hyperglyph_generator.py), so a
randomized multi-level "hyperglyph" can be previewed and dropped into the
live scene without leaving the app. For generating and rating many designs
at once, use the standalone hyperglyph_lab/ CLI/notebook instead — this
dialog is intentionally one-glyph-at-a-time and does not write any files
itself; Save/Save As on the main window covers that once a design is
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
fields for real, not just visually) before Save, then resume.
"""
from __future__ import annotations

import random

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QSpinBox, QVBoxLayout,
)

from glyphviz_core.glyph_recipe import generate_nodes
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
        root.addWidget(self._info_label)

        root.addWidget(QLabel("<b>Preview</b>"))
        self._mini_vp = Viewport()
        self._mini_vp.show_grid = False
        self._mini_vp.setMinimumHeight(280)
        self._mini_vp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self._mini_vp, stretch=1)

        footer = QHBoxLayout()
        footer.addStretch()
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
        recipe, meta = random_recipe(branch_levels, max_nodes, random.Random(seed),
                                      name="Hyperglyph")

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

        self._mini_vp.base_scale = self._main_win._viewport.base_scale
        self._mini_vp.set_nodes(nodes)

        seed_desc = "random seed" if randomize else "fixed seed (Randomize off)"
        self._info_label.setText(
            f"{len(nodes)} nodes &nbsp;|&nbsp; family={meta.get('geometry_family')} "
            f"&nbsp;|&nbsp; palette={meta.get('palette_scheme')} "
            f"&nbsp;|&nbsp; {seed_desc}: {seed}"
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
