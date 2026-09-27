#!/usr/bin/env python3
"""
build_climate_rings.py
======================
City Climate Rings: turn city_climate.csv (one flat row per city per month)
into a GlyphViz scene, as asked in prompt.md. Built with the glyphviz skill.

    World Grid (globe, Blue Marble, scale 3)
    └─ city ring ×31         Torus glyph + Torus topology, at the city's lon/lat
       └─ month carrier ×12  hidden; on top of the tube (tube angle 90), so its
          │                  +Z points straight up; clock-face angle
          ├─ month bead      sphere, colour = mean temperature
          ├─ temperature bar Link, hidden low end -> hidden high end
          │                  height above the ring = temperature
          └─ rain column     Link, hidden base -> hidden top, height = rainfall

Placement facts this relies on (skill rules 3, 5, 12, 13):
  * a globe grid's child has +Z up, +Y east, +X south (Wind_Rose README);
  * Torus places a child at (major + tube_r cos ty)(cos tx, sin tx), and
    aims its +Z along the tube normal, which at ty = 90 is the ring's axis:
    straight up. So clock position is translate_x = 180 - 30*month (Jan at
    -X = north, then clockwise seen from above), with no hand rotation;
  * a bar is a Link between two hidden nodes, so both of its ends are
    coordinates and hold at any Global Scale (recipe D);
  * carriers are hide=1 at uniform scale; the month carrier's scale cancels
    the ring's, so everything under it is authored in world units.

verify() re-measures all of that through GlyphViz's own engine before a file
is written, and refuses to write one that disagrees.

    python build_climate_rings.py              # the scene, beside this script
    python build_climate_rings.py --out <folder>
"""
import argparse
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BLUE_MARBLE = REPO / "examples" / "Wind_Rose_Example" / "Monsoon_Year" / "media"
STEM = "climate_rings"

GRID_SCALE = 3.0
# Sized to the tightest pair of neighbours (Beijing-Ulaanbaatar, ~28 world
# units apart at GRID_SCALE 3): rings 18 across leave a clear gap.
RING_SCALE = 9.0          # torus radius in world units (major = 9 x (1 - ratio))
RING_RATIO = 0.04
BEAD_R = 0.8
T_FLOOR = -45.0           # temperature at the ring's height
T_PER_DEG = 0.16          # world units per degree C
MM_PER_UNIT = 60.0        # rainfall: 60 mm per world unit
RAIN_OFFSET = 1.8         # rain column sits this far outside the month bead
TEMP_R, RAIN_R, STEM_R = 0.4, 0.28, 0.07
STEM_RGB = (150, 158, 180)
# No label is pinned: a pinned label draws even when its city is on the far
# side of the globe. Click a ring (or a bead, bar or column) to read it.
PINNED: set = set()
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Mean temperature -> colour: deep blue, cyan, pale, amber, red.
RAMP = [(-35, (40, 70, 220)), (-10, (60, 170, 240)), (8, (225, 235, 240)),
        (20, (250, 185, 60)), (32, (225, 50, 40))]
RAIN_RGB = (70, 150, 255)


def ramp(t):
    if t <= RAMP[0][0]:
        return RAMP[0][1]
    for (t0, c0), (t1, c1) in zip(RAMP, RAMP[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            return tuple(round(a + (b - a) * k) for a, b in zip(c0, c1))
    return RAMP[-1][1]


def fmt(t):
    return f"{t:.1f}".replace("-", "−") + " °C"


def build(data: pd.DataFrame) -> list[dict]:
    rows = []

    def add(**kw):
        r = dict(id=len(rows) + 1, type=5, parent_id=0, branch_level=0,
                 translate_x=0.0, translate_y=0.0, translate_z=0.0,
                 rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                 scale_x=1.0, scale_y=1.0, scale_z=1.0,
                 color_r=255, color_g=255, color_b=255, color_a=255,
                 geometry=3, hide=0, topo=0, ratio=0.1, child_id=0,
                 texture_id=0, show_text=0, segments_x=0, segments_y=0,
                 text="")
        r.update(kw)
        rows.append(r)
        return r["id"]

    add(type=0, geometry=22, hide=1, color_r=8, color_g=10, color_b=18,
        text="City Climate Rings: 31 cities, 2001-2020 monthly means, NASA POWER")
    grid = add(type=6, geometry=3, texture_id=1,
               scale_x=GRID_SCALE, scale_y=GRID_SCALE, scale_z=GRID_SCALE,
               color_r=150, color_g=160, color_b=180,
               segments_x=36, segments_y=18,
               text="Globe: NASA Blue Marble")

    for city, g in data.groupby("city", sort=False):
        g = g.set_index("month").loc[MONTHS]
        first = g.iloc[0]
        ring = add(parent_id=grid, branch_level=1,
                   translate_x=float(first.lon), translate_y=float(first.lat),
                   translate_z=0.4,
                   scale_x=RING_SCALE, scale_y=RING_SCALE, scale_z=RING_SCALE,
                   color_r=225, color_g=228, color_b=240,
                   geometry=7, topo=3, ratio=RING_RATIO,
                   show_text=int(city in PINNED),
                   text=f"{city}, {first.country} · mean {fmt(g.mean_c.min())} "
                        f"to {fmt(g.mean_c.max())} · {int(g.precip_mm.sum())} mm a year")
        for m, (month, r) in enumerate(g.iterrows()):
            where = f"{city} · {month}"
            car = add(parent_id=ring, branch_level=2, hide=1,
                      translate_x=180.0 - 30.0 * m, translate_y=90.0,
                      scale_x=1 / RING_SCALE, scale_y=1 / RING_SCALE,
                      scale_z=1 / RING_SCALE, geometry=22,
                      text=f"{where} (carrier)")
            c = ramp(r.mean_c)
            bead = add(parent_id=car, branch_level=3,
                scale_x=BEAD_R, scale_y=BEAD_R, scale_z=BEAD_R,
                color_r=c[0], color_g=c[1], color_b=c[2],
                text=f"{where} · mean {fmt(r.mean_c)}")
            z_lo = (r.low_c - T_FLOOR) * T_PER_DEG
            z_hi = (r.high_c - T_FLOOR) * T_PER_DEG
            lo = add(parent_id=car, branch_level=3, hide=1, geometry=22,
                     translate_z=round(z_lo, 4), text=f"{where} · low {fmt(r.low_c)}")
            hi = add(parent_id=car, branch_level=3, hide=1, geometry=22,
                     translate_z=round(z_hi, 4), text=f"{where} · high {fmt(r.high_c)}")
            # A thin stem from the bead up to the bar, so a bar floating at
            # its temperature still reads as belonging to its month.
            add(type=7, parent_id=bead, child_id=lo, branch_level=4,
                geometry=19, ratio=STEM_R,
                color_r=STEM_RGB[0], color_g=STEM_RGB[1], color_b=STEM_RGB[2],
                text=f"{where} · stem up to the low, {fmt(r.low_c)}")
            add(type=7, parent_id=lo, child_id=hi, branch_level=4,
                geometry=19, ratio=TEMP_R,
                color_r=c[0], color_g=c[1], color_b=c[2],
                text=f"{where} · average low {fmt(r.low_c)}, high {fmt(r.high_c)}")
            # "Outside the bead": radially away from the ring's centre. In the
            # carrier's frame that is +X, measured (verify() checks it).
            base = add(parent_id=car, branch_level=3, hide=1, geometry=22,
                       translate_x=RAIN_OFFSET, text=f"{where} · rain base")
            top = add(parent_id=car, branch_level=3, hide=1, geometry=22,
                      translate_x=RAIN_OFFSET,
                      translate_z=round(max(r.precip_mm, 1) / MM_PER_UNIT, 4),
                      text=f"{where} · rain {int(r.precip_mm)} mm")
            add(type=7, parent_id=base, child_id=top, branch_level=4,
                geometry=19, ratio=RAIN_R,
                color_r=RAIN_RGB[0], color_g=RAIN_RGB[1], color_b=RAIN_RGB[2],
                text=f"{where} · rain {int(r.precip_mm)} mm")
    return rows


def verify(csv_path: Path, data: pd.DataFrame):
    """Measure the promised geometry through GlyphViz's own engine."""
    import sys
    sys.path.insert(0, str(REPO))
    from glyphviz_core.csv_reader import load_node_csv
    from glyphviz_core.scene import Scene

    nodes = load_node_csv(str(csv_path))
    sc = Scene(nodes, base_scale=1.0)
    by_text = {n.text: n for n in nodes if n.text}
    pos = lambda n: np.array(sc.world_pos(n.id))
    worst = 0.0
    for city, g in data.groupby("city", sort=False):
        g = g.set_index("month")
        ring = next(n for n in nodes if n.text.startswith(city + ","))
        rc = pos(ring)
        up = rc / np.linalg.norm(rc)                       # globe outward
        east = np.cross([0, 0, 1], up); east /= np.linalg.norm(east)
        north = np.cross(up, east)
        for m, month in enumerate(MONTHS):
            where = f"{city} · {month}"
            bead = by_text[f"{where} · mean {fmt(g.loc[month].mean_c)}"]
            d = pos(bead) - rc
            d_flat = d - up * d.dot(up)
            ang = math.degrees(math.atan2(d_flat.dot(east), d_flat.dot(north))) % 360
            assert abs((ang - 30 * m + 180) % 360 - 180) < 0.5, (city, month, ang)
            lo = pos(by_text[f"{where} · low {fmt(g.loc[month].low_c)}"])
            hi = pos(by_text[f"{where} · high {fmt(g.loc[month].high_c)}"])
            want = (g.loc[month].high_c - g.loc[month].low_c) * T_PER_DEG
            v = hi - lo
            worst = max(worst, abs(np.linalg.norm(v) - want))
            if want > 1e-6:
                assert v.dot(up) / np.linalg.norm(v) > 0.999, (city, month, "bar not upright")
            base = pos(by_text[f"{where} · rain base"])
            out = (base - pos(bead)); out -= up * out.dot(up)
            assert out.dot(d_flat) > 0, (city, month, "rain column not outside")
    assert worst < 1e-6, worst
    print(f"verify: 31 clock faces (Jan north, clockwise), bars upright, "
          f"lengths exact to {worst:.1e}, rain columns outside the beads")


def load_data() -> pd.DataFrame:
    return pd.read_csv(HERE / "city_climate.csv")


def write_scene(out: Path) -> Path:
    """Write the scene folder (node CSV + media/) and verify it."""
    out.mkdir(parents=True, exist_ok=True)
    data = load_data()
    rows = build(data)
    df = pd.DataFrame(rows)
    path = out / f"{STEM}_gv_node.csv"
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\r\n")
    media = out / "media"
    media.mkdir(exist_ok=True)
    shutil.copy2(BLUE_MARBLE / sorted(p.name for p in BLUE_MARBLE.iterdir())[0],
                 media / "01_bluemarble.png")
    verify(path, data)
    print(f"{len(rows)} nodes -> {path}")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE))
    write_scene(Path(ap.parse_args().out))


if __name__ == "__main__":
    main()
