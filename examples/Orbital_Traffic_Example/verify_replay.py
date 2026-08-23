#!/usr/bin/env python
"""Does the One Orbit replay put the satellites where they really go?

`verify_scenes.py` checks a static scene. This drives the **real
`ChannelEngine`** — the same object the app's Channels panel drives — through
the replay, pulls each glyph's world position out of the real transform engine
at chosen frames, converts it back to latitude/longitude/altitude, and
compares that against an independent SGP4 propagation to that frame's wall
clock.

In other words: the animation is asked to prove, frame by frame, that it is
still telling the truth several hundred steps after frame 0.

    python verify_replay.py [path/to/one_orbit_gv_node.csv]
"""

from __future__ import annotations

import csv
import datetime as dt
import math
import os
import sys

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
from build_live_sky import KM_PER_UNIT  # noqa: E402
from glyphviz_core import channel_loader, csv_reader  # noqa: E402
from glyphviz_core import scene as scene_mod  # noqa: E402
from glyphviz_core.channel_engine import ChannelEngine  # noqa: E402

GLOBE_R = 180.0 / math.pi
FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def main(path: str) -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    nodes = csv_reader.load_node_csv(path)
    sc = scene_mod.Scene(nodes)
    node_by_id = {n.id: n for n in nodes}

    map_path, tracks_path = channel_loader.find_channel_files(path)
    check("0. GlyphViz auto-discovers exactly one ch-map and one ch-tracks",
          map_path is not None and tracks_path is not None,
          f"{os.path.basename(str(map_path))}, {os.path.basename(str(tracks_path))}"
          if map_path else "none found — two candidates in a folder disable "
                           "Channels entirely")
    if map_path is None:
        return 1

    ch_map = channel_loader.load_ch_map(map_path)
    tracks, id_to_col = channel_loader.load_ch_tracks(tracks_path)
    engine = ChannelEngine()
    engine.load(ch_map, tracks, id_to_col, nodes)
    n_frames = engine.frame_count
    check("1. the engine accepted the bindings", engine.has_bindings,
          f"{n_frames} frames, {len(engine.bound_node_ids)} animated nodes, "
          f"{tracks.shape[1]} track columns")

    # Every map row must have found both a node and a track column. The loader
    # silently drops rows that miss either, so compare the counts.
    map_rows = sum(len(v) for v in ch_map.values())
    ch_in_use = {int(r.get("ch_input_id", 0) or 0) for r in rows} - {0}
    orphan_channels = set(ch_map) - ch_in_use
    orphan_tracks = {t for v in ch_map.values() for t, _ in v} - set(id_to_col)
    check("2. the three-way join is complete",
          not orphan_channels and not orphan_tracks,
          f"{map_rows} bindings, {len(ch_map)} channels, "
          f"{len(orphan_channels)} channels drive no node, "
          f"{len(orphan_tracks)} tracks missing a column")

    # -- rebuild the ground truth ------------------------------------------
    # The scene's own labels carry the NORAD ids; re-fetch those element sets
    # from the cache and propagate them ourselves.
    cache = os.path.join(HERE, "data", "gp_cache")
    import io
    gp = {}
    for fn in sorted(os.listdir(cache)):
        if not fn.endswith(".csv"):
            continue
        text = open(os.path.join(cache, fn), encoding="utf-8").read()
        if not text.lstrip().startswith("OBJECT_NAME"):
            continue
        for r in csv.DictReader(io.StringIO(text)):
            gp.setdefault(int(r["NORAD_CAT_ID"]), r)

    sat_rows = {}
    for r in rows:
        if "CATNR=" in (r.get("link") or ""):
            sat_rows[int(r["link"].rsplit("=", 1)[1])] = r
    check("3. satellites in the scene resolve back to element sets",
          all(n in gp for n in sat_rows), f"{len(sat_rows)} satellites")

    # The replay's t0 is written into the timeline caption.
    t0 = None
    for r in rows:
        if "replay starts" in (r.get("text") or ""):
            stamp = r["text"].split("replay starts", 1)[1].split("UTC")[0].strip()
            t0 = dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=dt.timezone.utc)
    check("4. the replay's start time is recoverable from the scene", t0 is not None,
          f"{t0:%Y-%m-%d %H:%M:%S} UTC" if t0 else "no timeline caption found")
    if t0 is None:
        return 1

    # Step is implied by the caption's span and the frame count.
    span_min = None
    for r in rows:
        if "->" in (r.get("text") or "") and "minutes" in r["text"]:
            span_min = float(r["text"].split("->")[1].strip().split()[0])
    step_s = span_min * 60.0 / n_frames
    print(f"\n  replay: {n_frames} frames x {step_s:g} s from "
          f"{t0:%H:%M:%S} UTC\n")

    norads = sorted(sat_rows)
    sats, _ = orbits.build_sats([("x", gp[n]) for n in norads])
    id_of = {n: int(sat_rows[n]["id"]) for n in norads}

    # -- 5. positions, at frames across the whole span ---------------------
    probes = [0, 1, n_frames // 4, n_frames // 2, (3 * n_frames) // 4, n_frames - 1]
    worst_km, worst_frame = 0.0, None
    worst_alt_km = 0.0
    for f in probes:
        engine.apply_frame(f)
        sc.invalidate()
        when = t0 + dt.timedelta(seconds=f * step_s)
        ok, r_teme, _, lat, lon, alt, theta = orbits.propagate(sats, when)
        for i, n in enumerate(norads):
            if not ok[i]:
                continue
            w = np.asarray(sc.world_pos(id_of[n]), dtype=float)
            radius = float(np.linalg.norm(w))
            scene_alt = (radius - GLOBE_R) * KM_PER_UNIT
            scene_lat = math.degrees(math.asin(max(-1.0, min(1.0, w[2] / radius))))
            scene_lon = math.degrees(math.atan2(w[1], w[0]))
            # Great-circle separation on the ground, in km.
            a, b = math.radians(scene_lat), math.radians(float(lat[i]))
            dlon = math.radians(scene_lon - float(lon[i]))
            cosd = math.sin(a) * math.sin(b) + math.cos(a) * math.cos(b) * math.cos(dlon)
            sep = 6371.0 * math.acos(max(-1.0, min(1.0, cosd)))
            if sep > worst_km:
                worst_km, worst_frame = sep, f
            worst_alt_km = max(worst_alt_km, abs(scene_alt - float(alt[i])))

    # The CSV rounds longitude to 1e-4 deg, which is 11 m at the equator; the
    # altitude track rounds to 1e-4 world units, which is 11 m as well.
    check("5. animated ground position matches an independent propagation",
          worst_km < 0.05,
          f"worst {worst_km * 1000:.1f} m over {len(norads)} satellites x "
          f"{len(probes)} frames (worst at frame {worst_frame}); "
          f"CSV rounding alone is ~11 m")
    check("5b. animated altitude matches", worst_alt_km < 0.05,
          f"worst {worst_alt_km * 1000:.1f} m")

    # -- 6. colour follows the shadow --------------------------------------
    # At each probe frame, every satellite's rendered colour must be its
    # regime hue scaled by the illumination state the model computes.
    from build_live_sky import REGIME_RGB, SHADE
    mismatches, checked = 0, 0
    for f in (0, n_frames // 3, (2 * n_frames) // 3, n_frames - 1):
        engine.apply_frame(f)
        when = t0 + dt.timedelta(seconds=f * step_s)
        jd, fr = orbits.julian(when)
        _, r_teme, _, _, _, _, _ = orbits.propagate(sats, when)
        state = orbits.illumination(r_teme, jd, fr)
        for i, n in enumerate(norads):
            node = node_by_id[id_of[n]]
            regime = orbits.classify(sats[i])
            want = tuple(int(round(max(0, min(255, c * SHADE[int(state[i])]))))
                         for c in REGIME_RGB[regime])
            got = (node.color_r, node.color_g, node.color_b)
            checked += 1
            if got != want:
                mismatches += 1
    check("6. animated colour tracks the umbra/penumbra test",
          mismatches == 0,
          f"{checked} node-frames checked, {mismatches} mismatched")

    # -- 7. the terminator stays 90 deg from the Sun, all the way through ---
    term_ids, sun_id = [], None
    for r in rows:
        rgbv = (int(r["color_r"]), int(r["color_g"]), int(r["color_b"]))
        if int(r["type"]) == 5 and rgbv == (255, 158, 60):
            term_ids.append(int(r["id"]))
        elif int(r["type"]) == 5 and rgbv == (255, 238, 150):
            sun_id = int(r["id"])
    worst_term = 0.0
    for f in probes:
        engine.apply_frame(f)
        sun = node_by_id[sun_id]
        a, b = math.radians(sun.translate_y), math.radians(sun.translate_x)
        for tid in term_ids:
            t = node_by_id[tid]
            la, lo = math.radians(t.translate_y), math.radians(t.translate_x)
            cosd = math.sin(a) * math.sin(la) + math.cos(a) * math.cos(la) * math.cos(lo - b)
            worst_term = max(worst_term,
                             abs(math.degrees(math.acos(max(-1.0, min(1.0, cosd)))) - 90.0))
    check("7. terminator stays on the day/night circle for the whole replay",
          worst_term < 2e-4,
          f"{len(term_ids)} ring nodes x {len(probes)} frames, "
          f"worst {worst_term:.2e} deg")

    # -- 8. the Sun really does sweep west ---------------------------------
    engine.apply_frame(0)
    lon0 = node_by_id[sun_id].translate_x
    engine.apply_frame(n_frames - 1)
    lon1 = node_by_id[sun_id].translate_x
    swept = (lon0 - lon1 + 180.0) % 360.0 - 180.0
    # Earth turns at the *sidereal* rate (360 deg / 1436.07 min), but the Sun
    # creeps ~1 deg/day east along the ecliptic while it does, and that creep
    # cancels part of the rotation. What is left is the *solar* rate,
    # 360 deg / 1440 min — which is the whole reason a solar day runs four
    # minutes longer than a sidereal one. Getting sidereal here would mean the
    # solar model had stopped contributing.
    solar = 360.0 * (span_min / 1440.0)
    sidereal = 360.0 * (span_min / 1436.068)
    check("8. the sub-solar point sweeps west at the solar, not sidereal, rate",
          abs(swept - solar) < 0.1 and abs(swept - sidereal) > 0.03,
          f"{swept:.2f} deg over {span_min:g} min; solar {solar:.2f}, "
          f"sidereal {sidereal:.2f} — residual {swept - solar:+.3f} deg is "
          f"the equation of time over the span")

    # -- 9. Stop restores the authored values ------------------------------
    engine.apply_frame(n_frames // 2)
    moved = node_by_id[id_of[norads[0]]].translate_x
    engine.reset()
    restored = node_by_id[id_of[norads[0]]].translate_x
    csv_value = float(sat_rows[norads[0]]["translate_x"])
    check("9. Stop (reset) restores the CSV's own values",
          abs(restored - csv_value) < 1e-9,
          f"frame {n_frames // 2} had {moved:.3f}, reset gave {restored:.3f}, "
          f"CSV says {csv_value:.3f}")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: " + "; ".join(FAILURES))
        return 1
    print("All checks passed: the replay stays true for its whole span.")
    return 0


if __name__ == "__main__":
    default = os.path.join(HERE, "One_Orbit", "one_orbit_gv_node.csv")
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else default))
