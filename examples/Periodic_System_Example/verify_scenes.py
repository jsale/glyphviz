#!/usr/bin/env python3
"""
verify_scenes.py — does the built helix actually say what it claims?

Runs the scenes back through the REAL GlyphViz loader, transform engine and
ChannelEngine (no OpenGL context needed) and checks the geometry against the
chemistry — most importantly the central claim, that every group is a true
vertical column.
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

import elements as E                                              # noqa: E402
import build_periodic_scenes as B                                 # noqa: E402
from glyphviz_core.csv_reader import load_node_csv                # noqa: E402
from glyphviz_core.topology import compute_world_transforms       # noqa: E402
from glyphviz_core.channel_loader import (                        # noqa: E402
    find_channel_files, load_ch_map, load_ch_tracks)
from glyphviz_core.channel_engine import ChannelEngine            # noqa: E402

fails: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"    {'PASS' if ok else 'FAIL'}  {label}"
          + (f"   {detail}" if detail else ""))
    if not ok:
        fails.append(label)


els = E.load_elements()
by_symbol = {e.symbol: e for e in els}
lay = E.madelung_layout()

# ===========================================================================
print("\n=== Madelung_Helix ===")
# ===========================================================================
path = HERE / "Madelung_Helix" / "PeriodicHelix_gv_node.csv"
res = load_node_csv(str(path))
nodes = res[0] if isinstance(res, tuple) else res
print(f"  loaded {len(nodes):,} nodes")

t = compute_world_transforms(nodes, 1.0)
pos = np.asarray(t.world_pos)
idx = {n.id: k for k, n in enumerate(nodes)}
by_id = {n.id: n for n in nodes}

spirals = [n for n in nodes if n.topo == B.TOPO_SPIRAL]
check(len(spirals) == 1, "one Spiral-topology parent carries the helix")
sid = spirals[0].id

# Element nodes = children of the spiral whose label is an element symbol.
el_nodes = {}
for n in nodes:
    if n.parent_id == sid and (getattr(n, "text", "") or "") in by_symbol:
        el_nodes[getattr(n, "text")] = n
check(len(el_nodes) == 118, "all 118 elements present", f"{len(el_nodes)}")

# --- the central claim --------------------------------------------------
columns = defaultdict(list)
for sym, n in el_nodes.items():
    columns[lay[by_symbol[sym].z].slot].append(sym)

worst_xy, worst_col = 0.0, None
for slot, syms in columns.items():
    xy = np.array([pos[idx[el_nodes[s].id]][:2] for s in syms])
    spread = float(np.abs(xy - xy[0]).max())
    if spread > worst_xy:
        worst_xy, worst_col = spread, slot
check(worst_xy < 1e-6,
      "every group is a TRUE vertical column (constant x,y across turns)",
      f"worst horizontal spread {worst_xy:.2e} world units (slot {worst_col})")

# ...and the members are stacked in atomic-number order, evenly spaced.
rises = []
for slot, syms in columns.items():
    syms = sorted(syms, key=lambda s: by_symbol[s].z)
    zs = [pos[idx[el_nodes[s].id]][2] for s in syms]
    check_ok = all(b > a for a, b in zip(zs, zs[1:]))
    if not check_ok:
        check(False, f"slot {slot} ascends with Z")
    rises += [round(b - a, 6) for a, b in zip(zs, zs[1:])]
check(len(set(rises)) == 1 and abs(rises[0] - B.TURN_RISE) < 1e-9,
      "column steps are exactly one turn's rise",
      f"{sorted(set(rises))} vs TURN_RISE {B.TURN_RISE}")

# Named groups must be the columns chemists know.
NAMED = {"alkali metals": ["H", "Li", "Na", "K", "Rb", "Cs", "Fr"],
         "noble gases": ["Ne", "Ar", "Kr", "Xe", "Rn", "Og"],
         "halogens": ["F", "Cl", "Br", "I", "At", "Ts"],
         "coinage metals": ["Cu", "Ag", "Au", "Rg"]}
for label, syms in NAMED.items():
    slots = {lay[by_symbol[s].z].slot for s in syms}
    xy = {tuple(np.round(pos[idx[el_nodes[s].id]][:2], 6)) for s in syms}
    check(len(slots) == 1 and len(xy) == 1,
          f"the {label} share one column", f"slots {slots}")

# Helium's position is the arrangement's most contested consequence.
he, be, ne = (pos[idx[el_nodes[s].id]] for s in ("He", "Be", "Ne"))
check(abs(he[0] - be[0]) < 1e-6 and abs(he[1] - be[1]) < 1e-6
      and not (abs(he[0] - ne[0]) < 1e-6 and abs(he[1] - ne[1]) < 1e-6),
      "helium stands over beryllium, not over neon (left-step consequence)")

# --- the hyperglyphs ----------------------------------------------------
children = defaultdict(list)
for n in nodes:
    children[n.parent_id].append(n)

bad_count, bad_radius, bad_hund = [], [], []
for sym, en in el_nodes.items():
    e = by_symbol[sym]
    kids = [c for c in children[en.id] if c.geometry == 11]   # electrons
    if len(kids) != e.z:
        bad_count.append((sym, len(kids), e.z))
        continue
    # Every electron must sit at shell_radius(n) * the atom's own scale.
    want = sorted(round(B.shell_radius(n) * en.scale_x, 4)
                  for (n, _l), q in e.config.items() for _ in range(q))
    got = sorted(round(float(np.linalg.norm(pos[idx[c.id]]
                                            - pos[idx[en.id]])), 4)
                 for c in kids)
    if max(abs(a - b) for a, b in zip(want, got)) > 2e-3:
        bad_radius.append(sym)

check(not bad_count, "every atom carries exactly Z electron glyphs",
      f"{bad_count[:4]}")
check(not bad_radius, "every electron sits on its own principal shell",
      f"{bad_radius[:4]}")

# Hund's rule, read off the geometry: a half-filled subshell must be
# entirely in the northern (spin-up) hemisphere.
for sym, want_north in (("N", 3), ("Cr", 6), ("Mn", 5), ("Gd", 8)):
    e = by_symbol[sym]
    en = el_nodes[sym]
    kids = [c for c in children[en.id] if c.geometry == 11]
    north = sum(1 for c in kids if c.translate_y > 0)
    south = sum(1 for c in kids if c.translate_y < 0)
    check(north - south == E.unpaired_electrons(e.config),
          f"{sym}: north-minus-south hemisphere = unpaired electrons",
          f"{north}-{south}={north-south}, expected {want_north}")

# Anomalies are marked, and only anomalies.
crosses = {}
for n in nodes:
    if n.geometry == 25 and n.parent_id in by_id:
        crosses[getattr(by_id[n.parent_id], "text", "")] = n
marked = set(crosses)
truth = {e.symbol for e in els if e.is_anomalous}
check(marked == truth, "exactly the anomalous elements carry a cross",
      f"{len(marked)} marked, {len(truth)} anomalous")

# Group-column links must connect vertical neighbours only.
links = [n for n in nodes if n.type == 7]
bad_links = []
for lk in links:
    a, b = pos[idx[lk.parent_id]], pos[idx[lk.extras.get("child_id")
                                           and int(lk.extras["child_id"])]]
    if abs(a[0] - b[0]) > 1e-6 or abs(a[1] - b[1]) > 1e-6:
        bad_links.append(lk.id)
check(not bad_links, "every group link is exactly vertical",
      f"{len(links)} links, {len(bad_links)} skewed")

# ===========================================================================
print("\n=== Aufbau_Sequence ===")
# ===========================================================================
path = HERE / "Aufbau_Sequence" / "AufbauSequence_gv_node.csv"
res = load_node_csv(str(path))
nodes = res[0] if isinstance(res, tuple) else res
print(f"  loaded {len(nodes):,} nodes")

mp, tp = find_channel_files(str(path))
ch_map = load_ch_map(mp)
tracks, id_to_col = load_ch_tracks(tp)
eng = ChannelEngine()
eng.load(ch_map, tracks, id_to_col, nodes)
check(eng.has_bindings and eng.frame_count == 118 + B.HOLD_FRAMES,
      "channels bound, one frame per element plus a hold",
      f"{eng.frame_count} frames")

used = {int(n.extras["ch_input_id"]) for n in nodes
        if n.extras.get("ch_input_id") not in (None, "", 0)
        and int(n.extras["ch_input_id"])}
check(used == set(range(1, 119)), "channels are exactly Z = 1..118",
      f"{len(used)} channels")

# An element must be invisible before its turn and lit on it.
sym_node = {getattr(n, "text", ""): n for n in nodes
            if n.parent_id and getattr(n, "text", "") in by_symbol}
for sym, z in (("H", 1), ("Fe", 26), ("Og", 118)):
    eng.apply_frame(max(z - 2, 0))
    before = sym_node[sym].color_a
    eng.apply_frame(z - 1)
    at = sym_node[sym].color_a
    ok = (at == 255) and (before == 0 or z == 1)
    check(ok, f"{sym} (Z={z}) is dark before its frame and lit on it",
          f"alpha {before} -> {at}")

eng.apply_frame(eng.frame_count - 1)
check(all(0 <= n.color_a <= 255 for n in nodes), "alpha stays in 0..255")
lit = sum(1 for s in sym_node.values() if s.color_a > 0)
check(lit == 118, "every element is visible by the final frame", f"{lit}")
eng.reset()

print("\n" + ("ALL CHECKS PASSED" if not fails
             else f"{len(fails)} CHECK(S) FAILED: {fails}"))
sys.exit(1 if fails else 0)
