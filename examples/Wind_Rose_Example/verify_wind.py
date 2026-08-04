#!/usr/bin/env python3
"""
verify_wind.py — check the built scenes are *true*, not merely loadable.

Every check runs the real GlyphViz loader and transform engine over the shipped
CSVs and reads the answer back out of world-space geometry, so it tests what
the renderer will actually draw rather than what the builder intended.

 1. Structure: the hyperglyph really is nested — grid -> hub -> arm -> segment.
 2. Render floor: every visible node's OWN scale clears 0.2 per axis, which is
    what the renderer actually floors (node_world_matrix floors this node's
    scale x base_scale, then multiplies by the parent basis).  Authoring below
    it means the glyph is drawn bigger than it encodes.
 3. Sphere convention: the globe's own placement formula, established from the
    engine's output and then asserted, so checks 4-6 rest on measured ground.
 4. Compass fidelity: the bearing of each arm, recovered from world positions
    via the local East/North/Up frame, matches the sector it encodes — and
    every arm lies flat in the horizontal plane.
 5. Encoding round-trip: summing a petal's rendered segment lengths recovers
    the sector frequency that went in, to within the merge/clip tolerance.
 6. No overlap: no two roses collide on the globe.
 7. Channels: the ch-map/ch-tracks pair loads, binds, and applying frame m
    reproduces month m+1's petal geometry from the source climatology.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))

from glyphviz_core.csv_reader import load_node_csv                    # noqa: E402
from glyphviz_core.topology import compute_world_transforms           # noqa: E402
from glyphviz_core.channel_loader import load_ch_map, load_ch_tracks  # noqa: E402
from glyphviz_core.channel_engine import ChannelEngine                # noqa: E402

sys.path.insert(0, str(HERE))
import build_wind_scenes as B                                         # noqa: E402

fails: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail
                                                      else ""))
    if not ok:
        fails.append(label)


def load(scene: str, stem: str):
    nodes = load_node_csv(str(HERE / scene / f"{stem}_gv_node.csv"))
    tr = compute_world_transforms(nodes, 1.0)
    return nodes, tr


def cum_scale(tr, node_id) -> np.ndarray:
    """Per-axis cumulative rendered scale = column norms of the world basis."""
    b = tr.world_basis[tr.row_of_id[node_id]]
    return np.array([np.linalg.norm(b[:, i]) for i in range(3)])


# ===========================================================================
print("Monsoon_Year")
nodes, tr = load("Monsoon_Year", "monsoon_year")
by_id = {n.id: n for n in nodes}
pos = {n.id: tr.world_pos[tr.row_of_id[n.id]] for n in nodes}
kids: dict[int, list] = {}
for n in nodes:
    kids.setdefault(n.parent_id, []).append(n)

grid = next(n for n in nodes if n.type == 6)
hubs = [n for n in kids[grid.id] if n.topo == 4]

# --- 1. structure ----------------------------------------------------------
print("\n1. hyperglyph structure")
depth = {n.id: tr.depth[tr.row_of_id[n.id]] for n in nodes}
seg_nodes = [n for n in nodes if depth[n.id] == 3 and n.hide == 0]
arm_nodes = [n for n in nodes if depth[n.id] == 2 and n.hide == 1]
check(len(hubs) > 50, "station hubs under the World Grid", f"{len(hubs)}")
check(len(arm_nodes) > 800, "compass arms at depth 2", f"{len(arm_nodes)}")
check(len(seg_nodes) > 3000, "speed-bin segments at depth 3",
      f"{len(seg_nodes)}")
check(max(depth.values()) >= 3, "max hierarchy depth >= 3",
      f"deepest = {max(depth.values())}")

# --- 2. render floor -------------------------------------------------------
print("\n2. the 0.2 render floor (applied to each node's OWN scale)")
worst, worst_id, worst_cum = 9e9, None, 9e9
for n in nodes:
    if n.hide or n.type != 5:
        continue
    own = min(n.scale_x, n.scale_y, n.scale_z)
    if own < worst:
        worst, worst_id = own, n.id
    worst_cum = min(worst_cum, float(cum_scale(tr, n.id).min()))
check(worst >= 0.2 - 1e-9,
      "every visible node's own scale clears 0.2 on all three axes",
      f"tightest own scale = {worst:.4f} (node {worst_id}); "
      f"smallest rendered size in the scene = {worst_cum:.4f}")

# --- 3. establish the globe's sphere convention ----------------------------
print("\n3. globe placement formula (measured, then asserted)")
R = B.GLOBE_R * B.GRID_SCALE


def sphere_xyz(lon_deg, lat_deg, radius=R):
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    return np.array([radius * math.cos(la) * math.cos(lo),
                     radius * math.cos(la) * math.sin(lo),
                     radius * math.sin(la)])


err = 0.0
for h in hubs[:40]:
    p = pos[h.id]
    # elevation rides the grid scale too: the whole globe, surface and
    # altitude alike, is multiplied by it
    want = sphere_xyz(h.translate_x, h.translate_y,
                      R + h.translate_z * B.GRID_SCALE)
    err = max(err, float(np.linalg.norm(p - want)))
check(err < 1e-6, "hub positions match R*(cos lat cos lon, cos lat sin lon, "
                  "sin lat), elevation scaled by the grid",
      f"worst offset {err:.2e} world units")


def enu(lon_deg, lat_deg):
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    up = np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
                   math.sin(la)])
    north = np.array([-math.sin(la) * math.cos(lo),
                      -math.sin(la) * math.sin(lo), math.cos(la)])
    east = np.cross(north, up)
    return east / np.linalg.norm(east), north, up


# --- 4. compass fidelity ---------------------------------------------------
print("\n4. compass fidelity of every arm")
worst_bearing, worst_up = 0.0, 0.0
n_arms = 0
for h in hubs:
    e, nth, up = enu(h.translate_x, h.translate_y)
    for arm in kids.get(h.id, []):
        if arm.topo != 0 or arm.hide != 1:
            continue
        # Every arm is placed at radius B+tz = 0, i.e. exactly at the hub
        # centre: it is a rotation frame, not an offset.  Its outward
        # direction is therefore its local +X axis, read off the world basis.
        b = tr.world_basis[tr.row_of_id[arm.id]]
        v = b[:, 0]
        if np.linalg.norm(v) < 1e-9:
            continue
        bearing = math.degrees(math.atan2(float(v @ e), float(v @ nth))) % 360
        want = (180.0 - arm.translate_x) % 360.0
        d = abs((bearing - want + 180.0) % 360.0 - 180.0)
        worst_bearing = max(worst_bearing, d)
        worst_up = max(worst_up, abs(float(v @ up)) / np.linalg.norm(v))
        n_arms += 1
check(worst_bearing < 1e-6, "arm bearing == 180 - translate_x",
      f"{n_arms} arms, worst error {worst_bearing:.2e} deg")
check(worst_up < 1e-9, "every arm lies flat in the local horizontal plane",
      f"worst |up| component {worst_up:.2e}")

# --- 5. encoding round-trip -------------------------------------------------
print("\n5. recovering the source frequencies from rendered geometry")
roses = pd.read_csv(HERE / "data" / "wind_roses.csv")
st = pd.read_csv(HERE / "data" / "wind_stations.csv")
ann = B.annual(roses).merge(st, on="sid")
ann["key"] = list(zip(ann.lon.round(3), ann.lat.round(3)))
ann_by_key = {k: r for k, r in zip(ann.key, ann.itertuples())}

worst_freq, n_checked, clipped = 0.0, 0, 0
for h in hubs:
    key = (round(h.translate_x, 3), round(h.translate_y, 3))
    src = ann_by_key.get(key)
    if src is None:
        continue
    for arm in kids.get(h.id, []):
        if arm.topo != 0 or arm.hide != 1:
            continue
        sector = int(round(((180.0 - arm.translate_x) % 360.0) / B.SECTOR_DEG))
        sector %= B.N_SECTORS
        drawn = 0.0
        for seg in kids.get(arm.id, []):
            drawn += cum_scale(tr, seg.id)[0] / B.LEN_TO_SCALE
        if drawn <= 0:
            continue
        rose_r = 0.40 * 11.0 * B.GRID_SCALE
        want_total = sum(getattr(src, f"s{sector:02d}b{k}")
                         for k in range(B.N_BINS))
        if want_total / B.SECTOR_REF >= 1.0:
            clipped += 1
            continue
        got_total = drawn / rose_r * B.SECTOR_REF
        worst_freq = max(worst_freq, abs(got_total - want_total))
        n_checked += 1
check(worst_freq < 5e-4,
      "petal length decodes back to the sector frequency",
      f"{n_checked} petals, worst error {worst_freq:.2e} "
      f"(frequencies run 0-0.86); {clipped} clipped petals skipped")

# --- 6. no overlap ----------------------------------------------------------
print("\n6. rose separation on the globe")
P = np.array([pos[h.id] for h in hubs])
d = np.linalg.norm(P[:, None, :] - P[None, :, :], axis=-1)
np.fill_diagonal(d, 9e9)
min_sep = float(d.min())
rose_r = 0.40 * 11.0 * B.GRID_SCALE
check(min_sep > 2 * rose_r * 0.98, "no two roses can intersect",
      f"closest hubs {min_sep:.1f} units apart, rose diameter "
      f"{2 * rose_r:.1f}")

# --- 7. channels ------------------------------------------------------------
print("\n7. channel animation")
ch_map = load_ch_map(HERE / "Monsoon_Year" / "monsoon_year_gv_ch-map.csv")
tracks, id_to_col = load_ch_tracks(
    HERE / "Monsoon_Year" / "monsoon_year_gv_ch-tracks.csv")
eng = ChannelEngine()
eng.load(ch_map, tracks, id_to_col, nodes)
check(eng.frame_count == 12, "twelve monthly frames",
      f"frame_count={eng.frame_count}, {len(eng._bindings)} bindings")

def ch_id(n):
    return int(n.extras.get('ch_input_id', 0) or 0)


bound_segments = {n.id for n in seg_nodes if ch_id(n) > 0}
check(len(bound_segments) > 3000, "every speed segment is animated",
      f"{len(bound_segments)} bound segments")

# apply a mid-year frame and re-derive a petal from the moved geometry
by_sid_month = {(r.sid, int(r.month)): r for r in roses.itertuples()}
sid_by_key = {(round(r.lon, 3), round(r.lat, 3)): r.sid
              for r in st.itertuples()}

worst_anim, n_anim = 0.0, 0
for frame, month in ((0, 1), (6, 7)):
    eng.apply_frame(frame)
    tr2 = compute_world_transforms(nodes, 1.0)
    for h in hubs[:25]:
        sid = sid_by_key.get((round(h.translate_x, 3),
                              round(h.translate_y, 3)))
        src = by_sid_month.get((sid, month)) if sid else None
        if src is None:
            continue
        for arm in kids.get(h.id, []):
            if arm.topo != 0 or arm.hide != 1:
                continue
            sector = int(round(((180.0 - arm.translate_x) % 360.0)
                               / B.SECTOR_DEG)) % B.N_SECTORS
            drawn = 0.0
            for seg in kids.get(arm.id, []):
                # a bin absent this month is parked AT the hub centre; tell it
                # apart by position, not by size (a real band can sit exactly
                # on the floor too)
                if abs(seg.translate_x) < 1e-9:
                    continue
                b = tr2.world_basis[tr2.row_of_id[seg.id]]
                drawn += float(np.linalg.norm(b[:, 0])) / B.LEN_TO_SCALE
            want = sum(getattr(src, f"s{sector:02d}b{k}")
                       for k in range(B.N_BINS))
            if want / B.SECTOR_REF >= 1.0 or drawn <= 0:
                continue
            got = drawn / rose_r * B.SECTOR_REF
            worst_anim = max(worst_anim, abs(got - want))
            n_anim += 1
eng.reset()
check(worst_anim < 6e-3,
      "applying frame m reproduces that month's measured rose",
      f"{n_anim} petals across January and July, worst error "
      f"{worst_anim:.2e}")

# ===========================================================================
print("\nRose_Anatomy")
a_nodes, a_tr = load("Rose_Anatomy", "rose_anatomy")
a_depth = {n.id: a_tr.depth[a_tr.row_of_id[n.id]] for n in a_nodes}
worst_a = min(cum_scale(a_tr, n.id).min() for n in a_nodes
              if not n.hide and n.type == 5)
labels = [n for n in a_nodes if n.show_text and n.text]
check(max(a_depth.values()) >= 3, "nested to depth 3",
      f"deepest = {max(a_depth.values())}")
check(worst_a >= 0.2 - 1e-9, "clears the render floor",
      f"tightest = {worst_a:.4f}")
check(len(labels) >= 12, "archetype stations are labelled",
      f"{len(labels)} pinned labels")

print(f"\n{'ALL CHECKS PASSED' if not fails else 'FAILURES: ' + str(fails)}")
sys.exit(1 if fails else 0)
