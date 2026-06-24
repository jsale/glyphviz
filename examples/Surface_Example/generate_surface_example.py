#!/usr/bin/env python3
"""
generate_surface_example.py
============================
A real digital elevation model (DEM) rendered with GlyphViz's TOPO_SURFACE
(glyphviz_core/topology.py): Cowles Mountain (San Diego, CA), built from two
co-registered, identically-sized JPGs Jeff supplied in this folder --
cowles_dem_lowres.jpg (a grayscale heightmap: brighter = higher elevation)
and cowles_aerial_lowres.jpg (the matching satellite/aerial photo, used only
for per-point color).

No new dependency was needed for JPEG decoding -- PySide6.QtGui.QImage (an
existing GlyphViz dependency, the same class glyphviz_gl/texture_manager.py
already uses for textures) reads both JPGs directly, without a QApplication
instance.

How TOPO_SURFACE works (glyphviz_core/topology.py's `_surface_offset`):
children of a Surface-topology parent are placed at their literal Cartesian
(translate_x, translate_y) -- the grid position -- with translate_z as the
height at that grid point. glyphviz_gl/viewport.py's `_draw_topology_overlays`
groups a Surface parent's children back into a grid purely by their distinct
(translate_x, translate_y) values (no explicit row/col CSV column needed) and
draws a lit, per-vertex-colored GL_QUADS mesh between them -- so each child's
own color_r/g/b/a becomes that grid point's mesh color for free. Each child
ALSO gets its own small GEO_POINT glyph (per Jeff's ask, to keep the point
count cheap to render) which picks up the same color.

Resolution: every STRIDE'th pixel in both images (default 10, matching Jeff's
own suggestion to start crude) -- at the source images' actual size (390x369,
not exactly 256x256), stride 10 gives a 39x37 grid (~1,400 points), well
within interactive range for GL_POINTS + a quad mesh. Lower --stride for more
detail once this crude pass looks right.

Elevation convention assumed: brighter grayscale pixel = higher elevation
(confirmed against the source image: the single brightest region is an
isolated peak-like blob, consistent with a DEM render, not just noise). If
the rendered terrain looks inverted once viewed in the app, negate
height_frac in `sample_height()` below.

Output files (written to OUTPUT_DIR)
-------------------------------------
  {PREFIX}_gv_node.csv   root Surface node (hidden anchor) + one child per
                         sampled grid point (GEO_POINT, colored from the
                         aerial photo, translate_z = exaggerated DEM height)
  {PREFIX}_gv_tag.csv    one label on the root node

Usage
-----
  python generate_surface_example.py
  python generate_surface_example.py --stride 5 --exaggeration 16

Load in GlyphViz: File > Open Node CSV -> {PREFIX}_gv_node.csv
"""

import argparse
import csv
from pathlib import Path

from PySide6.QtGui import QImage

OUTPUT_DIR = Path(__file__).parent
PREFIX = "Surface_Example"

DEM_JPG    = OUTPUT_DIR / "cowles_dem_lowres.jpg"
AERIAL_JPG = OUTPUT_DIR / "cowles_aerial_lowres.jpg"

TOPO_SURFACE = 17   # glyphviz_core/topology.py
GEO_POINT    = 22   # glyphviz_core/geometry_data.py

STRIDE       = 10    # sample every STRIDE'th pixel in both images
EXAGGERATION = 12.0  # world-unit height at full-white (255) grayscale
CHILD_SCALE  = 0.15  # small GEO_POINT glyph size (world units) per grid point


def sample_height(gray_0_255: float, exaggeration: float) -> float:
    """Brighter = higher. See module docstring if this needs inverting."""
    return (gray_0_255 / 255.0) * exaggeration


def build_grid(dem: QImage, aerial: QImage, stride: int, exaggeration: float):
    """Returns list of (col_idx, row_idx, translate_z, color_r, color_g, color_b)
    for every sampled grid point, in row-major order, row 0 = north (top of
    the source images) so that translate_y increases northward once flipped
    by the caller."""
    w, h = dem.width(), dem.height()
    assert (w, h) == (aerial.width(), aerial.height()), \
        "DEM and aerial images must be the same pixel size (co-registered)"

    rows = list(range(0, h, stride))
    cols = list(range(0, w, stride))
    points = []
    for ri, y in enumerate(rows):
        for ci, x in enumerate(cols):
            dem_c = dem.pixelColor(x, y)
            gray = (dem_c.red() + dem_c.green() + dem_c.blue()) / 3.0
            tz = sample_height(gray, exaggeration)

            aerial_c = aerial.pixelColor(x, y)
            points.append((ci, ri, tz, aerial_c.red(), aerial_c.green(), aerial_c.blue()))
    return points, len(cols), len(rows)


def write_files(stride: int, exaggeration: float, child_scale: float) -> None:
    dem = QImage(str(DEM_JPG))
    aerial = QImage(str(AERIAL_JPG))
    if dem.isNull() or aerial.isNull():
        raise SystemExit(f"Could not load {DEM_JPG.name} / {AERIAL_JPG.name}")

    points, n_cols, n_rows = build_grid(dem, aerial, stride, exaggeration)
    print(f"Sampled {n_cols}x{n_rows} = {len(points)} grid points "
          f"(stride={stride}) from {dem.width()}x{dem.height()} source images")

    # Center the grid horizontally on the root (translate_x/y in grid-index
    # units, root scale_x/y = 1.0 -> 1 world unit per grid cell); flip row
    # order so translate_y increases northward (row 0 in the image = north).
    x_off = -(n_cols - 1) / 2.0
    y_off = -(n_rows - 1) / 2.0

    fieldnames = [
        "id", "type", "parent_id", "branch_level",
        "translate_x", "translate_y", "translate_z",
        "rotate_x", "rotate_y", "rotate_z",
        "scale_x", "scale_y", "scale_z",
        "color_r", "color_g", "color_b", "color_a",
        "geometry", "hide", "topo", "ratio",
    ]
    rows = [{
        # NOTE: glyphviz_gl/viewport.py's quad-mesh drawing gates on the
        # SURFACE PARENT's own `hide` flag (not just its own glyph) -- hiding
        # this root would silently skip the entire mesh, not just the root's
        # point glyph. Keep hide=0. scale_x/y/z must stay 1.0 -- _surface_offset
        # multiplies every child's translate_x/y/z by the PARENT's world scale,
        # so this is what makes 1 grid-index unit = 1 world unit; the root's
        # own GEO_POINT glyph renders a little larger than the children's
        # (whose scale_x/y/z is the separate, smaller child_scale) as a result,
        # but it's one dot among ~1,400 and sits near the grid's centroid --
        # not visually intrusive in practice (confirmed via headless render).
        "id": 1, "type": 5, "parent_id": 0, "branch_level": 0,
        "translate_x": 0.0, "translate_y": 0.0, "translate_z": 0.0,
        "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
        "scale_x": 1.0, "scale_y": 1.0, "scale_z": 1.0,
        "color_r": 128, "color_g": 128, "color_b": 128, "color_a": 255,
        "geometry": GEO_POINT, "hide": 0, "topo": TOPO_SURFACE, "ratio": 0.1,
    }]
    next_id = 2
    for ci, ri, tz, r, g, b in points:
        rows.append({
            "id": next_id, "type": 5, "parent_id": 1, "branch_level": 1,
            "translate_x": round(ci + x_off, 4),
            "translate_y": round((n_rows - 1 - ri) + y_off, 4),
            "translate_z": round(tz, 4),
            "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
            "scale_x": child_scale, "scale_y": child_scale, "scale_z": child_scale,
            "color_r": r, "color_g": g, "color_b": b, "color_a": 255,
            "geometry": GEO_POINT, "hide": 0, "topo": 0, "ratio": 0.1,
        })
        next_id += 1

    node_path = OUTPUT_DIR / f"{PREFIX}_gv_node.csv"
    with open(node_path, "w", newline="") as f:
        w_ = csv.DictWriter(f, fieldnames=fieldnames)
        w_.writeheader()
        w_.writerows(rows)
    print(f"  {node_path.name}: {len(rows)} nodes (1 root + {len(points)} DEM points)")

    tag_path = OUTPUT_DIR / f"{PREFIX}_gv_tag.csv"
    with open(tag_path, "w", newline="") as f:
        w_ = csv.DictWriter(f, fieldnames=["id", "table_id", "record_id", "title"])
        w_.writeheader()
        w_.writerow({
            "id": 0, "table_id": 0, "record_id": 1,
            "title": f"Cowles Mountain DEM (stride={stride}, {exaggeration:.0f}x height)",
        })
    print(f"  {tag_path.name}: 1 label on the root node")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stride", type=int, default=STRIDE,
                         help=f"sample every Nth pixel in both images (default {STRIDE})")
    parser.add_argument("--exaggeration", type=float, default=EXAGGERATION,
                         help=f"world-unit height at full-white grayscale (default {EXAGGERATION})")
    parser.add_argument("--child-scale", type=float, default=CHILD_SCALE,
                         help=f"GEO_POINT glyph size per grid point (default {CHILD_SCALE})")
    args = parser.parse_args()

    print(f"Writing Surface_Example to {OUTPUT_DIR}/\n")
    write_files(args.stride, args.exaggeration, args.child_scale)

    print(f"\nDone.  Open GlyphViz, then:")
    print(f"  File > Open Node CSV -> {PREFIX}_gv_node.csv")
    print(f"  Re-run with --stride 5 (or lower) for more detail once this looks right.")
