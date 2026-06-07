from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .csv_reader import load_node_csv
from .geometry import GEO_NAMES, GEO_COUNT
from .node import Node, NON_VISUAL_TYPES
from .node_table import NodeTableView
from .topology import TOPO_NAMES, TOPO_COUNT
from .viewport import Viewport


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GlyphViz")
        self.resize(1280, 800)
        self.nodes: list[Node] = []

        self._build_viewport()
        self._build_menu()
        self._build_panel()
        self._build_table()
        self._build_statusbar()

    def _build_viewport(self):
        self._viewport = Viewport(self)
        self._viewport.nodeClicked.connect(self._on_viewport_pick)
        self.setCentralWidget(self._viewport)

    def _build_menu(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        open_act = file_menu.addAction("&Open Node CSV…")
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._open_csv)
        file_menu.addSeparator()
        file_menu.addAction("&Quit").triggered.connect(self.close)

        view_menu = mb.addMenu("&View")

        self._axes_act = view_menu.addAction("Show &Axes")
        self._axes_act.setCheckable(True)
        self._axes_act.setChecked(True)
        self._axes_act.triggered.connect(lambda c: self._set_axes(c))

        self._grid_act = view_menu.addAction("Show &Grid")
        self._grid_act.setCheckable(True)
        self._grid_act.setChecked(True)
        self._grid_act.triggered.connect(lambda c: self._set_grid(c))

        self._hidden_act = view_menu.addAction("Show &Hidden Nodes")
        self._hidden_act.setCheckable(True)
        self._hidden_act.setChecked(False)
        self._hidden_act.triggered.connect(lambda c: self._set_hidden(c))

        view_menu.addSeparator()
        view_menu.addAction("Reset &Camera").triggered.connect(self._reset_camera)

    def _build_panel(self):
        dock = QDockWidget("Properties", self)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        dock.setMinimumWidth(200)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(8)

        # --- Display group ---
        disp = QGroupBox("Display")
        disp_layout = QVBoxLayout(disp)

        self._cb_axes = QCheckBox("Show Axes")
        self._cb_axes.setChecked(True)
        self._cb_axes.toggled.connect(self._set_axes)

        self._cb_grid = QCheckBox("Show Grid")
        self._cb_grid.setChecked(True)
        self._cb_grid.toggled.connect(self._set_grid)

        self._cb_hidden = QCheckBox("Show Hidden Nodes")
        self._cb_hidden.setChecked(False)
        self._cb_hidden.toggled.connect(self._set_hidden)

        disp_layout.addWidget(self._cb_axes)
        disp_layout.addWidget(self._cb_grid)
        disp_layout.addWidget(self._cb_hidden)

        # --- Scale group ---
        scale_grp = QGroupBox("Global Scale")
        scale_layout = QVBoxLayout(scale_grp)
        self._scale_label = QLabel("Scale: 3.0")
        self._scale_slider = QSlider(Qt.Orientation.Horizontal)
        self._scale_slider.setRange(1, 100)
        self._scale_slider.setValue(30)
        self._scale_slider.setTickInterval(10)
        self._scale_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._scale_slider.valueChanged.connect(self._update_scale)
        scale_layout.addWidget(self._scale_label)
        scale_layout.addWidget(self._scale_slider)

        # --- Stats group ---
        stats_grp = QGroupBox("Scene Info")
        stats_layout = QVBoxLayout(stats_grp)
        self._lbl_total = QLabel("Nodes: —")
        self._lbl_visible = QLabel("Visible: —")
        self._lbl_file = QLabel("File: —")
        self._lbl_file.setWordWrap(True)
        stats_layout.addWidget(self._lbl_file)
        stats_layout.addWidget(self._lbl_total)
        stats_layout.addWidget(self._lbl_visible)

        # --- Selected Node inspector ---
        self._insp_grp = QGroupBox("Selected Node")
        self._insp_grp.setEnabled(False)
        insp_layout = QFormLayout(self._insp_grp)
        insp_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self._insp_id     = QLabel("—")
        self._insp_type   = QLabel("—")
        self._insp_parent = QLabel("—")

        pos_widget = QWidget()
        pos_layout = QHBoxLayout(pos_widget)
        pos_layout.setContentsMargins(0, 0, 0, 0)
        pos_layout.setSpacing(4)
        self._insp_pos_x = QDoubleSpinBox()
        self._insp_pos_y = QDoubleSpinBox()
        self._insp_pos_z = QDoubleSpinBox()
        for sb in (self._insp_pos_x, self._insp_pos_y, self._insp_pos_z):
            sb.setRange(-1_000_000.0, 1_000_000.0)
            sb.setDecimals(3)
            sb.setSingleStep(1.0)
            sb.valueChanged.connect(self._on_insp_pos_changed)
            pos_layout.addWidget(sb)

        scale_widget = QWidget()
        scale_w_layout = QHBoxLayout(scale_widget)
        scale_w_layout.setContentsMargins(0, 0, 0, 0)
        scale_w_layout.setSpacing(4)
        self._insp_scale_x = QDoubleSpinBox()
        self._insp_scale_y = QDoubleSpinBox()
        self._insp_scale_z = QDoubleSpinBox()
        for sb in (self._insp_scale_x, self._insp_scale_y, self._insp_scale_z):
            sb.setRange(0.001, 10_000.0)
            sb.setDecimals(3)
            sb.setSingleStep(0.1)
            sb.valueChanged.connect(self._on_insp_scale_changed)
            scale_w_layout.addWidget(sb)

        self._insp_scale_lock = QCheckBox("Lock X/Y/Z together")
        self._insp_scale_lock.setToolTip(
            "When checked, editing one scale axis sets all three to the same value."
        )

        self._insp_geo = QComboBox()
        for geo_id in range(GEO_COUNT):
            self._insp_geo.addItem(GEO_NAMES[geo_id], geo_id)
        self._insp_geo.currentIndexChanged.connect(self._on_insp_geo_changed)

        self._insp_topo = QComboBox()
        for topo_id in range(TOPO_COUNT):
            self._insp_topo.addItem(TOPO_NAMES.get(topo_id, f"Topology {topo_id}"), topo_id)
        self._insp_topo.currentIndexChanged.connect(self._on_insp_topo_changed)

        self._insp_color_btn = QPushButton()
        self._insp_color_btn.setFixedHeight(24)
        self._insp_color_btn.clicked.connect(self._on_insp_color)

        insp_layout.addRow("ID:",       self._insp_id)
        insp_layout.addRow("Type:",     self._insp_type)
        insp_layout.addRow("Parent:",   self._insp_parent)
        insp_layout.addRow("Pos (X,Y,Z):", pos_widget)
        insp_layout.addRow("Scale (X,Y,Z):", scale_widget)
        insp_layout.addRow("", self._insp_scale_lock)
        insp_layout.addRow("Geometry:", self._insp_geo)
        insp_layout.addRow("Topology:", self._insp_topo)
        insp_layout.addRow("Color:",    self._insp_color_btn)

        layout.addWidget(disp)
        layout.addWidget(scale_grp)
        layout.addWidget(stats_grp)
        layout.addWidget(self._insp_grp)
        layout.addStretch()

        scroll.setWidget(panel)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_table(self):
        dock = QDockWidget("Node Table", self)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )

        self._table = NodeTableView()
        dock.setWidget(self._table)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

        self._table.selectionModel().selectionChanged.connect(self._on_table_selection)
        self._table.doubleClicked.connect(self._on_table_double_click)

    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.showMessage("Ready — File > Open Node CSV to load data.")

    # --- actions ---

    def _open_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open GaiaViz Node CSV",
            str(Path.home()),
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return
        try:
            self.nodes = load_node_csv(path)
            self._viewport.set_nodes(self.nodes)
            self._table.set_nodes(self.nodes)
            self._update_stats(Path(path).name)
            self.statusBar().showMessage(f"Loaded {len(self.nodes)} nodes from {Path(path).name}")
        except Exception as exc:
            self.statusBar().showMessage(f"Error: {exc}")

    def _set_axes(self, checked: bool):
        self._viewport.show_axes = checked
        self._cb_axes.setChecked(checked)
        self._axes_act.setChecked(checked)
        self._viewport.update()

    def _set_grid(self, checked: bool):
        self._viewport.show_grid = checked
        self._cb_grid.setChecked(checked)
        self._grid_act.setChecked(checked)
        self._viewport.update()

    def _set_hidden(self, checked: bool):
        self._viewport.show_hidden = checked
        self._cb_hidden.setChecked(checked)
        self._hidden_act.setChecked(checked)
        self._viewport.update()
        self._update_stats()

    def _update_scale(self, value: int):
        scale = value / 10.0
        self._scale_label.setText(f"Scale: {scale:.1f}")
        self._viewport.base_scale = scale
        self._viewport.update()

    def _on_viewport_pick(self, node_id: int):
        """Select the clicked node in the table (which then drives inspector + highlight)."""
        self._table.select_by_id(node_id)

    def _on_table_selection(self):
        node = self._table.selected_node()
        self._viewport.selected_node_id = node.id if node else None
        self._refresh_inspector(node)
        self._viewport.update()
        if node:
            self.statusBar().showMessage(
                f"Node {node.id}  type={node.type}  "
                f"pos=({node.translate_x:.2f}, {node.translate_y:.2f}, {node.translate_z:.2f})  "
                f"geo={node.geometry}  topo={node.topo}"
            )

    def _refresh_inspector(self, node: Node | None):
        if node is None:
            self._insp_grp.setEnabled(False)
            return
        self._insp_grp.setEnabled(True)
        self._insp_id.setText(str(node.id))
        self._insp_type.setText(str(node.type))
        self._insp_parent.setText(str(node.parent_id))
        for sb, val in (
            (self._insp_pos_x, node.translate_x),
            (self._insp_pos_y, node.translate_y),
            (self._insp_pos_z, node.translate_z),
            (self._insp_scale_x, node.scale_x),
            (self._insp_scale_y, node.scale_y),
            (self._insp_scale_z, node.scale_z),
        ):
            sb.blockSignals(True)
            sb.setValue(val)
            sb.blockSignals(False)
        idx = self._insp_geo.findData(node.geometry)
        self._insp_geo.blockSignals(True)
        self._insp_geo.setCurrentIndex(max(idx, 0))
        self._insp_geo.blockSignals(False)

        idx = self._insp_topo.findData(node.topo)
        self._insp_topo.blockSignals(True)
        self._insp_topo.setCurrentIndex(max(idx, 0))
        self._insp_topo.blockSignals(False)

        self._refresh_color_btn(node)

    def _refresh_color_btn(self, node: Node):
        self._insp_color_btn.setStyleSheet(
            f"background-color: rgba({node.color_r},{node.color_g},"
            f"{node.color_b},{node.color_a}); border: 1px solid #666;"
        )
        self._insp_color_btn.setText(
            f"#{node.color_r:02X}{node.color_g:02X}{node.color_b:02X}"
        )

    def _on_insp_pos_changed(self, _value: float):
        node = self._table.selected_node()
        if node is None:
            return
        node.translate_x = self._insp_pos_x.value()
        node.translate_y = self._insp_pos_y.value()
        node.translate_z = self._insp_pos_z.value()
        self._table.refresh_node(node.id)
        self._viewport.update()

    def _on_insp_geo_changed(self, _idx: int):
        node = self._table.selected_node()
        if node is None:
            return
        node.geometry = self._insp_geo.currentData()
        self._table.refresh_node(node.id)
        self._viewport.update()

    def _on_insp_scale_changed(self, value: float):
        node = self._table.selected_node()
        if node is None:
            return
        if self._insp_scale_lock.isChecked():
            sender = self.sender()
            for sb in (self._insp_scale_x, self._insp_scale_y, self._insp_scale_z):
                if sb is not sender:
                    sb.blockSignals(True)
                    sb.setValue(value)
                    sb.blockSignals(False)
        node.scale_x = self._insp_scale_x.value()
        node.scale_y = self._insp_scale_y.value()
        node.scale_z = self._insp_scale_z.value()
        self._table.refresh_node(node.id)
        self._viewport.update()

    def _on_insp_topo_changed(self, _idx: int):
        node = self._table.selected_node()
        if node is None:
            return
        node.topo = self._insp_topo.currentData()
        self._table.refresh_node(node.id)
        self._viewport.update()

    def _on_insp_color(self):
        node = self._table.selected_node()
        if node is None:
            return
        initial = QColor(node.color_r, node.color_g, node.color_b, node.color_a)
        color = QColorDialog.getColor(
            initial, self, "Node Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not color.isValid():
            return
        node.color_r = color.red()
        node.color_g = color.green()
        node.color_b = color.blue()
        node.color_a = color.alpha()
        self._refresh_color_btn(node)
        self._table.refresh_node(node.id)
        self._viewport.update()

    def _on_table_double_click(self):
        node = self._table.selected_node()
        if node is None:
            return
        self._viewport.focus_on_node(node)

    def _reset_camera(self):
        self._viewport.set_nodes(self.nodes)

    def _update_stats(self, filename: str = None):
        total = len(self.nodes)
        visible = sum(1 for n in self.nodes
                      if not n.hide and n.type not in NON_VISUAL_TYPES)
        if filename:
            self._lbl_file.setText(f"File: {filename}")
        self._lbl_total.setText(f"Nodes: {total}")
        self._lbl_visible.setText(f"Visible: {visible}")
