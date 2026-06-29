#!/usr/bin/env python3
"""
export_frame.py
================
Render a single frame of a GlyphViz node CSV to a PNG, headlessly — no
window is ever shown.  Built for generating reproducible tutorial/doc
screenshots and (later) visual regression baselines, rather than reaching
for an OS-level screen-grab tool every time one is needed.

Camera framing defaults to the same bounding-box auto-fit Viewport.set_nodes()
already computes for the desktop app; pass --azimuth/--elevation/--distance/
--target to override any of them individually.

Usage:
    python tools/export_frame.py --csv path/to/scene.csv --out frame.png
    python tools/export_frame.py --csv path/to/scene.csv --out frame.png \
        --width 1920 --height 1080 --azimuth 30 --elevation 20 --distance 80
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtWidgets import QApplication

from glyphviz_core.csv_reader import load_node_csv


def render_frame(
    csv_path: str,
    out_path: str,
    width: int = 1280,
    height: int = 720,
    base_scale: float = 1.0,
    azimuth: float | None = None,
    elevation: float | None = None,
    distance: float | None = None,
    target: tuple[float, float, float] | None = None,
    media_folder: str | None = None,
    show_grid: bool = True,
    show_axes: bool = True,
    show_tags: bool = True,
) -> None:
    """Load *csv_path*, frame it, and save a PNG to *out_path*.  Must be
    called with a QApplication already constructed (see main() below)."""
    from glyphviz_gl.viewport import Viewport   # deferred: needs QApplication first

    nodes = load_node_csv(csv_path)
    vp = Viewport()
    vp.base_scale = base_scale
    vp.show_grid = show_grid
    vp.show_axes = show_axes
    vp.show_tags = show_tags
    vp.set_nodes(nodes)   # auto-frames the camera from the scene's bounding box
    vp.set_camera(azimuth=azimuth, elevation=elevation, distance=distance, target=target)

    media = Path(media_folder) if media_folder else Path(csv_path).resolve().parent / "media"
    if media.is_dir():
        vp.load_texture_folder(media)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    vp.export_png(out_path, width, height)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, help="Node CSV to load.")
    parser.add_argument("--out", required=True, help="Output PNG path.")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--base-scale", type=float, default=1.0)
    parser.add_argument("--azimuth", type=float, default=None,
                         help="Camera azimuth in degrees. Default: auto bounding-box framing.")
    parser.add_argument("--elevation", type=float, default=None,
                         help="Camera elevation in degrees. Default: auto bounding-box framing.")
    parser.add_argument("--distance", type=float, default=None,
                         help="Camera distance. Default: auto bounding-box framing.")
    parser.add_argument("--target", type=float, nargs=3, default=None, metavar=("X", "Y", "Z"),
                         help="Camera look-at target. Default: auto bounding-box framing.")
    parser.add_argument("--media-folder", default=None,
                         help="Folder of images/videos/GIFs for texture_id. "
                              "Default: auto-detect 'media' next to --csv.")
    parser.add_argument("--no-grid", dest="show_grid", action="store_false")
    parser.add_argument("--no-axes", dest="show_axes", action="store_false")
    parser.add_argument("--no-tags", dest="show_tags", action="store_false")
    args = parser.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)
    render_frame(
        args.csv, args.out, args.width, args.height, args.base_scale,
        args.azimuth, args.elevation, args.distance,
        tuple(args.target) if args.target else None,
        args.media_folder, args.show_grid, args.show_axes, args.show_tags,
    )
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
