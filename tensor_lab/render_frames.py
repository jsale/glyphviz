"""
Render Channels frames of a scene through the real Viewport, headless: each
frame is what MainWindow does per tick (apply_frame + channel_frame_update)
followed by a paint, saved as a PNG. The camera is the one the app opens
with (auto-framed, azimuth 45, elevation 25) unless overridden.

    python render_frames.py SCENE_NODE_CSV --frames 0 400 900 --out DIR
        [--width 1600 --height 1000] [--azimuth A --elevation E --distance D --target X Y Z]
    python render_frames.py SCENE_NODE_CSV --time 120      # playback timing only

An offscreen paint is a proxy for the app's on-screen frame rate, but it runs
the same draw code.
"""
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import export_frame  # noqa: E402  (sets the headless DPR env before Qt loads)
from PySide6.QtWidgets import QApplication  # noqa: E402

from glyphviz_core.channel_engine import ChannelEngine  # noqa: E402
from glyphviz_core.channel_loader import (find_channel_files, load_ch_map,  # noqa: E402
                                          load_ch_tracks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--frames", type=int, nargs="+", default=[0])
    ap.add_argument("--out")
    ap.add_argument("--time", type=int, default=0, help="time this many frames, no PNGs")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=1000)
    ap.add_argument("--azimuth", type=float)
    ap.add_argument("--elevation", type=float)
    ap.add_argument("--distance", type=float)
    ap.add_argument("--target", type=float, nargs=3)
    args = ap.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    vp, nodes, _tex, _media = export_frame._build_viewport(
        args.csv, 1.0, False, False, False, None, args.width, args.height)
    if args.azimuth is not None:
        vp._cam_azimuth = args.azimuth
    if args.elevation is not None:
        vp._cam_elevation = args.elevation
    if args.distance is not None:
        vp._cam_distance = args.distance
    if args.target is not None:
        vp._cam_target = list(args.target)
    vp._snap_camera_goal()
    map_path, tracks_path = find_channel_files(args.csv)
    eng = ChannelEngine()
    tracks, id_to_col = load_ch_tracks(tracks_path)
    eng.load(load_ch_map(map_path), tracks, id_to_col, nodes)
    vp.set_channel_dynamic_nodes(eng.bound_node_ids, eng.transform_bound_node_ids)
    if args.time:
        vp.grabFramebuffer()
        times = []
        for f in range(300, 300 + args.time):
            t = time.perf_counter()
            eng.apply_frame(f)
            vp.channel_frame_update()
            vp.grabFramebuffer()
            times.append(time.perf_counter() - t)
        times.sort()
        med = times[len(times) // 2] * 1000
        print(f"{Path(args.csv).name}: {len(nodes)} nodes; per frame median {med:.1f} ms, "
              f"p90 {times[int(len(times) * 0.9)] * 1000:.1f} ms (~{1000 / med:.0f} fps)")
        return
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(args.csv).name.replace("_gv_node.csv", "")
    vp.grabFramebuffer()
    for f in args.frames:
        eng.apply_frame(f)
        vp.channel_frame_update()
        img = vp.grabFramebuffer()
        path = out / f"{stem}_f{f:04d}.png"
        img.save(str(path))
        print(path)


if __name__ == "__main__":
    main()
