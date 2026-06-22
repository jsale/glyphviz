#!/usr/bin/env python3
"""
generate_sine_example.py
========================
Generates four GlyphViz/GaiaViz CSV files that demonstrate channel animation
with sinusoidal time-series data.

Scene layout
------------
One branch-level-0 root node for each supported topology (Sphere, Torus, Pin,
Rod, Point, Plane, Spiral), spaced along the X axis.  Each root has
N_CHILDREN child nodes spread along their topology's natural translate_x
dimension.  The children's translate_z is driven by per-track sinusoidal
channels of increasing frequency (track 1 = 1 Hz … track 32 = 32 Hz).

Output files (written to OUTPUT_DIR)
-------------------------------------
  {PREFIX}_gv_node.csv       node hierarchy
  {PREFIX}_gv_tag.csv        topology name labels
  {PREFIX}_gv_ch-map.csv     channel → attribute mappings
  {PREFIX}_gv_ch-tracks.csv  sinusoidal time-series values

Usage
-----
  python generate_sine_example.py

Load in GlyphViz: File > Open Node CSV → {PREFIX}_gv_node.csv
The Channels panel appears automatically.  Press ▶ to animate.
"""

import csv
import math
from pathlib import Path

# ===========================================================================
# Parameters — modify these freely
# ===========================================================================

OUTPUT_DIR = Path(__file__).parent
PREFIX     = "SineWave_Example"

# Children per topology root
N_CHILDREN = 32

# Sinusoidal amplitude (peak translate_z displacement, in scene units)
AMPLITUDE = 3.0

# Minimum animation frames per cycle at the HIGHEST frequency track.
# Total frames = N_CHILDREN * MIN_SAMPLES_PER_CYCLE
# (e.g. 32 tracks × 16 samples = 512 frames; track 32 Hz has exactly 16 frames/cycle)
MIN_SAMPLES_PER_CYCLE = 16

# Scale of each topology root node
ROOT_SCALE = 3.0

# Scale of each child sphere node
CHILD_SCALE = 0.5

# Geometry IDs (ANTz kNPgeo* enum — see glyphviz/geometry.py)
GEO_CUBE       = 1
GEO_SPHERE     = 3
GEO_CONE       = 5
GEO_TORUS      = 7
GEO_PIN        = 16
GEO_CYLINDER   = 19
GEO_POINT      = 22

# Topology roots: (topo_id, geo_id, name, (r,g,b), tx_lo, tx_hi, periodic)
#
# translate_x interpretation per topology:
#   Sphere / Point : longitude in degrees  (0 = +X, 90 = +Y, …)
#   Torus          : major-ring angle in degrees  (0 → 360)
#   Rod            : axial position  (0 = bottom, 180 = top)
#   Pin            : height above pin-head in scene units
#   Plane          : Cartesian X offset in scene units
#   Spiral         : helix angle in degrees  (360 = one full turn)
#
# periodic=True  → children fill [tx_lo, tx_hi) with step = range / N_CHILDREN
#                   (avoids duplicate endpoints on a closed loop)
# periodic=False → children fill [tx_lo, tx_hi] with step = range / (N_CHILDREN-1)

TOPOLOGY_ROOTS = [
    # topo  geo          name       color             tx_lo   tx_hi  periodic
    (  2,  GEO_SPHERE,  "Sphere",  ( 50, 100, 220),   0.0,  360.0,  True  ),
    (  3,  GEO_TORUS,   "Torus",   (220, 120,  50),   0.0,  360.0,  True  ),
    (  5,  GEO_PIN,     "Pin",     ( 50, 200,  80),   1.0,   16.0,  False ),
    (  6,  GEO_CYLINDER,"Rod",     (220, 200,  50),   0.0,  180.0,  False ),
    (  7,  GEO_POINT,   "Point",   (200,  50, 200),   0.0,  360.0,  True  ),
    (  8,  GEO_CUBE,    "Plane",   ( 50, 200, 200),  -15.5,  15.5,  False ),
    ( 14,  GEO_CONE,    "Spiral",  (220,  80,  80),   0.0,  720.0,  True  ),
]

# Root node X positions: centred at origin, spaced ROOT_SPACING apart
ROOT_SPACING = 50.0

# ===========================================================================
# Derived constants — no need to edit below here
# ===========================================================================

N_ROOTS    = len(TOPOLOGY_ROOTS)
N_TRACKS   = N_CHILDREN
NUM_FRAMES = N_TRACKS * MIN_SAMPLES_PER_CYCLE   # 512 at defaults


def _root_x(ri: int) -> float:
    return (ri - (N_ROOTS - 1) / 2.0) * ROOT_SPACING


def _child_tx(tx_lo: float, tx_hi: float, periodic: bool, ci: int) -> float:
    if periodic:
        return tx_lo + ci * (tx_hi - tx_lo) / N_CHILDREN
    else:
        return tx_lo + ci * (tx_hi - tx_lo) / max(N_CHILDREN - 1, 1)


# ===========================================================================
# gv_node.csv
# ===========================================================================

def write_nodes(path: Path) -> int:
    fieldnames = [
        "id", "type", "parent_id", "branch_level",
        "translate_x", "translate_y", "translate_z",
        "rotate_x", "rotate_y", "rotate_z",
        "scale_x", "scale_y", "scale_z",
        "color_r", "color_g", "color_b", "color_a",
        "geometry", "hide", "topo", "ratio", "ch_input_id",
    ]

    rows  = []
    nid   = 1

    for ri, (topo, geo, name, color, tx_lo, tx_hi, periodic) in enumerate(TOPOLOGY_ROOTS):
        root_id = nid
        rows.append({
            "id": root_id, "type": 5, "parent_id": 0, "branch_level": 0,
            "translate_x": round(_root_x(ri), 4),
            "translate_y": 0.0, "translate_z": 0.0,
            "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
            "scale_x": ROOT_SCALE, "scale_y": ROOT_SCALE, "scale_z": ROOT_SCALE,
            "color_r": color[0], "color_g": color[1], "color_b": color[2], "color_a": 255,
            "geometry": geo, "hide": 0, "topo": topo, "ratio": 0.15,
            "ch_input_id": 0,
        })
        nid += 1

        for ci in range(N_CHILDREN):
            rows.append({
                "id": nid, "type": 5, "parent_id": root_id, "branch_level": 1,
                "translate_x": round(_child_tx(tx_lo, tx_hi, periodic, ci), 4),
                "translate_y": 0.0, "translate_z": 0.0,
                "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
                "scale_x": CHILD_SCALE, "scale_y": CHILD_SCALE, "scale_z": CHILD_SCALE,
                "color_r": 200, "color_g": 200, "color_b": 200, "color_a": 255,
                "geometry": GEO_SPHERE, "hide": 0, "topo": 0, "ratio": 0.1,
                "ch_input_id": ci + 1,   # 1-indexed; matches channel_id in ch-map
            })
            nid += 1

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    total = nid - 1
    print(f"  {path.name}: {total} nodes  "
          f"({N_ROOTS} roots + {N_ROOTS * N_CHILDREN} children)")
    return total


# ===========================================================================
# gv_tag.csv
# ===========================================================================

def write_tags(path: Path) -> None:
    # GlyphViz reads: table_id, record_id, title
    # record_id matches the root node's id (1-indexed, one per root)
    fieldnames = ["id", "table_id", "record_id", "title"]
    rows = []
    for ri, (_topo, _geo, name, _color, *_rest) in enumerate(TOPOLOGY_ROOTS):
        rows.append({
            "id": ri,
            "table_id": 0,
            "record_id": ri + 1,   # root node id is (ri + 1)
            "title": name,
        })
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows)} tags")


# ===========================================================================
# gv_ch-map.csv
# ===========================================================================

def write_ch_map(path: Path) -> None:
    # One row per channel: channel_id i drives track i, animating translate_z.
    # Every child node with ch_input_id == i is driven by this channel.
    fieldnames = ["id", "channel_id", "track_id", "attribute",
                  "track_table_id", "ch_map_table_id", "record_id"]
    rows = []
    for i in range(N_TRACKS):
        rows.append({
            "id": i,
            "channel_id": i + 1,
            "track_id": i + 1,
            "attribute": "translate_z",
            "track_table_id": 0,
            "ch_map_table_id": 0,
            "record_id": 0,
        })
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows)} channel mappings  "
          f"(ch_input_id 1-{N_TRACKS} → translate_z)")


# ===========================================================================
# gv_ch-tracks.csv
# ===========================================================================

def write_ch_tracks(path: Path) -> None:
    # Frame j (0-indexed), track i (1-indexed, frequency = i Hz):
    #
    #   dt = 1 / (N_TRACKS * MIN_SAMPLES_PER_CYCLE)   seconds per frame
    #   value = AMPLITUDE * sin(2π × i × j / NUM_FRAMES)
    #
    # At defaults: NUM_FRAMES=512, dt≈0.002 s, total duration=1 second.
    #   Track  1 (1 Hz):  512 frames/cycle  (slowest)
    #   Track 32 (32 Hz):  16 frames/cycle  (fastest — Nyquist headroom = 8)

    track_cols = [f"ch{i + 1}" for i in range(N_TRACKS)]
    fieldnames = ["cyclecount"] + track_cols

    denom = float(NUM_FRAMES)   # = N_TRACKS × MIN_SAMPLES_PER_CYCLE

    rows = []
    for j in range(NUM_FRAMES):
        row: dict = {"cyclecount": j}
        for i in range(N_TRACKS):
            freq  = i + 1
            angle = 2.0 * math.pi * freq * j / denom
            row[track_cols[i]] = round(AMPLITUDE * math.sin(angle), 6)
        rows.append(row)

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"  {path.name}: {NUM_FRAMES} frames × {N_TRACKS} tracks  "
          f"(freq 1–{N_TRACKS} Hz, amplitude ±{AMPLITUDE})")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing SineWave example to {OUTPUT_DIR}/\n")
    write_nodes    (OUTPUT_DIR / f"{PREFIX}_gv_node.csv")
    write_tags     (OUTPUT_DIR / f"{PREFIX}_gv_tag.csv")
    write_ch_map   (OUTPUT_DIR / f"{PREFIX}_gv_ch-map.csv")
    write_ch_tracks(OUTPUT_DIR / f"{PREFIX}_gv_ch-tracks.csv")
    print(f"\nDone.  Open GlyphViz, then:")
    print(f"  File > Open Node CSV → {PREFIX}_gv_node.csv")
    print(f"  The Channels panel appears automatically.  Press ▶ to animate.")
