import copy
import math
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
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
    QSpinBox,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from glyphviz_core.csv_reader import (
    companion_tag_path, load_node_csv, save_node_csv, save_tag_csv,
    stamp_node_and_tag_paths, unstamped_stem,
)
from glyphviz_core import camera_smoothing as cs
from glyphviz_core.drop_router import (
    ACTION_MERGE_CSV, ACTION_MESH, ACTION_OPEN_CSV, ACTION_PDB, ACTION_TEXTURES,
    DropPlan, can_accept, resolve_drop,
)
from glyphviz_core.draw_mode import place_stamp
from glyphviz_core.glyph_recipe import generate_nodes, load_recipe
from glyphviz_core.pdb_loader import load_pdb_file
from glyphviz_core.placement import (
    DEFAULT_CHILD_Z, DEFAULT_PLACEMENT_STEP, PLACEMENT_WRAP, columns_per_row,
    step_from, wrapped_grid_offset,
)
from glyphviz_core.scene import DEFAULT_SCALE_FLOOR
from glyphviz_core.scene_merge import merge_nodes
from glyphviz_core.selection_export import build_selection
from glyphviz_core.geometry_data import (
    GEO_NAMES, GEO_COUNT, GEO_GRID, GEO_GRID_WIRE, GEO_MESH, GEO_OCTA,
    GEO_SPHERE, GEO_SPHERE_WIRE, GEO_LINE, GEO_LINE_PRISM, GEO_POINT,
    _WIRE_IDS,
)
from glyphviz_core.node import (
    Node, NON_VISUAL_TYPES, ROTATION_MODE_EULER_XYZ, ROTATION_MODE_HEADING_TILT_ROLL,
    DEFAULT_TOPO_SCALE, TOPO_SCALE_ANTZ,
    GRID_DEFAULT_EXTENTS, GRID_DEFAULT_SEGMENTS,
    NODE_TYPE_GRID, NODE_TYPE_LINK, NODE_TYPE_WORLD,
    RENDER_MODE_COUNT, RENDER_MODE_NAMES, RENDER_MODE_NORMAL,
    WORLD_DEFAULT_BG_RGB, REF_GRID_DEFAULT_RGB,
    TAG_COLOR_MODE_UNIFORM, TAG_COLOR_MODE_NODE, TAG_DEFAULT_TEXT_RGB,
    TAG_DEFAULT_FONT_SIZE, TAG_FONT_SIZE_MIN, TAG_FONT_SIZE_MAX,
)
from glyphviz_core.topology import (
    TOPO_NAMES, TOPO_COUNT, TOPO_NONE, TOPO_PLANE, TOPO_POINT, CUBE_FACE_NAMES,
)
from glyphviz_core.color_palette import (
    PALETTE_NAMES, PALETTE_COUNT, PALETTE_DEFAULT,
    resolve_palette_color, palette_index_count,
)

from .audio_player import AudioPlayer
from .node_table import NodeTableView
from .topo_scale_ui import (
    TOPO_SCALE_MIN, TOPO_SCALE_MAX, TOPO_SCALE_STEPS_PER_DECADE,
    TOPO_SCALE_SLIDER_MAX, topo_scale_to_slider, slider_to_topo_scale,
)
from .texture_manager import _IMAGE_EXTS as _TEX_IMAGE_EXTS
from .viewport import Viewport

_AUDIO_TICK_MS = 33   # redraw rate while Channels playback is audio-driven (~30 Hz)

# --- Topology Scale inspector control (Node.topo_scale) ----------------------
# Range and slider mapping are shared with the Glyph Composer's per-level
# Topo Scale row — see topo_scale_ui for why they have to agree. Re-exported
# under the module-private names this file has always used.
_TOPO_SCALE_MIN = TOPO_SCALE_MIN
_TOPO_SCALE_MAX = TOPO_SCALE_MAX
_TOPO_SCALE_STEPS_PER_DECADE = TOPO_SCALE_STEPS_PER_DECADE
_TOPO_SCALE_SLIDER_MAX = TOPO_SCALE_SLIDER_MAX
_topo_scale_to_slider = topo_scale_to_slider
_slider_to_topo_scale = slider_to_topo_scale

# A topology change that leaves some child this many times its parent's own
# rendered radius away gets a status-bar hint pointing at Topology Scale (see
# MainWindow._hint_scattered_children). 20x is comfortably past any legitimate
# layout — a child ON its parent's surface sits at ~1x, and even a deliberately
# spread-out subtree stays within single digits — while the case this is for
# lands in the hundreds.
_TOPO_SCALE_HINT_RATIO = 20.0
_TOPO_SCALE_HINT_MS = 12000

# Shared by the Camera toolbar's Fly button and the View menu item.
_FLY_MODE_TIP = (
    "Free-flight camera, for composing screen-capture angles without\n"
    "orbiting a fixed pivot.  [C]\n"
    "\n"
    "LeftButton drag:   up/down flies forward/back, left/right turns\n"
    "                   (the horizon banks into the turn, then levels)\n"
    "RightButton drag:  look around from where the camera stands\n"
    "Both buttons:      slide the camera sideways / up / down\n"
    "Wheel:             fly forward / back\n"
    "MiddleButton:      pan (unchanged)\n"
    "\n"
    "Clicking still selects, and Shift+drag still rubber-band selects,\n"
    "but Move/Rotate/Size drags are suspended until Camera Mode is off.\n"
    "Not available on the fixed +X/+Y/+Z reference views."
)

_DRAW_MODE_TIP = (
    "Draw Mode: paint objects onto a World Grid with the mouse.  [D]\n"
    "\n"
    "Left click stamps one new object (built from the New Object Defaults\n"
    "above) where the cursor meets the grid's plane; click-drag stamps a\n"
    "trail of them, one per Stamp Spacing pixels of cursor travel. Draw Z\n"
    "sets each object's elevation above the plane.\n"
    "\n"
    "Draws onto the selected grid, else the scene's first grid; entering\n"
    "Draw Mode creates a grid if the scene has none. Right-drag still\n"
    "orbits, the wheel still zooms, Shift+drag still rubber-band selects,\n"
    "and Ctrl+click still adds to the selection — but plain click-select\n"
    "is suspended until Draw Mode is off. Esc or D exits."
)


def _app_dir() -> Path:
    """Directory treated as 'next to the executable' (K-key autosave, default
    media/ folder): the frozen executable's folder (e.g. PyInstaller), or the
    folder containing main.py when running from source. No ANTz-style
    usr/csv/ subfolder yet — that's a future convention, not implemented
    here.

    On macOS the executable lives at GlyphViz.app/Contents/MacOS/GlyphViz, and
    that folder is the wrong answer twice over: it's inside the bundle (so an
    autosave would vanish on upgrade, and code-signature validation breaks when
    a signed bundle's contents change), and it's read-only once the app sits in
    /Applications. Walk back out to the folder *containing* the .app instead."""
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        if sys.platform == 'darwin':
            for parent in exe_dir.parents:
                if parent.suffix == '.app':
                    beside = parent.parent
                    # ...and if the .app was installed to /Applications, that
                    # folder isn't user-writable either. ~/GlyphViz is, and
                    # _quick_save creates it on demand.
                    if os.access(beside, os.W_OK):
                        return beside
                    return Path.home() / 'GlyphViz'
        return exe_dir
    return Path(__file__).resolve().parents[1]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GlyphViz")
        self.resize(1280, 800)
        # Drops land on the window, not the viewport: QOpenGLWidget leaves
        # acceptDrops off, so a drop anywhere over the 3D view propagates up.
        self.setAcceptDrops(True)
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
        # The single node whose details are currently shown in the status bar
        # (None when 0 or 2+ nodes are selected) — kept so resizeEvent can
        # re-elide the tag text without re-running the whole selection handler.
        self._status_current_node: Node | None = None
        self._audio_follow_selection = False
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

        # Watch and Reload: poll the open node CSV's mtime once a second and
        # hot-reload the scene when a generator rewrites it (e.g. a --watch
        # data script), preserving camera, selection, and playback state.
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(1000)
        self._watch_timer.timeout.connect(self._watch_tick)
        self._watch_mtime: float | None = None

        # Gizmo manipulation state (Move/Rotate/Size mode selector)
        self._gizmo_mode: str | None = None
        self._mode_buttons: dict[str, QPushButton] = {}

        # Camera toolbar buttons (Main + 3 fixed axis views), kept in sync
        # with the viewport's active camera via cameraChanged.
        self._camera_buttons: list[QPushButton] = []

        # Link mode (interactive Link creation): click an A-end node, then a
        # B-end node, to create a type=7 Link between them. Separate from
        # _gizmo_mode/_mode_buttons above -- Move/Rotate/Size require an
        # existing selection and get force-cleared the moment selection is
        # empty (_on_table_selection), but Link mode must be armable with
        # nothing selected and must survive selecting the A-end/new Link node.
        self._link_mode_active: bool = False
        self._link_pending_a_id: int | None = None

        # Rate-animation pause: freezes translate_rate/rotate_rate/scale_rate
        # in place by zeroing them (snapshotting the originals here) so a Save
        # while paused writes a genuinely static file — not just a visually
        # frozen live view — then restores the originals on resume. See
        # _toggle_rates_paused. Snapshot is keyed by node id since paused
        # nodes could in principle be deleted before resume.
        self._rates_paused: bool = False
        self._paused_rate_snapshot: dict[int, tuple] = {}

        self._build_viewport()
        self._build_menu()
        self._build_manipulate_toolbar()
        self._build_camera_toolbar()
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
        self._viewport.nodeLinkActivated.connect(self._on_node_link_activated)
        self._viewport.nodesSelected.connect(self._on_viewport_nodes_selected)
        self._viewport.nodesSelectedAdditive.connect(self._on_viewport_nodes_selected_additive)
        self._viewport.hideSelectedRequested.connect(self._hide_selected)
        self._viewport.showAllRequested.connect(self._show_all)
        self._viewport.isolateSelectedRequested.connect(self._isolate_selected)
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
        self._viewport.gridSelectRequested.connect(self._select_next_grid)
        self._viewport.geoCycleRequested.connect(self._cycle_selected_geometry)
        self._viewport.topoCycleRequested.connect(self._cycle_selected_topology)
        self._viewport.colorIndexCycleRequested.connect(self._cycle_selected_color_index)
        self._viewport.paletteCycleRequested.connect(self._cycle_selected_palette)
        self._viewport.escapePressed.connect(self._on_escape_pressed)
        self._viewport.nodesManipulated.connect(self._on_viewport_manipulated)
        self._viewport.bgToggleRequested.connect(self._on_scene_bg_toggle_bw)
        self._viewport.renderModeCycleRequested.connect(self._on_scene_render_mode_cycle)
        self._viewport.channelPlayToggleRequested.connect(self._ch_toggle_play)
        self._viewport.channelStopRequested.connect(self._ch_stop)
        self._viewport.glInitialized.connect(self._load_default_media)
        self._viewport.cameraChanged.connect(self._on_camera_changed)
        self._viewport.flyModeChanged.connect(self._on_fly_mode_changed)
        self._draw_stroke_count = 0   # stamps in the current draw stroke
        self._draw_stroke_nodes = 0   # nodes those stamps created (hyperglyphs make several per stamp)
        self._viewport.drawModeChanged.connect(self._on_draw_mode_changed)
        self._viewport.drawStampRequested.connect(self._on_draw_stamp)
        self._viewport.drawStrokeFinished.connect(self._on_draw_stroke_finished)
        self.setCentralWidget(self._viewport)
        # Link self.nodes into the viewport scene so appends stay in sync.
        self._viewport.set_nodes(self.nodes)

    def _build_menu(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        open_act = file_menu.addAction("&Open Node CSV…")
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._open_csv)

        merge_act = file_menu.addAction("&Merge Node CSV…")
        merge_act.setShortcut("Ctrl+M")
        merge_act.setToolTip(
            "Load a second node CSV (and its companion tag file) INTO the\n"
            "current scene instead of replacing it. The merged nodes get fresh\n"
            "ids above the existing ones and keep their own coordinates, so the\n"
            "two scenes overlay in the same world space.  [Ctrl+M]"
        )
        merge_act.triggered.connect(self._merge_csv)

        self._watch_act = file_menu.addAction("Watch and &Reload")
        self._watch_act.setCheckable(True)
        self._watch_act.setChecked(False)
        self._watch_act.setShortcut("Ctrl+R")
        self._watch_act.setToolTip(
            "Watch the open node CSV on disk and hot-reload the scene\n"
            "whenever another program rewrites it (e.g. a data generator\n"
            "running with --watch). Camera, selection, and Channels playback\n"
            "survive each reload.  [Ctrl+R]"
        )
        self._watch_act.triggered.connect(self._toggle_watch_reload)

        import_pdb_act = file_menu.addAction("Import &PDB File…")
        import_pdb_act.setToolTip(
            "Load a .pdb protein structure: atoms become GEO_SPHERE nodes,\n"
            "bonds (distance-inferred) become link nodes. Replaces the current scene."
        )
        import_pdb_act.triggered.connect(self._import_pdb_file)

        self._save_act = file_menu.addAction("&Save")
        self._save_act.setShortcut("Ctrl+S")
        self._save_act.setEnabled(False)
        self._save_act.triggered.connect(self._save_csv)

        save_as_act = file_menu.addAction("Save &As…")
        save_as_act.setShortcut("Ctrl+Shift+S")
        save_as_act.triggered.connect(self._save_csv_as)

        self._save_sel_act = file_menu.addAction("Save Se&lection As…")
        self._save_sel_act.setShortcut("Ctrl+Alt+S")
        self._save_sel_act.setEnabled(False)
        self._save_sel_act.setToolTip(
            "Write the selected nodes (and, by default, their descendants) to\n"
            "a node CSV of their own. A node whose parent is left behind keeps\n"
            "its world placement, so the saved fragment reopens looking exactly\n"
            "as it does here.  [Ctrl+Alt+S]"
        )
        self._save_sel_act.triggered.connect(self._save_selection_as)

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

        edit_menu.addSeparator()
        invert_act = edit_menu.addAction("&Invert Selection")
        invert_act.setShortcut("Ctrl+I")
        invert_act.setToolTip("Select every node that is not currently selected.")
        invert_act.triggered.connect(self._on_invert_selection)

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

        tools_menu = mb.addMenu("&Tools")
        composer_act = tools_menu.addAction("&Glyph Composer…")
        composer_act.setShortcut("Ctrl+G")
        composer_act.setToolTip("Build and preview hierarchical glyph templates.")
        composer_act.triggered.connect(self._on_glyph_composer)

        hyperglyph_act = tools_menu.addAction("&Hyperglyph Generator…")
        hyperglyph_act.setShortcut("Ctrl+H")
        hyperglyph_act.setToolTip(
            "Procedurally generate a single randomized multi-level hyperglyph\n"
            "from a branch-level count and a node budget. For batches of many\n"
            "designs at once, see hyperglyph_lab/ instead."
        )
        hyperglyph_act.triggered.connect(self._on_hyperglyph_generator)

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
        self._tags_act.setChecked(False)   # matches Viewport.show_tags default
        self._tags_act.setToolTip("Toggle tag text display  [T]")
        self._tags_act.triggered.connect(lambda c: self._set_tags(c))

        self._selbox_act = self._view_menu.addAction("Show Selection &Box")
        self._selbox_act.setCheckable(True)
        self._selbox_act.setChecked(True)   # matches Viewport.show_selection_box
        self._selbox_act.setShortcut("Ctrl+B")
        self._selbox_act.setToolTip(
            "Draw the yellow bounding box around selected nodes.\n"
            "Uncheck for a selection-free screengrab without losing the\n"
            "selection -- manipulation and selection keys keep working.\n"
            "(ANTz toggles this with the spacebar, which GlyphViz uses for\n"
            "Channels playback.)  [Ctrl+B]"
        )
        self._selbox_act.triggered.connect(lambda c: self._set_selection_box(c))

        self._gizmo_act = self._view_menu.addAction("Show Transform &Handles")
        self._gizmo_act.setCheckable(True)
        self._gizmo_act.setChecked(True)   # matches Viewport.show_gizmo_handles
        self._gizmo_act.setToolTip(
            "Draw the red/green/blue X/Y/Z handles on the selected node while\n"
            "Move, Rotate or Size is armed, and let them be dragged directly.\n"
            "Unchecking leaves the armed mode and its free-form axis drags\n"
            "exactly as they were -- only the on-screen handles go away."
        )
        self._gizmo_act.triggered.connect(lambda c: self._set_gizmo_handles(c))

        self._scale_floor_act = self._view_menu.addAction(
            f"Enforce &Minimum Glyph Size ({DEFAULT_SCALE_FLOOR:g})")
        self._scale_floor_act.setCheckable(True)
        self._scale_floor_act.setChecked(False)  # matches Viewport._scale_floor
        self._scale_floor_act.setToolTip(
            f"Clamp every glyph's rendered size (scale x Global Scale) to at least\n"
            f"{DEFAULT_SCALE_FLOOR:g} per axis, so a very small or zero-scale node stays visible\n"
            "and clickable. Off by default: glyphs render at exactly their\n"
            "authored scale. World Grids are never clamped."
        )
        self._scale_floor_act.triggered.connect(lambda c: self._set_scale_floor(c))

        self._view_menu.addSeparator()
        self._stereo_act = self._view_menu.addAction("Stereo &3D (Cross-Eye)")
        self._stereo_act.setCheckable(True)
        self._stereo_act.setChecked(False)
        self._stereo_act.setToolTip(
            "Side-by-side stereo pair, free-viewed by crossing your eyes.\n"
            "Fills the Viewer panel and adapts as side panels open/close.\n"
            "Camera orbit/pan/zoom and single-node click/double-click selection\n"
            "still work; rubber-band region select is disabled while active."
        )
        self._stereo_act.triggered.connect(lambda c: self._set_stereo(c))

        self._view_menu.addSeparator()
        self._pause_rates_act = self._view_menu.addAction("&Pause Rate Animation")
        self._pause_rates_act.setCheckable(True)
        self._pause_rates_act.setChecked(False)
        self._pause_rates_act.setShortcut("P")
        self._pause_rates_act.setToolTip(
            "Freeze all translate_rate/rotate_rate/scale_rate animation in place\n"
            "(e.g. to Save a static snapshot mid-evolution of a Hyperglyph),\n"
            "then resume with the original rates unchanged.  [P]"
        )
        self._pause_rates_act.triggered.connect(self._toggle_rates_paused)

        self._view_menu.addSeparator()
        self._fly_act = self._view_menu.addAction("&Camera Mode (Free Flight)")
        self._fly_act.setCheckable(True)
        self._fly_act.setChecked(False)
        self._fly_act.setToolTip(_FLY_MODE_TIP)
        self._fly_act.triggered.connect(lambda c: self._viewport.set_fly_mode(c))

        self._follow_act = self._view_menu.addAction("&Follow Selected Node")
        self._follow_act.setCheckable(True)
        self._follow_act.setChecked(False)
        self._follow_act.setShortcut("F")
        self._follow_act.setToolTip(
            "Keep the camera centered on the selected node as it moves\n"
            "(the first selected node in the table when several are selected).\n"
            "Orbit and zoom stay live while following; panning is overridden.  [F]"
        )
        self._follow_act.triggered.connect(lambda c: self._set_follow(c))
        self._view_menu.addAction("Reset &Camera").triggered.connect(self._reset_camera)

    def _build_manipulate_toolbar(self):
        """Ever-present Move/Rotate/Size mode selector + X/Y/Z axis confinement,
        analogous to ANTz's persistent mouse-mode/tool indicator."""
        tb = QToolBar("Manipulate", self)
        tb.setObjectName("manipulateToolbar")
        tb.setMovable(False)

        for name, label, tip in (
            ("move", "Move", "Move selected node(s): drag a red/green/blue arrow to go along\n"
                             "that one axis, or drag anywhere else for the free-form axis drag\n"
                             "(LeftButton).  Click again to return to camera-only."),
            ("rotate", "Rotate", "Rotate selected node(s): drag a red/green/blue ring to turn about\n"
                                 "that one axis, or drag anywhere else for the free-form axis drag\n"
                                 "(LeftButton).  Click again to return to camera-only."),
            ("size", "Size", "Scale selected node(s): drag a red/green/blue bar to stretch that\n"
                             "one axis, or drag anywhere else for the free-form axis drag\n"
                             "(LeftButton).  Tick 'Lock X/Y/Z together' in the Properties\n"
                             "panel to scale all three axes uniformly instead.\n"
                             "Click again to return to camera-only."),
        ):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setEnabled(False)   # enabled once there's a selection
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _checked=False, n=name: self._on_mode_button_clicked(n))
            self._mode_buttons[name] = btn
            tb.addWidget(btn)

        tb.addSeparator()

        # Separate from the Move/Rotate/Size group above: Link mode must be
        # armable with nothing selected (see _link_mode_active), so it isn't
        # gated by _on_table_selection's has_selection enable/disable and
        # doesn't share _gizmo_mode's state.
        self._link_mode_btn = QPushButton("Link")
        self._link_mode_btn.setCheckable(True)
        self._link_mode_btn.setToolTip(
            "Click a node, then a second node, to create a Link between "
            "them (LeftButton). Escape or a miss-click cancels a pending "
            "pick without creating a link. Stays armed for the next pair "
            "until clicked again."
        )
        self._link_mode_btn.clicked.connect(self._on_link_mode_button_clicked)
        tb.addWidget(self._link_mode_btn)

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

    def _build_camera_toolbar(self):
        """Ever-present camera picker: Main (free orbit) + the 3 fixed
        +X/+Y/+Z reference views, matching the viewport's 4 default cameras,
        plus the Camera Mode (free flight) toggle. Shift+C cycles the camera
        list and C toggles flight; both stay in sync via cameraChanged /
        flyModeChanged (see _on_camera_changed, _on_fly_mode_changed)."""
        tb = QToolBar("Camera", self)
        tb.setObjectName("cameraToolbar")
        tb.setMovable(False)

        for i, name in enumerate(self._viewport.camera_names()):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setToolTip(
                "Fixed reference view: zoom only, no orbit/pan.  [Shift+C cycles]"
                if i else "Free orbit/pan/zoom camera.  [Shift+C cycles]"
            )
            btn.clicked.connect(lambda _checked=False, idx=i: self._viewport.select_camera(idx))
            self._camera_buttons.append(btn)
            tb.addWidget(btn)

        tb.addSeparator()
        self._fly_btn = QPushButton("Fly")
        self._fly_btn.setCheckable(True)
        self._fly_btn.setToolTip(_FLY_MODE_TIP)
        self._fly_btn.clicked.connect(lambda checked: self._viewport.set_fly_mode(checked))
        tb.addWidget(self._fly_btn)

        self.addToolBar(tb)
        self._view_menu.addAction(tb.toggleViewAction())

    def _on_camera_changed(self, index: int):
        for i, btn in enumerate(self._camera_buttons):
            btn.blockSignals(True)
            btn.setChecked(i == index)
            btn.blockSignals(False)
        name = self._viewport.camera_names()[index]
        self.statusBar().showMessage(f"Camera: {name}", 2000)

    def _on_fly_mode_changed(self, on: bool):
        """Keep the Fly button, the View-menu item, and Follow Selected in
        step with the viewport, whichever of them (or the C key) flipped it."""
        for widget in (self._fly_btn, self._fly_act):
            widget.blockSignals(True)
            widget.setChecked(on)
            widget.blockSignals(False)
        if on and self._follow_act.isChecked():
            # The viewport already cleared follow_selected — just untick it.
            self._follow_act.setChecked(False)
        self.statusBar().showMessage(
            "Camera Mode ON — Left: fly/turn · Right: look around · "
            "Both: slide · Wheel: fly  [C]" if on else "Camera Mode off", 4000)

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
        if mode is not None and self._link_mode_active:
            self._set_link_mode(False)   # mutually exclusive with Link mode
        self._viewport.update()
        if mode is not None:
            labels = {'move': 'Move', 'rotate': 'Rotate', 'size': 'Size'}
            hint = ("drag a handle for one axis, or drag anywhere else for the "
                    "free-form drag" if self._viewport.show_gizmo_handles
                    else "drag to edit the checked axes")
            if mode == 'size' and self._viewport.uniform_scale:
                hint += "; X/Y/Z locked together"
            self.statusBar().showMessage(f"{labels[mode]} mode — {hint}.", 5000)

    def _on_link_mode_button_clicked(self):
        self._set_link_mode(not self._link_mode_active)

    def _set_link_mode(self, active: bool):
        """Toggle interactive Link creation. Mutually exclusive with
        Move/Rotate/Size (see _set_gizmo_mode); unlike those, armable with
        nothing selected, and any pending A-end is dropped whenever the mode
        is (re)entered or left."""
        self._link_mode_active = active
        self._link_pending_a_id = None
        self._link_mode_btn.blockSignals(True)
        self._link_mode_btn.setChecked(active)
        self._link_mode_btn.blockSignals(False)
        if active:
            self._viewport.setCursor(Qt.CursorShape.CrossCursor)
            if self._gizmo_mode is not None:
                self._set_gizmo_mode(None)
            self.statusBar().showMessage("Link mode: click an A-end node, then a B-end node.")
        else:
            self._viewport.unsetCursor()

    def _on_gizmo_axis_toggled(self, axis: str, _checked: bool = False):
        self._viewport.gizmo_axes = {
            a: cb.isChecked() for a, cb in self._gizmo_axis_checks.items()
        }

    def _on_viewport_manipulated(self, node_ids: object):
        self._table.refresh_nodes(node_ids)
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

        # Reference-grid color. Sits with its checkbox, but — like the tag
        # colors below — it persists to the World node (see
        # _refresh_scene_settings), so it's scene data, not viewport state.
        grid_color_row = QWidget()
        grid_color_layout = QHBoxLayout(grid_color_row)
        grid_color_layout.setContentsMargins(0, 0, 0, 0)
        grid_color_layout.setSpacing(4)
        grid_color_layout.addWidget(QLabel("Grid Color:"))
        self._grid_color_btn = QPushButton()
        self._grid_color_btn.setFixedHeight(24)
        self._grid_color_btn.setToolTip(
            "Color of the reference grid drawn under the scene.\n"
            "A World Grid node (type 6) paints its own lattice from its own\n"
            "node color instead — this is the backdrop grid only."
        )
        self._grid_color_btn.clicked.connect(self._on_ref_grid_color)
        grid_color_layout.addWidget(self._grid_color_btn, 1)
        self._set_color_btn(self._grid_color_btn, *REF_GRID_DEFAULT_RGB, 255)

        self._cb_hidden = QCheckBox("Show Hidden Nodes")
        self._cb_hidden.setChecked(False)
        self._cb_hidden.toggled.connect(self._set_hidden)

        self._cb_tags = QCheckBox("Show Tag Labels")
        self._cb_tags.setChecked(False)   # matches Viewport.show_tags default
        self._cb_tags.setToolTip("Toggle tag text display in 3D view  [T]")
        self._cb_tags.toggled.connect(self._set_tags)

        self._cb_tags_selected = QCheckBox("Show Tag Labels of Selected")
        self._cb_tags_selected.setChecked(False)
        self._cb_tags_selected.setToolTip(
            "When checked, only selected nodes' tag labels are drawn."
        )
        self._cb_tags_selected.toggled.connect(self._set_tags_selected_only)

        # Tag text styling. Grouped here with the other tag controls, but
        # unlike them these persist to the World node (type=0, see
        # _refresh_scene_settings) — they're scene data, not viewport state.
        # The dark drop shadow behind tag text is deliberately not settable.
        tag_color_row = QWidget()
        tag_color_layout = QHBoxLayout(tag_color_row)
        tag_color_layout.setContentsMargins(0, 0, 0, 0)
        tag_color_layout.setSpacing(4)
        tag_color_layout.addWidget(QLabel("Tag Color:"))
        self._tag_color_btn = QPushButton()
        self._tag_color_btn.setFixedHeight(24)
        self._tag_color_btn.setToolTip(
            "Color of tag label text, for every tag in the scene.\n"
            "Ignored while 'Tag Text Matches Node Color' is checked."
        )
        self._tag_color_btn.clicked.connect(self._on_tag_text_color)
        tag_color_layout.addWidget(self._tag_color_btn, 1)
        self._set_color_btn(self._tag_color_btn, *TAG_DEFAULT_TEXT_RGB, 255)

        self._cb_tag_color_node = QCheckBox("Tag Text Matches Node Color")
        self._cb_tag_color_node.setChecked(False)
        self._cb_tag_color_node.setToolTip(
            "When checked, each tag label is drawn in its own node's color\n"
            "instead of the single Tag Color above, so a label reads as\n"
            "belonging to the glyph it names."
        )
        self._cb_tag_color_node.toggled.connect(self._on_tag_color_mode_toggled)

        # Tag text size — World-node scene data too, so a scene's labels are
        # the size its author chose. A slider rather than a dropdown of point
        # sizes: what reads well depends on the scene, the label lengths and
        # the distance you work at, and a slider lets you find that against
        # the live labels instead of committing to a number blind.
        self._tag_font_label = QLabel(f"Tag Text Size: {TAG_DEFAULT_FONT_SIZE} pt")
        self._tag_font_slider = QSlider(Qt.Orientation.Horizontal)
        self._tag_font_slider.setRange(TAG_FONT_SIZE_MIN, TAG_FONT_SIZE_MAX)
        self._tag_font_slider.setValue(TAG_DEFAULT_FONT_SIZE)
        self._tag_font_slider.setTickInterval(6)
        self._tag_font_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._tag_font_slider.setToolTip(
            "Point size of every tag label in the scene.\n"
            f"Default {TAG_DEFAULT_FONT_SIZE} pt; saved with the file, like Tag Color."
        )
        self._tag_font_slider.valueChanged.connect(self._on_tag_font_size_changed)

        disp_layout.addWidget(self._cb_axes)
        disp_layout.addWidget(self._cb_grid)
        disp_layout.addWidget(grid_color_row)
        disp_layout.addWidget(self._cb_hidden)
        disp_layout.addWidget(self._cb_tags)
        disp_layout.addWidget(self._cb_tags_selected)
        disp_layout.addWidget(tag_color_row)
        disp_layout.addWidget(self._cb_tag_color_node)
        disp_layout.addWidget(self._tag_font_label)
        disp_layout.addWidget(self._tag_font_slider)

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

        self._cb_audio_follow_selection = QCheckBox("Solo Audio to Selection")
        self._cb_audio_follow_selection.setChecked(False)
        self._cb_audio_follow_selection.setToolTip(
            "When checked, only video textures on currently selected nodes play\n"
            "audio -- select several video-textured nodes to hear all of them at\n"
            "once, or deselect to mute. Overrides the dropdown above while checked."
        )
        self._cb_audio_follow_selection.setEnabled(False)
        self._cb_audio_follow_selection.toggled.connect(self._on_audio_follow_selection_toggled)
        disp_layout.addWidget(self._cb_audio_follow_selection)

        # --- Scale group ---
        scale_grp = QGroupBox("Global Scale")
        scale_layout = QVBoxLayout(scale_grp)
        self._scale_label = QLabel("Scale: 1.0")
        self._scale_slider = QSlider(Qt.Orientation.Horizontal)
        self._scale_slider.setRange(1, 100)
        self._scale_slider.setValue(10)
        self._scale_slider.setTickInterval(10)
        self._scale_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._scale_slider.valueChanged.connect(self._update_scale)
        scale_layout.addWidget(self._scale_label)
        scale_layout.addWidget(self._scale_slider)

        # Opt-in revival of GlyphViz's original always-on minimum rendered
        # scale (see scene.DEFAULT_SCALE_FLOOR) — off by default so a glyph
        # renders at exactly the size its scale fields ask for.
        self._cb_scale_floor = QCheckBox(
            f"Enforce Minimum Glyph Size ({DEFAULT_SCALE_FLOOR:g})")
        self._cb_scale_floor.setChecked(False)
        self._cb_scale_floor.setToolTip(
            f"Clamp every glyph's rendered size (scale x Global Scale) to at\n"
            f"least {DEFAULT_SCALE_FLOOR:g} per axis, so a very small or zero-scale node stays\n"
            "visible and clickable.\n"
            "Off by default: glyphs render at exactly their authored scale.\n"
            "World Grids are never clamped."
        )
        self._cb_scale_floor.toggled.connect(self._set_scale_floor)
        scale_layout.addWidget(self._cb_scale_floor)

        # --- Stereo 3D group: side-by-side cross-eye free-view pair ---
        stereo_grp = QGroupBox("Stereo 3D (Cross-Eye)")
        stereo_layout = QVBoxLayout(stereo_grp)
        self._cb_stereo = QCheckBox("Enable Stereo View")
        self._cb_stereo.setChecked(False)
        self._cb_stereo.setToolTip(
            "Side-by-side stereo pair, free-viewed by crossing your eyes.\n"
            "Camera orbit/pan/zoom and single-node click/double-click selection\n"
            "still work; rubber-band region select is disabled while active."
        )
        self._cb_stereo.toggled.connect(self._set_stereo)
        self._stereo_sep_label = QLabel("Eye Separation: 3.0%")
        self._stereo_sep_slider = QSlider(Qt.Orientation.Horizontal)
        self._stereo_sep_slider.setRange(5, 150)   # 0.5% - 15.0% of camera distance
        self._stereo_sep_slider.setValue(30)       # 3.0% default
        self._stereo_sep_slider.setTickInterval(10)
        self._stereo_sep_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._stereo_sep_slider.setToolTip(
            "Eye separation as a % of camera distance -- auto-scales with zoom.\n"
            "Higher = stronger 3-D depth (and harder to fuse); lower = subtler."
        )
        self._stereo_sep_slider.valueChanged.connect(self._update_stereo_separation)
        stereo_layout.addWidget(self._cb_stereo)
        stereo_layout.addWidget(self._stereo_sep_label)
        stereo_layout.addWidget(self._stereo_sep_slider)

        # --- Camera group: optional ANTz-style navigation smoothing ---
        #
        # ANTz always eased its camera and never let you turn it off; former
        # ANTz users miss the glide, and it measurably buffers hand tremor
        # (Dr. Warner's patients). Off by default because ANTz's own version
        # also swung the target out of frame — see camera_smoothing.py for why
        # GlyphViz's doesn't. The slider is the amount; ANTz's own feel is one
        # preset on it, following the Topo Scale row's 1:1/ANTz idiom.
        camera_grp = QGroupBox("Camera")
        camera_layout = QVBoxLayout(camera_grp)
        self._cam_smooth_label = QLabel("Smoothing: Off")
        self._cam_smooth_slider = QSlider(Qt.Orientation.Horizontal)
        # Slider units are hundredths of a second of time constant, so the
        # scale is linear in the quantity the user actually perceives.
        self._cam_smooth_slider.setRange(0, int(round(cs.TAU_MAX * 100)))
        self._cam_smooth_slider.setValue(int(round(cs.TAU_OFF * 100)))
        self._cam_smooth_slider.setTickInterval(10)
        self._cam_smooth_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._cam_smooth_slider.setToolTip(
            "Camera glide (ANTz-style inertia). 0 = off: the view tracks the\n"
            "mouse exactly. Higher = the camera eases toward where you drag,\n"
            "which looks smoother in demos and buffers hand tremor.\n"
            "Unlike ANTz, aim and position ease together, so what you are\n"
            "orbiting never swings out of frame."
        )
        self._cam_smooth_slider.valueChanged.connect(self._update_camera_smoothing)

        cam_preset_row = QWidget()
        cam_preset_layout = QHBoxLayout(cam_preset_row)
        cam_preset_layout.setContentsMargins(0, 0, 0, 0)
        cam_preset_layout.setSpacing(4)
        btn_smooth_off = QPushButton("Off")
        btn_smooth_off.setToolTip("No smoothing — the default.")
        btn_smooth_off.clicked.connect(lambda: self._set_camera_smoothing_tau(cs.TAU_OFF))
        btn_smooth_antz = QPushButton("ANTz")
        btn_smooth_antz.setToolTip(
            "ANTz's own feel (%.2f s), without its swing-out-of-frame artifact."
            % cs.TAU_ANTZ
        )
        btn_smooth_antz.clicked.connect(lambda: self._set_camera_smoothing_tau(cs.TAU_ANTZ))
        cam_preset_layout.addWidget(btn_smooth_off)
        cam_preset_layout.addWidget(btn_smooth_antz)
        cam_preset_layout.addStretch(1)

        self._cam_smooth_scope = QComboBox()
        self._cam_smooth_scope.addItem("Left+Right drag only", cs.SCOPE_COMBO)
        self._cam_smooth_scope.addItem("All camera navigation", cs.SCOPE_ALL)
        self._cam_smooth_scope.setToolTip(
            "Which gestures glide. Left+Right drag only matches ANTz, where\n"
            "smoothing engaged on that combined orbit+zoom gesture.\n"
            "All camera navigation also covers single-button orbit, pan and\n"
            "wheel zoom — the setting to use for tremor buffering.\n"
            "Camera Mode (free flight) is never smoothed: it is already\n"
            "rate-based, so it has no jitter to filter."
        )
        self._cam_smooth_scope.setEnabled(False)   # nothing to scope while off
        self._cam_smooth_scope.currentIndexChanged.connect(self._update_camera_smoothing)
        camera_layout.addWidget(self._cam_smooth_label)
        camera_layout.addWidget(self._cam_smooth_slider)
        camera_layout.addWidget(cam_preset_row)
        camera_layout.addWidget(QLabel("Applies to:"))
        camera_layout.addWidget(self._cam_smooth_scope)

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
            "Each press steps X by the Placement Step below, wrapping to a\n"
            "new Y row at 360, at the Placement Z (root) height.  If a\n"
            "child-level node is selected, a child is added instead."
        )
        self._btn_new_node.clicked.connect(self._on_create_node)

        self._btn_new_child = QPushButton("New Child")
        self._btn_new_child.setToolTip(
            "Create a child object using the defaults below, under the\n"
            "selected node  [Shift+N]\n"
            "Siblings step along X by the Placement Step below and wrap to a\n"
            "new Y row at 360, so a full lap around a Sphere/Torus parent\n"
            "starts a new ring instead of overlapping; Placement Z (child)\n"
            "sets how far each one stands off its parent.\n"
            "Requires exactly one node to be selected."
        )
        self._btn_new_child.clicked.connect(self._create_child_node)

        self._btn_new_grid = QPushButton("Add World Grid")
        self._btn_new_grid.setToolTip(
            "Create a World Grid (type 6): a geospatial reference plane whose\n"
            "children place by longitude (X) / latitude (Y) / elevation (Z).\n"
            "Default window is the whole earth (-180..180, -90..90) at 1:1\n"
            "world units; edit the window and grid lines in the World Grid\n"
            "panel below. Scaling a grid re-spaces its children without\n"
            "resizing them. Multiple grids per scene are allowed.\n"
            "[G] selects / cycles through grids (grids aren't click-pickable\n"
            "so they never swallow clicks meant for glyphs on them)."
        )
        self._btn_new_grid.clicked.connect(self._create_world_grid)

        create_layout.addWidget(self._btn_new_node)
        create_layout.addWidget(self._btn_new_child)
        create_layout.addWidget(self._btn_new_grid)

        # --- New Object Defaults: geometry/topology/scale/color applied to
        # nodes created via New Node, New Child, N, and Shift+N, plus the
        # Placement Step that spaces them (rotation is never part of these
        # defaults).
        new_defaults_form = QFormLayout()
        new_defaults_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self._new_geo = QComboBox()
        for geo_id in range(GEO_COUNT):
            if geo_id == GEO_MESH:
                continue  # each imported mesh gets its own entry (_add_mesh_combo_entry)
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

        # Placement Step: how far apart consecutive new objects sit. ANTz
        # hardcoded its own step (15); this is the same lattice with the
        # number exposed. See glyphviz_core/placement.py.
        self._new_step = QDoubleSpinBox()
        self._new_step.setRange(0.0, 10_000.0)
        self._new_step.setDecimals(3)
        self._new_step.setSingleStep(1.0)
        self._new_step.setValue(DEFAULT_PLACEMENT_STEP)
        self._new_step.valueChanged.connect(self._on_new_step_changed)
        self._update_step_tip()

        # Placement Z: the translate_z every new object gets. Root and child
        # are separate numbers because the field MEANS different things at the
        # two levels — world elevation above the reference plane for a root,
        # offset off the parent (radially outward, on a Sphere/Torus/Cylinder)
        # for a child, which is why a child at 0 would sit inside a
        # topology-None parent while a root at 5 would hover off the grid.
        self._new_root_z = QDoubleSpinBox()
        self._new_root_z.setRange(-100_000.0, 100_000.0)
        self._new_root_z.setDecimals(3)
        self._new_root_z.setValue(0.0)
        self._new_root_z.setToolTip(
            "translate_z given to a new ROOT-level object (N with nothing, or\n"
            "a root, selected; New Node; paste with no selection; an imported\n"
            "mesh). Its height above the world plane. 0 sits on the plane."
        )

        self._new_child_z = QDoubleSpinBox()
        self._new_child_z.setRange(-100_000.0, 100_000.0)
        self._new_child_z.setDecimals(3)
        self._new_child_z.setValue(DEFAULT_CHILD_Z)
        self._new_child_z.setToolTip(
            "translate_z given to a new CHILD (Shift+N, New Child, paste onto\n"
            "a selection). What it means is the parent's topology's business:\n"
            "on Sphere/Torus/Cylinder it lifts the child off the surface\n"
            "radially, on Cartesian parents it is a plain Z offset. The\n"
            "default 5 is what keeps the first child from sitting inside a\n"
            "topology-None parent; 0 places it exactly on the surface."
        )

        new_z_widget = QWidget()
        new_z_layout = QHBoxLayout(new_z_widget)
        new_z_layout.setContentsMargins(0, 0, 0, 0)
        new_z_layout.setSpacing(4)
        new_z_layout.addWidget(QLabel("root"))
        new_z_layout.addWidget(self._new_root_z)
        new_z_layout.addWidget(QLabel("child"))
        new_z_layout.addWidget(self._new_child_z)

        new_defaults_form.addRow("Geometry:", self._new_geo)
        new_defaults_form.addRow("Topology:", self._new_topo)
        new_defaults_form.addRow("Scale (X,Y,Z):", new_scale_widget)
        new_defaults_form.addRow("", self._new_scale_lock)
        new_defaults_form.addRow("Color:", self._new_color_btn)
        new_defaults_form.addRow("Placement Step:", self._new_step)
        new_defaults_form.addRow("Placement Z:", new_z_widget)

        create_layout.addWidget(QLabel("New Object Defaults:"))
        create_layout.addLayout(new_defaults_form)

        # --- Draw Mode: paint New-Object-Defaults objects onto a World Grid
        # with the mouse (single click = one object, drag = a stamped trail).
        self._draw_mode_btn = QPushButton("Draw Mode")
        self._draw_mode_btn.setCheckable(True)
        self._draw_mode_btn.setToolTip(_DRAW_MODE_TIP)
        # clicked (not toggled): fires on user presses only, so the sync in
        # _on_draw_mode_changed can setChecked without looping.
        self._draw_mode_btn.clicked.connect(
            lambda checked: self._viewport.set_draw_mode(checked))

        self._draw_z = QDoubleSpinBox()
        self._draw_z.setRange(-100_000.0, 100_000.0)
        self._draw_z.setDecimals(3)
        self._draw_z.setValue(0.0)
        self._draw_z.setToolTip(
            "translate_z given to every drawn object — its elevation above\n"
            "the grid's drawing plane. 0 draws directly on the plane."
        )

        self._draw_spacing = QDoubleSpinBox()
        self._draw_spacing.setRange(0.0, 500.0)
        self._draw_spacing.setDecimals(0)
        self._draw_spacing.setValue(30.0)
        self._draw_spacing.setSuffix(" px")
        self._draw_spacing.setToolTip(
            "While dragging, stamp a new object every this many pixels of\n"
            "cursor travel. 0 stamps on every mouse move (maximum density)."
        )
        self._draw_spacing.valueChanged.connect(
            lambda v: setattr(self._viewport, 'draw_stamp_spacing_px', float(v)))

        # What each stamp is: a single object from the New Object Defaults,
        # or a whole Glyph Composer hyperglyph. Templates arrive via the
        # Load… button (a saved composer JSON) or the Glyph Composer's own
        # "Use as Draw Brush" button; each becomes a combo entry.
        self._draw_stamp_combo = QComboBox()
        self._draw_stamp_combo.addItem("Single Object (defaults above)", None)
        self._draw_stamp_combo.setToolTip(
            "What Draw Mode stamps: one object built from the New Object\n"
            "Defaults, or a whole Glyph Composer hyperglyph. Load a saved\n"
            "template with Load…, or send one straight from Tools > Glyph\n"
            "Composer with its Use as Draw Brush button."
        )
        self._draw_stamp_load_btn = QPushButton("Load…")
        self._draw_stamp_load_btn.setToolTip(
            "Load a Glyph Composer template (.json) as the Draw Mode brush.")
        self._draw_stamp_load_btn.clicked.connect(self._on_draw_stamp_load)
        stamp_row = QWidget()
        stamp_row_layout = QHBoxLayout(stamp_row)
        stamp_row_layout.setContentsMargins(0, 0, 0, 0)
        stamp_row_layout.setSpacing(4)
        stamp_row_layout.addWidget(self._draw_stamp_combo, stretch=1)
        stamp_row_layout.addWidget(self._draw_stamp_load_btn)

        self._draw_heading_jitter = QDoubleSpinBox()
        self._draw_heading_jitter.setRange(0.0, 180.0)
        self._draw_heading_jitter.setDecimals(0)
        self._draw_heading_jitter.setValue(0.0)
        self._draw_heading_jitter.setSuffix("°")
        self._draw_heading_jitter.setToolTip(
            "Spin each stamp by a random heading in ±this many degrees\n"
            "(added to rotate_z, so a hyperglyph turns as a whole).\n"
            "0 = every stamp faces the same way."
        )

        self._draw_scale_jitter = QDoubleSpinBox()
        self._draw_scale_jitter.setRange(0.0, 90.0)
        self._draw_scale_jitter.setDecimals(0)
        self._draw_scale_jitter.setValue(0.0)
        self._draw_scale_jitter.setSuffix(" %")
        self._draw_scale_jitter.setToolTip(
            "Grow or shrink each stamp by a random factor in ±this percent\n"
            "(one factor for all three axes, so proportions are preserved).\n"
            "0 = every stamp the same size."
        )

        draw_form = QFormLayout()
        draw_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        draw_form.addRow("Stamp:", stamp_row)
        draw_form.addRow("Draw Z:", self._draw_z)
        draw_form.addRow("Stamp Spacing:", self._draw_spacing)
        draw_form.addRow("Heading Jitter:", self._draw_heading_jitter)
        draw_form.addRow("Scale Jitter:", self._draw_scale_jitter)

        create_layout.addWidget(self._draw_mode_btn)
        create_layout.addLayout(draw_form)

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

        self._sel_invert_btn = QPushButton("Invert Selection")
        self._sel_invert_btn.setToolTip(
            "Select every node that is not currently selected  (Ctrl+I)\n"
            "Selected spheres → everything except those spheres, etc."
        )
        self._sel_invert_btn.clicked.connect(self._on_invert_selection)

        self._sel_criterion = QComboBox()
        self._sel_criterion.addItems(["Branch Level", "Geometry", "Topology"])
        self._sel_criterion.currentIndexChanged.connect(self._update_sel_values)

        self._sel_value = QComboBox()

        self._sel_btn = QPushButton("Select All Matching")
        self._sel_btn.clicked.connect(self._on_select_by)

        self._sel_cumulative = QCheckBox("Add to current selection")
        self._sel_cumulative.setChecked(False)
        self._sel_cumulative.setToolTip(
            "When checked, Select All Matching ADDS to the current selection\n"
            "instead of replacing it — e.g. select all spheres, then all\n"
            "cylinders, and keep both sets selected.\n"
            "(Ctrl+click and Ctrl+Shift+drag in the 3D view are always additive.)"
        )

        sel_layout.addRow(all_none_widget)
        sel_layout.addRow(self._sel_invert_btn)
        sel_layout.addRow("By:", self._sel_criterion)
        sel_layout.addRow("Value:", self._sel_value)
        sel_layout.addRow(self._sel_btn)
        sel_layout.addRow(self._sel_cumulative)

        self._sel_tag_keyword = QLineEdit()
        self._sel_tag_keyword.setPlaceholderText("keyword…")
        self._sel_tag_keyword.setToolTip(
            "Case-insensitive substring match against each node's tag text."
        )
        self._sel_tag_keyword.returnPressed.connect(self._on_select_by_tag)

        self._sel_tag_btn = QPushButton("Select Matching Tags")
        self._sel_tag_btn.setToolTip(
            "Select every node whose tag text contains the keyword above.\n"
            "Uses the same 'Add to current selection' checkbox as Select All Matching."
        )
        self._sel_tag_btn.clicked.connect(self._on_select_by_tag)

        sel_layout.addRow("Tag contains:", self._sel_tag_keyword)
        sel_layout.addRow(self._sel_tag_btn)

        # Render-only toggle for the yellow halo — lives here rather than in
        # the Display group because it is what you reach for while working
        # with a selection (View > Show Selection Box mirrors it).
        self._cb_selbox = QCheckBox("Show selection box")
        self._cb_selbox.setChecked(True)   # matches Viewport.show_selection_box
        self._cb_selbox.setToolTip(
            "Draw the yellow bounding box around selected nodes.\n"
            "Uncheck for a clean screengrab of a chosen state without having\n"
            "to deselect — the selection stays live, so Move/Rotate/Size and\n"
            "the selection keys keep working.  [Ctrl+B]"
        )
        self._cb_selbox.toggled.connect(self._set_selection_box)
        sel_layout.addRow(self._cb_selbox)

        # --- Visibility group ---
        # All four operate on the per-node hide flag (the table's Hide column,
        # saved to CSV). Hiding is strictly per-node: a hidden parent never
        # hides its children — each node's own flag alone decides.
        vis_grp = QGroupBox("Visibility")
        vis_layout = QVBoxLayout(vis_grp)

        self._btn_hide_sel = QPushButton("Hide Selected")
        self._btn_hide_sel.setToolTip(
            "Hide the selected node(s)  [H]\n"
            "Sets each node's own hide flag — children of a hidden node\n"
            "stay visible unless hidden themselves. The selection is kept,\n"
            "so Show Selected undoes this immediately."
        )
        self._btn_hide_sel.clicked.connect(self._hide_selected)

        self._btn_show_sel = QPushButton("Show Selected")
        self._btn_show_sel.setToolTip(
            "Clear the hide flag on the selected node(s).\n"
            "Tip: check 'Show Hidden Nodes' (Display group) to see and\n"
            "select hidden nodes in the 3D view; the table always shows them."
        )
        self._btn_show_sel.clicked.connect(self._show_selected)

        self._btn_isolate = QPushButton("Show Only Selected")
        self._btn_isolate.setToolTip(
            "Isolate the selection: hide every other node in one step  [I]\n"
            "(equivalent to Invert Selection + Hide Selected, without\n"
            "disturbing the current selection)."
        )
        self._btn_isolate.clicked.connect(self._isolate_selected)

        self._btn_show_all = QPushButton("Show All")
        self._btn_show_all.setToolTip(
            "Clear the hide flag on every node in the scene  [Shift+H]"
        )
        self._btn_show_all.clicked.connect(self._show_all)

        for btn in (self._btn_hide_sel, self._btn_show_sel, self._btn_isolate):
            btn.setEnabled(False)   # enabled once there's a selection

        vis_layout.addWidget(self._btn_hide_sel)
        vis_layout.addWidget(self._btn_show_sel)
        vis_layout.addWidget(self._btn_isolate)
        vis_layout.addWidget(self._btn_show_all)

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
            "Keep the three scale axes tied together.\n"
            "In these boxes: editing one axis sets all three to the same value.\n"
            "In Size mode: dragging any handle (or any free-form Size drag)\n"
            "applies the same factor to all three, so the glyph keeps its\n"
            "proportions rather than being flattened to a cube."
        )
        self._insp_scale_lock.toggled.connect(self._on_scale_lock_toggled)

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
        self._insp_rotate_rate_z.setToolTip(
            self._insp_rotate_rate_z.toolTip() + "\nOn a Link set to Prism "
            "(Textured) geometry, this field doubles up as texture scroll "
            "rate instead: nonzero values flow the texture along the link "
            "(sign sets direction, A-end to B-end when positive) to indicate "
            "directed-graph edge direction."
        )

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
        # Above 1.0 only means anything as a Link/Prism thickness — a torus
        # ratio is a proportion of its own radius, so >1 is degenerate there —
        # but a link spanning tens of world units needs a thickness to match,
        # and the CSV column was never capped. You have to type past 1.0.
        self._insp_ratio.setRange(0.01, 10.0)
        self._insp_ratio.setDecimals(3)
        self._insp_ratio.setSingleStep(0.01)
        self._insp_ratio.setToolTip(
            "Torus minor-radius proportion (GaiaViz/ANTz 'ratio'): the tube "
            "radius as a fraction of the torus's overall radius. Also used to "
            "place children riding on a Torus-topology parent's surface.\n"
            "On other glyphs this field doubles up: Point geometry uses it as "
            "an on-screen sprite size, and Plot-parent nodes use it as line "
            "width (ratio * 20, in pixels).\n"
            "On a Link it is the connector's THICKNESS, whatever geometry the "
            "link carries: line width in pixels for Line geometry, and the "
            "world-space half-width on both cross-axes for Prism (Textured) "
            "or any glyph geometry stretched between the link's two ends "
            "(the link's own scale fields play no part)."
        )
        self._insp_ratio.valueChanged.connect(self._on_insp_ratio_changed)

        self._insp_geo = QComboBox()
        for geo_id in range(GEO_COUNT):
            if geo_id == GEO_MESH:
                continue  # each imported mesh gets its own entry (_add_mesh_combo_entry)
            self._insp_geo.addItem(GEO_NAMES[geo_id], geo_id)
        self._insp_geo.currentIndexChanged.connect(self._on_insp_geo_changed)

        self._insp_topo = QComboBox()
        for topo_id in range(TOPO_COUNT):
            self._insp_topo.addItem(TOPO_NAMES.get(topo_id, f"Topology {topo_id}"), topo_id)
        self._insp_topo.currentIndexChanged.connect(self._on_insp_topo_changed)

        # Topology Scale (Node.topo_scale) — sits directly under Topology
        # because it describes the same thing: this node's coordinate system
        # for its children. Spin box for an exact value, log slider to feel
        # for one, and two preset buttons for the values that mean something.
        topo_scale_widget = QWidget()
        topo_scale_layout = QHBoxLayout(topo_scale_widget)
        topo_scale_layout.setContentsMargins(0, 0, 0, 0)
        topo_scale_layout.setSpacing(4)
        self._insp_topo_scale = QDoubleSpinBox()
        self._insp_topo_scale.setRange(_TOPO_SCALE_MIN, _TOPO_SCALE_MAX)
        self._insp_topo_scale.setDecimals(6)
        self._insp_topo_scale.setStepType(
            QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        self._insp_topo_scale.setKeyboardTracking(False)
        self._insp_topo_scale.setMaximumWidth(90)
        self._insp_topo_scale.valueChanged.connect(self._on_insp_topo_scale_changed)
        self._insp_topo_scale_slider = QSlider(Qt.Orientation.Horizontal)
        self._insp_topo_scale_slider.setRange(0, _TOPO_SCALE_SLIDER_MAX)
        self._insp_topo_scale_slider.setTickInterval(_TOPO_SCALE_STEPS_PER_DECADE)
        self._insp_topo_scale_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._insp_topo_scale_slider.valueChanged.connect(
            self._on_insp_topo_scale_slider)
        self._insp_topo_scale_one = QPushButton("1:1")
        self._insp_topo_scale_one.setMaximumWidth(34)
        self._insp_topo_scale_one.setToolTip(
            "Back to 1.0: one translate unit = one world unit.\n"
            "GlyphViz's original behavior, and what every file that has no\n"
            "topo_scale column loads as."
        )
        self._insp_topo_scale_one.clicked.connect(
            lambda: self._set_insp_topo_scale(DEFAULT_TOPO_SCALE))
        self._insp_topo_scale_antz = QPushButton("ANTz")
        self._insp_topo_scale_antz.setMaximumWidth(44)
        self._insp_topo_scale_antz.setToolTip(
            f"ANTz convention ({TOPO_SCALE_ANTZ:.6f} = 1/180): a linear axis\n"
            "spans this glyph's own extent, so translate 180 reaches the edge\n"
            "of a cube facet just as 180 degrees of longitude reaches the far\n"
            "side of a sphere.\n"
            "This is the setting at which switching between an angular and a\n"
            "linear topology leaves the children roughly where they were."
        )
        self._insp_topo_scale_antz.clicked.connect(
            lambda: self._set_insp_topo_scale(TOPO_SCALE_ANTZ))
        topo_scale_layout.addWidget(self._insp_topo_scale)
        topo_scale_layout.addWidget(self._insp_topo_scale_slider, 1)
        topo_scale_layout.addWidget(self._insp_topo_scale_one)
        topo_scale_layout.addWidget(self._insp_topo_scale_antz)
        for w in (topo_scale_widget, self._insp_topo_scale,
                  self._insp_topo_scale_slider):
            w.setToolTip(
                "How far one unit of a CHILD's translate reaches, for the axes\n"
                "this node's topology reads as a DISTANCE rather than an angle\n"
                "(a Cube facet's two axes, Pin/Cylinder height, altitude above\n"
                "a Sphere, all three axes of a plain Cartesian topology).\n"
                "\n"
                "Longitude, latitude, orbital and tube angles are never scaled,\n"
                "so this can never distort a circular layout — turn it down and\n"
                "a sphere's children stay exactly on the sphere.\n"
                "\n"
                f"1.0 = one translate unit is one world unit (the default).\n"
                f"{TOPO_SCALE_ANTZ:.6f} = ANTz (360 units across a cube facet).\n"
                "\n"
                "Set on the PARENT — it describes that node's coordinate\n"
                "system, the same way Topology and Ratio do. Turn it down when\n"
                "children authored in degrees fly off under a linear topology."
            )

        self._insp_subspace = QComboBox()
        for face_id, face_name in enumerate(CUBE_FACE_NAMES):
            self._insp_subspace.addItem(f"{face_id}: {face_name}", face_id)
        self._insp_subspace.setToolTip(
            "Which cube face this node sits on, when its PARENT uses the Cube "
            "or Zcube topology (ignored otherwise)."
        )
        self._insp_subspace.currentIndexChanged.connect(self._on_insp_subspace_changed)

        self._insp_palette = QComboBox()
        for pid in sorted(PALETTE_NAMES):
            self._insp_palette.addItem(PALETTE_NAMES[pid], pid)
        self._insp_palette.setToolTip(
            "Color palette used by the =/- and Alt+=/Alt+- cycle keys. "
            "Changing this re-resolves the node's color from the new "
            "palette at the current Color Index."
        )
        self._insp_palette.currentIndexChanged.connect(self._on_insp_palette_changed)

        self._insp_color_index = QSpinBox()
        self._insp_color_index.setRange(0, 127)
        self._insp_color_index.setToolTip(
            "Index within the active palette (=/- keys step this). "
            "Immediately resolves to a literal color_r/g/b — opening the "
            "Color picker below then overrides that until you cycle again."
        )
        self._insp_color_index.valueChanged.connect(self._on_insp_color_index_changed)

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

        self._insp_show_text = QCheckBox("Always Show Text")
        self._insp_show_text.setToolTip(
            "Keep this node's tag text on screen no matter how the scene-wide\n"
            "tag settings are set — neither 'Show Tag Labels' nor 'Show Tag\n"
            "Labels of Selected' can turn it off, and it is exempt from the\n"
            "all-tags frame cap. Hiding the node still hides its text.\n"
            "Applies to every selected node. Saved with the scene (show_text)."
        )
        # 'clicked' rather than 'toggled': a mixed selection shows the box
        # partially-checked, and only a real click should push one value onto
        # every selected node.
        self._insp_show_text.clicked.connect(self._on_insp_show_text_toggled)

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
        insp_layout.addRow("Topo Scale:", topo_scale_widget)
        insp_layout.addRow("Facet:",    self._insp_subspace)
        insp_layout.addRow("Ratio:",    self._insp_ratio)
        insp_layout.addRow("Texture ID:", self._insp_texture_id)
        insp_layout.addRow("Palette:",  self._insp_palette)
        insp_layout.addRow("Color Index:", self._insp_color_index)
        insp_layout.addRow("Color:",    self._insp_color_btn)
        insp_layout.addRow("Tag Text:", self._insp_text)
        insp_layout.addRow("",          self._insp_show_text)
        insp_layout.addRow("Link:",     self._insp_link)

        # --- World Grid group: extents window + grid lines for a selected
        # type-6 node (see Node.grid_extents / grid_segments). Enabled only
        # when exactly one World Grid is selected; the G key selects/cycles
        # grids since they're deliberately not click-pickable.
        self._grid_grp = QGroupBox("World Grid")
        self._grid_grp.setEnabled(False)
        self._grid_grp.setToolTip(
            "Coordinate window of the selected World Grid. Children place by\n"
            "these coordinates: X = longitude, Y = latitude, Z = elevation.\n"
            "Shrink the window to a region (e.g. -125..-66, 24..49 for the\n"
            "contiguous US) and raw lon/lat data lands on it directly — no\n"
            "coordinate transforms needed. Use the grid's Scale to zoom the\n"
            "layout and set aspect ratio; children re-space but never resize."
        )
        grid_form = QFormLayout(self._grid_grp)
        grid_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        lon_widget = QWidget()
        lon_layout = QHBoxLayout(lon_widget)
        lon_layout.setContentsMargins(0, 0, 0, 0)
        lon_layout.setSpacing(4)
        self._grid_lon_min = QDoubleSpinBox()
        self._grid_lon_max = QDoubleSpinBox()
        lat_widget = QWidget()
        lat_layout = QHBoxLayout(lat_widget)
        lat_layout.setContentsMargins(0, 0, 0, 0)
        lat_layout.setSpacing(4)
        self._grid_lat_min = QDoubleSpinBox()
        self._grid_lat_max = QDoubleSpinBox()
        for sb in (self._grid_lon_min, self._grid_lon_max,
                   self._grid_lat_min, self._grid_lat_max):
            sb.setRange(-1_000_000.0, 1_000_000.0)
            sb.setDecimals(3)
            sb.setSingleStep(1.0)
            sb.valueChanged.connect(self._on_grid_extents_changed)
        lon_layout.addWidget(self._grid_lon_min)
        lon_layout.addWidget(self._grid_lon_max)
        lat_layout.addWidget(self._grid_lat_min)
        lat_layout.addWidget(self._grid_lat_max)

        seg_widget = QWidget()
        seg_layout = QHBoxLayout(seg_widget)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(4)
        self._grid_seg_x = QSpinBox()
        self._grid_seg_y = QSpinBox()
        for sb in (self._grid_seg_x, self._grid_seg_y):
            sb.setRange(1, 3600)
            sb.setToolTip("Grid cell counts (ANTz segments_x/y). 1 = plain rectangle outline.")
            sb.valueChanged.connect(self._on_grid_segments_changed)
        seg_layout.addWidget(self._grid_seg_x)
        seg_layout.addWidget(self._grid_seg_y)

        self._grid_shape = QComboBox()
        self._grid_shape.addItem("Flat Rectangle", "flat")
        self._grid_shape.addItem("Globe (Sphere)", "globe")
        self._grid_shape.setToolTip(
            "Flat Rectangle: children place Cartesian within the lon/lat\n"
            "window below (X=lon, Y=lat, Z=elevation above the plane).\n"
            "Globe: the same children wrap onto a sphere at their absolute\n"
            "lon/lat, Z becomes radial elevation. Radius is 180/π (~57.3)\n"
            "world units at scale 1, so the equator is exactly 360 units —\n"
            "the flat 1:1 map rolled up. Equivalent to switching the grid's\n"
            "Geometry between Grid and Sphere (wire/solid is preserved);\n"
            "solid + an equirectangular texture gives a textured earth."
        )
        self._grid_shape.currentIndexChanged.connect(self._on_grid_shape_changed)

        self._grid_basemap_btn = QPushButton("Fetch Basemap…")
        self._grid_basemap_btn.setToolTip(
            "Download a map image (OpenStreetMap, satellite, or terrain) for\n"
            "this grid: the lon/lat window is prefilled from the grid's\n"
            "children, the map is reprojected to line up exactly with child\n"
            "placement, saved into the scene's media/ folder, and applied as\n"
            "the grid's texture. Free services, no API key; tiles are cached\n"
            "so refetches don't re-download."
        )
        self._grid_basemap_btn.clicked.connect(self._on_fetch_basemap)

        grid_form.addRow("Shape:", self._grid_shape)
        grid_form.addRow("Lon Min/Max:", lon_widget)
        grid_form.addRow("Lat Min/Max:", lat_widget)
        grid_form.addRow("Grid Cells (X,Y):", seg_widget)
        grid_form.addRow("", self._grid_basemap_btn)

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
        # Desired playback rate. The display box shows the *setting*; the
        # actually-achieved rate (which may be lower on heavy scenes) is the
        # status bar's fps readout.
        self._ch_fps = QSlider(Qt.Orientation.Horizontal)
        self._ch_fps.setRange(1, 30)
        self._ch_fps.setValue(30)   # matches the previous spinbox default
        self._ch_fps.setTickInterval(5)
        self._ch_fps.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._ch_fps.setToolTip("Desired playback speed in frames per second")
        self._ch_fps.valueChanged.connect(self._ch_update_fps)
        self._ch_fps_display = QLineEdit("30 fps")
        self._ch_fps_display.setReadOnly(True)
        self._ch_fps_display.setFixedWidth(52)
        self._ch_fps_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ch_fps_display.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._ch_fps_display.setToolTip(
            "The desired FPS setting (actual playback may be slower on heavy scenes)")
        ch_fps_layout.addWidget(self._ch_fps, 1)
        ch_fps_layout.addWidget(self._ch_fps_display)

        self._ch_loop = QCheckBox("Loop")
        self._ch_loop.setChecked(True)

        ch_layout.addWidget(self._ch_frame_label)
        ch_layout.addWidget(self._ch_slider)
        ch_layout.addWidget(ch_btn_row)
        ch_layout.addWidget(ch_fps_row)
        ch_layout.addWidget(self._ch_loop)

        layout.addWidget(disp)
        layout.addWidget(scale_grp)
        layout.addWidget(stereo_grp)
        layout.addWidget(camera_grp)
        layout.addWidget(scene_grp)
        layout.addWidget(stats_grp)
        layout.addWidget(create_grp)
        layout.addWidget(delete_grp)
        layout.addWidget(sel_grp)
        layout.addWidget(vis_grp)
        layout.addWidget(self._insp_grp)
        layout.addWidget(self._grid_grp)
        layout.addWidget(self._ch_grp)
        layout.addStretch()

        scroll.setWidget(panel)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self._view_menu.addSeparator()
        # Window-wide shortcut on the dock's own toggle action, so it shows
        # (and stays discoverable) next to the View-menu entry and works with
        # the panel closed — e.g. reopening Properties while in stereo 3D.
        toggle = dock.toggleViewAction()
        toggle.setShortcut("Ctrl+P")
        self._view_menu.addAction(toggle)

    def _build_table(self):
        dock = QDockWidget("Node Table", self)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )

        self._table = NodeTableView()
        dock.setWidget(self._table)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        toggle = dock.toggleViewAction()
        toggle.setShortcut("Ctrl+N")   # bare N/Shift+N (new node) are viewport keys; Ctrl+N is free
        self._view_menu.addAction(toggle)

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
        self._load_csv_path(path)

    def _load_csv_path(self, path: str) -> bool:
        """Open *path* as the current scene. Shared by File > Open and drag and
        drop; returns True on success so a drop can report per-file results."""
        try:
            self._ch_stop()
            self.nodes = load_node_csv(path)
            self._current_path = path
            self._current_tag_path = None
            self._path_is_stamped = False
            self._watch_mtime = self._file_mtime(path)
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
            return True
        except Exception as exc:
            self.statusBar().showMessage(f"Error: {exc}")
            return False

    def _merge_csv(self):
        """File > Merge Node CSV… (Ctrl+M): load a second node CSV (plus its
        companion tag file, which load_node_csv picks up automatically) INTO
        the current scene rather than replacing it.

        The incoming nodes are rebased onto fresh ids above everything already
        loaded (see glyphviz_core.scene_merge.merge_nodes) and appended in
        place, so the camera, the current texture set, and any running
        Channels playback all survive. Coordinates are preserved, so the two
        scenes overlay in the same world space.
        """
        start = str(Path(self._current_path).parent) if self._current_path else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Merge Node CSV into Current Scene",
            start,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return
        self._merge_csv_path(path)

    def _merge_csv_path(self, path: str) -> bool:
        """Merge *path* into the current scene. Shared by File > Merge and
        Shift+drop; returns True when nodes were actually added."""
        try:
            incoming = load_node_csv(path)
        except Exception as exc:
            self.statusBar().showMessage(f"Merge failed: {exc}")
            return False
        if not incoming:
            self.statusBar().showMessage(f"Merge: {Path(path).name} has no node rows.")
            return False

        result = merge_nodes(self.nodes, incoming)
        if not result.nodes:
            self.statusBar().showMessage(
                f"Merge: nothing to add from {Path(path).name} "
                "(only per-file World/Camera rows, already present here)."
            )
            return False

        # A merge is a manual edit of the in-memory scene; leaving Watch and
        # Reload armed would silently throw it away on the next disk change.
        if self._watch_act.isChecked():
            self._watch_act.setChecked(False)
            self._toggle_watch_reload(False)

        self.nodes.extend(result.nodes)          # same list object as _scene.nodes
        self._viewport.register_nodes(result.nodes)
        self._table.set_nodes(self.nodes)
        self._on_table_selection()               # model reset drops the old selection silently
        self._update_stats()
        self._update_sel_values()
        self._table.select_by_ids({n.id for n in result.nodes})

        msg = (f"Merged {result.count} node(s) from {Path(path).name} "
               f"— {len(self.nodes)} nodes total")
        msg += self._merge_notes(path, result)
        self.statusBar().showMessage(msg)
        return True

    def _merge_notes(self, path: str, result) -> str:
        """Trailing ' | …' notes for the merge status line: what was dropped or
        rewritten, and the two things a merge deliberately does NOT carry over
        (the incoming file's texture set and its Channels animation), each
        reported only when that file actually has them."""
        notes = []
        if result.skipped_global:
            notes.append(f"skipped {result.skipped_global} World/Camera row(s)")
        if result.dropped_links:
            notes.append(f"dropped {result.dropped_links} link(s) with an outside B-end")
        if result.rerooted:
            notes.append(f"re-rooted {result.rerooted} orphan(s)")
        if result.cleared_channels:
            notes.append(f"cleared channel bindings on {result.cleared_channels} node(s)")
        # Textures: the merged nodes' texture_id values index the incoming
        # file's own media/ folder, which load_texture_folder would have to
        # REPLACE the current set to honour — so merging leaves textures alone.
        incoming_media = Path(path).parent / "media"
        current_media = self._viewport.texture_folder
        if (any(n.texture_id for n in result.nodes) and incoming_media.is_dir()
                and (current_media is None or Path(current_media) != incoming_media)):
            notes.append(f"textures not loaded from {incoming_media.parent.name}/media/")
        from glyphviz_core.channel_loader import find_channel_files
        map_path, tracks_path = find_channel_files(path)
        if map_path and tracks_path:
            notes.append("Channels animation not merged")
        return (" | " + "; ".join(notes)) if notes else ""

    # --- Drag and drop ---
    #
    # Dropping a node CSV, a scene folder, or a zip of one loads it the same
    # way File > Open would — the tag file, ch-map/ch-tracks pair, audio
    # manifest, and media/ textures all come along, because every one of those
    # is discovered from the node CSV's own path. Shift held during the drop
    # merges instead of replacing, mirroring Ctrl+M. All the routing decisions
    # live in glyphviz_core.drop_router so they're testable without Qt.

    @staticmethod
    def _dropped_paths(mime) -> list[str]:
        """Local file-system paths from a drop's mime data (URLs that aren't
        local files — a link dragged from a browser — yield '' and are
        dropped here rather than confusing the router)."""
        if not mime.hasUrls():
            return []
        return [p for p in (u.toLocalFile() for u in mime.urls()) if p]

    def dragEnterEvent(self, event):
        paths = self._dropped_paths(event.mimeData())
        if paths and can_accept(paths):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        # Qt needs the move accepted too, or the cursor shows "no drop" over
        # child widgets even though dragEnterEvent said yes.
        if self._dropped_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = self._dropped_paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        merge = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        # Defer the actual load: the drag SOURCE (Explorer) stays blocked until
        # dropEvent returns, and unzipping a big example is not a wait to hand
        # someone else's window. Returning first also lets this status line
        # paint before the load takes over the thread.
        self.statusBar().showMessage("Loading dropped item(s)…")
        QTimer.singleShot(0, lambda: self.apply_drop(paths, merge=merge))

    def apply_drop(self, paths: list[str], merge: bool = False) -> DropPlan:
        """Resolve dropped paths and carry out the plan.

        Separate from dropEvent so tests can exercise the whole path — router
        through real loaders — without synthesising Qt drag events. Returns the
        plan so a caller can see what was done.
        """
        plan = resolve_drop(paths, merge=merge)

        if plan.is_empty:
            reason = "; ".join(plan.errors) if plan.errors else "nothing loadable in that drop"
            self.statusBar().showMessage(f"Drop: {reason}")
            return plan

        loaded = 0
        for action in plan.actions:
            path = str(action.path)
            if action.kind == ACTION_OPEN_CSV:
                ok = self._load_csv_path(path)
            elif action.kind == ACTION_MERGE_CSV:
                ok = self._merge_csv_path(path)
            elif action.kind == ACTION_PDB:
                ok = self._load_pdb_path(path)
            elif action.kind == ACTION_MESH:
                ok = self._load_mesh_path(path)
            elif action.kind == ACTION_TEXTURES:
                self._apply_texture_folder(action.path, silent=True)
                ok = True
            else:
                ok = False
            loaded += bool(ok)

        # Each loader wrote its own status line; append what the routing
        # decided on top of it, so "why did it open THAT file" is answerable.
        notes = plan.notes + plan.errors
        if notes:
            base = self.statusBar().currentMessage()
            self.statusBar().showMessage(f"{base} | drop: {'; '.join(notes)}")
        return plan

    # --- Watch and Reload ---

    @staticmethod
    def _file_mtime(path: str) -> float | None:
        try:
            return Path(path).stat().st_mtime
        except OSError:
            return None

    def _toggle_watch_reload(self, checked: bool):
        if checked and self._current_path is None:
            self._watch_act.setChecked(False)
            self.statusBar().showMessage(
                "Watch and Reload: open a node CSV first.")
            return
        if checked:
            self._watch_mtime = self._file_mtime(self._current_path)
            self._watch_timer.start()
            self.statusBar().showMessage(
                f"Watching {Path(self._current_path).name} — the scene will "
                "reload whenever the file changes on disk.")
        else:
            self._watch_timer.stop()
            self.statusBar().showMessage("Watch and Reload off.")

    def _watch_tick(self):
        if self._current_path is None:
            return
        m = self._file_mtime(self._current_path)
        if m is None:
            # File briefly missing (generator mid-replace): keep waiting.
            return
        if self._watch_mtime is None or m > self._watch_mtime:
            if self._reload_current_csv():
                self._watch_mtime = m

    def _reload_current_csv(self) -> bool:
        """Hot-reload the current node CSV (+ companion tag/channel files)
        in place, preserving camera, selection, and Channels playback.
        Returns False (keeping the old scene) if the file can't be parsed —
        e.g. a non-atomic writer caught mid-write; the next tick retries."""
        path = self._current_path
        try:
            nodes = load_node_csv(path)
        except Exception as exc:
            self.statusBar().showMessage(
                f"Watch: reload failed, keeping current scene ({exc})")
            return False
        cam = self._viewport.camera_state()
        sel_ids = {n.id for n in self._selected_nodes}
        was_playing = self._ch_playing
        prev_frame = self._ch_frame
        self._ch_stop()
        self.nodes = nodes
        self._viewport.set_nodes(self.nodes)
        self._table.set_nodes(self.nodes)
        self._update_stats(Path(path).name)
        self._update_sel_values()
        self._refresh_scene_settings()
        ch_msg = self._ch_load_from_csv(path)
        self._viewport.restore_camera_state(cam)
        keep = sel_ids & {n.id for n in self.nodes}
        if keep:
            self._table.select_by_ids(keep)
        if was_playing and self._ch_engine is not None:
            self._ch_frame = min(prev_frame, self._ch_engine.frame_count - 1)
            self._ch_apply_and_show_frame(self._ch_frame)
            self._ch_toggle_play()
        msg = f"Reloaded {len(self.nodes)} nodes from {Path(path).name}"
        if ch_msg:
            msg += f" | {ch_msg}"
        self.statusBar().showMessage(msg + "  [watching]")
        return True

    def _import_pdb_file(self):
        """File > Import PDB File…: parse a .pdb structure into atom/bond
        nodes and load it as the current scene (same bulk-replace pattern as
        _open_csv, since a protein can be thousands of nodes)."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import PDB File", str(Path.home()),
            "PDB Files (*.pdb);;All Files (*)",
        )
        if not path:
            return
        self._load_pdb_path(path)

    def _load_pdb_path(self, path: str) -> bool:
        """Import *path* as the current scene. Shared by File > Import PDB and
        drag and drop."""
        try:
            self._ch_stop()
            result = load_pdb_file(path)
            self.nodes = result.nodes
            self._current_path = None
            self._current_tag_path = None
            self._path_is_stamped = False
            self._save_act.setEnabled(False)
            self._viewport.set_nodes(self.nodes)
            self._table.set_nodes(self.nodes)
            self._update_stats(Path(path).name)
            self._update_sel_values()
            self._refresh_scene_settings()
            self.statusBar().showMessage(
                f"Imported {result.atom_count} atoms, {result.bond_count} bonds, "
                f"{result.chain_count} chain(s) from {Path(path).name}"
            )
            return True
        except Exception as exc:
            self.statusBar().showMessage(f"PDB import failed: {exc}")
            return False

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

    def _load_default_media(self):
        """Load textures from a media/ folder next to the app itself (the
        frozen executable's folder, or main.py's when running from source) as
        the startup default, matching ANTz's app-relative usr/images
        convention. Runs on the viewport's glInitialized signal — any earlier
        and the GL uploads silently produce zero textures. A media/ folder
        next to a subsequently opened CSV still takes precedence (_open_csv);
        the guard below keeps a context recreation from clobbering it."""
        if self._viewport.texture_folder is not None:
            return
        folder = _app_dir() / "media"
        if folder.is_dir():
            self._apply_texture_folder(folder, silent=True)
            self.statusBar().showMessage(
                f"Loaded {self._viewport.texture_count} texture(s) from app media/ folder"
            )

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

    def _on_glyph_composer(self):
        from .glyph_composer_dialog import GlyphComposerDialog
        dlg = GlyphComposerDialog(self, parent=self)
        dlg.exec()

    def _on_hyperglyph_generator(self):
        from .hyperglyph_dialog import HyperglyphGeneratorDialog
        dlg = HyperglyphGeneratorDialog(self, parent=self)
        dlg.exec()

    def _toggle_rates_paused(self, checked: bool):
        """Freeze (or unfreeze) every node's translate_rate/rotate_rate/
        scale_rate in place. Zeroing the real Node fields (rather than a
        purely visual pause) means a Save while paused writes a genuinely
        static file; resuming restores the exact original values."""
        if checked:
            self._paused_rate_snapshot.clear()
            for n in self.nodes:
                rates = (
                    n.translate_rate_x, n.translate_rate_y, n.translate_rate_z,
                    n.rotate_rate_x, n.rotate_rate_y, n.rotate_rate_z,
                    n.scale_rate_x, n.scale_rate_y, n.scale_rate_z,
                )
                if any(rates):
                    self._paused_rate_snapshot[n.id] = rates
                    n.translate_rate_x = n.translate_rate_y = n.translate_rate_z = 0.0
                    n.rotate_rate_x = n.rotate_rate_y = n.rotate_rate_z = 0.0
                    n.scale_rate_x = n.scale_rate_y = n.scale_rate_z = 0.0
            self._rates_paused = True
            self.statusBar().showMessage(
                f"Rate animation paused ({len(self._paused_rate_snapshot)} node(s) frozen) — "
                "Save now to write a static snapshot."
            )
        else:
            by_id = {n.id: n for n in self.nodes}
            for node_id, rates in self._paused_rate_snapshot.items():
                n = by_id.get(node_id)
                if n is None:
                    continue
                (n.translate_rate_x, n.translate_rate_y, n.translate_rate_z,
                 n.rotate_rate_x, n.rotate_rate_y, n.rotate_rate_z,
                 n.scale_rate_x, n.scale_rate_y, n.scale_rate_z) = rates
            self._paused_rate_snapshot.clear()
            self._rates_paused = False
            self.statusBar().showMessage("Rate animation resumed.")
        self._pause_rates_act.setChecked(checked)
        self._viewport.refresh_animation_state()
        self._viewport.update()

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
        self._load_mesh_path(path)

    def _load_mesh_path(self, path: str) -> bool:
        """Import *path* as a GEO_MESH shape. Shared by Meshes > Import Mesh
        File and drag and drop."""
        if len(self._selected_nodes) > 1:
            self.statusBar().showMessage("Select exactly one node (or none) as the import target.")
            return False
        try:
            mesh_id = self._viewport.load_mesh_file(path)
        except Exception as exc:
            self.statusBar().showMessage(f"Mesh import failed: {exc}")
            return False
        name = self._viewport.mesh_name(mesh_id)
        self._add_mesh_combo_entry(mesh_id)

        if len(self._selected_nodes) == 1:
            node = self._selected_nodes[0]
            node.geometry = GEO_MESH
            node.mesh_id = mesh_id
            self._table.refresh_node(node.id)
            self._update_sel_values()
            self._viewport.scene_invalidate()
            self.statusBar().showMessage(f"Assigned mesh '{name}' (id {mesh_id}) to node {node.id}.")
            return True

        next_x, next_y = self._next_root_pos()
        new_id = max((n.id for n in self.nodes), default=0) + 1
        self._add_node_to_scene(Node(
            id=new_id, type=5, parent_id=0, branch_level=0,
            translate_x=next_x, translate_y=next_y,
            translate_z=self._placement_z(is_child=False),
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=5.0, scale_y=5.0, scale_z=5.0,
            color_r=200, color_g=200, color_b=200, color_a=255,
            geometry=GEO_MESH, hide=0, topo=0, mesh_id=mesh_id,
        ))
        self.statusBar().showMessage(f"Imported mesh '{name}' (id {mesh_id}) as new node {new_id}.")
        return True

    # --- Imported-mesh entries in the geometry dropdowns ---
    #
    # Built-in geometries store a plain int geo_id as the combo item's data;
    # each imported mesh gets its own item whose data is the (GEO_MESH,
    # mesh_id) tuple, so picking it sets BOTH fields on the node — GEO_MESH
    # alone renders as the sphere fallback when mesh_id doesn't name a
    # loaded mesh (see GeoRenderer.draw).

    def _mesh_combo_label(self, mesh_id: int) -> str:
        name = self._viewport.mesh_name(mesh_id)
        return f"Mesh {mesh_id}: {name}" if name else f"Mesh {mesh_id} (not loaded)"

    def _add_mesh_combo_entry(self, mesh_id: int):
        """Add (or re-label) this mesh's entry in every geometry dropdown."""
        data = (GEO_MESH, mesh_id)
        label = self._mesh_combo_label(mesh_id)
        for combo in (self._new_geo, self._insp_geo):
            idx = next((i for i in range(combo.count()) if combo.itemData(i) == data), -1)
            if idx >= 0:
                combo.setItemText(idx, label)
            else:
                combo.addItem(label, data)

    def _geo_combo_index(self, combo: QComboBox, geo: int, mesh_id: int) -> int:
        """Combo index showing this node's geometry. For GEO_MESH nodes whose
        mesh_id has no entry yet (a CSV saved with meshes, reopened before
        re-importing the files), a '(not loaded)' entry is added on demand so
        the inspector doesn't misreport the geometry as Cube Wire."""
        if geo != GEO_MESH:
            return combo.findData(geo)
        self._add_mesh_combo_entry(mesh_id)
        data = (GEO_MESH, mesh_id)
        return next((i for i in range(combo.count()) if combo.itemData(i) == data), -1)

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
        self._audio_combo.setEnabled(len(tracks) > 1 and not self._audio_follow_selection)
        self._audio_combo.blockSignals(False)
        self._cb_audio_follow_selection.setEnabled(bool(tracks))
        if self._audio_follow_selection:
            self._update_selection_audio_solo()

    def _on_audio_track_selected(self, index: int):
        if self._audio_follow_selection:
            return
        texture_id = self._audio_combo.itemData(index)
        self._viewport.set_audio_solo(texture_id)

    def _on_audio_follow_selection_toggled(self, checked: bool):
        self._audio_follow_selection = checked
        tracks = self._viewport.list_audio_tracks()
        self._audio_combo.setEnabled(len(tracks) > 1 and not checked)
        if checked:
            self._update_selection_audio_solo()
        else:
            self._on_audio_track_selected(self._audio_combo.currentIndex())

    def _update_selection_audio_solo(self):
        """While 'Solo Audio to Selection' is on, mute every video except
        those textured on currently selected nodes -- multiple selected
        video-textured nodes all play at once; none selected plays none."""
        if not self._audio_follow_selection:
            return
        ids = {
            n.texture_id for n in self._selected_nodes
            if n.texture_id and self._viewport.is_video_texture(n.texture_id)
        }
        self._viewport.set_audio_solo(ids)

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

    def _selection_default_name(self) -> str:
        """Suggested filename for a selection export, keeping the node/tag
        stem convention intact: 'Cyclone_gv_node.csv' suggests
        'Cyclone_gv_selection_node.csv', whose tag companion is
        'Cyclone_gv_selection_tag.csv'."""
        if self._current_path:
            p = Path(self._current_path)
            stem = unstamped_stem(p)
            base = stem[:-4] if stem.endswith('node') else stem + '_'
            return str(p.parent / f"{base}selection_node{p.suffix or '.csv'}")
        return str(Path.home() / "gv_selection_node.csv")

    def _save_selection_as(self):
        """Ctrl+Alt+S — write the selected nodes to a node CSV of their own.

        The options dialog decides membership and how to treat a node whose
        parent stays behind; glyphviz_core.selection_export does the work
        (and explains why a naive subset save is wrong). The tag companion is
        written whenever the chosen filename allows it, regardless of the
        Save Tag File checkbox — that checkbox is about scene saves, and an
        exported fragment silently losing its labels would be data loss.
        """
        ids = {n.id for n in self._selected_nodes}
        if not ids:
            self.statusBar().showMessage("Select one or more nodes first.")
            return

        from glyphviz_core.channel_loader import find_channel_files
        from .save_selection_dialog import SaveSelectionDialog

        scene = self._viewport.scene
        ch_paths = (find_channel_files(self._current_path)
                    if self._current_path else (None, None))
        dlg = SaveSelectionDialog(scene, ids, self,
                                  has_channels=all(p is not None for p in ch_paths))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        export = build_selection(scene, ids, dlg.options)
        if not export.nodes:
            self.statusBar().showMessage("Nothing to save — the selection holds no exportable nodes.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Selection",
            self._selection_default_name(),
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            save_node_csv(export.nodes, path)
            msg = f"Saved {export.count} node(s) to {Path(path).name}"
            tag_path = companion_tag_path(path)
            if any(n.text or n.link for n in export.nodes):
                if tag_path:
                    save_tag_csv(export.nodes, str(tag_path))
                    msg += f" (+ tags to {tag_path.name})"
                else:
                    msg += " (tags skipped: name doesn't end in 'node')"
            if dlg.include_channels:
                msg += self._write_selection_channels(export.nodes, path, ch_paths)
            self.statusBar().showMessage(msg + self._selection_save_notes(export))
        except Exception as exc:
            self.statusBar().showMessage(f"Save Selection error: {exc}")

    def _write_selection_channels(self, nodes, node_path: str, ch_paths) -> str:
        """Companion ch-map/ch-tracks for an exported selection, holding only
        the channels those nodes are bound to. Returns a status fragment.

        The names are derived from the node file's stem the same way the tag
        file's are, so the pair is discoverable by find_channel_files — which
        wants EXACTLY ONE ch-map in the folder, the reason exporting into a
        folder that already holds another scene's companions is a bad idea.
        """
        from glyphviz_core.channel_engine import channel_ids_for_nodes
        from glyphviz_core.channel_loader import export_channel_subset

        ch_ids = channel_ids_for_nodes(nodes)
        if not ch_ids:
            return ""
        p = Path(node_path)
        stem = unstamped_stem(p)
        base = stem[:-4] if stem.endswith('node') else stem + '_'
        out_map = p.parent / f"{base}ch-map{p.suffix or '.csv'}"
        out_tracks = p.parent / f"{base}ch-tracks{p.suffix or '.csv'}"
        channels, tracks = export_channel_subset(
            ch_paths[0], ch_paths[1], ch_ids, out_map, out_tracks)
        if not channels:
            return ""
        return f" (+ {channels} channel(s), {tracks} track(s))"

    def _selection_save_notes(self, export) -> str:
        """Everything the export had to decide on the user's behalf, in one
        trailing clause — re-rooting, dropped links, and the two cases the
        bake can't carry across faithfully (see selection_export)."""
        notes = []
        if export.detached_ids:
            notes.append(f"{len(export.detached_ids)} re-rooted")
        if export.dropped_links:
            notes.append(f"{export.dropped_links} link(s) dropped")
        if export.approximated_ids:
            notes.append(f"{len(export.approximated_ids)} approximated "
                         "(stretched parent — shape can't be carried exactly)")
        if export.animated_detached:
            notes.append(f"{len(export.animated_detached)} with motion rates "
                         "now moving in world space")
        return f" — {', '.join(notes)}." if notes else "."

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
            # No-op everywhere the folder already exists; matters on macOS,
            # where _app_dir() can name a ~/GlyphViz that hasn't been made yet.
            node_path.parent.mkdir(parents=True, exist_ok=True)
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

    def _set_gizmo_handles(self, checked: bool):
        self._viewport.show_gizmo_handles = checked
        self._viewport.update()
        self.statusBar().showMessage(
            "Transform handles shown — drag an axis to constrain the edit."
            if checked else
            "Transform handles hidden (Move/Rotate/Size drags unchanged)."
        )

    def _set_selection_box(self, checked: bool):
        self._viewport.show_selection_box = checked
        self._cb_selbox.setChecked(checked)
        self._selbox_act.setChecked(checked)
        self._viewport.update()
        self.statusBar().showMessage(
            "Selection box shown." if checked
            else "Selection box hidden (selection still active)."
        )

    def _set_tags_selected_only(self, checked: bool):
        self._viewport.show_tags_selected_only = checked
        self._viewport.update()

    def _on_open_link(self):
        """U key: open the selected node's link in the default browser/app."""
        if len(self._selected_nodes) != 1:
            return
        self._open_link_value(self._selected_nodes[0].link.strip())

    def _on_node_link_activated(self, node_id: int):
        """Alt+click in the viewport: open the clicked node's link (the
        mouse counterpart of the U key — see Viewport.nodeLinkActivated)."""
        node = self._node_by_id(node_id)
        if node is not None:
            self._open_link_value(node.link.strip())

    def _open_link_value(self, link: str):
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

    def _set_scale_floor(self, checked: bool):
        """Toggle the opt-in minimum rendered glyph size (scene.scale_floor).

        Kept in sync between the Global Scale panel checkbox and the View
        menu action, the same two-surface pattern _set_hidden uses."""
        self._viewport.enforce_scale_floor = checked
        for w in (self._cb_scale_floor, self._scale_floor_act):
            if w.isChecked() != checked:
                w.blockSignals(True)
                w.setChecked(checked)
                w.blockSignals(False)
        self._viewport.update()
        self.statusBar().showMessage(
            f"Minimum glyph size {DEFAULT_SCALE_FLOOR:g} enforced."
            if checked else
            "Minimum glyph size off — glyphs render at their authored scale.")

    def _set_follow(self, checked: bool):
        self._viewport.follow_selected = checked
        self._viewport.update()

    def _set_stereo(self, checked: bool):
        self._viewport.stereo_mode = checked
        self._cb_stereo.setChecked(checked)
        self._stereo_act.setChecked(checked)
        self._viewport.update()

    def _update_stereo_separation(self, value: int):
        pct = value / 10.0
        self._stereo_sep_label.setText(f"Eye Separation: {pct:.1f}%")
        self._viewport.stereo_separation_pct = pct
        self._viewport.update()

    # --- Camera smoothing ---

    def _set_camera_smoothing_tau(self, tau: float):
        """Apply a preset (Off / ANTz) by moving the slider — the slider's own
        signal does the work, so there is exactly one path to the viewport."""
        self._cam_smooth_slider.setValue(int(round(tau * 100)))
        # setValue is a no-op when the slider is already there (e.g. pressing
        # Off twice), so make the preset idempotent rather than silent.
        self._update_camera_smoothing()

    def _update_camera_smoothing(self, _value: int = 0):
        """Push the slider + scope combo into the viewport and relabel."""
        tau = self._cam_smooth_slider.value() / 100.0
        scope = self._cam_smooth_scope.currentData()
        if tau <= 0.0:
            self._cam_smooth_label.setText("Smoothing: Off")
        else:
            suffix = "  (ANTz)" if abs(tau - cs.TAU_ANTZ) < 0.005 else ""
            self._cam_smooth_label.setText(f"Smoothing: {tau:.2f} s{suffix}")
        self._cam_smooth_scope.setEnabled(tau > 0.0)
        self._viewport.set_camera_smoothing(tau, scope)

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
        nodes = self._selectable_nodes()
        if nodes:
            if criterion == "Branch Level":
                for lv in sorted(set(n.branch_level for n in nodes)):
                    self._sel_value.addItem(str(lv), lv)
            elif criterion == "Geometry":
                for g in sorted(set(n.geometry for n in nodes)):
                    self._sel_value.addItem(f"{g}: {GEO_NAMES.get(g, f'Geo {g}')}", g)
            elif criterion == "Topology":
                for t in sorted(set(n.topo for n in nodes)):
                    self._sel_value.addItem(f"{t}: {TOPO_NAMES.get(t, f'Topo {t}')}", t)
        if current_data is not None:
            idx = self._sel_value.findData(current_data)
            if idx >= 0:
                self._sel_value.setCurrentIndex(idx)
        self._sel_value.blockSignals(False)

    def _selectable_nodes(self) -> list[Node]:
        """Nodes the bulk-selection commands (Select All/Invert/Select By)
        operate on: visual glyphs only. World/Camera config nodes are
        excluded — sweeping the invisible World node into Select All meant a
        bulk color edit silently changed the scene background (its color IS
        the background). World Grids are excluded too: Select-All + Move
        would drag the reference frame along with everything sitting on it,
        double-moving every child. Explicitly clicking such a row in the
        table (or pressing G for grids) still selects and edits it."""
        return [n for n in self.nodes
                if n.type not in NON_VISUAL_TYPES and n.type != NODE_TYPE_GRID]

    def _on_select_by(self):
        criterion = self._sel_criterion.currentText()
        value = self._sel_value.currentData()
        if value is None:
            return
        nodes = self._selectable_nodes()
        if criterion == "Branch Level":
            ids = {n.id for n in nodes if n.branch_level == value}
        elif criterion == "Geometry":
            ids = {n.id for n in nodes if n.geometry == value}
        elif criterion == "Topology":
            ids = {n.id for n in nodes if n.topo == value}
        else:
            return
        if self._sel_cumulative.isChecked():
            self._table.select_add_ids(ids)
        else:
            self._table.select_by_ids(ids)

    def _on_select_by_tag(self):
        """Select every node whose tag text contains the keyword (case-insensitive
        substring match). Deliberately reuses the plain highlight-in-table +
        yellow-bounding-box selection mechanism rather than a separate results
        list, matching every other Select By criterion (Geometry, Topology, ...)."""
        keyword = self._sel_tag_keyword.text().strip()
        if not keyword:
            return
        keyword_lower = keyword.lower()
        ids = {n.id for n in self._selectable_nodes() if keyword_lower in n.text.lower()}
        if self._sel_cumulative.isChecked():
            self._table.select_add_ids(ids)
        else:
            self._table.select_by_ids(ids)
        if ids:
            self.statusBar().showMessage(f'{len(ids)} node(s) tagged with "{keyword}".')
        else:
            self.statusBar().showMessage(f'No nodes tagged with "{keyword}".')

    def _on_select_all(self):
        self._table.select_by_ids({n.id for n in self._selectable_nodes()})

    def _on_deselect_all(self):
        self._table.select_by_ids(set())

    def _on_invert_selection(self):
        """Ctrl+I: select every table row that is not currently selected."""
        selected_ids = {n.id for n in self._selected_nodes}
        self._table.select_by_ids({n.id for n in self._selectable_nodes()} - selected_ids)

    def _on_select_all_toggle(self):
        """Ctrl+A: select all when nothing (or a partial set) is selected; deselect all otherwise."""
        if len(self._selected_nodes) < len(self._selectable_nodes()):
            self._on_select_all()
        else:
            self._on_deselect_all()

    # --- Visibility (per-node hide flag; see the Visibility group tooltips) ---

    def _after_visibility_change(self, changed_ids, message: str):
        """Shared tail for the hide/show operations: repaint (rebake the
        retained list without a transform recompute — hide doesn't move
        anything), refresh the table's Hide column, and update the
        visible-count statusbar stat."""
        self._table.refresh_nodes(changed_ids)
        self._viewport.scene_touch()
        self._update_stats()
        self.statusBar().showMessage(message)

    def _hide_selected(self):
        if not self._selected_nodes:
            self.statusBar().showMessage("No selection to hide.")
            return
        for node in self._selected_nodes:
            node.hide = 1
        # Selection is deliberately kept: hidden-but-selected nodes stay
        # pickable/manipulable (matching ANTz), and Show Selected undoes this.
        self._after_visibility_change(
            [n.id for n in self._selected_nodes],
            f"{len(self._selected_nodes)} node(s) hidden.")

    def _show_selected(self):
        if not self._selected_nodes:
            self.statusBar().showMessage("No selection to show.")
            return
        for node in self._selected_nodes:
            node.hide = 0
        self._after_visibility_change(
            [n.id for n in self._selected_nodes],
            f"{len(self._selected_nodes)} node(s) shown.")

    def _isolate_selected(self):
        """Show only the selected nodes: clear their hide flags, set everyone
        else's. World/camera rows are never drawn, so their flags are left
        untouched rather than silently rewritten in the saved CSV. World
        Grids stay visible too — they're the reference frame under the
        isolated glyphs, not part of the data being inspected."""
        if not self._selected_nodes:
            self.statusBar().showMessage("No selection to isolate.")
            return
        selected_ids = {n.id for n in self._selected_nodes}
        changed = []
        for node in self.nodes:
            if node.type in NON_VISUAL_TYPES or node.type == NODE_TYPE_GRID:
                continue
            new_hide = 0 if node.id in selected_ids else 1
            if node.hide != new_hide:
                node.hide = new_hide
                changed.append(node.id)
        self._after_visibility_change(
            changed, f"Showing only the {len(selected_ids)} selected node(s).")

    def _show_all(self):
        changed = [n.id for n in self.nodes if n.hide]
        for node in self.nodes:
            node.hide = 0
        self._after_visibility_change(
            changed, f"All nodes shown ({len(changed)} unhidden).")

    # --- ANTz-style attribute cycling (O = geometry, J = topology) ---
    #
    # The step is applied PER NODE — each selected node advances from its OWN
    # current value — so a mixed-geometry/topology selection stays mixed
    # instead of snapping to a single shared value (matching ANTz).

    def _cycle_targets(self) -> list[Node]:
        """Nodes the O/J cycling keys operate on: the current selection minus
        World/Camera rows and World Grids. A grid's geometry encodes flat vs
        globe and its topo is ignored, so cycling either would corrupt it —
        use the World Grid panel's Shape combo instead."""
        targets = [n for n in self._selected_nodes
                   if n.type not in NON_VISUAL_TYPES and n.type != NODE_TYPE_GRID]
        if not targets:
            self.statusBar().showMessage("No selection to cycle.")
        return targets

    def _after_attr_cycle(self, targets: list[Node], message: str):
        """Shared tail for the O/J cycles: refresh the table rows and the
        Select-By value combo, re-sync the inspector (its Geometry/Topology
        combos would otherwise show stale values), and rebuild the scene."""
        self._table.refresh_nodes(n.id for n in targets)
        self._update_sel_values()
        if len(self._selected_nodes) == 1:
            self._refresh_inspector(self._selected_nodes[0])
        else:
            self._refresh_inspector_multi(self._selected_nodes)
        self._viewport.scene_invalidate()
        self.statusBar().showMessage(message)

    _LINK_ONLY_GEOS = frozenset({GEO_LINE, GEO_LINE_PRISM})
    # Ids a Link node's O-cycle steps over. GEO_MESH for the same reason every
    # other node type skips it (a bare Mesh id means nothing without a
    # mesh_id); GEO_POINT because a Link renders it as a plain line — a
    # duplicate of the Line mode two stops away, not a distinct look.
    _LINK_SKIP_GEOS = frozenset({GEO_MESH, GEO_POINT})

    def _cycle_selected_geometry(self, step: int):
        """O / Shift+O: step each selected node's geometry forward/back one id.
        GEO_MESH is skipped over — like the Geometry dropdowns, a bare Mesh id
        is meaningless without a mesh_id (imported meshes get their own combo
        entries); a node already ON a mesh still cycles out of it normally.

        A **Link** (type=7) node cycles the same full range, since every
        geometry is meaningful on a link: GEO_LINE/GEO_LINE_PRISM are its two
        line modes and everything else renders as that glyph stretched between
        the link's two ends (link_geometry.py). Ordinary nodes still skip the
        two line ids, where a bare line/prism means nothing."""
        targets = self._cycle_targets()
        if not targets:
            return
        for node in targets:
            skip = (self._LINK_SKIP_GEOS if node.type == NODE_TYPE_LINK
                    else self._LINK_ONLY_GEOS | {GEO_MESH})
            geo = (node.geometry + step) % GEO_COUNT
            while geo in skip:
                geo = (geo + step) % GEO_COUNT
            node.geometry = geo
        if len(targets) == 1:
            g = targets[0].geometry
            msg = f"Geometry → {g}: {GEO_NAMES.get(g, f'Geo {g}')}"
        else:
            msg = f"Cycled geometry {step:+d} on {len(targets)} node(s)."
        self._after_attr_cycle(targets, msg)

    def _cycle_selected_topology(self, step: int):
        """J / Shift+J: step each selected node's topology forward/back one id
        (same per-node increment rule as O)."""
        targets = self._cycle_targets()
        if not targets:
            return
        for node in targets:
            node.topo = (node.topo + step) % TOPO_COUNT
        if len(targets) == 1:
            t = targets[0].topo
            msg = f"Topology → {t}: {TOPO_NAMES.get(t, f'Topo {t}')}"
        else:
            msg = f"Cycled topology {step:+d} on {len(targets)} node(s)."
        self._after_attr_cycle(targets, msg)
        # Overrides the message above when it applies — a subtree that just
        # vanished off screen is more urgent news than which topo id we landed
        # on (which the inspector shows anyway).
        self._hint_scattered_children(targets)

    def _cycle_selected_color_index(self, step: int):
        """= \\ -: step each selected node's color_index within its own
        palette's range, then immediately resolve to literal color_r/g/b
        (color_a is untouched -- ANTz palettes never carry alpha)."""
        targets = self._cycle_targets()
        if not targets:
            return
        for node in targets:
            node.color_index = (node.color_index + step) % palette_index_count(node.palette_id)
            node.color_r, node.color_g, node.color_b = resolve_palette_color(
                node.palette_id, node.color_index)
        if len(targets) == 1:
            msg = f"Color index → {targets[0].color_index}"
        else:
            msg = f"Cycled color index {step:+d} on {len(targets)} node(s)."
        self._after_attr_cycle(targets, msg)

    def _cycle_selected_palette(self, step: int):
        """Alt+= \\ Alt+-: step each selected node's palette_id, clamp
        color_index into the new palette's range, and re-resolve color_r/g/b."""
        targets = self._cycle_targets()
        if not targets:
            return
        for node in targets:
            node.palette_id = (node.palette_id + step) % PALETTE_COUNT
            node.color_index %= palette_index_count(node.palette_id)
            node.color_r, node.color_g, node.color_b = resolve_palette_color(
                node.palette_id, node.color_index)
        if len(targets) == 1:
            p = targets[0].palette_id
            msg = f"Palette → {PALETTE_NAMES.get(p, p)}"
        else:
            msg = f"Cycled palette {step:+d} on {len(targets)} node(s)."
        self._after_attr_cycle(targets, msg)

    # --- viewport pick callbacks ---

    def _on_viewport_pick(self, node_id: int):
        """Plain click: replace selection with this single node -- or, in
        Link mode, register it as the pending A-end / complete a pending link."""
        if self._link_mode_active:
            self._handle_link_pick(node_id)
            return
        self._table.select_by_id(node_id)

    def _on_viewport_pick_additive(self, node_id: int):
        """Ctrl+click: toggle this node in/out of the current selection --
        or, in Link mode, the same pick handling as a plain click (Link
        creation has no separate additive semantics)."""
        if self._link_mode_active:
            self._handle_link_pick(node_id)
            return
        self._table.select_toggle_id(node_id)

    def _on_viewport_nodes_selected(self, node_ids: object):
        """Rubber-band or click-on-empty: replace selection with the given ID
        set -- or, in Link mode, a miss-click cancels any pending A-end."""
        if self._link_mode_active:
            if not node_ids:
                self._link_pending_a_id = None
                self.statusBar().showMessage("Link: pending pick cancelled.")
            return
        self._table.select_by_ids(set(node_ids))

    def _handle_link_pick(self, node_id: int):
        """Second half of Link mode's click sequence. First hit becomes the
        pending A-end (still runs through normal selection so it's
        highlighted and previewed in the inspector); a different second hit
        creates the Link and re-arms for the next pair; picking the same id
        again is a no-op (can't self-link)."""
        if self._link_pending_a_id is None:
            self._link_pending_a_id = node_id
            self._table.select_by_id(node_id)
            self.statusBar().showMessage(f"Link: A-end = node {node_id}. Click the B-end node.")
            return
        if node_id == self._link_pending_a_id:
            self.statusBar().showMessage(
                f"Link: node {node_id} is already the A-end -- click a different node for the B-end."
            )
            return
        a_id = self._link_pending_a_id
        self._link_pending_a_id = None
        self._create_link(a_id, node_id)

    def _on_escape_pressed(self):
        """Esc: cancel the current modal action -- currently just a pending
        Link A-end, matching ANTz's R-click-cancels-Link behavior without
        overloading the right mouse button (already the third-axis
        manipulate drag / camera orbit everywhere else in GlyphViz)."""
        if self._link_mode_active and self._link_pending_a_id is not None:
            self._link_pending_a_id = None
            self.statusBar().showMessage("Link: pending pick cancelled.")

    def _create_link(self, a_id: int, b_id: int):
        """Create a type=7 Link node connecting a_id (A-end/parent_id) to
        b_id (B-end/child_id) -- the interactive counterpart to hand-authoring
        a Link row or a generator script (see pdb_loader.py,
        generate_gtdb_examples.py). Deliberately no root-only restriction
        (unlike ANTz): the Link renderer just resolves world_pos() for
        whichever two ids it's given, so linking nodes at any hierarchy depth
        already works identically -- restricting to roots would just be
        carrying over an ANTz UI limitation with no GlyphViz reason behind it."""
        a_node = next((n for n in self.nodes if n.id == a_id), None)
        if a_node is None:
            self.statusBar().showMessage(f"Link: node {a_id} no longer exists.")
            return
        new_id = max((n.id for n in self.nodes), default=0) + 1
        color = self._new_obj_color
        link = Node(
            id=new_id, type=NODE_TYPE_LINK, parent_id=a_id,
            branch_level=a_node.branch_level + 1,
            translate_x=0.0, translate_y=0.0, translate_z=0.0,
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=1.0, scale_y=1.0, scale_z=1.0,
            color_r=color.red(), color_g=color.green(), color_b=color.blue(), color_a=color.alpha(),
            geometry=GEO_LINE, hide=0, topo=TOPO_NONE,
            extras={'child_id': b_id},
        )
        self._add_node_to_scene(link)
        self.statusBar().showMessage(
            f"Link created (node {new_id}): {a_id} -> {b_id}. "
            "Click another A-end, or toggle Link mode off."
        )

    def _on_viewport_nodes_selected_additive(self, node_ids: object):
        """Ctrl+Shift+drag rubber-band: add the region's nodes to the selection."""
        self._table.select_add_ids(set(node_ids))

    # --- table selection → inspector + viewport highlight ---

    def _on_table_selection(self):
        self._selected_nodes = self._table.selected_nodes()
        self._viewport.selected_node_ids = {n.id for n in self._selected_nodes}
        self._viewport.update()
        self._update_selection_audio_solo()

        has_selection = bool(self._selected_nodes)
        for btn in self._mode_buttons.values():
            btn.setEnabled(has_selection)
        self._btn_delete.setEnabled(has_selection)
        self._save_sel_act.setEnabled(has_selection)
        for btn in (self._btn_hide_sel, self._btn_show_sel, self._btn_isolate):
            btn.setEnabled(has_selection)
        if not has_selection and self._gizmo_mode is not None:
            self._set_gizmo_mode(None)

        n = len(self._selected_nodes)
        if n == 0:
            self._refresh_inspector(None)
            self._status_current_node = None
            self.statusBar().showMessage("No selection.")
        elif n == 1:
            node = self._selected_nodes[0]
            self._refresh_inspector(node)
            self._status_current_node = node
            self._update_status_message()
        else:
            self._refresh_inspector_multi(self._selected_nodes)
            self._status_current_node = None
            self.statusBar().showMessage(f"{n} nodes selected.")

    def _update_status_message(self):
        """(Re-)render the status bar text for the single currently-selected
        node, appending its tag text (collapsed to one line) and eliding the
        whole message with a trailing ellipsis if it doesn't fit — tag text
        is intentionally NOT drawn in the 3D view unless the user opts in
        (Show Tag Labels), but Jeff's users still want a quick, low-commitment
        way to read it, without occupying the Properties panel for it."""
        node = self._status_current_node
        if node is None:
            return
        base = (
            f"Node {node.id}  type={node.type}  "
            f"pos=({node.translate_x:.2f}, {node.translate_y:.2f}, {node.translate_z:.2f})  "
            f"geo={node.geometry}  topo={node.topo}"
        )
        tag_text = " ".join(node.text.split()) if node.text else ""
        full = f'{base}   Tag: "{tag_text}"' if tag_text else base
        sb = self.statusBar()
        avail = sb.width() - self._fps_label.width() - 24
        elided = sb.fontMetrics().elidedText(full, Qt.TextElideMode.ElideRight, max(avail, 50))
        sb.showMessage(elided)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._status_current_node is not None:
            self._update_status_message()

    def _refresh_inspector(self, node: Node | None):
        """Single-node or empty inspector state."""
        if node is None:
            self._insp_grp.setTitle("Selected Node")
            self._insp_grp.setEnabled(False)
            self._refresh_grid_group()
            return
        self._insp_grp.setTitle("Selected Node")
        self._insp_grp.setEnabled(True)
        self._refresh_grid_group()
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
        idx = self._geo_combo_index(self._insp_geo, node.geometry, node.mesh_id)
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

        self._refresh_topo_scale_controls(node)
        self._refresh_palette_controls(node)
        self._refresh_color_btn(node)

        self._insp_text.blockSignals(True)
        self._insp_text.setText(node.text)
        self._insp_text.blockSignals(False)
        self._refresh_show_text_check([node])
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
        self._refresh_grid_group()
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

        idx = self._geo_combo_index(self._insp_geo, primary.geometry, primary.mesh_id)
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

        self._refresh_topo_scale_controls(primary)
        self._refresh_palette_controls(primary)
        self._refresh_color_btn(primary)

        self._insp_text.blockSignals(True)
        self._insp_text.setText(primary.text)
        self._insp_text.blockSignals(False)
        self._refresh_show_text_check(nodes)
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

    def _refresh_show_text_check(self, nodes: list[Node]):
        """Sync the Always Show Text box from the selection, showing the
        partially-checked state when the selected nodes disagree."""
        on = sum(1 for n in nodes if n.show_text)
        cb = self._insp_show_text
        cb.blockSignals(True)
        if on and on < len(nodes):
            cb.setTristate(True)
            cb.setCheckState(Qt.CheckState.PartiallyChecked)
        else:
            cb.setTristate(False)
            cb.setChecked(bool(on))
        cb.blockSignals(False)

    def _refresh_color_btn(self, node: Node):
        self._set_color_btn(self._insp_color_btn, node.color_r, node.color_g, node.color_b, node.color_a)

    def _refresh_palette_controls(self, node: Node):
        idx = self._insp_palette.findData(node.palette_id)
        self._insp_palette.blockSignals(True)
        self._insp_palette.setCurrentIndex(max(idx, 0))
        self._insp_palette.blockSignals(False)

        self._insp_color_index.blockSignals(True)
        self._insp_color_index.setMaximum(palette_index_count(node.palette_id) - 1)
        self._insp_color_index.setValue(node.color_index)
        self._insp_color_index.blockSignals(False)

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
            self._table.refresh_nodes(n.id for n in self._selected_nodes)
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
            self._table.refresh_nodes(n.id for n in self._selected_nodes)
        self._viewport.scene_invalidate()

    def _on_insp_geo_changed(self, _idx: int):
        if not self._selected_nodes:
            return
        data = self._insp_geo.currentData()
        geo, mesh_id = data if isinstance(data, tuple) else (data, None)
        for node in self._selected_nodes:
            node.geometry = geo
            if mesh_id is not None:
                node.mesh_id = mesh_id
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
        self._update_sel_values()
        self._refresh_grid_group()   # a grid's geometry decides flat vs globe
        self._viewport.scene_invalidate()

    def _on_scale_lock_toggled(self, checked: bool):
        """The Properties panel's scale lock also governs Size-mode dragging.

        One control for one idea ("these three move together"), rather than a
        second checkbox on the Manipulate toolbar meaning nearly the same
        thing. The two act differently only because a drag has to: the spin
        boxes set an absolute value and can honestly equalize all three, while
        a drag is multiplicative and shares its FACTOR — equalizing mid-drag
        would collapse a deliberately non-uniform glyph on the first pixel.
        """
        self._viewport.uniform_scale = checked
        self._viewport.update()
        if self._gizmo_mode == 'size':
            self.statusBar().showMessage(
                "Size drags scale X/Y/Z together." if checked
                else "Size drags scale each axis on its own.", 4000)

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
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
        self._viewport.scene_invalidate()

    def _on_insp_ratio_changed(self, value: float):
        if not self._selected_nodes:
            return
        for node in self._selected_nodes:
            node.ratio = value
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
        self._viewport.scene_invalidate()

    def _refresh_topo_scale_controls(self, node: Node):
        """Sync the Topology Scale spin box and its log slider from a node."""
        for w in (self._insp_topo_scale, self._insp_topo_scale_slider):
            w.blockSignals(True)
        self._insp_topo_scale.setValue(node.topo_scale)
        self._insp_topo_scale_slider.setValue(_topo_scale_to_slider(node.topo_scale))
        for w in (self._insp_topo_scale, self._insp_topo_scale_slider):
            w.blockSignals(False)

    def _on_insp_topo_scale_changed(self, value: float):
        """Spin-box edit: apply to every selected node (the absolute-value
        multi-select rule Topology/Ratio/Geometry already use), and re-place
        their children."""
        self._insp_topo_scale_slider.blockSignals(True)
        self._insp_topo_scale_slider.setValue(_topo_scale_to_slider(value))
        self._insp_topo_scale_slider.blockSignals(False)
        if not self._selected_nodes:
            return
        for node in self._selected_nodes:
            node.topo_scale = value
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
        self._viewport.scene_invalidate()

    def _on_insp_topo_scale_slider(self, pos: int):
        """Slider drag: the spin box is the single point that applies the
        value, so route through it rather than duplicating the apply."""
        self._insp_topo_scale.setValue(_slider_to_topo_scale(pos))

    def _set_insp_topo_scale(self, value: float):
        """The 1:1 / ANTz preset buttons.

        Applies the exact constant to the selection and then syncs the
        controls, rather than routing through the spin box: the spin box shows
        6 decimals, which would store the ANTz preset as 0.005556 instead of
        1/180. The displayed value is a rounded view of the real one — a typed
        edit still means exactly what it says.
        """
        if not self._selected_nodes:
            return
        for node in self._selected_nodes:
            node.topo_scale = value
        self._refresh_topo_scale_controls(self._selected_nodes[0])
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
        self._viewport.scene_invalidate()

    def _hint_scattered_children(self, nodes: list[Node]) -> None:
        """After a topology change, say something if the change just flung the
        children off into the distance.

        Switching a parent from an angular topology to a linear one reads
        translate values authored as degrees as world units instead, which can
        move a child hundreds of times its parent's own radius away — far
        enough that it is off screen with no hint as to where it went, and the
        single most confusing thing a new user can do to a scene. The field
        that fixes it (Topology Scale) is not one they would think to look
        for, so name it. Only fires on a parent whose children are still at a
        neutral topo_scale, since a deliberately-tuned value is not a mistake.
        """
        candidates = [n for n in nodes if n.topo_scale == DEFAULT_TOPO_SCALE]
        if not candidates:
            return
        ratio, parent_id = self._viewport.scene.worst_child_placement_ratio(
            n.id for n in candidates)
        if ratio < _TOPO_SCALE_HINT_RATIO:
            return
        suggestion = TOPO_SCALE_ANTZ if ratio > 1.0 else DEFAULT_TOPO_SCALE
        self.statusBar().showMessage(
            f"Node {parent_id}: children are now {ratio:.0f}x its own radius "
            f"away — lower its Topo Scale (try the ANTz preset, "
            f"{suggestion:.4f}) to bring them back in.",
            _TOPO_SCALE_HINT_MS,
        )

    def _on_insp_texture_id_changed(self, value: float):
        if not self._selected_nodes:
            return
        tex_id = int(value)
        for node in self._selected_nodes:
            node.texture_id = tex_id
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
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
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
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
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
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
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
        self._viewport.refresh_animation_state()
        self._viewport.scene_invalidate()

    def _on_insp_text_changed(self, value: str):
        if not self._selected_nodes:
            return
        for node in self._selected_nodes:
            node.text = value
        self._viewport.update()

    def _on_insp_show_text_toggled(self, checked: bool):
        """Pin (or unpin) the selected nodes' tag text — see Node.show_text.
        scene_touch(), not just update(): the viewport's per-revision scene
        scan caches whether any node is pinned at all."""
        if not self._selected_nodes:
            return
        self._insp_show_text.setTristate(False)   # a click resolves 'mixed'
        flag = 1 if checked else 0
        for node in self._selected_nodes:
            node.show_text = flag
        n = len(self._selected_nodes)
        untagged = sum(1 for node in self._selected_nodes if not node.text)
        self._viewport.scene_touch()
        msg = (f"Tag text pinned on for {n} node(s)." if checked
               else f"Tag text unpinned for {n} node(s).")
        if checked and untagged:
            msg += f"  {untagged} of them have no tag text to show yet."
        self.statusBar().showMessage(msg)

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
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
        self._update_sel_values()
        self._viewport.scene_invalidate()
        self._hint_scattered_children(self._selected_nodes)

    def _on_insp_subspace_changed(self, _idx: int):
        if not self._selected_nodes:
            return
        subspace = self._insp_subspace.currentData()
        for node in self._selected_nodes:
            node.subspace = subspace
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
        self._viewport.scene_invalidate()

    def _on_insp_rotation_mode_changed(self, _idx: int):
        if not self._selected_nodes:
            return
        rotation_mode = self._insp_rotation_mode.currentData()
        for node in self._selected_nodes:
            node.rotation_mode = rotation_mode
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
        self._viewport.scene_invalidate()

    def _on_insp_palette_changed(self, _idx: int):
        if not self._selected_nodes:
            return
        palette_id = self._insp_palette.currentData()
        for node in self._selected_nodes:
            node.palette_id = palette_id
            node.color_index %= palette_index_count(palette_id)
            node.color_r, node.color_g, node.color_b = resolve_palette_color(
                palette_id, node.color_index)
        self._refresh_palette_controls(self._selected_nodes[0])
        self._refresh_color_btn(self._selected_nodes[0])
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
        self._viewport.scene_invalidate()

    def _on_insp_color_index_changed(self, value: int):
        if not self._selected_nodes:
            return
        for node in self._selected_nodes:
            node.color_index = value % palette_index_count(node.palette_id)
            node.color_r, node.color_g, node.color_b = resolve_palette_color(
                node.palette_id, node.color_index)
        self._refresh_color_btn(self._selected_nodes[0])
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
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
        self._table.refresh_nodes(n.id for n in self._selected_nodes)
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

    def _update_step_tip(self):
        """Keep the Placement Step tooltip showing what the CURRENT step
        actually buys — the row width is a consequence of the number typed,
        and 'wraps at 360' means nothing until you know it's 72 objects."""
        step = self._new_step.value()
        if step <= 0.0:
            row = "0 stacks every new object at the same spot."
        else:
            row = (f"At {step:g}, a row holds {columns_per_row(step)} object(s) "
                   f"before wrapping.")
        self._new_step.setToolTip(
            "How far apart consecutive auto-placed objects sit (N / Shift+N /\n"
            "New Node / New Child / paste).\n"
            f"translate_x steps by this much; when it would reach {PLACEMENT_WRAP:g},\n"
            "it restarts at 0 and translate_y takes the step instead — so\n"
            "objects array into a grid on a Cartesian parent, and start a new\n"
            "ring instead of overlapping on a Sphere/Torus/Cylinder parent.\n"
            f"{row}\n"
            "ANTz used a fixed 15."
        )

    def _on_new_step_changed(self, value: float):
        self._update_step_tip()
        if value <= 0.0:
            self.statusBar().showMessage(
                "Placement Step 0 — new objects will stack at the parent's origin.")
        else:
            self.statusBar().showMessage(
                f"Placement Step {value:g} — {columns_per_row(value)} object(s) "
                f"per row, then translate_y steps to the next row.")

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
        tag_rgb = ((world.tag_color_r, world.tag_color_g, world.tag_color_b)
                   if world else TAG_DEFAULT_TEXT_RGB)
        tag_by_node = bool(world and world.tag_color_mode == TAG_COLOR_MODE_NODE)
        tag_pt = world.tag_font_size if world else TAG_DEFAULT_FONT_SIZE
        tag_pt = max(TAG_FONT_SIZE_MIN, min(TAG_FONT_SIZE_MAX, int(tag_pt)))
        grid_rgb = ((world.ref_grid_color_r, world.ref_grid_color_g, world.ref_grid_color_b)
                    if world else REF_GRID_DEFAULT_RGB)

        self._set_color_btn(self._scene_bg_btn, r, g, b, 255)
        self._set_color_btn(self._tag_color_btn, *tag_rgb, 255)
        self._set_color_btn(self._grid_color_btn, *grid_rgb, 255)
        self._cb_tag_color_node.blockSignals(True)
        self._cb_tag_color_node.setChecked(tag_by_node)
        self._cb_tag_color_node.blockSignals(False)
        self._tag_color_btn.setEnabled(not tag_by_node)
        # Signals blocked: the handler calls _ensure_world_node(), which would
        # synthesize a World row into every file merely by opening it.
        self._tag_font_slider.blockSignals(True)
        self._tag_font_slider.setValue(tag_pt)
        self._tag_font_slider.blockSignals(False)
        self._tag_font_label.setText(f"Tag Text Size: {tag_pt} pt")
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

    def _on_tag_text_color(self):
        world = self._ensure_world_node()
        initial = QColor(world.tag_color_r, world.tag_color_g, world.tag_color_b)
        color = QColorDialog.getColor(initial, self, "Tag Text Color")
        if not color.isValid():
            return
        world.tag_color_r = color.red()
        world.tag_color_g = color.green()
        world.tag_color_b = color.blue()
        self._set_color_btn(self._tag_color_btn, color.red(), color.green(), color.blue(), 255)
        self._table.refresh_node(world.id)
        self._viewport.update()

    def _on_ref_grid_color(self):
        world = self._ensure_world_node()
        initial = QColor(world.ref_grid_color_r, world.ref_grid_color_g,
                         world.ref_grid_color_b)
        color = QColorDialog.getColor(initial, self, "Grid Color")
        if not color.isValid():
            return
        world.ref_grid_color_r = color.red()
        world.ref_grid_color_g = color.green()
        world.ref_grid_color_b = color.blue()
        self._set_color_btn(self._grid_color_btn, color.red(), color.green(), color.blue(), 255)
        self._table.refresh_node(world.id)
        self._viewport.update()

    def _on_tag_font_size_changed(self, value: int):
        value = int(value)
        self._tag_font_label.setText(f"Tag Text Size: {value} pt")
        world = self._ensure_world_node()
        world.tag_font_size = value
        self._table.refresh_node(world.id)
        self._viewport.update()

    def _on_tag_color_mode_toggled(self, checked: bool):
        world = self._ensure_world_node()
        world.tag_color_mode = TAG_COLOR_MODE_NODE if checked else TAG_COLOR_MODE_UNIFORM
        self._tag_color_btn.setEnabled(not checked)
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
        data = self._new_geo.currentData()
        geo, mesh_id = data if isinstance(data, tuple) else (data, 0)
        return (
            geo,
            mesh_id,
            self._new_topo.currentData(),
            self._new_scale_x.value(),
            self._new_scale_y.value(),
            self._new_scale_z.value(),
            self._new_obj_color,
        )

    def _placement_step(self) -> float:
        """The Placement Step from the Create panel — how far apart auto-placed
        new objects sit. See glyphviz_core/placement.py for the lattice it
        feeds."""
        return float(self._new_step.value())

    def _placement_z(self, is_child: bool) -> float:
        """The Placement Z for a new root or a new child — see the two spin
        boxes' tooltips for why they're separate numbers."""
        return float((self._new_child_z if is_child else self._new_root_z).value())

    def _next_root_pos(self) -> tuple[float, float]:
        """(translate_x, translate_y) for a new root-level (branch_level 0)
        node: one Placement Step on from the LAST root created, wrapping to a
        new row at 360. Shared by _create_root_node, _paste_clipboard's
        no-selection case and _load_mesh_path.

        Keyed on the last root created (highest id) rather than the largest
        translate_x, because after a row wraps the largest x is back in the
        previous row. World Grids are skipped — a grid is the surface the
        array sits on, not a member of it."""
        root_glyphs = [
            n for n in self.nodes
            if n.type not in NON_VISUAL_TYPES and n.type != NODE_TYPE_GRID
            and n.branch_level == 0
        ]
        if not root_glyphs:
            return (0.0, 0.0)
        last = max(root_glyphs, key=lambda n: n.id)
        return step_from(last.translate_x, last.translate_y, self._placement_step())

    def _next_child_pos(self, parent: Node) -> tuple[float, float]:
        """(translate_x, translate_y) for the next child of *parent*: the next
        free slot in the wrapped step lattice. Shared by _create_child_node and
        _paste_clipboard's one-selection case.

        Links (type 7) parented to the node don't count — they render between
        their two ends and ignore translate, so counting them would leave a
        hole in the array."""
        placed = sum(
            1 for n in self.nodes
            if n.parent_id == parent.id and n.type != NODE_TYPE_LINK
        )
        return wrapped_grid_offset(placed, self._placement_step())

    def _create_root_node(self):
        """Create a new root-level node using the New Object Defaults, one
        Placement Step on from the last root created."""
        next_x, next_y = self._next_root_pos()
        new_id = max((n.id for n in self.nodes), default=0) + 1
        geo, mesh_id, topo, sx, sy, sz, color = self._new_object_defaults()
        self._add_node_to_scene(Node(
            id=new_id, type=5, parent_id=0, branch_level=0,
            translate_x=next_x, translate_y=next_y,
            translate_z=self._placement_z(is_child=False),
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=sx, scale_y=sy, scale_z=sz,
            color_r=color.red(), color_g=color.green(), color_b=color.blue(), color_a=color.alpha(),
            geometry=geo, hide=0, topo=topo, mesh_id=mesh_id,
        ))

    def _create_child_node(self):
        """Shift+N / New Child button: create a child node (using the New Object
        Defaults) under the selected node.

        Multiple presses keep the parent selected and distribute children along
        translate_x at the Placement Step, wrapping to a new translate_y row
        every full 360 so they don't overlap — ANTz's rule (_next_child_pos).
        """
        if len(self._selected_nodes) != 1:
            self.statusBar().showMessage("Select exactly one node to add a child.")
            return
        parent = self._selected_nodes[0]
        next_x, next_y = self._next_child_pos(parent)
        new_id = max((n.id for n in self.nodes), default=0) + 1
        geo, mesh_id, topo, sx, sy, sz, color = self._new_object_defaults()
        self._add_node_to_scene(Node(
            id=new_id, type=5, parent_id=parent.id,
            branch_level=parent.branch_level + 1,
            translate_x=next_x, translate_y=next_y,
            translate_z=self._placement_z(is_child=True),
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=sx, scale_y=sy, scale_z=sz,
            color_r=color.red(), color_g=color.green(), color_b=color.blue(), color_a=color.alpha(),
            geometry=geo, hide=0, topo=topo, mesh_id=mesh_id,
        ), select_new=False)

    def _create_world_grid(self):
        """Add World Grid button: create a NEW type-6 grid node (multiple per
        scene are allowed) at the world origin with the whole-earth window at
        1:1 scale — a child at translate (180, 90) lands at world (180, 90).
        Children attach explicitly (New Child / paste with the grid selected
        sets parent_id = grid.id); nothing attaches implicitly."""
        new_id = max((n.id for n in self.nodes), default=0) + 1
        grid = Node(
            id=new_id, type=NODE_TYPE_GRID, parent_id=0, branch_level=0,
            translate_x=0.0, translate_y=0.0, translate_z=0.0,
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=1.0, scale_y=1.0, scale_z=1.0,
            color_r=64, color_g=80, color_b=96, color_a=255,
            geometry=GEO_GRID_WIRE, hide=0, topo=TOPO_PLANE,
        )
        grid.set_grid_extents(*GRID_DEFAULT_EXTENTS)
        grid.set_grid_segments(*GRID_DEFAULT_SEGMENTS)
        self._add_node_to_scene(grid)
        self.statusBar().showMessage(
            f"World Grid created (node {new_id}): lon -180..180, lat -90..90, "
            "1:1 world units. G selects/cycles grids; New Child adds glyphs onto it."
        )

    # --- Draw Mode (paint objects onto a World Grid; see viewport.set_draw_mode) ---

    def _on_draw_mode_changed(self, on: bool):
        """Sync the panel button with the viewport's Draw Mode state (D key,
        Esc, or Camera Mode displacing it), and make sure there's a grid to
        draw on — entering Draw Mode in a gridless scene creates one, since
        the mode is meaningless without a target."""
        self._draw_mode_btn.setChecked(on)
        if on and not any(n.type == NODE_TYPE_GRID for n in self.nodes):
            self._create_world_grid()
        self.statusBar().showMessage(
            "Draw Mode ON — click / drag stamps New Object Defaults onto the "
            "grid at Draw Z; right-drag orbits  [D or Esc exits]" if on
            else "Draw Mode off", 6000)

    def _draw_target_grid(self) -> Node | None:
        """The grid Draw Mode stamps onto: a selected grid when there is one
        (same precedence the World Grid panel uses), else the scene's first
        grid in scene order."""
        for n in self._selected_nodes:
            if n.type == NODE_TYPE_GRID:
                return n
        return next((n for n in self.nodes if n.type == NODE_TYPE_GRID), None)

    def set_draw_stamp_recipe(self, recipe):
        """Register a Glyph Composer recipe as a Draw Mode brush and select
        it. Called by the panel's Load… button and the Glyph Composer's
        Use as Draw Brush button; each call adds a combo entry (loading two
        templates keeps both available for alternating strokes)."""
        self._draw_stamp_combo.addItem(recipe.name or "Template", recipe)
        self._draw_stamp_combo.setCurrentIndex(self._draw_stamp_combo.count() - 1)

    def _on_draw_stamp_load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Glyph Template as Draw Brush", "",
            "Glyph Template (*.json)")
        if not path:
            return
        try:
            recipe = load_recipe(path)
        except Exception as e:
            self.statusBar().showMessage(f"Template load failed: {e}")
            return
        self.set_draw_stamp_recipe(recipe)
        self.statusBar().showMessage(
            f'Draw brush: "{recipe.name}" — Draw Mode stamps this hyperglyph.')

    def _draw_stamp_nodes(self, grid: Node, start_id: int) -> list[Node]:
        """The nodes one stamp creates, at the stamp frame's origin (roots
        at translate 0,0,0 — place_stamp then lands them on the cursor):
        the selected Glyph Composer hyperglyph, or a single object from the
        New Object Defaults."""
        recipe = self._draw_stamp_combo.currentData()
        if recipe is not None:
            return generate_nodes(recipe, start_id=start_id,
                                  parent_id=grid.id,
                                  base_branch_level=grid.branch_level + 1)
        geo, mesh_id, topo, sx, sy, sz, color = self._new_object_defaults()
        return [Node(
            id=start_id, type=5, parent_id=grid.id,
            branch_level=grid.branch_level + 1,
            translate_x=0.0, translate_y=0.0, translate_z=0.0,
            rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
            scale_x=sx, scale_y=sy, scale_z=sz,
            color_r=color.red(), color_g=color.green(), color_b=color.blue(), color_a=color.alpha(),
            geometry=geo, hide=0, topo=topo, mesh_id=mesh_id,
        )]

    def _on_draw_stamp(self, x: float, y: float):
        """One Draw Mode stamp: land the click on the target grid's drawing
        plane and create the current brush there — a single New-Object-
        Defaults object or a whole Glyph Composer hyperglyph, with the
        panel's heading/scale jitter applied per stamp."""
        grid = self._draw_target_grid()
        if grid is None:
            # The mode-entry grid was deleted mid-mode; make a fresh one.
            self._create_world_grid()
            grid = self._draw_target_grid()
            if grid is None:
                return
        if grid.grid_is_globe():
            self.statusBar().showMessage(
                "Draw Mode draws on flat grids only for now — switch the "
                "grid's Shape to Flat in the World Grid panel.")
            return
        draw_z = self._draw_z.value()
        hit = self._viewport.draw_plane_hit(x, y, grid, draw_z)
        if hit is None:
            return   # plane edge-on or behind the camera: nothing to place
        lon, lat = hit
        start_id = max((n.id for n in self.nodes), default=0) + 1
        nodes = self._draw_stamp_nodes(grid, start_id)
        if not nodes:
            return
        place_stamp(nodes, grid.branch_level + 1, lon, lat, draw_z,
                    self._draw_heading_jitter.value(),
                    self._draw_scale_jitter.value())
        for nd in nodes:
            self._add_node_to_scene(nd, select_new=False)
        self._draw_stroke_count += 1
        self._draw_stroke_nodes += len(nodes)

    def _on_draw_stroke_finished(self):
        if self._draw_stroke_count:
            what = (f"{self._draw_stroke_count} stamp(s), "
                    f"{self._draw_stroke_nodes} node(s)"
                    if self._draw_stroke_nodes != self._draw_stroke_count
                    else f"{self._draw_stroke_count} object(s)")
            self.statusBar().showMessage(
                f"Drew {what} — Shift+drag selects a region, "
                "Delete removes it.")
        self._draw_stroke_count = 0
        self._draw_stroke_nodes = 0

    def _select_next_grid(self):
        """G key (ANTz-style): select the scene's World Grid; press again to
        cycle when there are several. Grids aren't click-pickable (they'd
        swallow clicks meant for glyphs sitting on them), so this — plus the
        node table — is how a grid gets selected for Move/Rotate/Scale or
        World Grid panel edits."""
        grids = [n for n in self.nodes if n.type == NODE_TYPE_GRID]
        if not grids:
            self.statusBar().showMessage(
                "No World Grid in this scene — use the Add World Grid button.")
            return
        selected_ids = {n.id for n in self._selected_nodes}
        cur = next((i for i, g in enumerate(grids) if g.id in selected_ids), -1)
        nxt = grids[(cur + 1) % len(grids)]
        self._table.select_by_id(nxt.id)
        self.statusBar().showMessage(
            f"World Grid {nxt.id} selected ({cur + 2 if cur >= 0 else 1} of "
            f"{len(grids)}) — Move/Rotate/Scale now apply to it; G cycles.")

    def _selected_single_grid(self) -> Node | None:
        if len(self._selected_nodes) == 1 and self._selected_nodes[0].type == NODE_TYPE_GRID:
            return self._selected_nodes[0]
        return None

    def _refresh_grid_group(self):
        """Sync the World Grid panel to the selection: enabled with values
        loaded when exactly one grid is selected, disabled otherwise."""
        grid = self._selected_single_grid()
        self._grid_grp.setEnabled(grid is not None)
        if grid is None:
            return
        lon_lo, lon_hi, lat_lo, lat_hi = grid.grid_extents()
        seg_x, seg_y = grid.grid_segments()
        for sb, val in (
            (self._grid_lon_min, lon_lo), (self._grid_lon_max, lon_hi),
            (self._grid_lat_min, lat_lo), (self._grid_lat_max, lat_hi),
            (self._grid_seg_x, seg_x), (self._grid_seg_y, seg_y),
        ):
            sb.blockSignals(True)
            sb.setValue(val)
            sb.blockSignals(False)
        globe = grid.grid_is_globe()
        self._grid_shape.blockSignals(True)
        self._grid_shape.setCurrentIndex(
            max(self._grid_shape.findData("globe" if globe else "flat"), 0))
        self._grid_shape.blockSignals(False)
        # A globe places children at absolute lon/lat — the extents window
        # only applies to the flat form (segments still set the graticule).
        for sb in (self._grid_lon_min, self._grid_lon_max,
                   self._grid_lat_min, self._grid_lat_max):
            sb.setEnabled(not globe)
        # A regional map can't wrap a globe — basemap fetch is flat-form only.
        self._grid_basemap_btn.setEnabled(not globe)

    def _on_grid_shape_changed(self, _idx: int):
        """Toggle the selected grid between flat rectangle and globe by
        rewriting its geometry (preserving the wire/solid choice) — the
        same effect as picking Grid/Sphere in the Geometry dropdown."""
        grid = self._selected_single_grid()
        if grid is None:
            return
        wire = grid.geometry in _WIRE_IDS
        if self._grid_shape.currentData() == "globe":
            grid.geometry = GEO_SPHERE_WIRE if wire else GEO_SPHERE
        else:
            grid.geometry = GEO_GRID_WIRE if wire else GEO_GRID
        self._table.refresh_node(grid.id)
        self._refresh_inspector(grid)   # re-sync Geometry combo + panel state
        self._viewport.scene_invalidate()   # child placement math changed

    def _on_grid_extents_changed(self, _value: float):
        grid = self._selected_single_grid()
        if grid is None:
            return
        lon_lo, lon_hi = self._grid_lon_min.value(), self._grid_lon_max.value()
        lat_lo, lat_hi = self._grid_lat_min.value(), self._grid_lat_max.value()
        if lon_hi <= lon_lo or lat_hi <= lat_lo:
            # Transient state while typing (or a genuinely inverted window):
            # don't store a degenerate window the renderer would ignore.
            self.statusBar().showMessage("Grid extents: max must exceed min on each axis.")
            return
        grid.set_grid_extents(lon_lo, lon_hi, lat_lo, lat_hi)
        self._table.refresh_node(grid.id)
        self._viewport.scene_invalidate()

    def _on_grid_segments_changed(self, _value: int):
        grid = self._selected_single_grid()
        if grid is None:
            return
        grid.set_grid_segments(self._grid_seg_x.value(), self._grid_seg_y.value())
        self._table.refresh_node(grid.id)
        # Segment counts change only the grid's own line rendering — no
        # transform recompute needed, but the retained scene list must rebake.
        self._viewport.scene_touch()

    def _on_fetch_basemap(self):
        """Fetch Basemap button (World Grid panel): download map imagery for
        the selected grid's lon/lat window (glyphviz_core.basemap), write it
        into the scene's media/ folder, and wire it up — grid extents set to
        the map's exact coverage, texture_id assigned, wire geometry promoted
        to solid so the texture is actually visible."""
        grid = self._selected_single_grid()
        if grid is None:
            return
        if grid.grid_is_globe():
            self.statusBar().showMessage(
                "Fetch Basemap needs the flat form — a regional map can't wrap a "
                "globe. Switch Shape to Flat Rectangle first.")
            return
        if not self._current_path:
            self.statusBar().showMessage(
                "Open or save the scene as a CSV first — the basemap image is "
                "stored in a media/ folder beside it.")
            return

        from .basemap_dialog import BasemapFetchDialog
        media_dir = Path(self._current_path).parent / "media"
        # A stable per-grid name: refetching overwrites in place (same
        # texture_id, no renumbering); the zz_ prefix keeps it sorted after
        # the scene's own deliberately-ordered media files.
        out_path = media_dir / f"zz_basemap_grid{grid.id}.png"
        existed = out_path.is_file()
        dlg = BasemapFetchDialog(grid, self.nodes, out_path, parent=self)
        if not dlg.exec() or dlg.result_path is None:
            return

        # texture_id is a 1-based index into media/ sorted alphanumerically
        # (images first, then videos) — inserting a NEW image shifts every id
        # at or after its sort position, so shift referencing nodes to match.
        # An overwrite keeps its old position: nothing moves.
        new_id = self._media_image_index(media_dir, out_path.name)
        if not existed and new_id:
            for n in self.nodes:
                if n.texture_id >= new_id:
                    n.texture_id += 1
        bbox = dlg.result_bbox
        grid.set_grid_extents(bbox.lon_min, bbox.lon_max, bbox.lat_min, bbox.lat_max)
        if new_id:
            grid.texture_id = new_id
        if grid.geometry == GEO_GRID_WIRE:
            grid.geometry = GEO_GRID
        self._apply_texture_folder(media_dir, silent=True)
        self._table.refresh_node(grid.id)
        self._refresh_inspector(grid)   # geometry combo + grid panel resync
        self._viewport.scene_invalidate()
        self.statusBar().showMessage(
            f"Basemap applied to World Grid {grid.id}: {out_path.name} "
            f"(texture {new_id}), extents lon {bbox.lon_min:.3f}..{bbox.lon_max:.3f}, "
            f"lat {bbox.lat_min:.3f}..{bbox.lat_max:.3f}. {dlg.result_attribution}")

    @staticmethod
    def _media_image_index(media_dir: Path, name: str) -> int:
        """1-based texture_id of *name* within media_dir's sorted image files
        (the TextureManager numbering), or 0 if it isn't there."""
        images = sorted(
            p.name for p in media_dir.iterdir()
            if p.is_file() and p.suffix.lower() in _TEX_IMAGE_EXTS
        )
        try:
            return images.index(name) + 1
        except ValueError:
            return 0

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
            child_x, child_y = self._next_child_pos(target)
            new_translate = (child_x, child_y, self._placement_z(is_child=True))
        else:
            new_parent_id = 0
            new_branch_level = 0
            root_x, root_y = self._next_root_pos()
            new_translate = (root_x, root_y, self._placement_z(is_child=False))
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
            self._viewport.set_channel_dynamic_nodes(None)
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
                self._viewport.set_channel_dynamic_nodes(None)
                self._ch_unload_audio()
                return None
            self._ch_engine = engine
            # Enable the playback fast path: bound nodes (and descendants of
            # transform-bound ones) leave the baked display list and draw
            # immediate per frame — see Viewport.channel_frame_update.
            self._viewport.set_channel_dynamic_nodes(
                engine.bound_node_ids, engine.transform_bound_node_ids)
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
                self._ch_fps_display.setEnabled(False)
                self._ch_fps_display.setText("audio")
                return f"channels: {engine.frame_count} frames, synced to {audio_path.name}"
            self._ch_unload_audio()
            return f"channels: {engine.frame_count} frames"
        except Exception as exc:
            self._ch_grp.setVisible(False)
            self._ch_engine = None
            self._viewport.set_channel_dynamic_nodes(None)
            self._ch_unload_audio()
            self.statusBar().showMessage(f"Channel load warning: {exc}")
            return None

    def _ch_unload_audio(self):
        self._ch_audio.unload()
        self._ch_audio_loaded = False
        self._ch_fps.setEnabled(True)
        self._ch_fps.setToolTip("Desired playback speed in frames per second")
        self._ch_fps_display.setEnabled(True)
        self._ch_fps_display.setText(f"{self._ch_fps.value()} fps")

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
        self._viewport.channel_frame_update()

    def _on_ch_slider(self, value: int):
        self._ch_frame = value
        if self._ch_engine:
            self._ch_engine.apply_frame(value)
            self._ch_frame_label.setText(f"Frame: {value} / {self._ch_engine.frame_count - 1}")
            self._viewport.channel_frame_update()
            if self._ch_audio_loaded and self._ch_engine.frame_count > 1:
                frac = value / (self._ch_engine.frame_count - 1)
                self._ch_audio.seek_ms(int(frac * self._ch_audio.duration_ms()))

    def _ch_update_fps(self, value: int):
        self._ch_fps_display.setText(f"{int(value)} fps")
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
