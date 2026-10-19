"""Render GlyphViz frames of a channel-animated scene, headlessly (glyphviz env).

    python gv_frames.py <scene_dir> <out_prefix> <frame> [frame ...]
        [--az 0 --el 0 --dist D --target X Y Z --w 1280 --h 720]

Poses the nodes with the app's own ChannelEngine exactly as the Channels panel
does (engine.load -> apply_frame -> viewport.channel_frame_update), then grabs
the real Viewport.  export_frame.py has no frame argument, hence this.
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO))

import export_frame as EF                                           # noqa: E402  (sets Qt env)
from PySide6.QtWidgets import QApplication                          # noqa: E402
from glyphviz_core.channel_engine import ChannelEngine              # noqa: E402
from glyphviz_core.channel_loader import (                          # noqa: E402
    find_channel_files, load_ch_map, load_ch_tracks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene_dir")
    ap.add_argument("out_prefix")
    ap.add_argument("frames", type=int, nargs="+")
    ap.add_argument("--az", type=float, default=0.0)
    ap.add_argument("--el", type=float, default=0.0)
    ap.add_argument("--dist", type=float, default=None)
    ap.add_argument("--target", type=float, nargs=3, default=None)
    ap.add_argument("--w", type=int, default=1280)
    ap.add_argument("--h", type=int, default=720)
    ap.add_argument("--grid", action="store_true")
    a = ap.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)         # noqa: F841
    csv = str(next(Path(a.scene_dir).glob("*_gv_node.csv")))
    vp, nodes, _t, _m = EF._build_viewport(csv, 1.0, a.grid, False, False, None, a.w, a.h)

    mp, tp = find_channel_files(csv)
    eng = ChannelEngine()
    ch_map = load_ch_map(mp)
    tracks, id_to_col = load_ch_tracks(tp)
    eng.load(ch_map, tracks, id_to_col, nodes)
    vp.set_channel_dynamic_nodes(eng.bound_node_ids, eng.transform_bound_node_ids)
    vp.scene_invalidate()

    for f in a.frames:
        eng.apply_frame(f)
        vp.channel_frame_update()
        vp.set_camera(azimuth=a.az, elevation=a.el, distance=a.dist,
                      target=tuple(a.target) if a.target else None)
        out = "%s_%03d.png" % (a.out_prefix, f)
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        vp.export_png(out, a.w, a.h)
        print("wrote", out)


if __name__ == "__main__":
    main()
