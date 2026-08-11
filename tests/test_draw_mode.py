"""
Draw Mode tests.

Math first (glyphviz_core/draw_mode.py, no Qt): that screen_ray inverts the
camera's own projection, and that grid_hit is the exact inverse of the flat
World Grid child placement in compute_world_transforms — a child created at
the returned (lon, lat, draw_z) lands on the clicked ray, whatever the grid's
translate/rotate/scale.

Then the wiring, through the real Viewport (offscreen Qt, camera matrices
seeded the same way tests/test_gizmo_viewport.py does — no GL context): a
left press in Draw Mode emits drawStampRequested instead of picking, a drag
stamps again only after draw_stamp_spacing_px of travel, release ends the
stroke without clearing the selection, and Draw Mode and Camera Mode
displace each other.
"""
import math
import os

import numpy as np
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from glyphviz_core import draw_mode as dm                     # noqa: E402
from glyphviz_core.geometry_data import GEO_GRID_WIRE          # noqa: E402
from glyphviz_core.node import Node, NODE_TYPE_GRID            # noqa: E402
from glyphviz_core.scene import Scene                          # noqa: E402


def _node(node_id, x=0.0, y=0.0, z=0.0, **kw):
    n = Node(
        id=node_id, type=5, parent_id=0, branch_level=0,
        translate_x=x, translate_y=y, translate_z=z,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=255, color_g=255, color_b=255, color_a=255,
        geometry=3, hide=0, topo=0,
    )
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def _grid(node_id=1, **kw):
    g = _node(node_id, type=NODE_TYPE_GRID, geometry=GEO_GRID_WIRE)
    for k, v in kw.items():
        setattr(g, k, v)
    return g


def _camera(eye, target, w=800.0, h=600.0, up=(0.0, 0.0, 1.0),
            fov_deg=45.0, near=0.1, far=100000.0):
    """Row-major gluLookAt/gluPerspective pair, exactly as the viewport's
    _capture_camera_matrices returns them (same construction as
    test_gizmo_viewport._seed_camera)."""
    eye = np.asarray(eye, dtype=np.float64)
    f = np.asarray(target, dtype=np.float64) - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, np.asarray(up, dtype=np.float64))
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    mv = np.eye(4)
    mv[0, :3], mv[1, :3], mv[2, :3] = s, u, -f
    mv[:3, 3] = -mv[:3, :3] @ eye

    cot = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    pr = np.zeros((4, 4))
    pr[0, 0] = cot / (w / h)
    pr[1, 1] = cot
    pr[2, 2] = (far + near) / (near - far)
    pr[2, 3] = 2.0 * far * near / (near - far)
    pr[3, 2] = -1.0
    return mv, pr


# --- screen_ray ---

def test_screen_ray_center_pixel_aims_at_the_target():
    w, h = 800.0, 600.0
    mv, pr = _camera(eye=(0.0, 0.0, 300.0), target=(0.0, 0.0, 0.0),
                     w=w, h=h, up=(0.0, 1.0, 0.0))
    origin, direction = dm.screen_ray(mv, pr, w / 2.0, h / 2.0, w, h)
    # The center pixel's ray runs straight down the view axis.
    assert np.allclose(direction, [0.0, 0.0, -1.0], atol=1e-9)
    assert np.allclose(origin[:2], [0.0, 0.0], atol=1e-6)


def test_screen_ray_round_trips_through_the_projection():
    """Any point along the returned ray projects back to the queried pixel."""
    w, h = 800.0, 600.0
    mv, pr = _camera(eye=(120.0, -80.0, 250.0), target=(10.0, 5.0, 0.0),
                     w=w, h=h)
    mvp = pr @ mv
    for px, py in [(400.0, 300.0), (100.0, 50.0), (731.0, 512.0)]:
        origin, direction = dm.screen_ray(mv, pr, px, py, w, h)
        for t in (5.0, 40.0, 900.0):
            p = np.append(origin + t * direction, 1.0)
            clip = mvp @ p
            ndc = clip[:3] / clip[3]
            sx = (ndc[0] + 1.0) * 0.5 * w
            sy = (1.0 - ndc[1]) * 0.5 * h
            assert abs(sx - px) < 1e-6 and abs(sy - py) < 1e-6


# --- grid_hit: exact inverse of flat-grid child placement ---

def _hit_matches_forward_placement(grid, target_world, ray_origin,
                                   draw_z=0.0):
    """grid_hit for a ray aimed at target_world must return (lon, lat) that
    compute_world_transforms places back at target_world exactly."""
    scene = Scene([grid], base_scale=1.0)
    pos = np.asarray(scene.world_pos(grid.id))
    basis = scene.basis_matrices(grid.id)[0]

    ray_origin = np.asarray(ray_origin, dtype=np.float64)
    direction = np.asarray(target_world, dtype=np.float64) - ray_origin
    direction /= np.linalg.norm(direction)
    hit = dm.grid_hit(ray_origin, direction, pos, basis, grid.grid_center(),
                      draw_z)
    assert hit is not None
    lon, lat = hit

    child = _node(99, x=lon, y=lat, z=draw_z, parent_id=grid.id,
                  branch_level=grid.branch_level + 1)
    scene2 = Scene([grid, child], base_scale=1.0)
    assert np.allclose(scene2.world_pos(child.id), target_world, atol=1e-9)


def test_grid_hit_default_grid_is_identity():
    """Whole-earth grid at the origin, scale 1: world (x, y, 0) is child
    (lon=x, lat=y) — the 1:1 frame the World Grid docs promise."""
    grid = _grid()
    grid.set_grid_extents(-180.0, 180.0, -90.0, 90.0)
    scene = Scene([grid], base_scale=1.0)
    pos = np.asarray(scene.world_pos(grid.id))
    basis = scene.basis_matrices(grid.id)[0]
    hit = dm.grid_hit((30.0, -20.0, 100.0), (0.0, 0.0, -1.0), pos, basis,
                      grid.grid_center())
    assert hit == pytest.approx((30.0, -20.0))


def test_grid_hit_region_window_recenters():
    """A region-extents grid recenters children on the window midpoint:
    the point straight above the grid's origin is the window center."""
    grid = _grid()
    grid.set_grid_extents(-120.0, -110.0, 30.0, 40.0)   # center (-115, 35)
    scene = Scene([grid], base_scale=1.0)
    pos = np.asarray(scene.world_pos(grid.id))
    basis = scene.basis_matrices(grid.id)[0]
    hit = dm.grid_hit((0.0, 0.0, 50.0), (0.0, 0.0, -1.0), pos, basis,
                      grid.grid_center())
    assert hit == pytest.approx((-115.0, 35.0))


def test_grid_hit_inverts_transformed_grid():
    """Translated + rotated + non-uniformly scaled grid, oblique ray."""
    grid = _grid(x=40.0, y=-25.0, z=12.0,
                 rotate_x=20.0, rotate_z=35.0,
                 scale_x=2.0, scale_y=0.5, scale_z=1.5)
    grid.set_grid_extents(-10.0, 10.0, -5.0, 5.0)
    scene = Scene([grid], base_scale=1.0)
    pos = np.asarray(scene.world_pos(grid.id))
    basis = scene.basis_matrices(grid.id)[0]
    # Aim at an arbitrary spot ON the grid plane: local (7.5, -2.0, 0).
    target = pos + basis @ np.array([7.5, -2.0, 0.0])
    _hit_matches_forward_placement(grid, target, (200.0, 150.0, 400.0))


def test_grid_hit_draw_z_lands_on_the_elevated_plane():
    grid = _grid(rotate_z=45.0, scale_x=3.0)
    scene = Scene([grid], base_scale=1.0)
    pos = np.asarray(scene.world_pos(grid.id))
    basis = scene.basis_matrices(grid.id)[0]
    target = pos + basis @ np.array([12.0, 30.0, 8.0])   # local z = 8
    _hit_matches_forward_placement(grid, target, (-90.0, 60.0, 500.0),
                                   draw_z=8.0)


def test_grid_hit_rejects_parallel_and_behind():
    grid = _grid()
    scene = Scene([grid], base_scale=1.0)
    pos = np.asarray(scene.world_pos(grid.id))
    basis = scene.basis_matrices(grid.id)[0]
    center = grid.grid_center()
    # Ray parallel to the plane.
    assert dm.grid_hit((0.0, 0.0, 10.0), (1.0, 0.0, 0.0), pos, basis,
                       center) is None
    # Plane behind the ray origin (looking up, plane below).
    assert dm.grid_hit((0.0, 0.0, 10.0), (0.0, 0.0, 1.0), pos, basis,
                       center) is None


# --- should_stamp (drag spacing gate) ---

def test_should_stamp_spacing():
    assert dm.should_stamp(None, 5.0, 5.0, 30.0)          # first point: always
    assert not dm.should_stamp((0.0, 0.0), 20.0, 0.0, 30.0)
    assert dm.should_stamp((0.0, 0.0), 30.0, 0.0, 30.0)   # exactly at spacing
    assert dm.should_stamp((0.0, 0.0), 25.0, 25.0, 30.0)  # diagonal distance
    assert dm.should_stamp((0.0, 0.0), 0.1, 0.0, 0.0)     # spacing 0: every move


# --- Viewport wiring (offscreen Qt, no GL context) ---

pytest.importorskip('PySide6.QtWidgets')

from PySide6.QtCore import QPoint, Qt                   # noqa: E402
from PySide6.QtWidgets import QApplication              # noqa: E402

from glyphviz_gl.viewport import Viewport               # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:                        # pragma: no cover
            pytest.skip(f'Qt unavailable: {exc}')
    return app


def _seed_camera(vp):
    """Same seeding as test_gizmo_viewport: the matrices paintGL would have
    captured for the viewport's own orbit rig."""
    w, h = float(vp.width()), float(vp.height())
    az, el = math.radians(vp._cam_azimuth), math.radians(vp._cam_elevation)
    tgt = np.array(vp._cam_target, dtype=np.float64)
    eye = tgt + vp._cam_distance * np.array([
        math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    vp._mv_matrix, vp._proj_matrix = _camera(eye, tgt, w, h,
                                             up=vp._camera_up())


class _Mouse:
    """Stand-in for QMouseEvent — the handlers only read pos()/button()/
    buttons()/modifiers()."""

    def __init__(self, x, y, button=Qt.MouseButton.LeftButton, buttons=None,
                 modifiers=Qt.KeyboardModifier.NoModifier):
        self._pos = QPoint(int(x), int(y))
        self._button = button
        self._buttons = buttons if buttons is not None else button
        self._mods = modifiers

    def pos(self):
        return self._pos

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons

    def modifiers(self):
        return self._mods


@pytest.fixture
def vp(qapp):
    v = Viewport()
    v.resize(800, 600)
    grid = _grid()
    grid.set_grid_extents(-180.0, 180.0, -90.0, 90.0)
    v.set_nodes([grid, _node(2, 40.0, 10.0, 0.0)])
    # Straight overhead, so the widget center looks at the world origin.
    v._cam_azimuth, v._cam_elevation, v._cam_distance = 0.0, 89.9, 400.0
    v._cam_target = [0.0, 0.0, 0.0]
    _seed_camera(v)
    return v


def _record(signal):
    hits = []
    signal.connect(lambda *args: hits.append(args))
    return hits


def test_draw_press_stamps_instead_of_picking(vp):
    vp.set_draw_mode(True)
    stamps = _record(vp.drawStampRequested)
    selected = _record(vp.nodesSelected)
    vp.mousePressEvent(_Mouse(400, 300))
    assert stamps == [(400.0, 300.0)]
    vp.mouseReleaseEvent(_Mouse(400, 300))
    assert selected == []          # the click-picker never ran
    assert stamps == [(400.0, 300.0)]


def test_draw_drag_stamps_at_spacing(vp):
    vp.set_draw_mode(True)
    vp.draw_stamp_spacing_px = 30.0
    stamps = _record(vp.drawStampRequested)
    strokes = _record(vp.drawStrokeFinished)
    vp.mousePressEvent(_Mouse(100, 100))
    vp.mouseMoveEvent(_Mouse(110, 100))     # 10 px: below spacing
    assert len(stamps) == 1
    vp.mouseMoveEvent(_Mouse(131, 100))     # 31 px from last stamp
    assert len(stamps) == 2
    vp.mouseMoveEvent(_Mouse(140, 100))     # 9 px from last stamp
    assert len(stamps) == 2
    vp.mouseReleaseEvent(_Mouse(140, 100))
    assert strokes == [()]
    # Stroke over: plain motion stamps nothing.
    vp.mouseMoveEvent(_Mouse(300, 300, buttons=Qt.MouseButton.NoButton))
    assert len(stamps) == 2


def test_ctrl_click_still_selects_in_draw_mode(vp):
    vp.set_draw_mode(True)
    stamps = _record(vp.drawStampRequested)
    vp.mousePressEvent(_Mouse(400, 300,
                              modifiers=Qt.KeyboardModifier.ControlModifier))
    assert stamps == []            # fell through to the normal press path


def test_draw_and_fly_modes_displace_each_other(vp):
    vp.set_draw_mode(True)
    vp.set_fly_mode(True)
    assert vp.fly_mode and not vp.draw_mode
    vp.set_draw_mode(True)
    assert vp.draw_mode and not vp.fly_mode


def test_draw_plane_hit_center_is_grid_center(vp):
    grid = vp.nodes[0]
    lon, lat = vp.draw_plane_hit(400.0, 300.0, grid, 0.0)
    # Camera looks at world (0,0,0) = grid-local (0,0) = window center (0,0).
    assert (lon, lat) == pytest.approx((0.0, 0.0), abs=1e-3)


def test_draw_plane_hit_matches_forward_placement(vp):
    """An off-center pixel's hit, fed back in as a child, projects to that
    same pixel — the stamped glyph appears under the cursor."""
    grid = vp.nodes[0]
    px, py = 520.0, 210.0
    lon, lat = vp.draw_plane_hit(px, py, grid, 0.0)
    child = _node(99, x=lon, y=lat, z=0.0, parent_id=grid.id, branch_level=1)
    scene = Scene([grid, child], base_scale=1.0)
    world = np.append(np.asarray(scene.world_pos(child.id)), 1.0)
    clip = (vp._proj_matrix @ vp._mv_matrix) @ world
    ndc = clip[:3] / clip[3]
    sx = (ndc[0] + 1.0) * 0.5 * vp.width()
    sy = (1.0 - ndc[1]) * 0.5 * vp.height()
    assert (sx, sy) == pytest.approx((px, py), abs=1e-6)
