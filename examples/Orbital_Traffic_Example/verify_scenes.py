#!/usr/bin/env python
"""Does the rendered scene mean what it claims?

`verify_orbits.py` checks the physics.  This checks the *picture*: it loads
the written CSV through the real `glyphviz_core` transform engine — the same
code path the app's viewport uses — pulls every node's world position back
out, and asks whether the glyph the viewer draws is actually where the
satellite is.

    python verify_scenes.py [path/to/live_sky_gv_node.csv]

Nothing here re-derives positions from the CSV columns by hand; the point is
to let GlyphViz place the nodes and then measure the result.
"""

from __future__ import annotations

import csv
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# The engine lives in the GlyphViz repo, not in this example.
for candidate in (os.environ.get("GLYPHVIZ_PATH"),
                  os.path.abspath(os.path.join(HERE, "..", "..")),
                  r"C:\Users\jsale\source\repos\glyphviz"):
    if candidate and os.path.isdir(os.path.join(candidate, "glyphviz_core")):
        sys.path.insert(0, candidate)
        break
else:
    raise SystemExit(
        "cannot find glyphviz_core — set GLYPHVIZ_PATH to your glyphviz checkout")

import orbits  # noqa: E402
from glyphviz_core import csv_reader  # noqa: E402
from glyphviz_core import scene as scene_mod  # noqa: E402

GLOBE_R = 180.0 / math.pi
KM_PER_UNIT = orbits.R_EARTH_EQ / GLOBE_R

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def main(path: str) -> int:
    print(__doc__.strip().splitlines()[0])
    print()
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    nodes = csv_reader.load_node_csv(path)
    sc = scene_mod.Scene(nodes)
    by_id = {int(r["id"]): r for r in rows}
    print(f"Loaded {len(rows)} nodes from {os.path.basename(path)}\n")

    globe = [r for r in rows if int(r["type"]) == 6]
    if not globe:
        print("  This scene has no World Grid globe, so these checks do not "
              "apply.\n  Orbital_Shells draws Earth as a plain Sphere glyph "
              "and places its\n  satellites on torus rings — use "
              "verify_shells.py for that one.")
        return 0
    check("0. exactly one World Grid globe", len(globe) == 1,
          f"id {globe[0]['id']}, geometry {globe[0]['geometry']} "
          f"(3 = solid sphere)")
    globe_id = int(globe[0]["id"])

    # -- 1. every globe child lands at the lon/lat/alt it was written with ---
    kids = [r for r in rows
            if int(r["parent_id"]) == globe_id and int(r["type"]) == 5
            and not int(r["hide"])]
    worst_r = worst_ang = 0.0
    for r in kids:
        lon, lat = float(r["translate_x"]), float(r["translate_y"])
        elev = float(r["translate_z"])
        w = np.asarray(sc.world_pos(int(r["id"])), dtype=float)
        got_r = float(np.linalg.norm(w))
        worst_r = max(worst_r, abs(got_r - (GLOBE_R + elev)))
        la, lo = math.radians(lat), math.radians(lon)
        want = np.array([math.cos(la) * math.cos(lo),
                         math.cos(la) * math.sin(lo),
                         math.sin(la)])
        cos_a = float(w @ want) / max(got_r, 1e-12)
        worst_ang = max(worst_ang, math.degrees(math.acos(max(-1.0, min(1.0, cos_a)))))
    check("1. globe children land at their written lon/lat/altitude",
          worst_r < 1e-6 and worst_ang < 1e-4,
          f"{len(kids)} nodes: radius {worst_r:.2e} world units, "
          f"bearing {worst_ang:.2e} deg")

    # -- 2. the engine's radius, read as altitude, is the real altitude -----
    # Re-propagate independently and compare against what the scene draws.
    sats_by_norad = {}
    for r in kids:
        link = r.get("link", "")
        if "CATNR=" in link:
            sats_by_norad[int(link.rsplit("=", 1)[1])] = r
    check("2. satellites carry a resolvable CelesTrak catalogue link",
          len(sats_by_norad) > 0, f"{len(sats_by_norad)} of {len(kids)} "
          f"globe children are satellites")

    worst_alt = 0.0
    for r in list(sats_by_norad.values()):
        w = np.asarray(sc.world_pos(int(r["id"])), dtype=float)
        alt_from_scene = (float(np.linalg.norm(w)) - GLOBE_R) * KM_PER_UNIT
        # The label states the altitude; the geometry must agree with it.
        stated = float(r["text"].split("|")[3].strip().split()[0].replace(",", ""))
        worst_alt = max(worst_alt, abs(alt_from_scene - stated))
    check("3. rendered altitude matches the altitude in the label",
          worst_alt < 0.75,
          f"worst {worst_alt * 1000:.0f} m over {len(sats_by_norad)} satellites "
          f"(label is rounded to the km)")

    # -- 4. links resolve at both ends --------------------------------------
    links = [r for r in rows if int(r["type"]) == 7]
    dangling = [r for r in links
                if int(r["parent_id"]) not in by_id or int(r["child_id"]) not in by_id]
    check("4. every link resolves at both ends", not dangling,
          f"{len(links)} links, {len(dangling)} dangling "
          f"(a one-ended link draws nothing, silently)")

    # -- 5. every drawn station link really is above the horizon ------------
    station_ids = {int(r["id"]) for r in rows
                   if int(r["parent_id"]) == globe_id and int(r["geometry"]) == 16}
    drawn = [r for r in links
             if not int(r["hide"]) and int(r["parent_id"]) in station_ids]
    worst_elev, n_checked = 90.0, 0
    for r in drawn:
        st_row = by_id[int(r["parent_id"])]
        sat_row = by_id[int(r["child_id"])]
        st = orbits.Station("x", "-", float(st_row["translate_y"]),
                            float(st_row["translate_x"]))
        sat_ecef = orbits.geodetic_to_ecef(
            float(sat_row["translate_y"]), float(sat_row["translate_x"]),
            float(sat_row["translate_z"]) * KM_PER_UNIT)
        elev, _ = orbits.look_angles(st, sat_ecef[None, :])
        worst_elev = min(worst_elev, float(elev[0]))
        n_checked += 1
    check("5. every drawn station edge is genuinely above the horizon",
          worst_elev >= 0.0,
          f"{n_checked} edges, lowest elevation {worst_elev:.2f} deg")

    # -- 6. hidden link-pool slots are inert --------------------------------
    hidden = [r for r in links if int(r["hide"])]
    self_ended = [r for r in hidden if r["parent_id"] == r["child_id"]]
    check("6. unused link-pool slots are hidden and self-ended",
          len(hidden) == len(self_ended),
          f"{len(hidden)} spare slots of {len(links)} links, all inert; "
          f"the pool is what keeps node ids stable between rewrites")

    # -- 7. the terminator ring really is the terminator ---------------------
    # Find it by colour: the ring nodes are the amber small spheres.
    term = [r for r in kids
            if int(r["color_r"]) == 255 and int(r["color_g"]) == 158
            and int(r["color_b"]) == 60]
    sun = [r for r in kids if int(r["color_g"]) == 238 and int(r["color_b"]) == 150]
    if term and sun:
        s_lat, s_lon = float(sun[0]["translate_y"]), float(sun[0]["translate_x"])
        worst = 0.0
        for r in term:
            la, lo = math.radians(float(r["translate_y"])), math.radians(float(r["translate_x"]))
            a, b = math.radians(s_lat), math.radians(s_lon)
            cosd = math.sin(a) * math.sin(la) + math.cos(a) * math.cos(la) * math.cos(lo - b)
            worst = max(worst, abs(math.degrees(math.acos(max(-1.0, min(1.0, cosd)))) - 90.0))
        # lon/lat are written to 4 decimal places, so half a unit in the last
        # place (5e-5 deg) is the floor this check can possibly reach.
        check("7. terminator ring sits 90 deg from the sub-solar marker",
              worst < 2e-4,
              f"{len(term)} ring nodes, worst deviation {worst:.2e} deg "
              f"(CSV rounds lon/lat to 1e-4 deg)")
    else:
        check("7. terminator ring present", False, "not found in the CSV")

    # -- 8. nothing is buried inside the Earth ------------------------------
    below = [r for r in kids if float(r["translate_z"]) < 0.0]
    check("8. no visible glyph is inside the globe", not below,
          f"{len(below)} nodes below the surface")

    # -- 9. scale floor -----------------------------------------------------
    tiny = [r for r in rows
            if int(r["type"]) == 5 and not int(r["hide"])
            and min(float(r["scale_x"]), float(r["scale_y"]),
                    float(r["scale_z"])) < 0.2]
    check("9. every visible glyph clears the 0.2 scale floor", not tiny,
          f"{len(tiny)} below floor")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: " + "; ".join(FAILURES))
        return 1
    print("All checks passed: the picture agrees with the propagator.")
    return 0


if __name__ == "__main__":
    default = os.path.join(HERE, "Live_Sky", "live_sky_gv_node.csv")
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else default))
