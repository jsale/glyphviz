"""
OpenXR stereo rendering CLI — renders a real GlyphViz scene to the Quest 3
as a tabletop diorama, reusing the existing kernel/renderer unchanged:
glyphviz_core.scene.node_world_matrix() supplies each node's transform and
glyphviz_gl.geometry.GeoRenderer draws it, exactly as glyphviz_gl.viewport
does on the desktop — only the camera (now per-eye, from the runtime) and
the output target (a swapchain framebuffer per eye, not a QOpenGLWidget) are
different.

Thin wiring layer only — the actual implementation (transforms, GL drawing,
controller navigation/picking, session/swapchain plumbing) lives in the
glyphviz_xr package. Run with the Quest 3 connected and Link active (see
tools/openxr_probe.py to confirm that part works first).

Usage:
    C:\\Users\\jsale\\anaconda3\\envs\\glyphviz\\python.exe tools\\openxr_stereo_spike.py
    C:\\Users\\jsale\\anaconda3\\envs\\glyphviz\\python.exe tools\\openxr_stereo_spike.py --csv tests\\golden\\scenes\\deep_hierarchy.csv --scale 0.03 --forward 3.0 --toe-deg 20.0

Defaults (--scale 1.0 --forward 15.0 --toe-deg 20.0) are the combo confirmed
on-headset 2026-06-18 to produce fully-overlapping, fusable stereo. Other
scale/forward combos will likely need a re-tuned --toe-deg.

Controllers: left thumbstick flies relative to head-look direction, right
thumbstick turns/moves vertically, grip-squeeze grab-drags the world, and
the trigger picks whatever the pointing ray hits (highlighted with a yellow
wireframe box).

Ctrl+C in the console (or exiting the app from the Quest dashboard) ends it.
"""
import argparse
import sys
from math import radians
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from glyphviz_core.scene import Scene
from glyphviz_gl.geometry import GeoRenderer
from glyphviz_xr.controller_nav import ControllerNav
from glyphviz_xr.render import draw_scene, init_gl_state
from glyphviz_xr.session import make_compat_gl_context_provider, view_loop_output_swapped
from glyphviz_xr.transforms import diorama_transform_matrix, gl_col_major, view_matrix


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
        from xr.utils.gl import ContextObject
    except ImportError as e:
        print(
            f"Missing dependency ({e}). Run:\n"
            "  C:\\Users\\jsale\\anaconda3\\envs\\glyphviz\\python.exe -m pip install -r requirements-xr.txt"
        )
        return 1

    scene = Scene.load(args.csv, base_scale=args.base_scale)
    print(f"Loaded {len(scene.nodes)} nodes from {args.csv}")

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
            context_provider=make_compat_gl_context_provider(glfw),
            instance_create_info=instance_create_info,
            reference_space_create_info=reference_space_create_info,
        ) as ctx:
            geo = GeoRenderer()
            ctx.graphics.make_current()
            geo.setup()
            init_gl_state()
            nav = ControllerNav(ctx)
            diorama_transform = diorama_transform_matrix(args.scale, args.forward, args.down)
            print("Session created. Rendering — Ctrl+C here (or exit from the "
                  "Quest dashboard) to stop.")

            from OpenGL.GL import (
                glMatrixMode, glLoadMatrixf, glClear, glMultMatrixf,
                GL_PROJECTION, GL_MODELVIEW, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,
            )
            from xr.utils import projection_from_fovf

            frame_count = 0
            logged_first_frame = False
            for frame_state in ctx.frame_loop():
                for eye_index, view in enumerate(view_loop_output_swapped(ctx, frame_state, args.swap_eyes)):
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
                        nav.update(view.pose.orientation, frame_state.predicted_display_time,
                                   scene, diorama_transform, args.scale)
                    glMatrixMode(GL_PROJECTION)
                    glLoadMatrixf(np.asarray(projection_from_fovf(view.fov), dtype=np.float32).flatten())
                    glMatrixMode(GL_MODELVIEW)
                    # eye_index 0 is the left eye (confirmed via its FOV being
                    # wider on the left/outward side) — toe each eye outward
                    # (left eye further left, right eye further right) by
                    # --toe-deg; see transforms.view_matrix's docstring for
                    # the sign math.
                    toe_sign = 1.0 if eye_index == 0 else -1.0
                    toe_rad = toe_sign * radians(args.toe_deg)
                    glLoadMatrixf(gl_col_major(view_matrix(view.pose, toe_rad)))
                    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                    # Re-asserted every frame rather than once before the loop
                    # as cheap insurance against any future GL-state-clobbering
                    # draw path (the actual cause of the depth/cull symptom
                    # seen on the SineWave scene turned out to be a backwards
                    # depth-func fix, not state loss — see render.init_gl_state).
                    init_gl_state()
                    # Controllers are drawn at their real tracked position,
                    # before the virtual-navigation rig transform is applied —
                    # your hands should never appear to drift as you fly/drag.
                    nav.draw_controllers(geo)
                    glMultMatrixf(gl_col_major(nav.rig_inverse()))
                    draw_scene(scene, geo, args.scale, args.forward, args.down,
                               selected_node=nav.selected_node)
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
