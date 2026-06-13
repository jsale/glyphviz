from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
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
from .geometry import GEO_NAMES, GEO_COUNT, GEO_OCTA
from .node import Node, NON_VISUAL_TYPES
from .node_table import NodeTableView
from .topology import TOPO_NAMES, TOPO_COUNT, TOPO_POINT
from .viewport import Viewport


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GlyphViz")
        self.resize(1280, 800)
        self.nodes: list[Node] = []

        # Multi-select state
        self._selected_nodes: list[Node] = []
        # Anchor values for delta-based position/rotation editing across a selection.
        # When the inspector is refreshed for a selection, these are set to the
        # primary node's values.  Each subsequent edit computes a delta from the
        # anchor, applies it to all selected nodes, then advances the anchor so
        # the next edit increments correctly.
        self._anchor_pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._anchor_rot: tuple[float, float, float] = (0.0, 0.0, 0.0)

        self._build_viewport()
        self._build_menu()
        self._build_panel()
        self._build_table()
        self._build_statusbar()

        QShortcut(QKeySequence("Ctrl+A"), self).activated.connect(
            self._on_select_all_toggle
        )

    def _build_viewport(self):
        self._viewport = Viewport(self)
        self._viewport.nodeClicked.connect(self._on_viewport_pick)
        self._viewport.nodeClickedAdditive.connect(self._on_viewport_pick_additive)
        self._viewport.nodesSelected.connect(self._on_viewport_nodes_selected)
        self._viewport.navParent.connect(self._nav_parent)
        self._viewport.navChild.connect(self._nav_child)
        self._viewport.navNextSibling.connect(self._nav_next_sibling)
        self._viewport.navPrevSibling.connect(self._nav_prev_sibling)
        self._viewport.createNode.connect(self._on_create_node)
        self._viewport.createChildNode.connect(self._create_child_node)
        self.setCentralWidget(self._viewport)
        # Link self.nodes into the viewport scene so appends stay in sync.
        self._viewport.set_nodes(self.nodes)

    def _build_menu(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        open_act = file_menu.addAction("&Open Node CSV…")
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._open_csv)
        file_menu.addSeparator()
        file_menu.addAction("&Quit").triggered.connect(self.close)

        self._view_menu = mb.addMenu("&View")

        self._axes_act = self._view_menu.addAction("Show &Axes")
        self._axes_act.setCheckable(True)
        self._axes_act.setChecked(True)
        self._axes_act.triggered.connect(lambda c: self._set_axes(c))

        self._grid_act = self._view_menu.addAction("Show &Grid")
        self._grid_act.setCheckable(True)
        self._grid_act.setChecked(True)
        self._grid_act.triggered.connect(lambda c: self._set_grid(c))

        self._hidden_act = self._view_menu.addAction("Show &Hidden Nodes")
        self._hidden_act.setCheckable(True)
        self._hidden_act.setChecked(False)
        self._hidden_act.triggered.connect(lambda c: self._set_hidden(c))

        self._view_menu.addSeparator()
        self._view_menu.addAction("Reset &Camera").triggered.connect(self._reset_camera)

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

        # --- Create group ---
        create_grp = QGroupBox("Create")
        create_layout = QVBoxLayout(create_grp)

        self._btn_new_node = QPushButton("New Node")
        self._btn_new_node.setToolTip(
            "Create a new octahedron at the world origin  [N]\n"
            "Each press increments X by 10 units.  If a child-level\n"
            "node is selected, a child is added instead."
        )
        self._btn_new_node.clicked.connect(self._on_create_node)

        self._btn_new_child = QPushButton("New Child")
        self._btn_new_child.setToolTip(
            "Create a child octahedron under the selected node  [Shift+N]\n"
            "Requires exactly one node to be selected."
        )
        self._btn_new_child.clicked.connect(self._create_child_node)

        create_layout.addWidget(self._btn_new_node)
        create_layout.addWidget(self._btn_new_child)

        # --- Select By group ---
        sel_grp = QGroupBox("Select By")
        sel_layout = QFormLayout(sel_grp)
        sel_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        all_none_widget = QWidget()
        all_none_layout = QHBoxLayout(all_none_widget)
        all_none_layout.setContentsMargins(0, 0, 0, 0)
        all_none_layout.setSpacing(4)
        self._sel_all_btn = QPushButton("Select All")
        self._sel_none_btn = QPushButton("Deselect All")
        self._sel_all_btn.setToolTip("Select every node  (Ctrl+A)")
        self._sel_none_btn.setToolTip("Clear the selection  (Ctrl+A again)")
        self._sel_all_btn.clicked.connect(self._on_select_all)
        self._sel_none_btn.clicked.connect(self._on_deselect_all)
        all_none_layout.addWidget(self._sel_all_btn)
        all_none_layout.addWidget(self._sel_none_btn)

        self._sel_criterion = QComboBox()
        self._sel_criterion.addItems(["Branch Level", "Geometry", "Topology"])
        self._sel_criterion.currentIndexChanged.connect(self._update_sel_values)

        self._sel_value = QComboBox()

        self._sel_btn = QPushButton("Select All Matching")
        self._sel_btn.clicked.connect(self._on_select_by)

        sel_layout.addRow(all_none_widget)
        sel_layout.addRow("By:", self._sel_criterion)
        sel_layout.addRow("Value:", self._sel_value)
        sel_layout.addRow(self._sel_btn)

        # --- Selected Node / Selection inspector ---
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

        rot_widget = QWidget()
        rot_layout = QHBoxLayout(rot_widget)
        rot_layout.setContentsMargins(0, 0, 0, 0)
        rot_layout.setSpacing(4)
        self._insp_rot_x = QDoubleSpinBox()
        self._insp_rot_y = QDoubleSpinBox()
        self._insp_rot_z = QDoubleSpinBox()
        for sb in (self._insp_rot_x, self._insp_rot_y, self._insp_rot_z):
            sb.setRange(-360.0, 360.0)
            sb.setDecimals(2)
            sb.setSingleStep(1.0)
            sb.setWrapping(True)
            sb.valueChanged.connect(self._on_insp_rotation_changed)
            rot_layout.addWidget(sb)

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

        self._insp_ratio = QDoubleSpinBox()
        self._insp_ratio.setRange(0.01, 1.0)
        self._insp_ratio.setDecimals(3)
        self._insp_ratio.setSingleStep(0.01)
        self._insp_ratio.setToolTip(
            "Torus minor-radius proportion (GaiaViz/ANTz 'ratio'): the tube "
            "radius as a fraction of the torus's overall radius. Also used to "
            "place children riding on a Torus-topology parent's surface."
        )
        self._insp_ratio.valueChanged.connect(self._on_insp_ratio_changed)

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
        insp_layout.addRow("Rotate (X,Y,Z):", rot_widget)
        insp_layout.addRow("Scale (X,Y,Z):", scale_widget)
        insp_layout.addRow("", self._insp_scale_lock)
        insp_layout.addRow("Geometry:", self._insp_geo)
        insp_layout.addRow("Topology:", self._insp_topo)
        insp_layout.addRow("Ratio:",    self._insp_ratio)
        insp_layout.addRow("Color:",    self._insp_color_btn)

        layout.addWidget(disp)
        layout.addWidget(scale_grp)
        layout.addWidget(stats_grp)
        layout.addWidget(create_grp)
        layout.addWidget(sel_grp)
        layout.addWidget(self._insp_grp)
        layout.addStretch()

        scroll.setWidget(panel)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self._view_menu.addSeparator()
        self._view_menu.addAction(dock.toggleViewAction())

    def _build_table(self):
        dock = QDockWidget("Node Table", self)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )

        self._table = NodeTableView()
        dock.setWidget(self._table)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self._view_menu.addAction(dock.toggleViewAction())

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
            self._update_sel_values()
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

    # --- Select By ---

    def _update_sel_values(self):
        """Repopulate the value combo for the current Select By criterion."""
        criterion = self._sel_criterion.currentText()
        self._sel_value.blockSignals(True)
        self._sel_value.clear()
        if self.nodes:
            if criterion == "Branch Level":
                for lv in sorted(set(n.branch_level for n in self.nodes)):
                    self._sel_value.addItem(str(lv), lv)
            elif criterion == "Geometry":
                for g in sorted(set(n.geometry for n in self.nodes)):
                    self._sel_value.addItem(f"{g}: {GEO_NAMES.get(g, f'Geo {g}')}", g)
            elif criterion == "Topology":
                for t in sorted(set(n.topo for n in self.nodes)):
                    self._sel_value.addItem(f"{t}: {TOPO_NAMES.get(t, f'Topo {t}')}", t)
        self._sel_value.blockSignals(False)

    def _on_select_by(self):
        criterion = self._sel_criterion.currentText()
        value = self._sel_value.currentData()
        if value is None:
            return
        if criterion == "Branch Level":
            ids = {n.id for n in self.nodes if n.branch_level == value}
        elif criterion == "Geometry":
            ids = {n.id for n in self.nodes if n.geometry == value}
        elif criterion == "Topology":
            ids = {n.id for n in self.nodes if n.topo == value}
        else:
            return
        self._table.select_by_ids(ids)

    def _on_select_all(self):
        self._table.select_by_ids({n.id for n in self.nodes})

    def _on_deselect_all(self):
        self._table.select_by_ids(set())

    def _on_select_all_toggle(self):
        """Ctrl+A: select all when nothing (or a partial set) is selected; deselect all otherwise."""
        if len(self._selected_nodes) < len(self.nodes):
            self._on_select_all()
        else:
            self._on_deselect_all()

    # --- viewport pick callbacks ---

    def _on_viewport_pick(self, node_id: int):
        """Plain click: replace selection with this single node."""
        self._table.select_by_id(node_id)

    def _on_viewport_pick_additive(self, node_id: int):
        """Ctrl+click: toggle this node in/out of the current selection."""
        self._table.select_toggle_id(node_id)

    def _on_viewport_nodes_selected(self, node_ids: object):
        """Rubber-band or click-on-empty: replace selection with the given ID set."""
        self._table.select_by_ids(set(node_ids))

    # --- table selection → inspector + viewport highlight ---

    def _on_table_selection(self):
        self._selected_nodes = self._table.selected_nodes()
        self._viewport.selected_node_ids = {n.id for n in self._selected_nodes}
        self._viewport.update()

        n = len(self._selected_nodes)
        if n == 0:
            self._refresh_inspector(None)
            self.statusBar().showMessage("No selection.")
        elif n == 1:
            node = self._selected_nodes[0]
            self._refresh_inspector(node)
            self.statusBar().showMessage(
                f"Node {node.id}  type={node.type}  "
                f"pos=({node.translate_x:.2f}, {node.translate_y:.2f}, {node.translate_z:.2f})  "
                f"geo={node.geometry}  topo={node.topo}"
            )
        else:
            self._refresh_inspector_multi(self._selected_nodes)
            self.statusBar().showMessage(f"{n} nodes selected.")

    def _refresh_inspector(self, node: Node | None):
        """Single-node or empty inspector state."""
        if node is None:
            self._insp_grp.setTitle("Selected Node")
            self._insp_grp.setEnabled(False)
            return
        self._insp_grp.setTitle("Selected Node")
        self._insp_grp.setEnabled(True)
        self._insp_id.setText(str(node.id))
        self._insp_type.setText(str(node.type))
        self._insp_parent.setText(str(node.parent_id))
        for sb, val in (
            (self._insp_pos_x, node.translate_x),
            (self._insp_pos_y, node.translate_y),
            (self._insp_pos_z, node.translate_z),
            (self._insp_rot_x, node.rotate_x),
            (self._insp_rot_y, node.rotate_y),
            (self._insp_rot_z, node.rotate_z),
            (self._insp_scale_x, node.scale_x),
            (self._insp_scale_y, node.scale_y),
            (self._insp_scale_z, node.scale_z),
            (self._insp_ratio, node.ratio),
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
        # Record anchors (used by multi-select delta logic; harmless for single)
        self._anchor_pos = (node.translate_x, node.translate_y, node.translate_z)
        self._anchor_rot = (node.rotate_x, node.rotate_y, node.rotate_z)

    def _refresh_inspector_multi(self, nodes: list[Node]):
        """
        Multi-node inspector state.  Shows the primary (first) node's values.

        Position / rotation edits apply a DELTA to all selected nodes so they
        move together rather than collapsing to one point.  Scale, geometry,
        topology, ratio, and color apply the same absolute value to all nodes.
        """
        n = len(nodes)
        self._insp_grp.setTitle(f"Selection ({n} nodes)")
        self._insp_grp.setEnabled(True)
        self._insp_id.setText("(multiple)")
        self._insp_type.setText("(multiple)")
        self._insp_parent.setText("(multiple)")

        primary = nodes[0]
        for sb, val in (
            (self._insp_pos_x, primary.translate_x),
            (self._insp_pos_y, primary.translate_y),
            (self._insp_pos_z, primary.translate_z),
            (self._insp_rot_x, primary.rotate_x),
            (self._insp_rot_y, primary.rotate_y),
            (self._insp_rot_z, primary.rotate_z),
            (self._insp_scale_x, primary.scale_x),
            (self._insp_scale_y, primary.scale_y),
            (self._insp_scale_z, primary.scale_z),
            (self._insp_ratio, primary.ratio),
        ):
            sb.blockSignals(True)
            sb.setValue(val)
            sb.blockSignals(False)

        idx = self._insp_geo.findData(primary.geometry)
        self._insp_geo.blockSignals(True)
        self._insp_geo.setCurrentIndex(max(idx, 0))
        self._insp_geo.blockSignals(False)

        idx = self._insp_topo.findData(primary.topo)
        self._insp_topo.blockSignals(True)
        self._insp_topo.setCurrentIndex(max(idx, 0))
        self._insp_topo.blockSignals(False)

        self._refresh_color_btn(primary)

        # Anchor for delta-based pos/rot edits
        self._anchor_pos = (primary.translate_x, primary.translate_y, primary.translate_z)
        self._anchor_rot = (primary.rotate_x, primary.rotate_y, primary.rotate_z)

    def _refresh_color_btn(self, node: Node):
        self._insp_color_btn.setStyleSheet(
            f"background-color: rgba({node.color_r},{node.color_g},"
            f"{node.color_b},{node.color_a}); border: 1px solid #666;"
        )
        self._insp_color_btn.setText(
            f"#{node.color_r:02X}{node.color_g:02X}{node.color_b:02X}"
        )

    # --- inspector change handlers ---

    def _on_insp_pos_changed(self, _value: float):
        if not self._selected_nodes:
            return
        if len(self._selected_nodes) == 1:
            node = self._selected_nodes[0]
            node.translate_x = self._insp_pos_x.value()
            node.translate_y = self._insp_pos_y.value()
            node.translate_z = self._insp_pos_z.value()
            self._table.refresh_node(node.id)
        else:
            # Delta-move: compute offset from the anchor, apply to all nodes.
            nx, ny, nz = (
                self._insp_pos_x.value(),
                self._insp_pos_y.value(),
                self._insp_pos_z.value(),
            )
            dx = nx - self._anchor_pos[0]
            dy = ny - self._anchor_pos[1]
            dz = nz - self._anchor_pos[2]
            self._anchor_pos = (nx, ny, nz)
            for node in self._selected_nodes:
                node.translate_x += dx
                node.translate_y += dy
                node.translate_z += dz
                self._table.refresh_node(node.id)
        self._viewport.update()

    def _on_insp_rotation_changed(self, _value: float):
        if not self._selected_nodes:
            return
        if len(self._selected_nodes) == 1:
            node = self._selected_nodes[0]
            node.rotate_x = self._insp_rot_x.value()
            node.rotate_y = self._insp_rot_y.value()
            node.rotate_z = self._insp_rot_z.value()
            self._table.refresh_node(node.id)
        else:
            nrx, nry, nrz = (
                self._insp_rot_x.value(),
                self._insp_rot_y.value(),
                self._insp_rot_z.value(),
            )
            drx = nrx - self._anchor_rot[0]
            dry = nry - self._anchor_rot[1]
            drz = nrz - self._anchor_rot[2]
            self._anchor_rot = (nrx, nry, nrz)
            for node in self._selected_nodes:
                node.rotate_x += drx
                node.rotate_y += dry
                node.rotate_z += drz
                self._table.refresh_node(node.id)
        self._viewport.update()

    def _on_insp_geo_changed(self, _idx: int):
        if not self._selected_nodes:
            return
        geo = self._insp_geo.currentData()
        for node in self._selected_nodes:
            node.geometry = geo
            self._table.refresh_node(node.id)
        self._viewport.update()

    def _on_insp_scale_changed(self, value: float):
        if not self._selected_nodes:
            return
        if self._insp_scale_lock.isChecked():
            sender = self.sender()
            for sb in (self._insp_scale_x, self._insp_scale_y, self._insp_scale_z):
                if sb is not sender:
                    sb.blockSignals(True)
                    sb.setValue(value)
                    sb.blockSignals(False)
        sx = self._insp_scale_x.value()
        sy = self._insp_scale_y.value()
        sz = self._insp_scale_z.value()
        for node in self._selected_nodes:
            node.scale_x = sx
            node.scale_y = sy
            node.scale_z = sz
            self._table.refresh_node(node.id)
        self._viewport.update()

    def _on_insp_ratio_changed(self, value: float):
        if not self._selected_nodes:
            return
        for node in self._selected_nodes:
            node.ratio = value
            self._table.refresh_node(node.id)
        self._viewport.update()

    def _on_insp_topo_changed(self, _idx: int):
        if not self._selected_nodes:
            return
        topo = self._insp_topo.currentData()
        for node in self._selected_nodes:
            node.topo = topo
            self._table.refresh_node(node.id)
        self._viewport.update()

    def _on_insp_color(self):
        if not self._selected_nodes:
            return
        primary = self._selected_nodes[0]
        initial = QColor(primary.color_r, primary.color_g, primary.color_b, primary.color_a)
        color = QColorDialog.getColor(
            initial, self, "Node Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not color.isValid():
            return
        for node in self._selected_nodes:
            node.color_r = color.red()
            node.color_g = color.green()
            node.color_b = color.blue()
            node.color_a = color.alpha()
            self._table.refresh_node(node.id)
        self._refresh_color_btn(self._selected_nodes[0])
        self._viewport.update()

    def _on_table_double_click(self):
        node = self._table.selected_node()
        if node is None:
            return
        self._viewport.focus_on_node(node)

    def _reset_camera(self):
        self._viewport.set_nodes(self.nodes)

    # --- ANTz-style keyboard hierarchy navigation ---

    def _node_by_id(self, node_id: int) -> Node | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def _get_siblings(self, node: Node) -> list[Node]:
        """
        Return the ordered list of nodes that Tab cycles through from node's position.

        branch_level == 0  →  all visual root nodes in the scene (glyph-to-glyph).
        branch_level  > 0  →  all visual nodes sharing the same parent_id (within
                               the same hyperglyph only).
        Order matches the node list (i.e., CSV row order).
        """
        visual = [n for n in self.nodes if n.type not in NON_VISUAL_TYPES]
        if node.branch_level == 0:
            return [n for n in visual if n.branch_level == 0]
        return [n for n in visual if n.parent_id == node.parent_id]

    def _nav_select(self, node: Node):
        """Select node and show a one-line status describing the move."""
        self._table.select_by_id(node.id)
        self.statusBar().showMessage(
            f"Nav → Node {node.id}  level={node.branch_level}  "
            f"parent={node.parent_id}  geo={node.geometry}  topo={node.topo}"
        )

    def _nav_parent(self):
        """Up arrow: move to the parent of the currently selected node."""
        if len(self._selected_nodes) != 1:
            return
        current = self._selected_nodes[0]
        parent = self._node_by_id(current.parent_id)
        if parent is None or parent.type in NON_VISUAL_TYPES:
            return
        self._nav_select(parent)

    def _nav_child(self):
        """Down arrow: move to the first child of the currently selected node."""
        if len(self._selected_nodes) != 1:
            return
        current = self._selected_nodes[0]
        child = next(
            (n for n in self.nodes
             if n.parent_id == current.id and n.type not in NON_VISUAL_TYPES),
            None,
        )
        if child is not None:
            self._nav_select(child)

    def _nav_next_sibling(self):
        """Tab: move to the next sibling at the same branch level.

        At branch_level 0 this cycles through all root nodes in the scene.
        At deeper levels it cycles only among siblings within the same parent.
        Wraps around at the end.  If nothing is selected, starts at the first
        visual node in the scene.
        """
        if not self._selected_nodes:
            first = next(
                (n for n in self.nodes if n.type not in NON_VISUAL_TYPES), None
            )
            if first:
                self._nav_select(first)
            return
        if len(self._selected_nodes) != 1:
            return
        current = self._selected_nodes[0]
        siblings = self._get_siblings(current)
        if not siblings:
            return
        idx = next((i for i, n in enumerate(siblings) if n.id == current.id), None)
        if idx is None:
            return
        self._nav_select(siblings[(idx + 1) % len(siblings)])

    def _nav_prev_sibling(self):
        """Shift+Tab: move to the previous sibling (reverse of Tab).  Wraps around."""
        if not self._selected_nodes:
            return
        if len(self._selected_nodes) != 1:
            return
        current = self._selected_nodes[0]
        siblings = self._get_siblings(current)
        if not siblings:
            return
        idx = next((i for i, n in enumerate(siblings) if n.id == current.id), None)
        if idx is None:
            return
        self._nav_select(siblings[(idx - 1) % len(siblings)])

    # --- ANTz-style node creation ---

    def _on_create_node(self):
        """N key / New Node button: adds a child when a child-level node is selected,
        otherwise creates a new root-level node."""
        if len(self._selected_nodes) == 1 and self._selected_nodes[0].branch_level >= 1:
            self._create_child_node()
        else:
            self._create_root_node()

    def _create_root_node(self):
        """Create a new root-level octahedron, stepping +10 along X from the last one."""
        root_glyphs = [
            n for n in self.nodes
            if n.type not in NON_VISUAL_TYPES and n.branch_level == 0
        ]
        next_x = (max(n.translate_x for n in root_glyphs) + 10.0) if root_glyphs else 0.0
        new_id = max((n.id for n in self.nodes), default=0) + 1
        self._add_node_to_scene(Node(
            id=new_id, type=5, parent_id=0, branch_level=0,
            translate_x=next_x, translate_y=0.0, translate_z=0.0,
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=1.0, scale_y=1.0, scale_z=1.0,
            color_r=200, color_g=200, color_b=200, color_a=255,
            geometry=GEO_OCTA, hide=0, topo=TOPO_POINT,
        ))

    def _create_child_node(self):
        """Shift+N / New Child button: create a child octahedron under the selected node."""
        if len(self._selected_nodes) != 1:
            self.statusBar().showMessage("Select exactly one node to add a child.")
            return
        parent = self._selected_nodes[0]
        new_id = max((n.id for n in self.nodes), default=0) + 1
        self._add_node_to_scene(Node(
            id=new_id, type=5, parent_id=parent.id,
            branch_level=parent.branch_level + 1,
            translate_x=0.0, translate_y=0.0, translate_z=5.0,
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=1.0, scale_y=1.0, scale_z=1.0,
            color_r=200, color_g=200, color_b=200, color_a=255,
            geometry=GEO_OCTA, hide=0, topo=TOPO_POINT,
        ))

    def _add_node_to_scene(self, node: Node):
        """Append a node to the live scene, table, and stats without resetting the camera."""
        self.nodes.append(node)           # also updates _scene.nodes (same list)
        self._viewport.register_node(node)  # syncs _by_id, invalidates, repaints
        self._table.append_node(node)
        self._update_stats()
        self._table.select_by_id(node.id)
        self.statusBar().showMessage(
            f"Created node {node.id}  parent={node.parent_id}  "
            f"level={node.branch_level}  geo={node.geometry}  topo={node.topo}"
        )

    def _update_stats(self, filename: str = None):
        total = len(self.nodes)
        visible = sum(1 for n in self.nodes
                      if not n.hide and n.type not in NON_VISUAL_TYPES)
        if filename:
            self._lbl_file.setText(f"File: {filename}")
        self._lbl_total.setText(f"Nodes: {total}")
        self._lbl_visible.setText(f"Visible: {visible}")
