#!/usr/bin/env python
"""What convention does a Torus parent actually use?

Scene 3 hangs satellites on rings and needs each one to land where the real
orbit puts it.  That requires knowing exactly how GlyphViz sizes a torus
parent's child ring and how it composes the parent's three rotation fields —
neither of which is written down.  So this asks the engine, the way the
Geomagnetic example had to establish the globe-child convention before it
could aim a cone.

    python probe_torus.py

Everything printed below is engine output, not hand math.  The findings it
establishes are used by `build_orbital_shells.py` and restated in the README.
"""

from __future__ import annotations

import csv
import itertools
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for candidate in (os.environ.get("GLYPHVIZ_PATH"),
                  os.path.abspath(os.path.join(HERE, "..", "..")),
                  r"C:\Users\jsale\source\repos\glyphviz"):
    if candidate and os.path.isdir(os.path.join(candidate, "glyphviz_core")):
        sys.path.insert(0, candidate)
        break
else:
    raise SystemExit("cannot find glyphviz_core — set GLYPHVIZ_PATH")

from glyphviz_core import csv_reader  # noqa: E402
from glyphviz_core import scene as scene_mod  # noqa: E402

BASE_SCALE = 3.0        # Scene(base_scale=...) default — the app's Global Scale


def rx(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def ry(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rz(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


MAKERS = {"X": rx, "Y": ry, "Z": rz}

COLS = ["id", "type", "parent_id", "branch_level",
        "translate_x", "translate_y", "translate_z",
        "rotate_x", "rotate_y", "rotate_z",
        "scale_x", "scale_y", "scale_z",
        "color_r", "color_g", "color_b", "color_a",
        "geometry", "hide", "topo", "ratio", "rotation_mode"]
BASE = dict(zip(COLS, [0] * len(COLS)))
BASE.update(type=5, scale_x=1.0, scale_y=1.0, scale_z=1.0, color_a=255,
            ratio=0.1)

_TMP = os.path.join(os.environ.get("TEMP", "."),
                    "glyphviz_probe_torus_gv_node.csv")


def load(rows):
    with open(_TMP, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)
    return scene_mod.Scene(csv_reader.load_node_csv(_TMP))


def ring(parent_kw, angles, ratio=0.01):
    """One torus parent at the origin with children at the given angles.

    Round-tripped through a CSV and `load_node_csv`, so this measures the same
    load path the app uses rather than an in-memory shortcut.
    """
    pk = dict(topo=3, geometry=6, ratio=ratio)
    pk.update(parent_kw)
    rows = [dict(BASE, id=1, parent_id=0, branch_level=0, **pk)]
    for i, ang in enumerate(angles):
        rows.append(dict(BASE, id=2 + i, parent_id=1, branch_level=1,
                         translate_x=float(ang), geometry=11,
                         scale_x=0.5, scale_y=0.5, scale_z=0.5))
    sc = load(rows)
    return [np.asarray(sc.world_pos(2 + i), dtype=float)
            for i in range(len(angles))]


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()
    S = 10.0

    # -- 1. ring radius and angle sense ------------------------------------
    w = ring(dict(scale_x=S, scale_y=S, scale_z=S), [0, 90, 180, 270])
    radii = [float(np.linalg.norm(v)) for v in w]
    R = radii[0]
    print("1. Torus parent, scale 10, ratio 0.01, children at tx = 0/90/180/270")
    for ang, v in zip([0, 90, 180, 270], w):
        print(f"     tx={ang:3d}  ->  ({v[0]:+9.5f}, {v[1]:+9.5f}, {v[2]:+9.5f})")
    print(f"   ring radius {R:.6f} for parent scale {S}  "
          f"=>  radius = {R / S:.4f} x scale")
    print(f"   Scene(base_scale=) default is {BASE_SCALE} — the app's Global")
    print(f"   Scale. So RADIUS = base_scale x parent scale, and a ring of")
    print(f"   radius R needs scale = R / {BASE_SCALE:g}.")
    print(f"   NOTE: the skill reference says B defaults to 1.0; the code says "
          f"{BASE_SCALE:g}.")
    print(f"   ring is flat in local XY: {max(abs(v[2]) for v in w) < 1e-9}")
    print(f"   tx runs from local +X toward +Y: "
          f"{w[1][1] > 0 and abs(w[1][0]) < 1e-9}")

    # -- 2. rotation composition order --------------------------------------
    A, B_, C = 37.0, 0.0, 61.0
    print(f"\n2. Composition order (rotate_x={A}, rotate_y={B_}, rotate_z={C})")
    found = {}
    for mode in (0, 1):
        w = ring(dict(scale_x=S, scale_y=S, scale_z=S, rotate_x=A,
                      rotate_y=B_, rotate_z=C, rotation_mode=mode), [0, 90])
        got = np.array(w) / R                      # unit local X and Y axes
        hit = None
        for order in itertools.permutations("XYZ"):
            m = np.eye(3)
            for axis in order:                     # leftmost = outermost
                m = m @ MAKERS[axis]({"X": A, "Y": B_, "Z": C}[axis])
            want = np.array([m @ np.array([1.0, 0.0, 0.0]),
                             m @ np.array([0.0, 1.0, 0.0])])
            if float(np.abs(want - got).max()) < 1e-9:
                hit = "".join(order)
                break
        found[mode] = hit
        label = {0: "Euler XYZ", 1: "ANTz Heading/Tilt/Roll"}[mode]
        if hit:
            print(f"   rotation_mode={mode} ({label}):  "
                  f"R{hit[0]}(r{hit[0].lower()}) . R{hit[1]}(r{hit[1].lower()}) "
                  f". R{hit[2]}(r{hit[2].lower()})")
        else:
            print(f"   rotation_mode={mode} ({label}):  not a plain Euler "
                  f"triple (axes: {got[0]}, {got[1]})")

    # -- 3. can ONE node express an orbit plane? ---------------------------
    # An orbit plane is the classical perifocal -> ECI transform
    #     r = Rz(RAAN) . Rx(inc) . (cos u, sin u, 0) * radius
    # so a single node would need to compose Z-outermost, X-inner.
    print("\n3. Orbit plane on ONE node: does (rotate_x=inc, rotate_z=RAAN) "
          "give\n   Rz(RAAN).Rx(inc), the perifocal -> ECI transform?")
    worst = 0.0
    for inc, raan, u in [(55.0, 120.0, 45.0), (98.6, 300.0, 217.0),
                         (63.4, 45.0, 270.0)]:
        w = ring(dict(scale_x=S, scale_y=S, scale_z=S, rotate_x=inc,
                      rotate_y=0.0, rotate_z=raan, rotation_mode=0), [u])
        want = R * (rz(raan) @ rx(inc) @ np.array(
            [math.cos(math.radians(u)), math.sin(math.radians(u)), 0.0]))
        worst = max(worst, float(np.linalg.norm(w[0] - want)))
    print(f"   worst error {worst:.4f} world units on a radius-{R:.0f} ring "
          f"=> {'yes' if worst < 1e-9 else 'NO'}")
    print(f"   Expected: the engine composes {found[0]} (X outermost), but an")
    print(f"   orbit needs Z outermost. A single node cannot express it with")
    print(f"   inc and RAAN written straight into the fields.")

    # -- 4. two nested nodes CAN ------------------------------------------
    # Transforms compose down the hierarchy, so an outer node carrying RAAN
    # and an inner torus carrying inclination give Rz(RAAN).Rx(inc) whatever
    # the single-node convention happens to be.
    print("\n4. Orbit plane on TWO nested nodes: outer rotate_z = RAAN,\n"
          "   inner torus rotate_x = inclination")
    worst = 0.0
    rows_out = []
    for inc, raan, u in [(55.0, 120.0, 45.0), (98.6, 300.0, 217.0),
                         (63.4, 45.0, 270.0), (0.0, 0.0, 90.0),
                         (86.4, 199.0, 123.0), (28.5, 355.0, 12.0)]:
        rows = [
            dict(BASE, id=1, parent_id=0, branch_level=0, topo=0, geometry=11,
                 rotate_z=raan, rotation_mode=0, hide=1),
            dict(BASE, id=2, parent_id=1, branch_level=1, topo=3, geometry=6,
                 ratio=0.01, rotate_x=inc, rotation_mode=0,
                 scale_x=S, scale_y=S, scale_z=S),
            dict(BASE, id=3, parent_id=2, branch_level=2, translate_x=u,
                 geometry=11, scale_x=0.5, scale_y=0.5, scale_z=0.5),
        ]
        sc = load(rows)
        got = np.asarray(sc.world_pos(3), dtype=float)
        want = R * (rz(raan) @ rx(inc) @ np.array(
            [math.cos(math.radians(u)), math.sin(math.radians(u)), 0.0]))
        err = float(np.linalg.norm(got - want))
        worst = max(worst, err)
        rows_out.append((inc, raan, u, got, want, err))
    for inc, raan, u, got, want, err in rows_out:
        print(f"     inc={inc:5.1f} RAAN={raan:5.1f} u={u:5.1f}  "
              f"engine ({got[0]:+7.3f},{got[1]:+7.3f},{got[2]:+7.3f})  "
              f"classical ({want[0]:+7.3f},{want[1]:+7.3f},{want[2]:+7.3f})  "
              f"|d| {err:.1e}")
    print(f"   worst error: {worst:.3e} world units  "
          f"=> {'CONFIRMED' if worst < 1e-9 else 'DOES NOT HOLD'}")

    # -- 5. does a Sphere-topology parent share the same radius rule? -------
    # Scene 3 wants Earth and the rings to scale together, so it needs the
    # sphere's surface radius to follow the same base_scale x scale rule.
    rows = [dict(BASE, id=1, parent_id=0, branch_level=0, topo=2, geometry=3,
                 scale_x=S, scale_y=S, scale_z=S),
            dict(BASE, id=2, parent_id=1, branch_level=1,
                 translate_x=0.0, translate_y=0.0, translate_z=0.0,
                 geometry=11, scale_x=0.5, scale_y=0.5, scale_z=0.5)]
    sc = load(rows)
    r_sphere = float(np.linalg.norm(np.asarray(sc.world_pos(2), dtype=float)))
    print(f"\n5. Sphere-topology parent, same scale: surface radius "
          f"{r_sphere:.6f}")
    print(f"   matches the torus ring radius {R:.6f}: "
          f"{abs(r_sphere - R) < 1e-9}")
    print("   => an Earth drawn as a plain Sphere glyph and the orbit rings")
    print("      obey ONE rule, so Global Scale moves them together. A World")
    print("      Grid globe would not: grids are documented as exempt from")
    print("      Global Scale, so Earth and orbits would decouple.")

    # -- 6. ratio only thickens the ring inward ----------------------------
    print("\n6. Child radius vs. the parent's `ratio`:")
    for ratio in (0.005, 0.02, 0.1, 0.3):
        w = ring(dict(scale_x=S, scale_y=S, scale_z=S), [0], ratio=ratio)
        print(f"     ratio={ratio:<6} child radius "
              f"{float(np.linalg.norm(w[0])):.6f}   drawn centreline "
              f"{R * (1 - ratio):.4f}")
    print("   => children ride the tube's OUTER edge at radius = base_scale x")
    print("      scale, whatever the ratio; ratio thickens the drawn ring")
    print("      inward only. Keep it small or the drawn circle sits visibly")
    print("      inside the orbit its own satellites are on.")

    # -- 7. translate_z is in the PARENT'S LOCAL units ----------------------
    # The trap that cost an hour: asking for "0.6 world units above the
    # surface" on a scale-19 Earth and getting 11.5.
    print("\n7. A topology child's translate_z, on a parent scaled to 19.0986")
    print("   (an Earth of radius 57.2958 world units):")
    e_scale = (orbits_r_earth := 57.29577951308232) / BASE_SCALE
    for tz in (0.0, 0.6, 0.6 / e_scale):
        rows = [dict(BASE, id=1, parent_id=0, branch_level=0, topo=2,
                     geometry=3, scale_x=e_scale, scale_y=e_scale,
                     scale_z=e_scale),
                dict(BASE, id=2, parent_id=1, branch_level=1,
                     translate_x=0.0, translate_y=0.0, translate_z=tz,
                     geometry=11, scale_x=0.5, scale_y=0.5, scale_z=0.5)]
        sc = load(rows)
        r_w = float(np.linalg.norm(np.asarray(sc.world_pos(2), dtype=float)))
        print(f"     translate_z={tz:<10.6f} -> radius {r_w:9.4f}  "
              f"({r_w - orbits_r_earth:+8.4f} world units above the surface)")
    print("   => translate_z is an altitude in the PARENT'S LOCAL units, so")
    print("      the parent's scale multiplies it. To sit a marker N world")
    print("      units off the surface, write N / parent_scale — not N.")
    print("      Torus children escape this only because their tz is 0.")

    # -- 8. a parent's scale multiplies its children's RENDERED SIZE --------
    # The one that actually shipped a broken scene. Nothing in the CSV looks
    # wrong; every glyph is authored at a sane number; every raw-scale
    # assertion passes. Only a picture shows it.
    print("\n8. A child authored at scale 0.5, under torus parents of "
          "increasing scale:")
    for S2 in (1.0, 10.0, 126.3):
        rows = [dict(BASE, id=1, parent_id=0, branch_level=0, topo=3,
                     geometry=6, ratio=0.01,
                     scale_x=S2, scale_y=S2, scale_z=S2),
                dict(BASE, id=2, parent_id=1, branch_level=1,
                     translate_x=0.0, geometry=11,
                     scale_x=0.5, scale_y=0.5, scale_z=0.5)]
        sc = load(rows)
        ws = float(np.asarray(sc.world_scale(2), dtype=float)[0])
        print(f"     parent scale {S2:<7} -> child world_scale {ws:8.3f}  "
              f"= a glyph {BASE_SCALE * ws:8.2f} world units across")
    rows = [dict(BASE, id=1, type=6, parent_id=0, branch_level=0, geometry=3,
                 scale_x=1.0, scale_y=1.0, scale_z=1.0),
            dict(BASE, id=2, parent_id=1, branch_level=1, geometry=11,
                 scale_x=0.5, scale_y=0.5, scale_z=0.5)]
    sc = load(rows)
    print(f"     World Grid globe        -> child world_scale "
          f"{float(np.asarray(sc.world_scale(2), dtype=float)[0]):8.3f}  "
          f"(grids are exempt — they re-space positions, never sizes)")
    print("   => an ordinary parent's scale multiplies its children's RENDERED")
    print("      SIZE, not just their positions. Scenes built on World Grid")
    print("      globes never meet this; scenes built on torus or sphere")
    print("      parents meet it immediately. Either divide the authored")
    print("      scale by the parent's, or keep the placement parent at")
    print("      scale 1 and carry the radius in the child's translate_z.")
    print("   The optional minimum-glyph-size clamp is measured against the")
    print("   RENDERED scale, so a small authored number is safe:")
    rows = [dict(BASE, id=1, parent_id=0, branch_level=0, topo=3, geometry=6,
                 ratio=0.01, scale_x=126.3, scale_y=126.3, scale_z=126.3),
            dict(BASE, id=2, parent_id=1, branch_level=1, translate_x=0.0,
                 geometry=11, scale_x=0.0119, scale_y=0.0119, scale_z=0.0119)]
    with open(_TMP, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)
    nodes = csv_reader.load_node_csv(_TMP)
    for floor in (0.0, 0.2):
        s = scene_mod.Scene(nodes, scale_floor=floor)
        print(f"     scale_floor {floor:.1f} -> authored 0.0119 renders at "
              f"{float(np.asarray(s.world_scale(2), dtype=float)[0]):.3f}")

    try:
        os.remove(_TMP)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
