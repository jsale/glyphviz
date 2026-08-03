#!/usr/bin/env python3
"""
verify_scenes.py — check the built cyclone scenes through the REAL GlyphViz
loader, transform engine and channel engine (no GL context needed).

Run after build_cyclone_scenes.py:
    python verify_scenes.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from glyphviz_core.csv_reader import load_node_csv                # noqa: E402
from glyphviz_core.topology import compute_world_transforms       # noqa: E402
from glyphviz_core.channel_loader import (                        # noqa: E402
    find_channel_files, load_ch_map, load_ch_tracks)
from glyphviz_core.channel_engine import ChannelEngine            # noqa: E402

GLOBE_R = 180.0 / math.pi
SCENES = [("Global_Tracks", "CycloneTracks_gv_node.csv"),
          ("Seasonal_Pulse", "SeasonalPulse_gv_node.csv"),
          ("Poleward_Drift", "PolewardDrift_gv_node.csv")]

fails: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    print(f"    {'PASS' if cond else 'FAIL'}  {label}"
          + (f"   {detail}" if detail else ""))
    if not cond:
        fails.append(label)


for folder, fname in SCENES:
    path = HERE / folder / fname
    print(f"\n=== {folder} ===")
    if not path.exists():
        check(False, "node CSV exists", str(path))
        continue

    res = load_node_csv(str(path))
    nodes = res[0] if isinstance(res, tuple) else res
    print(f"  loaded {len(nodes):,} nodes")

    grids = [n for n in nodes if n.type == 6]
    check(len(grids) == 1, "exactly one World Grid",
          f"geometry={grids[0].geometry if grids else '-'}")
    check(bool(grids) and grids[0].grid_is_globe(),
          "grid renders as a globe (Node.grid_is_globe)")
    check(bool(grids) and grids[0].texture_id == 1,
          "globe carries the Blue Marble texture (texture_id=1)")

    t = compute_world_transforms(nodes, 1.0)
    pos = np.asarray(t.world_pos)
    idx = {n.id: k for k, n in enumerate(nodes)}

    gid = grids[0].id if grids else None
    kids = [n for n in nodes if n.parent_id == gid and n.type == 5]
    check(len(kids) > 1000, "globe has the storm children",
          f"{len(kids):,} children")

    # Every globe child must sit at radius = GLOBE_R + its elevation.
    krow = np.array([idx[n.id] for n in kids])
    r = np.linalg.norm(pos[krow], axis=1)
    elev = np.array([n.translate_z for n in kids])
    resid = np.abs(r - (GLOBE_R + elev))
    check(resid.max() < 1e-6, "radius == globe radius + elevation",
          f"max residual {resid.max():.2e}")

    # ...and at the lon/lat the data says.
    lon = np.degrees(np.arctan2(pos[krow, 1], pos[krow, 0]))
    lat = np.degrees(np.arcsin(np.clip(pos[krow, 2] / r, -1, 1)))
    want_lon = np.array([n.translate_x for n in kids])
    want_lat = np.array([n.translate_y for n in kids])
    dlon = np.abs((lon - want_lon + 180) % 360 - 180)
    check(dlon.max() < 1e-4 and np.abs(lat - want_lat).max() < 1e-4,
          "children land at their own lon/lat on the globe",
          f"max err lon {dlon.max():.2e} lat "
          f"{np.abs(lat - want_lat).max():.2e}")

    print(f"    elevation range: {elev.min():.2f} .. {elev.max():.2f} "
          f"world units  (globe radius {GLOBE_R:.2f})")

    # --- channels -----------------------------------------------------------
    map_path, tracks_path = find_channel_files(str(path))
    if map_path is None:
        print("    (no channel files — static scene)")
        continue
    ch_map = load_ch_map(map_path)
    tracks, id_to_col = load_ch_tracks(tracks_path)
    print(f"    channels: {len(ch_map)} bound, tracks {tracks.shape}")

    used = {n.extras.get("ch_input_id") for n in nodes}
    used = {int(u) for u in used if u not in (None, "", 0) and int(u) != 0}
    check(used <= set(ch_map), "every ch_input_id has a map row",
          f"{len(used)} used")
    need = {tid for binds in ch_map.values() for tid, _a in binds}
    check(need <= set(id_to_col), "every map track_id has a tracks column")

    # Drive the REAL engine through the whole animation.
    eng = ChannelEngine()
    eng.load(ch_map, tracks, id_to_col, nodes)
    check(eng.has_bindings, "engine bound the scene",
          f"frame_count={eng.frame_count}")
    n_frames = eng.frame_count
    eng.apply_frame(0)
    alphas0 = np.array([n.color_a for n in nodes])
    mid = n_frames // 2
    eng.apply_frame(mid)
    alphas_mid = np.array([n.color_a for n in nodes])
    check(not np.array_equal(alphas0, alphas_mid),
          "frame 0 and mid-animation differ (animation actually moves)")
    eng.apply_frame(n_frames - 1)
    check(all(0 <= n.color_a <= 255 for n in nodes),
          "alpha stays in 0..255 across frames")
    bad_scale = [n for n in nodes
                 if n.type in (5, 7) and not n.hide
                 and min(n.scale_x, n.scale_y, n.scale_z) < 0.2]
    check(not bad_scale, "no animated scale drops below the 0.2 render floor",
          f"{len(bad_scale)} offenders")
    eng.reset()

print("\n" + ("ALL CHECKS PASSED" if not fails
             else f"{len(fails)} CHECK(S) FAILED: {fails}"))
sys.exit(1 if fails else 0)
