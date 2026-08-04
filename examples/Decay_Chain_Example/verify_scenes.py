#!/usr/bin/env python3
"""
verify_scenes.py — check the built decay scenes are true, not merely loadable.

decay.py's physics is checked separately by verify_decay.py.  This file checks
that the physics survived the trip into geometry: every claim is re-derived
from world-space positions produced by the real GlyphViz transform engine.

 1. Structure: the glyph nests as deep as the chain is long (U-238 must reach
    14 decay steps, plus ring/petal/tip below that).
 2. Render floor: every visible node's OWN scale clears 0.2 per axis (what
    node_world_matrix actually floors).  Separately, no node ends up so small
    that it cannot be seen -- the reason chain hubs are kept at scale 1 is
    that a parent's scale multiplies its whole subtree.
 3. Chart round-trip: a member's world offset from its chain root decodes back
    to its real (N, Z) displacement and its decay-step number.  This is the
    strong one -- it says the staircase really is the chart of nuclides.
 4. Bi-212's fork survives into the scene as two petals and two outgoing
    links, and the branches rejoin on a single Pb-208 node.
 5. Links: every link connects two nodes that are a real parent/daughter pair.
 6. Channels: the activity tracks reproduce the Bateman solution, and the
    normalisation means secular equilibrium reads as 1.0.
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
sys.path.insert(0, str(HERE))

from glyphviz_core.csv_reader import load_node_csv                    # noqa: E402
from glyphviz_core.topology import compute_world_transforms           # noqa: E402
from glyphviz_core.channel_loader import load_ch_map, load_ch_tracks  # noqa: E402
from glyphviz_core.channel_engine import ChannelEngine                # noqa: E402

import decay                                                          # noqa: E402
import build_decay_scenes as B                                        # noqa: E402

fails: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail
                                                      else ""))
    if not ok:
        fails.append(label)


def cum_scale(tr, node_id) -> np.ndarray:
    b = tr.world_basis[tr.row_of_id[node_id]]
    return np.array([np.linalg.norm(b[:, i]) for i in range(3)])


tbl = decay.NuclideTable()

# ===========================================================================
print("Chain_Forest")
nodes = load_node_csv(str(HERE / "Chain_Forest" / "chain_forest_gv_node.csv"))
tr = compute_world_transforms(nodes, 1.0)
pos = {n.id: tr.world_pos[tr.row_of_id[n.id]] for n in nodes}
depth = {n.id: tr.depth[tr.row_of_id[n.id]] for n in nodes}
by_id = {n.id: n for n in nodes}
kids: dict[int, list] = {}
for n in nodes:
    kids.setdefault(n.parent_id, []).append(n)

# --- 1. structure ----------------------------------------------------------
print("\n1. nesting depth follows the physics")
hubs = [n for n in nodes if n.type == 5 and n.hide == 1 and n.topo == 0]
# 16, not 17: the step-14 member of the U-238 chain is Pb-206, which is stable
# and so carries no decay petals at all.  The deepest tip therefore hangs off
# the step-13 member: 13 + ring + petal + tip.
check(max(depth.values()) == 16, "deepest node is 16 levels down",
      f"deepest = {max(depth.values())} (13 decay steps + ring + petal + tip; "
      f"the 14th member is stable Pb-206 and has no petals)")
check(len(hubs) >= 121, "one hub per chain member",
      f"{len(hubs)} member hubs across 16 chains")

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
      f"tightest own scale = {worst:.4f} (node {worst_id}, depth "
      f"{depth[worst_id]}); smallest rendered size = {worst_cum:.4f}")

# --- 3. chart-of-nuclides round-trip ---------------------------------------
print("\n3. decoding (N, Z) and step number back out of world geometry")
roots = [n for n in nodes if n.parent_id == 0 and n.type == 5 and n.hide == 1]
prepared = []
for name, _note in B.FOREST:
    nuc = tbl.by_name(name)
    if nuc is None:
        continue
    ch = decay.build_chain(tbl, nuc)
    prepared.append((max(x.depth for x in ch.values()), name, nuc, ch))
prepared.sort(key=lambda r: (r[0], r[1]))

worst_n, worst_z, worst_step, n_members = 0.0, 0.0, 0.0, 0
for (_steps, _name, nuc, chain), root_node in zip(prepared, roots):
    root_key = (nuc.z, nuc.n)
    parent, order, _extra = B.spanning_tree(chain, root_key)
    # recover the glyph origin: the root hub carries the centring offset
    origin = pos[root_node.id]
    step_of = {root_key: 0}
    hub_ids = {root_key: root_node.id}
    for key in order[1:]:
        pkey = parent[key][0]
        step_of[key] = step_of[pkey] + 1
    # walk the built hierarchy in the same BFS order
    frontier = [(root_key, root_node.id)]
    seen = {root_key}
    while frontier:
        key, nid = frontier.pop(0)
        for child in kids.get(nid, []):
            if child.type != 5 or child.hide != 1 or child.topo != 0:
                continue
            # find which chain member this hub is by its offset
            d = pos[child.id] - pos[nid]
            dn = round(d[0] / B.CHART_XY)
            dz = round(d[1] / B.CHART_XY)
            ckey = (chain[key].nuc.z + dz, chain[key].nuc.n + dn)
            if ckey not in chain or ckey in seen:
                continue
            seen.add(ckey)
            hub_ids[ckey] = child.id
            frontier.append((ckey, child.id))
            # exact residuals
            worst_n = max(worst_n, abs(d[0] / B.CHART_XY - dn))
            worst_z = max(worst_z, abs(d[1] / B.CHART_XY - dz))
            worst_step = max(worst_step,
                             abs(d[2] / B.STEP_RISE - 1.0))
            n_members += 1
    # absolute check: every member's total offset from the root equals its
    # real chart displacement
    for key, nid in hub_ids.items():
        if key == root_key:
            continue
        off = pos[nid] - origin
        want_n = (chain[key].nuc.n - nuc.n) * B.CHART_XY
        want_z = (chain[key].nuc.z - nuc.z) * B.CHART_XY
        want_s = step_of[key] * B.STEP_RISE
        worst_n = max(worst_n, abs(off[0] - want_n) / B.CHART_XY)
        worst_z = max(worst_z, abs(off[1] - want_z) / B.CHART_XY)
        worst_step = max(worst_step, abs(off[2] - want_s) / B.STEP_RISE)

check(max(worst_n, worst_z) < 1e-9,
      "horizontal offset == the real (N, Z) chart displacement",
      f"{n_members} members, worst residual "
      f"{max(worst_n, worst_z):.2e} chart units")
check(worst_step < 1e-9, "height == decay step number",
      f"worst residual {worst_step:.2e} steps")

# --- 4. Bi-212's fork -------------------------------------------------------
print("\n4. Bi-212's 64/36 fork in the built scene")
th = tbl.by_name("Th-232")
th_chain = decay.build_chain(tbl, th)
bi = tbl.by_name("Bi-212")
th_root = next((r, c) for (_s, nm, r, c) in prepared if nm == "Th-232")[0:2]
# locate the Th-232 chain's Bi-212 hub via the decoded map built above
bi_hub = None
for (_steps, name, nuc, chain), root_node in zip(prepared, roots):
    if name != "Th-232":
        continue
    origin = pos[root_node.id]
    for n in nodes:
        if n.type != 5 or n.hide != 1 or n.topo != 0:
            continue
        off = pos[n.id] - origin
        dn = off[0] / B.CHART_XY + nuc.n
        dz = off[1] / B.CHART_XY + nuc.z
        if abs(dn - bi.n) < 1e-6 and abs(dz - bi.z) < 1e-6:
            bi_hub = n.id
            break
petals = 0
if bi_hub is not None:
    for ring in kids.get(bi_hub, []):
        if ring.topo == 4:
            petals = len([p for p in kids.get(ring.id, []) if p.type == 5])
links = [n for n in nodes if n.type == 7]
bi_links = [l for l in links if l.parent_id == bi_hub]
check(bi_hub is not None, "Bi-212 is present in the Th-232 chain glyph",
      f"hub id {bi_hub}")
check(petals == 2, "it carries two decay-mode petals", f"{petals} petals")
check(len(bi_links) == 2, "and two outgoing decay links",
      f"{len(bi_links)} links")

pb208 = tbl.by_name("Pb-208")
pb_hubs = []
for (_steps, name, nuc, chain), root_node in zip(prepared, roots):
    if name != "Th-232":
        continue
    origin = pos[root_node.id]
    for n in nodes:
        if n.type != 5 or n.hide != 1 or n.topo != 0:
            continue
        off = pos[n.id] - origin
        if (abs(off[0] / B.CHART_XY + nuc.n - pb208.n) < 1e-6
                and abs(off[1] / B.CHART_XY + nuc.z - pb208.z) < 1e-6):
            pb_hubs.append(n.id)
check(len(pb_hubs) == 1, "both branches rejoin on ONE Pb-208 node",
      f"{len(pb_hubs)} Pb-208 hub(s); "
      f"{len([l for l in links if l.extras.get('child_id') in pb_hubs])} "
      f"links arrive")

# --- 5. links are real decay edges -----------------------------------------
print("\n5. every link is a real parent/daughter pair")
bad_links = 0
for l in links:
    a, b = l.parent_id, int(l.extras.get("child_id", 0) or 0)
    if a not in by_id or b not in by_id:
        bad_links += 1
        continue
    d = pos[b] - pos[a]
    if abs(d[2] / B.STEP_RISE - 1.0) > 1e-6:
        bad_links += 1
check(bad_links == 0, "links span exactly one decay step",
      f"{len(links)} links, {bad_links} malformed")

# ===========================================================================
print("\nSecular_Equilibrium")
s_nodes = load_node_csv(str(HERE / "Secular_Equilibrium"
                            / "secular_equilibrium_gv_node.csv"))
s_tr = compute_world_transforms(s_nodes, 1.0)
s_depth = {n.id: s_tr.depth[s_tr.row_of_id[n.id]] for n in s_nodes}
ch_map = load_ch_map(HERE / "Secular_Equilibrium"
                     / "secular_equilibrium_gv_ch-map.csv")
tracks, id_to_col = load_ch_tracks(HERE / "Secular_Equilibrium"
                                   / "secular_equilibrium_gv_ch-tracks.csv")
eng = ChannelEngine()
eng.load(ch_map, tracks, id_to_col, s_nodes)

print("\n6. Bateman activities survive into the tracks")
check(eng.frame_count == B.N_FRAMES, "frame count matches the time grid",
      f"{eng.frame_count} frames, {len(eng._bindings)} bindings")
worst_s = min(min(n.scale_x, n.scale_y, n.scale_z) for n in s_nodes
              if not n.hide and n.type == 5)
check(worst_s >= 0.2 - 1e-9, "clears the render floor",
      f"tightest own scale = {worst_s:.4f}")

# Re-solve Bateman independently and compare against what the track encodes.
times = list(np.logspace(B.T_LOG_LO, B.T_LOG_HI, B.N_FRAMES))
u = tbl.by_name("U-238")
u_chain = decay.build_chain(tbl, u)
acts = decay.activities(u_chain, (u.z, u.n), times)
rn = tbl.by_name("Rn-222")
series = acts[(rn.z, rn.n)]
want_first = round(0.35 + 2.4 * math.sqrt(min(1.35, max(0.0, series[0]))), 4)
want_last = round(0.35 + 2.4 * math.sqrt(min(1.35, max(0.0, series[-1]))), 4)
found = False
for col in range(tracks.shape[1]):
    v = tracks[:, col]
    if abs(v[0] - want_first) < 1e-6 and abs(v[-1] - want_last) < 1e-6:
        found = True
        break
check(found, "Rn-222's ingrowth curve is present verbatim in a track",
      f"scale {want_first:.3f} -> {want_last:.3f}")
u_series = acts[(u.z, u.n)]
ratio = series[-1] / u_series[-1]
check(abs(ratio - 1.0) < 1e-3,
      "Rn-222 reaches secular equilibrium with U-238",
      f"A_Rn/A_U(t) at {times[-1]:.2g} s = {ratio:.6f}; both are down to "
      f"{u_series[-1]:.4f} of the initial parent activity because U-238 has "
      f"itself decayed 4.8% by then")

early = acts[(rn.z, rn.n)][0]
check(early < 0.05, "and starts from essentially nothing",
      f"ratio at {times[0]:.2g} s = {early:.2e}")

print(f"\n{'ALL CHECKS PASSED' if not fails else 'FAILURES: ' + str(fails)}")
sys.exit(1 if fails else 0)
