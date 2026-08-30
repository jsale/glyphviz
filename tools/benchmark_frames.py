#!/usr/bin/env python3
"""
benchmark_frames.py
===================
Measure GlyphViz's frame rendering time for a node CSV, headlessly — the
repeatable benchmark used for tracking rendering-performance work and for
side-by-side comparisons against ANTz on the same files.

Renders N frames via the real Viewport (same code path as the desktop app)
and reports ms/frame and fps. Camera framing defaults to the same
bounding-box auto-fit the app uses on load.

IMPORTANT — comparing against ANTz or on-screen GlyphViz: each headless
frame here includes a synchronous grabFramebuffer() readback (GPU -> CPU
copy of the full frame) that interactive vsync'd rendering does not do, so
absolute numbers are pessimistic. Relative changes between GlyphViz builds
on the same machine are what this tool is for; for an ANTz comparison,
prefer each app's own on-screen FPS counter on the same file and machine
(GlyphViz emits one via Viewport.fpsUpdated, shown in the status bar).

Usage:
    python tools/benchmark_frames.py --csv path/to/scene_node.csv
    python tools/benchmark_frames.py --csv scene_node.csv --frames 30 \
        --width 1280 --height 720 --no-tags --stereo
"""
import argparse
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtWidgets import QApplication

from glyphviz_core.csv_reader import load_node_csv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, help="Node CSV to load.")
    parser.add_argument("--frames", type=int, default=30, help="Timed frames (default 30).")
    parser.add_argument("--warmup", type=int, default=3,
                        help="Untimed warm-up frames for display-list/texture compilation (default 3).")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--base-scale", type=float, default=1.0)
    parser.add_argument("--no-tags", dest="show_tags", action="store_false")
    parser.add_argument("--no-grid", dest="show_grid", action="store_false")
    parser.add_argument("--no-axes", dest="show_axes", action="store_false")
    parser.add_argument("--stereo", action="store_true", help="Benchmark the cross-eye stereo path.")
    parser.add_argument("--draw-limit", type=int, default=None,
                        help="Cap visible nodes like the \\ key does (default: draw everything).")
    parser.add_argument("--media-folder", default=None,
                        help="Folder of images/videos for texture_id. Default: 'media' next to --csv.")
    args = parser.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)
    from glyphviz_gl.viewport import Viewport   # deferred: needs QApplication first

    nodes = load_node_csv(args.csv)
    vp = Viewport()
    vp.base_scale = args.base_scale
    vp.show_tags = args.show_tags
    # Benchmark the whole-scene tag pass, not the (empty) selection's — the
    # app's default scopes tags to the selection.
    vp.show_tags_selected_only = False
    vp.show_grid = args.show_grid
    vp.show_axes = args.show_axes
    vp.stereo_mode = args.stereo
    vp.set_nodes(nodes)
    if args.draw_limit is not None:
        vp._draw_limit = args.draw_limit
    vp.resize(args.width, args.height)

    media = Path(args.media_folder) if args.media_folder else Path(args.csv).resolve().parent / "media"
    if media.is_dir():
        vp.load_texture_folder(media)

    for _ in range(args.warmup):
        vp.grabFramebuffer()

    times = []
    for _ in range(args.frames):
        t0 = time.perf_counter()
        vp.grabFramebuffer()
        times.append((time.perf_counter() - t0) * 1000.0)

    mean = statistics.fmean(times)
    med = statistics.median(times)
    print(f"file:    {args.csv}")
    print(f"nodes:   {len(nodes)}   size: {args.width}x{args.height}   "
          f"tags: {args.show_tags}   stereo: {args.stereo}")
    print(f"frames:  {args.frames} (+{args.warmup} warmup)")
    print(f"mean:    {mean:.1f} ms/frame  ({1000.0 / mean:.1f} fps)")
    print(f"median:  {med:.1f} ms/frame   min: {min(times):.1f}   max: {max(times):.1f}")
    print("note: headless frames include a full-frame GPU readback; "
          "interactive on-screen fps will be higher.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
