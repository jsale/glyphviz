import math

import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from .geometry import GeoRenderer
from .node import Node, NON_VISUAL_TYPES
from .scene import Scene, node_world_matrix

_DRAG_THRESHOLD = 4  # pixels — less than this counts as a click, not a drag


def _gl_col_major(M: np.ndarray) -> np.ndarray:
    """Convert a 4x4 NumPy row-major matrix to a float32 column-major flat array
    for glMultMatrixf / glLoadMatrixf (OpenGL column-major convention)."""
    return M.astype(np.float32).T.flatten()


class Viewport(QOpenGLWidget):
    # Emitted when the user clicks (not drags) on a node; carries node id
    nodeClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = Scene([])
        self._base_scale = 3.0
        self.show_axes = True
        self.show_grid = True
        self.show_hidden = False
        self.selected_node_id: int | None = None

        self._cam_distance = 500.0
        self._cam_azimuth = 45.0
        self._cam_elevation = 25.0
        self._cam_target = [0.0, 0.0, 0.0]

        self._last_pos = QPoint()
        self._press_pos = QPoint()
        self._drag_button = None
        self._drag_moved = False

        # color-ID pick FBO resources (created lazily after GL context exists)
        self._pick_fbo = 0
        self._pick_tex = 0
        self._pick_rbo = 0
        self._pick_fbo_size = (0, 0)

        self._geo = GeoRenderer()
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

    def set_nodes(self, nodes: list[Node]):
        self._scene = Scene(nodes, self._base_scale)
        self._scene._ensure()   # pre-compute so camera init can read positions
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

    # --- GL lifecycle ---

    def initializeGL(self):
        glClearColor(0.08, 0.08, 0.12, 1.0)
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
        # Recompute world transforms every frame so inspector edits show immediately.
        self._scene.invalidate()

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        az = math.radians(self._cam_azimuth)
        el = math.radians(self._cam_elevation)
        tx, ty, tz = self._cam_target
        eye_x = tx + self._cam_distance * math.cos(el) * math.cos(az)
        eye_y = ty + self._cam_distance * math.cos(el) * math.sin(az)
        eye_z = tz + self._cam_distance * math.sin(el)
        gluLookAt(eye_x, eye_y, eye_z, tx, ty, tz, 0.0, 0.0, 1.0)

        if self.show_grid:
            self._draw_grid()
        if self.show_axes:
            self._draw_axes()

        for node in self._scene.nodes:
            if node.type in NON_VISUAL_TYPES:
                continue
            if not self.show_hidden and node.hide:
                continue
            self._draw_node(node, selected=(node.id == self.selected_node_id))

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

        # M already encodes scale (column norms = rendered radii), so we draw
        # the geometry at unit size (1,1,1) and let the matrix handle sizing.
        self._geo.draw(node.geometry, 1.0, 1.0, 1.0, ratio=node.ratio)

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

    def _pick_node(self, screen_x: int, screen_y: int) -> Node | None:
        """
        Color-ID offscreen picking: render every glyph into an FBO with its
        node ID encoded as RGB (r = id & 0xFF, g = id>>8 & 0xFF, b = id>>16),
        then read the pixel under the cursor.

        Uses node_world_matrix — the same matrices and the same draw calls as
        paintGL — so the hit geometry is geometrically identical to what is
        displayed.  The Y-flip (Qt top-left vs OpenGL bottom-left) and the
        devicePixelRatio (HiDPI) are both handled here.
        """
        if not self._scene.nodes:
            return None

        self.makeCurrent()
        try:
            w, h = self.width(), self.height()
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

            # Mirror paintGL's projection and camera setup exactly
            glMatrixMode(GL_PROJECTION)
            glPushMatrix()
            glLoadIdentity()
            gluPerspective(45.0, w / h, 0.1, 100000.0)
            glMatrixMode(GL_MODELVIEW)
            glPushMatrix()
            glLoadIdentity()

            az = math.radians(self._cam_azimuth)
            el = math.radians(self._cam_elevation)
            tx, ty, tz = self._cam_target
            eye_x = tx + self._cam_distance * math.cos(el) * math.cos(az)
            eye_y = ty + self._cam_distance * math.cos(el) * math.sin(az)
            eye_z = tz + self._cam_distance * math.sin(el)
            gluLookAt(eye_x, eye_y, eye_z, tx, ty, tz, 0.0, 0.0, 1.0)

            glDisable(GL_LIGHTING)
            glDisable(GL_BLEND)

            # Re-use the scene cache from the most recent paint (no invalidate here)
            for node in self._scene.nodes:
                if node.type in NON_VISUAL_TYPES:
                    continue
                if not self.show_hidden and node.hide:
                    continue
                r = node.id & 0xFF
                g = (node.id >> 8) & 0xFF
                b = (node.id >> 16) & 0xFF
                glColor4ub(r, g, b, 255)
                M = node_world_matrix(node, self._scene)
                glPushMatrix()
                glMultMatrixf(_gl_col_major(M))
                self._geo.draw(node.geometry, 1.0, 1.0, 1.0, ratio=node.ratio)
                glPopMatrix()

            # Y-flip: Qt widget coords are top-left origin;
            # glReadPixels uses bottom-left origin.
            # HiDPI: multiply by devicePixelRatio to get framebuffer pixels.
            fb_x = min(max(int(screen_x * dpr), 0), fb_w - 1)
            fb_y = min(max(int((h - 1 - screen_y) * dpr), 0), fb_h - 1)
            pixel = glReadPixels(fb_x, fb_y, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)

            glEnable(GL_LIGHTING)
            glEnable(GL_BLEND)
            glMatrixMode(GL_PROJECTION)
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)
            glPopMatrix()
            glBindFramebuffer(GL_FRAMEBUFFER, qt_fbo)
            glViewport(0, 0, fb_w, fb_h)

        finally:
            self.doneCurrent()

        # Decode RGB → node ID
        arr = np.asarray(pixel, dtype=np.uint8).flat
        pr, pg, pb = int(arr[0]), int(arr[1]), int(arr[2])
        node_id = pr | (pg << 8) | (pb << 16)
        if node_id == 0:
            return None
        return self._scene.node_by_id(node_id)

    # --- mouse ---

    def mousePressEvent(self, event):
        self._last_pos = event.pos()
        self._press_pos = event.pos()
        self._drag_button = event.button()
        self._drag_moved = False

    def mouseReleaseEvent(self, event):
        if (not self._drag_moved
                and self._drag_button == Qt.MouseButton.LeftButton):
            node = self._pick_node(event.pos().x(), event.pos().y())
            label = f"Node {node.id}" if node else "miss"
            print(f"[pick] ({event.pos().x()},{event.pos().y()}) -> {label}")
            if node is not None:
                self.nodeClicked.emit(node.id)
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self.focus_on_node(node)
        self._drag_button = None
        self._drag_moved = False

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            node = self._pick_node(event.pos().x(), event.pos().y())
            if node is not None:
                self.nodeClicked.emit(node.id)
                self.focus_on_node(node)

    def mouseMoveEvent(self, event):
        if self._drag_button is None:
            return
        dx = event.pos().x() - self._last_pos.x()
        dy = event.pos().y() - self._last_pos.y()

        if not self._drag_moved:
            total_dx = event.pos().x() - self._press_pos.x()
            total_dy = event.pos().y() - self._press_pos.y()
            if total_dx**2 + total_dy**2 >= _DRAG_THRESHOLD**2:
                self._drag_moved = True

        if self._drag_button == Qt.MouseButton.LeftButton:
            self._cam_azimuth += dx * 0.4
            self._cam_elevation = max(-89.0, min(89.0, self._cam_elevation - dy * 0.4))

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

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 0.88 if delta > 0 else 1.14
        self._cam_distance = max(1.0, self._cam_distance * factor)
        self.update()
