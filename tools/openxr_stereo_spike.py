"""
OpenXR stereo rendering spike — renders a real GlyphViz scene to the Quest 3
as a tabletop diorama, reusing the existing kernel/renderer unchanged:
glyphviz_core.scene.node_world_matrix() supplies each node's transform and
glyphviz_gl.geometry.GeoRenderer draws it, exactly as glyphviz_gl.viewport
does on the desktop — only the camera (now per-eye, from the runtime) and
the output target (a swapchain framebuffer per eye, not a QOpenGLWidget) are
different.

This is a throwaway diagnostic, not the start of a "glyphviz_xr" package:
no picking, no textures, one fixed-direction light. Touch controller
navigation (thumbstick fly + grip-drag) is wired up via the OpenXR action
system; see ControllerNav.
Run it with the Quest 3 connected and Link active (see tools/openxr_probe.py
to confirm that part works first).

Usage:
    C:\\Users\\jsale\\anaconda3\\envs\\glyphviz\\python.exe tools\\openxr_stereo_spike.py
    C:\\Users\\jsale\\anaconda3\\envs\\glyphviz\\python.exe tools\\openxr_stereo_spike.py --csv tests\\golden\\scenes\\deep_hierarchy.csv --scale 0.03 --forward 3.0 --toe-deg 20.0

Defaults (--scale 1.0 --forward 15.0 --toe-deg 20.0) are the combo confirmed
on-headset 2026-06-18 to produce fully-overlapping, fusable stereo. Other
scale/forward combos will likely need a re-tuned --toe-deg.

Ctrl+C in the console (or exiting the app from the Quest dashboard) ends it.
"""
import argparse
import sys
import time
from math import radians
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from glyphviz_core.geometry_data import GEO_SPHERE
from glyphviz_core.node import NODE_TYPE_LINK, NON_VISUAL_TYPES
from glyphviz_core.scene import Scene, node_world_matrix
from glyphviz_gl.geometry import GeoRenderer


def _gl_col_major(M: np.ndarray) -> np.ndarray:
    """Row-major 4x4 -> flat column-major float32, for glLoadMatrixf/glMultMatrixf
    (mirrors glyphviz_gl.viewport._gl_col_major; duplicated to keep this
    diagnostic tool independent of the Qt-importing viewport module)."""
    return M.astype(np.float32).T.flatten()


def _toe_yaw_matrix(angle_rad: float) -> np.ndarray:
    """Extra yaw (around the local +Y/up axis) applied in eye space, for manual
    convergence tuning independent of whatever the runtime's own eye poses/FOV
    give us (see --toe-deg)."""
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    M = np.identity(4)
    M[0, 0] = c
    M[0, 2] = s
    M[2, 0] = -s
    M[2, 2] = c
    return M


def _view_matrix(pose, toe_rad: float = 0.0) -> np.ndarray:
    """Correct world-to-eye view matrix from an OpenXR pose.

    xr.utils.view_matrix_from_posef() has a bug: xr.utils.rotation_from_quaternionf()
    already returns the inverse (world-to-local) rotation, but view_matrix_from_posef
    transposes it *again* before use, embedding the forward (local-to-world) rotation
    in the view matrix instead. That makes the rendered scene rotate the same
    direction as the headset instead of counter-rotating. Built directly here from
    the (correctly inverse) rotation_from_quaternionf output, with no extra transpose.

    `toe_rad` adds a manual outward-toe yaw on top of the runtime-reported
    orientation (positive turns the view further toward +X in its own local
    frame) — a stopgap for dialing in convergence/overlap independent of
    whatever the runtime's per-eye FOV asymmetry is actually doing."""
    from xr.utils import rotation_from_quaternionf
    r_inv = np.asarray(rotation_from_quaternionf(pose.orientation), dtype=np.float64)
    position = np.array([pose.position.x, pose.position.y, pose.position.z])
    view = np.identity(4, dtype=np.float32)
    view[:3, :3] = r_inv
    view[:3, 3] = -(r_inv @ position)
    if toe_rad != 0.0:
        view = (_toe_yaw_matrix(toe_rad) @ view).astype(np.float32)
    return view


def _init_gl_state():
    """Mirrors glyphviz_gl.viewport.Viewport.initializeGL's fixed-function setup."""
    from OpenGL.GL import (
        glClearColor, glEnable, glLightfv,
        glColorMaterial, glShadeModel, glBlendFunc, glCullFace,
        GL_DEPTH_TEST, GL_LIGHTING, GL_LIGHT0, GL_DIFFUSE,
        GL_AMBIENT, GL_SPECULAR, GL_POSITION, GL_COLOR_MATERIAL,
        GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, GL_SMOOTH, GL_BLEND,
        GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_CULL_FACE, GL_BACK,
    )
    glClearColor(0.08, 0.08, 0.12, 1.0)
    glEnable(GL_DEPTH_TEST)
    # xr.utils.projection_from_fovf()'s docstring claims an "infinite
    # reverse-Z projection," which led to an earlier (wrong) fix here adding
    # glDepthFunc(GL_GREATER)/glClearDepth(0.0). Verified numerically
    # 2026-06-18: feeding real eye-space points through the actual matrix
    # this function returns gives depth-buffer values that *increase* with
    # distance (near=0.33, far=0.50 at z=-1m/-50m) — i.e. standard
    # near-is-small convention, the opposite of what the docstring claims.
    # The GL_GREATER fix was therefore backwards, telling GL to let farther
    # fragments win — exactly the "distant objects render in front of
    # closer ones" symptom reported on the SineWave scene. Plain GL
    # defaults (GL_LESS, clear-to-1.0, both implicit below) are correct.
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
    glEnable(GL_CULL_FACE)
    glCullFace(GL_BACK)


def _draw_scene(scene: Scene, geo: GeoRenderer, scale: float, forward: float, down: float):
    """Diorama-first placement: shrink the GlyphViz (Z-up) scene to roughly
    tabletop size, rotate Z-up into OpenXR's Y-up, and anchor it a fixed
    distance in front of / below wherever the LOCAL reference space origin
    is (i.e. where the headset was when Link/the app started) — not a
    room-scale, world-locked placement."""
    from OpenGL.GL import (
        glPushMatrix, glPopMatrix, glTranslatef, glRotatef, glScalef,
        glMultMatrixf, glColor4f,
    )
    glTranslatef(0.0, -down, -forward)
    glRotatef(-90.0, 1.0, 0.0, 0.0)  # GlyphViz +Z (up) -> OpenXR +Y (up)
    glScalef(scale, scale, scale)

    for node in scene.nodes:
        if node.type in NON_VISUAL_TYPES or node.type == NODE_TYPE_LINK:
            continue
        M = node_world_matrix(node, scene)
        glPushMatrix()
        glMultMatrixf(_gl_col_major(M))
        glColor4f(
            node.color_r / 255.0, node.color_g / 255.0,
            node.color_b / 255.0, node.color_a / 255.0,
        )
        # Textures/picking intentionally omitted from this spike.
        geo.draw(node.geometry, 1.0, 1.0, 1.0, ratio=node.ratio, gl_tex_name=0)
        glPopMatrix()


def _rig_inverse_matrix(nav_position: np.ndarray, nav_yaw: float) -> np.ndarray:
    """Inverse of Translate(nav_position) @ RotateY(nav_yaw) — the virtual
    "locomotion rig" transform accumulated from controller input. Multiplying
    this into MODELVIEW right after the (real, tracked) per-eye view matrix
    makes the world appear to move/turn as if the user's rig had moved by
    nav_position/nav_yaw, independent of their real physical position in the
    room. See ControllerNav for how nav_position/nav_yaw accumulate."""
    c, s = np.cos(-nav_yaw), np.sin(-nav_yaw)
    rot_inv = np.identity(4)
    rot_inv[0, 0] = c
    rot_inv[0, 2] = s
    rot_inv[2, 0] = -s
    rot_inv[2, 2] = c
    trans_inv = np.identity(4)
    trans_inv[:3, 3] = -nav_position
    return rot_inv @ trans_inv


def _draw_controller_marker(geo: GeoRenderer, position: np.ndarray, forward_dir: np.ndarray,
                             color: tuple[float, float, float]):
    """Small sphere at a controller's real (untransformed-by-nav) grip
    position, plus a thin pointing ray along its aim direction — drawn before
    the rig transform is applied, so these always show the controller's true
    physical position/orientation regardless of how far the user has
    virtually navigated."""
    from OpenGL.GL import (
        glPushMatrix, glPopMatrix, glTranslatef, glScalef, glColor4f,
        glBegin, glEnd, glVertex3f, glLineWidth, GL_LINES, glDisable, glEnable, GL_LIGHTING,
    )
    glPushMatrix()
    glTranslatef(float(position[0]), float(position[1]), float(position[2]))
    glColor4f(color[0], color[1], color[2], 1.0)
    glScalef(0.02, 0.02, 0.02)
    geo.draw(GEO_SPHERE, 1.0, 1.0, 1.0)
    glPopMatrix()

    ray_end = position + forward_dir * 0.5
    glDisable(GL_LIGHTING)
    glLineWidth(2.0)
    glColor4f(color[0], color[1], color[2], 1.0)
    glBegin(GL_LINES)
    glVertex3f(float(position[0]), float(position[1]), float(position[2]))
    glVertex3f(float(ray_end[0]), float(ray_end[1]), float(ray_end[2]))
    glEnd()
    glEnable(GL_LIGHTING)


class ControllerNav:
    """Quest Touch controller navigation via the OpenXR action system:
    thumbstick fly (left stick = move relative to real head-look direction,
    right stick = yaw turn + vertical) and grip-squeeze grab-drag (translate
    only, single-hand). Maintains nav_position/nav_yaw, the accumulated
    virtual offset consumed by _rig_inverse_matrix(); see that function's
    docstring for why a separate "rig" transform is needed at all instead of
    just moving the diorama's fixed placement."""

    TOUCH_CONTROLLER_PROFILE = "/interaction_profiles/oculus/touch_controller"
    MOVE_SPEED = 3.0       # m/s at full stick deflection
    TURN_SPEED = radians(90)  # rad/s at full stick deflection
    GRAB_ON_THRESHOLD = 0.6
    GRAB_OFF_THRESHOLD = 0.4

    def __init__(self, ctx):
        import xr
        self._xr = xr
        self.session = ctx.session
        self.base_space = ctx.space
        instance = ctx.instance
        session = ctx.session

        self.action_set = xr.create_action_set(
            instance, xr.ActionSetCreateInfo(
                action_set_name="navigation", localized_action_set_name="Navigation"))
        # ContextObject.frame_loop() does its own xr.attach_session_action_sets()
        # call (lazily, on first iteration) covering everything in
        # ctx.action_sets — OpenXR only allows one attach call per session
        # ever, so we register here instead of attaching separately ourselves.
        ctx.action_sets.append(self.action_set)
        self.hand_paths = {
            "left": xr.string_to_path(instance, "/user/hand/left"),
            "right": xr.string_to_path(instance, "/user/hand/right"),
        }
        sub_paths = list(self.hand_paths.values())

        self.grip_pose_action = xr.create_action(self.action_set, xr.ActionCreateInfo(
            action_name="grip_pose", localized_action_name="Grip Pose",
            action_type=xr.ActionType.POSE_INPUT,
            count_subaction_paths=len(sub_paths), subaction_paths=sub_paths))
        self.aim_pose_action = xr.create_action(self.action_set, xr.ActionCreateInfo(
            action_name="aim_pose", localized_action_name="Aim Pose",
            action_type=xr.ActionType.POSE_INPUT,
            count_subaction_paths=len(sub_paths), subaction_paths=sub_paths))
        self.thumbstick_action = xr.create_action(self.action_set, xr.ActionCreateInfo(
            action_name="thumbstick", localized_action_name="Thumbstick",
            action_type=xr.ActionType.VECTOR2F_INPUT,
            count_subaction_paths=len(sub_paths), subaction_paths=sub_paths))
        self.squeeze_action = xr.create_action(self.action_set, xr.ActionCreateInfo(
            action_name="squeeze", localized_action_name="Squeeze",
            action_type=xr.ActionType.FLOAT_INPUT,
            count_subaction_paths=len(sub_paths), subaction_paths=sub_paths))

        bindings = []
        for hand in self.hand_paths:
            bindings.append(xr.ActionSuggestedBinding(
                action=self.grip_pose_action,
                binding=xr.string_to_path(instance, f"/user/hand/{hand}/input/grip/pose")))
            bindings.append(xr.ActionSuggestedBinding(
                action=self.aim_pose_action,
                binding=xr.string_to_path(instance, f"/user/hand/{hand}/input/aim/pose")))
            bindings.append(xr.ActionSuggestedBinding(
                action=self.thumbstick_action,
                binding=xr.string_to_path(instance, f"/user/hand/{hand}/input/thumbstick")))
            bindings.append(xr.ActionSuggestedBinding(
                action=self.squeeze_action,
                binding=xr.string_to_path(instance, f"/user/hand/{hand}/input/squeeze/value")))
        xr.suggest_interaction_profile_bindings(instance, xr.InteractionProfileSuggestedBinding(
            interaction_profile=xr.string_to_path(instance, self.TOUCH_CONTROLLER_PROFILE),
            count_suggested_bindings=len(bindings), suggested_bindings=bindings))

        # Action spaces deferred to first update() call: some runtimes
        # require the owning action set to actually be attached first, which
        # (per the comment above) only happens once ctx.frame_loop() starts.
        self.grip_spaces = None
        self.aim_spaces = None

        self.nav_position = np.zeros(3)
        self.nav_yaw = 0.0
        self._grab_hand = None
        self._grab_anchor_grip_pos = None
        self._grab_anchor_nav_position = None
        self._last_time = time.perf_counter()
        self.controller_draws = []  # [(position, forward_dir, color), ...] for this frame

    def _thumbstick(self, hand):
        xr = self._xr
        state = xr.get_action_state_vector2f(self.session, xr.ActionStateGetInfo(
            action=self.thumbstick_action, subaction_path=self.hand_paths[hand]))
        return state.current_state.x, state.current_state.y

    def _squeeze(self, hand):
        xr = self._xr
        state = xr.get_action_state_float(self.session, xr.ActionStateGetInfo(
            action=self.squeeze_action, subaction_path=self.hand_paths[hand]))
        return state.current_state

    def _locate(self, space, display_time):
        xr = self._xr
        location = xr.locate_space(space, self.base_space, display_time)
        flags = location.location_flags
        if (flags & xr.SPACE_LOCATION_POSITION_VALID_BIT == 0
                or flags & xr.SPACE_LOCATION_ORIENTATION_VALID_BIT == 0):
            return None
        return location.pose

    def _grip_pose(self, hand, display_time):
        return self._locate(self.grip_spaces[hand], display_time)

    def _aim_pose(self, hand, display_time):
        return self._locate(self.aim_spaces[hand], display_time)

    def update(self, head_orientation, display_time):
        """Call once per real frame (not per eye). head_orientation is any
        eye's pose.orientation for that frame — both eyes share the same
        orientation (confirmed on-headset 2026-06-18), so either works for
        deriving the head-relative forward/right directions used by the
        left thumbstick."""
        xr = self._xr
        if self.grip_spaces is None:
            self.grip_spaces = {
                hand: xr.create_action_space(self.session, xr.ActionSpaceCreateInfo(
                    action=self.grip_pose_action, subaction_path=path))
                for hand, path in self.hand_paths.items()
            }
            self.aim_spaces = {
                hand: xr.create_action_space(self.session, xr.ActionSpaceCreateInfo(
                    action=self.aim_pose_action, subaction_path=path))
                for hand, path in self.hand_paths.items()
            }
        xr.sync_actions(self.session, xr.ActionsSyncInfo(
            count_active_action_sets=1,
            active_action_sets=[xr.ActiveActionSet(action_set=self.action_set,
                                                    subaction_path=xr.NULL_PATH)]))

        now = time.perf_counter()
        dt = now - self._last_time
        self._last_time = now

        from xr.utils import rotation_from_quaternionf
        r_inv = np.asarray(rotation_from_quaternionf(head_orientation), dtype=np.float64)
        r_fwd = r_inv.T
        forward = r_fwd @ np.array([0.0, 0.0, -1.0])
        right = r_fwd @ np.array([1.0, 0.0, 0.0])
        forward[1] = 0.0
        right[1] = 0.0
        forward = forward / max(np.linalg.norm(forward), 1e-6)
        right = right / max(np.linalg.norm(right), 1e-6)

        grip_poses = {}
        for hand in self.hand_paths:
            pose = self._grip_pose(hand, display_time)
            if pose is not None:
                grip_poses[hand] = pose

        # Grab-drag takes over from whichever hand is squeezing past the
        # threshold; thumbstick fly is suppressed for that hand while held
        # rather than fighting it for control of nav_position.
        for hand in self.hand_paths:
            squeeze = self._squeeze(hand)
            pose = grip_poses.get(hand)
            if pose is None:
                continue
            grip_pos = np.array([pose.position.x, pose.position.y, pose.position.z])
            if self._grab_hand is None and squeeze > self.GRAB_ON_THRESHOLD:
                self._grab_hand = hand
                self._grab_anchor_grip_pos = grip_pos
                self._grab_anchor_nav_position = self.nav_position.copy()
            elif self._grab_hand == hand and squeeze < self.GRAB_OFF_THRESHOLD:
                self._grab_hand = None
            elif self._grab_hand == hand:
                delta = grip_pos - self._grab_anchor_grip_pos
                self.nav_position = self._grab_anchor_nav_position - delta

        if self._grab_hand is None:
            lx, ly = self._thumbstick("left")
            rx, ry = self._thumbstick("right")
            self.nav_position = self.nav_position + (right * lx + forward * ly) * self.MOVE_SPEED * dt
            self.nav_position[1] += ry * self.MOVE_SPEED * dt
            self.nav_yaw += -rx * self.TURN_SPEED * dt

        self.controller_draws = []
        for hand, pose in grip_poses.items():
            pos = np.array([pose.position.x, pose.position.y, pose.position.z])
            # Ray direction comes from the *aim* pose, not grip: grip's local
            # -Z axis is oriented for holding the controller, not for where
            # it visually points — using it for the ray made the line
            # segment point up instead of forward (confirmed on-headset
            # 2026-06-18). Aim pose is OpenXR's purpose-built pointing pose.
            aim_pose = self._aim_pose(hand, display_time)
            ray_pose = aim_pose if aim_pose is not None else pose
            r_inv_hand = np.asarray(rotation_from_quaternionf(ray_pose.orientation), dtype=np.float64)
            hand_forward = r_inv_hand.T @ np.array([0.0, 0.0, -1.0])
            color = (0.2, 0.8, 1.0) if hand == "left" else (1.0, 0.6, 0.2)
            self.controller_draws.append((pos, hand_forward, color))

    def rig_inverse(self) -> np.ndarray:
        return _rig_inverse_matrix(self.nav_position, self.nav_yaw)

    def draw_controllers(self, geo: GeoRenderer):
        for position, forward_dir, color in self.controller_draws:
            _draw_controller_marker(geo, position, forward_dir, color)


def _view_loop_output_swapped(ctx, frame_state, swap_eyes: bool):
    """Drop-in replacement for xr.utils.gl.ContextObject.view_loop that
    routes each view's (pose, fov, rendered content) — kept self-consistent
    as a triple — to a physical swapchain slot. `swap_eyes` controls whether
    that slot is the view's own (normal) or the other one.

    A previous session observed the physical eyes seeing each other's image
    and added the swap as a fix, on the theory it was a swapchain-routing
    quirk independent of the view-matrix bugs fixed in that same session.
    It's since looking like that symptom may have been a side effect of
    those (now-fixed) matrix bugs, and the swap itself is what's now causing
    divergent/un-fusable stereo — hence making it a runtime-toggleable flag
    instead of baking in either assumption."""
    import xr
    from ctypes import byref, cast, POINTER

    if not frame_state.should_render:
        return
    layer = xr.CompositionLayerProjection(space=ctx.space)
    view_state, views = xr.locate_views(
        session=ctx.session,
        view_locate_info=xr.ViewLocateInfo(
            view_configuration_type=ctx.view_configuration_type,
            display_time=frame_state.predicted_display_time,
            space=ctx.space,
        ),
    )
    num_views = len(views)
    projection_layer_views = tuple(xr.CompositionLayerProjectionView() for _ in range(num_views))

    vsf = view_state.view_state_flags
    if (vsf & xr.VIEW_STATE_POSITION_VALID_BIT == 0
            or vsf & xr.VIEW_STATE_ORIENTATION_VALID_BIT == 0):
        return
    for view_index, view in enumerate(views):
        output_index = (num_views - 1 - view_index) if swap_eyes else view_index
        view_swapchain = ctx.swapchains[output_index]
        swapchain_image_index = xr.acquire_swapchain_image(
            swapchain=view_swapchain.handle,
            acquire_info=xr.SwapchainImageAcquireInfo(),
        )
        xr.wait_swapchain_image(
            swapchain=view_swapchain.handle,
            wait_info=xr.SwapchainImageWaitInfo(timeout=xr.INFINITE_DURATION),
        )
        layer_view = projection_layer_views[output_index]
        layer_view.pose = view.pose
        layer_view.fov = view.fov
        layer_view.sub_image.swapchain = view_swapchain.handle
        layer_view.sub_image.image_rect.offset[:] = [0, 0]
        layer_view.sub_image.image_rect.extent[:] = [
            view_swapchain.width, view_swapchain.height, ]
        swapchain_image_ptr = ctx.swapchain_image_ptr_buffers[output_index][swapchain_image_index]
        swapchain_image = cast(swapchain_image_ptr, POINTER(xr.SwapchainImageOpenGLKHR)).contents
        color_texture = swapchain_image.image
        ctx.graphics.begin_frame(layer_view, color_texture)

        yield view

        ctx.graphics.end_frame()
        xr.release_swapchain_image(
            swapchain=view_swapchain.handle,
            release_info=xr.SwapchainImageReleaseInfo(),
        )
    layer.views = projection_layer_views
    ctx.render_layers.append(byref(layer))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv", default=str(REPO_ROOT / "tests" / "golden" / "scenes" / "topo2_sphere.csv"),
        help="Node CSV to load (default: a small bundled golden-master fixture).",
    )
    parser.add_argument("--base-scale", type=float, default=3.0,
                         help="Scene base_scale, matches the golden-master default.")
    parser.add_argument("--scale", type=float, default=1.0,
                         help="Shrink factor from GlyphViz world units to meters.")
    parser.add_argument("--forward", type=float, default=15.0,
                         help="Meters in front of the LOCAL space origin.")
    parser.add_argument("--down", type=float, default=0.35,
                         help="Meters below the LOCAL space origin.")
    parser.add_argument("--no-swap-eyes", dest="swap_eyes", action="store_false",
                         help="Disable the output-slot eye swap (default: on). Confirmed "
                              "2026-06-18 still necessary: disabling it reproduces the "
                              "original 'physical eyes see each other's image' symptom.")
    parser.add_argument("--toe-deg", type=float, default=20.0,
                         help="Manual outward-toe yaw per eye, in degrees (each eye's view "
                              "rotates further away from center by this much). Stopgap for "
                              "tuning stereo overlap by hand. 20.0 confirmed on-headset "
                              "2026-06-18 at --scale 1.0 --forward 15.0 to fully fix a "
                              "no-overlap/unfusable stereo image; root cause of why this "
                              "much correction is needed is not yet understood.")
    args = parser.parse_args()

    try:
        import xr
        import glfw
        from xr.utils import GraphicsContextProvider
        from xr.utils.gl import ContextObject
    except ImportError as e:
        print(
            f"Missing dependency ({e}). Run:\n"
            "  C:\\Users\\jsale\\anaconda3\\envs\\glyphviz\\python.exe -m pip install -r requirements-xr.txt"
        )
        return 1

    scene = Scene.load(args.csv, base_scale=args.base_scale)
    print(f"Loaded {len(scene.nodes)} nodes from {args.csv}")

    class _CompatGLContextProvider(GraphicsContextProvider):
        """Hidden GLFW window/context with NO core-profile hint: GeoRenderer
        relies on fixed-function GL (display lists, glBegin/End, GLU
        quadrics), which requires a compatibility-profile context."""

        def __init__(self):
            if not glfw.init():
                raise RuntimeError("Failed to initialize GLFW")
            glfw.window_hint(glfw.VISIBLE, False)
            glfw.window_hint(glfw.DOUBLEBUFFER, False)
            self._window = glfw.create_window(1, 1, "", None, None)
            if self._window is None:
                glfw.terminate()
                raise RuntimeError("Failed to create hidden GLFW window")
            glfw.make_context_current(self._window)
            glfw.swap_interval(0)

        def make_current(self) -> None:
            glfw.make_context_current(self._window)

        def done_current(self) -> None:
            glfw.make_context_current(None)

        def destroy(self) -> None:
            if self._window is not None:
                glfw.destroy_window(self._window)
                glfw.terminate()
                self._window = None

    instance_create_info = xr.InstanceCreateInfo(
        application_info=xr.ApplicationInfo(
            application_name="GlyphViz VR Stereo Spike",
            application_version=1,
            engine_name="GlyphViz",
            engine_version=1,
            api_version=xr.XR_CURRENT_API_VERSION,
        ),
        enabled_extension_names=[xr.KHR_OPENGL_ENABLE_EXTENSION_NAME],
    )
    reference_space_create_info = xr.ReferenceSpaceCreateInfo(
        reference_space_type=xr.ReferenceSpaceType.LOCAL,
    )

    print("Creating OpenXR session (put the headset on if you haven't)...")
    try:
        with ContextObject(
            context_provider=_CompatGLContextProvider(),
            instance_create_info=instance_create_info,
            reference_space_create_info=reference_space_create_info,
        ) as ctx:
            geo = GeoRenderer()
            ctx.graphics.make_current()
            geo.setup()
            _init_gl_state()
            nav = ControllerNav(ctx)
            print("Session created. Rendering — Ctrl+C here (or exit from the "
                  "Quest dashboard) to stop.")

            from OpenGL.GL import (
                glMatrixMode, glLoadIdentity, glLoadMatrixf, glClear, glMultMatrixf,
                GL_PROJECTION, GL_MODELVIEW, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,
            )
            from xr.utils import projection_from_fovf

            frame_count = 0
            logged_first_frame = False
            for frame_state in ctx.frame_loop():
                for eye_index, view in enumerate(_view_loop_output_swapped(ctx, frame_state, args.swap_eyes)):
                    if not logged_first_frame:
                        p = view.pose.position
                        o = view.pose.orientation
                        f = view.fov
                        print(f"[first-render eye{eye_index}] pos=({p.x:.4f},{p.y:.4f},{p.z:.4f}) "
                              f"orient=({o.x:.4f},{o.y:.4f},{o.z:.4f},{o.w:.4f}) "
                              f"fov(l,r,u,d)=({f.angle_left:.4f},{f.angle_right:.4f},"
                              f"{f.angle_up:.4f},{f.angle_down:.4f})", flush=True)
                        if eye_index == 1:
                            logged_first_frame = True
                    if eye_index == 0:
                        # Once per frame, not once per eye — see ControllerNav.update.
                        nav.update(view.pose.orientation, frame_state.predicted_display_time)
                    glMatrixMode(GL_PROJECTION)
                    glLoadMatrixf(np.asarray(projection_from_fovf(view.fov), dtype=np.float32).flatten())
                    glMatrixMode(GL_MODELVIEW)
                    # eye_index 0 is the left eye (confirmed via its FOV being
                    # wider on the left/outward side) — toe each eye outward
                    # (left eye further left, right eye further right) by
                    # --toe-deg; see _view_matrix's docstring for the sign math.
                    toe_sign = 1.0 if eye_index == 0 else -1.0
                    toe_rad = toe_sign * radians(args.toe_deg)
                    glLoadMatrixf(_gl_col_major(_view_matrix(view.pose, toe_rad)))
                    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                    # Re-assert every frame, not just once before the loop:
                    # the same class of bug fixed in glyphviz_gl/viewport.py's
                    # paintGL() (commit 5f16dbf) — some geometry/draw path
                    # (not yet isolated; the small test scene never triggers
                    # it, the larger SineWave scene does) leaves GL_DEPTH_TEST
                    # and/or GL_CULL_FACE state clobbered, breaking depth
                    # ordering and backface culling for the rest of the
                    # session once that path runs once.
                    _init_gl_state()
                    # Controllers are drawn at their real tracked position,
                    # before the virtual-navigation rig transform is applied —
                    # your hands should never appear to drift as you fly/drag.
                    nav.draw_controllers(geo)
                    glMultMatrixf(_gl_col_major(nav.rig_inverse()))
                    _draw_scene(scene, geo, args.scale, args.forward, args.down)
                frame_count += 1
                if frame_count % 300 == 0:
                    print(f"...{frame_count} frames rendered")
    except KeyboardInterrupt:
        print("\nStopped by Ctrl+C.")
        return 0
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
