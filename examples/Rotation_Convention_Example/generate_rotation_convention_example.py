#!/usr/bin/env python3
"""
generate_rotation_convention_example.py
========================================
Side-by-side demonstration of GlyphViz's two `rotation_mode` values (see
glyphviz_core/node.py): ANTz's legacy HEADING_TILT_ROLL (a Z-X-Z "proper
Euler" sequence where rotate_y/rotate_z both rotate about z) versus the
GlyphViz-only EULER_XYZ (rotate_x/y/z each about their own named axis).

Why this is worth showing: it is NOT that one mode can "spin in place" and
the other can't (rotate_z is the innermost rotation in both conventions, so
animating only rotate_z is indistinguishable between the two -- a tempting
but incorrect claim). The real, verifiable difference is in how rotate_x
and rotate_y *jointly* aim the object when BOTH are non-zero:

  - HEADING_TILT_ROLL composes Heading (rotate_y, about z) then Tilt
    (rotate_x, about x) -- exactly the standard spherical-coordinate
    parameterization (azimuth, then colatitude) already used everywhere
    else in this engine (translate_x/y as longitude/latitude on Sphere
    topology). Holding Tilt fixed and sweeping Heading traces a perfectly
    level circle at constant elevation, like a lighthouse beam or radar
    dish sweeping at a fixed tilt angle.

  - EULER_XYZ composes rotate_x then rotate_y as plain axis-aligned
    rotations, which do NOT correspond to azimuth/elevation. Feeding the
    *exact same two numbers* (fixed rotate_x=30, rotate_y swept 0->360)
    into this mode makes the tip's elevation visibly wobble through the
    sweep instead of tracing a level circle.

Scene layout
------------
Two standalone Pin-geometry "beacon" nodes side by side, both driven by the
SAME Channels track animating rotate_y (Heading) from 0 to 360 degrees on a
loop, with the same fixed rotate_x=30 (Tilt). Beacon A uses
rotation_mode=HEADING_TILT_ROLL; Beacon B uses rotation_mode=EULER_XYZ.
Watch Beacon A's tip sweep a level circle while Beacon B's tip bobs up and
down as it sweeps -- same two input numbers, different rotation convention.

Output files (written to OUTPUT_DIR)
-------------------------------------
  {PREFIX}_gv_node.csv       the two beacon nodes
  {PREFIX}_gv_ch-map.csv     channel -> rotate_y mapping (shared by both nodes)
  {PREFIX}_gv_ch-tracks.csv  the 0->360 Heading sweep, looped

Usage
-----
  python generate_rotation_convention_example.py

Load in GlyphViz: File > Open Node CSV -> {PREFIX}_gv_node.csv
The Channels panel appears automatically. Press Play to animate.
"""

import csv
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent
PREFIX = "Rotation_Convention_Example"

GEO_PIN = 16   # glyphviz_core/geometry_data.py
TOPO_NONE = 0  # glyphviz_core/topology.py

ROTATION_MODE_EULER_XYZ = 0          # glyphviz_core/node.py
ROTATION_MODE_HEADING_TILT_ROLL = 1

TILT_DEG = 30.0   # fixed rotate_x for both beacons
N_FRAMES = 120     # one full 0->360 Heading sweep, looped
FPS = 30.0

SCALE = 0.2
SPACING = 4.0   # distance between the two beacons along X


def write_nodes(path: Path) -> None:
    fieldnames = [
        "id", "type", "parent_id", "branch_level",
        "translate_x", "translate_y", "translate_z",
        "rotate_x", "rotate_y", "rotate_z",
        "scale_x", "scale_y", "scale_z",
        "color_r", "color_g", "color_b", "color_a",
        "geometry", "hide", "topo", "ratio",
        "rotation_mode", "text", "ch_input_id",
    ]
    rows = [
        {
            "id": 1, "type": 5, "parent_id": 0, "branch_level": 0,
            "translate_x": -SPACING / 2, "translate_y": 0.0, "translate_z": 0.0,
            "rotate_x": TILT_DEG, "rotate_y": 0.0, "rotate_z": 0.0,
            "scale_x": SCALE, "scale_y": SCALE, "scale_z": SCALE,
            "color_r": 0, "color_g": 220, "color_b": 255, "color_a": 255,
            "geometry": GEO_PIN, "hide": 0, "topo": TOPO_NONE, "ratio": 0.1,
            "rotation_mode": ROTATION_MODE_HEADING_TILT_ROLL,
            "text": "Heading/Tilt/Roll (ANTz)", "ch_input_id": 1,
        },
        {
            "id": 2, "type": 5, "parent_id": 0, "branch_level": 0,
            "translate_x": SPACING / 2, "translate_y": 0.0, "translate_z": 0.0,
            "rotate_x": TILT_DEG, "rotate_y": 0.0, "rotate_z": 0.0,
            "scale_x": SCALE, "scale_y": SCALE, "scale_z": SCALE,
            "color_r": 255, "color_g": 120, "color_b": 0, "color_a": 255,
            "geometry": GEO_PIN, "hide": 0, "topo": TOPO_NONE, "ratio": 0.1,
            "rotation_mode": ROTATION_MODE_EULER_XYZ,
            "text": "Euler XYZ", "ch_input_id": 1,
        },
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows)} nodes (Beacon A = Heading/Tilt/Roll, Beacon B = Euler XYZ)")


def write_ch_map(path: Path) -> None:
    fieldnames = ["id", "channel_id", "track_id", "attribute",
                  "track_table_id", "ch_map_table_id", "record_id"]
    rows = [{
        "id": 0, "channel_id": 1, "track_id": 1, "attribute": "rotate_y",
        "track_table_id": 0, "ch_map_table_id": 0, "record_id": 0,
    }]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: 1 channel mapping (ch_input_id 1 -> rotate_y, shared by both beacons)")


def write_ch_tracks(path: Path) -> None:
    fieldnames = ["cyclecount", "ch1"]
    rows = []
    for j in range(N_FRAMES):
        heading = (j / N_FRAMES) * 360.0
        rows.append({"cyclecount": j, "ch1": round(heading, 4)})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {N_FRAMES} frames, Heading 0->360 deg looped at {FPS} fps")


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing Rotation_Convention_Example to {OUTPUT_DIR}/\n")
    write_nodes(OUTPUT_DIR / f"{PREFIX}_gv_node.csv")
    write_ch_map(OUTPUT_DIR / f"{PREFIX}_gv_ch-map.csv")
    write_ch_tracks(OUTPUT_DIR / f"{PREFIX}_gv_ch-tracks.csv")

    print(f"\nDone.  Open GlyphViz, then:")
    print(f"  File > Open Node CSV -> {PREFIX}_gv_node.csv")
    print(f"  The Channels panel appears automatically. Press Play to animate.")
    print(f"  Beacon A (cyan, Heading/Tilt/Roll) sweeps a level circle.")
    print(f"  Beacon B (orange, Euler XYZ) wobbles in elevation despite identical input.")
