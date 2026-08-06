#!/usr/bin/env python3
"""
build_rfc_scenes.py — the RFC series as a core sample and as a family tree.

Every internet standard is one numbered document, and the RFC Editor keeps
the whole series in a single index that records, for each one, what it
replaced and what replaced it.  That makes the corpus something rarer than a
list: a dated genealogy of every agreement the internet runs on, from 1969 to
this year.  Two scenes read it two ways.

  RFC_Spiral/         All 9,819 RFCs on a helix, one turn per calendar year,
                      each document placed at its publication month and
                      coloured by the status it holds today.  Obsoletes and
                      updates are drawn as links, so the churn is visible as
                      cabling running down the outside of the tower.  It is a
                      core sample: the sparse turns at the bottom are the
                      ARPANET, the thick ones in the middle are the 2000s.

  Standards_Lineage/  The obsoletes relation followed backwards from every
                      document still in force.  Each lineage is a hyperglyph
                      whose height is real time and whose depth is the number
                      of times that specification has been rewritten, with
                      the deepest at the centre.  Around the outside, at the
                      years they were published and connected to nothing,
                      stand the 44 full Internet Standards that were never
                      revised at all.

Usage:
    python build_rfc_scenes.py
    python build_rfc_scenes.py --only RFC_Spiral

Requires: pandas.  No network — reads the vendored index in data/.
Refresh the index with `python fetch_rfc_index.py`.
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rfcs                                                        # noqa: E402

# ---------------------------------------------------------------------------
# 1. CONSTANTS
# ---------------------------------------------------------------------------
EPOCH = 1968             # RFC 1 is dated April 1969; the index's floor is 1968

# --- helix -----------------------------------------------------------------
HELIX_R = 60.0           # world units, constant radius
TURN_RISE = 9.0          # world units gained per calendar year
TICK_OUT = 6.0           # year ticks sit this far outside the helix
LABEL_EVERY = 5          # ...and are labelled every N years

# --- lineage field ---------------------------------------------------------
YEAR_RISE = 7.0          # world units per year on the lineage scene
STEP_CLEARANCE = 1.10    # ...but consecutive bodies never intersect:
                         # a step is at least this times the two radii
PHYLLO_SPREAD = 4.4      # world units; nearest-neighbour spacing of lineages
GOLDEN_ANGLE = 137.50776405003785
FAN_RADIUS = 2.0         # sibling spread when one RFC retired several
STONE_RING_R = 178.0     # radius of the never-revised standards ring
LABEL_MIN_DEPTH = 5      # pin a lineage's label at this depth or deeper
LINEAGE_GAIN = 1.7       # bodies run bigger here: the field is tighter than
                         # the helix and nothing has to sit on a shared arc

# --- shared ----------------------------------------------------------------
SCALE_FLOOR = 0.2        # the renderer's per-axis floor; author above it
BODY_MIN, BODY_MAX = 0.22, 1.10

BG = (12, 13, 22, 255)
TAG_RGB = (232, 232, 214)
OBSOLETES_RGB = (198, 106, 44)     # warm: descent
SPINE_RGB = (216, 126, 58)         # ...a shade up where it is a lineage spine
UPDATES_RGB = (78, 104, 150)       # cool, quieter: amendment
TICK_RGB = (92, 96, 118)

GEO_CUBE, GEO_SPHERE, GEO_CONE = 1, 3, 5
GEO_OCTA, GEO_ICOSA = 11, 15
GEO_CIRCLE, GEO_CROSS, GEO_LINE = 24, 25, 27
TOPO_NONE, TOPO_SPIRAL = 0, 14
ROT_EULER = 0


def body_scale(pages: int, gain: float = 1.0) -> float:
    """Page count -> glyph size, floored clear of the renderer's 0.2 clamp.

    A 5-page RFC and a 500-page RFC differ by a factor of 100, so this is
    logarithmic; linear sizing would make everything short of the monsters
    invisible.  `gain` rescales the whole range per scene — the clamp is
    applied first, so the floor is respected before the gain widens it.
    """
    s = BODY_MIN + 0.30 * math.log10(max(pages, 1))
    return round(min(max(s, BODY_MIN), BODY_MAX) * gain, 4)


# ---------------------------------------------------------------------------
# 2. SCENE BUILDER
# ---------------------------------------------------------------------------
COLUMNS = ["id", "type", "parent_id", "branch_level", "child_id",
           "translate_x", "translate_y", "translate_z",
           "rotate_x", "rotate_y", "rotate_z",
           "scale_x", "scale_y", "scale_z",
           "color_r", "color_g", "color_b", "color_a",
           "geometry", "hide", "topo", "ratio", "show_text",
           "segments_x", "segments_y", "rotation_mode",
           "tag_color_mode", "tag_color_r", "tag_color_g", "tag_color_b",
           "text", "link"]

DEFAULTS = dict(child_id=0, translate_x=0.0, translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=255, color_g=255, color_b=255, color_a=255,
                geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE, ratio=0.1,
                show_text=0, segments_x=16, segments_y=16,
                rotation_mode=ROT_EULER, tag_color_mode=1,
                tag_color_r=TAG_RGB[0], tag_color_g=TAG_RGB[1],
                tag_color_b=TAG_RGB[2], text="", link="")


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

    def link(self, a: int, b: int, rgb, alpha: int, level: int) -> int:
        return self.add(type=7, parent_id=a, child_id=b, branch_level=level,
                        geometry=GEO_LINE, color_r=rgb[0], color_g=rgb[1],
                        color_b=rgb[2], color_a=alpha)

    def write(self, folder: Path, stem: str) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{stem}_gv_node.csv"
        pd.DataFrame(self.rows, columns=COLUMNS).to_csv(
            path, index=False, encoding="utf-8", lineterminator="\r\n")
        return path


def short(text: str, n: int = 34) -> str:
    """Pinned labels draw all the time and dozens of them share one view, so
    the ones that stay on are clipped to a readable width."""
    text = clean(text)
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def clean(text: str) -> str:
    """Strip anything that could corrupt a CSV cell or a label.

    One stray control character in a title silently drops labels downstream,
    so titles are scrubbed here rather than trusted.
    """
    out = "".join(c for c in text if c.isprintable() and c not in '\r\n')
    return " ".join(out.split()).replace('"', "'")


# ---------------------------------------------------------------------------
# 3. SCENE ONE — the helix
# ---------------------------------------------------------------------------
def helix_coords(t_years: float, radius: float) -> tuple[float, float, float]:
    """Spiral-topology coordinates for a point `t_years` after the epoch.

    Spiral places a child at ((B+tz)cos tx, (B+tz)sin tx, (tx/360)B + ty)
    with B = base_scale = 1, so tz carries the radius and ty corrects the
    pitch to TURN_RISE.  tx counts straight past 360, which is what a
    multi-turn helix wants: one turn is one calendar year, so January always
    faces the same way and a radial slice of the tower is a season.
    """
    tx = 360.0 * t_years
    tz = radius - 1.0
    ty = t_years * (TURN_RISE - 1.0)
    return round(tx, 4), round(ty, 4), round(tz, 4)


def build_spiral(recs: dict[int, rfcs.Rfc], out: Path) -> Path:
    sb = SceneBuilder()
    sb.world()

    years = sorted({r.year for r in recs.values()})
    y0, y1 = years[0], years[-1]
    span = (y1 + 1) - EPOCH
    z0 = -(span * TURN_RISE) / 2.0

    spiral = sb.add(type=5, parent_id=0, branch_level=0,
                    translate_z=round(z0, 4), geometry=0, hide=1,
                    topo=TOPO_SPIRAL, ratio=0.1,
                    text=f"RFC 1-{max(recs)} - {y0} to {y1}")

    # --- year ticks and labels ---------------------------------------------
    for y in range(y0, y1 + 1):
        tx, ty, tz = helix_coords(y - EPOCH, HELIX_R + TICK_OUT)
        labelled = (y % LABEL_EVERY == 0) or y == y0 or y == y1
        sb.add(type=5, parent_id=spiral, branch_level=1,
               translate_x=tx, translate_y=ty, translate_z=tz,
               scale_x=0.6, scale_y=0.6, scale_z=0.6,
               geometry=GEO_CROSS, ratio=0.5,
               color_r=TICK_RGB[0], color_g=TICK_RGB[1], color_b=TICK_RGB[2],
               color_a=200 if labelled else 110,
               show_text=1 if labelled else 0, text=str(y))

    # --- one glyph per RFC, spread within its publication month ------------
    bucket: dict[tuple[int, int], list[int]] = {}
    for num, r in recs.items():
        bucket.setdefault((r.year, r.month), []).append(num)

    node_of: dict[int, int] = {}
    for (year, month), nums in bucket.items():
        nums.sort()
        n = len(nums)
        # A month with no day field would stack every document on one radial
        # spoke; spread them evenly across the month's 30 degrees instead.
        m0 = (month - 1) if month > 0 else 5.5
        for i, num in enumerate(nums):
            r = recs[num]
            t = (year - EPOCH) + (m0 + (i + 0.5) / n) / 12.0
            tx, ty, tz = helix_coords(t, HELIX_R)
            s = body_scale(r.pages)
            rgb = r.rgb
            node_of[num] = sb.add(
                type=5, parent_id=spiral, branch_level=1,
                translate_x=tx, translate_y=ty, translate_z=tz,
                scale_x=s, scale_y=s, scale_z=s,
                geometry=GEO_SPHERE, topo=TOPO_NONE,
                color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=255,
                text=f"RFC {num}: {clean(r.title)}", link=r.url)

    # --- the cabling --------------------------------------------------------
    n_obs = n_upd = 0
    for num, r in recs.items():
        for o in r.obsoletes:
            if o in node_of:
                sb.link(node_of[num], node_of[o], OBSOLETES_RGB, 85, 2)
                n_obs += 1
    for num, r in recs.items():
        for u in r.updates:
            if u in node_of:
                lid = sb.link(node_of[num], node_of[u], UPDATES_RGB, 95, 2)
                sb.rows[lid - 1]['hide'] = 1
                n_upd += 1

    path = sb.write(out, "RFCSpiral")
    print(f"  RFC_Spiral      {len(sb.rows):,} nodes  "
          f"({len(node_of):,} RFCs, {n_obs:,} obsoletes, {n_upd:,} updates)")
    return path


# ---------------------------------------------------------------------------
# 4. SCENE TWO — the lineage field
# ---------------------------------------------------------------------------
def phyllotaxis(i: int) -> tuple[float, float]:
    """Sunflower packing: even area density, no rows to line up along.

    Index 0 lands at the centre, so sorting the forest deepest-first puts the
    tallest lineages in the middle and lets the field taper outward.
    """
    a = math.radians(GOLDEN_ANGLE * i)
    r = PHYLLO_SPREAD * math.sqrt(i)
    return r * math.cos(a), r * math.sin(a)


def build_lineage(recs: dict[int, rfcs.Rfc], out: Path) -> Path:
    forest = rfcs.lineage_forest(recs)
    stones = rfcs.standing_stones(recs)

    sb = SceneBuilder()
    sb.world()

    def z_of(r: rfcs.Rfc) -> float:
        return (r.when - EPOCH) * YEAR_RISE

    z_mid = (max(z_of(r) for r in recs.values())
             + min(z_of(r) for r in recs.values())) / 2.0

    field_anchor = sb.add(type=5, parent_id=0, branch_level=0,
                          translate_z=round(-z_mid, 4), geometry=0, hide=1,
                          topo=TOPO_NONE,
                          text="RFC lineages - height is real time")

    n_bodies = n_spines = 0
    for li, lin in enumerate(forest):
        px, py = phyllotaxis(li)
        root = recs[lin.root]

        # One anchor per lineage, always scale 1 so that nesting thirty-two
        # deep never compounds a scale factor into its descendants.
        anchor = sb.add(type=5, parent_id=field_anchor, branch_level=1,
                        translate_x=round(px, 4), translate_y=round(py, 4),
                        translate_z=round(z_of(root), 4),
                        geometry=0, hide=1, topo=TOPO_NONE)

        oldest = min(recs[n].year for n, *_ in lin.nodes)
        # Keyed by position in lin.nodes, not by RFC number: a document can
        # legitimately appear twice inside one lineage (both of two siblings
        # obsoleted it), and each occurrence needs its own frame.
        hub_at: list[int] = []
        for num, depth, parent, sib, nsib in lin.nodes:
            r = recs[num]
            if parent < 0:
                dx = dy = dz = 0.0
                parent_node, level = anchor, 2
            else:
                pnum = lin.nodes[parent][0]
                # Descent always goes down, and far enough that the two
                # spheres cannot intersect.  Anything tighter than that is
                # the encoding lying about which document came first; a
                # blanket minimum instead would displace small glyphs much
                # further than they need, and the displacement compounds
                # down a chain thirty generations long.
                floor = STEP_CLEARANCE * (body_scale(r.pages, LINEAGE_GAIN)
                                          + body_scale(recs[pnum].pages,
                                                       LINEAGE_GAIN))
                dz = min(z_of(r) - z_of(recs[pnum]), -floor)
                if nsib > 1:
                    # A document that retired several at once: fan them.
                    a = math.radians(360.0 * sib / nsib)
                    dx = FAN_RADIUS * math.cos(a)
                    dy = FAN_RADIUS * math.sin(a)
                else:
                    dx = dy = 0.0
                parent_node, level = hub_at[parent], 2 + depth

            hub = sb.add(type=5, parent_id=parent_node, branch_level=level,
                         translate_x=round(dx, 4), translate_y=round(dy, 4),
                         translate_z=round(dz, 4),
                         geometry=0, hide=1, topo=TOPO_NONE)
            hub_at.append(hub)

            s = body_scale(r.pages, LINEAGE_GAIN)
            rgb = r.rgb
            pin = 1 if (parent < 0 and lin.depth >= LABEL_MIN_DEPTH) else 0
            label = (f"RFC {num} - {lin.depth} rewrites back to {oldest}"
                     if pin else f"RFC {num}: {clean(r.title)}")
            sb.add(type=5, parent_id=hub, branch_level=level + 1,
                   scale_x=s, scale_y=s, scale_z=s,
                   geometry=GEO_SPHERE, topo=TOPO_NONE,
                   color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                   color_a=255, show_text=pin,
                   text=label, link=r.url)
            n_bodies += 1

            if parent >= 0:
                sb.link(hub_at[parent], hub, SPINE_RGB, 150, level)
                n_spines += 1

    # --- the standing stones -----------------------------------------------
    for i, r in enumerate(stones):
        a = math.radians(360.0 * i / len(stones))
        s = body_scale(r.pages, LINEAGE_GAIN)
        rgb = r.rgb
        sb.add(type=5, parent_id=field_anchor, branch_level=1,
               translate_x=round(STONE_RING_R * math.cos(a), 4),
               translate_y=round(STONE_RING_R * math.sin(a), 4),
               translate_z=round(z_of(r), 4),
               scale_x=s, scale_y=s, scale_z=s,
               geometry=GEO_ICOSA, topo=TOPO_NONE,
               color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=255,
               show_text=1,
               text=f"RFC {r.num} ({r.year}) {short(r.title)}", link=r.url)

    path = sb.write(out, "StandardsLineage")
    print(f"  Standards_Lineage {len(sb.rows):,} nodes  "
          f"({len(forest):,} lineages, {n_bodies:,} documents, "
          f"{n_spines:,} descent links, {len(stones)} never revised)")
    return path


# ---------------------------------------------------------------------------
# 5. MAIN
# ---------------------------------------------------------------------------
SCENES = {"RFC_Spiral": build_spiral, "Standards_Lineage": build_lineage}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=sorted(SCENES))
    ap.add_argument("--out", type=Path, default=HERE,
                    help="parent folder for the scene folders")
    args = ap.parse_args()

    recs = rfcs.load()
    print(f"loaded {len(recs):,} RFCs")
    for name, fn in SCENES.items():
        if args.only and name != args.only:
            continue
        fn(recs, args.out / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
