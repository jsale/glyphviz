#!/usr/bin/env python3
"""
generate_topology_example.py
=============================
Generates the GlyphViz node + tag CSVs for the "Topology" tutorial: one
branch-level-0 root per topology (all 18 types), each with child nodes that
demonstrate how that topology distributes children in 3-D space.

Scene layout
------------
18 root nodes spread along the X axis, one per topology, in the canonical
order from glyphviz_core/topology.py (None, Cube, Sphere, ... Surface).
Each root has 5 children (Surface gets 6 — it's an inherently grid-shaped
topology that doesn't divide evenly into 5) placed using translate_x/y/z
values chosen to make that topology's particular coordinate system obvious:

  Topology              translate_x / y / z meaning              Children pattern
  ---------------------------------------------------------------------------------
  None       (0)        raw Cartesian (dx, dy, dz)                scattered, no pattern (the baseline)
  Cube       (1)        face-plane u, v / facet picks the face     one child per face (facet 1-5)
  Sphere     (2)        longitude, latitude / altitude             5 around the equator, just above the surface
  Torus      (3)        major angle, minor angle / tube offset     5 around the major ring, on the tube surface
  Cylinder   (4)        angle, height / radial offset               5 around the axis, on the surface
  Pin        (5)        height, lateral x, lateral y               5 stacked along the pin's length
  Rod        (6)        axial position, angle, radial               5 along the rod's length (axis = -180..180)
  Point      (7)        longitude, latitude / altitude              5 around a ring, floating (no surface)
  Plane      (8)        raw Cartesian (dx, dy, dz) on the grid      5-point pentagon flat on the grid
  Zcube      (9)        face-plane u, v / offset from center        one child per face direction, pushed out from center
  Zsphere    (10)       longitude, latitude / offset from center    5 around a ring, offset from center
  Ztorus     (11)       major angle, minor angle / ring offset      5 around the major ring, off the ring centerline
  Zcylinder  (12)       angle, height / offset from axis            5 around the central axis (not the surface)
  Zrod       (13)       angle, height / offset from axis            5 along the axis (same math as Zcylinder)
  Spiral     (14)       helix angle (climbs each turn) / radial     5 children climbing a rising helix
  Video      (15)       raw Cartesian (dx, dy, dz) on the screen    screen's 4 corners + center
  Plot       (16)       raw Cartesian (dx, dy, dz)                  a simple rising/falling data series
  Surface    (17)       grid x, grid y / height value               2x3 height-field grid (6 points)

Output files (written to OUTPUT_DIR)
-------------------------------------
  {PREFIX}_gv_node.csv   node hierarchy (18 roots + their children)
  {PREFIX}_gv_tag.csv    topology-name label on every root

Usage
-----
  python generate_topology_example.py

Load in GlyphViz: File > Open Node CSV -> {PREFIX}_gv_node.csv
"""

import colorsys
import csv
import math
from pathlib import Path

# ===========================================================================
# Parameters - modify these freely
# ===========================================================================

OUTPUT_DIR = Path(__file__).parent
PREFIX     = "topology_example"

ROOT_SCALE   = 1.0   # scale of each topology root node
CHILD_SCALE  = 0.3   # scale of each child node
ROOT_SPACING = 12.0  # X distance between topology roots

# Geometry IDs (see glyphviz_core/geometry_data.py)
GEO_CUBE_WIRE     = 0
GEO_SPHERE_WIRE   = 2
GEO_CONE_WIRE     = 4
GEO_TORUS_WIRE    = 6
GEO_SPHERE        = 3
GEO_PIN_WIRE      = 17
GEO_CYLINDER_WIRE = 18
GEO_GRID_WIRE     = 20
GEO_GRID          = 21
GEO_POINT         = 22

# Topology ids, in the canonical order from glyphviz_core/topology.py.
TOPO_NAMES = [
    "None", "Cube", "Sphere", "Torus", "Cylinder", "Pin", "Rod", "Point",
    "Plane", "Zcube", "Zsphere", "Ztorus", "Zcylinder", "Zrod", "Spiral",
    "Video", "Plot", "Surface",
]

# Root geometry per topology - picked to visually hint at the topology's
# shape where a natural match exists (e.g. Cube -> cube wireframe); the
# pure-placement topologies (None, Point, Plot) just use a point marker.
TOPO_GEO = [
    GEO_POINT,         # None
    GEO_CUBE_WIRE,     # Cube
    GEO_SPHERE_WIRE,   # Sphere
    GEO_TORUS_WIRE,    # Torus
    GEO_CYLINDER_WIRE, # Cylinder
    GEO_PIN_WIRE,      # Pin
    GEO_CYLINDER_WIRE, # Rod
    GEO_POINT,         # Point
    GEO_GRID_WIRE,     # Plane
    GEO_CUBE_WIRE,     # Zcube
    GEO_SPHERE_WIRE,   # Zsphere
    GEO_TORUS_WIRE,    # Ztorus
    GEO_CYLINDER_WIRE, # Zcylinder
    GEO_CYLINDER_WIRE, # Zrod
    GEO_CONE_WIRE,     # Spiral
    GEO_GRID,          # Video
    GEO_POINT,         # Plot
    GEO_GRID_WIRE,     # Surface
]

# Shared coordinate building blocks.
RING      = [i * 72.0 for i in range(5)]            # 5 evenly-spaced angles: 0,72,144,216,288
AXIAL5    = [-1.5, -0.75, 0.0, 0.75, 1.5]            # Pin / Zrod height steps
ROD_AXIAL = [-120.0, -60.0, 0.0, 60.0, 120.0]        # within Rod's axial range of [-180, 180]

# Per-topology child (translate_x, translate_y, translate_z, facet) tuples.
# facet only matters for Cube/Zcube (it picks which of the 6 cube faces);
# every other topology leaves it at 1 (subspace 0).
CHILDREN: dict[int, list[tuple[float, float, float, int]]] = {
    0: [  # None - no topology, so there's no "natural" pattern: a deliberate scatter
        (3, 2, 0, 1), (-3, 2, -1, 1), (2, -3, 1, 1), (-2, -3, -1, 1), (0, 4, 2, 1),
    ],
    1: [(0, 0, 0, f) for f in (1, 2, 3, 4, 5)],                       # Cube: one child per face
    2: [(a, 0, 0.5, 1) for a in RING],                                # Sphere: ring, just above the surface
    3: [(a, 0, 0.0, 1) for a in RING],                                # Torus: ring, on the tube surface
    4: [(a, 0, 0.0, 1) for a in RING],                                # Cylinder: ring, on the surface
    5: [(h, 0, 0, 1) for h in AXIAL5],                                # Pin: stacked along its length
    6: [(a, 0, 0.0, 1) for a in ROD_AXIAL],                           # Rod: spread along the rod's axis
    7: [(a, 0, 2.0, 1) for a in RING],                                # Point: ring, floating (no surface)
    8: [(2 * math.cos(math.radians(a)), 2 * math.sin(math.radians(a)), 0, 1)
        for a in RING],                                               # Plane: pentagon flat on the grid
    9: [(0, 0, 1.5, f) for f in (1, 2, 3, 4, 5)],                      # Zcube: one per face direction, off-center
    10: [(a, 0, 1.5, 1) for a in RING],                                # Zsphere: ring, offset from center
    11: [(a, 0, 0.5, 1) for a in RING],                                # Ztorus: ring, off the ring centerline
    12: [(a, 0, 0.5, 1) for a in RING],                                # Zcylinder: ring around the central axis
    13: [(0, h, 0.3, 1) for h in AXIAL5],                              # Zrod: same math as Zcylinder, varies height
    14: [(a, 0, 0.0, 1) for a in (0, 144, 288, 432, 576)],             # Spiral: climbing helix (>360 deg across turns)
    15: [(-3, -2, 0, 1), (3, -2, 0, 1), (-3, 2, 0, 1), (3, 2, 0, 1), (0, 0, 0, 1)],  # Video: screen corners + center
    16: [(x, 0, z, 1) for x, z in zip((0, 1, 2, 3, 4), (0, 1.5, 0.5, 2.0, 1.0))],   # Plot: a data series
    17: [(x, y, z, 1) for (x, y), z in zip(
        [(0, 0), (2, 0), (4, 0), (0, 2), (2, 2), (4, 2)],
        (0, 1.0, 0.5, 0.3, 1.2, 0.6))],                                # Surface: 2x3 height-field grid (6 points)
}

N_ROOTS = len(TOPO_NAMES)

# ===========================================================================
# Derived helpers - no need to edit below here
# ===========================================================================


def _root_x(ri: int) -> float:
    return (ri - (N_ROOTS - 1) / 2.0) * ROOT_SPACING


def _root_color(ri: int) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(ri / N_ROOTS, 0.75, 0.95)
    return (round(r * 255), round(g * 255), round(b * 255))


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
        "geometry", "hide", "topo", "ratio", "facet",
    ]

    rows = []
    nid  = 1

    for topo_id in range(N_ROOTS):
        root_id = nid
        color = _root_color(topo_id)
        rows.append({
            "id": root_id, "type": 5, "parent_id": 0, "branch_level": 0,
            "translate_x": round(_root_x(topo_id), 4),
            "translate_y": 0.0, "translate_z": 0.0,
            "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
            "scale_x": ROOT_SCALE, "scale_y": ROOT_SCALE, "scale_z": ROOT_SCALE,
            "color_r": color[0], "color_g": color[1], "color_b": color[2], "color_a": 255,
            "geometry": TOPO_GEO[topo_id], "hide": 0, "topo": topo_id,
            "ratio": 0.15, "facet": 1,
        })
        nid += 1

        for tx, ty, tz, facet in CHILDREN[topo_id]:
            rows.append({
                "id": nid, "type": 5, "parent_id": root_id, "branch_level": 1,
                "translate_x": round(tx, 4), "translate_y": round(ty, 4), "translate_z": round(tz, 4),
                "rotate_x": 0.0, "rotate_y": 0.0, "rotate_z": 0.0,
                "scale_x": CHILD_SCALE, "scale_y": CHILD_SCALE, "scale_z": CHILD_SCALE,
                "color_r": 230, "color_g": 230, "color_b": 230, "color_a": 255,
                "geometry": GEO_SPHERE, "hide": 0, "topo": 0,
                "ratio": 0.1, "facet": facet,
            })
            nid += 1

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    total = nid - 1
    print(f"  {path.name}: {total} nodes  ({N_ROOTS} roots + {total - N_ROOTS} children)")
    return total


# ===========================================================================
# gv_tag.csv
# ===========================================================================

def write_tags(path: Path) -> None:
    # GlyphViz reads: id, table_id, record_id, title.
    # record_id matches the root node's id (roots are numbered 1, 1+len(children[0])+1,
    # ... in write_nodes, so recompute the same way here).
    #
    # The bare word "None" is deliberately NOT used as a tag title: pandas'
    # read_csv() treats it as a missing-value token by default and silently
    # turns it into NaN when the tag file is loaded.
    fieldnames = ["id", "table_id", "record_id", "title"]
    rows = []
    nid = 1
    for topo_id in range(N_ROOTS):
        root_id = nid
        title = "No Topology" if TOPO_NAMES[topo_id] == "None" else TOPO_NAMES[topo_id]
        rows.append({
            "id": topo_id,
            "table_id": 0,
            "record_id": root_id,
            "title": title,
        })
        nid += 1 + len(CHILDREN[topo_id])
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows)} tags")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing Topology example to {OUTPUT_DIR}/\n")
    write_nodes(OUTPUT_DIR / f"{PREFIX}_gv_node.csv")
    write_tags(OUTPUT_DIR / f"{PREFIX}_gv_tag.csv")
    print(f"\nDone.  Open GlyphViz, then:")
    print(f"  File > Open Node CSV -> {PREFIX}_gv_node.csv")
    print(f"  Each labeled root shows how its topology distributes 5 children in 3-D.")
