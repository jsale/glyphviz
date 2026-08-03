#!/usr/bin/env python3
"""
build_geomagnetic_scenes.py — four centuries of Earth's magnetic field
======================================================================

Builds two animated World-Grid *globe* scenes from published Gauss
coefficients (see geomag.py for the models and their provenance).  No data
download is needed: everything is computed from the two coefficient files
in data/, which together span 1590-2030.

  Field_And_Poles/   A lattice of cone glyphs on the globe, each one aimed
                     along the true local field direction — declination sets
                     its compass bearing, inclination its dip — and coloured
                     by field strength.  Animated from 1590 to 2025 the whole
                     lattice swings: this is *secular variation*, the slow
                     churn of the fluid outer core, made visible as a single
                     coherent motion instead of a table of numbers.  Both
                     magnetic dip poles ride the same clock along their
                     435-year wander paths, which are also drawn as static
                     labelled trails so you can see where they have been.
                     The north pole's recent sprint from Arctic Canada toward
                     Siberia is the fastest thing in the scene.

  Intensity_Shell/   The same globe wearing a shell of glyphs whose height
                     above the surface *is* the field strength.  Strong field
                     over the poles stands high; the South Atlantic Anomaly
                     is a growing dent in the shell over Brazil, the region
                     where the field is weak enough that satellites passing
                     through it take real radiation damage.  A tracked marker
                     sits at the weakest point and drifts west with it across
                     four centuries.

Both scenes are pure CSV: no plugin, no runtime model code.  Everything the
viewer animates was evaluated ahead of time into channel tracks.

Usage:
    python build_geomagnetic_scenes.py
    python build_geomagnetic_scenes.py --only Intensity_Shell
    python build_geomagnetic_scenes.py --step 10      # coarser time sampling

Requires: numpy, scipy, pandas
"""

from __future__ import annotations

import argparse
import math
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import geomag                                                     # noqa: E402

# ---------------------------------------------------------------------------
# 1. CONSTANTS
# ---------------------------------------------------------------------------
GLOBE_R = 180.0 / math.pi            # world radius of a scale-1 globe

YEAR_FIRST, YEAR_LAST = 1590, 2025
YEAR_STEP = 5

# Field_And_Poles
VEC_LON_STEP = 12.0
VEC_LAT_LIMIT, VEC_LAT_STEP = 78.0, 12.0
VEC_LEN = 4.6                        # cone half-length (scale_z)
# A GEO_CONE is centred on its node and spans +-scale_z along its own axis,
# so the node has to float at least a cone-half-length off the surface or a
# steeply dipping vector buries its apex — which is the end that carries the
# direction — inside the globe. Near the poles the dip IS ~90 degrees, so
# this margin is what keeps the polar field readable at all.
VEC_BASE_ELEV = VEC_LEN + 1.2
VEC_WIDTH = 1.15
TRAIL_STEP_YEARS = 5                 # dip-pole trail marker spacing
TRAIL_LABEL_YEARS = 100              # 50 stacks illegibly: the poles barely
#                                      moved for three centuries

# Intensity_Shell
SHELL_LON_STEP = 7.5
SHELL_LAT_LIMIT, SHELL_LAT_STEP = 78.75, 7.5
F_LO, F_HI = 20_000.0, 68_000.0      # nT, mapped onto the shell's height
SHELL_LO, SHELL_HI = 3.0, 34.0       # world units above the surface

PALETTE_ID = 10                      # Purple -> Yellow: weak -> strong
PALETTE_LO = (152, 0, 255)
PALETTE_HI = (255, 255, 0)

BG_COLOR = (8, 8, 20, 255)
ACCENT = (255, 196, 92)
NORTH_RGB = (120, 225, 255)
SOUTH_RGB = (255, 150, 205)

# Channel id blocks, kept far apart so the three-way join is easy to read.
CH_VEC_TILT = 1_000                  # + lattice index
CH_VEC_HEAD = 100_000                # + lattice index
CH_VEC_COLOR = 200_000               # + lattice index
CH_SHELL_Z = 300_000                 # + lattice index
CH_SHELL_COLOR = 400_000             # + lattice index
CH_POLE_N_LON, CH_POLE_N_LAT = 900_001, 900_002
CH_POLE_S_LON, CH_POLE_S_LAT = 900_003, 900_004
CH_SAA_LON, CH_SAA_LAT = 900_005, 900_006
CH_CURSOR = 900_007


def years() -> list[float]:
    return [float(y) for y in range(YEAR_FIRST, YEAR_LAST + 1, YEAR_STEP)]


def sanitize(t: str) -> str:
    return "".join(c for c in str(t)
                   if unicodedata.category(c)[0] != "C").strip()


# ---------------------------------------------------------------------------
# 2. ENCODINGS
# ---------------------------------------------------------------------------
def f_index(F_nT) -> np.ndarray:
    """Field strength (nT) -> 0..127 index on the Purple->Yellow gradient."""
    t = (np.asarray(F_nT, dtype=float) - F_LO) / (F_HI - F_LO)
    return np.clip(np.round(t * 127.0), 0, 127).astype(int)


def index_rgb(idx: int) -> tuple[int, int, int]:
    """The literal colour GlyphViz resolves for that index, so the scene is
    correctly coloured before playback ever starts (see color-palettes.md)."""
    t = (int(idx) % 128) / 127.0
    return tuple(int(round(a + (b - a) * t))
                 for a, b in zip(PALETTE_LO, PALETTE_HI))


def shell_height(F_nT) -> np.ndarray:
    t = (np.asarray(F_nT, dtype=float) - F_LO) / (F_HI - F_LO)
    return SHELL_LO + np.clip(t, 0.0, 1.0) * (SHELL_HI - SHELL_LO)


# Aiming a glyph on a globe (verified against the real transform engine):
#   a globe child's local +Z is radially OUTWARD (up), +Y is EAST, +X is SOUTH.
#   In Heading/Tilt/Roll mode, rotate_x is Tilt (angle away from up) and
#   rotate_y is Heading (which spins the tilted axis about up).  Heading 0
#   tilts toward EAST, 90 toward SOUTH, 180 WEST, 270 NORTH -- so a compass
#   azimuth A measured clockwise from north is heading = A - 90.
# The field's azimuth is the declination D, and its angle away from "up" is
# 90 + I, since inclination I is measured DOWNWARD from horizontal.
def aim(D_deg, I_deg):
    tilt = 90.0 + np.asarray(I_deg, dtype=float)
    head = (np.asarray(D_deg, dtype=float) - 90.0) % 360.0
    return tilt, head


ROTATION_MODE_HTR = 1


# ---------------------------------------------------------------------------
# 3. SCENE BUILDER
# ---------------------------------------------------------------------------
COLUMNS = ["id", "type", "parent_id", "branch_level", "child_id",
           "translate_x", "translate_y", "translate_z",
           "rotate_x", "rotate_y", "rotate_z",
           "scale_x", "scale_y", "scale_z",
           "color_r", "color_g", "color_b", "color_a", "color_index",
           "palette_id", "geometry", "hide", "topo", "ratio", "texture_id",
           "ch_input_id", "rotate_rate_z", "show_text",
           "trigger_lo_x", "trigger_hi_x", "trigger_lo_y", "trigger_hi_y",
           "segments_x", "segments_y", "rotation_mode", "text", "link"]

DEFAULTS = dict(child_id=0, translate_x=0.0, translate_y=0.0,
                translate_z=0.0, rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=255, color_g=255, color_b=255, color_a=255,
                color_index=0, palette_id=0, geometry=3, hide=0, topo=0,
                ratio=0.1, texture_id=0, ch_input_id=0, rotate_rate_z=0.0,
                show_text=0, trigger_lo_x=0, trigger_hi_x=0, trigger_lo_y=0,
                trigger_hi_y=0, segments_x=16, segments_y=16,
                rotation_mode=0, text="", link="")


@dataclass
class SceneBuilder:
    rows: list[dict] = field(default_factory=list)
    next_id: int = 1

    def add(self, **kw) -> int:
        self.rows.append({**DEFAULTS, "id": self.next_id, **kw})
        self.next_id += 1
        return self.next_id - 1

    def world(self) -> int:
        return self.add(type=0, parent_id=0, branch_level=0, geometry=0,
                        color_r=BG_COLOR[0], color_g=BG_COLOR[1],
                        color_b=BG_COLOR[2], color_a=BG_COLOR[3])

    def globe(self, **kw) -> int:
        opts = dict(type=6, parent_id=0, branch_level=0, geometry=3,
                    texture_id=1, segments_x=36, segments_y=18,
                    color_r=70, color_g=110, color_b=150, color_a=255,
                    text="")
        opts.update(kw)
        return self.add(**opts)

    def caption(self, z, text, size=2.2, rgb=ACCENT):
        return self.add(type=5, parent_id=0, branch_level=0,
                        translate_x=0.0, translate_y=0.0, translate_z=z,
                        scale_x=size, scale_y=size, scale_z=size,
                        geometry=11, color_r=rgb[0], color_g=rgb[1],
                        color_b=rgb[2], color_a=230, show_text=1,
                        text=sanitize(text))

    def colorbar(self, x0: float, lo_label: str, hi_label: str,
                 title: str) -> None:
        """Vertical key for the Purple->Yellow field-strength gradient."""
        self.caption(0.0, 0.0)          # placeholder no-op guard
        self.rows.pop()
        self.next_id -= 1
        n = 12
        for k in range(n):
            idx = int(round(127 * k / (n - 1)))
            rgb = index_rgb(idx)
            lab = ""
            if k == 0:
                lab = lo_label
            elif k == n - 1:
                lab = hi_label
            self.add(type=5, parent_id=0, branch_level=0,
                     translate_x=x0, translate_y=0.0,
                     translate_z=-22.0 + k * 4.0,
                     scale_x=1.7, scale_y=1.7, scale_z=1.7, geometry=3,
                     color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                     color_a=255, color_index=idx, palette_id=PALETTE_ID,
                     show_text=1 if lab else 0, text=lab)
        self.add(type=5, parent_id=0, branch_level=0,
                 translate_x=x0, translate_y=0.0, translate_z=-22.0 + n * 4.0,
                 scale_x=1.4, scale_y=1.4, scale_z=1.4, geometry=11,
                 color_r=ACCENT[0], color_g=ACCENT[1], color_b=ACCENT[2],
                 color_a=220, show_text=1, text=title)

    def timeline(self, z: float, yrs: list[float]) -> None:
        """Century-ticked bar under the globe, with a channel-driven cursor.

        Kept narrower than the globe is wide: the camera auto-fits the whole
        bounding box, so an over-long timeline shrinks the thing you came to
        look at.
        """
        x_lo, x_hi = -95.0, 95.0

        def x_of(y: float) -> float:
            f = (y - yrs[0]) / max(yrs[-1] - yrs[0], 1.0)
            return round(x_lo + (x_hi - x_lo) * f, 3)

        ends = [self.add(type=5, parent_id=0, branch_level=0,
                         translate_x=x, translate_y=0.0, translate_z=z,
                         scale_x=0.9, scale_y=0.9, scale_z=0.9, geometry=1,
                         color_r=ACCENT[0], color_g=ACCENT[1],
                         color_b=ACCENT[2], color_a=255)
                for x in (x_lo, x_hi)]
        self.add(type=7, parent_id=ends[0], child_id=ends[1], branch_level=1,
                 geometry=27, color_r=ACCENT[0], color_g=ACCENT[1],
                 color_b=ACCENT[2], color_a=180)
        y = int(math.ceil(yrs[0] / 50.0) * 50)
        while y <= yrs[-1]:
            major = (y % 100 == 0)
            self.add(type=5, parent_id=0, branch_level=0,
                     translate_x=x_of(y), translate_y=0.0,
                     translate_z=z + 2.0, scale_x=0.8, scale_y=0.8,
                     scale_z=3.0 if major else 1.8, geometry=1,
                     color_r=ACCENT[0], color_g=ACCENT[1], color_b=ACCENT[2],
                     color_a=230, show_text=1 if major else 0,
                     text=str(y) if major else "")
            y += 50
        self.add(type=5, parent_id=0, branch_level=0,
                 translate_x=x_lo, translate_y=0.0, translate_z=z + 5.0,
                 scale_x=3.4, scale_y=3.4, scale_z=3.4, geometry=11,
                 rotate_rate_z=0.7, color_r=255, color_g=246, color_b=190,
                 color_a=255, ch_input_id=CH_CURSOR)
        self._x_of_year = x_of

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=COLUMNS)


# ---------------------------------------------------------------------------
# 4. DIP-POLE PATHS
# ---------------------------------------------------------------------------
def pole_paths(yrs: list[float]):
    print("  locating dip poles (grid search + refinement per epoch) ...")
    north, south = [], []
    for y in yrs:
        north.append(geomag.dip_pole(y, north=True))
        south.append(geomag.dip_pole(y, north=False))
    return north, south


def pole_speed_kmyr(path, yrs) -> list[float]:
    out = [0.0]
    for k in range(1, len(path)):
        (la1, lo1), (la2, lo2) = path[k - 1], path[k]
        p1, p2 = math.radians(la1), math.radians(la2)
        dl = math.radians(lo2 - lo1)
        d = math.acos(max(-1.0, min(1.0, math.sin(p1) * math.sin(p2)
                                    + math.cos(p1) * math.cos(p2)
                                    * math.cos(dl))))
        out.append(math.degrees(d) * 111.195 / (yrs[k] - yrs[k - 1]))
    return out


# ---------------------------------------------------------------------------
# 5. SCENE 1 — FIELD AND POLES
# ---------------------------------------------------------------------------
def build_field_and_poles(yrs: list[float], npath, spath):
    lons = np.arange(-180.0, 180.0, VEC_LON_STEP)
    lats = np.arange(-VEC_LAT_LIMIT, VEC_LAT_LIMIT + 1e-9, VEC_LAT_STEP)
    LA, LO = np.meshgrid(lats, lons, indexing="ij")
    lat_f, lon_f = LA.ravel(), LO.ravel()
    n_vec = lat_f.size

    print(f"  evaluating {n_vec} field vectors x {len(yrs)} epochs "
          f"({n_vec * len(yrs):,} field solutions) ...")
    tilt = np.zeros((len(yrs), n_vec))
    head = np.zeros((len(yrs), n_vec))
    cidx = np.zeros((len(yrs), n_vec), dtype=int)
    for k, y in enumerate(yrs):
        m = geomag.field_at(y, lat_f, lon_f)
        tilt[k], head[k] = aim(m["D"], m["I"])
        cidx[k] = f_index(m["F"])

    sb = SceneBuilder()
    sb.world()
    g = sb.globe()

    # The field-vector lattice.
    for i in range(n_vec):
        rgb = index_rgb(int(cidx[-1, i]))
        sb.add(type=5, parent_id=g, branch_level=1,
               translate_x=round(float(lon_f[i]), 3),
               translate_y=round(float(lat_f[i]), 3),
               translate_z=VEC_BASE_ELEV,
               rotate_x=round(float(tilt[-1, i]), 3),
               rotate_y=round(float(head[-1, i]), 3),
               rotation_mode=ROTATION_MODE_HTR,
               scale_x=VEC_WIDTH, scale_y=VEC_WIDTH, scale_z=VEC_LEN,
               geometry=5,
               color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=245,
               color_index=int(cidx[-1, i]), palette_id=PALETTE_ID,
               ch_input_id=CH_VEC_TILT + i)

    # Static dip-pole trails, oldest to newest, with half-century labels.
    for path, rgb, tag in ((npath, NORTH_RGB, "north"),
                           (spath, SOUTH_RGB, "south")):
        for k, (la, lo) in enumerate(path):
            y = int(yrs[k])
            if y % TRAIL_STEP_YEARS:
                continue
            label = f"{y}" if y % TRAIL_LABEL_YEARS == 0 else ""
            f = k / max(len(path) - 1, 1)
            sb.add(type=5, parent_id=g, branch_level=1,
                   translate_x=round(lo, 4), translate_y=round(la, 4),
                   translate_z=1.2,
                   scale_x=0.55 + 0.9 * f, scale_y=0.55 + 0.9 * f,
                   scale_z=0.55 + 0.9 * f, geometry=3,
                   color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                   color_a=int(90 + 165 * f), show_text=1 if label else 0,
                   text=label)
        _ = tag

    # The live poles, riding the animation clock.
    sb.add(type=5, parent_id=g, branch_level=1,
           translate_x=round(npath[-1][1], 4), translate_y=round(npath[-1][0], 4),
           translate_z=9.0, scale_x=3.4, scale_y=3.4, scale_z=3.4,
           geometry=16, rotation_mode=ROTATION_MODE_HTR, rotate_x=180.0,
           color_r=NORTH_RGB[0], color_g=NORTH_RGB[1], color_b=NORTH_RGB[2],
           color_a=255, show_text=1, text="north magnetic (dip) pole",
           ch_input_id=CH_POLE_N_LON)
    sb.add(type=5, parent_id=g, branch_level=1,
           translate_x=round(spath[-1][1], 4), translate_y=round(spath[-1][0], 4),
           translate_z=9.0, scale_x=3.4, scale_y=3.4, scale_z=3.4,
           geometry=16, rotation_mode=ROTATION_MODE_HTR, rotate_x=180.0,
           color_r=SOUTH_RGB[0], color_g=SOUTH_RGB[1], color_b=SOUTH_RGB[2],
           color_a=255, show_text=1, text="south magnetic (dip) pole",
           ch_input_id=CH_POLE_S_LON)

    sb.colorbar(-GLOBE_R - 36.0, "20 uT", "68 uT", "field strength")
    sb.timeline(-GLOBE_R - 16.0, yrs)
    sb.caption(GLOBE_R + 36.0,
               f"Earth's magnetic field, {int(yrs[0])}-{int(yrs[-1])}  |  "
               f"gufm1 + IGRF-14", size=2.4)
    sb.caption(GLOBE_R + 29.0,
               "each cone points along the local field: bearing = declination,"
               " dip = inclination", size=1.4)

    # --- channels -----------------------------------------------------------
    map_rows, data = [], {"cyclecount": list(range(1, len(yrs) + 1))}

    def bind(chan, track, attr):
        map_rows.append(dict(id=len(map_rows) + 1, channel_id=chan,
                             track_id=track, attribute=attr,
                             track_table_id=0, ch_map_table_id=0, record_id=0))

    for i in range(n_vec):
        ch = CH_VEC_TILT + i
        bind(ch, CH_VEC_TILT + i, "rotate_x")
        bind(ch, CH_VEC_HEAD + i, "rotate_y")
        bind(ch, CH_VEC_COLOR + i, "color_index")
        data[f"ch{CH_VEC_TILT + i}"] = [round(float(tilt[k, i]), 3)
                                        for k in range(len(yrs))]
        data[f"ch{CH_VEC_HEAD + i}"] = [round(float(head[k, i]), 3)
                                        for k in range(len(yrs))]
        data[f"ch{CH_VEC_COLOR + i}"] = [int(cidx[k, i])
                                         for k in range(len(yrs))]

    bind(CH_POLE_N_LON, CH_POLE_N_LON, "translate_x")
    bind(CH_POLE_N_LON, CH_POLE_N_LAT, "translate_y")
    bind(CH_POLE_S_LON, CH_POLE_S_LON, "translate_x")
    bind(CH_POLE_S_LON, CH_POLE_S_LAT, "translate_y")
    data[f"ch{CH_POLE_N_LON}"] = [round(p[1], 4) for p in npath]
    data[f"ch{CH_POLE_N_LAT}"] = [round(p[0], 4) for p in npath]
    data[f"ch{CH_POLE_S_LON}"] = [round(p[1], 4) for p in spath]
    data[f"ch{CH_POLE_S_LAT}"] = [round(p[0], 4) for p in spath]

    bind(CH_CURSOR, CH_CURSOR, "translate_x")
    data[f"ch{CH_CURSOR}"] = [sb._x_of_year(y) for y in yrs]

    return (sb.to_dataframe(), pd.DataFrame(map_rows), pd.DataFrame(data),
            {"vectors": n_vec, "frames": len(yrs)})


# ---------------------------------------------------------------------------
# 6. SCENE 2 — INTENSITY SHELL
# ---------------------------------------------------------------------------
def build_intensity_shell(yrs: list[float]):
    lons = np.arange(-180.0, 180.0, SHELL_LON_STEP)
    lats = np.arange(-SHELL_LAT_LIMIT, SHELL_LAT_LIMIT + 1e-9, SHELL_LAT_STEP)
    LA, LO = np.meshgrid(lats, lons, indexing="ij")
    lat_f, lon_f = LA.ravel(), LO.ravel()
    n = lat_f.size
    print(f"  evaluating {n} shell samples x {len(yrs)} epochs "
          f"({n * len(yrs):,} field solutions) ...")

    hgt = np.zeros((len(yrs), n))
    cidx = np.zeros((len(yrs), n), dtype=int)
    saa = []
    # A generous South-Atlantic/African window: the anomaly's minimum starts
    # over Africa in 1590 and ends up over Paraguay, so the search box has to
    # cover the whole journey.
    WLA, WLO = np.meshgrid(np.arange(-55.0, 15.1, 1.0),
                           np.arange(-95.0, 45.1, 1.0), indexing="ij")
    wla, wlo = WLA.ravel(), WLO.ravel()
    for k, y in enumerate(yrs):
        m = geomag.field_at(y, lat_f, lon_f)
        hgt[k] = shell_height(m["F"])
        cidx[k] = f_index(m["F"])
        w = geomag.field_at(y, wla, wlo)["F"]
        j = int(np.argmin(w))
        saa.append((float(wla[j]), float(wlo[j]), float(w[j])))

    sb = SceneBuilder()
    sb.world()
    g = sb.globe()

    for i in range(n):
        rgb = index_rgb(int(cidx[-1, i]))
        sb.add(type=5, parent_id=g, branch_level=1,
               translate_x=round(float(lon_f[i]), 3),
               translate_y=round(float(lat_f[i]), 3),
               translate_z=round(float(hgt[-1, i]), 3),
               scale_x=0.3, scale_y=0.3, scale_z=0.3,
               geometry=22, ratio=0.16,
               color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=250,
               color_index=int(cidx[-1, i]), palette_id=PALETTE_ID,
               ch_input_id=CH_SHELL_Z + i)

    # Marker tracking the weakest point in the anomaly.
    sb.add(type=5, parent_id=g, branch_level=1,
           translate_x=round(saa[-1][1], 4), translate_y=round(saa[-1][0], 4),
           # Just above the floor of the dent, not above the whole shell:
           # radial elevation at 26 S tips a high marker down and away from
           # the depression it is supposed to be pointing at.
           translate_z=SHELL_LO + 8.0, scale_x=3.6, scale_y=3.6, scale_z=3.6,
           geometry=17, color_r=255, color_g=110, color_b=110, color_a=255,
           show_text=1, text="weakest field on Earth",
           ch_input_id=CH_SAA_LON)

    sb.colorbar(-GLOBE_R - 40.0, "20 uT", "68 uT", "field strength")
    sb.timeline(-GLOBE_R - 20.0, yrs)
    sb.caption(GLOBE_R + 46.0,
               f"Field strength as height, {int(yrs[0])}-{int(yrs[-1])}",
               size=2.4)
    sb.caption(GLOBE_R + 39.0,
               f"the dent over the South Atlantic deepens from "
               f"{saa[0][2]/1000:.1f} to {saa[-1][2]/1000:.1f} uT "
               f"and drifts {abs(saa[-1][1]-saa[0][1]):.0f} deg west",
               size=1.4)

    map_rows, data = [], {"cyclecount": list(range(1, len(yrs) + 1))}

    def bind(chan, track, attr):
        map_rows.append(dict(id=len(map_rows) + 1, channel_id=chan,
                             track_id=track, attribute=attr,
                             track_table_id=0, ch_map_table_id=0, record_id=0))

    for i in range(n):
        ch = CH_SHELL_Z + i
        bind(ch, CH_SHELL_Z + i, "translate_z")
        bind(ch, CH_SHELL_COLOR + i, "color_index")
        data[f"ch{CH_SHELL_Z + i}"] = [round(float(hgt[k, i]), 3)
                                       for k in range(len(yrs))]
        data[f"ch{CH_SHELL_COLOR + i}"] = [int(cidx[k, i])
                                           for k in range(len(yrs))]

    bind(CH_SAA_LON, CH_SAA_LON, "translate_x")
    bind(CH_SAA_LON, CH_SAA_LAT, "translate_y")
    data[f"ch{CH_SAA_LON}"] = [round(s[1], 4) for s in saa]
    data[f"ch{CH_SAA_LAT}"] = [round(s[0], 4) for s in saa]
    bind(CH_CURSOR, CH_CURSOR, "translate_x")
    data[f"ch{CH_CURSOR}"] = [sb._x_of_year(y) for y in yrs]

    return (sb.to_dataframe(), pd.DataFrame(map_rows), pd.DataFrame(data),
            {"samples": n, "frames": len(yrs), "saa": saa})


# ---------------------------------------------------------------------------
# 7. VALIDATION AND OUTPUT
# ---------------------------------------------------------------------------
BINDABLE = ({f"{p}_{a}" for p in ("translate", "rotate", "scale") for a in "xyz"}
            | {f"{p}_rate_{a}" for p in ("translate", "rotate", "scale")
               for a in "xyz"}
            | {"color_r", "color_g", "color_b", "color_a", "color_index",
               "palette_id", "texture_id", "ratio", "topo", "geometry",
               "mesh_id", "hide", "show_text", "render_mode", "fog_enabled",
               "fog_start", "fog_end"})


def validate(df: pd.DataFrame) -> list[str]:
    p = []
    if df.id.duplicated().any():
        p.append("duplicate ids")
    known = set(df.id)
    if len(df[(df.parent_id != 0) & (~df.parent_id.isin(known))]):
        p.append("rows with unknown parent_id")
    links = df[df.type == 7]
    if len(links) and (~links.child_id.isin(known)).any():
        p.append("link child_id references a missing node")
    for c in ("color_r", "color_g", "color_b", "color_a"):
        if ((df[c] < 0) | (df[c] > 255)).any():
            p.append(f"{c} out of 0..255")
    if ((df.color_index < 0) | (df.color_index > 127)).any():
        p.append("color_index outside 0..127")
    vis = df[(df.hide == 0) & (df.type.isin([5, 7]))]
    if (vis[["scale_x", "scale_y", "scale_z"]] < 0.2).any(axis=None):
        p.append("visible glyph with raw scale < 0.2")
    if df[df.type == 6].empty:
        p.append("no World Grid in the scene")
    kids = df[df.parent_id.isin(set(df[df.type == 6].id))]
    if len(kids) and (kids.translate_x.abs().max() > 180.0
                      or kids.translate_y.abs().max() > 90.0):
        p.append("globe child outside lon/lat range")
    return p


def validate_channels(df, ch_map, ch_tracks) -> list[str]:
    p = []
    channels = set(ch_map.channel_id)
    used = set(df.loc[df.ch_input_id != 0, "ch_input_id"])
    if used - channels:
        p.append(f"ch_input_id with no map row: {sorted(used - channels)[:5]}")
    if channels - used:
        p.append(f"map channel with no node: {sorted(channels - used)[:5]}")
    cols = {int(c[2:]) for c in ch_tracks.columns
            if c.startswith("ch") and c[2:].isdigit()}
    if set(ch_map.track_id) - cols:
        p.append(f"map track_id with no ch<id> column: "
                 f"{sorted(set(ch_map.track_id) - cols)[:5]}")
    if set(ch_map.attribute) - BINDABLE:
        p.append(f"unbindable attributes: "
                 f"{sorted(set(ch_map.attribute) - BINDABLE)}")
    for t in ch_map.loc[ch_map.attribute == "color_index", "track_id"]:
        col = ch_tracks[f"ch{t}"]
        if ((col < 0) | (col > 127)).any():
            p.append(f"ch{t}: color_index outside 0..127")
            break
    for t in ch_map.loc[ch_map.attribute == "translate_y", "track_id"]:
        col = ch_tracks[f"ch{t}"]
        if (col.abs() > 90.0).any():
            p.append(f"ch{t}: animated latitude outside -90..90")
            break
    return p


def write_csv(df: pd.DataFrame, path: Path, float_format="%.4f") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\r\n",
              float_format=float_format)
    back = pd.read_csv(path, encoding="utf-8", low_memory=False)
    assert len(back) == len(df), f"round-trip row-count mismatch: {path}"


def emit(name: str, stem: str, node_df, ch_map, ch_tracks) -> bool:
    problems = validate(node_df) + validate_channels(node_df, ch_map,
                                                     ch_tracks)
    if problems:
        for x in problems:
            print(f"  VALIDATION FAILURE [{name}]: {x}", file=sys.stderr)
        return False
    out = HERE / name
    write_csv(node_df, out / f"{stem}_gv_node.csv")
    write_csv(ch_map, out / f"{stem}_gv_ch-map.csv", float_format=None)
    write_csv(ch_tracks, out / f"{stem}_gv_ch-tracks.csv", float_format="%.3f")
    print(f"  {name}: {len(node_df):,} nodes, {len(ch_map):,} bindings, "
          f"{len(ch_tracks):,} frames x {len(ch_tracks.columns)-1:,} tracks"
          f"  [validation clean]")
    return True


# ---------------------------------------------------------------------------
# 8. MAIN
# ---------------------------------------------------------------------------
SCENES = ("Field_And_Poles", "Intensity_Shell")


def main() -> int:
    global YEAR_STEP
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--only", choices=SCENES, action="append")
    ap.add_argument("--step", type=int, default=YEAR_STEP,
                    help="years between animation frames (default 5)")
    args = ap.parse_args()
    YEAR_STEP = args.step

    yrs = years()
    print(f"Epochs: {int(yrs[0])}-{int(yrs[-1])} every {YEAR_STEP} yr "
          f"({len(yrs)} frames); models "
          f"{geomag.coeffs_for(yrs[0])[2]} -> {geomag.coeffs_for(yrs[-1])[2]}")

    wanted = args.only or list(SCENES)
    ok = True

    npath = spath = None
    if "Field_And_Poles" in wanted:
        npath, spath = pole_paths(yrs)
        node, cmap, ctr, info = build_field_and_poles(yrs, npath, spath)
        ok &= emit("Field_And_Poles", "GeomagField", node, cmap, ctr)
        print(f"     north dip pole: {npath[0][0]:.1f},{npath[0][1]:.1f} "
              f"({int(yrs[0])}) -> {npath[-1][0]:.1f},{npath[-1][1]:.1f} "
              f"({int(yrs[-1])})")
        # Report speed averaged over long spans, not per 5-year epoch: near
        # the pole the |I| = 90 surface is very flat, so a single epoch's
        # located position carries a wobble of a few tens of km that a short
        # baseline turns into wild apparent speeds.
        sp = pole_speed_kmyr(npath, yrs)
        for lo, hi in ((1600, 1800), (1800, 1900), (1900, 1990),
                       (1990, 2025)):
            v = [s for y, s in zip(yrs, sp) if lo < y <= hi]
            if v:
                print(f"       mean speed {lo}-{hi}: "
                      f"{sum(v)/len(v):5.1f} km/yr")

    if "Intensity_Shell" in wanted:
        node, cmap, ctr, info = build_intensity_shell(yrs)
        ok &= emit("Intensity_Shell", "GeomagShell", node, cmap, ctr)
        s0, s1 = info["saa"][0], info["saa"][-1]
        print(f"     South Atlantic Anomaly minimum: "
              f"{s0[2]/1000:.1f} uT at {s0[0]:.0f},{s0[1]:.0f} "
              f"({int(yrs[0])})  ->  {s1[2]/1000:.1f} uT at "
              f"{s1[0]:.0f},{s1[1]:.0f} ({int(yrs[-1])})")

    print("\nOpen either scene's node CSV in GlyphViz. Space plays four "
          "centuries of secular variation.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
