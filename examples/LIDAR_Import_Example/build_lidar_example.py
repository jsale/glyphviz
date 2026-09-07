#!/usr/bin/env python3
"""
LIDAR Import Example — an aerial laser scan, brought into GlyphViz as a
Point Cloud topology (topo 18) scene.

You do not need this script to use the example. The point of the example IS
the importer: open GlyphViz and use **Meshes > Import Point Cloud...**, or
just drag `aerial_survey.laz` onto the window. What follows is for people who
want the same thing from code, or want to see which knobs the dialog is
turning.

THE FILE
--------
`aerial_survey.laz` is a real airborne survey: 442,767 points over about
960 x 1,130 metres of ground, with per-point RGB from simultaneous imagery.
It is a good example precisely because it is ordinary — everything awkward
about real LIDAR is in it:

* **Projected coordinates with a huge origin.** Eastings run 704,194 to
  705,153 and northings 3,626,785 to 3,627,912 (a UTM zone, around 32.8 N).
  Dropped into a scene unchanged this would be a speck 3.6 million units from
  the origin, so the importer recentres it and scales it to a world span you
  choose.
* **8-bit colour in 16-bit fields.** LAS stores RGB as 16-bit, but this
  writer put 0-255 values straight into those slots — which plenty of them
  do. Shifting it down 8 bits like a true 16-bit file would render the whole
  scan black, so the importer decides from the data instead of assuming.
* **No classification.** Every point is code 0, "created, never classified",
  which is the normal state of most LIDAR outside government tiles. So the
  ground/vegetation/building colouring has nothing to work with here and the
  automatic mode correctly falls through to the file's own RGB.

WHY .laz AND NOT .las
---------------------
Identical data: LAZ is the lossless compressed form of LAS, and the round
trip is bit-for-bit (verified on this file, X/Y/Z and RGB alike). It is
17.7 MB as .las and **2.55 MB as .laz** — 14%. That is the whole argument for
the format, and it is why an example that ships a scan ships it compressed.

WHAT THE SCENE LOOKS LIKE
-------------------------
One cloud parent glyph with 442,767 point children under it. Every point is a
real node: click one and the Properties panel edits it. The parent carries
the provenance in its label, and moving/rotating/scaling it carries the whole
scan.

Run:
    <glyphviz-env>\\python.exe examples/LIDAR_Import_Example/build_lidar_example.py
    <glyphviz-env>\\python.exe examples/LIDAR_Import_Example/build_lidar_example.py --points 100000
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from glyphviz_core.csv_reader import save_node_csv          # noqa: E402
from glyphviz_core.point_cloud_loader import import_to_nodes  # noqa: E402

HERE = Path(__file__).resolve().parent
SCAN = HERE / "aerial_survey.laz"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--points', type=int, default=442_767,
                    help="how many points to keep (default: all of them). "
                         "The app defaults to 100,000; this file is small "
                         "enough to take whole.")
    ap.add_argument('--method', default='random',
                    choices=('random', 'voxel', 'stride'),
                    help="how to choose them when decimating (default random)")
    ap.add_argument('--color', default='auto',
                    choices=('auto', 'rgb', 'elevation', 'intensity',
                             'classification'),
                    help="colour source (default auto -> rgb for this file)")
    ap.add_argument('--exaggeration', type=float, default=1.0,
                    help="vertical exaggeration; 1.0 is truthful (default)")
    ap.add_argument('--span', type=float, default=360.0,
                    help="world width to fit the scan to (default 360, "
                         "GlyphViz's 1:1 frame)")
    ap.add_argument('--out', type=Path,
                    default=HERE / "LIDAR_Import_Example_gv_node.csv",
                    help="node CSV to write")
    args = ap.parse_args()

    if not SCAN.is_file():
        print(f"Missing {SCAN.name} — it ships beside this script.")
        return 1

    nodes, report = import_to_nodes(
        str(SCAN), max_points=args.points, method=args.method,
        color_mode=args.color, span=args.span,
        exaggeration=args.exaggeration, point_size=2.0,
    )

    print(f"{report['points']:,} points of {report['total_points']:,}, "
          f"coloured by {report['color_mode']}")
    sx, sy, sz = report['source_span']
    print(f"  source extent   {sx:,.0f} x {sy:,.0f} x {sz:,.0f} units")
    wx, wy, wz = report['world_span']
    print(f"  world extent    {wx:,.1f} x {wy:,.1f} x {wz:,.1f} "
          f"(scale {report['world_scale']:.5f})")

    save_node_csv(nodes, str(args.out))
    mb = args.out.stat().st_size / 1e6
    print(f"  wrote {args.out.name}  ({mb:.1f} MB)")
    # Worth saying out loud, because it is the one number that surprises
    # people: a saved node row is the full 94-column ANTz-compatible layout,
    # about 550 bytes a point. The .laz this came from is 2.55 MB.
    print(f"  (the scan itself is {SCAN.stat().st_size / 1e6:.2f} MB as .laz — "
          f"the CSV is larger because every point becomes a full node row)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
