#!/usr/bin/env python3
"""
verify_scenes.py — prove the built geomagnetic scenes tell the truth.

The interesting check here is not "does the CSV load" but "does the picture
mean what it claims".  Each field cone asserts a direction; this script pulls
that direction back OUT of the real GlyphViz transform engine (the glyph's
local +Z axis expressed in world coordinates), converts it to the local
East/North/Up frame, and compares the declination and inclination it implies
against geomag.py's field for that year — at frame 0, mid-animation and the
final frame, driving the real ChannelEngine in between.

Run after build_geomagnetic_scenes.py:
    python verify_scenes.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))

import geomag                                                     # noqa: E402
from glyphviz_core.csv_reader import load_node_csv                # noqa: E402
from glyphviz_core.topology import compute_world_transforms       # noqa: E402
from glyphviz_core.channel_loader import (                        # noqa: E402
    find_channel_files, load_ch_map, load_ch_tracks)
from glyphviz_core.channel_engine import ChannelEngine            # noqa: E402

GLOBE_R = 180.0 / math.pi
YEARS = [float(y) for y in range(1590, 2026, 5)]

fails: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"    {'PASS' if ok else 'FAIL'}  {label}"
          + (f"   {detail}" if detail else ""))
    if not ok:
        fails.append(label)


def enu(lat_deg: float, lon_deg: float):
    """East / North / Up unit vectors in world XYZ for a globe child."""
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    up = np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
                   math.sin(la)])
    east = np.array([-math.sin(lo), math.cos(lo), 0.0])
    return east, np.cross(up, east), up


def load(folder: str, fname: str):
    res = load_node_csv(str(HERE / folder / fname))
    return res[0] if isinstance(res, tuple) else res


# ===========================================================================
print("\n=== Field_And_Poles ===")
# ===========================================================================
nodes = load("Field_And_Poles", "GeomagField_gv_node.csv")
print(f"  loaded {len(nodes):,} nodes")
grids = [n for n in nodes if n.type == 6]
check(len(grids) == 1 and grids[0].grid_is_globe(), "one globe World Grid")
gid = grids[0].id

# The cones are exactly the globe children bound to a vector channel.
cones = [n for n in nodes if n.parent_id == gid and n.geometry == 5]
check(len(cones) > 100, "field-vector cones present", f"{len(cones)} cones")

map_path, tracks_path = find_channel_files(str(HERE / "Field_And_Poles"
                                               / "GeomagField_gv_node.csv"))
ch_map = load_ch_map(map_path)
tracks, id_to_col = load_ch_tracks(tracks_path)
eng = ChannelEngine()
eng.load(ch_map, tracks, id_to_col, nodes)
check(eng.has_bindings and eng.frame_count == len(YEARS),
      "channels bound with one frame per epoch",
      f"{eng.frame_count} frames vs {len(YEARS)} epochs")

idx = {n.id: k for k, n in enumerate(nodes)}
for frame in (0, len(YEARS) // 2, len(YEARS) - 1):
    year = YEARS[frame]
    eng.apply_frame(frame)
    t = compute_world_transforms(nodes, 1.0)
    basis = np.asarray(t.world_basis)

    worst_D = worst_I = 0.0
    for n in cones:
        z = basis[idx[n.id]][:, 2]
        z = z / np.linalg.norm(z)
        e, nn, u = enu(n.translate_y, n.translate_x)
        # Recover declination/inclination from the glyph's own aim.
        got_D = math.degrees(math.atan2(float(z @ e), float(z @ nn)))
        got_I = math.degrees(math.asin(float(np.clip(-(z @ u), -1, 1))))
        m = geomag.field_at(year, n.translate_y, n.translate_x)
        wD, wI = float(m["D"]), float(m["I"])
        worst_D = max(worst_D, abs((got_D - wD + 180) % 360 - 180))
        worst_I = max(worst_I, abs(got_I - wI))
    check(worst_D < 0.02 and worst_I < 0.02,
          f"cones aim along the true field at {int(year)}",
          f"worst dD {worst_D:.4f} deg, dI {worst_I:.4f} deg "
          f"({len(cones)} cones)")

# The animated dip poles must land where geomag says the poles are.
poles = [n for n in nodes if n.parent_id == gid and n.geometry == 16]
check(len(poles) == 2, "two live dip-pole markers")
for frame in (0, len(YEARS) - 1):
    eng.apply_frame(frame)
    year = YEARS[frame]
    for n in poles:
        north = "north" in (getattr(n, "text", "") or "")
        want = geomag.dip_pole(year, north=north)
        d = math.hypot(n.translate_y - want[0],
                       (n.translate_x - want[1]) * math.cos(
                           math.radians(want[0])))
        check(d < 0.05,
              f"{'N' if north else 'S'} pole marker at {int(year)}",
              f"marker {n.translate_y:.2f},{n.translate_x:.2f} vs "
              f"model {want[0]:.2f},{want[1]:.2f}")
eng.reset()

# ===========================================================================
print("\n=== Intensity_Shell ===")
# ===========================================================================
nodes = load("Intensity_Shell", "GeomagShell_gv_node.csv")
print(f"  loaded {len(nodes):,} nodes")
grids = [n for n in nodes if n.type == 6]
check(len(grids) == 1 and grids[0].grid_is_globe(), "one globe World Grid")
gid = grids[0].id
shell = [n for n in nodes if n.parent_id == gid and n.geometry == 22]
check(len(shell) > 500, "shell samples present", f"{len(shell)} points")

map_path, tracks_path = find_channel_files(str(HERE / "Intensity_Shell"
                                               / "GeomagShell_gv_node.csv"))
ch_map = load_ch_map(map_path)
tracks, id_to_col = load_ch_tracks(tracks_path)
eng = ChannelEngine()
eng.load(ch_map, tracks, id_to_col, nodes)
check(eng.frame_count == len(YEARS), "one frame per epoch")

F_LO, F_HI, S_LO, S_HI = 20_000.0, 68_000.0, 3.0, 34.0
for frame in (0, len(YEARS) // 2, len(YEARS) - 1):
    year = YEARS[frame]
    eng.apply_frame(frame)
    t = compute_world_transforms(nodes, 1.0)
    pos = np.asarray(t.world_pos)
    idx = {n.id: k for k, n in enumerate(nodes)}

    worst = 0.0
    for n in shell[::7]:
        F = float(geomag.field_at(year, n.translate_y, n.translate_x)["F"])
        want_h = S_LO + min(max((F - F_LO) / (F_HI - F_LO), 0.0), 1.0) \
            * (S_HI - S_LO)
        got_r = float(np.linalg.norm(pos[idx[n.id]]))
        worst = max(worst, abs((got_r - GLOBE_R) - want_h))
    check(worst < 0.01,
          f"shell height reproduces |B| at {int(year)}",
          f"worst radial error {worst:.4f} world units")

# The headline claim: the anomaly deepens.
eng.apply_frame(0)
t0 = min(float(np.linalg.norm(
    np.asarray(compute_world_transforms(nodes, 1.0).world_pos)[
        {n.id: k for k, n in enumerate(nodes)}[n.id]])) - GLOBE_R
    for n in shell if -40 < n.translate_y < 5 and -80 < n.translate_x < 30)
eng.apply_frame(len(YEARS) - 1)
t1 = min(float(np.linalg.norm(
    np.asarray(compute_world_transforms(nodes, 1.0).world_pos)[
        {n.id: k for k, n in enumerate(nodes)}[n.id]])) - GLOBE_R
    for n in shell if -40 < n.translate_y < 5 and -80 < n.translate_x < 30)
check(t1 < t0,
      "the South Atlantic dent is deeper in 2025 than in 1590",
      f"lowest shell point over the region {t0:.2f} -> {t1:.2f} world units")
eng.reset()

print("\n" + ("ALL CHECKS PASSED" if not fails
             else f"{len(fails)} CHECK(S) FAILED: {fails}"))
sys.exit(1 if fails else 0)
