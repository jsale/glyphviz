#!/usr/bin/env python3
"""
build_wind_scenes.py — the wind rose as a hyperglyph, planet-wide.

A wind rose is not an encoding invented to justify a nested glyph: it is the
standard meteorological representation, and it already *has* the anatomy.  A
station's rose is a hub carrying sixteen compass arms, and every arm is itself
a stack of speed-bin segments.  That is three real levels of structure before
the World Grid is counted, and every level carries measured data.

  Rose_Anatomy/   Twelve archetype stations laid out on a plane, drawn large
                  and labelled, so one glyph can actually be read: the calm
                  core at the centre, sixteen petals whose length is how often
                  the wind blows from that quarter, each petal banded by speed,
                  and a needle showing the vector-mean wind.  Learn the
                  anatomy here; then read the planet in the other scene.

  Monsoon_Year/   ~200 stations on the globe, animated through the twelve
                  months of the year.  Every rose reshapes itself on the same
                  clock.  The trades over the Atlantic barely move; the
                  westerlies breathe; and around the Indian Ocean, West Africa
                  and northern Australia the petals swing bodily through 180
                  degrees as the monsoon reverses.  A marker tracks the
                  subsolar latitude, which is the reason it happens.

Placement note (verified against the real engine, not assumed): a station hub
is a child of a Sphere-geometry World Grid, so its local frame is +Z up, +Y
east, +X south.  Its topo is Cylinder, whose children are placed at
`offset = ((B+tz)cos tx, (B+tz)sin tx, ty)` and carried around by Rz(tx).
Compass bearing therefore maps to the arm's translate_x as

    translate_x = 180 - bearing

which puts every arm exactly in the local horizontal plane at every latitude.

Usage:
    python build_wind_scenes.py
    python build_wind_scenes.py --only Rose_Anatomy

Requires: numpy, pandas.  No network — reads the vendored climatology in
data/ produced by fetch_wind.py.
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
DATA = HERE / "data"

# ---------------------------------------------------------------------------
# 1. CONSTANTS
# ---------------------------------------------------------------------------
GLOBE_R = 180.0 / math.pi        # a scale-1 globe: 1 degree of arc = 1 world unit

N_SECTORS = 16
SECTOR_DEG = 360.0 / N_SECTORS
BIN_LABELS = ["0.5-2", "2-4", "4-6", "6-9", "9+"]
N_BINS = len(BIN_LABELS)

# Cube geometry is inscribed in the unit sphere, so a cube of scale s spans
# +-s/sqrt(3): a segment of world length L needs scale L*sqrt(3)/2.
CUBE_HALF = 1.0 / math.sqrt(3.0)
LEN_TO_SCALE = 1.0 / (2.0 * CUBE_HALF)          # = sqrt(3)/2

# The renderer floors each node's OWN scale (x base_scale) at 0.2 per axis and
# then multiplies by the parent basis, so a segment authored below 0.2 is drawn
# BIGGER than it encodes -- the encoding would lie.  Every hub and arm here is
# scale 1, so the floor lands directly on the segment and caps how short a
# speed band can honestly be: 0.2 * 2/sqrt(3) ~ 0.231 world units.  Segments
# under that are merged into a neighbour rather than silently inflated.
SCALE_FLOOR = 0.2
MIN_SEG_LEN = SCALE_FLOOR / LEN_TO_SCALE        # ~0.2309 world units

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# Speed-bin ramp: cool = light air, hot = strong.  Monotonic in warmth so a
# petal reads as a thermometer from the middle outward.
BIN_RGB = [(150, 205, 240), (85, 160, 225), (245, 205, 95),
           (240, 130, 60), (214, 52, 48)]
CALM_RGB = (205, 205, 215)
NEEDLE_RGB = (255, 240, 170)
BG = (10, 12, 20, 255)
ACCENT = (232, 238, 250)

# geometry ids
GEO_CUBE, GEO_SPHERE, GEO_CONE = 1, 3, 5
GEO_SPHERE_WIRE, GEO_CIRCLE = 2, 24

TOPO_NONE, TOPO_SPHERE, TOPO_CYLINDER, TOPO_PLANE = 0, 2, 4, 8
ROT_EULER, ROT_HTR = 0, 1

# Reference frequency that maps to a full-length petal.  Fixed across every
# station so petal length is comparable between glyphs rather than
# self-normalised per rose.  0.28 sits just above the 75th percentile of
# per-station peak sectors, so it uses most of the dynamic range while
# clipping only the ~2% of sectors that are more concentrated than that.
SECTOR_REF = 0.28

# The globe is drawn at this World Grid scale.  Grid scale re-spaces child
# POSITIONS without touching subtree size (measured, not assumed: at scale 3
# hub separation goes 9.99 -> 29.96 world units while the arm offset stays
# 4.000 and the segment's world scale stays 0.5000).  That is what lets the
# roses be drawn large enough for their speed bands to clear the 0.2 render
# floor while still fitting ~100 stations on the planet.
GRID_SCALE = 3.0


# ---------------------------------------------------------------------------
# 2. SCENE BUILDER
# ---------------------------------------------------------------------------
COLUMNS = ["id", "type", "parent_id", "branch_level", "child_id",
           "translate_x", "translate_y", "translate_z",
           "rotate_x", "rotate_y", "rotate_z",
           "scale_x", "scale_y", "scale_z",
           "color_r", "color_g", "color_b", "color_a", "color_index",
           "geometry", "hide", "topo", "ratio", "texture_id",
           "ch_input_id", "show_text",
           "trigger_lo_x", "trigger_hi_x", "trigger_lo_y", "trigger_hi_y",
           "segments_x", "segments_y", "rotation_mode", "text"]

DEFAULTS = dict(child_id=0, translate_x=0.0, translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=255, color_g=255, color_b=255, color_a=255,
                color_index=0, geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE,
                ratio=0.1, texture_id=0, ch_input_id=0, show_text=0,
                trigger_lo_x=0, trigger_hi_x=0, trigger_lo_y=0,
                trigger_hi_y=0, segments_x=36, segments_y=18,
                rotation_mode=ROT_EULER, text="")


def sanitize(t: str) -> str:
    """Tag text must survive a UTF-8 round trip; one bad byte drops every tag."""
    t = unicodedata.normalize("NFKD", str(t))
    return "".join(c for c in t if 32 <= ord(c) < 127).strip()


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
                        color_r=BG[0], color_g=BG[1], color_b=BG[2],
                        color_a=BG[3])

    def caption(self, text, size=2.0, rgb=ACCENT, ch=0, **pos) -> int:
        return self.add(type=5, parent_id=0, branch_level=0,
                        scale_x=size, scale_y=size, scale_z=size,
                        geometry=GEO_CIRCLE, ratio=0.02,
                        color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                        color_a=200, show_text=1, text=sanitize(text),
                        ch_input_id=ch, **pos)

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=COLUMNS)


# ---------------------------------------------------------------------------
# 3. THE ROSE GLYPH
# ---------------------------------------------------------------------------
def calm_radius(rose_r: float, calm_frac: float) -> float:
    """Radius of the still-air core at the centre of a rose.

    Used by both the static build and the monthly channel tracks; they must
    agree exactly or the animated segments would start at the wrong radius.
    """
    return 0.12 * rose_r + 0.5 * rose_r * calm_frac


def merge_small(segs: list[tuple[float, int]],
                floor: float) -> list[tuple[float, int, tuple[int, ...]]]:
    """Fold sub-floor segments into a neighbour, preserving total length.

    The renderer cannot draw a segment shorter than `floor`, and inflating one
    silently would overstate a rare speed bin.  Merging instead keeps the
    petal's total length -- the frequency of wind from that quarter -- exactly
    right, at the cost of colour resolution in the tail.  The colour kept is
    the longer contributor's.

    Returns (length, colour bin, bins covered).  The covered-bin tuple is what
    lets the monthly animation allocate across exactly this grouping instead of
    re-merging per month, which would make bands appear and vanish and lose
    their length (see _bind_segment).
    """
    work = [(ln, c, (c,)) for ln, c in segs if ln > 0]
    if not work:
        return []
    # A whole petal shorter than the floor cannot be drawn honestly at any
    # subdivision, so that direction is simply not drawn rather than inflated
    # to a misleading minimum stub.
    if sum(ln for ln, _c, _b in work) < floor:
        return []
    changed = True
    while changed and len(work) > 1:
        changed = False
        for i, (ln, c, bins) in enumerate(work):
            if ln >= floor:
                continue
            j = i - 1 if i > 0 else 1
            other_len, other_c, other_bins = work[j]
            keep_c = c if ln > other_len else other_c
            merged = (ln + other_len, keep_c,
                      tuple(sorted(set(bins) | set(other_bins))))
            lo, hi = min(i, j), max(i, j)
            work = work[:lo] + [merged] + work[hi + 1:]
            changed = True
            break
    return [t for t in work if t[0] >= floor]


@dataclass
class RoseStats:
    """Banding retention: how much of a rose survives the 0.2 render floor.

    Counting merges per petal is misleading because a third of all sectors are
    genuine stubs (frequency < 2%) that *should* collapse to one segment.
    What matters is whether the petals carrying the wind keep their speed
    bands, so bands are also averaged weighted by petal length.
    """
    merges: int = 0
    segments: int = 0
    petals: int = 0
    band_len: float = 0.0          # sum over petals of bands * length
    total_len: float = 0.0         # sum over petals of length
    dom_bands: list = field(default_factory=list)   # bands in each rose's peak

    def report(self) -> str:
        w = self.band_len / self.total_len if self.total_len else 0.0
        dom = (sum(self.dom_bands) / len(self.dom_bands)
               if self.dom_bands else 0.0)
        return (f"{self.segments} segments / {self.petals} petals; "
                f"bands per petal: {self.segments / max(1, self.petals):.2f} "
                f"unweighted, {w:.2f} length-weighted; "
                f"dominant petal keeps {dom:.2f} bands")


def add_rose(sb: SceneBuilder, parent: int, parent_level: int,
             row: pd.Series, rose_r: float, *, hub_kw: dict,
             stats: RoseStats, channels: dict | None = None,
             months: pd.DataFrame | None = None,
             label: str = "") -> int:
    """Build one station's rose under `parent`.  Returns the hub node id.

    Structure, all of it data-bearing:

        hub            invisible frame, topo=Cylinder      (level L)
        +- calm core   sphere sized by the calm fraction   (level L+1)
        +- needle      cone aimed along the vector mean    (level L+1)
        +- arm x16     invisible, placed at 180 - bearing  (level L+1)
           +- segment  cube per speed bin, stacked outward (level L+2)
    """
    hub = sb.add(type=5, parent_id=parent, branch_level=parent_level + 1,
                 topo=TOPO_CYLINDER, hide=1, geometry=GEO_SPHERE,
                 scale_x=1.0, scale_y=1.0, scale_z=1.0, **hub_kw)

    # --- calm core: how often the air is still -----------------------------
    calm_r = calm_radius(rose_r, float(row.calm_frac))
    core = sb.add(type=5, parent_id=hub, branch_level=parent_level + 2,
                  translate_x=0.0, translate_y=0.0, translate_z=-1.0,
                  geometry=GEO_SPHERE, ratio=0.1,
                  scale_x=calm_r, scale_y=calm_r, scale_z=calm_r,
                  color_r=CALM_RGB[0], color_g=CALM_RGB[1],
                  color_b=CALM_RGB[2], color_a=220,
                  show_text=1 if label else 0, text=sanitize(label))

    # --- resultant needle: vector mean, i.e. directional constancy ---------
    # Length is the resultant speed as a fraction of the scalar mean, so a
    # trade-wind station gets a long needle and a variable one a stub.
    con = float(row.constancy)
    ndl_len = 0.35 * rose_r + 0.75 * rose_r * con
    warmth = int(90 + 165 * con)
    sb.add(type=5, parent_id=hub, branch_level=parent_level + 2,
           translate_x=180.0 - float(row.resultant_dir),
           translate_y=0.0, translate_z=ndl_len * 0.5 - 1.0,
           geometry=GEO_CONE, rotation_mode=ROT_HTR,
           rotate_x=90.0, rotate_y=-90.0,
           scale_x=0.045 * rose_r, scale_y=0.045 * rose_r,
           scale_z=ndl_len * 0.5,
           color_r=NEEDLE_RGB[0], color_g=NEEDLE_RGB[1],
           color_b=warmth, color_a=235)

    # --- sixteen compass arms ----------------------------------------------
    sector_totals = [sum(float(row[f"s{t:02d}b{k}"]) for k in range(N_BINS))
                     for t in range(N_SECTORS)]
    dom_idx = int(np.argmax(sector_totals))

    for s in range(N_SECTORS):
        bearing = s * SECTOR_DEG
        arm = sb.add(type=5, parent_id=hub, branch_level=parent_level + 2,
                     translate_x=180.0 - bearing, translate_y=0.0,
                     translate_z=-1.0, topo=TOPO_NONE, hide=1,
                     geometry=GEO_CUBE,
                     scale_x=1.0, scale_y=1.0, scale_z=1.0)

        raw = [(float(row[f"s{s:02d}b{k}"]), k) for k in range(N_BINS)]
        sector_total = sector_totals[s]
        if sector_total <= 0:
            continue
        petal = min(1.0, sector_total / SECTOR_REF) * rose_r
        lens = [(petal * (v / sector_total), k) for v, k in raw]
        before = len([1 for ln, _ in lens if ln > 0])
        segs = merge_small(lens, MIN_SEG_LEN)
        stats.merges += max(0, before - len(segs))
        stats.petals += 1
        stats.band_len += len(segs) * petal
        stats.total_len += petal
        if s == dom_idx:
            stats.dom_bands.append(len(segs))

        cursor = calm_r * 0.85
        for seg_len, k, covered in segs:
            half = seg_len / 2.0
            rgb = BIN_RGB[k]
            seg = sb.add(type=5, parent_id=arm,
                         branch_level=parent_level + 3,
                         translate_x=cursor + half, translate_y=0.0,
                         translate_z=0.0, geometry=GEO_CUBE,
                         scale_x=seg_len * LEN_TO_SCALE,
                         scale_y=0.115 * rose_r, scale_z=0.075 * rose_r,
                         color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                         color_a=245)
            stats.segments += 1
            cursor += seg_len

            if channels is not None and months is not None:
                groups = [c for _l, _k, c in segs]
                _bind_segment(channels, seg, months, s, covered, groups,
                              rose_r)

    return hub


def _bind_segment(channels: dict, node_id: int, months: pd.DataFrame,
                  sector: int, covered: tuple[int, ...],
                  groups: list[tuple[int, ...]], rose_r: float) -> None:
    """Animate one segment's length and radial position over the 12 months.

    A segment is a cube centred on its node, so growing it means moving it too:
    both translate_x and scale_x are driven, and the whole petal is recomputed
    together each month so the stack stays contiguous every frame.

    The segments themselves are fixed by the ANNUAL rose, so each month is
    allocated across that same grouping rather than re-merged from scratch --
    otherwise a band that merges differently in July would have no node to live
    on, and the petal would silently come up short.  Within a month any group
    falling under the render floor is parked inside the calm core and the
    remaining groups are rescaled to keep the petal's total length -- the
    frequency of wind from that quarter -- exactly right.
    """
    lens_by_month, pos_by_month = [], []
    for _m, mrow in months.iterrows():
        freq = [float(mrow[f"s{sector:02d}b{k}"]) for k in range(N_BINS)]
        tot = sum(freq)
        calm_r = calm_radius(rose_r, float(mrow.calm_frac))
        start = calm_r * 0.85

        if tot <= 0:
            lens_by_month.append(MIN_SEG_LEN * LEN_TO_SCALE)
            pos_by_month.append(0.0)
            continue

        petal = min(1.0, tot / SECTOR_REF) * rose_r
        raw = [petal * sum(freq[b] for b in g) / tot for g in groups]
        keep = [i for i, ln in enumerate(raw) if ln >= MIN_SEG_LEN]
        kept_sum = sum(raw[i] for i in keep)
        lens = [0.0] * len(groups)
        if kept_sum > 0:
            for i in keep:
                lens[i] = raw[i] * petal / kept_sum

        cursor, found = start, None
        for i, g in enumerate(groups):
            if lens[i] <= 0.0:
                if g == covered:
                    # parked: floor-length, at the hub centre, where the calm
                    # core (radius >= 0.12*rose_r) hides it
                    found = (MIN_SEG_LEN, 0.0)
                continue
            if g == covered:
                found = (lens[i], cursor + lens[i] / 2.0)
                break
            cursor += lens[i]
        if found is None:
            found = (MIN_SEG_LEN, 0.0)
        lens_by_month.append(found[0] * LEN_TO_SCALE)
        pos_by_month.append(found[1])
    channels["seg"].append((node_id, lens_by_month, pos_by_month))


# ---------------------------------------------------------------------------
# 4. STATION SELECTION
# ---------------------------------------------------------------------------
def great_circle_deg(a_lat, a_lon, b_lat, b_lon) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dl = math.radians(b_lon - a_lon)
    x = (math.sin(p1) * math.sin(p2)
         + math.cos(p1) * math.cos(p2) * math.cos(dl))
    return math.degrees(math.acos(max(-1.0, min(1.0, x))))


def thin_stations(st: pd.DataFrame, min_sep_deg: float) -> pd.DataFrame:
    """Greedy thinning so no two roses can overlap on the globe."""
    kept: list[pd.Series] = []
    for _i, row in st.iterrows():
        if all(great_circle_deg(row.lat, row.lon, k.lat, k.lon) >= min_sep_deg
               for k in kept):
            kept.append(row)
    return pd.DataFrame(kept).reset_index(drop=True)


def annual(roses: pd.DataFrame) -> pd.DataFrame:
    """Observation-weighted annual mean of the monthly rose tables."""
    num = [c for c in roses.columns if c not in ("sid", "month")]
    g = roses.groupby("sid")
    out = g.apply(lambda d: pd.Series(
        {c: np.average(d[c], weights=d.n_obs) for c in num}),
        include_groups=False)
    # resultant_dir is a bearing: average it as a vector, not a number
    def vec_dir(d):
        th = np.radians(d.resultant_dir.values)
        w = d.n_obs.values * d.resultant_speed.values
        return math.degrees(math.atan2(np.average(np.sin(th), weights=w),
                                       np.average(np.cos(th), weights=w))) % 360
    out["resultant_dir"] = g.apply(vec_dir, include_groups=False)
    return out.reset_index()


# ---------------------------------------------------------------------------
# 5. SCENE 1 — ROSE ANATOMY
# ---------------------------------------------------------------------------
# (match pattern, short name, one-line regime note).  Short names because tag
# text is drawn in screen space and long strings from neighbouring glyphs run
# into each other however far apart the roses are placed.
ARCHETYPES = [
    ("ASCENSION", "Ascension I.", "SE trades - one quarter, all year"),
    ("GRANTLEY ADAMS", "Barbados", "NE trades"),
    ("MALLAM AMINU KANO", "Kano", "monsoon vs harmattan"),
    ("DARWIN", "Darwin", "Australian monsoon"),
    ("SULTAN MAHMUD BADARUDDIN", "Palembang", "equatorial Sumatra"),
    ("TOKYO", "Tokyo", "East Asian monsoon"),
    ("SHANNON", "Shannon", "N Atlantic westerlies"),
    ("WELLINGTON", "Wellington", "the Roaring Forties"),
    ("JIUQUAN", "Jiuquan", "Gobi - no prevailing quarter"),
    ("ALMERIA", "Almeria", "Mediterranean sea breeze"),
    ("KING SALMON", "King Salmon", "Bering Sea storm track"),
    ("DENVER", "Denver", "high plains downslope"),
]


def screen(right: float, up: float) -> dict:
    """Lay a flat scene out the way it will be READ, looking straight down.

    Verified from the rendered compass ticks: in a top-down view GlyphViz maps
    world +Y to screen right and world -X to screen up.  Authoring in (right,
    up) and converting here keeps the layout code readable and stops the grid
    coming out transposed.
    """
    return dict(translate_x=-up, translate_y=right, translate_z=0.0)


def build_rose_anatomy(roses: pd.DataFrame, st: pd.DataFrame):
    ann = annual(roses).merge(st, on="sid")
    sb = SceneBuilder()
    sb.world()
    stats = RoseStats()

    chosen = []
    for pat, short, note in ARCHETYPES:
        m = ann[ann.name.str.upper().str.contains(pat, na=False, regex=False)]
        if len(m):
            chosen.append((m.iloc[0], short, note))
    if not chosen:
        raise SystemExit("no archetype stations matched the vendored data")

    cols, rose_r, pitch = 4, 11.0, 40.0
    rows = (len(chosen) + cols - 1) // cols
    for i, (row, short, note) in enumerate(chosen):
        right = (i % cols - (cols - 1) / 2.0) * pitch
        up = ((rows - 1) / 2.0 - i // cols) * pitch
        plate = sb.add(type=5, parent_id=0, branch_level=0,
                       topo=TOPO_NONE, hide=1, geometry=GEO_CUBE,
                       **screen(right, up))
        add_rose(sb, plate, 0, row, rose_r,
                 hub_kw=dict(translate_x=0.0, translate_y=0.0,
                             translate_z=0.0),
                 stats=stats)
        sb.add(type=5, parent_id=plate, branch_level=1,
               geometry=GEO_CIRCLE, ratio=0.02,
               scale_x=0.75, scale_y=0.75, scale_z=0.75,
               color_r=235, color_g=240, color_b=252, color_a=210,
               show_text=1, text=sanitize(short),
               **screen(0.0, rose_r * 1.42))
        # the regime note sits below its rose so two labels never share a line
        sb.add(type=5, parent_id=plate, branch_level=1,
               geometry=GEO_CIRCLE, ratio=0.02,
               scale_x=0.6, scale_y=0.6, scale_z=0.6,
               color_r=150, color_g=165, color_b=200, color_a=170,
               show_text=1, text=sanitize(note),
               **screen(0.0, -rose_r * 1.5))
        # compass ticks so the reader knows which way is north
        for bearing, tag in ((0, "N"), (90, "E"), (180, "S"), (270, "W")):
            ang = math.radians(180.0 - bearing)
            r = rose_r * 1.15
            sb.add(type=5, parent_id=plate, branch_level=1,
                   translate_x=r * math.cos(ang), translate_y=r * math.sin(ang),
                   translate_z=0.0, geometry=GEO_CIRCLE, ratio=0.02,
                   scale_x=0.7, scale_y=0.7, scale_z=0.7,
                   color_r=150, color_g=160, color_b=185, color_a=180,
                   show_text=1, text=tag)

    top = (rows - 1) / 2.0 * pitch
    left = -((cols - 1) / 2.0 * pitch + rose_r * 1.3)
    sb.caption(**screen(left, top + 24.0), size=2.6,
               text="Wind rose anatomy - 2019-2023 hourly climatology, NOAA ISD")
    sb.caption(**screen(left, top + 18.5), size=1.5,
               text="petal length = how often the wind blows FROM that quarter"
                    " | colour = speed | core = calm | needle = vector mean")
    for k, lab in enumerate(BIN_LABELS):
        rgb = BIN_RGB[k]
        sb.add(type=5, parent_id=0, branch_level=0, geometry=GEO_CUBE,
               scale_x=1.0, scale_y=2.4, scale_z=1.0,
               color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=245,
               show_text=1, text=f"{lab} m/s",
               **screen(left + 6.0 + k * 19.0, -(top + 22.0)))
    return sb.to_dataframe(), stats, len(chosen)


# ---------------------------------------------------------------------------
# 6. SCENE 2 — MONSOON YEAR
# ---------------------------------------------------------------------------
def subsolar_lat(month_index: int) -> float:
    """Solar declination at mid-month — why the monsoon reverses."""
    day = 15 + 30.44 * month_index
    return 23.44 * math.sin(math.radians(360.0 / 365.24 * (day - 80.0)))


def build_monsoon_year(roses: pd.DataFrame, st: pd.DataFrame,
                       min_sep: float):
    ann = annual(roses).merge(st, on="sid")
    ann = ann.sort_values("n_obs", ascending=False)
    keep = thin_stations(ann, min_sep)
    # 1 degree of arc = 1 world unit at grid scale 1, and grid scale multiplies
    # station spacing without touching rose size, so the roses can be this big.
    rose_r = 0.40 * min_sep * GRID_SCALE

    sb = SceneBuilder()
    sb.world()
    grid = sb.add(type=6, parent_id=0, branch_level=0, geometry=GEO_SPHERE,
                  texture_id=1, segments_x=36, segments_y=18,
                  scale_x=GRID_SCALE, scale_y=GRID_SCALE, scale_z=GRID_SCALE,
                  color_r=70, color_g=95, color_b=130, color_a=255,
                  topo=TOPO_NONE)

    stats = RoseStats()
    channels: dict[str, list] = {"seg": []}
    by_sid = {s: d.sort_values("month") for s, d in roses.groupby("sid")}

    for _i, row in keep.iterrows():
        months = by_sid[row.sid]
        if len(months) != 12:
            continue
        add_rose(sb, grid, 0, row, rose_r,
                 hub_kw=dict(translate_x=float(row.lon),
                             translate_y=float(row.lat),
                             translate_z=0.6),
                 stats=stats, channels=channels, months=months)

    # --- subsolar marker + month caption -----------------------------------
    sun = sb.add(type=5, parent_id=grid, branch_level=1,
                 translate_x=0.0, translate_y=0.0, translate_z=6.0 * GRID_SCALE,
                 geometry=GEO_SPHERE, scale_x=2.4, scale_y=2.4, scale_z=2.4,
                 color_r=255, color_g=225, color_b=120, color_a=245,
                 show_text=1, text="subsolar latitude")

    ch = 1
    map_rows: list[dict] = []
    data: dict[str, list] = {"cyclecount": list(range(1, 13))}

    def bind(chan: int, track: int, attr: str) -> None:
        map_rows.append(dict(id=len(map_rows) + 1, channel_id=chan,
                             track_id=track, attribute=attr,
                             track_table_id=0, ch_map_table_id=0, record_id=0))

    # subsolar latitude rides the globe
    sun_ch = ch
    ch += 1
    bind(sun_ch, sun_ch, "translate_y")
    data[f"ch{sun_ch}"] = [round(subsolar_lat(m), 3) for m in range(12)]
    sb.rows[sun - 1]["ch_input_id"] = sun_ch

    # one caption per month, revealed by its own hide track
    for m, name in enumerate(MONTHS):
        cch = ch
        ch += 1
        cid = sb.caption(f"{name}  -  monthly wind climatology 2019-2023",
                         size=2.6, ch=cch, translate_x=0.0, translate_y=0.0,
                         translate_z=GLOBE_R * GRID_SCALE + 22.0,
                         hide=0 if m == 0 else 1)
        bind(cch, cch, "hide")
        data[f"ch{cch}"] = [0 if k == m else 1 for k in range(12)]
        _ = cid

    # every speed-bin segment: length and radial position
    for node_id, lens, poss in channels["seg"]:
        c = ch
        ch += 1
        t_len, t_pos = c * 2, c * 2 + 1
        bind(c, t_len, "scale_x")
        bind(c, t_pos, "translate_x")
        data[f"ch{t_len}"] = [round(v, 4) for v in lens]
        data[f"ch{t_pos}"] = [round(v, 4) for v in poss]
        sb.rows[node_id - 1]["ch_input_id"] = c

    return (sb.to_dataframe(), pd.DataFrame(map_rows), pd.DataFrame(data),
            stats, len(keep), rose_r)


# ---------------------------------------------------------------------------
# 7. VALIDATION + OUTPUT
# ---------------------------------------------------------------------------
def validate(df: pd.DataFrame) -> list[str]:
    errs = []
    if df.id.duplicated().any():
        errs.append("duplicate node ids")
    ids = set(df.id)
    bad = df[(df.parent_id != 0) & (~df.parent_id.isin(ids))]
    if len(bad):
        errs.append(f"{len(bad)} rows reference a missing parent")
    for c in ("color_r", "color_g", "color_b", "color_a"):
        if not df[c].between(0, 255).all():
            errs.append(f"{c} out of range")
    if not df.geometry.between(0, 28).all():
        errs.append("geometry id out of range")
    if not df.topo.between(0, 17).all():
        errs.append("topo id out of range")
    vis = df[(df.hide == 0) & (df.type == 5)]
    for c in ("scale_x", "scale_y", "scale_z"):
        if (vis[c] <= 0).any():
            errs.append(f"non-positive {c} on a visible node")
    return errs


def validate_channels(df, ch_map, ch_tracks) -> list[str]:
    errs = []
    if ch_map is None or not len(ch_map):
        return errs
    track_cols = {int(c[2:]) for c in ch_tracks.columns
                  if c.startswith("ch") and c[2:].isdigit()}
    missing = set(ch_map.track_id) - track_cols
    if missing:
        errs.append(f"{len(missing)} ch-map track_ids have no ch<id> column")
    bound = set(df[df.ch_input_id > 0].ch_input_id)
    unmapped = bound - set(ch_map.channel_id)
    if unmapped:
        errs.append(f"{len(unmapped)} nodes bound to an unmapped channel")
    return errs


def write_csv(df: pd.DataFrame, path: Path, float_format="%.4f") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\r\n",
              float_format=float_format)
    back = pd.read_csv(path, encoding="utf-8", low_memory=False)
    assert len(back) == len(df), f"{path.name} did not round-trip"


def emit(name: str, stem: str, node_df, ch_map=None, ch_tracks=None) -> bool:
    errs = validate(node_df) + validate_channels(node_df, ch_map, ch_tracks)
    if errs:
        print(f"  !! {name}: " + "; ".join(errs))
        return False
    out = HERE / name
    write_csv(node_df, out / f"{stem}_gv_node.csv")
    if ch_map is not None and len(ch_map):
        write_csv(ch_map, out / f"{stem}_gv_ch-map.csv", float_format="%.6g")
        write_csv(ch_tracks, out / f"{stem}_gv_ch-tracks.csv",
                  float_format="%.4f")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e6
    print(f"  wrote {name}/  {len(node_df):,} nodes  ({size:.1f} MB)")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--min-sep", type=float, default=11.0,
                    help="minimum great-circle separation between roses, deg")
    args = ap.parse_args()

    roses = pd.read_csv(DATA / "wind_roses.csv")
    st = pd.read_csv(DATA / "wind_stations.csv")
    print(f"climatology: {len(st)} stations, {len(roses)} station-months")

    ok = True
    if args.only in ("", "Rose_Anatomy"):
        df, stats, n = build_rose_anatomy(roses, st)
        print(f"Rose_Anatomy: {n} archetype stations")
        print(f"              {stats.report()}")
        ok &= emit("Rose_Anatomy", "rose_anatomy", df)

    if args.only in ("", "Monsoon_Year"):
        df, cmap, ctr, stats, n, rr = build_monsoon_year(roses, st,
                                                         args.min_sep)
        print(f"Monsoon_Year: {n} stations at >= {args.min_sep} deg "
              f"separation, rose radius {rr:.1f} units "
              f"(render floor = {100 * MIN_SEG_LEN / rr:.1f}% of it)")
        print(f"              {stats.report()}")
        print(f"              {len(ctr.columns) - 1} tracks x {len(ctr)} frames")
        ok &= emit("Monsoon_Year", "monsoon_year", df, cmap, ctr)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
