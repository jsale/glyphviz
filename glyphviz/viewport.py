import math

from OpenGL.GL import *
from OpenGL.GLU import *
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from .geometry import GeoRenderer, GEO_SPHERE
from .node import Node, NON_VISUAL_TYPES
from .topology import compute_world_positions, compute_world_scales

_DRAG_THRESHOLD = 4  # pixels — less than this counts as a click, not a drag


# --- rotation helpers for picking (mirror the Rx/Ry/Rz convention glRotatef
# uses — right-hand rule about each axis — so we can invert a node's
# rotation when transforming a pick ray into its local space) ---

def _rotate_x(x, y, z, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return x, c*y - s*z, s*y + c*z


def _rotate_y(x, y, z, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return c*x + s*z, y, -s*x + c*z


def _rotate_z(x, y, z, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return c*x - s*y, s*x + c*y, z


class Viewport(QOpenGLWidget):
    # Emitted when the user clicks (not drags) on a node; carries node id
    nodeClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.nodes: list[Node] = []
        self.show_axes = True
        self.show_grid = True
        self.show_hidden = False
        self.base_scale = 3.0
        self.selected_node_id: int | None = None
        self._world_pos: dict[int, tuple[float, float, float]] = {}
        self._world_scale: dict[int, tuple[float, float, float]] = {}

        self._cam_distance = 500.0
        self._cam_azimuth = 45.0
        self._cam_elevation = 25.0
        self._cam_target = [0.0, 0.0, 0.0]

        self._last_pos = QPoint()
        self._press_pos = QPoint()
        self._drag_button = None
        self._drag_moved = False
        self._quadric = None
        self._geo = GeoRenderer()

        self.setMinimumSize(400, 300)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_nodes(self, nodes: list[Node]):
        self.nodes = nodes
        self._recompute_world_positions()
        visible = [n for n in nodes if n.type not in NON_VISUAL_TYPES]
        if visible:
            positions = [self._world_pos[n.id] for n in visible]
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

    def _radius_of(self, node: Node) -> tuple[float, float, float]:
        """Rendered per-axis surface radii (rx, ry, rz), honoring scale
        inherited from ancestors (scaling a parent up/down carries its whole
        subtree proportionally) and letting a node's own scale_x/y/z stretch
        its glyph independently along each axis."""
        scale = self._world_scale.get(node.id)
        if scale is None:
            scale = (node.scale_x, node.scale_y, node.scale_z)
        sx, sy, sz = scale
        return (
            max(sx * self.base_scale, 0.2),
            max(sy * self.base_scale, 0.2),
            max(sz * self.base_scale, 0.2),
        )

    def _placement_radius_of(self, node: Node) -> float:
        """Single effective radius used for surface-based topology placement
        (e.g. a sphere child riding its parent's surface). Non-uniformly
        scaled glyphs render as ellipsoids/distorted tori, but placing
        children on their exact distorted surface is a much larger undertaking
        than independent XYZ scaling calls for — so placement math uses the
        average of the per-axis radii as a representative "effective" surface,
        which matches the old (uniform-scale) behavior exactly when scale_x ==
        scale_y == scale_z."""
        rx, ry, rz = self._radius_of(node)
        return (rx + ry + rz) / 3.0

    def _recompute_world_positions(self):
        """Resolve every node's rendered world position and size, honoring
        parent topology (e.g. sphere children riding their parent's surface)
        and inherited scale — so that moving or resizing a parent carries its
        whole subtree along with it."""
        self._world_scale = compute_world_scales(self.nodes)
        self._world_pos = compute_world_positions(self.nodes, self._placement_radius_of, self._world_scale)

    def world_position(self, node_id: int) -> tuple[float, float, float] | None:
        """Rendered world-space position of a node, as last computed for drawing."""
        return self._world_pos.get(node_id)

    def focus_on(self, world_pos: tuple[float, float, float], min_distance: float = 1.0):
        """Center the camera on `world_pos` and pull it in to roughly 1/10 of
        its current distance from that point — a quick way to "jump to and
        zoom into" a node of interest while preserving the current viewing
        angle (azimuth/elevation). Never moves closer than `min_distance`,
        so the camera doesn't end up embedded inside the object when it was
        already nearby."""
        az = math.radians(self._cam_azimuth)
        el = math.radians(self._cam_elevation)
        tx, ty, tz = self._cam_target
        ex = tx + self._cam_distance * math.cos(el) * math.sin(az)
        ey = ty + self._cam_distance * math.sin(el)
        ez = tz + self._cam_distance * math.cos(el) * math.cos(az)

        px, py, pz = world_pos
        dist_to_obj = math.sqrt((ex - px)**2 + (ey - py)**2 + (ez - pz)**2)

        self._cam_target = [px, py, pz]
        self._cam_distance = max(dist_to_obj / 10.0, min_distance)
        self.update()

    def focus_on_node(self, node: Node):
        """Center the camera on `node` and zoom toward it (see focus_on),
        clamping the minimum camera distance to ~1.5x the node's largest
        rendered radius — enough headroom to keep the whole glyph in view
        rather than the camera ending up inside it."""
        pos = self.world_position(node.id) or (node.translate_x, node.translate_y, node.translate_z)
        rx, ry, rz = self._radius_of(node)
        self.focus_on(pos, min_distance=max(rx, ry, rz) * 1.5)

    def initializeGL(self):
        glClearColor(0.08, 0.08, 0.12, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [1.0, 1.0, 1.0, 1.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.3, 0.3, 0.3, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [0.5, 0.5, 0.5, 1.0])
        glLightfv(GL_LIGHT0, GL_POSITION, [1.0, 2.0, 1.0, 0.0])
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glShadeModel(GL_SMOOTH)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        self._quadric = gluNewQuadric()
        gluQuadricNormals(self._quadric, GLU_SMOOTH)
        self._geo.setup()

    def resizeGL(self, w, h):
        if h == 0:
            h = 1
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, w / h, 0.1, 100000.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        self._recompute_world_positions()

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        az = math.radians(self._cam_azimuth)
        el = math.radians(self._cam_elevation)
        tx, ty, tz = self._cam_target

        eye_x = tx + self._cam_distance * math.cos(el) * math.sin(az)
        eye_y = ty + self._cam_distance * math.sin(el)
        eye_z = tz + self._cam_distance * math.cos(el) * math.cos(az)

        gluLookAt(eye_x, eye_y, eye_z, tx, ty, tz, 0.0, 1.0, 0.0)

        if self.show_grid:
            self._draw_grid()
        if self.show_axes:
            self._draw_axes()

        for node in self.nodes:
            if node.type in NON_VISUAL_TYPES:
                continue
            if not self.show_hidden and node.hide:
                continue
            self._draw_node(node, selected=(node.id == self.selected_node_id))

    def _draw_node(self, node: Node, selected: bool = False):
        wx, wy, wz = self._world_pos.get(node.id, (node.translate_x, node.translate_y, node.translate_z))

        glPushMatrix()
        glTranslatef(wx, wy, wz)
        glRotatef(node.rotate_z, 0.0, 0.0, 1.0)
        glRotatef(node.rotate_y, 0.0, 1.0, 0.0)
        glRotatef(node.rotate_x, 1.0, 0.0, 0.0)

        glColor4f(
            node.color_r / 255.0,
            node.color_g / 255.0,
            node.color_b / 255.0,
            node.color_a / 255.0,
        )

        rx, ry, rz = self._radius_of(node)
        self._geo.draw(node.geometry, rx, ry, rz)

        if selected:
            glDisable(GL_LIGHTING)
            glLineWidth(2.0)
            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
            glColor4f(1.0, 0.95, 0.1, 1.0)
            self._geo.draw(GEO_SPHERE, rx * 1.35, ry * 1.35, rz * 1.35)
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
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
        count = 20          # larger count ensures coverage after panning
        size = step * count
        # Fixed world position (Y=0) — panning moves the camera, not the grid,
        # so grid and nodes shift together on screen just like any world object.
        glBegin(GL_LINES)
        for i in range(-count, count + 1):
            glVertex3f(i * step, 0.0, -size)
            glVertex3f(i * step, 0.0,  size)
            glVertex3f(-size, 0.0, i * step)
            glVertex3f( size, 0.0, i * step)
        glEnd()
        glEnable(GL_LIGHTING)

    # --- picking (ray cast against rotated/stretched bounding ellipsoids) ---

    def _ellipsoid_hit_t(self, node, ocx, ocy, ocz, rdx, rdy, rdz, rx, ry, rz):
        """
        Ray-vs-glyph hit test against the actual rendered shape: an ellipsoid
        with the node's per-axis radii (rx, ry, rz), oriented by its
        rotate_x/y/z — matching what _draw_node renders via glRotatef +
        glScalef. A plain bounding *sphere* over- or under-selects nodes that
        are stretched along one or two axes (the "elongated ends are hard to
        click / parent can't be selected" symptom): a long thin glyph either
        gets a too-small sphere (misses its tips) or a too-large one (its
        empty space blocks clicks meant for neighbors).

        `ocx,ocy,ocz` is the eye position relative to the node's world-space
        center; `rdx,rdy,rdz` is the (unit-length) ray direction. Returns the
        ray parameter t (== world-space hit distance, since the ray direction
        is unit length) of the nearest intersection, or None.

        Method: transform the ray into the node's local space by undoing its
        rotation (inverse of a rotation matrix is its transpose — rotating by
        the same angles in reverse order, negated) and then dividing by the
        per-axis radii. That maps the rendered ellipsoid onto a unit sphere
        while preserving the ray's parametrization t (rotation and uniform
        rescaling are linear maps applied identically to the ray's origin and
        direction, so the parameter along the ray is unchanged) — so a plain
        unit-sphere quadratic yields the correct hit distance directly.
        """
        # _draw_node composes world = translate * Rz * Ry * Rx * scale, so the
        # inverse (local = scale^-1 * Rx^-1 * Ry^-1 * Rz^-1 * world_relative)
        # undoes Z, then Y, then X — each by its negated angle.
        ox, oy, oz = _rotate_x(*_rotate_y(*_rotate_z(ocx, ocy, ocz, -node.rotate_z), -node.rotate_y), -node.rotate_x)
        dx, dy, dz = _rotate_x(*_rotate_y(*_rotate_z(rdx, rdy, rdz, -node.rotate_z), -node.rotate_y), -node.rotate_x)

        ox, oy, oz = ox / rx, oy / ry, oz / rz
        dx, dy, dz = dx / rx, dy / ry, dz / rz

        a = dx*dx + dy*dy + dz*dz
        b = 2.0 * (ox*dx + oy*dy + oz*dz)
        c = ox*ox + oy*oy + oz*oz - 1.0
        disc = b*b - 4.0*a*c
        if disc < 0:
            return None
        sqrt_disc = math.sqrt(disc)
        t = (-b - sqrt_disc) / (2.0*a)
        if t <= 0:
            t = (-b + sqrt_disc) / (2.0*a)
        return t if t > 0 else None

    def _pick_node(self, screen_x: int, screen_y: int) -> Node | None:
        """
        Cast a ray from camera through (screen_x, screen_y) in widget coords.
        Returns the nearest visible node whose rendered glyph (a rotated,
        per-axis-scaled ellipsoid) is hit, or None.
        Uses camera parameters directly — no GL matrix reads required.
        """
        if not self.nodes:
            return None
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return None

        # ---- Camera position ------------------------------------------------
        az = math.radians(self._cam_azimuth)
        el = math.radians(self._cam_elevation)
        tx, ty, tz = self._cam_target

        ex = tx + self._cam_distance * math.cos(el) * math.sin(az)
        ey = ty + self._cam_distance * math.sin(el)
        ez = tz + self._cam_distance * math.cos(el) * math.cos(az)

        # ---- Camera basis (forward, right, up) ------------------------------
        # forward = normalise(target - eye)
        fdx, fdy, fdz = tx - ex, ty - ey, tz - ez
        fd = math.sqrt(fdx*fdx + fdy*fdy + fdz*fdz)
        fdx, fdy, fdz = fdx/fd, fdy/fd, fdz/fd

        # right = cross(forward, world_up)  → (-fdz, 0, fdx)
        rx, ry, rz = -fdz, 0.0, fdx
        rd = math.sqrt(rx*rx + rz*rz)
        if rd < 1e-9:          # camera pointing straight up/down — use fallback
            rx, rz = 1.0, 0.0
        else:
            rx, rz = rx/rd, rz/rd

        # up = cross(right, forward)
        ux = ry*fdz - rz*fdy
        uy = rz*fdx - rx*fdz
        uz = rx*fdy - ry*fdx

        # ---- Screen → world ray direction -----------------------------------
        # NDC: x ∈ [-1,+1] left→right, y ∈ [-1,+1] bottom→top
        ndc_x = (2.0 * screen_x / w) - 1.0
        ndc_y = 1.0 - (2.0 * screen_y / h)   # Qt y is top-down

        tan_hfov = math.tan(math.radians(22.5))   # half of 45° fov
        aspect = w / h
        vx = ndc_x * aspect * tan_hfov
        vy = ndc_y * tan_hfov

        # ray_dir = normalise(forward + vx*right + vy*up)
        rdx = fdx + vx*rx + vy*ux
        rdy = fdy + vx*ry + vy*uy
        rdz = fdz + vx*rz + vy*uz
        rdn = math.sqrt(rdx*rdx + rdy*rdy + rdz*rdz)
        rdx, rdy, rdz = rdx/rdn, rdy/rdn, rdz/rdn

        # ---- Ray–glyph tests -------------------------------------------------
        best_node, best_t = None, float('inf')
        _CLICK_MARGIN = 1.15  # slightly enlarge each axis for easier clicking

        for node in self.nodes:
            if node.type in NON_VISUAL_TYPES:
                continue
            if not self.show_hidden and node.hide:
                continue

            node_rx, node_ry, node_rz = self._radius_of(node)
            wx, wy, wz = self._world_pos.get(node.id, (node.translate_x, node.translate_y, node.translate_z))
            ocx = ex - wx
            ocy = ey - wy
            ocz = ez - wz
            t = self._ellipsoid_hit_t(
                node, ocx, ocy, ocz, rdx, rdy, rdz,
                node_rx * _CLICK_MARGIN, node_ry * _CLICK_MARGIN, node_rz * _CLICK_MARGIN,
            )
            if t is not None and t < best_t:
                best_t, best_node = t, node

        return best_node

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
            print(f"[pick] ({event.pos().x()},{event.pos().y()}) → {label}")
            if node is not None:
                self.nodeClicked.emit(node.id)
                # Shift-click: jump to and zoom in on the clicked node — an
                # in-viewport alternative to double-clicking its table row.
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

        # Mark as a drag once the cursor has moved enough
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
            right_x = math.cos(az)
            right_z = -math.sin(az)
            up_x = -math.sin(el) * math.sin(az)
            up_y = math.cos(el)
            up_z = -math.sin(el) * math.cos(az)
            speed = self._cam_distance * 0.0015
            self._cam_target[0] -= (dx * right_x - dy * up_x) * speed
            self._cam_target[1] += dy * up_y * speed
            self._cam_target[2] -= (dx * right_z - dy * up_z) * speed

        self._last_pos = event.pos()
        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 0.88 if delta > 0 else 1.14
        self._cam_distance = max(1.0, self._cam_distance * factor)
        self.update()
