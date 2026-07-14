#!/usr/bin/env python3
"""
generate_palette_example.py
============================
Demonstrates GlyphViz's built-in color palette / color_index feature (see
glyphviz_core/color_palette.py, glyphviz_core/node.py's palette_id/color_index
fields). Since palette resolution only ever happens interactively (the =/-/
Alt+=/Alt+- keys, or the Inspector's Palette/Color Index controls -- never
automatically on load), this generator computes each node's literal
color_r/g/b directly (mirroring color_palette.resolve_palette_color) and
stamps the matching palette_id/color_index alongside it, the same way a real
authored file would.

Scene layout
------------
Five rows of Pin-geometry nodes, one row per palette, each node's
color_index spaced evenly across that palette's valid range:
  Row 1  Palette 0  (20 Distinct Colors)            -- all 20 entries
  Row 2  Palette 1  (20 Distinct Colors, Inverted)   -- all 20 entries
  Row 3  Palette 2  (Rainbow Heatmap)                -- 20 samples of 0-127
  Row 4  Palette 4  (Blue -> Green)                  -- 20 samples of 0-127
  Row 5  Palette 24 (Greyscale)                      -- 20 samples of 0-127

Load in GlyphViz, select a node, and try the palette keys:
  =  / -          step color_index within the node's current palette
  Alt+=  / Alt+-  step to the next/previous palette (re-resolves color)
Or use the Inspector's Palette combo / Color Index spinner directly.

Output: {PREFIX}_gv_node.csv in this directory.
"""

import colorsys
import csv
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent
PREFIX = "Palette_Example"

GEO_PIN = 16     # glyphviz_core/geometry_data.py
TOPO_NONE = 0    # glyphviz_core/topology.py

N_PER_ROW = 20
SPACING = 1.5
SCALE = 0.3

# Mirrors glyphviz_core/color_palette.py's built-in table for the palettes
# demonstrated here (kept standalone/no glyphviz_core import, matching this
# project's other example generators).
PALETTE_20_RGB = [
    (50, 101, 101), (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
    (152, 0, 255), (255, 168, 0), (0, 255, 255), (255, 0, 255), (0, 153, 0),
    (185, 153, 102), (255, 180, 255), (0, 152, 255), (185, 255, 0), (152, 0, 0),
    (127, 127, 127), (127, 127, 255), (197, 82, 0), (0, 0, 0), (255, 255, 255),
]


def _lerp_rgb(c0, c1, t):
    return tuple(round(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))


def _rainbow(t):
    r, g, b = colorsys.hsv_to_rgb(t, 1.0, 1.0)
    return (round(r * 255), round(g * 255), round(b * 255))


def _row(row_index, palette_id, color_indices, resolve):
    y = -row_index * SPACING
    n = len(color_indices)
    rows = []
    for i, ci in enumerate(color_indices):
        r, g, b = resolve(ci)
        rows.append({
            "translate_x": (i - (n - 1) / 2) * SPACING, "translate_y": y,
            "palette_id": palette_id, "color_index": ci,
            "color_r": r, "color_g": g, "color_b": b,
        })
    return rows


def build_rows():
    rows = []
    rows += _row(0, 0, list(range(20)), lambda ci: PALETTE_20_RGB[ci])
    rows += _row(1, 1, list(range(20)),
                 lambda ci: tuple(255 - c for c in PALETTE_20_RGB[ci]))
    gradient_indices = [round(i * 127 / (N_PER_ROW - 1)) for i in range(N_PER_ROW)]
    rows += _row(2, 2, gradient_indices, lambda ci: _rainbow(ci / 127.0))
    rows += _row(3, 4, gradient_indices,
                 lambda ci: _lerp_rgb((0, 0, 255), (0, 255, 0), ci / 127.0))
    rows += _row(4, 24, gradient_indices,
                 lambda ci: _lerp_rgb((0, 0, 0), (255, 255, 255), ci / 127.0))
    return rows


def write_nodes(path: Path) -> None:
    fieldnames = [
        "id", "type", "parent_id", "branch_level",
        "translate_x", "translate_y", "translate_z",
        "rotate_x", "rotate_y", "rotate_z",
        "scale_x", "scale_y", "scale_z",
        "color_r", "color_g", "color_b", "color_a", "color_index", "palette_id",
        "geometry", "hide", "topo", "ratio",
    ]
    out_rows = []
    for i, r in enumerate(build_rows(), start=1):
        out_rows.append({
            "id": i, "type": 5, "parent_id": 0, "branch_level": 0,
            "translate_x": r["translate_x"], "translate_y": r["translate_y"], "translate_z": 0.0,
            "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
            "scale_x": SCALE, "scale_y": SCALE, "scale_z": SCALE,
            "color_r": r["color_r"], "color_g": r["color_g"], "color_b": r["color_b"], "color_a": 255,
            "color_index": r["color_index"], "palette_id": r["palette_id"],
            "geometry": GEO_PIN, "hide": 0, "topo": TOPO_NONE, "ratio": 0.1,
        })
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    print(f"  {path.name}: {len(out_rows)} nodes across 5 palette rows")


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing Palette_Example to {OUTPUT_DIR}/\n")
    write_nodes(OUTPUT_DIR / f"{PREFIX}_gv_node.csv")
    print(f"\nDone.  Open GlyphViz, then:")
    print(f"  File > Open Node CSV -> {PREFIX}_gv_node.csv")
    print(f"  Select a node and try =/- (step color_index) and Alt+=/Alt+- (step palette).")
