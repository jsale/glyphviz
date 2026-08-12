from operator import attrgetter

from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QItemSelection, QItemSelectionModel,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from glyphviz_core.node import Node

# (header label, Node attribute or None for special columns)
_COLUMNS = [
    ("ID",      "id"),
    ("Type",    "type"),
    ("Parent",  "parent_id"),
    ("Level",   "branch_level"),
    ("Geo",     "geometry"),
    ("Topo",    "topo"),
    ("Hide",    "hide"),
    ("Texture", "texture_id"),
    ("X",       "translate_x"),
    ("Y",       "translate_y"),
    ("Z",       "translate_z"),
    ("Rx",      "rotate_x"),
    ("Ry",      "rotate_y"),
    ("Rz",      "rotate_z"),
    ("RotMode", "rotation_mode"),
    ("Sx",      "scale_x"),
    ("Sy",      "scale_y"),
    ("Sz",      "scale_z"),
    ("Ratio",   "ratio"),
    ("TopoScl", "topo_scale"),
    ("Color",   None),
]

_FLOAT_ATTRS = frozenset({"translate_x", "translate_y", "translate_z",
                           "rotate_x", "rotate_y", "rotate_z",
                           "scale_x", "scale_y", "scale_z", "ratio"})
# Float columns shown at significant-figure rather than fixed-decimal
# precision (see the DisplayRole branch below).
_SIGFIG_ATTRS = frozenset({"topo_scale"})
_COLOR_COL = len(_COLUMNS) - 1


def _merge_runs(sorted_rows):
    """Yield (start, end) inclusive runs of consecutive ints from a sorted list."""
    start = prev = None
    for r in sorted_rows:
        if start is None:
            start = prev = r
        elif r == prev + 1:
            prev = r
        else:
            yield start, prev
            start = prev = r
    if start is not None:
        yield start, prev


class NodeTableModel(QAbstractTableModel):
    """Flat table over the scene's node list, sorted in-place by sort().

    There is deliberately no QSortFilterProxyModel in front of this model:
    the proxy sorts by calling data() once per comparison from C++ into
    Python (~10 s for 100k rows), and every selection round-trip through
    mapTo/FromSource degrades to per-row work. Sorting the underlying list
    with a key function instead is O(n) key extractions (~0.2 s at 100k),
    and view rows equal model rows everywhere else.
    """

    def __init__(self):
        super().__init__()
        self._nodes: list[Node] = []
        self._row_by_id: dict[int, int] = {}

    def _rebuild_row_map(self):
        self._row_by_id = {n.id: row for row, n in enumerate(self._nodes)}

    def set_nodes(self, nodes: list[Node]):
        self.beginResetModel()
        self._nodes = list(nodes)
        self._rebuild_row_map()
        self.endResetModel()

    def append_node(self, node: Node):
        row = len(self._nodes)
        self.beginInsertRows(QModelIndex(), row, row)
        self._nodes.append(node)
        self._row_by_id[node.id] = row
        self.endInsertRows()

    def node_at(self, row: int) -> Node:
        return self._nodes[row]

    def row_of_id(self, node_id: int) -> int | None:
        return self._row_by_id.get(node_id)

    def rowCount(self, parent=QModelIndex()):
        return len(self._nodes)

    def columnCount(self, parent=QModelIndex()):
        return len(_COLUMNS)

    def sort(self, column: int, order=Qt.SortOrder.AscendingOrder):
        """Key-based sort of the node list. Called by QTableView on header
        clicks (sortingEnabled) and by NodeTableView.set_nodes to re-apply
        the current indicator after a model reset. Persistent indexes
        (selection ranges, current index) are remapped so the selection
        follows the nodes, not the row numbers."""
        if column < 0 or column >= len(_COLUMNS) or not self._nodes:
            return
        attr = _COLUMNS[column][1]
        if column == _COLOR_COL:
            # Mirrors the packed-RGB value data() serves for UserRole.
            def key_of(n: Node) -> int:
                return n.color_r << 16 | n.color_g << 8 | n.color_b
        else:
            key_of = attrgetter(attr)
        reverse = order == Qt.SortOrder.DescendingOrder

        # (PySide6 exposes layoutAboutToBeChanged/layoutChanged as zero-arg
        # signals — the C++ VerticalSortHint overload isn't emittable here.)
        self.layoutAboutToBeChanged.emit()
        old_nodes = self._nodes
        perm = sorted(range(len(old_nodes)),
                      key=lambda i: key_of(old_nodes[i]), reverse=reverse)
        self._nodes = [old_nodes[i] for i in perm]
        self._rebuild_row_map()
        old_persist = self.persistentIndexList()
        if old_persist:
            new_row_of_old = [0] * len(perm)
            for new_row, old_row in enumerate(perm):
                new_row_of_old[old_row] = new_row
            self.changePersistentIndexList(
                old_persist,
                [self.index(new_row_of_old[ix.row()], ix.column())
                 for ix in old_persist],
            )
        self.layoutChanged.emit()

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section][0]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        node = self._nodes[index.row()]
        col = index.column()
        attr = _COLUMNS[col][1]

        if col == _COLOR_COL:
            if role == Qt.ItemDataRole.DecorationRole:
                return QColor(node.color_r, node.color_g, node.color_b, node.color_a)
            if role == Qt.ItemDataRole.DisplayRole:
                return f"#{node.color_r:02X}{node.color_g:02X}{node.color_b:02X}"
            if role == Qt.ItemDataRole.UserRole:
                return node.color_r << 16 | node.color_g << 8 | node.color_b
            return None

        val = getattr(node, attr)
        if role == Qt.ItemDataRole.DisplayRole:
            if attr in _SIGFIG_ATTRS:
                # A multiplier spanning decades: 3 dp would render the ANTz
                # topo_scale (1/180) as a flat "0.006".
                return f"{val:g}"
            return f"{val:.3f}" if attr in _FLOAT_ATTRS else str(val)
        if role == Qt.ItemDataRole.UserRole:
            return val
        return None


class NodeTableView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = NodeTableModel()
        self.setModel(self._model)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # Header clicks call NodeTableModel.sort() directly (no proxy).
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)

        vh = self.verticalHeader()
        vh.setVisible(False)
        vh.setDefaultSectionSize(20)

        hh = self.horizontalHeader()
        hh.setStretchLastSection(True)
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setDefaultSectionSize(56)
        # Auto-width from a sample of rows; the default (1000) makes
        # resizeSections cost ~0.5 s on a 100k-row load for no visible gain.
        hh.setResizeContentsPrecision(200)

        self.setMinimumHeight(140)

    def set_nodes(self, nodes: list[Node]):
        self._model.set_nodes(nodes)
        hh = self.horizontalHeader()
        # A model reset drops the sorted order but keeps the header indicator;
        # re-apply it so the view keeps showing what the indicator claims.
        if self.isSortingEnabled() and hh.sortIndicatorSection() >= 0:
            self._model.sort(hh.sortIndicatorSection(), hh.sortIndicatorOrder())
        hh.resizeSections(QHeaderView.ResizeMode.ResizeToContents)

    def append_node(self, node: Node):
        self._model.append_node(node)

    # --- selection helpers ---
    #
    # All bulk selection work stays range-based: reading the selection
    # per-index (selectedRows/selectedIndexes) materializes a QModelIndex
    # per selected CELL — minutes of PySide object churn at 100k rows —
    # while the range list is a handful of objects for typical selections.

    def _selected_rows(self) -> list[int]:
        """Sorted, deduped rows of the current selection."""
        rows: set[int] = set()
        for rng in self.selectionModel().selection():
            rows.update(range(rng.top(), rng.bottom() + 1))
        return sorted(rows)

    def selected_node(self) -> Node | None:
        """Return the first (topmost) selected node, or None."""
        sel = self.selectionModel().selection()
        if sel.isEmpty():
            return None
        return self._model.node_at(min(rng.top() for rng in sel))

    def selected_nodes(self) -> list[Node]:
        """Return all currently selected nodes (order matches table display order)."""
        return [self._model.node_at(r) for r in self._selected_rows()]

    def select_by_id(self, node_id: int):
        """Replace the selection with exactly this one node and scroll to it."""
        row = self._model.row_of_id(node_id)
        if row is None:
            return
        idx = self._model.index(row, 0)
        self.selectionModel().select(
            idx,
            QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows,
        )
        self.scrollTo(idx)

    def select_toggle_id(self, node_id: int):
        """Toggle one node into/out of the current selection (Ctrl+click semantics)."""
        row = self._model.row_of_id(node_id)
        if row is None:
            return
        idx = self._model.index(row, 0)
        self.selectionModel().select(
            idx,
            QItemSelectionModel.SelectionFlag.Toggle
            | QItemSelectionModel.SelectionFlag.Rows,
        )
        self.scrollTo(idx)

    def select_by_ids(self, node_ids: set[int]):
        """Replace the selection with the given set of node IDs (one signal fired)."""
        rows = sorted(
            row for nid in node_ids
            if (row := self._model.row_of_id(nid)) is not None
        )
        last_col = self._model.columnCount() - 1
        selection = QItemSelection()
        for start, end in _merge_runs(rows):
            selection.select(self._model.index(start, 0),
                             self._model.index(end, last_col))
        self.selectionModel().select(
            selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        if rows:
            self.scrollTo(self._model.index(rows[0], 0))

    def select_add_ids(self, node_ids: set[int]):
        """Add the given node IDs to the current selection without clearing it
        (cumulative Select-By / Ctrl+rubber-band semantics)."""
        rows = sorted(
            row for nid in node_ids
            if (row := self._model.row_of_id(nid)) is not None
        )
        if not rows:
            return
        last_col = self._model.columnCount() - 1
        selection = QItemSelection()
        for start, end in _merge_runs(rows):
            selection.select(self._model.index(start, 0),
                             self._model.index(end, last_col))
        self.selectionModel().select(
            selection, QItemSelectionModel.SelectionFlag.Select)
        self.scrollTo(self._model.index(rows[0], 0))

    def refresh_node(self, node_id: int):
        """Notify the model that a node's data has changed in-place."""
        row = self._model.row_of_id(node_id)
        if row is None:
            return
        self._model.dataChanged.emit(
            self._model.index(row, 0),
            self._model.index(row, self._model.columnCount() - 1),
        )

    def refresh_nodes(self, node_ids):
        """Batched refresh_node: one dataChanged per contiguous row run.
        Bulk edits (gizmo drags, inspector changes on a large selection)
        must not emit one signal per node — at 100k that alone is seconds."""
        rows = sorted(
            row for nid in node_ids
            if (row := self._model.row_of_id(nid)) is not None
        )
        if not rows:
            return
        runs = list(_merge_runs(rows))
        if len(runs) > 64:
            # One spanning emission beats thousands of tiny ones; the view
            # only repaints the visible region either way.
            runs = [(rows[0], rows[-1])]
        last_col = self._model.columnCount() - 1
        for start, end in runs:
            self._model.dataChanged.emit(
                self._model.index(start, 0),
                self._model.index(end, last_col),
            )
