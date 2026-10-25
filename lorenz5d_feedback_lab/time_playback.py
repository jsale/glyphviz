"""
Time Channels playback of this lab's scenes through the real Viewport,
headless: each step is what MainWindow does per tick (apply_frame +
channel_frame_update) plus a full paint via grabFramebuffer().

    python time_playback.py [--scene cells|tower|loop] [--frames 120]

An offscreen paint is a proxy, not the app's on-screen frame rate, but it
exercises the same draw code (the four animated heat-map Surfaces re-emitted
every frame, everything static replayed from display lists).
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

SCENES = {"cells": HERE / "Convection_Cells" / "Convection_Cells_gv_node.csv",
          "tower": HERE / "R_Sweep_Tower" / "R_Sweep_Tower_gv_node.csv",
          "loop": HERE / "Feedback_Loop" / "Feedback_Loop_gv_node.csv"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", choices=sorted(SCENES), default="cells")
    ap.add_argument("--frames", type=int, default=120)
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=1000)
    args = ap.parse_args()
    scene = SCENES[args.scene]

    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    t0 = time.perf_counter()
    vp, nodes, _tex, _media = export_frame._build_viewport(
        str(scene), 1.0, False, False, False, None, args.width, args.height)
    map_path, tracks_path = find_channel_files(str(scene))
    eng = ChannelEngine()
    tracks, id_to_col = load_ch_tracks(tracks_path)
    eng.load(load_ch_map(map_path), tracks, id_to_col, nodes)
    vp.set_channel_dynamic_nodes(eng.bound_node_ids, eng.transform_bound_node_ids)
    print(f"{scene.name}: load + viewport setup {time.perf_counter() - t0:.1f} s, "
          f"{len(nodes)} nodes")

    start = 600
    vp.grabFramebuffer()              # first paint compiles the display lists
    times = []
    for f in range(start, start + args.frames):
        t = time.perf_counter()
        eng.apply_frame(f)
        vp.channel_frame_update()
        vp.grabFramebuffer()
        times.append(time.perf_counter() - t)
    times.sort()
    med = times[len(times) // 2] * 1000
    p90 = times[int(len(times) * 0.9)] * 1000
    print(f"per frame: median {med:.1f} ms, p90 {p90:.1f} ms  (~{1000 / med:.0f} fps median)")


if __name__ == "__main__":
    main()
