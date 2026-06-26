import copy
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
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
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from glyphviz_core.csv_reader import (
    load_node_csv, save_node_csv, save_tag_csv, stamp_node_and_tag_paths,
)
from glyphviz_core.geometry_data import GEO_NAMES, GEO_COUNT, GEO_OCTA, GEO_MESH
from glyphviz_core.node import (
    Node, NON_VISUAL_TYPES, ROTATION_MODE_EULER_XYZ, ROTATION_MODE_HEADING_TILT_ROLL,
    NODE_TYPE_LINK, NODE_TYPE_WORLD, RENDER_MODE_COUNT, RENDER_MODE_NAMES, RENDER_MODE_NORMAL,
    WORLD_DEFAULT_BG_RGB,
)
from glyphviz_core.topology import TOPO_NAMES, TOPO_COUNT, TOPO_POINT, CUBE_FACE_NAMES

from .audio_player import AudioPlayer
from .node_table import NodeTableView
from .viewport import Viewport

_AUDIO_TICK_MS = 33   # redraw rate while Channels playback is audio-driven (~30 Hz)


def _app_dir() -> Path:
    """Directory treated as 'next to the executable' for K-key autosave: the
    frozen executable's folder (e.g. PyInstaller), or the folder containing
    main.py when running from source. No ANTz-style usr/csv/ subfolder yet —
    that's a future convention, not implemented here."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GlyphViz")
        self.resize(1280, 800)
        self.nodes: list[Node] = []
        self._current_path: str | None = None   # path of the currently open file
        self._current_tag_path: str | None = None   # companion tag-file path, if any
        # False right after Open (the on-disk file has no timestamp yet); the
        # first Ctrl+S after opening silently stamps a *new* file rather than
        # overwriting the original, so opening + saving never clobbers an
        # un-timestamped file the user (or another tool) created.
        self._path_is_stamped = False

        # Multi-select state
        self._selected_nodes: list[Node] = []
        # Anchor values for delta-based position/rotation editing across a selection.
        # When the inspector is refreshed for a selection, these are set to the
        # primary node's values.  Each subsequent edit computes a delta from the
        # anchor, applies it to all selected nodes, then advances the anchor so
        # the next edit increments correctly.
        self._anchor_pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._anchor_rot: tuple[float, float, float] = (0.0, 0.0, 0.0)

        # Copy/Paste clipboard: a node plus its full descendant closure, always
        # copied together (V1 — see CLAUDE.md/memory; no partial-subtree copies).
        self._clipboard_nodes: list[Node] = []
        self._clipboard_root_id: int | None = None

        # Channel animation state
        self._ch_engine = None
        self._ch_frame = 0
        self._ch_playing = False
        self._ch_timer = QTimer(self)
        self._ch_timer.timeout.connect(self._ch_tick)
        # Audio-synced Channels ("music synesthesia"): when a Channels example
        # has a companion gv_audio.txt manifest, frame advance is driven by
        # this player's real playback position instead of the fixed-FPS timer.
        self._ch_audio = AudioPlayer()
        self._ch_audio_loaded = False

        # Gizmo manipulation state (Move/Rotate/Size mode selector)
        self._gizmo_mode: str | None = None
        self._mode_buttons: dict[str, QPushButton] = {}

        self._build_viewport()
        self._build_menu()
        self._build_manipulate_toolbar()
        self._build_panel()
        self._build_table()
        self._build_statusbar()

        QShortcut(QKeySequence("Ctrl+A"), self).activated.connect(
            self._on_select_all_toggle
        )
        QShortcut(QKeySequence("U"), self).activated.connect(self._on_open_link)
        QShortcut(QKeySequence("Delete"), self).activated.connect(self._delete_selected)
        QShortcut(QKeySequence("Backspace"), self).activated.connect(self._delete_selected)

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
        self._viewport.drawLimitChanged.connect(self._on_draw_limit_changed)
        self._viewport.fpsUpdated.connect(self._on_fps_updated)
        self._viewport.tagToggled.connect(self._on_tag_toggled)
        self._viewport.quickSaveRequested.connect(self._quick_save)
        self._viewport.nodesManipulated.connect(self._on_viewport_manipulated)
        self._viewport.bgToggleRequested.connect(self._on_scene_bg_toggle_bw)
        self._viewport.renderModeCycleRequested.connect(self._on_scene_render_mode_cycle)
        self.setCentralWidget(self._viewport)
        # Link self.nodes into the viewport scene so appends stay in sync.
        self._viewport.set_nodes(self.nodes)

    def _build_menu(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        open_act = file_menu.addAction("&Open Node CSV…")
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._open_csv)

        self._save_act = file_menu.addAction("&Save")
        self._save_act.setShortcut("Ctrl+S")
        self._save_act.setEnabled(False)
        self._save_act.triggered.connect(self._save_csv)

        save_as_act = file_menu.addAction("Save &As…")
        save_as_act.setShortcut("Ctrl+Shift+S")
        save_as_act.triggered.connect(self._save_csv_as)

        file_menu.addSeparator()
        png_act = file_menu.addAction("Save &Scene as PNG…")
        png_act.setShortcut("F12")
        png_act.setToolTip("Save the current viewport as a PNG image  [F12]")
        png_act.triggered.connect(self._save_scene_png)

        file_menu.addSeparator()
        file_menu.addAction("&Quit").triggered.connect(self.close)

        edit_menu = mb.addMenu("&Edit")
        copy_act = edit_menu.addAction("&Copy")
        copy_act.setShortcut("Ctrl+C")
        copy_act.setToolTip("Copy the selected node and its full descendant subtree.")
        copy_act.triggered.connect(self._copy_selected)

        paste_act = edit_menu.addAction("&Paste")
        paste_act.setShortcut("Ctrl+V")
        paste_act.setToolTip("Paste the copied subtree as a new sibling, with fresh ids.")
        paste_act.triggered.connect(self._paste_clipboard)

        tex_menu = mb.addMenu("&Textures")

        set_tex_act = tex_menu.addAction("Set Texture &Folder…")
        set_tex_act.setToolTip(
            "Load images from a folder in alphanumeric order.\n"
            "Texture ID 1 = first file, 2 = second, etc.\n"
            "Matches the ANTz usr/images/ convention."
        )
        set_tex_act.triggered.connect(self._browse_texture_folder)

        clear_tex_act = tex_menu.addAction("&Clear Textures")
        clear_tex_act.setToolTip("Unload all textures and return to solid-color rendering.")
        clear_tex_act.triggered.connect(self._clear_textures)

        mesh_menu = mb.addMenu("&Meshes")
        import_mesh_act = mesh_menu.addAction("&Import Mesh File…")
        import_mesh_act.setToolTip(
            "Load an OBJ/STL/PLY/glTF file as a GEO_MESH shape.\n"
            "Applies to the selected node, or creates a new root node if none is selected."
        )
        import_mesh_act.triggered.connect(self._import_mesh_file)

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

        self._tags_act = self._view_menu.addAction("Show Tag &Labels")
        self._tags_act.setCheckable(True)
        self._tags_act.setChecked(True)
        self._tags_act.setToolTip("Toggle tag text display  [T]")
        self._tags_act.triggered.connect(lambda c: self._set_tags(c))

        self._view_menu.addSeparator()
        self._view_menu.addAction("Reset &Camera").triggered.connect(self._reset_camera)

    def _build_manipulate_toolbar(self):
        """Ever-present Move/Rotate/Size mode selector + X/Y/Z axis confinement,
        analogous to ANTz's persistent mouse-mode/tool indicator."""
        tb = QToolBar("Manipulate", self)
        tb.setObjectName("manipulateToolbar")
        tb.setMovable(False)

        for name, label, tip in (
            ("move", "Move", "Drag selected node(s) (LeftButton).  Click again to return to camera-only."),
            ("rotate", "Rotate", "Rotate selected node(s) (LeftButton).  Click again to return to camera-only."),
            ("size", "Size", "Scale selected node(s) (LeftButton).  Click again to return to camera-only."),
        ):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setEnabled(False)   # enabled once there's a selection
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _checked=False, n=name: self._on_mode_button_clicked(n))
            self._mode_buttons[name] = btn
            tb.addWidget(btn)

        tb.addSeparator()

        self._gizmo_axis_checks: dict[str, QCheckBox] = {}
        for axis in ('x', 'y', 'z'):
            cb = QCheckBox(axis.upper())
            cb.setChecked(True)
            cb.toggled.connect(lambda _checked=False, a=axis: self._on_gizmo_axis_toggled(a))
            self._gizmo_axis_checks[axis] = cb
            tb.addWidget(cb)
        tb.setToolTip(
            "Confine Move/Rotate/Size drags to these axes.\n"
            "With all three checked: LeftButton drags the first two, "
            "RightButton drags the third.\n"
            "With one or two checked: LeftButton drags them directly, "
            "RightButton always orbits the camera."
        )

        self.addToolBar(tb)
        self._view_menu.addAction(tb.toggleViewAction())

    def _on_mode_button_clicked(self, name: str):
        new_mode = None if self._gizmo_mode == name else name
        self._set_gizmo_mode(new_mode)

    def _set_gizmo_mode(self, mode: str | None):
        self._gizmo_mode = mode
        for n, btn in self._mode_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(n == mode)
            btn.blockSignals(False)
        self._viewport.gizmo_mode = mode

    def _on_gizmo_axis_toggled(self, axis: str, _checked: bool = False):
        self._viewport.gizmo_axes = {
            a: cb.isChecked() for a, cb in self._gizmo_axis_checks.items()
        }

    def _on_viewport_manipulated(self, node_ids: object):
        for nid in node_ids:
            self._table.refresh_node(nid)
        if len(self._selected_nodes) == 1:
            self._refresh_inspector(self._selected_nodes[0])
        elif len(self._selected_nodes) > 1:
            self._refresh_inspector_multi(self._selected_nodes)

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

        self._cb_tags = QCheckBox("Show Tag Labels")
        self._cb_tags.setChecked(True)
        self._cb_tags.setToolTip("Toggle tag text display in 3D view  [T]")
        self._cb_tags.toggled.connect(self._set_tags)

        self._cb_tags_selected = QCheckBox("Show Tag Labels of Selected")
        self._cb_tags_selected.setChecked(False)
        self._cb_tags_selected.setToolTip(
            "When checked, only selected nodes' tag labels are drawn."
        )
        self._cb_tags_selected.toggled.connect(self._set_tags_selected_only)

        disp_layout.addWidget(self._cb_axes)
        disp_layout.addWidget(self._cb_grid)
        disp_layout.addWidget(self._cb_hidden)
        disp_layout.addWidget(self._cb_tags)
        disp_layout.addWidget(self._cb_tags_selected)

        tex_row = QWidget()
        tex_row_layout = QHBoxLayout(tex_row)
        tex_row_layout.setContentsMargins(0, 0, 0, 0)
        tex_row_layout.setSpacing(4)
        self._lbl_tex = QLabel("No textures loaded")
        self._lbl_tex.setWordWrap(True)
        btn_tex = QPushButton("…")
        btn_tex.setFixedWidth(28)
        btn_tex.setToolTip("Set texture folder (Textures menu)")
        btn_tex.clicked.connect(self._browse_texture_folder)
        tex_row_layout.addWidget(self._lbl_tex, 1)
        tex_row_layout.addWidget(btn_tex)
        disp_layout.addWidget(tex_row)

        self._audio_combo = QComboBox()
        self._audio_combo.setToolTip(
            "Videos play their audio all at once by default.\n"
            "Pick one to mute the rest, or 'All Audio Tracks' to hear them together again."
        )
        self._audio_combo.setEnabled(False)
        self._audio_combo.currentIndexChanged.connect(self._on_audio_track_selected)
        disp_layout.addWidget(self._audio_combo)

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

        # --- Scene Settings group: world-level (not per-node) background
        # color, render/blend mode, and fog — read from/written to the World
        # node (type=0, see node.py), mirroring ANTz's global Background
        # Color (B) and Transparency Mode (8) hotkeys.
        scene_grp = QGroupBox("Scene Settings")
        scene_form = QFormLayout(scene_grp)
        scene_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        bg_row = QWidget()
        bg_row_layout = QHBoxLayout(bg_row)
        bg_row_layout.setContentsMargins(0, 0, 0, 0)
        bg_row_layout.setSpacing(4)
        self._scene_bg_btn = QPushButton()
        self._scene_bg_btn.setFixedHeight(24)
        self._scene_bg_btn.clicked.connect(self._on_scene_bg_color)
        self._scene_bg_bw_btn = QPushButton("B/W")
        self._scene_bg_bw_btn.setFixedWidth(36)
        self._scene_bg_bw_btn.setToolTip("Toggle background between black and white  [B]")
        self._scene_bg_bw_btn.clicked.connect(self._on_scene_bg_toggle_bw)
        bg_row_layout.addWidget(self._scene_bg_btn, 1)
        bg_row_layout.addWidget(self._scene_bg_bw_btn)
        self._set_color_btn(self._scene_bg_btn, *WORLD_DEFAULT_BG_RGB, 255)

        self._scene_render_mode = QComboBox()
        for mode_id in range(RENDER_MODE_COUNT):
            self._scene_render_mode.addItem(RENDER_MODE_NAMES.get(mode_id, str(mode_id)), mode_id)
        self._scene_render_mode.setToolTip(
            "Scene-wide blend mode for transparent glyphs  [8 cycles modes]"
        )
        self._scene_render_mode.currentIndexChanged.connect(self._on_scene_render_mode_changed)

        self._scene_fog_enabled = QCheckBox("Enable Fog")
        self._scene_fog_enabled.toggled.connect(self._on_scene_fog_toggled)

        fog_row = QWidget()
        fog_row_layout = QHBoxLayout(fog_row)
        fog_row_layout.setContentsMargins(0, 0, 0, 0)
        fog_row_layout.setSpacing(4)
        self._scene_fog_start = QDoubleSpinBox()
        self._scene_fog_end = QDoubleSpinBox()
        for sb in (self._scene_fog_start, self._scene_fog_end):
            sb.setRange(0.0, 1_000_000.0)
            sb.setDecimals(1)
            sb.setSingleStep(10.0)
            sb.setEnabled(False)
            fog_row_layout.addWidget(sb)
        # Set initial values *before* connecting valueChanged — this group is
        # built before _build_table(), so a triggered handler here would hit
        # self._table before it exists.
        self._scene_fog_start.setValue(20.0)
        self._scene_fog_end.setValue(200.0)
        self._scene_fog_start.valueChanged.connect(self._on_scene_fog_changed)
        self._scene_fog_end.valueChanged.connect(self._on_scene_fog_changed)
        self._scene_fog_start.setToolTip("Distance where fog begins")
        self._scene_fog_end.setToolTip("Distance where fog is fully opaque")

        scene_form.addRow("Background:", bg_row)
        scene_form.addRow("Render Mode:", self._scene_render_mode)
        scene_form.addRow("", self._scene_fog_enabled)
        scene_form.addRow("Fog Start/End:", fog_row)

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

        self._cb_save_tag = QCheckBox("Also Save Tag File")
        self._cb_save_tag.setChecked(True)
        self._cb_save_tag.setToolTip(
            "When checked, Save/Save As also writes a companion gv_tag.csv-style\n"
            "file (id,table_id,record_id,title) for any node with tag text or a link.\n"
            "Only possible when the node file's name ends in 'node' (e.g. gv_node.csv).\n"
            "The K key always saves both, regardless of this checkbox."
        )
        stats_layout.addWidget(self._cb_save_tag)

        # --- Create group ---
        create_grp = QGroupBox("Create")
        create_layout = QVBoxLayout(create_grp)

        self._btn_new_node = QPushButton("New Node")
        self._btn_new_node.setToolTip(
            "Create a new object using the defaults below, at the world origin  [N]\n"
            "Each press increments X by 10 units.  If a child-level\n"
            "node is selected, a child is added instead."
        )
        self._btn_new_node.clicked.connect(self._on_create_node)

        self._btn_new_child = QPushButton("New Child")
        self._btn_new_child.setToolTip(
            "Create a child object using the defaults below, under the\n"
            "selected node  [Shift+N]\n"
            "Requires exactly one node to be selected."
        )
        self._btn_new_child.clicked.connect(self._create_child_node)

        create_layout.addWidget(self._btn_new_node)
        create_layout.addWidget(self._btn_new_child)

        # --- New Object Defaults: geometry/topology/scale/color applied to
        # nodes created via New Node, New Child, N, and Shift+N. Position and
        # rotation for new nodes stay as the existing auto-placed defaults.
        new_defaults_form = QFormLayout()
        new_defaults_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self._new_geo = QComboBox()
        for geo_id in range(GEO_COUNT):
            self._new_geo.addItem(GEO_NAMES[geo_id], geo_id)
        self._new_geo.setCurrentIndex(max(self._new_geo.findData(GEO_OCTA), 0))

        self._new_topo = QComboBox()
        for topo_id in range(TOPO_COUNT):
            self._new_topo.addItem(TOPO_NAMES.get(topo_id, f"Topology {topo_id}"), topo_id)
        self._new_topo.setCurrentIndex(max(self._new_topo.findData(TOPO_POINT), 0))

        new_scale_widget = QWidget()
        new_scale_layout = QHBoxLayout(new_scale_widget)
        new_scale_layout.setContentsMargins(0, 0, 0, 0)
        new_scale_layout.setSpacing(4)
        self._new_scale_x = QDoubleSpinBox()
        self._new_scale_y = QDoubleSpinBox()
        self._new_scale_z = QDoubleSpinBox()
        for sb in (self._new_scale_x, self._new_scale_y, self._new_scale_z):
            sb.setRange(0.001, 10_000.0)
            sb.setDecimals(3)
            sb.setSingleStep(0.1)
            sb.setValue(1.0)
            sb.valueChanged.connect(self._on_new_scale_changed)
            new_scale_layout.addWidget(sb)

        self._new_scale_lock = QCheckBox("Lock X/Y/Z together")
        self._new_scale_lock.setChecked(True)
        self._new_scale_lock.setToolTip(
            "When checked, editing one scale axis sets all three to the same value."
        )

        self._new_obj_color = QColor(200, 200, 200, 255)
        self._new_color_btn = QPushButton()
        self._new_color_btn.setFixedHeight(24)
        self._new_color_btn.clicked.connect(self._on_new_color)
        self._set_color_btn(self._new_color_btn, 200, 200, 200, 255)

        new_defaults_form.addRow("Geometry:", self._new_geo)
        new_defaults_form.addRow("Topology:", self._new_topo)
        new_defaults_form.addRow("Scale (X,Y,Z):", new_scale_widget)
        new_defaults_form.addRow("", self._new_scale_lock)
        new_defaults_form.addRow("Color:", self._new_color_btn)

        create_layout.addWidget(QLabel("New Object Defaults:"))
        create_layout.addLayout(new_defaults_form)

        # --- Delete group ---
        delete_grp = QGroupBox("Delete")
        delete_layout = QVBoxLayout(delete_grp)

        self._btn_delete = QPushButton("Delete Selected Objects")
        self._btn_delete.setToolTip(
            "Delete the selected node(s)  [Delete/Backspace]\n"
            "Any children of a deleted node are deleted too — children are\n"
            "never reparented, since there's no well-defined place to put them."
        )
        self._btn_delete.setEnabled(False)   # enabled once there's a selection
        self._btn_delete.clicked.connect(self._delete_selected)

        delete_layout.addWidget(self._btn_delete)

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

        self._insp_rotation_mode = QComboBox()
        self._insp_rotation_mode.addItem("Euler XYZ", ROTATION_MODE_EULER_XYZ)
        self._insp_rotation_mode.addItem("Heading/Tilt/Roll (ANTz)", ROTATION_MODE_HEADING_TILT_ROLL)
        self._insp_rotation_mode.setToolTip(
            "Euler XYZ: rotate_x/y/z each rotate about their own named axis "
            "(intuitive for hand-posing).\n"
            "Heading/Tilt/Roll: ANTz's legacy convention — rotate_y and "
            "rotate_z both rotate about z, with rotate_x in between. Lets a "
            "node spin in place around wherever it's aimed using only "
            "rotate_z, useful for outward-facing children on Sphere/Torus."
        )
        self._insp_rotation_mode.currentIndexChanged.connect(self._on_insp_rotation_mode_changed)

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

        # --- Rate widgets (ANTz translate_rate/rotate_rate/scale_rate) ---
        # Per-cycle velocities added to position/rotation/scale every cycle
        # (nominally 60 cycles/second) by the viewport's continuous animation
        # tick. A script-authored node CSV can set these with no GUI needed;
        # this just exposes the same fields for hand-tuning.
        translate_rate_widget = QWidget()
        translate_rate_layout = QHBoxLayout(translate_rate_widget)
        translate_rate_layout.setContentsMargins(0, 0, 0, 0)
        translate_rate_layout.setSpacing(4)
        self._insp_translate_rate_x = QDoubleSpinBox()
        self._insp_translate_rate_y = QDoubleSpinBox()
        self._insp_translate_rate_z = QDoubleSpinBox()
        for sb in (self._insp_translate_rate_x, self._insp_translate_rate_y, self._insp_translate_rate_z):
            sb.setRange(-1_000_000.0, 1_000_000.0)
            sb.setDecimals(4)
            sb.setSingleStep(0.01)
            sb.setToolTip(
                "Position delta applied every cycle (ANTz convention: nominally "
                "60 cycles/second). Nonzero values keep this node moving "
                "continuously in the viewport."
            )
            sb.valueChanged.connect(self._on_insp_translate_rate_changed)
            translate_rate_layout.addWidget(sb)

        rotate_rate_widget = QWidget()
        rotate_rate_layout = QHBoxLayout(rotate_rate_widget)
        rotate_rate_layout.setContentsMargins(0, 0, 0, 0)
        rotate_rate_layout.setSpacing(4)
        self._insp_rotate_rate_x = QDoubleSpinBox()
        self._insp_rotate_rate_y = QDoubleSpinBox()
        self._insp_rotate_rate_z = QDoubleSpinBox()
        for sb in (self._insp_rotate_rate_x, self._insp_rotate_rate_y, self._insp_rotate_rate_z):
            sb.setRange(-3600.0, 3600.0)
            sb.setDecimals(4)
            sb.setSingleStep(0.01)
            sb.setToolTip(
                "Degrees added every cycle (nominally 60 cycles/second). "
                "Spins this node continuously about the corresponding axis."
            )
            sb.valueChanged.connect(self._on_insp_rotate_rate_changed)
            rotate_rate_layout.addWidget(sb)

        scale_rate_widget = QWidget()
        scale_rate_layout = QHBoxLayout(scale_rate_widget)
        scale_rate_layout.setContentsMargins(0, 0, 0, 0)
        scale_rate_layout.setSpacing(4)
        self._insp_scale_rate_x = QDoubleSpinBox()
        self._insp_scale_rate_y = QDoubleSpinBox()
        self._insp_scale_rate_z = QDoubleSpinBox()
        for sb in (self._insp_scale_rate_x, self._insp_scale_rate_y, self._insp_scale_rate_z):
            sb.setRange(-10_000.0, 10_000.0)
            sb.setDecimals(4)
            sb.setSingleStep(0.001)
            sb.setToolTip(
                "Scale added every cycle (nominally 60 cycles/second). Rarely "
                "useful at nonzero values — the glyph will continuously grow "
                "or shrink without bound."
            )
            sb.valueChanged.connect(self._on_insp_scale_rate_changed)
            scale_rate_layout.addWidget(sb)

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

        self._insp_subspace = QComboBox()
        for face_id, face_name in enumerate(CUBE_FACE_NAMES):
            self._insp_subspace.addItem(f"{face_id}: {face_name}", face_id)
        self._insp_subspace.setToolTip(
            "Which cube face this node sits on, when its PARENT uses the Cube "
            "or Zcube topology (ignored otherwise)."
        )
        self._insp_subspace.currentIndexChanged.connect(self._on_insp_subspace_changed)

        self._insp_color_btn = QPushButton()
        self._insp_color_btn.setFixedHeight(24)
        self._insp_color_btn.clicked.connect(self._on_insp_color)

        self._insp_texture_id = QDoubleSpinBox()
        self._insp_texture_id.setDecimals(0)
        self._insp_texture_id.setRange(0, 9999)
        self._insp_texture_id.setSingleStep(1)
        self._insp_texture_id.setToolTip(
            "ANTz texture_id: 0 = none, 1 = first image in texture folder "
            "(sorted alphanumerically), 2 = second, etc."
        )
        self._insp_texture_id.valueChanged.connect(self._on_insp_texture_id_changed)

        self._insp_text = QLineEdit()
        self._insp_text.setPlaceholderText("Tag label text…")
        self._insp_text.setToolTip("Text label shown near node in 3D view  [T toggles display]")
        self._insp_text.textChanged.connect(self._on_insp_text_changed)

        self._insp_link = QLineEdit()
        self._insp_link.setPlaceholderText("URL or file path  (U key opens)")
        self._insp_link.setToolTip(
            "URL or file path opened when U is pressed with this node selected.\n"
            "Supports http://, https://, and local file paths."
        )
        self._insp_link.textChanged.connect(self._on_insp_link_changed)

        insp_layout.addRow("ID:",       self._insp_id)
        insp_layout.addRow("Type:",     self._insp_type)
        insp_layout.addRow("Parent:",   self._insp_parent)
        insp_layout.addRow("Pos (X,Y,Z):", pos_widget)
        insp_layout.addRow("Translate Rate:", translate_rate_widget)
        insp_layout.addRow("Rotate (X,Y,Z):", rot_widget)
        insp_layout.addRow("Rotate Rate:", rotate_rate_widget)
        insp_layout.addRow("Rotation Mode:", self._insp_rotation_mode)
        insp_layout.addRow("Scale (X,Y,Z):", scale_widget)
        insp_layout.addRow("Scale Rate:", scale_rate_widget)
        insp_layout.addRow("", self._insp_scale_lock)
        insp_layout.addRow("Geometry:", self._insp_geo)
        insp_layout.addRow("Topology:", self._insp_topo)
        insp_layout.addRow("Facet:",    self._insp_subspace)
        insp_layout.addRow("Ratio:",    self._insp_ratio)
        insp_layout.addRow("Texture ID:", self._insp_texture_id)
        insp_layout.addRow("Color:",    self._insp_color_btn)
        insp_layout.addRow("Tag Text:", self._insp_text)
        insp_layout.addRow("Link:",     self._insp_link)

        # --- Channels / playback group ---
        self._ch_grp = QGroupBox("Channels")
        self._ch_grp.setVisible(False)
        ch_layout = QVBoxLayout(self._ch_grp)
        ch_layout.setSpacing(4)

        self._ch_frame_label = QLabel("Frame: 0 / 0")
        self._ch_slider = QSlider(Qt.Orientation.Horizontal)
        self._ch_slider.setRange(0, 0)
        self._ch_slider.valueChanged.connect(self._on_ch_slider)

        ch_btn_row = QWidget()
        ch_btn_layout = QHBoxLayout(ch_btn_row)
        ch_btn_layout.setContentsMargins(0, 0, 0, 0)
        ch_btn_layout.setSpacing(4)
        self._ch_play_btn = QPushButton("▶")
        self._ch_stop_btn = QPushButton("■")
        self._ch_play_btn.setFixedWidth(36)
        self._ch_stop_btn.setFixedWidth(36)
        self._ch_play_btn.setToolTip("Play / Pause channel animation")
        self._ch_stop_btn.setToolTip("Stop and reset to frame 0")
        self._ch_play_btn.clicked.connect(self._ch_toggle_play)
        self._ch_stop_btn.clicked.connect(self._ch_stop)
        ch_btn_layout.addWidget(self._ch_play_btn)
        ch_btn_layout.addWidget(self._ch_stop_btn)
        ch_btn_layout.addStretch()

        ch_fps_row = QWidget()
        ch_fps_layout = QHBoxLayout(ch_fps_row)
        ch_fps_layout.setContentsMargins(0, 0, 0, 0)
        ch_fps_layout.setSpacing(4)
        ch_fps_layout.addWidget(QLabel("FPS:"))
        self._ch_fps = QDoubleSpinBox()
        self._ch_fps.setRange(1, 120)
        self._ch_fps.setValue(30)
        self._ch_fps.setDecimals(0)
        self._ch_fps.setFixedWidth(60)
        self._ch_fps.setToolTip("Playback speed in frames per second")
        self._ch_fps.valueChanged.connect(self._ch_update_fps)
        ch_fps_layout.addWidget(self._ch_fps)
        ch_fps_layout.addStretch()

        self._ch_loop = QCheckBox("Loop")
        self._ch_loop.setChecked(True)

        ch_layout.addWidget(self._ch_frame_label)
        ch_layout.addWidget(self._ch_slider)
        ch_layout.addWidget(ch_btn_row)
        ch_layout.addWidget(ch_fps_row)
        ch_layout.addWidget(self._ch_loop)

        layout.addWidget(disp)
        layout.addWidget(scale_grp)
        layout.addWidget(scene_grp)
        layout.addWidget(stats_grp)
        layout.addWidget(create_grp)
        layout.addWidget(delete_grp)
        layout.addWidget(sel_grp)
        layout.addWidget(self._insp_grp)
        layout.addWidget(self._ch_grp)
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
        self._fps_label = QLabel("-- fps")
        self._fps_label.setMinimumWidth(70)
        self._fps_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        sb.addPermanentWidget(self._fps_label)

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
            self._ch_stop()
            self.nodes = load_node_csv(path)
            self._current_path = path
            self._current_tag_path = None
            self._path_is_stamped = False
            self._save_act.setEnabled(True)
            self._viewport.set_nodes(self.nodes)
            self._table.set_nodes(self.nodes)
            self._update_stats(Path(path).name)
            self._update_sel_values()
            self._refresh_scene_settings()
            msg = f"Loaded {len(self.nodes)} nodes from {Path(path).name}"
            # Auto-load textures/videos/GIFs from a media/ folder next to the CSV.
            auto_tex = Path(path).parent / "media"
            if auto_tex.is_dir():
                self._apply_texture_folder(auto_tex, silent=True)
                msg += f" | textures: {self._viewport.texture_count} from …/media/"
            ch_msg = self._ch_load_from_csv(path)
            if ch_msg:
                msg += f" | {ch_msg}"
            self.statusBar().showMessage(msg)
        except Exception as exc:
            self.statusBar().showMessage(f"Error: {exc}")

    def _browse_texture_folder(self):
        start = (
            str(self._viewport.texture_folder)
            if self._viewport.texture_folder
            else str(Path.home())
        )
        folder = QFileDialog.getExistingDirectory(
            self, "Select Texture Folder", start
        )
        if folder:
            self._apply_texture_folder(Path(folder))

    def _apply_texture_folder(self, folder: Path, silent: bool = False):
        try:
            count = self._viewport.load_texture_folder(folder)
            label = f"{count} texture(s) from {folder.name}/" if count else f"0 textures found in {folder.name}/"
            self._lbl_tex.setText(label)
            if not silent:
                self.statusBar().showMessage(f"Loaded {count} texture(s) from {folder}")
        except Exception as exc:
            self._lbl_tex.setText("Texture load failed")
            self.statusBar().showMessage(f"Texture error: {exc}")
        self._refresh_audio_combo()

    def _import_mesh_file(self):
        """Meshes > Import Mesh File…: load an OBJ/STL/etc. as a GEO_MESH
        shape. Mirrors Paste's target rule — applies to the single selected
        node if there is one, else creates a new root node (see
        _create_root_node)."""
        if len(self._selected_nodes) > 1:
            self.statusBar().showMessage("Select exactly one node (or none) as the import target.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Mesh File", str(Path.home()),
            "Mesh Files (*.obj *.stl *.ply *.glb *.gltf)",
        )
        if not path:
            return
        try:
            mesh_id = self._viewport.load_mesh_file(path)
        except Exception as exc:
            self.statusBar().showMessage(f"Mesh import failed: {exc}")
            return
        name = self._viewport.mesh_name(mesh_id)

        if len(self._selected_nodes) == 1:
            node = self._selected_nodes[0]
            node.geometry = GEO_MESH
            node.mesh_id = mesh_id
            self._table.refresh_node(node.id)
            self._update_sel_values()
            self._viewport.scene_invalidate()
            self.statusBar().showMessage(f"Assigned mesh '{name}' (id {mesh_id}) to node {node.id}.")
            return

        next_x = self._next_root_x()
        new_id = max((n.id for n in self.nodes), default=0) + 1
        self._add_node_to_scene(Node(
            id=new_id, type=5, parent_id=0, branch_level=0,
            translate_x=next_x, translate_y=0.0, translate_z=0.0,
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=5.0, scale_y=5.0, scale_z=5.0,
            color_r=200, color_g=200, color_b=200, color_a=255,
            geometry=GEO_MESH, hide=0, topo=0, mesh_id=mesh_id,
        ))
        self.statusBar().showMessage(f"Imported mesh '{name}' (id {mesh_id}) as new node {new_id}.")

    def _clear_textures(self):
        self._viewport.clear_textures()
        self._lbl_tex.setText("No textures loaded")
        self.statusBar().showMessage("Textures cleared.")
        self._refresh_audio_combo()

    def _refresh_audio_combo(self):
        """Repopulate the audio-track dropdown from the videos currently loaded
        as textures.  Defaults to 'All Audio Tracks' (every video heard at once)."""
        tracks = self._viewport.list_audio_tracks()
        self._audio_combo.blockSignals(True)
        self._audio_combo.clear()
        self._audio_combo.addItem("All Audio Tracks", None)
        for texture_id, name in tracks:
            self._audio_combo.addItem(f"Only: {name}", texture_id)
        self._audio_combo.setCurrentIndex(0)
        self._audio_combo.setEnabled(len(tracks) > 1)
        self._audio_combo.blockSignals(False)

    def _on_audio_track_selected(self, index: int):
        texture_id = self._audio_combo.itemData(index)
        self._viewport.set_audio_solo(texture_id)

    def _save_csv(self):
        """Ctrl+S — overwrite the currently open (already-timestamped) file.
        If the open file has no timestamp yet (freshly Opened), silently
        stamp it first — this writes a new file rather than overwriting the
        original un-timestamped one, and that new path becomes current."""
        if not self._current_path:
            self._save_csv_as()
            return
        if not self._path_is_stamped:
            self._restamp_current_path()
        self._write_node_and_tag(self._current_path, self._current_tag_path)

    def _save_csv_as(self):
        """Ctrl+Shift+S — pick a base name/location, then save under a fresh
        YYYYMMDDHHMMSS-stamped name. Every subsequent Ctrl+S overwrites this
        same stamped file; picking Save As again generates a new stamp."""
        start = self._current_path or str(Path.home() / "gv_node.csv")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Node CSV",
            start,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return
        self._current_path = path
        self._restamp_current_path()
        self._write_node_and_tag(self._current_path, self._current_tag_path)
        self._save_act.setEnabled(True)

    def _restamp_current_path(self):
        """Generate a fresh timestamp for self._current_path (and its tag
        companion), updating both current-path fields and the file label."""
        node_path, tag_path = stamp_node_and_tag_paths(self._current_path)
        self._current_path = str(node_path)
        self._current_tag_path = str(tag_path) if tag_path else None
        self._path_is_stamped = True
        self._lbl_file.setText(f"File: {Path(self._current_path).name}")

    def _quick_save(self):
        """K — fully automatic save, no dialog: writes a fresh-stamped node
        CSV and tag CSV (always both, regardless of the tag checkbox) next
        to the executable, under the gv_node/gv_tag base names. Independent
        of whatever file is currently open via Open/Save As."""
        node_path, tag_path = stamp_node_and_tag_paths(_app_dir() / "gv_node.csv")
        try:
            save_node_csv(self.nodes, str(node_path))
            save_tag_csv(self.nodes, str(tag_path))
            self.statusBar().showMessage(
                f"Quick-saved {len(self.nodes)} nodes to {node_path.name} (+ {tag_path.name})"
            )
        except Exception as exc:
            self.statusBar().showMessage(f"Quick-save error: {exc}")

    def _save_scene_png(self):
        """F12 — save the current viewport as a PNG image."""
        start = str(Path(self._current_path).with_suffix(".png")) if self._current_path \
            else str(Path.home() / "scene.png")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Scene as PNG",
            start,
            "PNG Files (*.png);;All Files (*)",
        )
        if not path:
            return
        try:
            self._viewport.save_screenshot(path)
            self.statusBar().showMessage(f"Saved scene to {Path(path).name}")
        except Exception as exc:
            self.statusBar().showMessage(f"Screenshot error: {exc}")

    def _write_node_and_tag(self, node_path: str, tag_path: str | None):
        try:
            save_node_csv(self.nodes, node_path)
            msg = f"Saved {len(self.nodes)} nodes to {Path(node_path).name}"
            if self._cb_save_tag.isChecked():
                if tag_path:
                    save_tag_csv(self.nodes, tag_path)
                    msg += f" (+ tags to {Path(tag_path).name})"
                else:
                    msg += " (tag file skipped: name doesn't end in 'node')"
            self.statusBar().showMessage(msg)
        except Exception as exc:
            self.statusBar().showMessage(f"Save error: {exc}")

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

    def _set_tags(self, checked: bool):
        self._viewport.show_tags = checked
        self._cb_tags.setChecked(checked)
        self._tags_act.setChecked(checked)
        self._viewport.update()

    def _on_tag_toggled(self, checked: bool):
        """Sync UI when T key toggles tags inside the viewport."""
        self._cb_tags.setChecked(checked)
        self._tags_act.setChecked(checked)

    def _set_tags_selected_only(self, checked: bool):
        self._viewport.show_tags_selected_only = checked
        self._viewport.update()

    def _on_open_link(self):
        """U key: open the selected node's link in the default browser/app."""
        if len(self._selected_nodes) != 1:
            return
        link = self._selected_nodes[0].link.strip()
        if not link:
            self.statusBar().showMessage("Node has no link.")
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if link.startswith(('http://', 'https://', 'ftp://', 'www.')):
            url = QUrl(link if not link.startswith('www.') else 'https://' + link)
        else:
            url = QUrl.fromLocalFile(link)
        QDesktopServices.openUrl(url)
        self.statusBar().showMessage(f"Opening: {link}")

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
        """Repopulate the value combo for the current Select By criterion.

        Called both when the criterion changes and whenever an edit could have
        changed which geometry/topology/branch-level values exist in the scene
        (e.g. changing selected nodes' geometry) — otherwise the combo keeps
        showing values that no longer match any node, or hides new ones."""
        criterion = self._sel_criterion.currentText()
        current_data = self._sel_value.currentData()
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
        if current_data is not None:
            idx = self._sel_value.findData(current_data)
            if idx >= 0:
                self._sel_value.setCurrentIndex(idx)
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

        has_selection = bool(self._selected_nodes)
        for btn in self._mode_buttons.values():
            btn.setEnabled(has_selection)
        self._btn_delete.setEnabled(has_selection)
        if not has_selection and self._gizmo_mode is not None:
            self._set_gizmo_mode(None)

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
            (self._insp_texture_id, node.texture_id),
            (self._insp_translate_rate_x, node.translate_rate_x),
            (self._insp_translate_rate_y, node.translate_rate_y),
            (self._insp_translate_rate_z, node.translate_rate_z),
            (self._insp_rotate_rate_x, node.rotate_rate_x),
            (self._insp_rotate_rate_y, node.rotate_rate_y),
            (self._insp_rotate_rate_z, node.rotate_rate_z),
            (self._insp_scale_rate_x, node.scale_rate_x),
            (self._insp_scale_rate_y, node.scale_rate_y),
            (self._insp_scale_rate_z, node.scale_rate_z),
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

        idx = self._insp_subspace.findData(node.subspace)
        self._insp_subspace.blockSignals(True)
        self._insp_subspace.setCurrentIndex(max(idx, 0))
        self._insp_subspace.blockSignals(False)

        idx = self._insp_rotation_mode.findData(node.rotation_mode)
        self._insp_rotation_mode.blockSignals(True)
        self._insp_rotation_mode.setCurrentIndex(max(idx, 0))
        self._insp_rotation_mode.blockSignals(False)

        self._refresh_color_btn(node)

        self._insp_text.blockSignals(True)
        self._insp_text.setText(node.text)
        self._insp_text.blockSignals(False)
        self._insp_link.blockSignals(True)
        self._insp_link.setText(node.link)
        self._insp_link.blockSignals(False)

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
            (self._insp_texture_id, primary.texture_id),
            (self._insp_translate_rate_x, primary.translate_rate_x),
            (self._insp_translate_rate_y, primary.translate_rate_y),
            (self._insp_translate_rate_z, primary.translate_rate_z),
            (self._insp_rotate_rate_x, primary.rotate_rate_x),
            (self._insp_rotate_rate_y, primary.rotate_rate_y),
            (self._insp_rotate_rate_z, primary.rotate_rate_z),
            (self._insp_scale_rate_x, primary.scale_rate_x),
            (self._insp_scale_rate_y, primary.scale_rate_y),
            (self._insp_scale_rate_z, primary.scale_rate_z),
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

        idx = self._insp_subspace.findData(primary.subspace)
        self._insp_subspace.blockSignals(True)
        self._insp_subspace.setCurrentIndex(max(idx, 0))
        self._insp_subspace.blockSignals(False)

        idx = self._insp_rotation_mode.findData(primary.rotation_mode)
        self._insp_rotation_mode.blockSignals(True)
        self._insp_rotation_mode.setCurrentIndex(max(idx, 0))
        self._insp_rotation_mode.blockSignals(False)

        self._refresh_color_btn(primary)

        self._insp_text.blockSignals(True)
        self._insp_text.setText(primary.text)
        self._insp_text.blockSignals(False)
        self._insp_link.blockSignals(True)
        self._insp_link.setText(primary.link)
        self._insp_link.blockSignals(False)

        # Anchor for delta-based pos/rot edits
        self._anchor_pos = (primary.translate_x, primary.translate_y, primary.translate_z)
        self._anchor_rot = (primary.rotate_x, primary.rotate_y, primary.rotate_z)

    def _set_color_btn(self, btn: QPushButton, r: int, g: int, b: int, a: int):
        btn.setStyleSheet(
            f"background-color: rgba({r},{g},{b},{a}); border: 1px solid #666;"
        )
        btn.setText(f"#{r:02X}{g:02X}{b:02X}")

    def _refresh_color_btn(self, node: Node):
        self._set_color_btn(self._insp_color_btn, node.color_r, node.color_g, node.color_b, node.color_a)

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
        self._viewport.scene_invalidate()

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
        self._viewport.scene_invalidate()

    def _on_insp_geo_changed(self, _idx: int):
        if not self._selected_nodes:
            return
        geo = self._insp_geo.currentData()
        for node in self._selected_nodes:
            node.geometry = geo
            self._table.refresh_node(node.id)
        self._update_sel_values()
        self._viewport.scene_invalidate()

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
        self._viewport.scene_invalidate()

    def _on_insp_ratio_changed(self, value: float):
        if not self._selected_nodes:
            return
        for node in self._selected_nodes:
            node.ratio = value
            self._table.refresh_node(node.id)
        self._viewport.scene_invalidate()

    def _on_insp_texture_id_changed(self, value: float):
        if not self._selected_nodes:
            return
        tex_id = int(value)
        for node in self._selected_nodes:
            node.texture_id = tex_id
            self._table.refresh_node(node.id)
        self._viewport.scene_invalidate()

    def _on_insp_translate_rate_changed(self, _value: float):
        if not self._selected_nodes:
            return
        rx = self._insp_translate_rate_x.value()
        ry = self._insp_translate_rate_y.value()
        rz = self._insp_translate_rate_z.value()
        for node in self._selected_nodes:
            node.translate_rate_x = rx
            node.translate_rate_y = ry
            node.translate_rate_z = rz
            self._table.refresh_node(node.id)
        self._viewport.refresh_animation_state()
        self._viewport.scene_invalidate()

    def _on_insp_rotate_rate_changed(self, _value: float):
        if not self._selected_nodes:
            return
        rx = self._insp_rotate_rate_x.value()
        ry = self._insp_rotate_rate_y.value()
        rz = self._insp_rotate_rate_z.value()
        for node in self._selected_nodes:
            node.rotate_rate_x = rx
            node.rotate_rate_y = ry
            node.rotate_rate_z = rz
            self._table.refresh_node(node.id)
        self._viewport.refresh_animation_state()
        self._viewport.scene_invalidate()

    def _on_insp_scale_rate_changed(self, _value: float):
        if not self._selected_nodes:
            return
        rx = self._insp_scale_rate_x.value()
        ry = self._insp_scale_rate_y.value()
        rz = self._insp_scale_rate_z.value()
        for node in self._selected_nodes:
            node.scale_rate_x = rx
            node.scale_rate_y = ry
            node.scale_rate_z = rz
            self._table.refresh_node(node.id)
        self._viewport.refresh_animation_state()
        self._viewport.scene_invalidate()

    def _on_insp_text_changed(self, value: str):
        if not self._selected_nodes:
            return
        for node in self._selected_nodes:
            node.text = value
        self._viewport.update()

    def _on_insp_link_changed(self, value: str):
        if not self._selected_nodes:
            return
        for node in self._selected_nodes:
            node.link = value

    def _on_insp_topo_changed(self, _idx: int):
        if not self._selected_nodes:
            return
        topo = self._insp_topo.currentData()
        for node in self._selected_nodes:
            node.topo = topo
            self._table.refresh_node(node.id)
        self._update_sel_values()
        self._viewport.scene_invalidate()

    def _on_insp_subspace_changed(self, _idx: int):
        if not self._selected_nodes:
            return
        subspace = self._insp_subspace.currentData()
        for node in self._selected_nodes:
            node.subspace = subspace
            self._table.refresh_node(node.id)
        self._viewport.scene_invalidate()

    def _on_insp_rotation_mode_changed(self, _idx: int):
        if not self._selected_nodes:
            return
        rotation_mode = self._insp_rotation_mode.currentData()
        for node in self._selected_nodes:
            node.rotation_mode = rotation_mode
            self._table.refresh_node(node.id)
        self._viewport.scene_invalidate()

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
        self._viewport.scene_invalidate()

    # --- New Object Defaults change handlers ---

    def _on_new_scale_changed(self, value: float):
        if not self._new_scale_lock.isChecked():
            return
        sender = self.sender()
        for sb in (self._new_scale_x, self._new_scale_y, self._new_scale_z):
            if sb is not sender:
                sb.blockSignals(True)
                sb.setValue(value)
                sb.blockSignals(False)

    def _on_new_color(self):
        color = QColorDialog.getColor(
            self._new_obj_color, self, "New Object Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not color.isValid():
            return
        self._new_obj_color = color
        self._set_color_btn(self._new_color_btn, color.red(), color.green(), color.blue(), color.alpha())

    # --- Scene Settings (World node) handlers ---

    def _ensure_world_node(self) -> Node:
        """Return the scene's World node (type=0), synthesizing one with
        default settings if the file doesn't have one yet. The new node is
        appended (not written to disk until save_node_csv sees a non-default
        value, same asymmetric-default rule as rotation_mode).

        id is allocated as max(existing ids) + 1, like _create_root_node —
        NOT 0, since parent_id=0 is the universal "attached to grid" sentinel
        (see topology.py's by_id.get(node.parent_id)); a World node at id=0
        would silently become the parent of every root-level node in the file.
        """
        world_nodes = [n for n in self.nodes if n.type == NODE_TYPE_WORLD]
        if world_nodes:
            return min(world_nodes, key=lambda n: n.id)
        r, g, b = WORLD_DEFAULT_BG_RGB
        new_id = max((n.id for n in self.nodes), default=0) + 1
        node = Node(
            id=new_id, type=NODE_TYPE_WORLD, parent_id=0, branch_level=0,
            translate_x=0.0, translate_y=0.0, translate_z=0.0,
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=1.0, scale_y=1.0, scale_z=1.0,
            color_r=r, color_g=g, color_b=b, color_a=255,
            geometry=0, hide=0, topo=0,
        )
        self.nodes.append(node)
        self._viewport.register_node(node)
        self._table.append_node(node)
        self._update_stats()
        return node

    def _refresh_scene_settings(self):
        """Sync the Scene Settings panel from the current World node (or
        defaults, if none exists yet) — called after loading a file."""
        world_nodes = [n for n in self.nodes if n.type == NODE_TYPE_WORLD]
        world = min(world_nodes, key=lambda n: n.id) if world_nodes else None
        r, g, b = (world.color_r, world.color_g, world.color_b) if world else WORLD_DEFAULT_BG_RGB
        mode = world.render_mode if world else RENDER_MODE_NORMAL
        fog_on = bool(world.fog_enabled) if world else False
        fog_start = world.fog_start if world and world.fog_start else 20.0
        fog_end = world.fog_end if world and world.fog_end else 200.0

        self._set_color_btn(self._scene_bg_btn, r, g, b, 255)
        idx = self._scene_render_mode.findData(mode)
        self._scene_render_mode.blockSignals(True)
        self._scene_render_mode.setCurrentIndex(max(idx, 0))
        self._scene_render_mode.blockSignals(False)
        self._scene_fog_enabled.blockSignals(True)
        self._scene_fog_enabled.setChecked(fog_on)
        self._scene_fog_enabled.blockSignals(False)
        for sb, value in ((self._scene_fog_start, fog_start), (self._scene_fog_end, fog_end)):
            sb.blockSignals(True)
            sb.setValue(value)
            sb.setEnabled(fog_on)
            sb.blockSignals(False)

    def _on_scene_bg_color(self):
        world = self._ensure_world_node()
        initial = QColor(world.color_r, world.color_g, world.color_b)
        color = QColorDialog.getColor(initial, self, "Background Color")
        if not color.isValid():
            return
        world.color_r, world.color_g, world.color_b = color.red(), color.green(), color.blue()
        self._set_color_btn(self._scene_bg_btn, color.red(), color.green(), color.blue(), 255)
        self._table.refresh_node(world.id)
        self._viewport.update()

    def _on_scene_bg_toggle_bw(self):
        """Mirrors ANTz's 'B' hotkey: flip background between black and white."""
        world = self._ensure_world_node()
        is_white = world.color_r >= 128
        rgb = 0 if is_white else 255
        world.color_r = world.color_g = world.color_b = rgb
        self._set_color_btn(self._scene_bg_btn, rgb, rgb, rgb, 255)
        self._table.refresh_node(world.id)
        self._viewport.update()

    def _on_scene_render_mode_cycle(self):
        """Mirrors ANTz's '8' hotkey: cycle to the next render mode."""
        next_index = (self._scene_render_mode.currentIndex() + 1) % self._scene_render_mode.count()
        self._scene_render_mode.setCurrentIndex(next_index)   # triggers _on_scene_render_mode_changed

    def _on_scene_render_mode_changed(self, _index: int):
        mode = self._scene_render_mode.currentData()
        if mode is None:
            return
        world = self._ensure_world_node()
        world.render_mode = mode
        self._table.refresh_node(world.id)
        self._viewport.update()

    def _on_scene_fog_toggled(self, checked: bool):
        world = self._ensure_world_node()
        world.fog_enabled = 1 if checked else 0
        self._scene_fog_start.setEnabled(checked)
        self._scene_fog_end.setEnabled(checked)
        self._table.refresh_node(world.id)
        self._viewport.update()

    def _on_scene_fog_changed(self, _value: float):
        world = self._ensure_world_node()
        world.fog_start = self._scene_fog_start.value()
        world.fog_end = self._scene_fog_end.value()
        self._table.refresh_node(world.id)
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

    def _on_fps_updated(self, fps: float):
        self._fps_label.setText(f"{fps:.1f} fps")

    def _on_draw_limit_changed(self, visible: int, total: int):
        self._lbl_visible.setText(f"Visible: {visible}")
        if visible >= total:
            self.statusBar().showMessage(f"All {total} nodes visible  (Shift+\\ to restore)")
        else:
            self.statusBar().showMessage(
                f"Draw limit: {visible} / {total} nodes  (\\ halve · Shift+\\ double)"
            )

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

    def _new_object_defaults(self):
        """Current geometry/topology/scale/color from the New Object Defaults
        panel, applied to every node created via New Node/New Child/N/Shift+N."""
        return (
            self._new_geo.currentData(),
            self._new_topo.currentData(),
            self._new_scale_x.value(),
            self._new_scale_y.value(),
            self._new_scale_z.value(),
            self._new_obj_color,
        )

    def _next_root_x(self) -> float:
        """Next translate_x for a new root-level (branch_level 0) node,
        stepping +10 along X from the last one. Shared by _create_root_node
        and _paste_clipboard's no-selection case."""
        root_glyphs = [
            n for n in self.nodes
            if n.type not in NON_VISUAL_TYPES and n.branch_level == 0
        ]
        return (max(n.translate_x for n in root_glyphs) + 10.0) if root_glyphs else 0.0

    def _create_root_node(self):
        """Create a new root-level node using the New Object Defaults, stepping +10 along X from the last one."""
        next_x = self._next_root_x()
        new_id = max((n.id for n in self.nodes), default=0) + 1
        geo, topo, sx, sy, sz, color = self._new_object_defaults()
        self._add_node_to_scene(Node(
            id=new_id, type=5, parent_id=0, branch_level=0,
            translate_x=next_x, translate_y=0.0, translate_z=0.0,
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=sx, scale_y=sy, scale_z=sz,
            color_r=color.red(), color_g=color.green(), color_b=color.blue(), color_a=color.alpha(),
            geometry=geo, hide=0, topo=topo,
        ))

    def _create_child_node(self):
        """Shift+N / New Child button: create a child node (using the New Object
        Defaults) under the selected node.

        Multiple presses keep the parent selected and distribute children evenly
        along translate_x so they don't overlap.
        """
        if len(self._selected_nodes) != 1:
            self.statusBar().showMessage("Select exactly one node to add a child.")
            return
        parent = self._selected_nodes[0]
        sibling_count = sum(1 for n in self.nodes if n.parent_id == parent.id)
        new_id = max((n.id for n in self.nodes), default=0) + 1
        geo, topo, sx, sy, sz, color = self._new_object_defaults()
        self._add_node_to_scene(Node(
            id=new_id, type=5, parent_id=parent.id,
            branch_level=parent.branch_level + 1,
            translate_x=sibling_count * 5.0, translate_y=0.0, translate_z=5.0,
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=sx, scale_y=sy, scale_z=sz,
            color_r=color.red(), color_g=color.green(), color_b=color.blue(), color_a=color.alpha(),
            geometry=geo, hide=0, topo=topo,
        ), select_new=False)

    def _add_node_to_scene(self, node: Node, select_new: bool = True):
        """Append a node to the live scene, table, and stats without resetting the camera."""
        self.nodes.append(node)           # also updates _scene.nodes (same list)
        self._viewport.register_node(node)  # syncs _by_id, invalidates, repaints
        self._table.append_node(node)
        self._update_stats()
        self._update_sel_values()
        if select_new:
            self._table.select_by_id(node.id)
        self.statusBar().showMessage(
            f"Created node {node.id}  parent={node.parent_id}  "
            f"level={node.branch_level}  geo={node.geometry}  topo={node.topo}"
        )

    def _descendants_of(self, root_ids: set[int]) -> set[int]:
        """root_ids plus every descendant id, transitively (cascade-delete closure).
        Children are never reparented onto a deleted node's parent — there's no
        well-defined place to put them — so deleting a node always takes its
        whole subtree with it."""
        result = set(root_ids)
        frontier = result
        while frontier:
            frontier = {n.id for n in self.nodes if n.parent_id in frontier and n.id not in result}
            result |= frontier
        return result

    def _delete_selected(self):
        """Delete/Backspace key or Delete button: remove the selected node(s)
        and all of their descendants from the scene."""
        if not self._selected_nodes:
            return
        ids_to_delete = self._descendants_of({n.id for n in self._selected_nodes})
        self._viewport.remove_nodes(ids_to_delete)   # mutates self.nodes in place (shared list)
        self._table.set_nodes(self.nodes)
        # set_nodes()'s model reset silently drops the table's internal selection
        # without emitting selectionChanged, so resync self._selected_nodes by hand.
        self._on_table_selection()
        self._update_stats()
        self._update_sel_values()
        self.statusBar().showMessage(f"Deleted {len(ids_to_delete)} node(s).")

    # --- Copy / Paste (V1: single node + full descendant closure only) ---

    def _copy_selected(self):
        """Ctrl+C / Edit > Copy: snapshot the selected node and its full
        descendant subtree onto an in-memory clipboard. No partial-subtree
        copies — a node always brings every descendant with it, mirroring
        _delete_selected's restriction model."""
        if len(self._selected_nodes) != 1:
            self.statusBar().showMessage("Select exactly one node to copy.")
            return
        root = self._selected_nodes[0]
        closure_ids = self._descendants_of({root.id})
        self._clipboard_root_id = root.id
        self._clipboard_nodes = [
            copy.deepcopy(n) for n in self.nodes if n.id in closure_ids
        ]
        self.statusBar().showMessage(
            f"Copied node {root.id} and {len(self._clipboard_nodes) - 1} descendant(s)."
        )

    def _paste_clipboard(self):
        """Ctrl+V / Edit > Paste: insert a fresh copy of the clipboard subtree
        (ids reassigned via max(existing ids) + 1, same allocation rule as
        _create_root_node), parented onto whatever's selected right now:

        - exactly one node selected -> the pasted subtree becomes a CHILD of
          it (positioned like _create_child_node). Re-selecting the original
          parent and pasting reproduces a plain "new sibling," since a
          sibling is just another child of the same parent.
        - nothing selected -> the pasted subtree becomes a new root-level
          (branch_level 0, parent_id=0) object (positioned like
          _create_root_node), regardless of where the original lived.
        - more than one node selected -> ambiguous paste target; aborted.

        Internal links (type=7) whose A-end and B-end both fall inside the
        copied subtree are remapped to the new ids; a link whose other end
        falls outside the copied subtree is dropped rather than left
        dangling or pointed at an ambiguous target."""
        if not self._clipboard_nodes:
            self.statusBar().showMessage("Nothing to paste — copy a node first.")
            return
        if len(self._selected_nodes) > 1:
            self.statusBar().showMessage("Select exactly one node (or none) as the paste target.")
            return

        next_id = max((n.id for n in self.nodes), default=0) + 1
        id_map: dict[int, int] = {}
        for n in self._clipboard_nodes:
            id_map[n.id] = next_id
            next_id += 1

        root = next(n for n in self._clipboard_nodes if n.id == self._clipboard_root_id)
        target = self._selected_nodes[0] if self._selected_nodes else None
        if target is not None:
            new_parent_id = target.id
            new_branch_level = target.branch_level + 1
            sibling_count = sum(1 for n in self.nodes if n.parent_id == target.id)
            new_translate = (sibling_count * 5.0, 0.0, 5.0)
        else:
            new_parent_id = 0
            new_branch_level = 0
            new_translate = (self._next_root_x(), 0.0, 0.0)
        branch_level_delta = new_branch_level - root.branch_level

        pasted: list[Node] = []
        for n in self._clipboard_nodes:
            new_node = copy.deepcopy(n)
            new_node.id = id_map[n.id]
            new_node.branch_level = n.branch_level + branch_level_delta
            if n.id == self._clipboard_root_id:
                new_node.parent_id = new_parent_id
                new_node.translate_x, new_node.translate_y, new_node.translate_z = new_translate
            else:
                new_node.parent_id = id_map.get(n.parent_id, n.parent_id)
            if new_node.type == NODE_TYPE_LINK:
                b_id = int(float(n.extras.get('child_id', 0)))
                if b_id not in id_map:
                    continue   # B-end outside the copied subtree — drop the link
                new_node.extras['child_id'] = id_map[b_id]
            pasted.append(new_node)
            self._add_node_to_scene(new_node, select_new=False)

        self._table.select_by_ids({n.id for n in pasted})
        self.statusBar().showMessage(f"Pasted {len(pasted)} node(s).")

    # --- Channel / animation playback ---

    def _ch_load_from_csv(self, path: str) -> str | None:
        """Detect and load companion channel files (and a synced audio file,
        if present).  Returns a short status string or None."""
        from glyphviz_core.channel_loader import (
            find_audio_file, find_channel_files, load_ch_map, load_ch_tracks,
        )
        from glyphviz_core.channel_engine import ChannelEngine

        map_path, tracks_path = find_channel_files(path)
        if not map_path or not tracks_path:
            self._ch_grp.setVisible(False)
            self._ch_engine = None
            self._ch_unload_audio()
            return None

        try:
            ch_map = load_ch_map(map_path)
            tracks, id_to_col = load_ch_tracks(tracks_path)
            engine = ChannelEngine()
            engine.load(ch_map, tracks, id_to_col, self.nodes)
            if engine.frame_count == 0 or not engine.has_bindings:
                self._ch_grp.setVisible(False)
                self._ch_engine = None
                self._ch_unload_audio()
                return None
            self._ch_engine = engine
            self._ch_frame = 0
            self._ch_slider.blockSignals(True)
            self._ch_slider.setRange(0, engine.frame_count - 1)
            self._ch_slider.setValue(0)
            self._ch_slider.blockSignals(False)
            self._ch_frame_label.setText(f"Frame: 0 / {engine.frame_count - 1}")
            self._ch_grp.setVisible(True)

            audio_path = find_audio_file(path)
            if audio_path:
                self._ch_audio.load(audio_path)
                self._ch_audio_loaded = True
                self._ch_fps.setEnabled(False)
                self._ch_fps.setToolTip(
                    "Disabled: this Channels animation is synced to its audio "
                    "file's real playback position instead of a fixed rate."
                )
                return f"channels: {engine.frame_count} frames, synced to {audio_path.name}"
            self._ch_unload_audio()
            return f"channels: {engine.frame_count} frames"
        except Exception as exc:
            self._ch_grp.setVisible(False)
            self._ch_engine = None
            self._ch_unload_audio()
            self.statusBar().showMessage(f"Channel load warning: {exc}")
            return None

    def _ch_unload_audio(self):
        self._ch_audio.unload()
        self._ch_audio_loaded = False
        self._ch_fps.setEnabled(True)
        self._ch_fps.setToolTip("Playback speed in frames per second")

    def _ch_toggle_play(self):
        if self._ch_playing:
            self._ch_timer.stop()
            self._ch_playing = False
            self._ch_play_btn.setText("▶")
            if self._ch_audio_loaded:
                self._ch_audio.pause()
        else:
            if self._ch_engine is None:
                return
            if self._ch_audio_loaded:
                self._ch_timer.start(_AUDIO_TICK_MS)
                self._ch_audio.play(loop=self._ch_loop.isChecked())
            else:
                self._ch_timer.start(max(1, int(1000 / self._ch_fps.value())))
            self._ch_playing = True
            self._ch_play_btn.setText("⏸")

    def _ch_stop(self):
        self._ch_timer.stop()
        self._ch_playing = False
        self._ch_play_btn.setText("▶")
        self._ch_frame = 0
        if self._ch_audio_loaded:
            self._ch_audio.stop()
        if self._ch_engine:
            self._ch_engine.reset()
            self._ch_slider.blockSignals(True)
            self._ch_slider.setValue(0)
            self._ch_slider.blockSignals(False)
            self._ch_frame_label.setText(f"Frame: 0 / {self._ch_engine.frame_count - 1}")
            self._viewport.scene_invalidate()

    def _ch_tick(self):
        if self._ch_engine is None:
            return
        if self._ch_audio_loaded:
            self._ch_tick_audio_synced()
        else:
            self._ch_tick_fixed_rate()

    def _ch_tick_fixed_rate(self):
        self._ch_frame += 1
        if self._ch_frame >= self._ch_engine.frame_count:
            if self._ch_loop.isChecked():
                self._ch_frame = 0
            else:
                self._ch_frame = self._ch_engine.frame_count - 1
                self._ch_timer.stop()
                self._ch_playing = False
                self._ch_play_btn.setText("▶")
        self._ch_apply_and_show_frame(self._ch_frame)

    def _ch_tick_audio_synced(self):
        """Drive the Channels frame index from the audio file's real playback
        position rather than a fixed rate, so render slowdowns cost smoothness,
        not audio sync — see [[project_audio_strategy]] in memory for why."""
        duration_ms = self._ch_audio.duration_ms()
        if duration_ms <= 0:
            return   # audio hasn't finished opening yet
        position_frac = min(1.0, self._ch_audio.position_ms() / duration_ms)
        frame = min(self._ch_engine.frame_count - 1, int(position_frac * self._ch_engine.frame_count))
        self._ch_frame = frame
        self._ch_apply_and_show_frame(frame)
        if self._ch_audio.has_ended() and not self._ch_loop.isChecked():
            self._ch_timer.stop()
            self._ch_playing = False
            self._ch_play_btn.setText("▶")

    def _ch_apply_and_show_frame(self, frame: int):
        self._ch_engine.apply_frame(frame)
        self._ch_slider.blockSignals(True)
        self._ch_slider.setValue(frame)
        self._ch_slider.blockSignals(False)
        self._ch_frame_label.setText(f"Frame: {frame} / {self._ch_engine.frame_count - 1}")
        self._viewport.scene_invalidate()

    def _on_ch_slider(self, value: int):
        self._ch_frame = value
        if self._ch_engine:
            self._ch_engine.apply_frame(value)
            self._ch_frame_label.setText(f"Frame: {value} / {self._ch_engine.frame_count - 1}")
            self._viewport.scene_invalidate()
            if self._ch_audio_loaded and self._ch_engine.frame_count > 1:
                frac = value / (self._ch_engine.frame_count - 1)
                self._ch_audio.seek_ms(int(frac * self._ch_audio.duration_ms()))

    def _ch_update_fps(self, _value: float):
        if self._ch_playing and not self._ch_audio_loaded:
            self._ch_timer.start(max(1, int(1000 / self._ch_fps.value())))

    def _update_stats(self, filename: str = None):
        total = len(self.nodes)
        visible = sum(1 for n in self.nodes
                      if not n.hide and n.type not in NON_VISUAL_TYPES)
        if filename:
            self._lbl_file.setText(f"File: {filename}")
        self._lbl_total.setText(f"Nodes: {total}")
        self._lbl_visible.setText(f"Visible: {visible}")
