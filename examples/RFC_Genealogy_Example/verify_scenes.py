#!/usr/bin/env python3
"""
verify_scenes.py — read the shipped CSVs back through the real GlyphViz.

`verify_rfc.py` checks the index.  This checks the scenes: it loads them with
GlyphViz's own `load_node_csv`, runs its own `compute_world_transforms`, and
then decodes the RFC series back out of the resulting world-space geometry —
publication dates out of the helix, publication years out of the lineage
field, ancestry out of the link endpoints.  If the encoding is right, the
picture can be read as a measurement.

    python verify_scenes.py
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))

import build_rfc_scenes as B                                       # noqa: E402
import rfcs                                                       # noqa: E402
from glyphviz_core.csv_reader import load_node_csv                # noqa: E402
from glyphviz_core.scene import compute_world_transforms          # noqa: E402

SCALE_FLOOR = 0.2
FAILS: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(label)


def load(path: Path):
    res = load_node_csv(str(path))
    nodes = res[0] if isinstance(res, tuple) else res
    t = compute_world_transforms(nodes, 1.0)
    return nodes, np.asarray(t.world_pos)


def link_end(node) -> int:
    """A Link's B-end.  `child_id` is not a tracked Node field — it is one
    of the 94 columns kept verbatim in `extras` and interpreted only in this
    context — so it has to be read from there."""
    return int(node.extras["child_id"])


def rfc_number(text: str) -> int | None:
    if not text.startswith("RFC "):
        return None
    head = text[4:].split(":")[0].split()[0].strip()
    return int(head) if head.isdigit() else None


def floor_check(nodes, label: str) -> None:
    worst = min((min(n.scale_x, n.scale_y, n.scale_z), n.id)
                for n in nodes if n.type == 5 and not n.hide)
    check(worst[0] >= SCALE_FLOOR - 1e-9,
          f"{label}: every visible glyph clears the 0.2 render floor",
          f"tightest {worst[0]:.4f} at node {worst[1]}")


def main() -> int:
    recs = rfcs.load()

    # ---------------------------------------------------------------- helix
    print("== RFC_Spiral ==")
    nodes, pos = load(HERE / "RFC_Spiral" / "RFCSpiral_gv_node.csv")
    idx = {n.id: i for i, n in enumerate(nodes)}
    by_id = {n.id: n for n in nodes}
    floor_check(nodes, "RFC_Spiral")

    spiral = next(n for n in nodes if n.topo == B.TOPO_SPIRAL)
    z0 = float(pos[idx[spiral.id]][2])

    glyphs = {}
    for n in nodes:
        if n.type != 5 or n.geometry != B.GEO_SPHERE:
            continue
        num = rfc_number(n.text)
        if num is not None:
            glyphs[num] = n
    check(len(glyphs) == len(recs), "every RFC is on the helix",
          f"{len(glyphs):,} glyphs for {len(recs):,} RFCs")

    p = np.array([pos[idx[glyphs[n].id]] for n in sorted(glyphs)])
    radius = np.hypot(p[:, 0], p[:, 1])
    check(float(np.abs(radius - B.HELIX_R).max()) < 1e-3,
          "the helix is a true cylinder: every RFC at one radius",
          f"{B.HELIX_R:.0f} +/- {float(np.abs(radius - B.HELIX_R).max()) * 1e3:.3f}e-3")

    # The round trip.  Height carries the turn count and turn count is years,
    # so the publication date can be read straight off the geometry.
    t_from_z = (p[:, 2] - z0) / B.TURN_RISE
    when_scene = B.EPOCH + t_from_z
    when_data = np.array([recs[n].when for n in sorted(glyphs)])
    err_year = np.abs(when_scene - when_data)
    check(float(err_year.max()) < 1.0 / 12.0 + 1e-6,
          "height decodes to each RFC's publication date, within its month",
          f"worst {float(err_year.max()) * 12:.4f} months over "
          f"{len(glyphs):,} documents")

    # Azimuth is the month of the year, and must agree with the height.
    az = np.degrees(np.arctan2(p[:, 1], p[:, 0])) % 360.0
    az_expect = (360.0 * t_from_z) % 360.0
    daz = np.abs((az - az_expect + 180.0) % 360.0 - 180.0)
    # Tolerance is set by the CSV, not the maths: translate_y is written to
    # four decimals, which is +/-4e-3 degrees of azimuth once height is
    # converted back into a turn count.
    check(float(daz.max()) < 2e-2,
          "...and azimuth agrees with it, so January always faces one way",
          f"worst {float(daz.max()) * 1e3:.3f}e-3 deg")

    ticks = [n for n in nodes if n.geometry == B.GEO_CROSS]
    years = sorted({r.year for r in recs.values()})
    check(len(ticks) == len(years), "one tick per calendar year",
          f"{len(ticks)} ticks, {years[0]}-{years[-1]}")
    tp = np.array([pos[idx[n.id]] for n in ticks])
    tick_az = np.degrees(np.arctan2(tp[:, 1], tp[:, 0])) % 360.0
    check(float(np.minimum(tick_az, 360.0 - tick_az).max()) < 1e-3,
          "...all on the January meridian",
          f"worst {float(np.minimum(tick_az, 360.0 - tick_az).max()) * 1e3:.3f}e-3 deg")
    check(float(np.abs(np.hypot(tp[:, 0], tp[:, 1])
                       - (B.HELIX_R + B.TICK_OUT)).max()) < 1e-3,
          "...and standing clear of the documents")

    links = [n for n in nodes if n.type == 7]
    obs = [n for n in links if not n.hide]
    upd = [n for n in links if n.hide]
    n_obs = sum(1 for r in recs.values() for o in r.obsoletes if o in recs)
    n_upd = sum(1 for r in recs.values() for u in r.updates if u in recs)
    check(len(obs) == n_obs and len(upd) == n_upd,
          "obsoletes links are drawn, updates links ship hidden",
          f"{len(obs):,} obsoletes visible, {len(upd):,} updates hidden "
          f"(Display > Show Hidden Nodes)")

    # Endpoints must be the real pair, in the real direction.
    edges = {(rfc_number(by_id[n.parent_id].text),
              rfc_number(by_id[link_end(n)].text)) for n in obs}
    want = {(n, o) for n, r in recs.items() for o in r.obsoletes if o in recs}
    check(edges == want,
          "every drawn link runs from the successor to what it replaced",
          f"{len(edges):,} edges, {len(edges ^ want)} wrong")

    drop = [float(pos[idx[n.parent_id]][2] - pos[idx[link_end(n)]][2])
            for n in obs]
    check(sum(1 for d in drop if d <= 0) <= 5,
          "...and almost every one of them points down the tower, into the past",
          f"{sum(1 for d in drop if d <= 0)} of {len(drop):,} do not; "
          f"median drop {np.median(drop):.1f} world units "
          f"= {np.median(drop) / B.TURN_RISE:.1f} years")

    # ------------------------------------------------------------- lineages
    print("\n== Standards_Lineage ==")
    nodes, pos = load(HERE / "Standards_Lineage"
                      / "StandardsLineage_gv_node.csv")
    idx = {n.id: i for i, n in enumerate(nodes)}
    by_id = {n.id: n for n in nodes}
    floor_check(nodes, "Standards_Lineage")

    forest = rfcs.lineage_forest(recs)
    stones = rfcs.standing_stones(recs)

    field = next(n for n in nodes if n.type == 5 and n.parent_id == 0)
    z_field = float(pos[idx[field.id]][2])

    bodies = [n for n in nodes
              if n.geometry == B.GEO_SPHERE and rfc_number(n.text) is not None]
    check(len(bodies) == sum(l.size for l in forest),
          "every lineage slot is drawn, duplicates included",
          f"{len(bodies):,} bodies for {sum(l.size for l in forest):,} slots")

    # Height is real time here too, so a body's world Z should decode back
    # to its own publication date.  The exception is deliberate: consecutive
    # generations are pushed apart far enough that their two spheres cannot
    # intersect, which matters in the handful of lineages that were re-issued
    # every few months.  Rather than tolerate a fuzzy pass rate, every
    # deviation is required to be explained by that rule.
    body_of: dict[int, object] = {}
    for n in bodies:
        body_of.setdefault(n.parent_id, n)

    # Positions are written to four decimals and compose through up to
    # thirty-two levels of nesting, so "exact" means exact to the CSV.
    EXACT = 1e-4
    # Checked as a *step*, not as an absolute date: displacement is inherited,
    # so one clamped generation shifts every document below it and an
    # absolute test would flag descendants that are themselves encoded
    # perfectly.  The step is the thing the builder decides, so the step is
    # the thing to hold it to.
    bad_step, clamped = [], 0
    for n in bodies:
        hub = by_id[n.parent_id]
        parent_hub = by_id.get(hub.parent_id)
        pbody = body_of.get(parent_hub.id) if parent_hub is not None else None
        if pbody is None:
            continue
        num, pnum = rfc_number(n.text), rfc_number(pbody.text)
        floor = B.STEP_CLEARANCE * (n.scale_x + pbody.scale_x)
        want = min((recs[num].when - recs[pnum].when) * B.YEAR_RISE, -floor)
        got = float(pos[idx[n.id]][2] - pos[idx[pbody.id]][2])
        if abs(got - want) > 1e-3:
            bad_step.append((pnum, num, want, got))
        if want < (recs[num].when - recs[pnum].when) * B.YEAR_RISE - EXACT:
            clamped += 1
    n_steps = len(bodies) - len(forest)
    check(not bad_step,
          "every generation step is exactly the time between the two "
          "documents, or the clearance floor",
          f"{n_steps:,} steps, {n_steps - clamped:,} carrying real elapsed "
          f"time, {clamped} at the floor")

    # ...and separately, what that costs in absolute terms, since a clamped
    # step shifts everything below it.
    err = [abs(((float(pos[idx[n.id]][2]) - z_field) / B.YEAR_RISE + B.EPOCH)
               - recs[rfc_number(n.text)].when) for n in bodies]
    displaced = [e for e in err if e >= EXACT]
    check(max(err) < 4.0,
          "...so almost every document still stands at its true date",
          f"{len(bodies) - len(displaced):,} of {len(bodies):,} exact; "
          f"worst displacement {max(err):.2f} y, 99th percentile "
          f"{np.percentile(err, 99):.2f} y, median of the "
          f"{len(displaced)} displaced {np.median(displaced):.2f} y")

    # The clearance rule is only worth its cost if it actually works.
    touching = 0
    for n in bodies:
        hub = by_id[n.parent_id]
        parent_hub = by_id.get(hub.parent_id)
        pbody = body_of.get(parent_hub.id) if parent_hub is not None else None
        if pbody is None:
            continue
        d = float(np.linalg.norm(pos[idx[n.id]] - pos[idx[pbody.id]]))
        if d < n.scale_x + pbody.scale_x - 1e-6:
            touching += 1
    check(touching == 0,
          "...and no two consecutive generations intersect",
          f"checked {len(bodies) - len(forest):,} parent-child pairs")

    icos = [n for n in nodes if n.geometry == B.GEO_ICOSA]
    check(len(icos) == len(stones),
          "one standing stone per never-revised Internet Standard",
          f"{len(icos)}")
    sp = np.array([pos[idx[n.id]] for n in icos])
    r_stone = np.hypot(sp[:, 0], sp[:, 1])
    check(float(np.abs(r_stone - B.STONE_RING_R).max()) < 1e-3,
          "...standing in a ring outside the lineage field",
          f"ring at {B.STONE_RING_R:.0f}, field reaches "
          f"{B.PHYLLO_SPREAD * math.sqrt(len(forest) - 1):.0f}")
    stone_err = max(
        abs((float(pos[idx[n.id]][2]) - z_field) / B.YEAR_RISE + B.EPOCH
            - recs[rfc_number(n.text)].when) for n in icos)
    check(stone_err < 1.0 / 12.0 + 1e-6,
          "...each at the year it was published and never touched again",
          f"worst {stone_err * 12:.4f} months")

    # Nesting depth is the finding, so it has to survive into the scene.
    # Chain from a body: hub(g) -> hub(g-1) -> ... -> hub(0) -> lineage
    # anchor -> field anchor, so the walk overshoots the generation count by
    # the one step onto the anchor.
    per_lineage: dict[int, int] = defaultdict(int)
    for n in bodies:
        cur = by_id[n.parent_id]
        d = -1
        while cur.parent_id != field.id:
            cur = by_id[cur.parent_id]
            d += 1
        per_lineage[cur.id] = max(per_lineage[cur.id], d)
    check(max(per_lineage.values()) == max(l.depth for l in forest),
          "the deepest glyph nests as deep as the data does",
          f"{max(per_lineage.values())} generations, matching RFC "
          f"{max(forest, key=lambda l: l.depth).root}")
    check(sorted(per_lineage.values(), reverse=True)
          == sorted((l.depth for l in forest), reverse=True),
          "...and every lineage's nesting depth matches its own history")

    spines = [n for n in nodes if n.type == 7]
    check(len(spines) == sum(l.size - 1 for l in forest),
          "one descent link per generation step",
          f"{len(spines):,}")

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: " + "; ".join(FAILS))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
