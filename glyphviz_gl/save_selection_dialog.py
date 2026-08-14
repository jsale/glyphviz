"""Save Selection As… — the options dialog in front of the export.

Collects the three choices glyphviz_core.selection_export offers and shows,
live, exactly which rows each combination would write. The preview runs
plan_selection (set walks over the node list, no copying) rather than the
full build, so toggling an option stays instant on a large scene.

The dialog decides nothing else: MainWindow owns the file chooser and the
actual write, the same division basemap_dialog uses.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QGroupBox, QLabel, QRadioButton,
    QVBoxLayout,
)

from glyphviz_core.selection_export import (
    DETACH_ANCESTORS, DETACH_BAKE, DETACH_RAW, ExportOptions, plan_selection,
)


class SaveSelectionDialog(QDialog):
    """Modal options dialog. On accept, `options` holds the chosen
    ExportOptions and `plan` the SelectionPlan they produce."""

    def __init__(self, scene, selected_ids, parent=None, has_channels: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Save Selection")
        self._scene = scene
        self._selected_ids = set(selected_ids)
        self._has_channels = has_channels
        self.options = ExportOptions()
        self.plan = None

        self._build_ui()
        self._refresh_preview()

    @property
    def include_channels(self) -> bool:
        """Whether to write ch-map/ch-tracks companions alongside the node
        CSV. Handled by MainWindow, not by the core export: it is a file
        operation on the open scene's companions, not a node-list decision."""
        return self._has_channels and self._channels.isChecked()

    def _build_ui(self):
        root = QVBoxLayout(self)

        self._descendants = QCheckBox("Include each selected node's descendants")
        self._descendants.setChecked(True)
        self._descendants.setToolTip(
            "Selecting a node brings its whole subtree, the way Copy and\n"
            "Delete already do. Turn this off to write only the highlighted\n"
            "rows.")
        self._descendants.toggled.connect(self._refresh_preview)
        root.addWidget(self._descendants)

        detach_grp = QGroupBox("When a selected node's parent is not included")
        detach_lay = QVBoxLayout(detach_grp)
        self._bake = QRadioButton("Keep it where it is (bake world placement)")
        self._bake.setToolTip(
            "Fold the missing parents' placement into the node itself, so the\n"
            "saved fragment reopens exactly where, and at the size and angle,\n"
            "it appeared here. Its own children are unaffected.")
        self._ancestors = QRadioButton("Save its parent nodes too")
        self._ancestors.setToolTip(
            "Write the ancestor chain as well, so the hierarchy is intact.\n"
            "Perfectly faithful, but the file then holds glyphs you did not\n"
            "select.")
        self._raw = QRadioButton("Keep its authored values (template export)")
        self._raw.setToolTip(
            "Leave translate/rotate/scale exactly as authored. The fragment\n"
            "lands near the origin in its old parent's local coordinates —\n"
            "what you want when reusing a glyph as a template, not when\n"
            "saving a region of a scene.")
        self._bake.setChecked(True)
        for rb in (self._bake, self._ancestors, self._raw):
            rb.toggled.connect(self._refresh_preview)
            detach_lay.addWidget(rb)
        root.addWidget(detach_grp)

        self._world = QCheckBox("Include scene settings (background, fog, tag colors)")
        self._world.setChecked(True)
        self._world.setToolTip(
            "Carries the World row, which holds the scene-wide look. Without\n"
            "it the fragment reopens on the default background.")
        self._world.toggled.connect(self._refresh_preview)
        root.addWidget(self._world)

        self._channels = QCheckBox("Include channel animation for these nodes")
        self._channels.setChecked(self._has_channels)
        self._channels.setEnabled(self._has_channels)
        self._channels.setToolTip(
            "Write ch-map/ch-tracks companions holding only the channels the\n"
            "exported nodes are bound to."
            if self._has_channels else
            "This scene has no channel animation loaded.")
        root.addWidget(self._channels)

        self._preview = QLabel()
        self._preview.setWordWrap(True)
        root.addWidget(self._preview)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save…")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        root.addWidget(self._buttons)

    def current_options(self) -> ExportOptions:
        if self._ancestors.isChecked():
            detach = DETACH_ANCESTORS
        elif self._raw.isChecked():
            detach = DETACH_RAW
        else:
            detach = DETACH_BAKE
        return ExportOptions(
            include_descendants=self._descendants.isChecked(),
            detach=detach,
            include_world_row=self._world.isChecked(),
        )

    def _refresh_preview(self, *_):
        self.options = self.current_options()
        self.plan = plan_selection(self._scene, self._selected_ids, self.options)
        self._preview.setText(describe_plan(self.plan, len(self._selected_ids)))
        ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setEnabled(self.plan.count > 0)


def describe_plan(plan, selected_count: int) -> str:
    """One-paragraph summary of what a plan will write. Shared with
    MainWindow's post-save status line so the dialog's promise and the
    result are phrased the same way."""
    if plan.count == 0:
        return "Nothing to save — select one or more glyphs first."
    parts = [f"{plan.count} row(s) from {selected_count} selected"]
    if plan.descendants_added:
        parts.append(f"+{plan.descendants_added} descendant(s)")
    if plan.ancestors_added:
        parts.append(f"+{plan.ancestors_added} parent(s)")
    if plan.links_added:
        parts.append(f"+{plan.links_added} link(s)")
    if plan.world_row:
        parts.append("+ scene settings")
    text = ", ".join(parts) + "."
    if plan.detached_ids:
        text += f"  {len(plan.detached_ids)} node(s) will be re-rooted."
    if plan.dropped_links:
        text += (f"  {plan.dropped_links} link(s) dropped — the node at the"
                 " other end is not in the selection.")
    return text
