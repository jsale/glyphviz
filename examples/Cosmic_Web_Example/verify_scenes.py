#!/usr/bin/env python3
"""
verify_scenes.py — read the shipped CSVs back through the real GlyphViz.

`verify_astro.py` checks the sky.  This checks the scenes: it loads them with
GlyphViz's own `load_node_csv`, runs its own `compute_world_transforms`, and
then tries to recover the input catalogue out of the resulting world-space
geometry.  A scene that survives this is one whose picture can be measured,
not just looked at.

    python verify_scenes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))

import build_cosmic_scenes as B                                    # noqa: E402
import skymap as S                                                 # noqa: E402
from glyphviz_core.csv_reader import load_node_csv                 # noqa: E402
from glyphviz_core.scene import compute_world_transforms           # noqa: E402

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


def floor_check(nodes, label: str) -> None:
    """The renderer clamps each node's own scale at 0.2 per axis, so anything
    authored below that is drawn bigger than it encodes and the encoding
    quietly lies.  Hidden placement frames are exempt: they are never drawn.
    """
    worst = min(
        (min(n.scale_x, n.scale_y, n.scale_z), n.id)
        for n in nodes
        if n.type == 5 and not n.hide)
    check(worst[0] >= SCALE_FLOOR - 1e-9,
          f"{label}: every visible node clears the 0.2 render floor",
          f"tightest {worst[0]:.4f} at node {worst[1]}")


def main() -> int:
    cat = S.load()
    df = cat.df
    xyz = cat.xyz

    print("== Local_Universe ==")
    nodes, pos = load(HERE / "Local_Universe" / "LocalUniverse_gv_node.csv")
    check(len(nodes) == len(df) + 2 + 1 + len(S.LANDMARKS),
          "node count is the catalogue plus World, anchor and markers",
          f"{len(nodes):,} nodes for {len(df):,} galaxies")
    floor_check(nodes, "Local_Universe")

    idx = {n.id: i for i, n in enumerate(nodes)}
    anchor = next(n for n in nodes if n.hide and n.type == 5)
    gal = [n for n in nodes if n.parent_id == anchor.id and not n.hide
           and n.geometry == B.GEO_SPHERE]
    check(len(gal) == len(df), "every galaxy made it into the scene",
          f"{len(gal):,}")

    got = np.array([pos[idx[n.id]] for n in gal]) / B.MPC
    err = np.abs(got - xyz).max()
    check(err < 2e-3,
          "world positions recover the catalogue's supergalactic coordinates",
          f"worst axis error {err * 1000:.3f} kpc over {len(gal):,} galaxies")

    # Distance is the quantity everything else rides on; check it end to end.
    d_scene = np.linalg.norm(got, axis=1)
    d_cat = df.dist.to_numpy()
    check(float(np.abs(d_scene - d_cat).max()) < 3e-3,
          "...so distance from the observer round-trips",
          f"worst {float(np.abs(d_scene - d_cat).max()) * 1000:.2f} kpc, "
          f"range {d_cat.min():.1f}-{d_cat.max():.0f} Mpc")

    marks = {n.text.split(" (")[0]: pos[idx[n.id]]
             for n in nodes if n.geometry == B.GEO_ICOSA_WIRE}
    worst_mark = max(
        float(np.linalg.norm(marks[lm.name] - S.landmark_xyz(lm) * B.MPC))
        for lm in S.LANDMARKS)
    check(worst_mark < 2e-3, "all nine landmark markers are where they belong",
          f"worst {worst_mark * 1000:.3f} kpc")

    # The estimator behind the colour ramp must actually separate voids from
    # cluster cores, or the picture is decorative.
    dens = S.knn_density(xyz, k=6)
    near_coma = np.linalg.norm(
        xyz - S.landmark_xyz(S.LANDMARKS[6]), axis=1) < 4.0
    check(float(np.median(dens[near_coma])) - float(np.median(dens)) > 1.0,
          "the density estimate separates a cluster core from the field",
          f"median log10 n: Coma core {float(np.median(dens[near_coma])):.2f} "
          f"vs catalogue {float(np.median(dens)):.2f}")

    print("\n== Cluster_Anatomy ==")
    nodes, pos = load(HERE / "Cluster_Anatomy" / "ClusterAnatomy_gv_node.csv")
    floor_check(nodes, "Cluster_Anatomy")
    idx = {n.id: i for i, n in enumerate(nodes)}
    by_id = {n.id: n for n in nodes}

    vl = cat.volume_limited(B.VL_DEPTH).reset_index(drop=True)
    gid, groups, _ = B.find_groups(vl)
    vxyz = vl[["sgx", "sgy", "sgz"]].to_numpy()

    scene_anchor = next(n for n in nodes
                        if n.type == 5 and n.parent_id == 0 and n.hide)
    field_anchor = next(n for n in nodes
                        if n.text.startswith("field galaxies"))
    hub_ids = {n.id for n in nodes
               if n.hide and n.type == 5
               and n.parent_id == scene_anchor.id
               and n.id != field_anchor.id}
    check(len(hub_ids) == len(groups),
          "one hidden hub per group of 5 or more",
          f"{len(hub_ids)} hubs, {len(groups)} groups")

    # Every group member is authored as an offset from its group's centre, so
    # this is the check that the nesting composes back to an absolute sky
    # position rather than merely looking plausible.
    members = [n for n in nodes
               if n.parent_id in hub_ids and n.geometry == B.GEO_SPHERE]
    check(len(members) == sum(len(g.members) for g in groups),
          "every grouped galaxy is drawn inside its hub",
          f"{len(members):,}")

    # Compared group by group rather than as one pooled cloud: the pooled
    # version has to sort two 4,078-point sets into the same order, and
    # positions written to 3 decimal places tie often enough that the sort
    # disagrees with itself.  Matching within a hub needs no global order and
    # is the stronger claim anyway — it says *this* hub carries *these*
    # galaxies.
    hubs = sorted((n for n in nodes if n.id in hub_ids), key=lambda n: n.id)
    kids_of: dict[int, list] = {h.id: [] for h in hubs}
    for n in members:
        kids_of[n.parent_id].append(n)

    worst, worst_gr = 0.0, None
    for hub, gr in zip(hubs, groups):
        kids = kids_of[hub.id]
        if len(kids) != len(gr.members):
            worst, worst_gr = float("inf"), gr
            break
        have = np.sort(np.array([pos[idx[k.id]] for k in kids]) / B.MPC, axis=0)
        want = np.sort(vxyz[gr.members], axis=0)
        e = float(np.abs(have - want).max())
        if e > worst:
            worst, worst_gr = e, gr
    check(worst < 2e-3,
          "hub offset + hub position reconstructs each member's true place",
          f"worst axis error {worst * 1000:.3f} kpc, over {len(groups)} groups "
          f"(worst: {worst_gr.name or 'unnamed'}, "
          f"{len(worst_gr.members)} galaxies)")

    centres = np.array([pos[idx[h.id]] for h in hubs]) / B.MPC
    check(float(np.abs(centres - np.array([g.centre for g in groups])).max())
          < 2e-3,
          "...and each hub really sits at its group's centre of mass")

    shells = [n for n in nodes if n.geometry == B.GEO_SPHERE_WIRE]
    check(len(shells) == sum(1 for g in groups
                             if len(g.members) >= B.SHELL_MIN),
          "a wire shell on every group big enough to earn one",
          f"{len(shells)}")
    # A shell that does not contain its own galaxies would be decoration.
    covered = []
    for n in shells:
        hub = by_id[n.parent_id]
        d = np.linalg.norm(
            np.array([pos[idx[k.id]] for k in kids_of[hub.id]])
            - pos[idx[hub.id]], axis=1)
        covered.append(float((d <= n.scale_x * 2.0).mean()))
    check(min(covered) > 0.5,
          "...and each shell's radius really is its group's own spread",
          f"worst shell holds {100 * min(covered):.0f}% of its members "
          f"inside 2x its radius, median {100 * float(np.median(covered)):.0f}%")

    field = [n for n in nodes if n.parent_id == field_anchor.id]
    ungrouped = int(len(vl) - sum(len(g.members) for g in groups))
    check(len(field) == ungrouped,
          "the field holds exactly the galaxies percolation left alone",
          f"{len(field):,} of {len(vl):,}")
    check(len(field) + len(members) == len(vl),
          "...and field plus groups is the whole volume-limited subsample")

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: " + "; ".join(FAILS))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
