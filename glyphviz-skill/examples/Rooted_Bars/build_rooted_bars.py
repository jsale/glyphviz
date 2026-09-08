#!/usr/bin/env python3
"""Rooted_Bars — four ways to draw a bar, side by side, measured.

A bar is the simplest thing a data visualisation asks for and the easiest
thing to get wrong in GlyphViz, because a length written into `scale_z` is
not a length: every geometry is centred on its own origin and spans -1..+1,
so the bar grows *both* ways and half of it goes below the baseline. Then
the viewer changes Global Scale and the baseline itself moves.

This scene draws the same fourteen values four times, once per recipe, so
the difference is visible rather than described:

                                            at GS 1          at GS 3
    row A  scale_z = H                   -0.58H..0.58H   -1.73H..1.73H
    row B  cube scale_z = H/1.155,
           lifted to translate_z = H/2        0..H            -H..2H
    row C  Pin  scale_z = H/1.1               0..H             0..3H
    row D  Link from a hidden base at 0
           to a hidden tip at H               0..H             0..H

Only D is invariant, because in D the height is a *coordinate* rather than
a size. That is the general rule: a length that carries data belongs in
position space. See SKILL.md hard rule 5.

Row A is wrong in two ways at once, and the second one is the subtler: a
cube is inscribed in the unit sphere, so its faces reach only 1/sqrt(3) of
its scale. `scale_z = H` therefore draws a bar 1.15H tall, centred on the
baseline -- shorter than the value it is supposed to encode as well as half
underground. Rows B and C divide that geometry factor back out, which is
why the same 0.55 half-width is written as scale 0.95 on a cube and 5.5 on
a Pin (a Pin is a needle 0.1 wide). Those numbers come from the checker's
measured `LOCAL_BOX` table, not from an assumption about what "scale 1"
means.

The numbers above are not asserted from the documentation -- `verify()`
re-measures every one of them through the real placement engine before the
scene is written, at Global Scale 1 and 3, and refuses to emit if any row
disagrees.

Data: the 14 unstable members of the uranium-238 decay chain, half-lives
from the IAEA ground-state table bundled with the Decay_Chain example
(`data/u238_chain.csv` is the 14-row extract). Bar height is decades of
half-life above the shortest-lived member, Po-214 at 164 microseconds --
a span of 20.9 orders of magnitude, which is exactly the kind of domain
that has to be clamped into a rendered range before it is drawn.

    python build_rooted_bars.py
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "code"))

from gv_kernel import load_node_csv, Scene, node_world_matrix  # noqa: E402
from gv_extents import local_box  # noqa: E402

# ---------------------------------------------------------------------------
# Constants that describe the scene, so nothing is a bare number below.
# ---------------------------------------------------------------------------
GEO_CUBE, GEO_SPHERE, GEO_PIN = 1, 3, 16
GEO_CYLINDER, GEO_GRID_WIRE, GEO_CIRCLE = 19, 20, 24
TOPO_NONE = 0
TYPE_GLYPH, TYPE_GRID, TYPE_LINK, TYPE_WORLD = 5, 6, 7, 0
ROT_EULER = 0

BG = (18, 20, 26, 255)
PLATE = (96, 104, 122, 150)
TITLE_RGB = (232, 236, 244)

BAR_PITCH = 3.0            # world units between bars in a row
ROW_PITCH = 12.0           # world units between recipe rows
BAR_HALF_WIDTH = 0.55      # RENDERED half-width of every bar, all four recipes
DECADE = 0.25              # world units per decade of half-life

# Every glyph fits inside radius 1, which is not the same as spanning -1..+1
# per axis, and the difference is the whole reason these four rows can be made
# to agree. Taken from the checker's measured table rather than assumed:
#   a cube's faces are 1/sqrt(3) = 0.577 out, so `scale` 0.55 is 0.318 wide;
#   a Pin is a needle 0.1 wide and 1.1 tall, so the same 0.55 is 0.055 wide --
#   ten times thinner than the cube beside it, which is exactly the bug this
#   scene would have shipped with had the numbers not been measured.
CUBE_HALF = local_box(GEO_CUBE)[0][0]        # 0.5774
PIN_HALF_XY = local_box(GEO_PIN)[0][0]       # 0.1
PIN_SPAN = float(local_box(GEO_PIN)[0][2] * 2.0)   # 1.1, and it starts at 0

# variable -> channel -> domain -> clamped range (SKILL.md rule 5 / design
# reference section 4). The domain is the real data's; the range is the room
# the design allots it, and nothing may leave that room.
#
#   variable  half-life                      channel  bar height
#   domain    164 us .. 4.5 Gy = 20.9 decades range    HEIGHT_MIN..HEIGHT_MAX
#
# The floor is not cosmetic. The shortest-lived nuclide sits at 0 decades and
# would otherwise be a bar of height 0 -- invisible, and unclickable, so its
# label could not be read either. At 0.44 every recipe's authored scale_z also
# stays above 0.2, so the scene reads identically whether or not the viewer has
# View > Enforce Minimum Glyph Size switched on (SKILL.md rule 6).
# The ceiling never binds on this data -- it is there for the next dataset.
HEIGHT_MIN, HEIGHT_MAX = 0.44, 5.40

RECIPES = [
    # key, label, row colour, one-line verdict
    ("A", "A  scale_z = H  -  half underground and only 0.58H above it",
     (214, 78, 74)),
    ("B", "B  cube scale_z = H/1.155 lifted H/2  -  exact at GS 1 only",
     (222, 152, 60)),
    ("C", "C  Pin scale_z = H/1.1  -  base holds, height scales with GS",
     (108, 186, 108)),
    ("D", "D  Link base 0 to tip H  -  invariant, the height is a coordinate",
     (92, 162, 226)),
]

COLUMNS = ["id", "type", "parent_id", "branch_level", "child_id",
           "translate_x", "translate_y", "translate_z",
           "rotate_x", "rotate_y", "rotate_z",
           "scale_x", "scale_y", "scale_z",
           "color_r", "color_g", "color_b", "color_a",
           "geometry", "hide", "topo", "ratio", "show_text", "rotation_mode",
           "trigger_lo_x", "trigger_hi_x", "trigger_lo_y", "trigger_hi_y",
           "segments_x", "segments_y", "text"]

DEFAULTS = dict(child_id=0, translate_x=0.0, translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=255, color_g=255, color_b=255, color_a=255,
                geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE, ratio=0.1,
                show_text=0, rotation_mode=ROT_EULER,
                trigger_lo_x=0.0, trigger_hi_x=0.0,
                trigger_lo_y=0.0, trigger_hi_y=0.0,
                segments_x=0, segments_y=0, text="")


@dataclass
class SceneBuilder:
    rows: list[dict] = field(default_factory=list)
    next_id: int = 1

    def add(self, **kw) -> int:
        self.rows.append({**DEFAULTS, "id": self.next_id, **kw})
        self.next_id += 1
        return self.next_id - 1

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=COLUMNS)


def sanitize(s: str) -> str:
    """Labels are written as UTF-8; keep them to characters a CSV round-trips."""
    return "".join(c for c in s if c.isprintable() and c not in '",')


# ---------------------------------------------------------------------------
# 1. DATA -> the clamped rendered range
# ---------------------------------------------------------------------------
def load_chain() -> pd.DataFrame:
    df = pd.read_csv(HERE / "data" / "u238_chain.csv")
    lo = math.log10(df.half_life_sec.min())
    df["decades"] = df.half_life_sec.map(lambda t: math.log10(t) - lo)
    # Clamp on the way in, not after something has already gone wrong.
    df["height"] = df.decades.map(
        lambda d: min(HEIGHT_MAX, max(HEIGHT_MIN, d * DECADE)))
    return df


def pretty_half_life(sec: float) -> str:
    for unit, n in (("Gy", 3.156e16), ("My", 3.156e13), ("y", 3.156e7),
                    ("d", 86400.0), ("h", 3600.0), ("min", 60.0), ("s", 1.0)):
        if sec >= n:
            return f"{sec / n:.4g} {unit}"
    return f"{sec * 1e6:.4g} us"


# ---------------------------------------------------------------------------
# 2. THE FOUR RECIPES
# ---------------------------------------------------------------------------
def add_bar(sb: SceneBuilder, recipe: str, x: float, y: float, h: float,
            rgb: tuple[int, int, int], label: str,
            key_of_id: dict[int, str]) -> None:
    """One bar of height `h`, standing on z = 0, in the named recipe."""
    w = BAR_HALF_WIDTH
    common = dict(type=TYPE_GLYPH, parent_id=0, branch_level=0,
                  translate_x=x, translate_y=y,
                  color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                  text=sanitize(label))

    if recipe == "A":
        # The naive version: the value goes straight into scale_z. It is wrong
        # twice over -- the bar is centred on its position, so half of it is
        # underground, and a cube only reaches 0.577 of its scale, so the part
        # above ground is 0.577H rather than the H that was asked for.
        key_of_id[sb.add(geometry=GEO_CUBE, translate_z=0.0,
                         scale_x=w / CUBE_HALF, scale_y=w / CUBE_HALF,
                         scale_z=h, **common)] = "A"

    elif recipe == "B":
        # Divide the geometry out and lift by half the height: exactly 0..H at
        # Global Scale 1, and only there -- GS multiplies the size but not a
        # root's z, so the base leaves the ground the moment the viewer zooms.
        key_of_id[sb.add(geometry=GEO_CUBE, translate_z=h / 2.0,
                         scale_x=w / CUBE_HALF, scale_y=w / CUBE_HALF,
                         scale_z=h / (2.0 * CUBE_HALF), **common)] = "B"

    elif recipe == "C":
        # A Pin already stands on its origin (0..1.1), so the base is right by
        # construction and only the height rides Global Scale. Its XY is a
        # tenth of its scale, so the width has to be divided out too.
        key_of_id[sb.add(geometry=GEO_PIN, translate_z=0.0,
                         scale_x=w / PIN_HALF_XY, scale_y=w / PIN_HALF_XY,
                         scale_z=h / PIN_SPAN, **common)] = "C"

    elif recipe == "D":
        # Both ends are coordinates. Nothing the viewer does can move them.
        base = sb.add(geometry=GEO_SPHERE, translate_z=0.0, hide=1,
                      scale_x=0.2, scale_y=0.2, scale_z=0.2,
                      **{**common, "text": sanitize(label + " base")})
        tip = sb.add(geometry=GEO_SPHERE, translate_z=h, hide=1,
                     scale_x=0.2, scale_y=0.2, scale_z=0.2,
                     **{**common, "text": sanitize(label + " tip")})
        key_of_id[sb.add(type=TYPE_LINK, parent_id=base, child_id=tip,
                         branch_level=1, geometry=GEO_CYLINDER, ratio=w,
                         color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                         text=sanitize(label))] = "D"
    else:
        raise ValueError(recipe)


def build_scene(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[int, str]]:
    sb = SceneBuilder()
    key_of_id: dict[int, str] = {}
    sb.add(type=TYPE_WORLD, parent_id=0, branch_level=0, geometry=0,
           color_r=BG[0], color_g=BG[1], color_b=BG[2], color_a=BG[3],
           text="World row: background colour only")

    n = len(df)
    span_x = (n - 1) * BAR_PITCH
    rows_y = [(1.5 - i) * ROW_PITCH for i in range(len(RECIPES))]

    # A World Grid as the baseline, so "below zero" is something you can see
    # rather than something you have to be told. Its extents window sizes the
    # plate; grids are exempt from the minimum-glyph-size clamp.
    half_x = span_x / 2.0 + 4.0
    half_y = (len(RECIPES) - 1) * ROW_PITCH / 2.0 + 6.0
    sb.add(type=TYPE_GRID, parent_id=0, branch_level=0, geometry=GEO_GRID_WIRE,
           color_r=PLATE[0], color_g=PLATE[1], color_b=PLATE[2], color_a=PLATE[3],
           trigger_lo_x=-half_x, trigger_hi_x=half_x,
           trigger_lo_y=-half_y, trigger_hi_y=half_y,
           segments_x=n + 2, segments_y=len(RECIPES) * 2,
           text="Baseline plate: z = 0")

    sb.add(type=TYPE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CIRCLE,
           translate_x=0.0, translate_y=half_y - 2.0, translate_z=7.0,
           scale_x=2.0, scale_y=2.0, scale_z=2.0, ratio=0.02,
           color_r=TITLE_RGB[0], color_g=TITLE_RGB[1], color_b=TITLE_RGB[2],
           color_a=205, show_text=1,
           text=sanitize("Four rooted bars - U-238 chain half-lives "
                         "(decades above Po-214)"))

    for (key, caption, rgb), y in zip(RECIPES, rows_y):
        sb.add(type=TYPE_GLYPH, parent_id=0, branch_level=0, geometry=GEO_CIRCLE,
               translate_x=-half_x + 2.0, translate_y=y, translate_z=1.5,
               scale_x=1.2, scale_y=1.2, scale_z=1.2, ratio=0.02,
               color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=205,
               show_text=1, text=sanitize(caption))

        for i, r in df.reset_index(drop=True).iterrows():
            x = i * BAR_PITCH - span_x / 2.0
            label = (f"{key}  {r.nuclide}  t-half {pretty_half_life(r.half_life_sec)}"
                     f"  ({r.decades:.1f} decades, H={r.height:.2f})")
            add_bar(sb, key, x, y, float(r.height), rgb, label, key_of_id)

    return sb.to_dataframe(), key_of_id


# ---------------------------------------------------------------------------
# 3. VERIFY -- measure the four recipes through the real engine
# ---------------------------------------------------------------------------
def measure(path: Path, base_scale: float,
            key_of_id: dict[int, str]) -> dict[str, tuple[float, float]]:
    """Bottom and top of every bar, per recipe, as the app will render it."""
    nodes = load_node_csv(str(path))
    scene = Scene(nodes, base_scale)
    by_id = {n.id: n for n in nodes}
    spans: dict[str, list[tuple[float, float]]] = {k: [] for k, _, _ in RECIPES}

    for n in nodes:
        key = key_of_id.get(n.id)
        if key is None:
            continue
        if n.type == TYPE_LINK:
            a = by_id[n.parent_id]
            b = by_id.get(int(n.extras.get("child_id", 0) or 0))
            if b is None:
                continue
            # A link spans its two endpoints' positions, which for a root are
            # its literal translate values -- that is the whole point of D.
            za = a.translate_z * 1.0
            zb = b.translate_z * 1.0
            spans[key].append((min(za, zb), max(za, zb)))
        else:
            m = node_world_matrix(n, scene)
            lhalf, lcentre = local_box(n.geometry, n.ratio)
            mid = m[2, 3] + float(m[2, :3] @ lcentre)
            half = abs(m[2, 2]) * lhalf[2]
            spans[key].append((mid - half, mid + half))

    return {k: (min(z[0] for z in v), max(z[1] for z in v))
            for k, v in spans.items() if v}


def verify(path: Path, df: pd.DataFrame,
           key_of_id: dict[int, str]) -> list[str]:
    """The documented table, re-derived. Any disagreement blocks the write."""
    h_max = float(df.height.max())
    errs: list[str] = []
    tol = 1e-3          # the CSV is written at 4 decimal places

    c = CUBE_HALF
    for b, expect in ((1.0, {"A": (-c * h_max, c * h_max),
                             "B": (0.0, h_max),
                             "C": (0.0, h_max),
                             "D": (0.0, h_max)}),
                      (3.0, {"A": (-3 * c * h_max, 3 * c * h_max),
                             "B": (-h_max, 2 * h_max),
                             "C": (0.0, 3 * h_max),
                             "D": (0.0, h_max)})):
        got = measure(path, b, key_of_id)
        for key, (lo, hi) in expect.items():
            if key not in got:
                errs.append(f"GS {b:g}: recipe {key} measured nothing")
                continue
            glo, ghi = got[key]
            if abs(glo - lo) > tol or abs(ghi - hi) > tol:
                errs.append(f"GS {b:g}: recipe {key} spans {glo:.4f}..{ghi:.4f}, "
                            f"documented {lo:.4f}..{hi:.4f}")
        print(f"  Global Scale {b:g}: " + "  ".join(
            f"{k} {got[k][0]:+.2f}..{got[k][1]:+.2f}" for k, _, _ in RECIPES
            if k in got))
    return errs


def main() -> int:
    df = load_chain()
    print(f"{len(df)} nuclides, "
          f"{df.decades.min():.1f}..{df.decades.max():.1f} decades "
          f"-> heights {df.height.min():.2f}..{df.height.max():.2f}")

    scene, key_of_id = build_scene(df)
    out = HERE / "rooted_bars_gv_node.csv"
    scene.to_csv(out, index=False, encoding="utf-8", lineterminator="\r\n",
                 float_format="%.4f")

    print(f"{out.name}: {len(scene)} rows")
    errs = verify(out, df, key_of_id)
    if errs:
        print("\n".join("  !! " + e for e in errs))
        out.unlink()
        return 1
    print("  recipes agree with the documented table at Global Scale 1 and 3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
