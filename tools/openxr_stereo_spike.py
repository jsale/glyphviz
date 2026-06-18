"""
OpenXR stereo rendering spike — renders a real GlyphViz scene to the Quest 3
as a tabletop diorama, reusing the existing kernel/renderer unchanged:
glyphviz_core.scene.node_world_matrix() supplies each node's transform and
glyphviz_gl.geometry.GeoRenderer draws it, exactly as glyphviz_gl.viewport
does on the desktop — only the camera (now per-eye, from the runtime) and
the output target (a swapchain framebuffer per eye, not a QOpenGLWidget) are
different.

This is a throwaway diagnostic, not the start of a "glyphviz_xr" package:
no picking, no textures, no controller input, one fixed-direction light.
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
from math import radians
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

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
        glClearColor, glClearDepth, glDepthFunc, glEnable, glLightfv,
        glColorMaterial, glShadeModel, glBlendFunc, glCullFace,
        GL_DEPTH_TEST, GL_GREATER, GL_LIGHTING, GL_LIGHT0, GL_DIFFUSE,
        GL_AMBIENT, GL_SPECULAR, GL_POSITION, GL_COLOR_MATERIAL,
        GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, GL_SMOOTH, GL_BLEND,
        GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_CULL_FACE, GL_BACK,
    )
    glClearColor(0.08, 0.08, 0.12, 1.0)
    glEnable(GL_DEPTH_TEST)
    # xr.utils.projection_from_fovf() defaults to an infinite reverse-Z
    # projection (near maps to 1, far to 0) — the GL_LESS/clear-to-1.0
    # defaults assume the opposite convention and make depth testing a
    # near-no-op, letting draw order rather than real depth decide
    # occlusion.
    glDepthFunc(GL_GREATER)
    glClearDepth(0.0)
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
            print("Session created. Rendering — Ctrl+C here (or exit from the "
                  "Quest dashboard) to stop.")

            from OpenGL.GL import (
                glMatrixMode, glLoadIdentity, glLoadMatrixf, glClear,
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
