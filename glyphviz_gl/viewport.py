import math
import time

import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *
from PySide6.QtCore import Qt, QEvent, QPoint, QRect, Signal, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from pathlib import Path

from glyphviz_core.node import (
    Node, NON_VISUAL_TYPES, NODE_TYPE_LINK,
    RENDER_MODE_NORMAL, RENDER_MODE_ADDITIVE, RENDER_MODE_SUBTRACTIVE,
    RENDER_MODE_DARK, RENDER_MODE_OFF, RENDER_MODE_SCREEN, RENDER_MODE_PREMULTIPLIED,
    WORLD_DEFAULT_BG_RGB,
)
from glyphviz_core.scene import Scene, node_world_matrix
from glyphviz_core.topology import TOPO_PLOT, TOPO_SURFACE
from glyphviz_core.mesh_loader import load_mesh_file as _load_mesh_data

from .geometry import GeoRenderer, WIRE_TO_SOLID
from .texture_manager import TextureManager
from .video_manager import VideoManager

_DRAG_THRESHOLD = 4  # pixels — less than this counts as a click, not a drag

# ANTz rate convention (translate_rate_x/y/z, rotate_rate_x/y/z, scale_rate_x/y/z):
# a delta applied every cycle, nominally 60 cycles/second — see
# Node-Field-Descriptions.md's Translate/Rotate/Scale sections.
_RATE_CYCLE_MS = 1000.0 / 60.0


def _gl_col_major(M: np.ndarray) -> np.ndarray:
    """Convert a 4x4 NumPy row-major matrix to a float32 column-major flat array
    for glMultMatrixf / glLoadMatrixf (OpenGL column-major convention)."""
    return M.astype(np.float32).T.flatten()


_DEFAULT_BG = tuple(c / 255.0 for c in WORLD_DEFAULT_BG_RGB)  # used when the scene has no World node


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


class Viewport(QOpenGLWidget):
    # Plain left-click on a node: replaces the selection
    nodeClicked = Signal(int)
    # Ctrl+left-click on a node: toggle that node in/out of selection
    nodeClickedAdditive = Signal(int)
    # Rubber-band release OR click-on-empty-space: replace selection with this set
    # (empty set = clear all).  Also used by Select-By to push a set of IDs.
    nodesSelected = Signal(object)   # carries set[int]

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = Scene([])
        self._base_scale = 1.0
        self.show_axes = True
        self.show_grid = True
        self.show_hidden = False
        self.selected_node_ids: set[int] = set()

        # Gizmo manipulation state (Move/Rotate/Size).  None = camera-only.
        self.gizmo_mode: str | None = None
        self.gizmo_axes = {'x': True, 'y': True, 'z': True}

        self._cam_distance = 500.0
        self._cam_azimuth = 45.0
        self._cam_elevation = 25.0
        self._cam_target = [0.0, 0.0, 0.0]

        # Cross-eye free-view stereo: render the scene twice (per-eye lateral
        # camera offset, same look-at target -> toe-in convergence at the
        # target with zero parallax there), side by side in this same widget.
        # Separation auto-scales with cam_distance (a fixed % of it) so it
        # stays sensible across zoom levels; stereo_separation_pct is also
        # user-adjustable for scenes where the default depth feels too flat
        # or too extreme.
        self.stereo_mode: bool = False
        self.stereo_separation_pct: float = 3.0

        self._last_pos = QPoint()
        self._press_pos = QPoint()
        self._drag_button = None
        self._drag_moved = False

        # Draw-limit culling: None = show all; int = show first N visual nodes
        self._draw_limit: int | None = None

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

        self.show_tags = True
        self.show_tags_selected_only = False

        # Cached camera matrices for tag world→screen projection (updated each frame).
        self._mv_matrix: np.ndarray | None = None
        self._proj_matrix: np.ndarray | None = None

        self._geo = GeoRenderer()
        self._next_mesh_id = 1
        self._mesh_names: dict[int, str] = {}   # mesh_id -> source filename, for the UI
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
    def nodes(self) -> list[Node]:
        """The current node list (read-only; use set_nodes to replace)."""
        return self._scene.nodes

    def scene_invalidate(self):
        """Mark scene transforms stale and request a repaint.
        Call this whenever node data (position, rotation, scale, topo) changes."""
        self._scene.invalidate()
        self.update()

    def register_node(self, node: Node):
        """Sync a node appended directly to self._scene.nodes into the scene's lookup cache."""
        self._scene.register_node(node)
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
        self._scene = Scene(nodes, self._base_scale)
        self._scene._ensure()   # pre-compute so camera init can read positions
        self._update_render_timer_state()
        visible = [n for n in nodes if n.type not in NON_VISUAL_TYPES]
        if visible:
            positions = [
                self._scene.world_pos(n.id) or (n.translate_x, n.translate_y, n.translate_z)
                for n in visible
            ]
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
        self.update()

    def world_position(self, node_id: int) -> tuple[float, float, float] | None:
        """World-space position of a node as computed for the last rendered frame."""
        return self._scene.world_pos(node_id)

    def _radius_of(self, node: Node) -> tuple[float, float, float]:
        """Per-axis rendered radii (rx, ry, rz) for camera focus and UI hints."""
        s = self._scene.world_scale(node.id) or (node.scale_x, node.scale_y, node.scale_z)
        bs = self._base_scale
        return (max(s[0]*bs, 0.2), max(s[1]*bs, 0.2), max(s[2]*bs, 0.2))

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

    def focus_on(self, world_pos: tuple[float, float, float], min_distance: float = 1.0):
        """Point camera at world_pos and pull it in to ~1/10 current distance."""
        az = math.radians(self._cam_azimuth)
        el = math.radians(self._cam_elevation)
        tx, ty, tz = self._cam_target
        ex = tx + self._cam_distance * math.cos(el) * math.cos(az)
        ey = ty + self._cam_distance * math.cos(el) * math.sin(az)
        ez = tz + self._cam_distance * math.sin(el)
        px, py, pz = world_pos
        dist_to_obj = math.sqrt((ex-px)**2 + (ey-py)**2 + (ez-pz)**2)
        self._cam_target = [px, py, pz]
        self._cam_distance = max(dist_to_obj / 10.0, min_distance)
        self.update()

    def focus_on_node(self, node: Node):
        """Center and zoom toward node, leaving at least 1.5× its radius of headroom."""
        pos = self.world_position(node.id) or (node.translate_x, node.translate_y, node.translate_z)
        rx, ry, rz = self._radius_of(node)
        self.focus_on(pos, min_distance=max(rx, ry, rz) * 1.5)

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
        self._update_render_timer_state()
        self.update()
        return img_count + vid_count

    def load_mesh_file(self, path: str) -> int:
        """Import an OBJ/STL/etc. file (glyphviz_core.mesh_loader) and compile
        it into a new GEO_MESH display list. Must be called while the OpenGL
        context is current (safe from the main thread after the widget has
        been shown). Returns the new mesh_id (1, 2, 3, ... in import order)."""
        data = _load_mesh_data(path)
        self.makeCurrent()
        self._geo.setup()
        mesh_id = self._next_mesh_id
        self._next_mesh_id += 1
        self._geo.register_mesh(mesh_id, data)
        self._mesh_names[mesh_id] = data.name
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
        self._update_render_timer_state()
        self.update()

    def _has_active_rates(self) -> bool:
        """True if any non-frozen node has a nonzero translate/rotate/scale rate
        (ANTz's freeze flag, preserved in Node.extras, suspends a node's own
        rates but doesn't need to be checked against other nodes still moving)."""
        for n in self._scene.nodes:
            if n.extras.get('freeze', 0):
                continue
            if (n.translate_rate_x or n.translate_rate_y or n.translate_rate_z
                    or n.rotate_rate_x or n.rotate_rate_y or n.rotate_rate_z
                    or n.scale_rate_x or n.scale_rate_y or n.scale_rate_z):
                return True
        return False

    def _update_render_timer_state(self):
        """Start/stop the ~30fps continuous-repaint timer based on whether
        anything needs per-frame ticking: video/GIF playback or rate-driven
        node animation. Call after any scene or texture change that could
        flip either condition."""
        needs = self._needs_video_tick or self._has_active_rates()
        if needs and not self._render_timer.isActive():
            self._render_timer.start(33)   # ~30 fps continuous repaint
            self._last_tex_tick = time.perf_counter()
        elif not needs and self._render_timer.isActive():
            self._render_timer.stop()

    def refresh_animation_state(self):
        """Public hook for callers that mutate node rate fields directly
        (e.g. the Properties inspector) to re-evaluate continuous repaint."""
        self._update_render_timer_state()

    def _apply_rate_animation(self, dt_ms: float) -> bool:
        """Advance translate_x/y/z, rotate_x/y/z, scale_x/y/z by their
        *_rate_* velocities (see _RATE_CYCLE_MS). Returns True if any node
        moved, so the caller knows to invalidate the scene's transform cache."""
        cycles = dt_ms / _RATE_CYCLE_MS
        if cycles <= 0:
            return False
        moved = False
        for n in self._scene.nodes:
            if n.extras.get('freeze', 0):
                continue
            if n.translate_rate_x or n.translate_rate_y or n.translate_rate_z:
                n.translate_x += n.translate_rate_x * cycles
                n.translate_y += n.translate_rate_y * cycles
                n.translate_z += n.translate_rate_z * cycles
                moved = True
            if n.rotate_rate_x or n.rotate_rate_y or n.rotate_rate_z:
                n.rotate_x += n.rotate_rate_x * cycles
                n.rotate_y += n.rotate_rate_y * cycles
                n.rotate_z += n.rotate_rate_z * cycles
                moved = True
            if n.scale_rate_x or n.scale_rate_y or n.scale_rate_z:
                n.scale_x += n.scale_rate_x * cycles
                n.scale_y += n.scale_rate_y * cycles
                n.scale_z += n.scale_rate_z * cycles
                moved = True
        return moved

    def list_audio_tracks(self) -> list[tuple[int, str]]:
        """Return (texture_id, filename) for each loaded video's audio track."""
        return self._video_mgr.list_tracks()

    def set_audio_solo(self, texture_id: int | None):
        """Mute every video's audio except *texture_id* (None = play all)."""
        self._video_mgr.set_solo(texture_id)

    # --- GL lifecycle ---

    def initializeGL(self):
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
        if self._apply_rate_animation(dt_ms):
            self._scene.invalidate()
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
                self._draw_scene_content()
                if self.show_tags and mv is not None:
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
            gluLookAt(eye_x, eye_y, eye_z, tx, ty, tz, 0.0, 0.0, 1.0)

            # Capture camera matrices for world→screen tag projection (before node transforms).
            self._mv_matrix, self._proj_matrix = self._capture_camera_matrices()

            self._draw_scene_content()
            self._video_mgr.finalize_frame()   # pause any video no node drew this frame

            if self._rubber_mode and self._rubber_start and self._rubber_end:
                self._draw_rubber_band()

            # QPainter tag overlay (must come after all glBegin/glEnd blocks).
            if self.show_tags and self._mv_matrix is not None:
                self._draw_tags_qpainter()

        # FPS: count this frame; emit once per second
        self._fps_frames += 1
        now = time.perf_counter()
        elapsed = now - self._fps_t0
        if elapsed >= 1.0:
            self.fpsUpdated.emit(self._fps_frames / elapsed)
            self._fps_frames = 0
            self._fps_t0 = now

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
        gluLookAt(eye_x, eye_y, eye_z, tx, ty, tz, 0.0, 0.0, 1.0)

    def _capture_camera_matrices(self) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Snapshot the current GL modelview/projection matrices (row-major)
        for world->screen tag projection, right after gluLookAt/gluPerspective."""
        try:
            mv = np.array(glGetDoublev(GL_MODELVIEW_MATRIX), dtype=np.float64)
            pr = np.array(glGetDoublev(GL_PROJECTION_MATRIX), dtype=np.float64)
            return mv.reshape(4, 4).T, pr.reshape(4, 4).T   # column-major -> row-major
        except Exception:
            return None, None

    def _draw_scene_content(self):
        """Draw grid/axes/nodes/topology overlays against whatever camera
        matrices are currently loaded. Shared by the normal single-eye pass
        and each stereo eye pass in paintGL."""
        if self.show_grid:
            self._draw_grid()
        if self.show_axes:
            self._draw_axes()

        visible_count = 0
        for node in self._scene.nodes:
            if node.type in NON_VISUAL_TYPES:
                continue
            if node.type == NODE_TYPE_LINK:
                continue   # rendered as lines in _draw_topology_overlays
            if not self.show_hidden and node.hide:
                continue
            if self._draw_limit is not None and visible_count >= self._draw_limit:
                break
            self._draw_node(node, selected=(node.id in self.selected_node_ids))
            visible_count += 1

        self._draw_topology_overlays()

    def _draw_topology_overlays(self):
        """Draw type=7 link lines, TOPO_PLOT polylines, and TOPO_SURFACE quad meshes."""
        # Build parent→children map and collect link nodes in a single pass.
        children_of: dict[int, list[Node]] = {}
        link_nodes: list[Node] = []
        for node in self._scene.nodes:
            if node.type == NODE_TYPE_LINK:
                link_nodes.append(node)
            elif node.parent_id and node.parent_id != node.id:
                children_of.setdefault(node.parent_id, []).append(node)

        any_plot    = any(n.topo == TOPO_PLOT    for n in self._scene.nodes)
        any_surface = any(n.topo == TOPO_SURFACE for n in self._scene.nodes)
        if not link_nodes and not any_plot and not any_surface:
            return

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
        if any_plot:
            for node in self._scene.nodes:
                if node.topo != TOPO_PLOT:
                    continue
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
        if any_surface:
            glEnable(GL_LIGHTING)
            for node in self._scene.nodes:
                if node.topo != TOPO_SURFACE:
                    continue
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

    def _project_tagged_nodes(self, mv: np.ndarray, pr: np.ndarray,
                               vx: int, vy: int, vw: int, vh: int) -> list[tuple[str, int, int]]:
        """World->screen project every tagged, visible node's position using
        the given camera matrices into the (vx, vy, vw, vh) viewport sub-rect
        (Qt widget coordinates). Used for both the full-widget single-eye
        view and each half-width stereo eye view."""
        tagged: list[tuple[str, int, int]] = []
        visible_count = 0
        for node in self._scene.nodes:
            if node.type in NON_VISUAL_TYPES:
                continue
            if node.type == NODE_TYPE_LINK:
                continue
            if not self.show_hidden and node.hide:
                continue
            if self._draw_limit is not None and visible_count >= self._draw_limit:
                break
            visible_count += 1
            if not node.text:
                continue
            if self.show_tags_selected_only and node.id not in self.selected_node_ids:
                continue
            wp = self._scene.world_pos(node.id) or (node.translate_x, node.translate_y, node.translate_z)
            try:
                v = np.array([wp[0], wp[1], wp[2], 1.0])
                clip = pr @ mv @ v
                if clip[3] <= 0:
                    continue
                ndc = clip[:3] / clip[3]
                if not (-1.0 <= ndc[0] <= 1.0 and -1.0 <= ndc[1] <= 1.0 and -1.0 <= ndc[2] <= 1.0):
                    continue
                sx = vx + int((ndc[0] + 1.0) / 2.0 * vw)
                sy = vy + int((1.0 - (ndc[1] + 1.0) / 2.0) * vh)   # Y-flip for Qt
                tagged.append((node.text, sx, sy))
            except Exception:
                continue
        return tagged

    def _paint_tags(self, painter: QPainter, tagged: list[tuple[str, int, int]]):
        for text, sx, sy in tagged:
            painter.setPen(QColor(0, 0, 0, 200))
            painter.drawText(sx + 6, sy + 1, text)
            painter.setPen(QColor(255, 255, 200, 230))
            painter.drawText(sx + 5, sy, text)

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

    def _draw_node(self, node: Node, selected: bool = False):
        # node_world_matrix is the single source of truth — same matrix the
        # pick pass uses, so rendering and picking are identical by construction.
        M = node_world_matrix(node, self._scene)

        glPushMatrix()
        glMultMatrixf(_gl_col_major(M))

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

        if selected:
            glDisable(GL_LIGHTING)
            glLineWidth(1.5)
            glColor4f(1.0, 0.95, 0.1, 1.0)
            # Bounding box at ±1.05 in unit local space (M's scale makes it
            # track the node's actual rendered size).
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
        glDisable(GL_LIGHTING)
        glColor3f(0.22, 0.22, 0.28)
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
            gluLookAt(eye_x, eye_y, eye_z, tx, ty, tz, 0.0, 0.0, 1.0)

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
            M = node_world_matrix(node, self._scene)
            glPushMatrix()
            glMultMatrixf(_gl_col_major(M))
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
                M = node_world_matrix(node, self._scene)
                glPushMatrix()
                glMultMatrixf(_gl_col_major(M))
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

    def mouseReleaseEvent(self, event):
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
            if node is not None:
                if ctrl:
                    self.nodeClickedAdditive.emit(node.id)
                else:
                    self.nodeClicked.emit(node.id)
            elif not ctrl:
                # Click on empty space (no Ctrl) → clear the selection
                self.nodesSelected.emit(set())

        self._drag_button = None
        self._drag_moved = False

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            node = self._pick_node(event.pos().x(), event.pos().y())
            if node is not None:
                self.nodeClicked.emit(node.id)
                self.focus_on_node(node)

    def mouseMoveEvent(self, event):
        # Rubber-band mode: just track the end corner, no camera movement
        if self._rubber_mode:
            self._rubber_end = event.pos()
            self.update()
            return

        if self._drag_button is None:
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

        if self._drag_button == Qt.MouseButton.LeftButton:
            if manipulating and enabled_axes:
                raw_deltas = {enabled_axes[0]: dx}
                if len(enabled_axes) >= 2:
                    raw_deltas[enabled_axes[1]] = -dy
                self._apply_axis_deltas(raw_deltas)
            else:
                self._orbit_camera(dx, dy)

        elif self._drag_button == Qt.MouseButton.RightButton:
            if manipulating and len(enabled_axes) == 3:
                self._apply_axis_deltas({enabled_axes[2]: -dy})
            else:
                self._orbit_camera(dx, dy)

        elif self._drag_button == Qt.MouseButton.MiddleButton:
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
        self._cam_azimuth += dx * 0.4
        self._cam_elevation = max(-89.0, min(89.0, self._cam_elevation - dy * 0.4))

    def _apply_axis_deltas(self, raw_deltas: dict):
        """Apply one drag-step of Move/Rotate/Size to every selected node.

        raw_deltas maps axis letter ('x'/'y'/'z') to a raw screen-space pixel
        delta for that axis; sign/scale conversion to world units happens here
        based on the active gizmo_mode.
        """
        if not raw_deltas or not self.selected_node_ids:
            return
        changed = set()
        for nid in self.selected_node_ids:
            node = self._scene.node_by_id(nid)
            if node is None:
                continue
            for axis, raw in raw_deltas.items():
                if self.gizmo_mode == 'move':
                    speed = self._cam_distance * 0.0015   # matches camera-pan speed
                    attr = f'translate_{axis}'
                    setattr(node, attr, getattr(node, attr) + raw * speed)
                elif self.gizmo_mode == 'rotate':
                    attr = f'rotate_{axis}'
                    setattr(node, attr, getattr(node, attr) + raw * 0.4)  # matches orbit sensitivity
                elif self.gizmo_mode == 'size':
                    attr = f'scale_{axis}'
                    factor = 1.0 + raw * 0.004
                    setattr(node, attr, max(0.001, getattr(node, attr) * factor))
            changed.add(nid)
        if changed:
            self._scene.invalidate()
            self.update()
            self.nodesManipulated.emit(changed)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 0.88 if delta > 0 else 1.14
        self._cam_distance = max(1.0, self._cam_distance * factor)
        self.update()
