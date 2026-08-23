#!/usr/bin/env python
"""One Orbit — ninety-three minutes of low Earth orbit, replayable.

Live Sky shows near-Earth space moving at 1x, which is honest and far too slow
to perceive: the ISS takes 93 real minutes to go round once.  This scene
precomputes that whole revolution into GlyphViz Channels tracks, so pressing
Space replays it in about twenty seconds — and the orbital motion, which was
invisible in real time, becomes the entire point.

Three things move together on one clock:

  * **The satellites**, along their real SGP4 trajectories.
  * **Their colour**, as each one crosses into and out of Earth's shadow —
    the conical umbra/penumbra test from `orbits.py`, evaluated per frame.
  * **The terminator and sub-solar point**, which slide 23 degrees west while
    the shell goes round once.  The day/night line is not a backdrop here;
    it is what the satellites are flying through.

Nothing is fetched at view time and nothing is propagated at view time: the
scene is pure CSV, and the viewer plays back numbers computed ahead of it.

Usage
-----
    python build_one_orbit.py                  # 93 min, 10 s steps, from cache
    python build_one_orbit.py --minutes 186    # two revolutions
    python build_one_orbit.py --step 5         # smoother, twice the tracks
    python build_one_orbit.py --max-alt-km 800 # just the crowded shell
    python build_one_orbit.py --fetch          # refresh elements first
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import math
import os
import shutil
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import orbits  # noqa: E402
from build_live_sky import (BG, COLUMNS, DEFAULT_GROUPS,  # noqa: E402
                            GEO_BY_TYPE, GEO_LINE, GEO_OCTA, GEO_SPHERE,
                            GEO_UNKNOWN, KM_PER_UNIT, REGIME_NOTE,
                            REGIME_ORDER, REGIME_RGB, SHADE, SHADE_NOTE,
                            SUN_RGB, TAG_FONT_PT, TERM_RGB, dim, glyph_scale,
                            load_satcat, parse_csv, sanitize)
from orbits import LIT, PENUMBRA, UMBRA  # noqa: E402

# Live Sky has no animation, so its column set carries neither the Channels
# opt-in nor the spin rate this scene's cursor uses.
NODE_COLUMNS = COLUMNS[:-2] + ["ch_input_id", "rotate_rate_z"] + COLUMNS[-2:]
NODE_DEFAULTS = {c: 0 for c in NODE_COLUMNS}
NODE_DEFAULTS.update(scale_x=1.0, scale_y=1.0, scale_z=1.0, color_a=255,
                     ratio=0.1, text="", link="")

# ---------------------------------------------------------------------------
# 1. Scene constants
# ---------------------------------------------------------------------------
OUT_DIR = os.path.join(HERE, "One_Orbit")
STEM = "one_orbit_gv"

N_TERMINATOR = 120                # the ring only has to read as a curve
TRAIL_STEP_S = 60.0               # one trail marker a minute
LEGEND_X = -118.0
BAR_Z = -88.0                     # timeline, south of the globe
BAR_HALF = 62.0
TRAIL_DIM = 0.45

# Objects whose full orbit is drawn as a static trail, so the eye has
# something to follow while the swarm sweeps.  Matched on name prefix.
TRAIL_NAMES = ["ISS (ZARYA)", "CSS (TIANHE)", "HST", "TERRA", "AQUA",
               "LANDSAT 9", "SENTINEL-2A", "NOAA 20"]

# Channel/track id blocks, kept far apart so the three-way join reads clearly
# in a diff.  A satellite gets ONE channel driving six attributes; the six
# tracks come from these blocks.
CH_SAT = 1_000                    # + index -> the satellite's channel
TR_X, TR_Y, TR_Z = 1_000, 100_000, 200_000        # + index
TR_COLOR = 300_000                # deduplicated colour tracks, allocated in 3s
CH_TERM = 500_000                 # + index (channel and longitude track alike)
TR_TERM_LAT = 550_000             # + index -> the ring's latitude track
CH_SUN, CH_CURSOR = 600_001, 600_002
TR_SUN, TR_SUN_LAT, TR_CURSOR = 600_001, 600_003, 600_002


# ---------------------------------------------------------------------------
# 2. Scene assembly
# ---------------------------------------------------------------------------
class OrbitScene:
    def __init__(self, sats, meta, n_frames, trail_idx):
        self.rows: list[dict] = []
        self.map_rows: list[dict] = []
        self.tracks: dict[int, list] = {}
        self.sats, self.meta = sats, meta
        self.n_frames = n_frames
        self.trail_idx = trail_idx
        self.next_id = 1

    # -- rows ---------------------------------------------------------------
    def add(self, **kw) -> int:
        row = dict(NODE_DEFAULTS)
        row.update(kw)
        if "id" not in kw:
            row["id"] = self.next_id
        self.next_id = max(self.next_id, row["id"] + 1)
        self.rows.append(row)
        return row["id"]

    # -- channels -----------------------------------------------------------
    def track(self, track_id: int, values) -> int:
        if len(values) != self.n_frames:
            raise SystemExit(f"track {track_id}: {len(values)} values for "
                             f"{self.n_frames} frames")
        self.tracks[track_id] = values
        return track_id

    def bind(self, channel_id: int, track_id: int, attribute: str) -> None:
        self.map_rows.append(dict(channel_id=channel_id, track_id=track_id,
                                  attribute=attribute))


def build(sats, meta, args, log):
    # -- the clock ----------------------------------------------------------
    t0 = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    n_frames = int(args.minutes * 60 / args.step)
    times = [t0 + dt.timedelta(seconds=k * args.step) for k in range(n_frames)]
    log(f"{n_frames} frames x {args.step:g} s = {args.minutes:g} min "
        f"from {t0:%Y-%m-%d %H:%M:%S} UTC")

    # -- propagate the whole span in one shot -------------------------------
    jds, frs = zip(*(orbits.julian(t) for t in times))
    arr_jd, arr_fr = np.array(jds), np.array(frs)
    from sgp4.api import SatrecArray
    tic = time.perf_counter()
    err, r, v = SatrecArray([s.satrec for s in sats]).sgp4(arr_jd, arr_fr)
    log(f"propagated {len(sats)} x {n_frames} = {len(sats) * n_frames:,} "
        f"states in {(time.perf_counter() - tic) * 1000:.0f} ms")

    ok_all = err == 0                                   # (n_sat, n_frame)
    keep = ok_all.all(axis=1)
    r = np.where(ok_all[..., None], r, 0.0)

    # Geodetic sub-points, frame by frame (the rotation differs per frame).
    lat = np.zeros(r.shape[:2]); lon = np.zeros(r.shape[:2])
    alt = np.zeros(r.shape[:2]); state = np.zeros(r.shape[:2], dtype=np.int8)
    for k in range(n_frames):
        theta = orbits.gmst_rad(arr_jd[k], arr_fr[k])
        la, lo, al = orbits.ecef_to_geodetic(orbits.teme_to_ecef(r[:, k, :], theta))
        lat[:, k], lon[:, k], alt[:, k] = la, lo, al
        state[:, k] = orbits.illumination(r[:, k, :], arr_jd[k], arr_fr[k])

    # An object must stay inside the altitude window for the whole replay,
    # otherwise it would pop in and out mid-flight for no visible reason.
    if args.max_alt_km is not None:
        keep &= (alt <= args.max_alt_km).all(axis=1)
    keep &= (alt > 0.0).all(axis=1)

    idx = np.where(keep)[0]
    log(f"{len(idx)} objects survive the whole span "
        f"({len(sats) - len(idx)} dropped: decayed, out of range, or "
        f"unpropagatable)")

    sats = [sats[i] for i in idx]
    meta = [meta[i] for i in idx]
    lat, lon, alt, state = lat[idx], lon[idx], alt[idx], state[idx]

    trail_idx = [i for i, s in enumerate(sats)
                 if any(s.name.upper().startswith(t.upper()) for t in TRAIL_NAMES)]
    log(f"drawing full-orbit trails for {len(trail_idx)}: "
        + ", ".join(sats[i].name for i in trail_idx))

    sc = OrbitScene(sats, meta, n_frames, trail_idx)

    # -- static furniture ---------------------------------------------------
    sc.add(type=0, parent_id=0, branch_level=0, geometry=0,
           color_r=BG[0], color_g=BG[1], color_b=BG[2], color_a=BG[3],
           tag_color_mode=1, tag_font_size=TAG_FONT_PT)
    globe_id = sc.add(type=6, parent_id=0, branch_level=0,
                      geometry=GEO_SPHERE, texture_id=1,
                      segments_x=36, segments_y=18,
                      color_r=64, color_g=96, color_b=132, color_a=255)

    legend(sc, args)
    timeline(sc, t0, args, n_frames)

    # -- the satellites -----------------------------------------------------
    color_pool: dict[tuple, tuple[int, int, int]] = {}
    next_color = [TR_COLOR]

    for i, sat in enumerate(sats):
        m = meta[i]
        s = m["scale"] * args.glyph_scale
        ch = CH_SAT + i
        nid = sc.add(type=5, parent_id=globe_id, branch_level=1,
                     translate_x=round(float(lon[i, 0]), 4),
                     translate_y=round(float(lat[i, 0]), 4),
                     translate_z=round(float(alt[i, 0]) / KM_PER_UNIT, 4),
                     scale_x=s, scale_y=s, scale_z=s,
                     geometry=m["geometry"], ch_input_id=ch,
                     **rgb_kw(dim(REGIME_RGB[m["regime"]], SHADE[int(state[i, 0])])),
                     text=sanitize(
                         f"{sat.name}  |  {sat.norad}  |  {m['regime']}  |  "
                         f"{alt[i, 0]:,.0f} km  |  {m['owner']}"),
                     link=f"https://celestrak.org/satcat/table-satcat.php"
                          f"?CATNR={sat.norad}")
        m["node_id"] = nid

        sc.bind(ch, sc.track(TR_X + i, [round(float(x), 4) for x in lon[i]]),
                "translate_x")
        sc.bind(ch, sc.track(TR_Y + i, [round(float(x), 4) for x in lat[i]]),
                "translate_y")
        sc.bind(ch, sc.track(TR_Z + i,
                             [round(float(a) / KM_PER_UNIT, 4) for a in alt[i]]),
                "translate_z")

        # Colour is regime hue x illumination shade, and the hue never moves.
        # Any two objects whose *shadow history* is identical therefore need
        # exactly the same three colour tracks — which happens constantly,
        # because most satellites are simply lit for the whole span. Sharing
        # them is what keeps the tracks file from tripling in width.
        key = (m["regime"], state[i].tobytes())
        if key not in color_pool:
            base = REGIME_RGB[m["regime"]]
            seq = [dim(base, SHADE[int(st)]) for st in state[i]]
            t = next_color[0]
            next_color[0] += 3
            color_pool[key] = (
                sc.track(t, [c[0] for c in seq]),
                sc.track(t + 1, [c[1] for c in seq]),
                sc.track(t + 2, [c[2] for c in seq]),
            )
        tr, tg, tb = color_pool[key]
        sc.bind(ch, tr, "color_r")
        sc.bind(ch, tg, "color_g")
        sc.bind(ch, tb, "color_b")

    log(f"colour tracks: {len(color_pool) * 3} after sharing "
        f"(vs {len(sats) * 3} per-node) — "
        f"{len(color_pool)} distinct shadow histories among {len(sats)} objects")

    # -- trails -------------------------------------------------------------
    n_trail = trails(sc, globe_id, sats, meta, lat, lon, alt, args)
    log(f"{n_trail} trail markers")

    # -- Sun, terminator ----------------------------------------------------
    sun_terminator(sc, globe_id, times, n_frames)

    return sc, times


def rgb_kw(rgb):
    return dict(color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=255)


def legend(sc, args):
    z = 46.0
    sc.add(type=5, parent_id=0, branch_level=0,
           translate_x=LEGEND_X, translate_y=0.0, translate_z=z,
           scale_x=2.0, scale_y=2.0, scale_z=2.0, geometry=GEO_OCTA,
           color_r=255, color_g=255, color_b=255, color_a=255, show_text=1,
           text="Space plays one orbit; Shift+Space resets")
    for regime in REGIME_ORDER:
        z -= 11.0
        rgb = REGIME_RGB[regime]
        sc.add(type=5, parent_id=0, branch_level=0,
               translate_x=LEGEND_X, translate_y=0.0, translate_z=z,
               scale_x=2.4, scale_y=2.4, scale_z=2.4, geometry=GEO_OCTA,
               **rgb_kw(rgb), show_text=1, text=REGIME_NOTE[regime])
    z -= 16.0
    for st in (LIT, PENUMBRA, UMBRA):
        sc.add(type=5, parent_id=0, branch_level=0,
               translate_x=LEGEND_X, translate_y=0.0, translate_z=z,
               scale_x=2.4, scale_y=2.4, scale_z=2.4, geometry=GEO_OCTA,
               **rgb_kw(dim(REGIME_RGB[orbits.LEO], SHADE[st])), show_text=1,
               text=SHADE_NOTE[st])
        z -= 11.0


def timeline(sc, t0, args, n_frames):
    """A UTC bar with a channel-driven cursor — the scene's only clock.

    Channels cannot animate label text, so the readout has to be geometry:
    static ticks that say what time they are, and a marker that slides.
    """
    sc.add(type=5, parent_id=0, branch_level=0,
           translate_x=-BAR_HALF, translate_y=0.0, translate_z=BAR_Z + 7.0,
           scale_x=2.0, scale_y=2.0, scale_z=2.0, geometry=GEO_OCTA,
           color_r=255, color_g=196, color_b=92, color_a=255, show_text=1,
           text=sanitize(f"replay starts {t0:%Y-%m-%d %H:%M:%S} UTC  ->  "
                         f"{args.minutes:g} minutes"))

    ticks = 7
    prev = None
    for k in range(ticks):
        frac = k / (ticks - 1)
        x = -BAR_HALF + 2.0 * BAR_HALF * frac
        mins = args.minutes * frac
        nid = sc.add(type=5, parent_id=0, branch_level=0,
                     translate_x=round(x, 3), translate_y=0.0, translate_z=BAR_Z,
                     scale_x=0.9, scale_y=0.9, scale_z=0.9, geometry=GEO_OCTA,
                     color_r=255, color_g=196, color_b=92, color_a=220,
                     show_text=1,
                     text=sanitize(f"T+{mins:.0f} min  "
                                   f"{(t0 + dt.timedelta(minutes=mins)):%H:%M}"))
        if prev is not None:
            sc.add(type=7, parent_id=prev, child_id=nid, branch_level=1,
                   geometry=GEO_LINE, ratio=0.06,
                   color_r=255, color_g=196, color_b=92, color_a=160)
        prev = nid

    cursor = sc.add(type=5, parent_id=0, branch_level=0,
                    translate_x=-BAR_HALF, translate_y=0.0, translate_z=BAR_Z + 3.2,
                    scale_x=2.4, scale_y=2.4, scale_z=2.4, geometry=GEO_OCTA,
                    color_r=255, color_g=255, color_b=255, color_a=255,
                    rotate_rate_z=1.2, ch_input_id=CH_CURSOR)
    sc.bind(CH_CURSOR,
            sc.track(TR_CURSOR,
                     [round(-BAR_HALF + 2.0 * BAR_HALF * k / max(1, n_frames - 1), 4)
                      for k in range(n_frames)]),
            "translate_x")
    return cursor


def trails(sc, globe_id, sats, meta, lat, lon, alt, args):
    """Static markers along the full path of a few recognisable objects."""
    every = max(1, int(round(TRAIL_STEP_S / args.step)))
    n = 0
    for i in sc.trail_idx:
        rgb = dim(REGIME_RGB[meta[i]["regime"]], TRAIL_DIM)
        prev = prev_lon = None
        for k in range(0, lat.shape[1], every):
            lo = float(lon[i, k])
            nid = sc.add(type=5, parent_id=globe_id, branch_level=1,
                         translate_x=round(lo, 4),
                         translate_y=round(float(lat[i, k]), 4),
                         translate_z=round(float(alt[i, k]) / KM_PER_UNIT, 4),
                         scale_x=0.35, scale_y=0.35, scale_z=0.35,
                         geometry=GEO_SPHERE, **rgb_kw(rgb))
            # A link is a straight chord between two world positions, so
            # joining the samples either side of the antimeridian would drive
            # a line clean through the planet. Break the trail there instead.
            if prev is not None and abs(lo - prev_lon) < 180.0:
                sc.add(type=7, parent_id=prev, child_id=nid, branch_level=2,
                       geometry=GEO_LINE, ratio=0.05,
                       color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                       color_a=150)
            prev, prev_lon = nid, lo
            n += 1
        # Name the trail once, at its start.
        sc.add(type=5, parent_id=globe_id, branch_level=1,
               translate_x=round(float(lon[i, 0]), 4),
               translate_y=round(float(lat[i, 0]), 4),
               translate_z=round(float(alt[i, 0]) / KM_PER_UNIT + 1.6, 4),
               scale_x=0.6, scale_y=0.6, scale_z=0.6, geometry=GEO_OCTA,
               **rgb_kw(rgb), show_text=1,
               text=sanitize(f"{sats[i].name} — start of replay"))
    return n


def sun_terminator(sc, globe_id, times, n_frames):
    """The sub-solar point and the day/night great circle, both animated.

    The sub-solar longitude sweeps about 23 degrees west over one orbit, which
    dominates; the declination drifts only ~0.02 degrees in the same span.  It
    is tempting to animate longitude alone and let latitude sit still — but
    that approximation is not free.  Freezing the ring's latitudes leaves it
    up to 0.016 degrees off the true terminator by the end of the replay, and
    `verify_replay.py` measures exactly that.  Two hundred and forty tracks
    instead of a hundred and twenty is a cheap price for a day/night line that
    is still the day/night line at frame 557, so both axes get a track.
    """
    subs = [orbits.subsolar_point(t) for t in times]
    rings = [orbits.terminator_ring(la, lo, N_TERMINATOR) for la, lo in subs]

    sun_id = sc.add(type=5, parent_id=globe_id, branch_level=1,
                    translate_x=round(subs[0][1], 4),
                    translate_y=round(subs[0][0], 4), translate_z=2.5,
                    scale_x=3.0, scale_y=3.0, scale_z=3.0, geometry=GEO_SPHERE,
                    **rgb_kw(SUN_RGB), show_text=1, ch_input_id=CH_SUN,
                    text=sanitize("sub-solar point (Sun overhead)"))
    sc.bind(CH_SUN, sc.track(TR_SUN, [round(s[1], 4) for s in subs]),
            "translate_x")
    sc.bind(CH_SUN, sc.track(TR_SUN_LAT, [round(s[0], 4) for s in subs]),
            "translate_y")

    ids = []
    for k in range(N_TERMINATOR):
        la, lo = rings[0][k]
        ch = CH_TERM + k
        nid = sc.add(type=5, parent_id=globe_id, branch_level=1,
                     translate_x=round(lo, 4), translate_y=round(la, 4),
                     translate_z=0.45,
                     scale_x=0.4, scale_y=0.4, scale_z=0.4,
                     geometry=GEO_SPHERE, **rgb_kw(TERM_RGB), ch_input_id=ch)
        sc.bind(ch, sc.track(ch, [round(rings[f][k][1], 4)
                                  for f in range(n_frames)]), "translate_x")
        sc.bind(ch, sc.track(TR_TERM_LAT + k, [round(rings[f][k][0], 4)
                                               for f in range(n_frames)]),
                "translate_y")
        ids.append(nid)
    for k, nid in enumerate(ids):
        sc.add(type=7, parent_id=nid, child_id=ids[(k + 1) % len(ids)],
               branch_level=2, geometry=GEO_LINE, ratio=0.07,
               color_r=TERM_RGB[0], color_g=TERM_RGB[1], color_b=TERM_RGB[2],
               color_a=210)


# ---------------------------------------------------------------------------
# 3. Validation — nothing in the Channels join warns on its own
# ---------------------------------------------------------------------------
BINDABLE = {"translate_x", "translate_y", "translate_z",
            "rotate_x", "rotate_y", "rotate_z",
            "scale_x", "scale_y", "scale_z",
            "color_r", "color_g", "color_b", "color_a",
            "palette_id", "color_index", "ratio", "topo", "topo_scale",
            "geometry", "mesh_id", "texture_id", "hide", "show_text"}


def validate(sc):
    ids = [r["id"] for r in sc.rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate node ids")
    known = set(ids)
    for r in sc.rows:
        if r["parent_id"] and r["parent_id"] not in known:
            raise SystemExit(f"node {r['id']}: dangling parent")
        if r["type"] == 7 and r["child_id"] not in known:
            raise SystemExit(f"link {r['id']}: dangling child_id")
        if not r["hide"] and r["type"] == 5 and min(
                r["scale_x"], r["scale_y"], r["scale_z"]) < 0.2:
            raise SystemExit(f"node {r['id']}: below the 0.2 scale floor")
        for c in ("color_r", "color_g", "color_b", "color_a"):
            if not 0 <= r[c] <= 255:
                raise SystemExit(f"node {r['id']}: {c} = {r[c]}")

    # The three-way join: node.ch_input_id -> map.channel_id -> tracks column.
    # Every one of these can break silently at load time.
    channels = {m["channel_id"] for m in sc.map_rows}
    for r in sc.rows:
        ch = r.get("ch_input_id", 0)
        if ch and ch not in channels:
            raise SystemExit(f"node {r['id']}: ch_input_id {ch} has no map row")
    for m in sc.map_rows:
        if m["track_id"] not in sc.tracks:
            raise SystemExit(f"channel {m['channel_id']}: track "
                             f"{m['track_id']} has no ch<id> column")
        if m["attribute"] not in BINDABLE:
            raise SystemExit(f"channel {m['channel_id']}: attribute "
                             f"{m['attribute']!r} is silently ignored on load")
    bound = {m["channel_id"] for m in sc.map_rows}
    used = {r.get("ch_input_id", 0) for r in sc.rows} - {0}
    if bound - used:
        raise SystemExit(f"{len(bound - used)} channels drive no node")
    for tid, vals in sc.tracks.items():
        if len(vals) != sc.n_frames:
            raise SystemExit(f"track {tid}: ragged ({len(vals)} rows)")
        if any(v is None or (isinstance(v, float) and not math.isfinite(v))
               for v in vals):
            raise SystemExit(f"track {tid}: non-finite value")


def write_nodes(rows, path):
    """Temp file + os.replace, so a reload never sees a torn CSV."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=NODE_COLUMNS,
                           lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def write_channels(sc, out_dir, stem, log):
    map_path = os.path.join(out_dir, f"{stem}_ch-map.csv")
    tracks_path = os.path.join(out_dir, f"{stem}_ch-tracks.csv")

    tmp = map_path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["channel_id", "track_id", "attribute"],
                           lineterminator="\r\n")
        w.writeheader()
        w.writerows(sc.map_rows)
    os.replace(tmp, map_path)

    tids = sorted(sc.tracks)
    header = ["cyclecount"] + [f"ch{t}" for t in tids]
    cols = [sc.tracks[t] for t in tids]
    tmp = tracks_path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(header)
        for k in range(sc.n_frames):
            w.writerow([k] + [c[k] for c in cols])
    os.replace(tmp, tracks_path)

    log(f"  {os.path.basename(map_path)}    {len(sc.map_rows):,} bindings")
    log(f"  {os.path.basename(tracks_path)} {sc.n_frames} frames x "
        f"{len(tids):,} tracks  "
        f"({os.path.getsize(tracks_path) / 1e6:.1f} MB)")


# ---------------------------------------------------------------------------
# 4. Main
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build the One Orbit Channels replay scene.")
    ap.add_argument("--groups", nargs="+", default=DEFAULT_GROUPS)
    ap.add_argument("--minutes", type=float, default=93.0,
                    help="span of the replay (default 93 = one ISS orbit)")
    ap.add_argument("--step", type=float, default=10.0,
                    help="seconds between frames (default 10)")
    ap.add_argument("--max-alt-km", type=float, default=2000.0,
                    help="LEO only by default; raise to include MEO/GEO")
    ap.add_argument("--glyph-scale", type=float, default=1.1)
    ap.add_argument("--fetch", action="store_true",
                    help="refresh element sets (respects the 2 h limit)")
    ap.add_argument("--out-dir", default=OUT_DIR)
    args = ap.parse_args(argv)

    log = print
    log("One Orbit - a full revolution as a Channels replay\n")

    cache = os.path.join(HERE, "data", "gp_cache")
    rows = []
    for g in args.groups:
        try:
            rows += [(g, r) for r in parse_csv(
                orbits.fetch_group(g, cache, offline=not args.fetch, log=log))]
        except Exception as e:
            log(f"  ! {g}: {e} - skipped")
    seen, uniq = set(), []
    for g, r in rows:
        if r.get("NORAD_CAT_ID") and r["NORAD_CAT_ID"] not in seen:
            seen.add(r["NORAD_CAT_ID"])
            uniq.append((g, r))
    if not uniq:
        raise SystemExit("no element sets available")

    satcat = load_satcat(os.path.join(HERE, "data", "satcat.csv"),
                         offline=not args.fetch, log=log)
    sats, bad = orbits.build_sats(uniq)
    sats.sort(key=lambda s: s.norad)
    meta = []
    for s in sats:
        info = satcat.get(s.norad, {})
        meta.append({
            "regime": orbits.classify(s),
            "owner": info.get("owner", "?"),
            "geometry": GEO_BY_TYPE.get(info.get("type", ""), GEO_UNKNOWN),
            "scale": glyph_scale(info.get("rcs"), 1.0),
        })
    log(f"{len(sats)} element sets loaded"
        + (f", {bad} rejected" if bad else "") + "\n")

    sc, times = build(sats, meta, args, log)
    validate(sc)

    os.makedirs(os.path.join(args.out_dir, "media"), exist_ok=True)
    node_path = os.path.join(args.out_dir, f"{STEM}_node.csv")
    log("\nWriting:")
    # Channels first, node CSV last: the app watches the node file.
    write_channels(sc, args.out_dir, STEM, log)
    write_nodes(sc.rows, node_path)
    log(f"  {os.path.basename(node_path)}      {len(sc.rows):,} nodes")

    media = os.path.join(args.out_dir, "media", "01_bluemarble.png")
    if not os.path.exists(media):
        src = os.path.join(HERE, "Live_Sky", "media", "01_bluemarble.png")
        if os.path.exists(src):
            shutil.copy2(src, media)
            log(f"  media/01_bluemarble.png  copied")

    log(f"\nOpen {node_path}\nand press Space.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
