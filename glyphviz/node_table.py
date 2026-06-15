from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QItemSelection,
    QItemSelectionModel, QSortFilterProxyModel,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from .node import Node

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
    ("Sx",      "scale_x"),
    ("Sy",      "scale_y"),
    ("Sz",      "scale_z"),
    ("Ratio",   "ratio"),
    ("Color",   None),
]

_FLOAT_ATTRS = frozenset({"translate_x", "translate_y", "translate_z",
                           "rotate_x", "rotate_y", "rotate_z",
                           "scale_x", "scale_y", "scale_z", "ratio"})
_COLOR_COL = len(_COLUMNS) - 1


class NodeTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._nodes: list[Node] = []

    def set_nodes(self, nodes: list[Node]):
        self.beginResetModel()
        self._nodes = list(nodes)
        self.endResetModel()

    def append_node(self, node: Node):
        row = len(self._nodes)
        self.beginInsertRows(QModelIndex(), row, row)
        self._nodes.append(node)
        self.endInsertRows()

    def node_at(self, row: int) -> Node:
        return self._nodes[row]

    def rowCount(self, parent=QModelIndex()):
        return len(self._nodes)

    def columnCount(self, parent=QModelIndex()):
        return len(_COLUMNS)

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
            return f"{val:.3f}" if attr in _FLOAT_ATTRS else str(val)
        if role == Qt.ItemDataRole.UserRole:
            return val
        return None


class NodeTableView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = NodeTableModel()
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.setModel(self._proxy)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
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

        self.setMinimumHeight(140)

    def set_nodes(self, nodes: list[Node]):
        self._model.set_nodes(nodes)
        self.horizontalHeader().resizeSections(QHeaderView.ResizeMode.ResizeToContents)

    def append_node(self, node: Node):
        self._model.append_node(node)

    # --- selection helpers ---

    def selected_node(self) -> Node | None:
        """Return the first (or only) selected node, or None."""
        rows = self.selectionModel().selectedRows()
        if not rows:
            return None
        src = self._proxy.mapToSource(rows[0])
        return self._model.node_at(src.row())

    def selected_nodes(self) -> list[Node]:
        """Return all currently selected nodes (order matches table display order)."""
        rows = self.selectionModel().selectedRows()
        result = []
        for idx in rows:
            src = self._proxy.mapToSource(idx)
            result.append(self._model.node_at(src.row()))
        return result

    def select_by_id(self, node_id: int):
        """Replace the selection with exactly this one node and scroll to it."""
        for row in range(self._model.rowCount()):
            if self._model.node_at(row).id == node_id:
                src_idx = self._model.index(row, 0)
                proxy_idx = self._proxy.mapFromSource(src_idx)
                self.selectionModel().select(
                    proxy_idx,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
                self.scrollTo(proxy_idx)
                return

    def select_toggle_id(self, node_id: int):
        """Toggle one node into/out of the current selection (Ctrl+click semantics)."""
        for row in range(self._model.rowCount()):
            if self._model.node_at(row).id == node_id:
                src_idx = self._model.index(row, 0)
                proxy_idx = self._proxy.mapFromSource(src_idx)
                self.selectionModel().select(
                    proxy_idx,
                    QItemSelectionModel.SelectionFlag.Toggle
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
                self.scrollTo(proxy_idx)
                return

    def select_by_ids(self, node_ids: set[int]):
        """Replace the selection with the given set of node IDs (one signal fired)."""
        selection = QItemSelection()
        for row in range(self._model.rowCount()):
            if self._model.node_at(row).id in node_ids:
                src_idx = self._model.index(row, 0)
                proxy_idx = self._proxy.mapFromSource(src_idx)
                selection.select(proxy_idx, proxy_idx)
        self.selectionModel().select(
            selection,
            QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows,
        )
        if not selection.isEmpty():
            self.scrollTo(selection.indexes()[0])

    def refresh_node(self, node_id: int):
        """Notify the model that a node's data has changed in-place."""
        for row in range(self._model.rowCount()):
            if self._model.node_at(row).id == node_id:
                tl = self._model.index(row, 0)
                br = self._model.index(row, self._model.columnCount() - 1)
                self._model.dataChanged.emit(tl, br)
                return
