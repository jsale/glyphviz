#!/usr/bin/env python
"""Are the orbital planes real planes, and are the satellites on them?

Orbital Shells is built out of nested rotations, which is exactly the kind of
construction that looks plausible while being wrong.  So this reads the scene
back through the real `glyphviz_core` transform engine and asks whether each
glyph's world position is the satellite's actual inertial position, whether
each drawn ring is genuinely the plane its members orbit in, and whether the
spin rates are the true orbital rates rather than something that merely looks
busy.

    python verify_shells.py [path/to/orbital_shells_gv_node.csv]
"""

from __future__ import annotations

import csv
import datetime as dt
import math
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for candidate in (os.environ.get("GLYPHVIZ_PATH"),
                  os.path.abspath(os.path.join(HERE, "..", "..")),
                  r"C:\Users\jsale\source\repos\glyphviz"):
    if candidate and os.path.isdir(os.path.join(candidate, "glyphviz_core")):
        sys.path.insert(0, candidate)
        break
else:
    raise SystemExit("cannot find glyphviz_core — set GLYPHVIZ_PATH")

import orbits  # noqa: E402
from build_live_sky import KM_PER_UNIT, parse_csv  # noqa: E402
from build_orbital_shells import (BASE_SCALE, CONSTELLATIONS,  # noqa: E402
                                  MIN_RING_MEMBERS, RATE_CYCLES_PER_S,
                                  R_EARTH_UNITS, SIDEREAL_DEG_PER_S,
                                  cluster_planes, osculating_plane)
from glyphviz_core import csv_reader  # noqa: E402
from glyphviz_core import scene as scene_mod  # noqa: E402

FAILURES: list[str] = []

# Published constellation designs — the numbers this scene claims to show.
# Published constellation designs. GEO is deliberately absent: the
# geostationary belt is a shared regime, not an engineered plane structure.
EXPECTED_PLANES = {"gps-ops": 6, "glo-ops": 3, "iridium-NEXT": 6,
                   "galileo": 3}


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def main(path: str) -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    sc = scene_mod.Scene(csv_reader.load_node_csv(path))
    by_id = {int(r["id"]): r for r in rows}
    print(f"Loaded {len(rows):,} nodes from {os.path.basename(path)}\n")

    sat_rows = {int(r["link"].rsplit("=", 1)[1]): r
                for r in rows if "CATNR=" in (r.get("link") or "")}
    check("0. the scene carries resolvable satellites", len(sat_rows) > 100,
          f"{len(sat_rows)} satellites")

    # -- ground truth -------------------------------------------------------
    cache = os.path.join(HERE, "data", "gp_cache")
    gp, group_of = {}, {}
    for _, group, _, _ in CONSTELLATIONS:
        try:
            text = orbits.fetch_group(group, cache, offline=True,
                                      log=lambda *a: None)
        except Exception:
            continue
        for r in parse_csv(text):
            n = int(r["NORAD_CAT_ID"])
            if n not in gp:
                gp[n], group_of[n] = r, group

    norads = sorted(n for n in sat_rows if n in gp)
    sats, _ = orbits.build_sats([(group_of[n], gp[n]) for n in norads])
    by_norad = {s.norad: s for s in sats}

    # The scene's Earth carries the build time in its label.
    t0 = None
    for r in rows:
        if r.get("text", "").startswith("Earth"):
            for tok in r["text"].split(","):
                tok = tok.strip()
                if tok[:4].isdigit() and "-" in tok:
                    t0 = dt.datetime.strptime(tok.split(" UTC")[0],
                                              "%Y-%m-%d %H:%M:%S").replace(
                        tzinfo=dt.timezone.utc)
    check("1. the build time is recoverable from the Earth's label",
          t0 is not None, f"{t0:%Y-%m-%d %H:%M:%S} UTC" if t0 else "not found")
    if t0 is None:
        return 1

    ok, r_teme, v_teme, _, _, _, theta = orbits.propagate(sats, t0)

    # -- 2. every satellite where SGP4 says it is ---------------------------
    # The scene's world frame is TEME: the rings are inertial and the Earth
    # spins inside them, so a glyph's world position should be the propagated
    # TEME vector divided by the km-per-unit scale, with no rotation at all.
    worst_km, worst_name = 0.0, None
    for i, s in enumerate(sats):
        if not ok[i]:
            continue
        w = np.asarray(sc.world_pos(int(sat_rows[s.norad]["id"])), dtype=float)
        want = r_teme[i] / KM_PER_UNIT
        d_km = float(np.linalg.norm(w - want)) * KM_PER_UNIT
        if d_km > worst_km:
            worst_km, worst_name = d_km, s.name
    check("2. every glyph sits at its true inertial position",
          worst_km < 0.05,
          f"worst {worst_km * 1000:.1f} m ({worst_name}) over "
          f"{len(sats)} satellites")

    # -- 3. every satellite has a visible ring, and rides it ---------------
    rings = [r for r in rows if int(r["topo"]) == 3 and not int(r["hide"])]
    all_rings = [r for r in rows if int(r["topo"]) == 3]

    def ring_frame(ring_row):
        raan = math.radians(float(by_id[int(ring_row["parent_id"])]["rotate_z"]))
        inc = math.radians(float(ring_row["rotate_x"]))
        n = np.array([math.sin(inc) * math.sin(raan),
                      -math.sin(inc) * math.cos(raan),
                      math.cos(inc)])
        return n, float(ring_row["scale_x"]) * BASE_SCALE

    def off_ring(sat_row, ring_row):
        n, R = ring_frame(ring_row)
        w = np.asarray(sc.world_pos(int(sat_row["id"])), dtype=float)
        h = abs(float(w @ n))
        in_plane = math.sqrt(max(0.0, float(w @ w) - h * h))
        return math.hypot(h, in_plane - R)

    # The complaint that produced these two checks: circles with nothing
    # following them. Both halves have to hold — every satellite is exactly on
    # its own ring node, AND that ring is close enough to a *drawn* one that
    # nothing appears to float free of the paths.
    worst_off = max(off_ring(r, by_id[int(r["parent_id"])])
                    for r in sat_rows.values())
    check("4. every satellite lies exactly on its own ring node",
          worst_off < 1e-6,
          f"worst {worst_off:.2e} world units over {len(sat_rows)} satellites")

    ring_frames = [ring_frame(r) for r in rings]
    worst_seen, n_far = 0.0, 0
    for r in sat_rows.values():
        w = np.asarray(sc.world_pos(int(r["id"])), dtype=float)
        best = min(math.hypot(abs(float(w @ n)),
                              math.sqrt(max(0.0, float(w @ w)
                                            - float(w @ n) ** 2)) - R)
                   for n, R in ring_frames)
        worst_seen = max(worst_seen, best)
        n_far += best > 3.0
    check("3. every satellite sits on a ring that is actually drawn",
          n_far == 0,
          f"{len(rings)} rings drawn for {len(sat_rows)} satellites "
          f"({len(all_rings) - len(rings)} suppressed as duplicates); "
          f"worst satellite is {worst_seen:.2f} world units "
          f"({worst_seen * KM_PER_UNIT:.0f} km) from the nearest drawn ring, "
          f"inside its own glyph")

    # ...and that ring must be the satellite's real orbit plane.
    worst_norm = 0.0
    for i, s_ in enumerate(sats):
        if not ok[i]:
            continue
        n, _ = ring_frame(by_id[int(sat_rows[s_.norad]["parent_id"])])
        h = np.cross(r_teme[i], v_teme[i])
        h /= np.linalg.norm(h)
        worst_norm = max(worst_norm, float(np.degrees(math.acos(
            max(-1.0, min(1.0, abs(float(n @ h))))))))
    check("4b. each ring's plane is that satellite's real orbit plane",
          worst_norm < 1e-4,
          f"worst {worst_norm:.2e} deg between the drawn ring normal and "
          f"the angular-momentum vector")

    # -- 4c. a ring thin enough to quantise away cannot be selected --------
    # Picking renders the SOLID form of a wireframe, and the torus mesh is
    # cached per ratio rounded to 2 decimals. A ratio under 0.005 becomes a
    # zero-thickness tube: it still draws as wires, but has no silhouette, so
    # neither a click nor a rubber-band region can ever hit it.
    thin = [r for r in rings if round(float(r["ratio"]), 2) <= 0.0]
    check("4c. no ring is too thin to pick", not thin,
          f"{len(rings)} rings, min ratio "
          f"{min(float(r['ratio']) for r in rings):.4f} "
          f"(must round to >= 0.01 at 2 dp)")

    # -- 5. the published plane structure is still recoverable -------------
    # The planes are no longer drawn as separate rings, so re-derive them
    # here rather than counting geometry.
    detail, all_ok = [], True
    for group, expect in EXPECTED_PLANES.items():
        members = [i for i, s_ in enumerate(sats)
                   if ok[i] and group_of[s_.norad] == group]
        elems = {}
        for i in members:
            raan, inc, u, radius = osculating_plane(r_teme[i], v_teme[i])
            elems[i] = (raan, inc, u, radius / KM_PER_UNIT)
        clusters = [g for g in cluster_planes(members, elems)
                    if len(g) >= MIN_RING_MEMBERS]
        detail.append(f"{group} {len(clusters)}/{expect}")
        all_ok &= (len(clusters) == expect)
    check("5. the published plane structure is recoverable from live data",
          all_ok, ", ".join(detail))

    # -- 6. spin rates are the true orbital rates --------------------------
    worst_rate = 0.0
    for s in sats:
        torus = by_id[int(sat_rows[s.norad]["parent_id"])]
        rate = float(torus["rotate_rate_z"])          # deg per 1/60 s cycle
        deg_per_s = rate * RATE_CYCLES_PER_S
        true_deg_per_s = s.mean_motion * 360.0 / 86400.0
        scale = deg_per_s / true_deg_per_s
        worst_rate = max(worst_rate, abs(scale - 300.0))
    check("6. every ring spins at its own true orbital rate",
          worst_rate < 0.01,
          f"all {len(sats)} rings within {worst_rate:.4f} of a single shared "
          f"time scale — the relative rates are exact")

    # -- 7. Earth ----------------------------------------------------------
    earth = [r for r in rows if int(r["topo"]) == 2][0]
    e_scale = float(earth["scale_x"])
    check("7. Earth's rendered radius is one Earth radius",
          abs(e_scale * BASE_SCALE - R_EARTH_UNITS) < 1e-9,
          f"scale {e_scale:.6f} x base_scale {BASE_SCALE:g} = "
          f"{e_scale * BASE_SCALE:.4f} world units "
          f"({e_scale * BASE_SCALE * KM_PER_UNIT:,.0f} km)")

    spin = float(earth["rotate_rate_z"]) * RATE_CYCLES_PER_S
    check("7b. Earth spins at the sidereal rate, on the same time scale",
          abs(spin / SIDEREAL_DEG_PER_S - 300.0) < 0.01,
          f"{spin:.5f} deg/s = {spin / SIDEREAL_DEG_PER_S:.2f}x sidereal "
          f"(a sidereal day in {86164.0905 / 300 / 60:.1f} min)")

    check("7c. Earth's prime meridian is at its true right ascension",
          abs(float(earth["rotate_z"])
              - math.degrees(theta) % 360.0) < 1e-3,
          f"rotate_z {float(earth['rotate_z']):.3f} deg vs GMST "
          f"{math.degrees(theta) % 360.0:.3f} deg")

    # -- 8. landmarks sit ON the surface, not above it ---------------------
    pins = [r for r in rows if int(r["parent_id"]) == int(earth["id"])]
    worst_pin = 0.0
    for r in pins:
        w = np.asarray(sc.world_pos(int(r["id"])), dtype=float)
        worst_pin = max(worst_pin, abs(float(np.linalg.norm(w)) - R_EARTH_UNITS))
    # The pins are authored 0.6 world units proud of the surface so they do
    # not z-fight with the texture. Before the local-units fix they sat 11.46
    # units — 1,275 km — up, as a halo.
    check("8. surface landmarks sit just proud of the surface, not in a halo",
          abs(worst_pin - 0.6) < 1e-3,
          f"{len(pins)} pins at {worst_pin:.4f} world units "
          f"({worst_pin * KM_PER_UNIT:.0f} km); the un-divided translate_z "
          f"would put them at 11.46 units (1,275 km)")

    # -- 9. a landmark's longitude really is its longitude ------------------
    # Greenwich at GMST must point along the ECEF x-axis rotated into TEME.
    gw = [r for r in pins if r.get("text") == "Greenwich"]
    if gw:
        w = np.asarray(sc.world_pos(int(gw[0]["id"])), dtype=float)
        lam = math.radians(float(gw[0]["translate_x"]))
        phi = math.radians(float(gw[0]["translate_y"]))
        local = np.array([math.cos(phi) * math.cos(lam),
                          math.cos(phi) * math.sin(lam), math.sin(phi)])
        c, s_ = math.cos(theta), math.sin(theta)
        want = np.array([local[0] * c - local[1] * s_,
                         local[0] * s_ + local[1] * c, local[2]])
        want *= float(np.linalg.norm(w))
        err = math.degrees(math.acos(max(-1.0, min(1.0,
              float(w @ want) / (np.linalg.norm(w) * np.linalg.norm(want))))))
        check("9. a landmark's lon/lat lands at its true right ascension",
              err < 1e-6,
              f"Greenwich off by {err:.2e} deg — the sphere reads translate_x "
              f"as longitude and rotate_z carries it into the inertial frame")

    # -- 9b. RENDERED glyph size, not authored -----------------------------
    # The check that was missing the first time round. Every satellite was
    # authored at scale ~1.5 and every one passed a raw-scale assertion, while
    # actually drawing at up to 190 world units — bigger than the Earth —
    # because a torus parent's scale multiplies its children's rendered size.
    # Authored scale is not what you see; ask the engine.
    # A glyph's rendered radius is base_scale x its world scale, and world
    # scale carries every ancestor's. Check EVERY visible glyph, not just the
    # satellites: the first fix corrected the satellites and left the surface
    # landmarks drawing at a radius of 51 world units, nearly the size of the
    # Earth they sit on. Anything that is not the Earth should be small.
    # Two things are meant to be big: the Earth, and the plane rings, which are
    # structural geometry sized to the orbit they represent. Everything else is
    # a marker and must read as one.
    earth_id = int(earth["id"])
    ring_ids = {int(r["id"]) for r in rings}
    worst, worst_name, smallest = 0.0, None, 1e9
    for r in rows:
        if int(r["type"]) != 5 or int(r["hide"]):
            continue
        if int(r["id"]) == earth_id or int(r["id"]) in ring_ids:
            continue
        rad = BASE_SCALE * float(max(np.asarray(
            sc.world_scale(int(r["id"])), dtype=float)))
        smallest = min(smallest, rad)
        if rad > worst:
            worst, worst_name = rad, (r.get("text") or "")[:28] or "unlabelled"
    check("9b. every visible glyph's RENDERED size is sane",
          worst <= 0.25 * R_EARTH_UNITS,
          f"rendered radius {smallest:.2f} to {worst:.2f} world units "
          f"(largest: {worst_name}); Earth is {R_EARTH_UNITS:.1f}. "
          f"Authored scale is not what you see — ask the engine")

    # -- 10. nothing inside the Earth --------------------------------------
    buried = 0
    for n, r in sat_rows.items():
        w = np.asarray(sc.world_pos(int(r["id"])), dtype=float)
        if float(np.linalg.norm(w)) < R_EARTH_UNITS:
            buried += 1
    check("10. no satellite is inside the Earth", buried == 0,
          f"{len(sat_rows)} checked")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: " + "; ".join(FAILURES))
        return 1
    print("All checks passed: the planes are real and the satellites are on them.")
    return 0


def _ring_group(ring_row, rows):
    """Which constellation a visible ring belongs to, by its colour."""
    rgb = (int(ring_row["color_r"]), int(ring_row["color_g"]),
           int(ring_row["color_b"]))
    for _, group, _, c in CONSTELLATIONS:
        if tuple(c) == rgb:
            return group
    return None


if __name__ == "__main__":
    default = os.path.join(HERE, "Orbital_Shells", "orbital_shells_gv_node.csv")
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else default))
