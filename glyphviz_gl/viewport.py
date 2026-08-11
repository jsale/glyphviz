import math
import time
from dataclasses import dataclass, field

import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *
from PySide6.QtCore import Qt, QEvent, QPoint, QRect, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QStaticText
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from pathlib import Path

from glyphviz_core.node import (
    Node, GRID_GLOBE_RADIUS, NON_VISUAL_TYPES, NODE_TYPE_GRID, NODE_TYPE_LINK,
    RENDER_MODE_NORMAL, RENDER_MODE_ADDITIVE, RENDER_MODE_SUBTRACTIVE,
    RENDER_MODE_DARK, RENDER_MODE_OFF, RENDER_MODE_SCREEN, RENDER_MODE_PREMULTIPLIED,
    WORLD_DEFAULT_BG_RGB, REF_GRID_DEFAULT_RGB,
    TAG_COLOR_MODE_NODE, TAG_DEFAULT_TEXT_RGB, TAG_TEXT_ALPHA, TAG_SHADOW_RGBA,
)
from glyphviz_core import gizmo as gz
from glyphviz_core.scene import DEFAULT_SCALE_FLOOR, NO_SCALE_FLOOR, Scene
from glyphviz_core.topology import (
    TOPO_NONE, TOPO_PLANE, TOPO_PLOT, TOPO_SURFACE, TOPO_VIDEO,
)
from glyphviz_core.mesh_loader import load_mesh_file as _load_mesh_data

from glyphviz_core.geometry_data import GEO_TORUS, GEO_TORUS_WIRE, GEO_LINE_PRISM

from .geometry import GeoRenderer, WIRE_TO_SOLID
from .texture_manager import TextureManager
from .video_manager import VideoManager

_DRAG_THRESHOLD = 4  # pixels — less than this counts as a click, not a drag

# Safety valve for scenes where most/all nodes are tagged at once (e.g. a
# heatmap-style file with thousands of labeled points): QPainter text
# rasterization is CPU-bound and doesn't batch, so drawing thousands of
# on-screen tags every frame can dominate frame time even after they're
# individually cheap to project. Ordinary tag counts (tens to low hundreds)
# never hit this; it only engages on pathological cases.
#
# Deliberately NOT applied in show_tags_selected_only mode: selecting is an
# explicit user scoping action, so every selected tag draws even when that
# costs frame rate (Jeff's call — see _project_tagged_nodes).
_MAX_TAGS_PER_FRAME = 500

# ANTz rate convention (translate_rate_x/y/z, rotate_rate_x/y/z, scale_rate_x/y/z):
# a delta applied every cycle, nominally 60 cycles/second — see
# Node-Field-Descriptions.md's Translate/Rotate/Scale sections.
_RATE_CYCLE_MS = 1000.0 / 60.0

# Parent shapes whose translate_x/y/z map linearly (Cartesian) into the
# parent's local frame — for these, a Move-drag's screen-space delta can be
# converted exactly into translate units by dividing out the parent's
# cumulative per-axis scale (see _move_axis_divisors). Angular topologies
# (Sphere/Torus/...) use degrees and keep the historical fixed drag rate.
_CARTESIAN_PARENT_TOPOS = frozenset({
    TOPO_NONE, TOPO_PLANE, TOPO_VIDEO, TOPO_PLOT, TOPO_SURFACE,
})

# --- Manipulation sensitivity -------------------------------------------------
# The per-pixel rates of the axis-checkbox drags (_apply_axis_deltas). Named
# constants rather than literals because the transform gizmo's drag math has
# to speak the same currency: a handle drag arrives already converted into
# world units / degrees / a multiplier, and these are what the free-form drag
# converts ITS pixels into, so the two paths stay comparable.
_MOVE_WORLD_PER_PX = 0.0015    # x arm length — matches the camera-pan speed
_ROTATE_DEG_PER_PX = 0.4       # matches the camera-orbit sensitivity
_SIZE_FACTOR_PER_PX = 0.004    # multiplicative, per drag step

# --- Camera Mode (free flight, C key) tuning ---------------------------------
# Left-drag flight is rate-based (ANTz-style): the press point becomes the
# bearings origin, and the cursor's *held offset* from it sets a continuous
# speed — flight keeps going while the button is down even with the mouse
# stationary, and bringing the cursor back to the origin stops it. Speeds
# scale off the arm length (_cam_distance) so flying feels the same whether
# you're circling a whole 500-unit scene or nosing around one glyph: holding
# ~100px above the origin covers roughly one view distance per second.
_FLY_RATE_PER_PX_S = 0.01       # arm-length fraction per second, per px of vertical offset
_FLY_TURN_DEG_PER_PX_S = 0.5    # degrees per second, per px of horizontal offset
_FLY_DEADZONE_PX = 3.0          # per-axis: no motion until the cursor leaves this radius
_FLY_SPEED_PER_PX = 0.004       # strafe (Left+Right slide): arm-length fraction per px of drag
_FLY_WHEEL_STEP = 0.12          # fraction of arm length per wheel notch
_LOOK_DEG_PER_PX = 0.25         # look-around (right-drag) rate, both axes

_Vec3 = tuple[float, float, float]


def _past_deadzone(offset: float) -> float:
    """Pixels of flight-drag cursor offset beyond the dead zone (0 inside
    it) — measured from the edge, so motion ramps up from zero as the cursor
    leaves the zone instead of jumping to a dead-zone-sized speed."""
    if offset > _FLY_DEADZONE_PX:
        return offset - _FLY_DEADZONE_PX
    if offset < -_FLY_DEADZONE_PX:
        return offset + _FLY_DEADZONE_PX
    return 0.0


_DEFAULT_BG = tuple(c / 255.0 for c in WORLD_DEFAULT_BG_RGB)  # used when the scene has no World node
_DEFAULT_REF_GRID = tuple(c / 255.0 for c in REF_GRID_DEFAULT_RGB)   # ditto, for the backdrop grid


@dataclass
class _CameraView:
    """A saved orbit-camera viewpoint (azimuth/elevation/distance/target),
    switchable with the C key or the Camera toolbar. `locked` cameras
    (the 3 default axis views) are fixed reference views: orbit and pan are
    disabled while active, zoom (distance) is not."""
    name: str
    azimuth: float
    elevation: float
    distance: float
    target: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    locked: bool = False


def _apply_render_mode(mode: int):
    """Scene-wide blend state — see node.py's RENDER_MODE_* constants."""
    if mode == RENDER_MODE_OFF:
        glDisable(GL_BLEND)
        return
    glEnable(GL_BLEND)
    if mode == RENDER_MODE_ADDITIVE:
        glBlendEquation(GL_FUNC_ADD)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
    elif mode == RENDER_MODE_SUBTRACTIVE:
        glBlendEquation(GL_FUNC_REVERSE_SUBTRACT)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
    elif mode == RENDER_MODE_DARK:
        glBlendEquation(GL_FUNC_ADD)
        glBlendFunc(GL_ZERO, GL_SRC_COLOR)
    elif mode == RENDER_MODE_SCREEN:
        glBlendEquation(GL_FUNC_ADD)
        glBlendFunc(GL_ONE_MINUS_DST_COLOR, GL_ONE)
    elif mode == RENDER_MODE_PREMULTIPLIED:
        glBlendEquation(GL_FUNC_ADD)
        glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
    else:  # RENDER_MODE_NORMAL
        glBlendEquation(GL_FUNC_ADD)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


class _SceneScan:
    """Special-role node membership paintGL needs every frame — rate-driven
    movers, link/plot/surface nodes, World Grid presence — collected in ONE
    pass over the node list and cached per Scene revision (see
    Viewport._scene_scan). Before this cache, each frame re-scanned the
    whole scene several times over in Python, which at 700k nodes cost
    ~900 ms/frame no matter how few nodes the \\-key draw limit let render."""
    __slots__ = ('rate_nodes', 'link_nodes', 'plot_nodes', 'surface_nodes',
                 'has_grid', 'has_pinned_tags', '_children_of')

    def __init__(self, nodes: list[Node]):
        self.rate_nodes: list[Node] = []
        self.link_nodes: list[Node] = []
        self.plot_nodes: list[Node] = []
        self.surface_nodes: list[Node] = []
        self.has_grid = False
        # Any node with show_text set — the tag overlay pass has to run even
        # with the scene-wide tag display off, and this keeps that check off
        # the per-frame path (see Viewport.paintGL). Deliberately not ANDed
        # with n.text: whether a pinned node has text yet changes on every
        # keystroke in the inspector, and rebaking the scan (and with it the
        # retained display list) that often is far more expensive than an
        # overlay pass that finds nothing to draw.
        self.has_pinned_tags = False
        self._children_of: dict[int, list[Node]] | None = None
        for n in nodes:
            if (n.translate_rate_x or n.translate_rate_y or n.translate_rate_z
                    or n.rotate_rate_x or n.rotate_rate_y or n.rotate_rate_z
                    or n.scale_rate_x or n.scale_rate_y or n.scale_rate_z):
                self.rate_nodes.append(n)
            if n.show_text:
                self.has_pinned_tags = True
            if n.type == NODE_TYPE_LINK:
                self.link_nodes.append(n)
            else:
                if n.topo == TOPO_PLOT:
                    self.plot_nodes.append(n)
                elif n.topo == TOPO_SURFACE:
                    self.surface_nodes.append(n)
                if n.type == NODE_TYPE_GRID:
                    self.has_grid = True

    def children_map(self, nodes: list[Node]) -> dict[int, list[Node]]:
        """parent_id → children (links excluded), built lazily on first use —
        only Plot/Surface overlay drawing needs it, so scenes without those
        topologies never pay for the dict."""
        if self._children_of is None:
            m: dict[int, list[Node]] = {}
            for n in nodes:
                if (n.type != NODE_TYPE_LINK and n.parent_id
                        and n.parent_id != n.id):
                    m.setdefault(n.parent_id, []).append(n)
            self._children_of = m
        return self._children_of


class Viewport(QOpenGLWidget):
    # Plain left-click on a node: replaces the selection
    nodeClicked = Signal(int)
    # Ctrl+left-click on a node: toggle that node in/out of selection
    nodeClickedAdditive = Signal(int)
    # Alt+left-click on a node: select it AND open its link (tag URL /
    # inline link column) in the default browser or OS handler — the
    # pointer-device counterpart of the U key.
    nodeLinkActivated = Signal(int)
    # Rubber-band release OR click-on-empty-space: replace selection with this set
    # (empty set = clear all).  Also used by Select-By to push a set of IDs.
    nodesSelected = Signal(object)   # carries set[int]
    # Ctrl+rubber-band release: ADD this set to the current selection
    nodesSelectedAdditive = Signal(object)   # carries set[int]

    # Emitted after a Move/Rotate/Size mouse-drag mutates node transforms.
    nodesManipulated = Signal(object)   # carries set[int] of changed node ids

    # Keyboard hierarchy navigation (ANTz-style)
    navParent = Signal()       # Up arrow  → parent node
    navChild = Signal()        # Down arrow → first child node
    navNextSibling = Signal()  # Tab       → next sibling at same branch level
    navPrevSibling = Signal()  # Shift+Tab → previous sibling at same branch level

    # Node creation (ANTz-style)
    createNode = Signal()       # N        → new root node (or child when context warrants)
    createChildNode = Signal()  # Shift+N  → new child of selected node

    # Draw-limit culling (ANTz \\ / Shift+\\ to halve / double visible node count)
    drawLimitChanged = Signal(int, int)   # (visible_count, total_count)

    # FPS counter — emitted once per second with the current frame rate
    fpsUpdated = Signal(float)

    # Tag visibility toggled with T key
    tagToggled = Signal(bool)

    bgToggleRequested = Signal()         # B → toggle background black/white
    renderModeCycleRequested = Signal()  # 8 → cycle scene render mode
    quickSaveRequested = Signal()        # K → silent auto-save node+tag CSV
    gridSelectRequested = Signal()       # G → select / cycle World Grid nodes (ANTz-style)
    escapePressed = Signal()             # Esc → cancel current modal action (e.g. a pending Link A-end)

    # Active camera switched (Shift+C, or the Camera toolbar) — carries
    # the new active camera's index into self.camera_names().
    cameraChanged = Signal(int)

    # Camera (free-flight) Mode toggled with C — carries the new state.
    flyModeChanged = Signal(bool)

    # ANTz-style per-node attribute cycling: each SELECTED node steps its own
    # geometry (O) or topology (J) to the next id in the list, so a mixed
    # selection stays mixed. Payload is the step (+1, or -1 with Shift held).
    geoCycleRequested = Signal(int)      # O / Shift+O → cycle geometry ±1
    topoCycleRequested = Signal(int)     # J / Shift+J → cycle topology ±1
    colorIndexCycleRequested = Signal(int)   # = / - → cycle color_index ±1
    paletteCycleRequested = Signal(int)      # Alt+= / Alt+- → cycle palette_id ±1

    # Channels playback transport (handled here, not as window-wide
    # shortcuts, so a bare Space still types normally in text fields;
    # works whenever the viewport has focus — e.g. Properties panel closed).
    channelPlayToggleRequested = Signal()   # Space       → play / pause
    channelStopRequested = Signal()         # Shift+Space → stop & reset

    # Visibility hotkeys (handled by MainWindow, which owns the hide logic)
    hideSelectedRequested = Signal()     # H       → hide selected nodes
    showAllRequested = Signal()          # Shift+H → clear every hide flag
    isolateSelectedRequested = Signal()  # I       → show only selected nodes

    # Emitted from initializeGL once the GL context exists. Texture uploads
    # before this point silently produce zero textures (makeCurrent() is a
    # no-op on an uninitialized widget), so startup texture loading must wait
    # for it. Re-emitted if the context is ever recreated (widget reparent,
    # screen change).
    glInitialized = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = Scene([])
        self._base_scale = 1.0
        # Opt-in minimum rendered scale per axis (see scene.DEFAULT_SCALE_FLOOR).
        # Off by default: a glyph renders at exactly the scale it was authored at.
        self._scale_floor = NO_SCALE_FLOOR
        self.show_axes = True
        self.show_grid = True
        self.show_hidden = False
        self.selected_node_ids: set[int] = set()

        # Gizmo manipulation state (Move/Rotate/Size).  None = camera-only.
        self.gizmo_mode: str | None = None
        self.gizmo_axes = {'x': True, 'y': True, 'z': True}

        # On-screen red/green/blue handles for the armed mode, drawn on the
        # first selected visual node. Purely ADDITIVE to the axis-checkbox
        # drags above: grabbing a handle constrains the drag to that one axis
        # and tracks the cursor exactly, while a press that misses every
        # handle still gets the free-form ANTz-style drag it always did.
        self.show_gizmo_handles = True
        # Size mode only: every axis takes the same factor, whichever bar is
        # dragged, so the glyph keeps its proportions. Driven by the
        # Properties panel's "Lock X/Y/Z together" checkbox (MainWindow keeps
        # the two in step). A drag shares the same FACTOR rather than forcing
        # the three fields equal the way the panel's spin boxes do — equalizing
        # would snap a deliberately 3:1:1 glyph to a cube on the first pixel.
        self.uniform_scale = False
        self._gizmo_hover: str | None = None    # axis under the cursor, for highlight
        # Live handle drag. The frame (origin, axis direction, handle length)
        # is FROZEN at the press: a handle that re-aimed itself as the node
        # moved under it would chase the cursor. See _begin_gizmo_drag.
        self._gizmo_drag: dict | None = None
        # Hover highlighting needs move events with no button held.
        self.setMouseTracking(True)

        self._cam_distance = 500.0
        self._cam_azimuth = 45.0
        self._cam_elevation = 25.0
        self._cam_target = [0.0, 0.0, 0.0]

        # Multiple cameras (ANTz-style): index 0 is always the free orbit
        # camera above ("Main"); 1-3 are fixed +X/+Y/+Z reference views onto
        # the world origin. Re-derived with scene-appropriate distances in
        # set_nodes(); see _make_default_cameras.
        self._cameras: list[_CameraView] = self._make_default_cameras()
        self._active_camera = 0
        # True only while both Left and Right buttons are held together —
        # drives the combined orbit+zoom gesture (see _orbit_zoom_camera).
        self._combo_active = False

        # Camera Mode (free flight, C key). The camera rig stays the same
        # azimuth/elevation/distance/target orbit rig — fly mode only changes
        # which end of the arm the mouse drives: normally the eye swings
        # around a fixed target, in fly mode the target swings around a fixed
        # eye (look-around) and both translate together (flight). See
        # _apply_fly_drag / _look_around_camera.
        self.fly_mode: bool = False
        # Rate-flight drag state: the left-press point (bearings origin) and
        # the latest cursor position, both in widget pixels. The held offset
        # between them drives continuous motion once per repaint tick in
        # _apply_fly_drag; None = no flight drag in progress.
        self._fly_anchor: tuple[float, float] | None = None
        self._fly_cursor: tuple[float, float] | None = None

        # Cross-eye free-view stereo: render the scene twice (per-eye lateral
        # camera offset, same look-at target -> toe-in convergence at the
        # target with zero parallax there), side by side in this same widget.
        # Separation auto-scales with cam_distance (a fixed % of it) so it
        # stays sensible across zoom levels; stereo_separation_pct is also
        # user-adjustable for scenes where the default depth feels too flat
        # or too extreme.
        self.stereo_mode: bool = False
        self.stereo_separation_pct: float = 3.0

        # Camera-follow: keep _cam_target locked to the first selected visual
        # node (in scene order) each frame, so orbit/zoom stay live while the
        # node animates away. Pan is overridden while this is on.
        self.follow_selected: bool = False

        self._last_pos = QPoint()
        self._press_pos = QPoint()
        self._drag_button = None
        self._drag_moved = False

        # Draw-limit culling: None = show all; int = show first N visual nodes
        self._draw_limit: int | None = None

        # Per-revision scene-membership scan (see _SceneScan) — rebuilt only
        # when Scene._revision moves, so per-frame consumers (rate animation,
        # topology overlays, grid-presence check) stop re-scanning the whole
        # node list every paintGL.
        self._scan_cache: _SceneScan | None = None
        self._scan_cache_rev: int | None = None

        # FPS tracking
        self._fps_frames = 0
        self._fps_t0 = time.perf_counter()

        # Rubber-band (Shift+drag) state
        self._rubber_mode = False
        self._rubber_start: QPoint | None = None
        self._rubber_end: QPoint | None = None

        # color-ID pick FBO resources (created lazily after GL context exists)
        self._pick_fbo = 0
        self._pick_tex = 0
        self._pick_rbo = 0
        self._pick_fbo_size = (0, 0)

        self.show_tags = False   # off by default (Jeff's preference); toggle with T
        self.show_tags_selected_only = False
        # Yellow selection halo. On by default; toggled with Ctrl+B (ANTz uses
        # the spacebar for this, which GlyphViz already spends on Channels
        # transport). Purely a render toggle — the selection itself stays live,
        # so manipulation/keys keep working with the boxes hidden. Exists so a
        # screengrab can show a chosen state without a selection-free deselect.
        self.show_selection_box = True
        # Per-string QStaticText cache: text layout is computed once per
        # unique string instead of on every drawText call, which halves the
        # per-frame cost of painting thousands of tags. Keyed by tag text;
        # cleared on scene load (see set_nodes) and size-guarded in
        # _paint_tags against pathological churn.
        self._tag_text_cache: dict[str, QStaticText] = {}

        # Cached camera matrices for tag world→screen projection (updated each frame).
        self._mv_matrix: np.ndarray | None = None
        self._proj_matrix: np.ndarray | None = None

        # Retained-mode scene display list: the whole per-node draw loop
        # baked into one glCallList, rebuilt only when the scene changes
        # (see _draw_scene_content). _assets_rev covers change sources the
        # Scene revision counter can't see: texture/video folder loads and
        # mesh (re)registration, which alter the GL names / nested display
        # lists the baked commands reference.
        self._scene_dl = 0
        self._scene_dl_key = None        # key the compiled list matches
        self._scene_dl_last_key = None   # key seen on the previous pass
        self._scene_dl_video_ids: set[int] = set()
        self._assets_rev = 0

        # Channels-playback fast path (see set_channel_dynamic_nodes /
        # channel_frame_update): ids of channel-bound nodes (plus all
        # descendants of transform-bound ones) that are excluded from the
        # baked scene display list and drawn immediate every frame instead,
        # so playback frames replay the static bulk from the DL and pay
        # per-node Python cost only for the animated subtrees.
        self._ch_dynamic_ids: set[int] = set()      # drawn immediate (excluded from DL)
        self._ch_transform_ids: set[int] = set()    # subset whose matrices move each frame
        self._ch_dynamic_rev = 0                    # bumped per set change; part of the DL key
        # Per-scene-revision caches derived from the id sets (row indices
        # shift and nodes may vanish whenever the scene actually changes):
        self._ch_dynamic_nodes: list[Node] = []     # dynamic nodes in scene order
        self._ch_transform_rows: np.ndarray | None = None
        self._ch_cache_rev: tuple | None = None

        self._geo = GeoRenderer()
        self._next_mesh_id = 1
        self._mesh_names: dict[int, str] = {}   # mesh_id -> source filename, for the UI
        self._mesh_paths: dict[str, int] = {}   # resolved source path -> mesh_id, to dedupe re-imports
        self._tex_mgr = TextureManager()
        self._video_mgr = VideoManager()
        self._last_tex_tick = time.perf_counter()
        self._render_timer = QTimer(self)
        self._render_timer.timeout.connect(self.update)
        self._needs_video_tick = False   # video/animated-GIF playback active
        self.setMinimumSize(400, 300)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # --- public interface ---

    @property
    def base_scale(self) -> float:
        return self._base_scale

    @base_scale.setter
    def base_scale(self, value: float):
        self._base_scale = value
        self._scene.base_scale = value
        self._scene.invalidate()

    @property
    def enforce_scale_floor(self) -> bool:
        """Whether the opt-in minimum rendered scale is being applied."""
        return self._scale_floor > 0.0

    @enforce_scale_floor.setter
    def enforce_scale_floor(self, enabled: bool):
        self._scale_floor = DEFAULT_SCALE_FLOOR if enabled else NO_SCALE_FLOOR
        self._scene.scale_floor = self._scale_floor
        self._scene.invalidate()

    @property
    def nodes(self) -> list[Node]:
        """The current node list (read-only; use set_nodes to replace)."""
        return self._scene.nodes

    def scene_invalidate(self):
        """Mark scene transforms stale and request a repaint.
        Call this whenever node data (position, rotation, scale, topo) changes."""
        self._scene.invalidate()
        self.update()

    def scene_touch(self):
        """Request a repaint with a retained-list rebake but no transform
        recompute — for edits that change draw content without moving
        anything (hide flags). See Scene.touch()."""
        self._scene.touch()
        self.update()

    # --- Channels playback fast path ---

    def set_channel_dynamic_nodes(self, bound_ids: set[int] | None,
                                  transform_bound_ids: set[int] | None = None):
        """Declare which nodes a loaded Channels animation drives, enabling
        the playback fast path. Call with the engine's bound_node_ids /
        transform_bound_node_ids after a successful channel load, and with
        None when channels unload.

        Transform-bound ids are expanded to include ALL their descendants:
        a scale/rotate on a parent cascades through the hierarchy, so the
        whole subtree must leave the baked display list and get its matrices
        refreshed each frame. Color-only-bound nodes are excluded from the
        DL too (color compiles into it) but need no matrix work."""
        if not bound_ids:
            changed = bool(self._ch_dynamic_ids)
            self._ch_dynamic_ids = set()
            self._ch_transform_ids = set()
        else:
            transform_ids = self._expand_with_descendants(
                transform_bound_ids or set())
            dynamic_ids = set(bound_ids) | transform_ids
            changed = (dynamic_ids != self._ch_dynamic_ids
                       or transform_ids != self._ch_transform_ids)
            self._ch_dynamic_ids = dynamic_ids
            self._ch_transform_ids = transform_ids
        if changed:
            self._ch_dynamic_rev += 1
            self._ch_cache_rev = None
        self.update()

    def _expand_with_descendants(self, ids: set[int]) -> set[int]:
        if not ids:
            return set()
        children: dict[int, list[int]] = {}
        for n in self._scene.nodes:
            if n.parent_id and n.parent_id != n.id:
                children.setdefault(n.parent_id, []).append(n.id)
        out = set(ids)
        stack = list(ids)
        while stack:
            for child_id in children.get(stack.pop(), ()):
                if child_id not in out:
                    out.add(child_id)
                    stack.append(child_id)
        return out

    def channel_frame_update(self):
        """Repaint for a Channels playback frame WITHOUT invalidating the
        scene: Scene._revision stays put, so paintGL keeps replaying the
        baked static display list and only the declared dynamic subtrees
        get a matrix refresh + immediate draw. Falls back to a plain
        scene_invalidate() when the fast path isn't available."""
        if not self._ch_dynamic_ids or self._draw_limit is not None:
            self.scene_invalidate()
            return
        self._ch_ensure_playback_cache()
        if self._ch_transform_rows is not None and len(self._ch_transform_rows):
            self._scene.refresh_rows(self._ch_transform_rows)
        self.update()

    def _ch_ensure_playback_cache(self):
        """Recompute the row indices / node list derived from the dynamic id
        sets whenever the scene actually changed (edits, node add/remove —
        anything that bumps Scene._revision or the set itself)."""
        rev = (self._scene._revision, self._ch_dynamic_rev)
        if self._ch_cache_rev == rev:
            return
        self._ch_dynamic_nodes = [n for n in self._scene.nodes
                                  if n.id in self._ch_dynamic_ids]
        self._ch_transform_rows = self._scene.rows_for_ids(self._ch_transform_ids)
        self._ch_cache_rev = rev

    def register_node(self, node: Node):
        """Sync a node appended directly to self._scene.nodes into the scene's lookup cache."""
        self._scene.register_node(node)
        self._update_render_timer_state()
        self.update()

    def register_nodes(self, nodes: list[Node]):
        """Bulk register_node for a batch appended in one go (a scene merge).
        Unlike set_nodes() this keeps the existing Scene — and therefore the
        camera, draw limit, and channel dynamic set — untouched."""
        self._scene.register_nodes(nodes)
        self._update_render_timer_state()
        self.update()

    def remove_nodes(self, ids: set[int]):
        """Remove nodes (by id) from the scene in place, without resetting the camera.
        Mutates self._scene.nodes in place — MainWindow.nodes aliases the same list
        object (see _add_node_to_scene), so this keeps both in sync."""
        self._scene.nodes[:] = [n for n in self._scene.nodes if n.id not in ids]
        for nid in ids:
            self._scene._by_id.pop(nid, None)
        self.selected_node_ids -= ids
        self._scene.invalidate()
        self._update_render_timer_state()
        self.update()

    def set_nodes(self, nodes: list[Node]):
        self._draw_limit = None   # new scene → show everything
        self._assets_rev += 1     # new Scene restarts its revision counter — force a scene-list rebuild
        self._tag_text_cache.clear()
        # Any channel dynamic set belonged to the old scene; the caller
        # re-declares it after (re)loading channels for the new one.
        self._ch_dynamic_ids = set()
        self._ch_transform_ids = set()
        self._ch_dynamic_nodes = []
        self._ch_transform_rows = None
        self._ch_cache_rev = None
        self._ch_dynamic_rev += 1
        self._scene = Scene(nodes, self._base_scale, self._scale_floor)
        # A new Scene restarts its revision counter, so the old scan could
        # alias the new scene's revision — drop it explicitly.
        self._scan_cache = None
        self._scan_cache_rev = None
        self._scene._ensure()   # pre-compute so camera init can read positions
        self._update_render_timer_state()
        visible = [n for n in nodes if n.type not in NON_VISUAL_TYPES]
        if visible:
            positions = [
                self._scene.world_pos(n.id) or (n.translate_x, n.translate_y, n.translate_z)
                for n in visible
            ]
            # A World Grid's footprint spans far beyond its center point —
            # include its corners so a grid scene opens fully framed.
            for n, p in zip(visible, list(positions)):
                if n.type == NODE_TYPE_GRID:
                    rx, ry, _ = self._radius_of(n)
                    positions.append((p[0] - rx, p[1] - ry, p[2]))
                    positions.append((p[0] + rx, p[1] + ry, p[2]))
            xs = [p[0] for p in positions]
            ys = [p[1] for p in positions]
            zs = [p[2] for p in positions]
            self._cam_target = [
                (min(xs) + max(xs)) / 2,
                (min(ys) + max(ys)) / 2,
                (min(zs) + max(zs)) / 2,
            ]
            span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
            self._cam_distance = max(span * 1.5, 50.0)
            # Axis cameras look at the origin specifically, not the scene's
            # bounding-box center, so their distance is sized off how far
            # content actually reaches from the origin, not off `span`.
            origin_radius = max(math.dist((0.0, 0.0, 0.0), p) for p in positions)
            axis_distance = max(origin_radius * 1.5, 50.0)
        else:
            axis_distance = 500.0
        self._cameras = self._make_default_cameras(axis_distance)
        self._active_camera = 0
        self.cameraChanged.emit(0)
        self.update()

    def world_position(self, node_id: int) -> tuple[float, float, float] | None:
        """World-space position of a node as computed for the last rendered frame."""
        return self._scene.world_pos(node_id)

    def _radius_of(self, node: Node) -> tuple[float, float, float]:
        """Per-axis rendered radii (rx, ry, rz) for camera focus and UI hints.

        Mirrors the draw matrices' scale, including whether the opt-in
        minimum (self._scale_floor) is in force, so framing matches what is
        actually on screen."""
        fl = self._scale_floor
        if node.type == NODE_TYPE_GRID:
            # World Grid: footprint = shape half-spans x raw scale, no
            # base_scale/floor (mirrors scene._grid_draw_scale).
            if node.grid_is_globe():
                gr = GRID_GLOBE_RADIUS
                return (max(node.scale_x * gr, fl),
                        max(node.scale_y * gr, fl),
                        max(node.scale_z * gr, fl))
            half_lon, half_lat = node.grid_half_extents()
            return (max(node.scale_x * half_lon, fl),
                    max(node.scale_y * half_lat, fl),
                    max(node.scale_z, fl))
        s = self._scene.world_scale(node.id) or (node.scale_x, node.scale_y, node.scale_z)
        bs = self._base_scale
        return (max(s[0]*bs, fl), max(s[1]*bs, fl), max(s[2]*bs, fl))

    def set_camera(self, azimuth: float = None, elevation: float = None,
                   distance: float = None, target: tuple[float, float, float] = None):
        """Override one or more camera parameters, leaving the rest (e.g. the
        bounding-box auto-framing set_nodes() already computed) untouched."""
        if azimuth is not None:
            self._cam_azimuth = azimuth
        if elevation is not None:
            self._cam_elevation = elevation
        if distance is not None:
            self._cam_distance = distance
        if target is not None:
            self._cam_target = list(target)

    def _make_default_cameras(self, axis_distance: float = 500.0) -> list['_CameraView']:
        """The 4 default cameras. Eye position for (azimuth, elevation) is
        target + distance*(cos(el)cos(az), cos(el)sin(az), sin(el)) (see
        paintGL's gluLookAt setup), so azimuth=elevation=0 looks from the
        +X axis, azimuth=90 from +Y, and elevation=89 (not exactly 90, to
        avoid the up-vector singularity — same clamp _orbit_camera uses)
        from nearly straight above on +Z."""
        return [
            _CameraView('Main', self._cam_azimuth, self._cam_elevation,
                        self._cam_distance, list(self._cam_target), locked=False),
            _CameraView('+X View', 0.0, 0.0, axis_distance, [0.0, 0.0, 0.0], locked=True),
            _CameraView('+Y View', 90.0, 0.0, axis_distance, [0.0, 0.0, 0.0], locked=True),
            _CameraView('+Z View', 0.0, 89.0, axis_distance, [0.0, 0.0, 0.0], locked=True),
        ]

    def camera_names(self) -> list[str]:
        return [c.name for c in self._cameras]

    @property
    def active_camera_index(self) -> int:
        return self._active_camera

    def active_camera_locked(self) -> bool:
        return bool(self._cameras) and self._cameras[self._active_camera].locked

    def _sync_active_camera(self):
        """Write the live _cam_* state back into the active camera's saved slot."""
        cam = self._cameras[self._active_camera]
        cam.azimuth, cam.elevation = self._cam_azimuth, self._cam_elevation
        cam.distance = self._cam_distance
        cam.target = list(self._cam_target)

    def select_camera(self, index: int):
        """Switch the active camera (by index, wrapping) and load its saved
        viewpoint live. Used by both C-key cycling and the Camera toolbar."""
        if not self._cameras:
            return
        index %= len(self._cameras)
        self._sync_active_camera()
        self._active_camera = index
        cam = self._cameras[index]
        self._cam_azimuth, self._cam_elevation = cam.azimuth, cam.elevation
        self._cam_distance = cam.distance
        self._cam_target = list(cam.target)
        if cam.locked and self.fly_mode:
            # Fixed reference views don't fly — picking one leaves Camera Mode.
            self.set_fly_mode(False)
        self.cameraChanged.emit(index)
        self.update()

    def cycle_camera(self, step: int = 1):
        self.select_camera(self._active_camera + step)

    # --- Camera Mode (free flight) ---

    def set_fly_mode(self, on: bool):
        """Turn free-flight Camera Mode on or off.

        Flight engages from wherever the view already is — no jump — but it
        can't run on a locked axis camera (those exist precisely to stay
        put), so turning it on switches to the Main camera first.
        """
        on = bool(on)
        if on and self.active_camera_locked():
            self.select_camera(0)
        if on == self.fly_mode:
            return
        self.fly_mode = on
        if on:
            # Following pins the target to a node every frame, which would
            # undo flight's translation on the spot.
            self.follow_selected = False
        if not on:
            self._fly_anchor = self._fly_cursor = None
            self._update_render_timer_state()
        self.flyModeChanged.emit(on)
        self.update()

    def toggle_fly_mode(self):
        self.set_fly_mode(not self.fly_mode)

    def camera_state(self) -> dict:
        """Snapshot the live camera, the saved camera list, and the active
        index — so a scene reload (File > Watch and Reload) can put the
        viewpoint back exactly where the user left it, undoing set_nodes()'s
        auto-framing."""
        self._sync_active_camera()
        return {
            'azimuth': self._cam_azimuth,
            'elevation': self._cam_elevation,
            'distance': self._cam_distance,
            'target': list(self._cam_target),
            'cameras': [_CameraView(c.name, c.azimuth, c.elevation,
                                    c.distance, list(c.target), c.locked)
                        for c in self._cameras],
            'active': self._active_camera,
            'fly': self.fly_mode,
        }

    def restore_camera_state(self, state: dict):
        """Reapply a camera_state() snapshot (after set_nodes)."""
        self._cameras = [_CameraView(c.name, c.azimuth, c.elevation,
                                     c.distance, list(c.target), c.locked)
                         for c in state['cameras']]
        self._active_camera = min(state['active'], len(self._cameras) - 1)
        self._cam_azimuth = state['azimuth']
        self._cam_elevation = state['elevation']
        self._cam_distance = state['distance']
        self._cam_target = list(state['target'])
        self.cameraChanged.emit(self._active_camera)
        self.set_fly_mode(state.get('fly', False))
        self.update()

    def export_png(self, path: str, width: int, height: int) -> None:
        """Render the current scene at an explicit pixel resolution and save
        it as a PNG.  Works without the widget ever being shown on screen.
        Compensates for devicePixelRatio so the saved file's actual
        dimensions match width x height (falls back to a resample if the
        platform's DPR rounding leaves it off by a pixel or two)."""
        dpr = self.devicePixelRatioF() or 1.0
        self.resize(max(1, round(width / dpr)), max(1, round(height / dpr)))
        img = self.grabFramebuffer()
        if img.width() != width or img.height() != height:
            img = img.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        if not img.save(str(path)):
            raise RuntimeError(f"Failed to save screenshot to {path}")

    def save_screenshot(self, path: str) -> None:
        """Save the scene exactly as currently displayed on screen, at the
        widget's current size — unlike export_png(), this never resizes the
        (visible, interactive) widget."""
        img = self.grabFramebuffer()
        if not img.save(str(path)):
            raise RuntimeError(f"Failed to save screenshot to {path}")

    # Headroom multiplier on the exact bounding-sphere tangent-fit distance:
    # the focused object fills ~1/1.3 (~75%) of the tighter view dimension.
    _FOCUS_MARGIN = 1.3

    def _fit_distance(self, radius: float) -> float:
        """Camera distance at which a bounding sphere of `radius` exactly fits
        the view (tangent to the narrower FOV axis), times _FOCUS_MARGIN.
        Mirrors paintGL's gluPerspective(45, w/h, ...); in stereo mode each
        eye only gets half the widget width."""
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        if self.stereo_mode and w >= 2:
            w //= 2
        half_v = math.radians(45.0) / 2.0
        half_h = math.atan(math.tan(half_v) * (w / h))
        return radius * self._FOCUS_MARGIN / math.sin(min(half_v, half_h))

    def _bound_radius(self, node: Node) -> float:
        """Bounding-sphere radius, about node's own world position, of the
        node plus all its visible descendants — so double-clicking the root of
        a composite glyph frames the whole glyph. Every primitive geometry is
        inscribed in the unit sphere (see geometry.py), so a node's max
        per-axis world radius bounds it."""
        center = self.world_position(node.id) or (node.translate_x, node.translate_y, node.translate_z)
        children: dict[int, list[Node]] = {}
        for n in self._scene.nodes:
            children.setdefault(n.parent_id, []).append(n)
        radius = max(self._radius_of(node))
        stack = list(children.get(node.id, []))
        visited = {node.id}
        while stack:
            n = stack.pop()
            if n.id in visited:
                continue
            visited.add(n.id)
            if n.type in NON_VISUAL_TYPES or n.type == NODE_TYPE_LINK:
                continue
            if not self.show_hidden and n.hide:
                continue
            pos = self.world_position(n.id)
            if pos is not None:
                d = math.dist(pos, center)
                radius = max(radius, d + max(self._radius_of(n)))
            stack.extend(children.get(n.id, []))
        return radius

    def focus_on(self, world_pos: tuple[float, float, float], radius: float = 1.0):
        """Center the camera on world_pos, at the distance where a bounding
        sphere of `radius` is fully in view with headroom. The distance is
        absolute (not relative to the current camera), so this jumps in from
        far away but backs OUT when the camera is already closer than the fit
        distance — including starting inside the object."""
        self._cam_target = list(world_pos)
        self._cam_distance = max(self._fit_distance(radius), 1.0)
        self.update()

    def focus_on_node(self, node: Node):
        """Center on node and frame it (and its child glyph structure) fully in view."""
        pos = self.world_position(node.id) or (node.translate_x, node.translate_y, node.translate_z)
        self.focus_on(pos, self._bound_radius(node))

    def follow_node(self) -> Node | None:
        """The node the camera follows while follow_selected is on: the first
        selected visual node in scene (table/tree) order, or None."""
        if not self.selected_node_ids:
            return None
        for n in self._scene.nodes:
            if n.id in self.selected_node_ids and n.type not in NON_VISUAL_TYPES:
                return n
        return None

    def _apply_follow_target(self):
        """Re-center _cam_target on the followed node (called once per frame
        from paintGL, after rate animation has moved nodes). Distance/azimuth/
        elevation are left alone so orbit and zoom stay interactive."""
        node = self.follow_node()
        if node is None:
            return
        pos = self._scene.world_pos(node.id)
        if pos is not None:
            self._cam_target = list(pos)

    # --- texture management ---

    @property
    def texture_folder(self) -> Path | None:
        return self._tex_mgr.folder

    @property
    def texture_count(self) -> int:
        """Total number of loaded textures (static images + videos)."""
        return self._tex_mgr.count() + self._video_mgr.count()

    def load_texture_folder(self, folder: Path) -> int:
        """Load all images and videos from *folder* as GL textures.  Must be
        called while the OpenGL context is current (safe to call from the main
        thread after the widget has been shown).  Returns total texture count."""
        self.makeCurrent()
        img_count = self._tex_mgr.load_folder(folder)
        vid_count = self._video_mgr.load_folder(folder, img_count + 1)
        self._needs_video_tick = bool(vid_count) or self._tex_mgr.has_animated()
        self._assets_rev += 1   # GL texture names changed — rebake the scene list
        self._update_render_timer_state()
        self.update()
        return img_count + vid_count

    def load_mesh_file(self, path: str) -> int:
        """Import an OBJ/STL/etc. file (glyphviz_core.mesh_loader) and compile
        it into a GEO_MESH display list. Must be called while the OpenGL
        context is current (safe from the main thread after the widget has
        been shown). Returns the mesh_id (1, 2, 3, ... in import order).

        Re-importing a file that was already imported reuses its existing
        mesh_id — the file is re-read and its display list rebuilt (so edits
        on disk show up), but no duplicate mesh entry is created."""
        data = _load_mesh_data(path)
        key = str(Path(path).resolve())
        self.makeCurrent()
        self._geo.setup()
        mesh_id = self._mesh_paths.get(key)
        if mesh_id is None:
            mesh_id = self._next_mesh_id
            self._next_mesh_id += 1
            self._mesh_paths[key] = mesh_id
        self._geo.register_mesh(mesh_id, data)
        self._mesh_names[mesh_id] = data.name
        self._assets_rev += 1   # baked glCallList references resolve by id — rebake
        self.update()
        return mesh_id

    def mesh_name(self, mesh_id: int) -> str:
        return self._mesh_names.get(mesh_id, "")

    def clear_textures(self):
        """Release all loaded textures and stop video playback."""
        self.makeCurrent()
        self._tex_mgr.release()
        self._video_mgr.release()
        self._needs_video_tick = False
        self._assets_rev += 1   # texture names released — rebake the scene list
        self._update_render_timer_state()
        self.update()

    def _scene_scan(self) -> _SceneScan:
        """The current scene's _SceneScan, rebuilt when Scene._revision moved
        since the last build (same change-detection contract as the retained
        display list). set_nodes resets the cache explicitly because a new
        Scene restarts its revision counter."""
        rev = self._scene._revision
        if self._scan_cache is None or self._scan_cache_rev != rev:
            self._scan_cache = _SceneScan(self._scene.nodes)
            self._scan_cache_rev = rev
        return self._scan_cache

    def _any_tags_to_draw(self) -> bool:
        """True when the tag overlay pass has anything to do: either the
        scene-wide tag display is on, or some node pins its own text with
        show_text (which draws regardless of the scene-wide settings)."""
        if self.show_tags or self._scene_scan().has_pinned_tags:
            return True
        # Channels can animate show_text, and the scan behind has_pinned_tags
        # is keyed on Scene._revision — which the playback fast path
        # deliberately never bumps. A label pinned mid-playback in a scene
        # that had none at load time would otherwise never draw, because
        # this gate skips the whole overlay pass.
        if self._ch_dynamic_ids:
            self._ch_ensure_playback_cache()
            return any(n.show_text for n in self._ch_dynamic_nodes)
        return False

    def _has_active_rates(self) -> bool:
        """True if any non-frozen node has a nonzero translate/rotate/scale rate
        (ANTz's freeze flag, preserved in Node.extras, suspends a node's own
        rates but doesn't need to be checked against other nodes still moving)."""
        return any(not n.extras.get('freeze', 0)
                   for n in self._scene_scan().rate_nodes)

    def _update_render_timer_state(self):
        """Start/stop the ~30fps continuous-repaint timer based on whether
        anything needs per-frame ticking: video/GIF playback, rate-driven
        node animation, or a flight drag in progress (rate flight integrates
        the held cursor offset once per tick, so it must keep repainting even
        while the mouse sits still). Call after any scene or texture change
        that could flip any of those."""
        needs = (self._needs_video_tick or self._fly_anchor is not None
                 or self._has_active_rates())
        if needs and not self._render_timer.isActive():
            self._render_timer.start(33)   # ~30 fps continuous repaint
            self._last_tex_tick = time.perf_counter()
        elif not needs and self._render_timer.isActive():
            self._render_timer.stop()

    def refresh_animation_state(self):
        """Public hook for callers that mutate node rate fields directly
        (e.g. the Properties inspector) to re-evaluate continuous repaint."""
        self._update_render_timer_state()

    def _apply_rate_animation(self, dt_ms: float) -> set[int]:
        """Advance translate_x/y/z, rotate_x/y/z, scale_x/y/z by their
        *_rate_* velocities (see _RATE_CYCLE_MS). Returns the ids of nodes
        that moved (empty set = nothing changed), so the caller can either
        invalidate the scene's transform cache or — when every mover is
        inside the Channels dynamic set — take the partial-refresh fast
        path instead."""
        cycles = dt_ms / _RATE_CYCLE_MS
        if cycles <= 0:
            return set()
        candidates = self._scene_scan().rate_nodes
        if self._ch_dynamic_ids:
            # Channels playback can write rate fields through the
            # no-revision-bump fast path (refresh_rows), so the revision-keyed
            # scan can miss a channel-driven mover — always consider the
            # dynamic set too.
            self._ch_ensure_playback_cache()
            seen = {n.id for n in candidates}
            candidates = candidates + [n for n in self._ch_dynamic_nodes
                                       if n.id not in seen]
        moved: set[int] = set()
        for n in candidates:
            if n.extras.get('freeze', 0):
                continue
            if n.translate_rate_x or n.translate_rate_y or n.translate_rate_z:
                n.translate_x += n.translate_rate_x * cycles
                n.translate_y += n.translate_rate_y * cycles
                n.translate_z += n.translate_rate_z * cycles
                moved.add(n.id)
            if n.rotate_rate_x or n.rotate_rate_y or n.rotate_rate_z:
                n.rotate_x += n.rotate_rate_x * cycles
                n.rotate_y += n.rotate_rate_y * cycles
                n.rotate_z += n.rotate_rate_z * cycles
                moved.add(n.id)
            if n.scale_rate_x or n.scale_rate_y or n.scale_rate_z:
                n.scale_x += n.scale_rate_x * cycles
                n.scale_y += n.scale_rate_y * cycles
                n.scale_z += n.scale_rate_z * cycles
                moved.add(n.id)
        return moved

    def list_audio_tracks(self) -> list[tuple[int, str]]:
        """Return (texture_id, filename) for each loaded video's audio track."""
        return self._video_mgr.list_tracks()

    def set_audio_solo(self, texture_ids: int | set[int] | None):
        """Mute every video's audio except *texture_ids* (None = play all)."""
        self._video_mgr.set_solo(texture_ids)

    def is_video_texture(self, texture_id: int) -> bool:
        """True if *texture_id* is a loaded video (vs. a static image) --
        lets callers filter a node selection down to its video textures for
        selection-driven audio solo."""
        return self._video_mgr.has(texture_id)

    # --- GL lifecycle ---

    def initializeGL(self):
        # If the GL context was recreated (widget reparent, screen change),
        # any previously compiled scene display list id is dead — forget it
        # so the next paint rebakes instead of calling a stale list.
        self._scene_dl = 0
        self._scene_dl_key = None
        self._scene_dl_last_key = None
        glClearColor(*_DEFAULT_BG, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_DIFFUSE,  [1.0, 1.0, 1.0, 1.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT,  [0.3, 0.3, 0.3, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [0.5, 0.5, 0.5, 1.0])
        glLightfv(GL_LIGHT0, GL_POSITION, [1.0, 2.0, 1.0, 0.0])
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glShadeModel(GL_SMOOTH)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_CULL_FACE)
        glCullFace(GL_BACK)
        # Antialias GL_POINTS (rounds Point-geometry sprites and the round
        # line caps/joins drawn below) and GL_LINES/LINE_STRIP (smooths the
        # otherwise jagged Link/Plot lines). Both rely on GL_BLEND, already
        # enabled above.
        glEnable(GL_POINT_SMOOTH)
        glHint(GL_POINT_SMOOTH_HINT, GL_NICEST)
        glEnable(GL_LINE_SMOOTH)
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
        self._geo.setup()
        self.glInitialized.emit()

    def resizeGL(self, w, h):
        if h == 0:
            h = 1
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, w / h, 0.1, 100000.0)
        glMatrixMode(GL_MODELVIEW)
        self._cleanup_pick_fbo()     # size changed → recreate on next pick

    # --- rendering ---

    def paintGL(self):
        self._video_mgr.tick()   # upload any pending decoded frames before drawing
        now = time.perf_counter()
        dt_ms = (now - self._last_tex_tick) * 1000.0
        self._last_tex_tick = now
        self._tex_mgr.tick(dt_ms)   # advance any playing animated GIFs
        rate_moved = self._apply_rate_animation(dt_ms)
        if rate_moved:
            if (self._ch_dynamic_ids and self._draw_limit is None
                    and rate_moved <= self._ch_transform_ids):
                # Every rate-driven mover is a channel-bound subtree (e.g. a
                # channel driving rotate_rate): refresh just those rows so
                # the static display list keeps replaying.
                self._ch_ensure_playback_cache()
                self._scene.refresh_rows(self._ch_transform_rows)
            else:
                self._scene.invalidate()
                # Rate integration only moved already-known movers — scene
                # membership is unchanged, so re-key the scan cache to the
                # bumped revision instead of rescanning every node next frame.
                self._scan_cache_rev = self._scene._revision
        self._apply_fly_drag(dt_ms)
        if self.follow_selected:
            self._apply_follow_target()
        # QPainter's GL paint engine (used by _draw_tags_qpainter) can leave
        # all of this state changed after painter.end() -- restore it every
        # frame rather than relying on the one-time initializeGL()/resizeGL()
        # setup, since QPainter.end() doesn't guarantee restoring the exact
        # prior fixed-function state (including which matrix is loaded).
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)
        glEnable(GL_CULL_FACE)
        glEnable(GL_LIGHTING)
        glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE)
        glEnable(GL_POINT_SMOOTH)
        glEnable(GL_LINE_SMOOTH)

        world = self._scene.world_node()
        if world is not None:
            bg_r, bg_g, bg_b = world.color_r / 255.0, world.color_g / 255.0, world.color_b / 255.0
        else:
            bg_r, bg_g, bg_b = _DEFAULT_BG
        glClearColor(bg_r, bg_g, bg_b, 1.0)
        _apply_render_mode(world.render_mode if world is not None else RENDER_MODE_NORMAL)
        if world is not None and world.fog_enabled:
            glEnable(GL_FOG)
            glFogi(GL_FOG_MODE, GL_LINEAR)
            glFogfv(GL_FOG_COLOR, [bg_r, bg_g, bg_b, 1.0])
            glFogf(GL_FOG_START, world.fog_start)
            glFogf(GL_FOG_END, world.fog_end)
        else:
            glDisable(GL_FOG)

        w, h = self.width(), self.height()
        if h <= 0 or w <= 0:
            return
        dpr = self.devicePixelRatioF()
        fb_w, fb_h = int(w * dpr), int(h * dpr)
        glViewport(0, 0, fb_w, fb_h)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        if self.stereo_mode and w >= 2:
            self._mv_matrix = None
            self._proj_matrix = None
            half_w = w // 2
            right_w = w - half_w
            sep = self._cam_distance * (self.stereo_separation_pct / 100.0)
            # Cross-eye free-view: the eyes converge by crossing, so the image
            # meant for the RIGHT eye goes on the screen's LEFT half and vice
            # versa (opposite of parallel/"wall-eyed" viewing).
            tag_batches = []
            for screen_x, seg_w, lateral_offset in (
                (0, half_w, +sep / 2.0),        # screen-left  <- right-eye camera
                (half_w, right_w, -sep / 2.0),  # screen-right <- left-eye camera
            ):
                vp_x = int(screen_x * dpr)
                vp_w = fb_w - vp_x if screen_x else int(half_w * dpr)
                glViewport(vp_x, 0, vp_w, fb_h)
                self._setup_stereo_eye_matrices(lateral_offset, seg_w, h)
                mv, pr = self._capture_camera_matrices()
                self._draw_scene_content(mv, pr)
                if self._any_tags_to_draw() and mv is not None:
                    tag_batches.append((screen_x, seg_w, mv, pr))
            self._video_mgr.finalize_frame()   # pause any video no node drew this frame

            glViewport(0, 0, fb_w, fb_h)   # restore full-widget viewport for QPainter overlay
            if tag_batches:
                self._draw_tags_qpainter_stereo(tag_batches)
        else:
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            gluPerspective(45.0, w / h, 0.1, 100000.0)
            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()

            az = math.radians(self._cam_azimuth)
            el = math.radians(self._cam_elevation)
            tx, ty, tz = self._cam_target
            eye_x = tx + self._cam_distance * math.cos(el) * math.cos(az)
            eye_y = ty + self._cam_distance * math.cos(el) * math.sin(az)
            eye_z = tz + self._cam_distance * math.sin(el)
            up_x, up_y, up_z = self._camera_up()
            gluLookAt(eye_x, eye_y, eye_z, tx, ty, tz, up_x, up_y, up_z)

            # Capture camera matrices for world→screen tag projection (before node transforms).
            self._mv_matrix, self._proj_matrix = self._capture_camera_matrices()

            self._draw_scene_content()
            self._video_mgr.finalize_frame()   # pause any video no node drew this frame

            if self._rubber_mode and self._rubber_start and self._rubber_end:
                self._draw_rubber_band()

            # QPainter tag overlay (must come after all glBegin/glEnd blocks).
            if self._any_tags_to_draw() and self._mv_matrix is not None:
                self._draw_tags_qpainter()

        # FPS: count this frame; emit once per second
        self._fps_frames += 1
        now = time.perf_counter()
        elapsed = now - self._fps_t0
        if elapsed >= 1.0:
            self.fpsUpdated.emit(self._fps_frames / elapsed)
            self._fps_frames = 0
            self._fps_t0 = now

    def _camera_basis(self) -> tuple[_Vec3, _Vec3, _Vec3]:
        """The camera's (forward, right, up) unit vectors in world space.

        `forward` points eye→target, `right` is horizontal (world-Z is up), and
        `up` completes the right-handed frame. Derived from the same
        azimuth/elevation the eye position uses, so it stays exactly in sync
        with gluLookAt; the elevation clamp (±89°) keeps `right` well away from
        the degenerate forward-parallel-to-world-up case.
        """
        az = math.radians(self._cam_azimuth)
        el = math.radians(self._cam_elevation)
        ce, se, ca, sa = math.cos(el), math.sin(el), math.cos(az), math.sin(az)
        forward = (-ce * ca, -ce * sa, -se)
        right = (-sa, ca, 0.0)
        up = (-ca * se, -sa * se, ce)
        return forward, right, up

    def _camera_up(self) -> _Vec3:
        """gluLookAt's up vector: the camera never rolls, so always world-Z."""
        return (0.0, 0.0, 1.0)

    def _eye_position_with_offset(self, lateral_offset: float) -> tuple[float, float, float]:
        """Eye position for the current orbit camera, shifted by lateral_offset
        world units along the camera's right vector (perpendicular to the view
        direction, in the XY plane -- same "right" convention as the
        middle-button pan in mouseMoveEvent). lateral_offset=0 matches the
        normal single-eye camera exactly; used to build the two stereo eyes."""
        az = math.radians(self._cam_azimuth)
        el = math.radians(self._cam_elevation)
        tx, ty, tz = self._cam_target
        eye_x = tx + self._cam_distance * math.cos(el) * math.cos(az)
        eye_y = ty + self._cam_distance * math.cos(el) * math.sin(az)
        eye_z = tz + self._cam_distance * math.sin(el)
        eye_x += -math.sin(az) * lateral_offset
        eye_y += math.cos(az) * lateral_offset
        return eye_x, eye_y, eye_z

    def _setup_stereo_eye_matrices(self, lateral_offset: float, seg_w: float, h: float):
        """Set up GL_PROJECTION (off-axis/asymmetric frustum) and GL_MODELVIEW
        (shared orbit-camera orientation + an eye-space lateral translate) for
        one stereo eye pass. Call with GL_PROJECTION/GL_MODELVIEW already
        pushed; this overwrites both with glLoadIdentity().

        Both eyes use the *exact same* gluLookAt call (same eye position,
        target, up) -- the only per-eye differences are an eye-space
        glTranslatef and a matching shift of the projection frustum's
        center, which keeps the camera's orientation (and hence the
        rendered "up" direction) identical between the two eyes at every
        azimuth/elevation.

        This matters because the earlier approach -- shifting each eye's
        *world-space position* and re-aiming a separate gluLookAt at the
        same target -- gives each eye a slightly different forward vector.
        gluLookAt derives its internal right/up basis via cross(forward,
        up), and that cross product shrinks toward zero (and becomes
        numerically unstable) as forward approaches parallel to the
        world-up axis -- i.e. orbiting toward a straight-down view. Because
        the two eyes' forward vectors differ ever so slightly, they'd
        destabilize differently and visibly twist relative to each other
        near the pole. Sharing one orientation for both eyes sidesteps the
        instability entirely (any wobble at the exact pole now matches
        whatever the single-eye camera already does, identically in both
        eyes), while the off-axis frustum shift keeps convergence
        (zero parallax) exactly at the orbit target -- see paintGL's
        eye-offset/distance ratio for the eye-separation math itself.
        """
        near, far = 0.1, 100000.0
        half_h = near * math.tan(math.radians(45.0) / 2.0)
        half_w = half_h * (seg_w / h)
        d = max(self._cam_distance, 1e-6)
        shift = -lateral_offset * near / d

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glFrustum(shift - half_w, shift + half_w, -half_h, half_h, near, far)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glTranslatef(-lateral_offset, 0.0, 0.0)
        az = math.radians(self._cam_azimuth)
        el = math.radians(self._cam_elevation)
        tx, ty, tz = self._cam_target
        eye_x = tx + self._cam_distance * math.cos(el) * math.cos(az)
        eye_y = ty + self._cam_distance * math.cos(el) * math.sin(az)
        eye_z = tz + self._cam_distance * math.sin(el)
        up_x, up_y, up_z = self._camera_up()
        gluLookAt(eye_x, eye_y, eye_z, tx, ty, tz, up_x, up_y, up_z)

    def _capture_camera_matrices(self) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Snapshot the current GL modelview/projection matrices (row-major)
        for world->screen tag projection, right after gluLookAt/gluPerspective."""
        try:
            mv = np.array(glGetDoublev(GL_MODELVIEW_MATRIX), dtype=np.float64)
            pr = np.array(glGetDoublev(GL_PROJECTION_MATRIX), dtype=np.float64)
            return mv.reshape(4, 4).T, pr.reshape(4, 4).T   # column-major -> row-major
        except Exception:
            return None, None

    def _draw_scene_content(self, mv: np.ndarray | None = None, pr: np.ndarray | None = None):
        """Draw grid/axes/nodes/topology overlays against whatever camera
        matrices are currently loaded. Shared by the normal single-eye pass
        and each stereo eye pass in paintGL. mv/pr let the stereo per-eye
        loop pass its own just-captured matrices in for frustum culling
        (self._mv_matrix/_proj_matrix are left None in stereo mode -- see
        paintGL -- since each eye needs its own off-axis projection)."""
        if self.show_grid and not self._scene_scan().has_grid:
            # Procedural backdrop only for scenes with no real World Grid —
            # once one exists, its own lattice is the reference plane and the
            # decoration's unrelated spacing would just fight it.
            self._draw_grid()
        if self.show_axes:
            self._draw_axes()

        # Retained-mode fast path: when nothing about the scene's *content*
        # has changed since the last pass (camera motion doesn't count — the
        # camera lives on the modelview stack outside the baked commands),
        # the entire per-node loop is replayed from one compiled display
        # list, eliminating all per-node Python work. The key captures every
        # content-change source: Scene._revision (node edits, gizmo drags,
        # rate animation, base_scale), _assets_rev (texture/video/mesh
        # loads), and the two loop-shape toggles baked into the commands.
        # Channels playback splits the scene: bound subtrees are excluded
        # from the baked list and drawn immediate after it every frame
        # (channel_frame_update refreshes their matrices without bumping
        # _revision, so the key — and the baked static bulk — hold still).
        # Disabled under a draw limit: the decimation cap counts nodes in
        # scene order and can't be split across two passes.
        ch_dynamic = (self._ch_dynamic_ids
                      if self._ch_dynamic_ids and self._draw_limit is None
                      else None)
        key = (self._scene._revision, self._assets_rev,
               self.show_hidden, self._draw_limit,
               self._ch_dynamic_rev if ch_dynamic is not None else None)
        if self._scene_dl and key == self._scene_dl_key:
            for tid in self._scene_dl_video_ids:
                self._video_mgr.get_gl_name(tid)   # keep baked videos marked visible
            glCallList(self._scene_dl)
        elif key == self._scene_dl_last_key:
            # Scene content held still for a full pass — bake it now, then
            # replay. (Rate-animated scenes bump _revision every frame and
            # never reach here; they stay on the immediate path below.)
            self._compile_scene_dl(key, skip_ids=ch_dynamic)
            glCallList(self._scene_dl)
        else:
            self._draw_nodes_immediate(self._frustum_planes(mv, pr))
            ch_dynamic = None   # everything (dynamic included) just drew
        self._scene_dl_last_key = key
        if ch_dynamic is not None:
            # Dynamic subtrees draw after the static bulk so translucent
            # animated nodes blend over the baked content. (Like the rest
            # of the renderer, there is no depth sorting — a translucent
            # static in front of a dynamic node blends in bake order.)
            self._ch_ensure_playback_cache()
            self._draw_nodes_immediate(self._frustum_planes(mv, pr),
                                       nodes=self._ch_dynamic_nodes)

        self._draw_selected_outlines()
        self._draw_topology_overlays()
        self._draw_gizmo()

    def _draw_nodes_immediate(self, planes, nodes: list[Node] | None = None,
                              skip_ids: set[int] | None = None):
        """Per-node draw loop with CPU frustum culling — used while scene
        content is actively changing (and by _compile_scene_dl, without
        culling, for the baked list). `nodes` restricts the loop to a
        subset (the Channels dynamic pass); `skip_ids` excludes ids while
        iterating the full scene (the static bake). The two are never
        combined, and the draw limit is disabled whenever either is in
        play (see _draw_scene_content), so the decimation count still sees
        every node in scene order when it is active."""
        visible_count = 0
        for node in (self._scene.nodes if nodes is None else nodes):
            if node.type in NON_VISUAL_TYPES:
                continue
            if node.type == NODE_TYPE_LINK:
                continue   # rendered as lines in _draw_topology_overlays
            if not self.show_hidden and node.hide:
                continue
            if skip_ids is not None and node.id in skip_ids:
                continue
            if self._draw_limit is not None and visible_count >= self._draw_limit:
                break
            # Count this node against the decimation cap regardless of
            # frustum culling, so the \\-key limit stays a stable scene-wide
            # cap rather than fluctuating with camera angle.
            visible_count += 1
            M, gl_matrix, radius = self._scene.node_draw_data(node)
            if planes is not None and not self._sphere_in_frustum(
                    planes, M[0, 3], M[1, 3], M[2, 3], radius * 1.2):
                continue
            self._draw_node(node, gl_matrix)

    def _compile_scene_dl(self, key, skip_ids: set[int] | None = None):
        """Bake the whole per-node draw loop into one display list —
        excluding `skip_ids` (the Channels dynamic set) when given, so
        playback frames can replay the static bulk and immediate-draw only
        the animated subtrees on top (see _draw_scene_content).

        No frustum culling here — the list must stay valid from any camera
        angle (GPU clipping handles off-screen geometry). Selection outlines
        are drawn outside the list (_draw_selected_outlines), so selection
        changes never force a rebake. Texture binds compile into the list by
        GL name; video/GIF managers update the *content* under those same
        names each tick, so playback keeps animating inside the baked list —
        but VideoManager also pauses any video no draw call "used" this
        frame, so we record which video texture_ids got baked in and re-mark
        them every replayed frame (see _draw_scene_content)."""
        if not self._scene_dl:
            self._scene_dl = glGenLists(1)
        self._scene_dl_video_ids = set()
        for node in self._scene.nodes:
            if node.texture_id and not self._tex_mgr.get_gl_name(node.texture_id):
                if self._video_mgr.get_gl_name(node.texture_id):
                    self._scene_dl_video_ids.add(node.texture_id)
            # Pre-warm the per-ratio torus lists: GeoRenderer.draw compiles
            # them lazily, and glNewList must never nest inside the bake
            # below. (The immediate pass usually warmed them already, but a
            # frustum-culled off-screen torus wouldn't be.)
            if node.geometry in (GEO_TORUS, GEO_TORUS_WIRE):
                textured = (node.geometry == GEO_TORUS and node.texture_id
                            and bool(self._tex_mgr.get_gl_name(node.texture_id)
                                     or self._video_mgr.get_gl_name(node.texture_id)))
                self._geo.ensure_torus_list(node.geometry, bool(textured), node.ratio)
        glNewList(self._scene_dl, GL_COMPILE)
        self._draw_nodes_immediate(planes=None, skip_ids=skip_ids)
        glEndList()
        self._scene_dl_key = key

    def _draw_selected_outlines(self):
        """Yellow bounding-box halo around each selected node. Drawn as its
        own pass (not inside _draw_node) so the baked scene display list is
        selection-independent — which also means show_selection_box can gate
        the whole pass without forcing a rebake."""
        if not self.show_selection_box or not self.selected_node_ids:
            return
        visible_count = 0
        limit_ids: set[int] | None = None
        if self._draw_limit is not None:
            # Mirror the draw loop's decimation: only outline nodes that
            # actually rendered.
            limit_ids = set()
            for node in self._scene.nodes:
                if node.type in NON_VISUAL_TYPES or node.type == NODE_TYPE_LINK:
                    continue
                if not self.show_hidden and node.hide:
                    continue
                if visible_count >= self._draw_limit:
                    break
                visible_count += 1
                limit_ids.add(node.id)
        for nid in self.selected_node_ids:
            node = self._scene.node_by_id(nid)
            if node is None or node.type in NON_VISUAL_TYPES or node.type == NODE_TYPE_LINK:
                continue
            if not self.show_hidden and node.hide:
                continue
            if limit_ids is not None and nid not in limit_ids:
                continue
            _, gl_matrix, _ = self._scene.node_draw_data(node)
            glPushMatrix()
            glMultMatrixf(gl_matrix)
            glDisable(GL_LIGHTING)
            glLineWidth(1.5)
            glColor4f(1.0, 0.95, 0.1, 1.0)
            # Bounding box at ±1.05 in unit local space (the matrix's scale
            # makes it track the node's actual rendered size).
            b = 1.05
            glBegin(GL_LINES)
            for sx in (-b, b):
                for sy in (-b, b):
                    glVertex3f(sx, sy, -b); glVertex3f(sx, sy, b)
            for sx in (-b, b):
                for sz in (-b, b):
                    glVertex3f(sx, -b, sz); glVertex3f(sx, b, sz)
            for sy in (-b, b):
                for sz in (-b, b):
                    glVertex3f(-b, sy, sz); glVertex3f(b, sy, sz)
            glEnd()
            glLineWidth(1.0)
            glEnable(GL_LIGHTING)
            glPopMatrix()

    def _frustum_planes(self, mv: np.ndarray | None = None, pr: np.ndarray | None = None
                         ) -> list[tuple[float, float, float, float]] | None:
        """Six view-frustum planes (a,b,c,d), normalized so a point's signed
        distance is a*x+b*y+c*z+d, derived from the projection/modelview
        matrices via the standard Gribb/Hartmann extraction. Falls back to
        self._mv_matrix/_proj_matrix (the single-eye camera) when mv/pr
        aren't passed explicitly; returns None if neither is available yet."""
        mv = self._mv_matrix if mv is None else mv
        pr = self._proj_matrix if pr is None else pr
        if mv is None or pr is None:
            return None
        m = pr @ mv   # row-major: clip = m @ world
        raw = (m[3] + m[0], m[3] - m[0],   # left, right
               m[3] + m[1], m[3] - m[1],   # bottom, top
               m[3] + m[2], m[3] - m[2])   # near, far
        planes = []
        for p in raw:
            n = math.sqrt(p[0] * p[0] + p[1] * p[1] + p[2] * p[2])
            if n < 1e-12:
                n = 1.0
            planes.append((p[0] / n, p[1] / n, p[2] / n, p[3] / n))
        return planes

    @staticmethod
    def _sphere_in_frustum(planes: list[tuple[float, float, float, float]],
                           cx: float, cy: float, cz: float, radius: float) -> bool:
        """True unless the bounding sphere (center, radius) is entirely on
        the outside of some frustum plane. All glyph geometry is compiled at
        unit scale (radius ~1 -- see geometry.py's module docstring), so
        callers pass Scene.node_draw_data's cached max-column-norm radius,
        times headroom for shapes that touch the unit sphere at their
        corners (e.g. cube) and for the selection-outline halo drawn at 1.05."""
        for a, b, c, d in planes:
            if a * cx + b * cy + c * cz + d < -radius:
                return False
        return True

    # World units per texture repeat along a GEO_LINE_PRISM link's length
    # (GL_REPEAT wrap keeps stripe density constant regardless of length),
    # and the conversion from rotate_rate_z's "degrees per cycle" units
    # (repurposed as texture scroll rate for links, see _draw_link_prism)
    # into texture repeats per accumulated rotate_z degree.
    _LINK_TEX_TILE = 1.0
    _LINK_SCROLL_SCALE = 1.0 / 360.0

    def _draw_link_prism(self, link: Node, a_pos, b_pos):
        """GEO_LINE_PRISM: renders a type=7 link as a small textured 4-sided
        (square cross-section) tube between its A-end and B-end instead of a
        flat-color line, so a texture can indicate directed flow -- e.g. for
        directed-graph edges. `ratio` sets the tube's half-width (same field
        the classic line uses for its pixel width). `rotate_rate_z` is
        otherwise inert for links (they apply no rotation), so it's
        repurposed here as a texture scroll rate: the existing rate-animation
        system (_apply_rate_animation) already integrates it into rotate_z
        every frame with zero extra code, and its sign controls flow
        direction (positive scrolls A->B, negative B->A; zero stays static,
        matching every file that doesn't set it)."""
        ax, ay, az = a_pos
        bx, by, bz = b_pos
        dx, dy, dz = bx - ax, by - ay, bz - az
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length < 1e-6:
            return
        dx, dy, dz = dx / length, dy / length, dz / length

        # Arbitrary-up trick: cross the direction with a reference axis not
        # (near-)parallel to it, then cross again for an orthonormal
        # (right, up) basis around the tube's axis.
        ref = (0.0, 0.0, 1.0) if abs(dz) < 0.99 else (1.0, 0.0, 0.0)
        rx, ry, rz = dy * ref[2] - dz * ref[1], dz * ref[0] - dx * ref[2], dx * ref[1] - dy * ref[0]
        rlen = math.sqrt(rx * rx + ry * ry + rz * rz) or 1.0
        rx, ry, rz = rx / rlen, ry / rlen, rz / rlen
        ux, uy, uz = ry * dz - rz * dy, rz * dx - rx * dz, rx * dy - ry * dx

        radius = max(link.ratio, 0.01)
        # Square cross-section corners in (right, up) order: ++, +-, -+, --.
        corners = [
            (rx * s * radius + ux * t * radius,
             ry * s * radius + uy * t * radius,
             rz * s * radius + uz * t * radius)
            for s in (1, -1) for t in (1, -1)
        ]
        # Ring order stepping consistently around the square (++, +-, --, -+).
        loop = [corners[0], corners[1], corners[3], corners[2]]

        gl_tex = 0
        if link.texture_id:
            gl_tex = self._tex_mgr.get_gl_name(link.texture_id)
            if not gl_tex:
                gl_tex = self._video_mgr.get_gl_name(link.texture_id)

        v_b = length / self._LINK_TEX_TILE
        if gl_tex:
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, gl_tex)
            glColor4f(1.0, 1.0, 1.0, link.color_a / 255.0)   # don't tint the flow texture
            v_scroll = link.rotate_z * self._LINK_SCROLL_SCALE
            glMatrixMode(GL_TEXTURE)
            glPushMatrix()
            glLoadIdentity()
            glTranslatef(0.0, v_scroll, 0.0)
            glMatrixMode(GL_MODELVIEW)
        else:
            glColor4f(link.color_r / 255.0, link.color_g / 255.0,
                      link.color_b / 255.0, link.color_a / 255.0)

        glBegin(GL_QUADS)
        for i in range(4):
            c0 = loop[i]
            c1 = loop[(i + 1) % 4]
            u0 = i / 4.0
            u1 = (i + 1) / 4.0
            # Vertex order (c0, c1, B+c1, B+c0): winds each face CCW as seen
            # from outside so it survives paintGL's GL_CULL_FACE(GL_BACK) --
            # empirically verified with a headless render (a prior hand
            # derivation got the sign backwards and rendered the inside of
            # the tube instead; fixed after Jeff caught it visually).
            glTexCoord2f(u0, 0.0)
            glVertex3f(ax + c0[0], ay + c0[1], az + c0[2])
            glTexCoord2f(u1, 0.0)
            glVertex3f(ax + c1[0], ay + c1[1], az + c1[2])
            glTexCoord2f(u1, v_b)
            glVertex3f(bx + c1[0], by + c1[1], bz + c1[2])
            glTexCoord2f(u0, v_b)
            glVertex3f(bx + c0[0], by + c0[1], bz + c0[2])
        glEnd()

        if gl_tex:
            glMatrixMode(GL_TEXTURE)
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)
            glDisable(GL_TEXTURE_2D)

    def _draw_topology_overlays(self):
        """Draw type=7 link lines, TOPO_PLOT polylines, and TOPO_SURFACE quad meshes."""
        # Membership comes from the per-revision scene scan — most scenes
        # (no links/plots/surfaces) return here without touching the node
        # list, and the parent→children map is built once per revision, not
        # once per frame.
        scan = self._scene_scan()
        link_nodes = scan.link_nodes
        plot_nodes = scan.plot_nodes
        surface_nodes = scan.surface_nodes
        if self._ch_dynamic_ids:
            # Channels can animate `topo`, so a node may have entered or left
            # Plot/Surface since the scan was built — and the scan is keyed on
            # Scene._revision, which the playback fast path deliberately never
            # bumps (same reasoning as the rate-node union in
            # _apply_rate_animation). Re-derive membership for the dynamic set
            # only: drop every dynamic node from the cached lists, then re-add
            # the ones whose topo currently says so. A type=7 link's topo is
            # meaningless — it renders as a line, not a polyline parent.
            self._ch_ensure_playback_cache()
            dyn = self._ch_dynamic_ids
            plot_nodes = [n for n in plot_nodes if n.id not in dyn]
            surface_nodes = [n for n in surface_nodes if n.id not in dyn]
            for n in self._ch_dynamic_nodes:
                if n.type == NODE_TYPE_LINK:
                    continue
                if n.topo == TOPO_PLOT:
                    plot_nodes.append(n)
                elif n.topo == TOPO_SURFACE:
                    surface_nodes.append(n)
        if not link_nodes and not plot_nodes and not surface_nodes:
            return
        children_of = (scan.children_map(self._scene.nodes)
                       if (plot_nodes or surface_nodes) else {})

        glDisable(GL_LIGHTING)

        # ---- Type-7 link lines ----
        for link in link_nodes:
            if not self.show_hidden and link.hide:
                continue
            a_id = link.parent_id
            b_id = int(float(link.extras.get('child_id', 0)))
            if not a_id or not b_id:
                continue
            a_pos = self._scene.world_pos(a_id)
            b_pos = self._scene.world_pos(b_id)
            if a_pos is None or b_pos is None:
                continue
            if link.geometry == GEO_LINE_PRISM:
                self._draw_link_prism(link, a_pos, b_pos)
                continue
            width = max(link.ratio * 20.0, 1.0)
            glLineWidth(width)
            glColor4f(link.color_r / 255.0, link.color_g / 255.0,
                      link.color_b / 255.0, link.color_a / 255.0)
            glBegin(GL_LINES)
            glVertex3f(a_pos[0], a_pos[1], a_pos[2])
            glVertex3f(b_pos[0], b_pos[1], b_pos[2])
            glEnd()
            # Round end caps: GL_LINE_SMOOTH antialiases a line's edges but
            # its caps stay flat/square, so stamp an antialiased GL_POINTS
            # dot (same width) at each endpoint to round them off too.
            glPointSize(width)
            glBegin(GL_POINTS)
            glVertex3f(a_pos[0], a_pos[1], a_pos[2])
            glVertex3f(b_pos[0], b_pos[1], b_pos[2])
            glEnd()

        # ---- TOPO_PLOT polylines ----
        if plot_nodes:
            for node in plot_nodes:
                if not self.show_hidden and node.hide:
                    continue
                kids = [k for k in children_of.get(node.id, [])
                        if self.show_hidden or not k.hide]
                if len(kids) < 2:
                    continue
                width = max(node.ratio * 20.0, 1.0)
                kid_positions = [
                    self._scene.world_pos(kid.id) or
                    (kid.translate_x, kid.translate_y, kid.translate_z)
                    for kid in kids
                ]
                glLineWidth(width)
                glBegin(GL_LINE_STRIP)
                for kid, pos in zip(kids, kid_positions):
                    glColor4f(kid.color_r / 255.0, kid.color_g / 255.0,
                              kid.color_b / 255.0, kid.color_a / 255.0)
                    glVertex3f(pos[0], pos[1], pos[2])
                glEnd()
                # Round caps/joins: see the matching comment in the link-line
                # block above -- one antialiased point per vertex, including
                # interior joints, so corners aren't left mitred/jagged.
                glPointSize(width)
                glBegin(GL_POINTS)
                for kid, pos in zip(kids, kid_positions):
                    glColor4f(kid.color_r / 255.0, kid.color_g / 255.0,
                              kid.color_b / 255.0, kid.color_a / 255.0)
                    glVertex3f(pos[0], pos[1], pos[2])
                glEnd()

        glLineWidth(1.0)
        glPointSize(1.0)

        # ---- TOPO_SURFACE quad meshes (with lighting for 3-D shading) ----
        if surface_nodes:
            glEnable(GL_LIGHTING)
            for node in surface_nodes:
                if not self.show_hidden and node.hide:
                    continue
                kids = [k for k in children_of.get(node.id, [])
                        if self.show_hidden or not k.hide]
                if len(kids) < 4:
                    continue

                # Build (translate_x, translate_y) → node grid.
                # Children use translate_z as height at that grid point.
                grid: dict[tuple[float, float], Node] = {}
                for kid in kids:
                    grid[(round(kid.translate_x, 6), round(kid.translate_y, 6))] = kid
                xs = sorted(set(k[0] for k in grid))
                ys = sorted(set(k[1] for k in grid))
                if len(xs) < 2 or len(ys) < 2:
                    continue

                glBegin(GL_QUADS)
                for ri in range(len(ys) - 1):
                    for ci in range(len(xs) - 1):
                        n00 = grid.get((xs[ci],     ys[ri]))
                        n10 = grid.get((xs[ci + 1], ys[ri]))
                        n11 = grid.get((xs[ci + 1], ys[ri + 1]))
                        n01 = grid.get((xs[ci],     ys[ri + 1]))
                        if n00 is None or n10 is None or n11 is None or n01 is None:
                            continue
                        p00 = self._scene.world_pos(n00.id) or (n00.translate_x, n00.translate_y, n00.translate_z)
                        p10 = self._scene.world_pos(n10.id) or (n10.translate_x, n10.translate_y, n10.translate_z)
                        p11 = self._scene.world_pos(n11.id) or (n11.translate_x, n11.translate_y, n11.translate_z)
                        p01 = self._scene.world_pos(n01.id) or (n01.translate_x, n01.translate_y, n01.translate_z)
                        # Per-face normal from cross product (CCW winding → outward normal)
                        ea = np.asarray(p10, dtype=np.float64) - np.asarray(p00, dtype=np.float64)
                        eb = np.asarray(p01, dtype=np.float64) - np.asarray(p00, dtype=np.float64)
                        norm = np.cross(ea, eb)
                        nl = np.linalg.norm(norm)
                        if nl > 1e-10:
                            norm /= nl
                        else:
                            norm = np.array([0.0, 0.0, 1.0])
                        glNormal3f(float(norm[0]), float(norm[1]), float(norm[2]))
                        for nn, pp in ((n00, p00), (n10, p10), (n11, p11), (n01, p01)):
                            glColor4f(nn.color_r / 255.0, nn.color_g / 255.0,
                                      nn.color_b / 255.0, nn.color_a / 255.0)
                            glVertex3f(float(pp[0]), float(pp[1]), float(pp[2]))
                glEnd()

        glEnable(GL_LIGHTING)  # restore for subsequent passes (rubber band, etc.)

    def _tag_pin_state(self, node: Node) -> bool | None:
        """Whether this node's label should draw at all, and if so whether it
        is pinned. None = don't draw. Shared by the ordinary-node and Link
        collection passes so the two can't drift apart on tag settings.

        A pinned node (show_text) ignores both scene-wide tag settings. Its
        own hide flag and the draw limit are NOT checked here — those decide
        whether the object is on screen at all, and each caller applies the
        rule its own draw path uses."""
        if not node.text:
            return None
        pinned = bool(node.show_text)
        if not pinned:
            if not self.show_tags:
                return None
            if self.show_tags_selected_only and node.id not in self.selected_node_ids:
                return None
        return pinned

    def _link_label_anchor(self, link: Node) -> tuple[float, float, float] | None:
        """World position for a Link's tag label: the midpoint of the edge it
        draws. When the B-end is missing or unresolvable — the link draws no
        line but is still selectable — fall back to the link's own position,
        which is exactly where _begin_pick_scene puts its fallback pick
        sphere, so the label sits on what a click would hit."""
        a_id = link.parent_id
        b_id = int(float(link.extras.get('child_id', 0)))
        a_pos = self._scene.world_pos(a_id) if a_id else None
        b_pos = self._scene.world_pos(b_id) if b_id else None
        if a_pos is not None and b_pos is not None:
            return ((a_pos[0] + b_pos[0]) / 2.0,
                    (a_pos[1] + b_pos[1]) / 2.0,
                    (a_pos[2] + b_pos[2]) / 2.0)
        return self._scene.world_pos(link.id)

    def _project_tagged_nodes(self, mv: np.ndarray, pr: np.ndarray,
                               vx: int, vy: int, vw: int, vh: int
                               ) -> list[tuple[str, int, int, tuple | None]]:
        """World->screen project every tagged, visible node's position using
        the given camera matrices into the (vx, vy, vw, vh) viewport sub-rect
        (Qt widget coordinates). Used for both the full-widget single-eye
        view and each half-width stereo eye view.

        Covers ordinary glyphs and Link (type=7) nodes alike — a link's label
        anchors to the middle of the edge — under identical tag settings.

        Returns (text, screen_x, screen_y, rgb) tuples; rgb is the node's own
        color under TAG_COLOR_MODE_NODE and None under the uniform mode, where
        _paint_tags uses the World node's single tag color for every label."""
        # Selected-only mode draws every selected tag, uncapped: the user
        # explicitly scoped the set, so completeness beats frame rate there.
        # The cap only guards the unscoped all-tags mode. Individually pinned
        # tags (show_text) are exempt too, for the same reason — see below.
        cap = None if self.show_tags_selected_only else _MAX_TAGS_PER_FRAME
        world = self._scene.world_node()
        per_node_color = (world is not None
                          and world.tag_color_mode == TAG_COLOR_MODE_NODE)

        # Pass 1: collect eligible (text, world-pos) pairs in scene order,
        # remembering which ones are pinned so the cap can skip them.
        texts: list[str] = []
        positions: list[tuple[float, float, float]] = []
        colors: list[tuple[int, int, int] | None] = []
        pinned_flags: list[bool] = []
        any_pinned = False
        visible_count = 0
        for node in self._scene.nodes:
            if node.type in NON_VISUAL_TYPES:
                continue
            if node.type == NODE_TYPE_LINK:
                continue   # links carry labels too — collected in pass 1b
            if not self.show_hidden and node.hide:
                continue
            if self._draw_limit is not None and visible_count >= self._draw_limit:
                break
            visible_count += 1
            pinned = self._tag_pin_state(node)
            if pinned is None:
                continue
            wp = self._scene.world_pos(node.id) or (node.translate_x, node.translate_y, node.translate_z)
            texts.append(node.text)
            positions.append(wp)
            colors.append((node.color_r, node.color_g, node.color_b)
                          if per_node_color else None)
            pinned_flags.append(pinned)
            any_pinned |= pinned

        # Pass 1b: Link (type=7) labels, anchored to the middle of the edge.
        # Links get their own pass off the scan list because that is exactly
        # how _draw_topology_overlays draws them — irrespective of the \ draw
        # limit, whose early break above exists to keep that limit O(visible)
        # instead of O(scene). Every tag setting applies to them identically.
        # They land after the ordinary nodes, so in the rare scene that both
        # exceeds the cap AND labels its links, node labels win the budget.
        for link in self._scene_scan().link_nodes:
            if not self.show_hidden and link.hide:
                continue
            pinned = self._tag_pin_state(link)
            if pinned is None:
                continue
            anchor = self._link_label_anchor(link)
            if anchor is None:
                continue
            texts.append(link.text)
            positions.append(anchor)
            colors.append((link.color_r, link.color_g, link.color_b)
                          if per_node_color else None)
            pinned_flags.append(pinned)
            any_pinned |= pinned

        if not texts:
            return []

        # Pass 2: project every candidate in one batched matrix multiply —
        # per-node 4x4 @ 4-vec numpy calls cost seconds at tens of thousands
        # of tags, the batch is milliseconds.
        mvp = pr @ mv
        pos = np.ones((len(positions), 4), dtype=np.float64)
        pos[:, :3] = positions
        clip = pos @ mvp.T
        w_clip = clip[:, 3]
        with np.errstate(divide='ignore', invalid='ignore'):
            ndc = clip[:, :3] / w_clip[:, None]
        on_screen = (
            (w_clip > 0)
            & (ndc[:, 0] >= -1.0) & (ndc[:, 0] <= 1.0)
            & (ndc[:, 1] >= -1.0) & (ndc[:, 1] <= 1.0)
            & (ndc[:, 2] >= -1.0) & (ndc[:, 2] <= 1.0)
        )
        sx_all = vx + ((ndc[:, 0] + 1.0) / 2.0 * vw).astype(np.int64)
        sy_all = vy + ((1.0 - (ndc[:, 1] + 1.0) / 2.0) * vh).astype(np.int64)  # Y-flip for Qt

        # Apply the safety valve to the ORDINARY tags only. Truncating the
        # combined list instead would silently drop pinned tags that happen to
        # sit late in scene order — the cap is a frame-rate guard on the
        # unscoped all-tags mode, never on labels the user asked for by name.
        selected = np.flatnonzero(on_screen)
        if cap is not None and len(selected) > cap:
            if any_pinned:
                is_pinned = np.asarray(pinned_flags, dtype=bool)[selected]
                # union1d re-sorts, so the kept tags stay in scene order.
                selected = np.union1d(selected[~is_pinned][:cap],
                                      selected[is_pinned])
            else:
                selected = selected[:cap]

        return [(texts[i], int(sx_all[i]), int(sy_all[i]), colors[i])
                for i in selected]

    def _paint_tags(self, painter: QPainter,
                    tagged: list[tuple[str, int, int, tuple | None]]):
        # Single-pen passes (shadow, then face) over cached QStaticText:
        # per-tag setPen switching plus per-call text layout is what made
        # thousands of tags cost seconds per frame. drawStaticText anchors at
        # the TOP-left, drawText at the baseline — subtract the ascent to
        # keep the exact placement the old drawText calls had.
        cache = self._tag_text_cache
        if len(cache) > 100_000:
            cache.clear()   # size guard against per-frame text churn
        statics = []
        for text, sx, sy, rgb in tagged:
            st = cache.get(text)
            if st is None:
                st = cache[text] = QStaticText(text)
            statics.append((st, sx, sy, rgb))
        top_offset = painter.fontMetrics().ascent()
        painter.setPen(QColor(*TAG_SHADOW_RGBA))
        for st, sx, sy, _rgb in statics:
            painter.drawStaticText(sx + 6, sy + 1 - top_offset, st)

        world = self._scene.world_node()
        if world is not None and world.tag_color_mode == TAG_COLOR_MODE_NODE:
            # Group by color so the face pass is still one setPen per distinct
            # color rather than one per label — a scene colored by category
            # has a handful of them however many labels are on screen.
            by_color: dict[tuple, list] = {}
            for st, sx, sy, rgb in statics:
                by_color.setdefault(rgb, []).append((st, sx, sy))
            for rgb, items in by_color.items():
                painter.setPen(QColor(*rgb, TAG_TEXT_ALPHA))
                for st, sx, sy in items:
                    painter.drawStaticText(sx + 5, sy - top_offset, st)
            return

        if world is not None:
            face = (world.tag_color_r, world.tag_color_g, world.tag_color_b)
        else:
            face = TAG_DEFAULT_TEXT_RGB
        painter.setPen(QColor(*face, TAG_TEXT_ALPHA))
        for st, sx, sy, _rgb in statics:
            painter.drawStaticText(sx + 5, sy - top_offset, st)

    def _draw_tags_qpainter(self):
        """Project tagged nodes to screen space and draw text with QPainter overlay."""
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        tagged = self._project_tagged_nodes(self._mv_matrix, self._proj_matrix, 0, 0, w, h)
        if not tagged:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        self._paint_tags(painter, tagged)
        painter.end()

    def _draw_tags_qpainter_stereo(self, batches: list[tuple[int, int, np.ndarray, np.ndarray]]):
        """Stereo equivalent of _draw_tags_qpainter: project and draw each
        eye's tags into its own screen half. batches is a list of
        (screen_x, seg_w, mv, pr) -- one entry per eye pass."""
        h = self.height()
        if h <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        for screen_x, seg_w, mv, pr in batches:
            tagged = self._project_tagged_nodes(mv, pr, screen_x, 0, seg_w, h)
            self._paint_tags(painter, tagged)
        painter.end()

    def _draw_node(self, node: Node, gl_matrix: np.ndarray):
        # gl_matrix is Scene.node_draw_data's cached column-major float32
        # form of node_world_matrix — the single source of truth, shared
        # with the pick pass, so rendering and picking are identical by
        # construction. Selection outlines are a separate pass
        # (_draw_selected_outlines) so this body can compile into the
        # retained scene display list unchanged.
        if node.type == NODE_TYPE_GRID:
            self._draw_world_grid(node, gl_matrix)
            return
        glPushMatrix()
        glMultMatrixf(gl_matrix)

        glColor4f(
            node.color_r / 255.0,
            node.color_g / 255.0,
            node.color_b / 255.0,
            node.color_a / 255.0,
        )

        gl_tex = 0
        if node.texture_id:
            gl_tex = self._tex_mgr.get_gl_name(node.texture_id)
            if not gl_tex:
                gl_tex = self._video_mgr.get_gl_name(node.texture_id)

        # M already encodes scale (column norms = rendered radii), so we draw
        # the geometry at unit size (1,1,1) and let the matrix handle sizing.
        self._geo.draw(node.geometry, 1.0, 1.0, 1.0, ratio=node.ratio, gl_tex_name=gl_tex,
                       mesh_id=node.mesh_id)

        glPopMatrix()

    # Globe tessellation (unit sphere, scaled to GRID_GLOBE_RADIUS x node
    # scale by the draw matrix). A single grid node draws this immediate-mode
    # once per bake, so density is chosen for smooth texture mapping.
    _GLOBE_SLICES = 48   # longitude bands
    _GLOBE_STACKS = 24   # latitude bands

    def _draw_world_grid(self, node: Node, gl_matrix: np.ndarray):
        """Bespoke draw path for World Grid nodes (type=6), flat or globe.

        The draw matrix already carries the shape's half-spans times the
        node's raw scale (see scene._grid_draw_scale), so everything here
        renders in ±1 local units. Flat form: lattice lines at the node's
        segments_x/y counts, plus — for a solid geometry choice — a
        double-sided plate taking the node's texture (an equirectangular
        earth map matches the default whole-earth window exactly). Globe form
        (Node.grid_is_globe): a lon/lat graticule and, when solid, a unit
        sphere with exact equirect UVs (u=(lon+180)/360, v=(lat+90)/180 —
        gluSphere's mapping is offset AND mirrored in longitude relative to
        KML, so the sphere is built here instead). Both draw unlit so the
        map reads at full brightness with no day/night shading."""
        seg_x, seg_y = node.grid_segments()
        wire_only = node.geometry in WIRE_TO_SOLID   # any *_WIRE geometry id
        globe = node.grid_is_globe()

        glPushMatrix()
        glMultMatrixf(gl_matrix)
        glDisable(GL_LIGHTING)

        r, g, b, a = (node.color_r / 255.0, node.color_g / 255.0,
                      node.color_b / 255.0, node.color_a / 255.0)
        if not wire_only:
            gl_tex = 0
            if node.texture_id:
                gl_tex = self._tex_mgr.get_gl_name(node.texture_id)
                if not gl_tex:
                    gl_tex = self._video_mgr.get_gl_name(node.texture_id)
            if gl_tex:
                glEnable(GL_TEXTURE_2D)
                glBindTexture(GL_TEXTURE_2D, gl_tex)
                glColor4f(1.0, 1.0, 1.0, a)   # don't tint the map texture
            else:
                glColor4f(r, g, b, a)
            if globe:
                self._globe_surface(textured=bool(gl_tex))
            else:
                self._grid_plate(textured=True)
            if gl_tex:
                glDisable(GL_TEXTURE_2D)

        # Lattice/graticule lines. Over a solid surface they dim toward half
        # opacity for contrast and lift slightly off the surface (in local
        # units, so the offset scales with the grid).
        if wire_only:
            glColor4f(r, g, b, a)
        else:
            glColor4f(r, g, b, a * 0.5)
        glLineWidth(1.0)
        if globe:
            self._globe_graticule(seg_x, seg_y,
                                  radius=1.0 if wire_only else 1.002)
        else:
            z = 0.0 if wire_only else 0.001
            glBegin(GL_LINES)
            for i in range(seg_x + 1):
                x = -1.0 + 2.0 * i / seg_x
                glVertex3f(x, -1.0, z)
                glVertex3f(x, 1.0, z)
            for j in range(seg_y + 1):
                y = -1.0 + 2.0 * j / seg_y
                glVertex3f(-1.0, y, z)
                glVertex3f(1.0, y, z)
            glEnd()

        glEnable(GL_LIGHTING)
        glPopMatrix()

    @staticmethod
    def _grid_plate(textured: bool):
        """±1 double-sided flat plate (GEO_GRID's UV convention: v grows
        with +y). Shared by the draw pass and the pick pass's occluder."""
        glBegin(GL_QUADS)
        glNormal3f(0.0, 0.0, 1.0)
        for x, y, u, v in ((-1, -1, 0, 0), (1, -1, 1, 0),
                           (1, 1, 1, 1), (-1, 1, 0, 1)):
            if textured:
                glTexCoord2f(u, v)
            glVertex3f(x, y, 0.0)
        glNormal3f(0.0, 0.0, -1.0)
        for x, y, u, v in ((-1, 1, 0, 1), (1, 1, 1, 1),
                           (1, -1, 1, 0), (-1, -1, 0, 0)):
            if textured:
                glTexCoord2f(u, v)
            glVertex3f(x, y, 0.0)
        glEnd()

    @classmethod
    def _globe_surface(cls, textured: bool):
        """Unit sphere as latitude-band quad strips with KML-aligned equirect
        UVs: lon 0 faces +X (u=0.5), u grows eastward, v grows northward."""
        slices, stacks = cls._GLOBE_SLICES, cls._GLOBE_STACKS
        for j in range(stacks):
            lat0 = math.radians(-90.0 + 180.0 * j / stacks)
            lat1 = math.radians(-90.0 + 180.0 * (j + 1) / stacks)
            z0, c0 = math.sin(lat0), math.cos(lat0)
            z1, c1 = math.sin(lat1), math.cos(lat1)
            v0, v1 = j / stacks, (j + 1) / stacks
            glBegin(GL_QUAD_STRIP)
            for i in range(slices + 1):
                lon = math.radians(-180.0 + 360.0 * i / slices)
                cl, sl = math.cos(lon), math.sin(lon)
                u = i / slices
                if textured:
                    glTexCoord2f(u, v1)
                glNormal3f(c1 * cl, c1 * sl, z1)
                glVertex3f(c1 * cl, c1 * sl, z1)
                if textured:
                    glTexCoord2f(u, v0)
                glNormal3f(c0 * cl, c0 * sl, z0)
                glVertex3f(c0 * cl, c0 * sl, z0)
            glEnd()

    @classmethod
    def _globe_graticule(cls, seg_x: int, seg_y: int, radius: float):
        """Meridians (seg_x of them) and parallels (seg_y bands' edges,
        poles excluded) on a sphere of `radius` in local units."""
        arc = cls._GLOBE_SLICES  # vertices per full circle
        for i in range(seg_x):
            lon = math.radians(-180.0 + 360.0 * i / seg_x)
            cl, sl = math.cos(lon), math.sin(lon)
            glBegin(GL_LINE_STRIP)
            for j in range(arc + 1):
                lat = math.radians(-90.0 + 180.0 * j / arc)
                c, z = math.cos(lat), math.sin(lat)
                glVertex3f(radius * c * cl, radius * c * sl, radius * z)
            glEnd()
        for j in range(1, seg_y):
            lat = math.radians(-90.0 + 180.0 * j / seg_y)
            c, z = math.cos(lat), math.sin(lat)
            glBegin(GL_LINE_LOOP)
            for i in range(arc):
                lon = math.radians(-180.0 + 360.0 * i / arc)
                glVertex3f(radius * c * math.cos(lon),
                           radius * c * math.sin(lon), radius * z)
            glEnd()

    def _draw_rubber_band(self):
        """Draw a semi-transparent rectangle in 2D screen space for rubber-band select."""
        x1 = min(self._rubber_start.x(), self._rubber_end.x())
        y1 = min(self._rubber_start.y(), self._rubber_end.y())
        x2 = max(self._rubber_start.x(), self._rubber_end.x())
        y2 = max(self._rubber_start.y(), self._rubber_end.y())
        w, h = self.width(), self.height()

        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glDisable(GL_CULL_FACE)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        # Top-left origin matches Qt widget coordinates
        glOrtho(0, w, h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        # Semi-transparent fill
        glColor4f(0.2, 0.6, 1.0, 0.12)
        glBegin(GL_QUADS)
        glVertex2f(x1, y1); glVertex2f(x2, y1)
        glVertex2f(x2, y2); glVertex2f(x1, y2)
        glEnd()

        # Solid border
        glColor4f(0.3, 0.7, 1.0, 0.9)
        glLineWidth(1.5)
        glBegin(GL_LINE_LOOP)
        glVertex2f(x1, y1); glVertex2f(x2, y1)
        glVertex2f(x2, y2); glVertex2f(x1, y2)
        glEnd()
        glLineWidth(1.0)

        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_CULL_FACE)

    def _draw_axes(self):
        glDisable(GL_LIGHTING)
        glLineWidth(2.0)
        span = self._cam_distance * 0.15
        glBegin(GL_LINES)
        glColor3f(1.0, 0.2, 0.2); glVertex3f(0, 0, 0); glVertex3f(span, 0, 0)
        glColor3f(0.2, 1.0, 0.2); glVertex3f(0, 0, 0); glVertex3f(0, span, 0)
        glColor3f(0.2, 0.4, 1.0); glVertex3f(0, 0, 0); glVertex3f(0, 0, span)
        glEnd()
        glLineWidth(1.0)
        glEnable(GL_LIGHTING)

    def _draw_grid(self):
        """Procedural reference grid (no World Grid node in the scene). Its
        color comes from the World node's ref_grid_color_r/g/b, falling back
        to the historical gray when the scene has no World row."""
        glDisable(GL_LIGHTING)
        world = self._scene.world_node()
        if world is not None:
            glColor3f(world.ref_grid_color_r / 255.0,
                      world.ref_grid_color_g / 255.0,
                      world.ref_grid_color_b / 255.0)
        else:
            glColor3f(*_DEFAULT_REF_GRID)
        glLineWidth(1.0)
        step = max(10.0, self._cam_distance * 0.04)
        count = 20
        size = step * count
        glBegin(GL_LINES)
        for i in range(-count, count + 1):
            glVertex3f(i * step, -size, 0.0)
            glVertex3f(i * step,  size, 0.0)
            glVertex3f(-size, i * step, 0.0)
            glVertex3f( size, i * step, 0.0)
        glEnd()
        glEnable(GL_LIGHTING)

    # --- color-ID FBO picking ---

    def _ensure_pick_fbo(self, fb_w: int, fb_h: int):
        """Create or recreate the pick FBO if the framebuffer size changed."""
        if self._pick_fbo_size == (fb_w, fb_h):
            return
        self._cleanup_pick_fbo()

        fbo = glGenFramebuffers(1)
        self._pick_fbo = int(fbo) if not hasattr(fbo, '__len__') else int(fbo[0])
        glBindFramebuffer(GL_FRAMEBUFFER, self._pick_fbo)

        tex = glGenTextures(1)
        self._pick_tex = int(tex) if not hasattr(tex, '__len__') else int(tex[0])
        glBindTexture(GL_TEXTURE_2D, self._pick_tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, fb_w, fb_h, 0,
                     GL_RGB, GL_UNSIGNED_BYTE, None)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                               GL_TEXTURE_2D, self._pick_tex, 0)

        rbo = glGenRenderbuffers(1)
        self._pick_rbo = int(rbo) if not hasattr(rbo, '__len__') else int(rbo[0])
        glBindRenderbuffer(GL_RENDERBUFFER, self._pick_rbo)
        glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, fb_w, fb_h)
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT,
                                  GL_RENDERBUFFER, self._pick_rbo)

        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if status != GL_FRAMEBUFFER_COMPLETE:
            print(f"[pick] FBO incomplete (status={status:#x})")

        # Restore Qt's own FBO
        glBindFramebuffer(GL_FRAMEBUFFER, self.defaultFramebufferObject())
        self._pick_fbo_size = (fb_w, fb_h)

    def _cleanup_pick_fbo(self):
        if self._pick_fbo:
            glDeleteFramebuffers(1, [self._pick_fbo])
            glDeleteTextures(1, [self._pick_tex])
            glDeleteRenderbuffers(1, [self._pick_rbo])
        self._pick_fbo = self._pick_tex = self._pick_rbo = 0
        self._pick_fbo_size = (0, 0)

    def _render_pick_scene(self, seg_w: float | None = None, lateral_offset: float = 0.0) -> tuple | None:
        """
        Bind the pick FBO and render all glyphs with color-ID encoding.

        seg_w: width (Qt logical px) to use for the perspective aspect ratio
        and FBO sizing instead of self.width() -- used for stereo per-eye
        picking, where a click falls within one half of the split widget.
        lateral_offset: camera eye lateral offset (world units), matching
        paintGL's stereo eye offset; 0.0 (the default) is the normal
        single-eye camera.

        Returns (qt_fbo, fb_w, fb_h, dpr, w, h) with the GL state ready for
        glReadPixels, or None if setup failed.  Caller MUST call
        _finish_pick_scene() afterward to restore GL state.

        Must be called between makeCurrent() / doneCurrent().
        """
        if not self._scene.nodes:
            return None
        w = seg_w if seg_w is not None else self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return None
        dpr = self.devicePixelRatio()
        fb_w = max(1, int(w * dpr))
        fb_h = max(1, int(h * dpr))

        self._ensure_pick_fbo(fb_w, fb_h)
        qt_fbo = self.defaultFramebufferObject()
        glBindFramebuffer(GL_FRAMEBUFFER, self._pick_fbo)
        glViewport(0, 0, fb_w, fb_h)
        glClearColor(0.0, 0.0, 0.0, 0.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # Mirror paintGL's projection and camera setup exactly (including the
        # per-eye off-axis frustum/eye-space shift when called for stereo-mode
        # picking -- see _setup_stereo_eye_matrices).
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()

        if seg_w is not None:
            self._setup_stereo_eye_matrices(lateral_offset, w, h)
        else:
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            gluPerspective(45.0, w / h, 0.1, 100000.0)
            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()
            eye_x, eye_y, eye_z = self._eye_position_with_offset(lateral_offset)
            tx, ty, tz = self._cam_target
            up_x, up_y, up_z = self._camera_up()
            gluLookAt(eye_x, eye_y, eye_z, tx, ty, tz, up_x, up_y, up_z)

        glDisable(GL_LIGHTING)
        glDisable(GL_BLEND)
        glDisable(GL_FOG)  # fog tints fragment color by distance — would corrupt color-ID reads
        # Point/line antialiasing blends edge pixels toward the background —
        # would corrupt color-ID reads at glyph silhouettes the same way fog does.
        glDisable(GL_POINT_SMOOTH)
        glDisable(GL_LINE_SMOOTH)

        # Re-use the scene cache from the most recent paint (no invalidate here).
        # Mirror paintGL's _draw_limit cutoff so nodes hidden by the
        # backslash decimation aren't pickable — except already-selected
        # nodes, which stay pickable/modifiable even past the cutoff
        # (matches ANTz: selecting then hiding keeps the selection live).
        visible_count = 0
        for node in self._scene.nodes:
            if node.type in NON_VISUAL_TYPES:
                continue
            if node.type == NODE_TYPE_LINK:
                continue   # links are picked via lines below
            if not self.show_hidden and node.hide:
                continue
            if node.type == NODE_TYPE_GRID:
                # World Grids are never click/rubber-band targets: a grid
                # usually fills the view under its children, so making it
                # pickable would swallow every near-miss click meant for a
                # glyph. Select a grid with the G key (cycles through grids,
                # ANTz-style), the node table, or the World Grid panel; once
                # selected, Move/Rotate/Size drags apply to it as normal.
                # Still counted against the draw limit so this pass's
                # decimation cutoff stays aligned with the draw loop's.
                if self._draw_limit is None or visible_count < self._draw_limit:
                    visible_count += 1
                # A SOLID grid surface visually occludes glyphs behind it
                # (especially a globe's far side), so render it into the
                # pick depth buffer as color-ID 0: clicks on it read as
                # background rather than selecting something hidden. Wire
                # grids see through, so they get no occluder.
                if node.geometry not in WIRE_TO_SOLID:
                    glColor4ub(0, 0, 0, 255)
                    _, gl_matrix, _ = self._scene.node_draw_data(node)
                    glPushMatrix()
                    glMultMatrixf(gl_matrix)
                    if node.grid_is_globe():
                        self._globe_surface(textured=False)
                    else:
                        self._grid_plate(textured=False)
                    glPopMatrix()
                continue
            is_selected = node.id in self.selected_node_ids
            within_limit = self._draw_limit is None or visible_count < self._draw_limit
            if within_limit:
                visible_count += 1
            elif not is_selected:
                continue
            r = node.id & 0xFF
            g = (node.id >> 8) & 0xFF
            b = (node.id >> 16) & 0xFF
            glColor4ub(r, g, b, 255)
            _, gl_matrix, _ = self._scene.node_draw_data(node)
            glPushMatrix()
            glMultMatrixf(gl_matrix)
            # Draw the solid equivalent for wireframe geometries so the
            # entire silhouette is pickable, not just the visible wires.
            pick_geo = WIRE_TO_SOLID.get(node.geometry, node.geometry)
            self._geo.draw(pick_geo, 1.0, 1.0, 1.0, ratio=node.ratio, mesh_id=node.mesh_id)
            glPopMatrix()

        # Draw link nodes as pick targets.  Each link gets:
        #   1. A thick line between its endpoints (when both endpoints resolve).
        #   2. A small sphere at its own world position so it's always clickable
        #      even when the B-end (child_id) is missing or 0.
        for node in self._scene.nodes:
            if node.type != NODE_TYPE_LINK:
                continue
            if not self.show_hidden and node.hide:
                continue
            r = node.id & 0xFF
            g = (node.id >> 8) & 0xFF
            b_enc = (node.id >> 16) & 0xFF
            glColor4ub(r, g, b_enc, 255)

            a_id = node.parent_id
            b_id = int(float(node.extras.get('child_id', 0)))
            a_pos = self._scene.world_pos(a_id) if a_id else None
            b_pos = self._scene.world_pos(b_id) if b_id else None
            if a_pos is not None and b_pos is not None:
                glLineWidth(max(node.ratio * 20.0, 5.0))
                glBegin(GL_LINES)
                glVertex3f(a_pos[0], a_pos[1], a_pos[2])
                glVertex3f(b_pos[0], b_pos[1], b_pos[2])
                glEnd()
                glLineWidth(1.0)

            # Fallback sphere at the link node's own position.
            own_pos = self._scene.world_pos(node.id)
            if own_pos is not None:
                _, gl_matrix, _ = self._scene.node_draw_data(node)
                glPushMatrix()
                glMultMatrixf(gl_matrix)
                self._geo.draw(3, 1.0, 1.0, 1.0)   # GEO_SPHERE = 3
                glPopMatrix()

        return qt_fbo, fb_w, fb_h, dpr, w, h

    def _finish_pick_scene(self, qt_fbo: int, fb_w: int, fb_h: int):
        """Restore GL state after reading from the pick FBO."""
        glEnable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glBindFramebuffer(GL_FRAMEBUFFER, qt_fbo)
        glViewport(0, 0, fb_w, fb_h)

    def _pick_node(self, screen_x: int, screen_y: int) -> Node | None:
        """
        Color-ID offscreen picking: render every glyph into an FBO with its
        node ID encoded as RGB, then read the single pixel under the cursor.

        The Y-flip (Qt top-left vs OpenGL bottom-left) and devicePixelRatio
        (HiDPI) are both handled here.

        In stereo mode, the click falls in one half of the split widget;
        re-render the pick pass with that half's eye offset and aspect ratio
        (mirroring paintGL's stereo loop) so the pick ray matches what's
        actually on screen there.
        """
        self.makeCurrent()
        try:
            if self.stereo_mode:
                w = self.width()
                half_w = w // 2
                sep = self._cam_distance * (self.stereo_separation_pct / 100.0)
                if screen_x < half_w:
                    seg_w, local_x, lateral_offset = half_w, screen_x, +sep / 2.0
                else:
                    seg_w, local_x, lateral_offset = w - half_w, screen_x - half_w, -sep / 2.0
                result = self._render_pick_scene(seg_w=seg_w, lateral_offset=lateral_offset)
            else:
                local_x = screen_x
                result = self._render_pick_scene()
            if result is None:
                return None
            qt_fbo, fb_w, fb_h, dpr, w, h = result

            # Y-flip + HiDPI scaling
            fb_x = min(max(int(local_x * dpr), 0), fb_w - 1)
            fb_y = min(max(int((h - 1 - screen_y) * dpr), 0), fb_h - 1)
            pixel = glReadPixels(fb_x, fb_y, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)

            self._finish_pick_scene(qt_fbo, fb_w, fb_h)
        finally:
            self.doneCurrent()

        # Decode RGB → node ID
        arr = np.frombuffer(pixel, dtype=np.uint8)
        pr, pg, pb = int(arr[0]), int(arr[1]), int(arr[2])
        node_id = pr | (pg << 8) | (pb << 16)
        if node_id == 0:
            return None
        return self._scene.node_by_id(node_id)

    def _pick_nodes_in_rect(self, x1: int, y1: int, x2: int, y2: int) -> set[int]:
        """
        Color-ID pick over a rectangular screen region; returns IDs of every
        node whose silhouette overlaps the rectangle.  Coordinates are in Qt
        widget space (top-left origin, no HiDPI scaling).
        """
        self.makeCurrent()
        try:
            result = self._render_pick_scene()
            if result is None:
                return set()
            qt_fbo, fb_w, fb_h, dpr, w, h = result

            # Map the screen rect to FBO pixels (Y-flip + HiDPI)
            rx1 = min(x1, x2)
            rx2 = max(x1, x2)
            ry1 = min(y1, y2)
            ry2 = max(y1, y2)

            fb_x = max(0, int(rx1 * dpr))
            fb_y = max(0, int((h - ry2) * dpr))
            fw = max(1, min(int((rx2 - rx1) * dpr) + 1, fb_w - fb_x))
            fh = max(1, min(int((ry2 - ry1) * dpr) + 1, fb_h - fb_y))

            pixels = glReadPixels(fb_x, fb_y, fw, fh, GL_RGB, GL_UNSIGNED_BYTE)

            self._finish_pick_scene(qt_fbo, fb_w, fb_h)
        finally:
            self.doneCurrent()

        # Vectorised decode: r | (g<<8) | (b<<16), ignore black background (id==0)
        arr = np.frombuffer(pixels, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        ids_arr = arr[:, 0] | (arr[:, 1] << 8) | (arr[:, 2] << 16)
        return set(int(i) for i in ids_arr[ids_arr != 0])

    # --- keyboard hierarchy navigation ---

    def event(self, event):
        # Qt consumes Key_Tab before keyPressEvent for focus traversal.
        # Intercept it here so we can use Tab / Shift+Tab for scene navigation.
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Tab:
                self.navNextSibling.emit()
                event.accept()
                return True
            if event.key() == Qt.Key.Key_Backtab:   # Shift+Tab
                self.navPrevSibling.emit()
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Up:
            self.navParent.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_Down:
            self.navChild.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_N:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.createChildNode.emit()
            else:
                self.createNode.emit()
            event.accept()
        elif event.key() in (Qt.Key.Key_Backslash, Qt.Key.Key_Bar):
            # Key_Bar is what Windows sends for Shift+\ (the | character)
            if event.key() == Qt.Key.Key_Bar or event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._adjust_draw_limit(2.0)   # Shift+\ or | → double (restore)
            else:
                self._adjust_draw_limit(0.5)   # \ → halve
            event.accept()
        elif event.key() == Qt.Key.Key_T:
            self.show_tags = not self.show_tags
            self.tagToggled.emit(self.show_tags)
            self.update()
            event.accept()
        elif event.key() == Qt.Key.Key_B:
            self.bgToggleRequested.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_8:
            self.renderModeCycleRequested.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_K:
            self.quickSaveRequested.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_G:
            self.gridSelectRequested.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_O:
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.geoCycleRequested.emit(-1 if shift else 1)
            event.accept()
        elif event.key() == Qt.Key.Key_J:
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.topoCycleRequested.emit(-1 if shift else 1)
            event.accept()
        elif event.key() in (Qt.Key.Key_Equal, Qt.Key.Key_Minus):
            step = 1 if event.key() == Qt.Key.Key_Equal else -1
            if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                self.paletteCycleRequested.emit(step)
            else:
                self.colorIndexCycleRequested.emit(step)
            event.accept()
        elif event.key() == Qt.Key.Key_H:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.showAllRequested.emit()
            else:
                self.hideSelectedRequested.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_I:
            self.isolateSelectedRequested.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_Space:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.channelStopRequested.emit()
            else:
                self.channelPlayToggleRequested.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.escapePressed.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_C:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # ANTz-style: repeated hits step through the cameras. (Plain C
                # used to do this; it now toggles Camera Mode, and the Camera
                # toolbar still jumps straight to any camera.)
                self.cycle_camera(1)
            else:
                self.toggle_fly_mode()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _adjust_draw_limit(self, factor: float):
        """Halve or double the draw limit; emits drawLimitChanged with (visible, total)."""
        total = sum(
            1 for n in self._scene.nodes
            if n.type not in NON_VISUAL_TYPES and (self.show_hidden or not n.hide)
        )
        if total == 0:
            return
        current = total if self._draw_limit is None else self._draw_limit
        new_limit = max(1, min(total, round(current * factor)))
        if new_limit >= total:
            self._draw_limit = None
        else:
            self._draw_limit = new_limit
        visible = total if self._draw_limit is None else self._draw_limit
        self.drawLimitChanged.emit(visible, total)
        self.update()

    # --- mouse ---

    def mousePressEvent(self, event):
        # A press on a gizmo handle beats everything else a left-press can
        # start — including Shift+drag rubber-band, so a handle stays
        # grabbable whatever modifier happens to be down (matching GlyphViz
        # Web). Nothing else about the press is recorded: the drag is
        # single-axis and self-contained, and its release must not fall
        # through to the click-picker and clear the selection.
        if event.button() == Qt.MouseButton.LeftButton:
            axis = self._gizmo_pick(event.pos().x(), event.pos().y())
            if axis is not None:
                self._begin_gizmo_drag(axis, event.pos())
                if self._gizmo_drag is not None:
                    self._last_pos = self._press_pos = event.pos()
                    self._drag_button = Qt.MouseButton.LeftButton
                    self._drag_moved = True
                    return

        # Shift+LeftButton starts rubber-band region select (disabled in
        # stereo mode: a single screen-space rectangle can't be mapped back
        # to one node set when the two eyes show different projections of
        # the same scene). Single-node click/double-click picking still
        # works in stereo -- see _pick_node, which re-renders the matching
        # eye's pick pass for whichever half was clicked.
        if (not self.stereo_mode and event.button() == Qt.MouseButton.LeftButton
                and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._rubber_mode = True
            self._rubber_start = event.pos()
            self._rubber_end = event.pos()
            self.setCursor(Qt.CursorShape.CrossCursor)
            return

        self._last_pos = event.pos()
        self._press_pos = event.pos()
        self._drag_button = event.button()
        self._drag_moved = False

        # Left+Right held together (ANTz-style combined orbit+zoom, see
        # _orbit_zoom_camera): snap the orbit pivot onto the selected object
        # the moment the second button goes down, not continuously.
        buttons = event.buttons()
        combo = bool(buttons & Qt.MouseButton.LeftButton) and bool(buttons & Qt.MouseButton.RightButton)
        if combo and not self._combo_active:
            self._maybe_snap_orbit_target()
        self._combo_active = combo

        # ANTz-style rate flight: a lone LeftButton press in Camera Mode drops
        # the bearings origin where the click landed. Nothing moves yet —
        # flight engages once the cursor leaves the origin's dead zone (see
        # _apply_fly_drag) — but the repaint timer starts now, because a held
        # offset must keep flying even while the mouse sits still.
        if self.fly_mode:
            if buttons == Qt.MouseButton.LeftButton:
                pos = (float(event.pos().x()), float(event.pos().y()))
                self._fly_anchor = self._fly_cursor = pos
            else:
                self._fly_anchor = self._fly_cursor = None
            self._update_render_timer_state()

    def mouseReleaseEvent(self, event):
        # --- gizmo handle release --- (returns before the click-picker: a
        # handle press that never moved is a no-op, not a click on empty
        # space, and must not clear the selection out from under the handles)
        if (self._gizmo_drag is not None
                and event.button() == Qt.MouseButton.LeftButton):
            self._gizmo_drag = None
            self._drag_button = None
            self._drag_moved = False
            self._update_gizmo_hover(event.pos())
            self.update()
            return

        # --- rubber-band release ---
        if self._rubber_mode and event.button() == Qt.MouseButton.LeftButton:
            self.unsetCursor()
            self._rubber_mode = False
            if self._rubber_start is not None and self._rubber_end is not None:
                dx = abs(self._rubber_end.x() - self._rubber_start.x())
                dy = abs(self._rubber_end.y() - self._rubber_start.y())
                if dx > 2 or dy > 2:
                    ids = self._pick_nodes_in_rect(
                        min(self._rubber_start.x(), self._rubber_end.x()),
                        min(self._rubber_start.y(), self._rubber_end.y()),
                        max(self._rubber_start.x(), self._rubber_end.x()),
                        max(self._rubber_start.y(), self._rubber_end.y()),
                    )
                    # Ctrl+Shift+drag adds to the selection (mirrors
                    # Ctrl+click's additive single-node semantics);
                    # plain Shift+drag replaces it.
                    if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                        self.nodesSelectedAdditive.emit(ids)
                    else:
                        self.nodesSelected.emit(ids)
            self._rubber_start = None
            self._rubber_end = None
            self.update()
            return

        # --- normal click --- (single-node picking works in stereo mode too;
        # only rubber-band region select is disabled there, see mousePressEvent)
        if (not self._drag_moved
                and self._drag_button == Qt.MouseButton.LeftButton):
            node = self._pick_node(event.pos().x(), event.pos().y())
            label = f"Node {node.id}" if node else "miss"
            print(f"[pick] ({event.pos().x()},{event.pos().y()}) -> {label}")

            ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
            if node is not None:
                if ctrl:
                    self.nodeClickedAdditive.emit(node.id)
                else:
                    self.nodeClicked.emit(node.id)
                    if alt:
                        # Alt+click: also open the node's link (U-key
                        # equivalent for the mouse) — after selection, so
                        # the opened node is highlighted and inspected.
                        self.nodeLinkActivated.emit(node.id)
            elif not ctrl and not alt:
                # Click on empty space (no Ctrl/Alt) → clear the selection
                self.nodesSelected.emit(set())

        # Fall back to whichever button (if any) is still held rather than
        # unconditionally clearing the drag — releasing one button of a
        # Left+Right combo drag should resume plain single-button orbit,
        # not stop navigation until re-pressed.
        remaining = event.buttons()
        for btn in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            if remaining & btn:
                self._drag_button = btn
                break
        else:
            self._drag_button = None
            self._drag_moved = False
        self._combo_active = bool(remaining & Qt.MouseButton.LeftButton) and bool(remaining & Qt.MouseButton.RightButton)

        # Rate flight tracks the held-button state: ending a combo with Left
        # still down resumes flight from a fresh origin at the cursor's
        # current spot (the pre-combo origin is stale — it would lurch the
        # camera the moment Right lifted); anything else stops flight.
        if self.fly_mode:
            if remaining == Qt.MouseButton.LeftButton:
                pos = (float(event.pos().x()), float(event.pos().y()))
                self._fly_anchor = self._fly_cursor = pos
            else:
                self._fly_anchor = self._fly_cursor = None
            self._update_render_timer_state()

    def leaveEvent(self, event):
        """Drop any handle highlight when the cursor leaves the viewport, so
        a hover doesn't stay lit while the mouse is off in a panel."""
        if self._gizmo_hover is not None and self._gizmo_drag is None:
            self._gizmo_hover = None
            self.update()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            node = self._pick_node(event.pos().x(), event.pos().y())
            if node is not None:
                self.nodeClicked.emit(node.id)
                self.focus_on_node(node)

    def mouseMoveEvent(self, event):
        # Gizmo handle drag: single-axis, and it owns the whole gesture.
        if self._gizmo_drag is not None:
            self._apply_gizmo_drag(event.pos())
            self._last_pos = event.pos()
            return

        # Rubber-band mode: just track the end corner, no camera movement
        if self._rubber_mode:
            self._rubber_end = event.pos()
            self.update()
            return

        if self._drag_button is None:
            # No button down: the only thing motion means is hovering a
            # handle (mouse tracking is on for exactly this).
            self._update_gizmo_hover(event.pos())
            return
        dx = event.pos().x() - self._last_pos.x()
        dy = event.pos().y() - self._last_pos.y()

        if not self._drag_moved:
            total_dx = event.pos().x() - self._press_pos.x()
            total_dy = event.pos().y() - self._press_pos.y()
            if total_dx**2 + total_dy**2 >= _DRAG_THRESHOLD**2:
                self._drag_moved = True

        manipulating = self.gizmo_mode is not None and bool(self.selected_node_ids)
        enabled_axes = [a for a in ('x', 'y', 'z') if self.gizmo_axes.get(a)]

        buttons = event.buttons()
        left = bool(buttons & Qt.MouseButton.LeftButton)
        right = bool(buttons & Qt.MouseButton.RightButton)
        middle = bool(buttons & Qt.MouseButton.MiddleButton)

        if self.fly_mode and (left or right):
            # Camera Mode owns every drag button outright — that's the point
            # of a mode. Click-to-select still works (a click isn't a drag),
            # as does Shift+drag rubber-band, but gizmo manipulation is
            # suspended until Camera Mode is switched back off.
            if left and right:
                self._fly_strafe_camera(dx, dy)
            elif left:
                # Rate flight: only track the cursor here — _apply_fly_drag
                # turns the held offset from the press origin into motion,
                # once per repaint tick rather than per mouse-move event.
                pos = (float(event.pos().x()), float(event.pos().y()))
                if self._fly_anchor is None:
                    # Camera Mode was toggled mid-drag (no press seen in fly
                    # mode): adopt the cursor's current spot as the origin.
                    self._fly_anchor = pos
                    self._update_render_timer_state()
                self._fly_cursor = pos
            else:
                self._look_around_camera(dx, dy)

        elif left and right:
            # Both buttons together always means camera nav (Dr. Dave
            # Warner's requested ANTz gesture) — takes priority over any
            # in-progress gizmo manipulation.
            self._orbit_zoom_camera(dx, dy)

        elif left:
            if manipulating and enabled_axes:
                raw_deltas = {enabled_axes[0]: dx}
                if len(enabled_axes) >= 2:
                    raw_deltas[enabled_axes[1]] = -dy
                self._apply_axis_deltas(raw_deltas)
            else:
                self._orbit_camera(dx, dy)

        elif right:
            if manipulating and len(enabled_axes) == 3:
                self._apply_axis_deltas({enabled_axes[2]: -dy})
            else:
                self._orbit_camera(dx, dy)

        elif middle and not self.active_camera_locked():
            az = math.radians(self._cam_azimuth)
            el = math.radians(self._cam_elevation)
            right_x = -math.sin(az)
            right_y =  math.cos(az)
            up_x = -math.cos(az) * math.sin(el)
            up_y = -math.sin(az) * math.sin(el)
            up_z =  math.cos(el)
            speed = self._cam_distance * 0.0015
            self._cam_target[0] -= (dx * right_x - dy * up_x) * speed
            self._cam_target[1] -= (dx * right_y - dy * up_y) * speed
            self._cam_target[2] += dy * up_z * speed

        self._last_pos = event.pos()
        self.update()

    def _orbit_camera(self, dx: float, dy: float):
        if self.active_camera_locked():
            return   # fixed reference view: no orbit/pan, zoom only
        # Sign is inverted from a plain camera-orbit ("fly around the
        # object") so the drag instead reads as grabbing the object's
        # near surface: drag right and the left side rotates toward the
        # viewer; drag down and the top rotates toward the viewer. Jeff
        # found the un-inverted mapping backwards on both axes.
        self._cam_azimuth -= dx * 0.4
        self._cam_elevation = max(-89.0, min(89.0, self._cam_elevation + dy * 0.4))

    def _orbit_zoom_camera(self, dx: float, dy: float):
        """Both mouse buttons held together: horizontal drag orbits azimuth
        (around the selected object, see _maybe_snap_orbit_target), vertical
        drag zooms — Dr. Dave Warner's requested ANTz-style combined
        orbit+zoom gesture. Locked (axis) cameras still zoom, but ignore the
        orbit component to stay fixed reference views. Azimuth sign matches
        _orbit_camera's inverted (grab-the-object) convention."""
        if not self.active_camera_locked():
            self._cam_azimuth -= dx * 0.4
        factor = 1.0 + dy * 0.005
        self._cam_distance = max(1.0, self._cam_distance * factor)

    # --- Camera Mode navigation ---
    #
    # All three gestures keep the arm length (_cam_distance) fixed and move
    # the whole rig, so the orbit target rides along in front of the camera
    # rather than pinning it. That's what makes flight feel unanchored: there
    # is no object you're stuck circling. Switch Camera Mode back off and the
    # target is wherever you last left it, ready to orbit again.

    def _fly_speed(self) -> float:
        """World units per pixel of a strafe drag — scaled off the arm length
        so the same drag feels right at any zoom level."""
        return max(self._cam_distance, 1.0) * _FLY_SPEED_PER_PX

    def _translate_rig(self, vec: _Vec3, amount: float):
        """Move eye and target together along `vec` (eye position is derived
        from the target, so translating the target translates both)."""
        for i in range(3):
            self._cam_target[i] += vec[i] * amount

    def _reaim_about_eye(self, d_azimuth: float, d_elevation: float = 0.0):
        """Swing the *aim* by these angle deltas while the eye stays planted.

        The rig stores a target and derives the eye from it, so naively
        changing azimuth/elevation orbits the eye around the target — the
        exact anchored feeling Camera Mode exists to escape. Re-deriving the
        target from the preserved eye inverts that: the camera pivots where
        it stands, and whatever it was pointed at slides out of frame.
        """
        eye = self._eye_position_with_offset(0.0)
        self._cam_azimuth += d_azimuth
        if d_elevation:
            self._cam_elevation = max(-89.0, min(89.0,
                                      self._cam_elevation + d_elevation))
        az = math.radians(self._cam_azimuth)
        el = math.radians(self._cam_elevation)
        d = self._cam_distance
        self._cam_target = [
            eye[0] - d * math.cos(el) * math.cos(az),
            eye[1] - d * math.cos(el) * math.sin(az),
            eye[2] - d * math.sin(el),
        ]

    def _apply_fly_drag(self, dt_ms: float):
        """LeftButton held in Camera Mode: ANTz-style rate flight, integrated
        once per repaint tick (called from paintGL, kept ticking by the
        render timer — see mousePressEvent for where the drag starts).

        The press point is the bearings origin (_fly_anchor). Holding the
        cursor above it flies forward, below it flies back, and left/right
        of it turns the camera — each at a rate proportional to the held
        offset, so a slight offset gives a slight but *constant* motion for
        as long as the button is down, and bringing the cursor back inside
        the origin's dead zone stops it. Flight is locked to the horizontal
        plane it starts on: translation follows the camera's heading with
        the pitch component dropped, so altitude never changes no matter
        where the aim points."""
        if not self.fly_mode or self._fly_anchor is None or self._fly_cursor is None:
            return
        dt = max(dt_ms, 0.0) / 1000.0
        if not dt:
            return
        off_x = _past_deadzone(self._fly_cursor[0] - self._fly_anchor[0])
        off_y = _past_deadzone(self._fly_cursor[1] - self._fly_anchor[1])
        if off_y:
            # Cursor above the origin (off_y < 0) = fly forward. World-Z is
            # up, so the heading-only (horizontal-plane) forward is the full
            # forward vector with its elevation term dropped, renormalized —
            # which is just the azimuth direction.
            az = math.radians(self._cam_azimuth)
            heading = (-math.cos(az), -math.sin(az), 0.0)
            speed = max(self._cam_distance, 1.0) * _FLY_RATE_PER_PX_S
            self._translate_rig(heading, -off_y * speed * dt)
        if off_x:
            # Cursor right of the origin = turn right. Azimuth runs counter-
            # clockwise from +X and the camera looks *back* along it, so a
            # right turn decreases it — the same sign _orbit_camera already
            # uses for a right drag.
            self._reaim_about_eye(-off_x * _FLY_TURN_DEG_PER_PX_S * dt)

    def _look_around_camera(self, dx: float, dy: float):
        """RightButton drag in Camera Mode: pivot the view about the eye
        (ANTz's left-button look-around) instead of swinging the eye about the
        target. Same drag directions as the orbit camera — drag right and the
        view turns right, drag down and it tips down — so muscle memory
        carries over between the two modes."""
        self._reaim_about_eye(-dx * _LOOK_DEG_PER_PX, dy * _LOOK_DEG_PER_PX)

    def _fly_strafe_camera(self, dx: float, dy: float):
        """Left+Right together in Camera Mode: slide the camera sideways and
        vertically in its own frame (truck/pedestal), without turning. This is
        the gesture for nudging a composed shot into place — flying and
        looking both change the aim, this doesn't."""
        _forward, right, up = self._camera_basis()
        speed = self._fly_speed()
        if dx:
            self._translate_rig(right, dx * speed)
        if dy:
            self._translate_rig(up, -dy * speed)   # drag down = move down

    def _maybe_snap_orbit_target(self):
        """Called once, at the moment a Left+Right combo drag begins: re-center
        the orbit pivot on the selected node so the combined orbit+zoom
        gesture orbits *the selected object*, not whatever the camera
        happened to be pointed at. Skipped for locked axis cameras, which
        must always stay aimed at the world origin, and in Camera Mode, where
        the eye is derived from the target — moving the pivot there would
        teleport the camera onto the selected node mid-flight."""
        if self.active_camera_locked() or self.fly_mode:
            return
        node = self.follow_node()
        if node is None:
            return
        pos = self.world_position(node.id)
        if pos is not None:
            self._cam_target = list(pos)

    def _apply_axis_deltas(self, raw_deltas: dict, field_deltas: dict | None = None):
        """Apply one drag-step of Move/Rotate/Size to every selected node.

        Two callers, two currencies:

        * `raw_deltas` (the axis-checkbox free-form drag) maps axis letter to
          a raw screen-pixel delta, converted here at the fixed per-pixel
          rates. Move additionally divides out the parent's cumulative scale
          per node (_move_axis_divisors), which is what keeps the on-screen
          drag speed constant under a scaled parent.

        * `field_deltas` (a gizmo handle drag) maps axis letter to a change
          already expressed in the FIELD's own units — translate units for
          Move, degrees for Rotate, a multiplier for Size — because the
          handle worked out exactly how far the cursor pushed it (see
          _apply_gizmo_drag). No per-node conversion: every selected node
          takes the identical field change the grabbed node did, matching
          GlyphViz Web's multi-select rule. For a selection that sits under
          one parent — the usual case — the two rules agree anyway.

        Exactly one of the two is passed.
        """
        deltas = field_deltas if field_deltas is not None else raw_deltas
        if not deltas or not self.selected_node_ids:
            return
        direct = field_deltas is not None
        if self.gizmo_mode == 'size' and self.uniform_scale:
            # Locked: one factor for all three axes, whichever bar (or which
            # drag direction) produced it. The first entry wins — for a
            # handle drag there is only one, and for the free-form drag it is
            # the first checked axis, i.e. the horizontal component.
            amount = next(iter(deltas.values()))
            deltas = {a: amount for a in ('x', 'y', 'z')}
        changed = set()
        for nid in self.selected_node_ids:
            node = self._scene.node_by_id(nid)
            if node is None:
                continue
            move_div = (self._move_axis_divisors(node)
                        if self.gizmo_mode == 'move' and not direct else None)
            for axis, raw in deltas.items():
                if self.gizmo_mode == 'move':
                    attr = f'translate_{axis}'
                    step = raw if direct else (
                        raw * self._cam_distance * _MOVE_WORLD_PER_PX
                        / move_div[axis])
                    setattr(node, attr, getattr(node, attr) + step)
                elif self.gizmo_mode == 'rotate':
                    attr = f'rotate_{axis}'
                    step = raw if direct else raw * _ROTATE_DEG_PER_PX
                    setattr(node, attr, getattr(node, attr) + step)
                elif self.gizmo_mode == 'size':
                    attr = f'scale_{axis}'
                    factor = raw if direct else 1.0 + raw * _SIZE_FACTOR_PER_PX
                    setattr(node, attr, max(0.001, getattr(node, attr) * factor))
            changed.add(nid)
        if changed:
            self._scene.invalidate()
            self.update()
            self.nodesManipulated.emit(changed)

    # --- transform gizmo (red/green/blue handles) ---------------------------
    #
    # The handles are drawn on ONE node (the first selected visual one) and
    # constrain a drag to a single axis, but the resulting field change is
    # applied to the whole selection like any other manipulation.
    #
    # Each mode's handles point along the frame that mode's fields genuinely
    # act in — which is not the same frame for all three, and for two of them
    # is not the node's local axes at all. glyphviz_core/gizmo.py works those
    # out (and explains why); everything here is GL drawing, hit-testing
    # against the live camera, and drag bookkeeping.

    def gizmo_node(self) -> Node | None:
        """The node the handles attach to: the first selected node in scene
        order that has a transform worth showing them on. Same first-in-scene-
        order rule as follow_node(), minus Links — a Link's own transform is
        inert (the edge follows its two endpoints), so handles on one would
        promise an edit that does nothing."""
        if not self.selected_node_ids:
            return None
        for n in self._scene.nodes:
            if (n.id in self.selected_node_ids
                    and n.type not in NON_VISUAL_TYPES
                    and n.type != NODE_TYPE_LINK):
                return n
        return None

    def _gizmo_frame(self) -> dict | None:
        """Everything needed to draw or hit-test the handles right now, or
        None when they shouldn't be on screen at all.

        Suppressed in Camera Mode (which owns every drag button outright) and
        in stereo mode, where the handles would be drawn once per eye and a
        cursor measured against the whole widget would grab at neither —
        the same restriction rubber-band select already carries. The armed
        mode and the axis-checkbox drags keep working in both.
        """
        if (not self.show_gizmo_handles or self.gizmo_mode not in gz.MODES
                or self.fly_mode or self.stereo_mode):
            return None
        node = self.gizmo_node()
        if node is None:
            return None
        origin = self._scene.world_pos(node.id)
        bases = self._scene.basis_matrices(node.id)
        if origin is None or bases is None:
            return None
        world_basis, parent_basis, child_local = bases

        if self.gizmo_mode == gz.MODE_ROTATE:
            axes = gz.rotation_axes(node, parent_basis, child_local)
            field_per_unit = np.ones(3)
        elif self.gizmo_mode == gz.MODE_SIZE:
            axes = gz.unit_columns(world_basis)
            field_per_unit = np.ones(3)
        else:
            parent = self._scene.node_by_id(node.parent_id)
            if parent is node:
                parent = None
            pwb = None
            if parent is not None:
                pbases = self._scene.basis_matrices(parent.id)
                pwb = pbases[0] if pbases is not None else None
            grad = gz.translate_gradient(parent, node, self._base_scale, pwb)
            axes = gz.unit_columns(grad)
            # World units per unit of the field: the drag converts cursor
            # travel to world distance, then to a field change through this.
            norms = np.linalg.norm(grad, axis=0)
            field_per_unit = np.where(norms > 1e-9, norms, 1.0)

        length = gz.handle_world_length(
            self._eye_position_with_offset(0.0), origin,
            gz.HANDLE_PX, 45.0, float(self.height()))
        return {
            'node': node,
            'origin': np.asarray(origin, dtype=np.float64),
            'axes': axes,
            'length': length,
            'world_per_field': field_per_unit,
        }

    def _gizmo_screen_handles(self, frame: dict) -> dict | None:
        """Project the frame's handles into widget pixels with the camera
        matrices the last paint used. None before the first paint (or in
        stereo, where they aren't captured)."""
        if self._mv_matrix is None or self._proj_matrix is None:
            return None
        mvp = self._proj_matrix @ self._mv_matrix
        pts = gz.handle_points(self.gizmo_mode, frame['origin'],
                               frame['axes'], frame['length'])
        return {a: gz.project(mvp, p, float(self.width()), float(self.height()))[0]
                for a, p in pts.items()}

    def _gizmo_pick(self, x: float, y: float) -> str | None:
        """Axis letter of the handle under the cursor, or None."""
        frame = self._gizmo_frame()
        if frame is None:
            return None
        screen = self._gizmo_screen_handles(frame)
        if screen is None:
            return None
        return gz.pick(screen, (x, y))

    def _update_gizmo_hover(self, pos):
        """Highlight the handle under an un-pressed cursor. Repaints only on
        a change, so plain mouse motion over a scene costs one hit test."""
        axis = None
        if self.show_gizmo_handles and self.gizmo_mode is not None:
            axis = self._gizmo_pick(pos.x(), pos.y())
        if axis != self._gizmo_hover:
            self._gizmo_hover = axis
            self.update()

    def _begin_gizmo_drag(self, axis: str, pos):
        """Grab a handle. The frame is snapshotted here and held for the whole
        drag: the node moves/rotates/scales under it, and re-deriving the
        handle from the moved node each step would feed that motion back into
        the next step's direction."""
        frame = self._gizmo_frame()
        if frame is None:
            return
        i = gz.AXIS_INDEX[axis]
        direction = frame['axes'][:, i]
        eye = np.asarray(self._eye_position_with_offset(0.0), dtype=np.float64)
        self._gizmo_drag = {
            'axis': axis,
            'origin': frame['origin'],
            'direction': direction,
            'length': frame['length'],
            'world_per_field': float(frame['world_per_field'][i]),
            # A ring seen from its back turns clockwise for a right-handed
            # rotation; decided once, from where the camera stood at the grab.
            'toward_viewer': bool(np.dot(direction, eye - frame['origin']) > 0.0),
            'last': (float(pos.x()), float(pos.y())),
        }
        self._gizmo_hover = axis
        self.update()

    def _apply_gizmo_drag(self, pos):
        """One step of a handle drag: cursor motion in, one field change out."""
        drag = self._gizmo_drag
        if drag is None or self._mv_matrix is None or self._proj_matrix is None:
            return
        cur = (float(pos.x()), float(pos.y()))
        last = drag['last']
        drag['last'] = cur
        mvp = self._proj_matrix @ self._mv_matrix
        w, h = float(self.width()), float(self.height())
        axis = drag['axis']

        if self.gizmo_mode == gz.MODE_ROTATE:
            centre, _ = gz.project(mvp, drag['origin'][None, :], w, h)
            if not np.isfinite(centre[0]).all():
                return
            delta = gz.sweep_degrees(centre[0], last, cur, drag['toward_viewer'])
            if delta:
                self._apply_axis_deltas({}, field_deltas={axis: delta})
            return

        shaft = np.array([
            drag['origin'] + drag['direction'] * drag['length'] * gz.SHAFT_START,
            drag['origin'] + drag['direction'] * drag['length'],
        ])
        screen, _ = gz.project(mvp, shaft, w, h)
        pixels = gz.axis_drag_pixels(screen, cur[0] - last[0], cur[1] - last[1])
        if not pixels:
            return
        if self.gizmo_mode == gz.MODE_SIZE:
            self._apply_axis_deltas(
                {}, field_deltas={axis: 1.0 + pixels * _SIZE_FACTOR_PER_PX})
            return
        world_per_px = gz.axis_world_per_pixel(screen, drag['length'])
        if not world_per_px:
            return   # handle is edge-on: no unambiguous drag direction
        self._apply_axis_deltas(
            {}, field_deltas={axis: pixels * world_per_px / drag['world_per_field']})

    def _draw_gizmo(self):
        """Draw the armed mode's handles: arrows (Move), rings (Rotate), or
        capped bars (Size), in X-red / Y-green / Z-blue.

        Chrome, so drawn unlit, unfogged, and with the depth test off — a
        handle you can grab has to be a handle you can see, even when the
        glyph it sits on is bigger than it is.

        In Size mode with the scale lock on, a pale triangle joins the three
        bar ends: the handles still read X/Y/Z, but the tie says out loud
        that dragging any one of them moves all three."""
        frame = self._gizmo_frame()
        if frame is None:
            return
        active = (self._gizmo_drag['axis'] if self._gizmo_drag is not None
                  else self._gizmo_hover)
        points = gz.handle_points(self.gizmo_mode, frame['origin'],
                                  frame['axes'], frame['length'])
        unit = gz.unit_columns(frame['axes'])

        was_fogged = glIsEnabled(GL_FOG)
        glDisable(GL_LIGHTING)
        glDisable(GL_FOG)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_CULL_FACE)
        for name in gz.AXES:
            i = gz.AXIS_INDEX[name]
            r, g, b = gz.AXIS_COLORS[name]
            if name == active:
                r, g, b = min(r + 0.45, 1.0), min(g + 0.45, 1.0), min(b + 0.45, 1.0)
            glColor4f(r, g, b, 1.0)
            glLineWidth(3.5 if name == active else 2.0)
            path = points[name]
            if self.gizmo_mode == gz.MODE_ROTATE:
                glBegin(GL_LINE_STRIP)
                for p in path:
                    glVertex3f(*p)
                glEnd()
            else:
                glBegin(GL_LINES)
                glVertex3f(*path[0])
                glVertex3f(*path[1])
                glEnd()
                cap = frame['length'] * gz.ARROW_HEAD * (0.55 if self.gizmo_mode
                                                         == gz.MODE_SIZE else 1.0)
                # Cross-section basis from the handle's OWN axis, not the
                # other two: they need not be perpendicular to it (see
                # gizmo.perpendicular_basis), and a cone or box built on
                # skewed vectors comes out sheared.
                u, v = gz.perpendicular_basis(unit[:, i])
                self._draw_gizmo_cap(path[1], unit[:, i], u, v,
                                     cap, self.gizmo_mode == gz.MODE_SIZE)

        if self.gizmo_mode == gz.MODE_SIZE and self.uniform_scale:
            glColor4f(0.85, 0.85, 0.6, 1.0)
            glLineWidth(1.5)
            glBegin(GL_LINE_LOOP)
            for name in gz.AXES:
                glVertex3f(*points[name][1])
            glEnd()
        glLineWidth(1.0)
        glEnable(GL_CULL_FACE)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        if was_fogged:
            glEnable(GL_FOG)   # the scene's own fog setting, left as found

    @staticmethod
    def _draw_gizmo_cap(tip, axis, u, v, size: float, boxy: bool):
        """The blob at the end of a Move/Size handle: a cone tip for Move
        (which way the arrow points is the whole message), a cube for Size
        (a corner to pull). Unlit flat color, so both read as silhouettes."""
        if boxy:
            h = size * 0.5
            centre = np.asarray(tip, dtype=np.float64) - np.asarray(axis) * h
            corners = [centre + axis * (h * sx) + u * (h * sy) + v * (h * sz)
                       for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
            # (index triples into `corners`, ordered so each quad is one face)
            for face in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
                         (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
                glBegin(GL_QUADS)
                for k in face:
                    glVertex3f(*corners[k])
                glEnd()
            return
        base = np.asarray(tip, dtype=np.float64) - np.asarray(axis) * size
        radius = size * 0.32
        segs = 12
        rim = [base + u * (radius * math.cos(t)) + v * (radius * math.sin(t))
               for t in (2.0 * math.pi * k / segs for k in range(segs + 1))]
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(*tip)
        for p in rim:
            glVertex3f(*p)
        glEnd()
        glBegin(GL_TRIANGLE_FAN)    # cap the base so the cone isn't hollow
        glVertex3f(*base)
        for p in reversed(rim):
            glVertex3f(*p)
        glEnd()

    def _move_axis_divisors(self, node: Node) -> dict[str, float]:
        """Per-axis divisors converting a Move-drag's world-unit step into
        the node's translate units.

        A child's translate maps to world through its parent's cumulative
        scale, so under a scaled parent a raw translate step of X moves the
        node scale*X world units — the source of the old 'child of a big
        grid flies off screen at the slightest drag' hypersensitivity.
        Dividing by the parent's cumulative per-axis scale makes the on-
        screen drag speed constant (matching camera pan) no matter how the
        parent is scaled. Applied only where translate really is a linear
        length: World Grid parents and Cartesian-mapping topologies —
        angular topologies' translate fields are degrees, left untouched.
        """
        parent = self._scene.node_by_id(node.parent_id)
        if (parent is None or parent is node
                or (parent.type != NODE_TYPE_GRID
                    and parent.topo not in _CARTESIAN_PARENT_TOPOS)):
            return {'x': 1.0, 'y': 1.0, 'z': 1.0}
        s = self._scene.world_scale(parent.id)
        if s is None:
            return {'x': 1.0, 'y': 1.0, 'z': 1.0}
        return {axis: max(abs(v), 1e-9) for axis, v in zip('xyz', s)}

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if self.fly_mode:
            # In Camera Mode the wheel flies rather than zooms: shortening the
            # arm would creep the eye toward a target that's supposed to ride
            # along in front of it, and would quietly slow every later drag
            # (flight speed scales off arm length).
            forward, _right, _up = self._camera_basis()
            step = self._cam_distance * _FLY_WHEEL_STEP
            self._translate_rig(forward, step if delta > 0 else -step)
        else:
            factor = 0.88 if delta > 0 else 1.14
            self._cam_distance = max(1.0, self._cam_distance * factor)
        self.update()
