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
    C:\\Users\\jsale\\anaconda3\\envs\\glyphviz\\python.exe tools\\openxr_stereo_spike.py --csv examples\\SineWave_Example\\SineWave_Example_np_node.csv

--scale defaults to auto (scaled from the loaded scene's own bounding box —
see --target-size), so any --csv file should just work without per-file
tuning. --forward 15.0 and --toe-deg 20.0 are the combo confirmed
on-headset 2026-06-18 to produce fully-overlapping, fusable stereo, and
held across very different --scale values (1.0 and 0.05) at that same
--forward — toe correction appears tied to viewing distance, not scale.
Pass --scale explicitly to override auto-sizing.

Controllers: left thumbstick flies relative to head-look direction, right
thumbstick turns/moves vertically, grip-squeeze grab-drags the world, and
the trigger picks whatever the pointing ray hits (highlighted with a yellow
wireframe box).

If a companion np_ch-map.csv/np_ch-tracks.csv is found next to --csv, channel
animation auto-plays and loops from the moment the session starts (no
in-headset playback controls yet — see --ch-fps). If a texture-driven
channel (attribute=texture_id) is present, textures are loaded from
--images-folder, or auto-detected at usr/images next to --csv.

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

from glyphviz_core.channel_engine import ChannelEngine
from glyphviz_core.channel_loader import find_channel_files, load_ch_map, load_ch_tracks
from glyphviz_core.scene import Scene
from glyphviz_gl.geometry import GeoRenderer
from glyphviz_gl.texture_manager import TextureManager
from glyphviz_xr.controller_nav import ControllerNav
from glyphviz_xr.render import draw_scene, init_gl_state
from glyphviz_xr.scene_fit import auto_scale_for_scene
from glyphviz_xr.session import make_compat_gl_context_provider, view_loop_output_swapped
from glyphviz_xr.transforms import diorama_transform_matrix, gl_col_major, view_matrix


def _load_channel_engine(csv_path: str, nodes) -> ChannelEngine | None:
    """Auto-detect and load companion np_ch-map.csv/np_ch-tracks.csv, if any.
    Mirrors glyphviz_gl.main_window._ch_load_from_csv (desktop), minus the UI."""
    map_path, tracks_path = find_channel_files(csv_path)
    if not map_path or not tracks_path:
        return None
    try:
        ch_map = load_ch_map(map_path)
        tracks, id_to_col = load_ch_tracks(tracks_path)
        engine = ChannelEngine()
        engine.load(ch_map, tracks, id_to_col, nodes)
        if engine.frame_count == 0 or not engine.has_bindings:
            return None
        print(f"Loaded channel animation: {engine.frame_count} frames "
              f"(auto-playing at --ch-fps, looping)")
        return engine
    except Exception as exc:
        print(f"Channel load warning: {exc}")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv", default=str(REPO_ROOT / "tests" / "golden" / "scenes" / "topo2_sphere.csv"),
        help="Node CSV to load (default: a small bundled golden-master fixture).",
    )
    parser.add_argument("--base-scale", type=float, default=3.0,
                         help="Scene base_scale, matches the golden-master default.")
    parser.add_argument("--scale", type=float, default=None,
                         help="Shrink factor from GlyphViz world units to meters. Default: "
                              "auto-computed from the loaded scene's bounding box (see "
                              "--target-size), so any --csv file just works without per-file "
                              "tuning.")
    parser.add_argument("--target-size", type=float, default=20.0,
                         help="Meters the auto-computed --scale should map the scene's "
                              "largest bounding-box dimension to. Ignored if --scale is given.")
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
    parser.add_argument("--images-folder", default=None,
                         help="Folder of images for texture_id (1-based, alphabetical), e.g. "
                              "a usr/images/ dir of mapNNNNN.jpg files. Default: auto-detect "
                              "'usr/images' next to --csv (matches the example layout under "
                              "examples/*/usr/images). No textures are loaded if neither is "
                              "found, and any texture-driven channel animation just has no "
                              "visible effect.")
    parser.add_argument("--ch-fps", type=float, default=30.0,
                         help="Channel animation playback speed in frames per second, if a "
                              "companion np_ch-map.csv/np_ch-tracks.csv is found next to "
                              "--csv. Playback auto-starts and loops; there's no in-headset "
                              "control for it yet.")
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

    ch_engine = _load_channel_engine(args.csv, scene.nodes)

    images_folder = (
        Path(args.images_folder) if args.images_folder
        else Path(args.csv).resolve().parent / "usr" / "images"
    )

    if args.scale is None:
        args.scale = auto_scale_for_scene(scene, args.target_size)
        print(f"Auto-scale: {args.scale:.5f} (largest dimension -> "
              f"~{args.target_size:.0f}m; pass --scale to override)")

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

            tex_mgr = TextureManager()
            if images_folder.is_dir():
                tex_count = tex_mgr.load_folder(images_folder)
                print(f"Loaded {tex_count} texture(s) from {images_folder}")
            elif args.images_folder:
                print(f"--images-folder not found: {images_folder}")

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
            ch_frame = 0
            ch_accum = 0.0
            ch_last_time = time.perf_counter()
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
                        if ch_engine is not None:
                            now = time.perf_counter()
                            ch_accum += now - ch_last_time
                            ch_last_time = now
                            step = 1.0 / args.ch_fps
                            while ch_accum >= step:
                                ch_accum -= step
                                ch_frame = (ch_frame + 1) % ch_engine.frame_count
                            ch_engine.apply_frame(ch_frame)
                            scene.invalidate()
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
                               selected_node=nav.selected_node, tex_mgr=tex_mgr)
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
