"""
Check both qudit scenes through GlyphViz's own objects (load_node_csv,
ChannelEngine, compute_world_transforms), against independent recomputation;
optionally bake chosen frames into stand-alone node CSVs for
tools/export_frame.py (which renders a static file and knows nothing of
Channels).

    python verify_qudit_scenes.py [--bake-dir DIR] [--frames 0 300 ...]
                                  [--scene Cyclotomic_Search|Reachable_Net]

Cyclotomic_Search:
  * the Channels join; each level's clouds are hidden until their frame
  * every drawn zoom-column point, read back from its WORLD position (floor
    -> entry value, height -> twin size via the HCS map), matches the
    level-2 lattice points in the window one for one; no point is drawn at
    a level higher than the first one that contains it
  * the full-disc panel holds exactly the legal entries (11, 111, 2251)
  * both candidate glyphs sit inside the slot: column error <= eps, under
    the ceiling; the completed column is exact in integer arithmetic
Reachable_Net:
  * layers 0-2 (qubit) and 0-1 (qutrit) re-derived by brute force over
    Clifford words, independent of the layer-by-layer search
  * every qubit point lies on the Bloch sphere, every qutrit point inside
    the tube, read back from world positions
  * at every stage the nearest-state marker sits on the true nearest state
"""
import argparse
import itertools
import os
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from glyphviz_core.csv_reader import load_node_csv, save_node_csv  # noqa: E402
from glyphviz_core.channel_loader import (find_channel_files, load_ch_map,  # noqa: E402
                                          load_ch_tracks)
from glyphviz_core.channel_engine import ChannelEngine, channel_id_of  # noqa: E402
from glyphviz_core.topology import compute_world_transforms  # noqa: E402

import generate_cyclotomic_search as cs  # noqa: E402
import generate_reachable_net as rn  # noqa: E402
import qudit_math as qm  # noqa: E402


def load(stem):
    path = HERE / stem / f"{stem}_gv_node.csv"
    nodes = load_node_csv(str(path))
    map_path, tracks_path = find_channel_files(str(path))
    ch_map = load_ch_map(map_path)
    tracks, id_to_col = load_ch_tracks(tracks_path)
    bound = {channel_id_of(n) for n in nodes} - {0}
    assert bound == set(ch_map), "channel ids in nodes and map differ"
    assert not {t for rows in ch_map.values() for t, _ in rows} - set(id_to_col)
    eng = ChannelEngine()
    eng.load(ch_map, tracks, id_to_col, nodes)
    # The app opens on the file's static values and applies no frame until
    # playback starts, so the file must already BE frame 0.
    bound = [(n, attr) for n in nodes if channel_id_of(n)
             for _, attr in ch_map[channel_id_of(n)]]
    static = [getattr(n, attr) for n, attr in bound]
    eng.apply_frame(0)
    off = [(n.id, attr, s, getattr(n, attr)) for (n, attr), s in zip(bound, static)
           if abs(getattr(n, attr) - s) > 1e-6]
    eng.reset()
    assert not off, f"static values differ from frame 0: {off[:5]}"
    print(f"{stem}: {len(nodes)} nodes, {len(ch_map)} channels, tracks {tracks.shape}; "
          f"Channels join OK; the file opens on frame 0 ({len(bound)} bound fields)")
    return path, nodes, eng


def local_frame(st, node):
    r = st.row_of_id[node.id]
    o, B = st.world_pos[r], st.world_basis[r]
    return lambda n: B.T @ (st.world_pos[st.row_of_id[n.id]] - o)


def children(nodes):
    kids = {}
    for n in nodes:
        kids.setdefault(n.parent_id, []).append(n)
    return kids


def match(a, b, tol):
    """Every row of a has a row of b within tol and vice versa (small sets)."""
    da, _ = cKDTree(b).query(a)
    db, _ = cKDTree(a).query(b)
    return float(max(da.max(initial=0), db.max(initial=0))) <= tol, float(da.max(initial=0))


# --------------------------------------------------------------------------
# Cyclotomic_Search
# --------------------------------------------------------------------------

def check_cyclotomic():
    path, nodes, eng = load("Cyclotomic_Search")
    kids = children(nodes)
    z = np.exp(1j * cs.THETA)
    col = next(n for n in nodes if n.text.startswith("zoom column: floor"))
    wall = next(n for n in nodes if n.text.startswith("backdrop wall"))

    eng.apply_frame(cs.FRAMES - 1)
    st = compute_world_transforms(nodes, 1.0)
    to_col = local_frame(st, col)

    # Zoom column: read every drawn point back to (entry value, twin size).
    clouds = [n for n in kids[col.id] if n.topo == 18]
    drawn, by_level = [], {}
    for c in clouds:
        k = int(c.text.split()[1])
        for p in kids.get(c.id, []):
            X, Y, h = to_col(p)
            w = z + complex(Y / cs.S, -X / cs.S) * z
            # Compared in world units (height, not r): inverting r/(1+r) near the top
            # magnifies the CSV's 4-decimal rounding sixfold.
            drawn.append((cs.S * w.real, cs.S * w.imag, h))
            by_level.setdefault(k, []).append((cs.S * w.real, cs.S * w.imag, h))
    A, y1, y2 = qm.enumerate_box(cs.LEVELS[-1], z, cs.W * np.sqrt(2), cs.R_CAP)
    d = cs.zoom_d(y1)
    inwin = (np.abs(d.real) <= cs.W) & (np.abs(d.imag) <= cs.W)
    want = np.c_[cs.S * y1[inwin].real, cs.S * y1[inwin].imag, cs.hcs(np.abs(y2[inwin]))]
    ok, worst = match(np.array(drawn), want, 3e-4)
    print(f"zoom column: {len(drawn)} points drawn, {len(want)} level-{cs.LEVELS[-1]} lattice "
          f"points in the window; worst read-back mismatch {worst:.1e}")
    assert ok and len(drawn) == len(want)
    for k in cs.LEVELS[1:]:
        A, y1, y2 = qm.enumerate_box(k - 1, z, cs.W * np.sqrt(2), cs.R_CAP)
        lower = np.c_[cs.S * y1.real, cs.S * y1.imag, cs.hcs(np.abs(y2))]
        dist, _ = cKDTree(lower).query(np.array(by_level[k]))
        assert dist.min() > 1e-4, f"a level-{k} point already exists at level {k - 1}"
    print(f"  per level: {[len(by_level[k]) for k in cs.LEVELS]}; none repeats a lower level")

    # Full disc: exactly the legal entries.
    to_wall = local_frame(st, wall)
    disc = [n for n in kids[wall.id] if n.topo == 18]
    pts = np.array([to_wall(p)[1:] for c in disc for p in kids[c.id]])
    w = ((pts[:, 0] - cs.A0[0]) + 1j * (pts[:, 1] - cs.A0[1])) / cs.RA
    A, y1, y2 = qm.enumerate_box(cs.LEVELS[-1], 0j, 1.0, 1.0)
    legal = y1[np.abs(y1) <= 1 + qm.TOL]
    ok, worst = match(np.c_[w.real, w.imag], np.c_[legal.real, legal.imag], 2e-4)
    counts = [len(qm.enumerate_box(k, 0j, 1.0, 1.0)[0]) for k in cs.LEVELS]
    print(f"full disc: {len(w)} drawn = {len(legal)} legal entries; per-level totals "
          f"{counts}; predicted pi^2 25^k / covolume = "
          f"{[round(np.pi ** 2 * 25 ** k / qm.COVOLUME) for k in cs.LEVELS]}")
    assert ok and len(w) == len(legal)

    # Candidates: inside the slot, under the ceiling; exact column.
    cands = [n for n in kids[col.id] if n.geometry == 3 and "andidate" in n.text.lower()]
    assert len(cands) == 2
    for n in cands:
        X, Y, h = to_col(n)
        w = z + complex(Y / cs.S, -X / cs.S) * z
        err = np.sqrt(2 - 2 * (w * np.conj(z)).real)
        assert abs(w) <= 1 + 1e-4 and err <= cs.EPS and h <= cs.hcs(1.0) + 1e-4, (w, err, h)
    best = qm.sliver_points(cs.LEVELS[-1], cs.THETA, cs.EPS)
    u = best[0][int(np.argmin(best[3]))]
    parts = qm.complete_column(u, cs.LEVELS[-1])
    total = qm.mul(u, qm.conj(u))
    for p in parts:
        e = qm.from_real(*p)
        total = total + qm.mul(e, e)
    assert [int(v) for v in total] == [25, 0, 0, 0], total
    print(f"candidates: both inside the slot and under the ceiling; |u|^2 + sum a^2 = 25 "
          f"exactly in Z[zeta5] for u = {list(map(int, u))}, fillers {parts}")

    # Level timing.
    for k, f0 in zip(cs.LEVELS, cs.F_LEVEL):
        lvl = [c for c in clouds if c.text.startswith(f"level {k} ")]
        eng.apply_frame(f0 - 1)
        assert all(c.hide for c in lvl)
        eng.apply_frame(f0)
        assert not any(c.hide for c in lvl)
    eng.reset()
    print(f"timing: each level's clouds appear exactly at frames {cs.F_LEVEL}")
    return path, nodes, eng


# --------------------------------------------------------------------------
# Reachable_Net
# --------------------------------------------------------------------------

def brute_layers(d, gate, kmax):
    """States C_k G ... C_1 G C_0 |0>, every Clifford word with up to kmax
    gates -> {k: set of keys first reached at k}."""
    C = qm.clifford_group(d)
    e0 = np.zeros(d, complex)
    e0[0] = 1
    seen, out = set(), {}
    cur = C @ e0
    for k in range(kmax + 1):
        if k:
            cur = np.einsum("cij,nj->cni", C, cur @ gate.T).reshape(-1, d)
        _, K = qm._canonical(cur)
        keys = {r.tobytes() for r in K}
        out[k] = keys - seen
        seen |= keys
    return out


def check_reachable():
    path, nodes, eng = load("Reachable_Net")
    for name, d, gate, kmax in (("qubit", 2, qm.t_gate(2), 2), ("qutrit", 3, qm.r_gate(), 1)):
        layers = qm.reachable_states(d, gate, kmax)
        brute = brute_layers(d, gate, kmax)
        for k in range(kmax + 1):
            _, K = qm._canonical(layers[k])
            assert {r.tobytes() for r in K} == brute[k], (name, k)
        print(f"{name}: layers 0-{kmax} match brute force over Clifford words "
              f"({[len(brute[k]) for k in range(kmax + 1)]})")
    # The brute force extends every word, duplicates and all; the search
    # extends only the previous layer's new states. Equal sets say that
    # pruning loses nothing.

    kids = children(nodes)
    turn = next(n for n in nodes if n.text.startswith("frame turned"))
    eng.apply_frame(rn.FRAMES - 1)
    st = compute_world_transforms(nodes, 1.0)
    to_turn = local_frame(st, turn)
    worst_b, worst_t, nq, nt = 0.0, 0.0, 0, 0
    for c in (n for n in kids[turn.id] if n.topo == 18):
        P = np.array([to_turn(p) for p in kids[c.id]])
        if c.text.startswith("qubit"):
            worst_b = max(worst_b, np.abs(np.linalg.norm(P - rn.QB, axis=1) - rn.RB).max())
            nq += len(P)
        else:
            q = P - rn.QT
            ring = np.hypot(q[:, 0], q[:, 1])
            tube = np.hypot(ring - rn.R0, q[:, 2])
            worst_t = max(worst_t, tube.max() - rn.RT)
            nt += len(P)
    print(f"qubit: {nq} points, worst distance off the Bloch sphere {worst_b:.1e}; "
          f"qutrit: {nt} points, worst outside the tube {worst_t:.1e}")
    assert worst_b < 2e-3 and worst_t < 2e-3
    assert nq == 6 * (2 ** (rn.K_QUBIT + 1) - 1)

    # Nearest-state markers, every stage.
    q_layers = qm.reachable_states(2, qm.t_gate(2), rn.K_QUBIT)
    t_layers = qm.reachable_states(3, qm.r_gate(), rn.K_QUTRIT)
    rng = np.random.default_rng(rn.SEED)
    q_target = rn.pick_target(2, q_layers, rng)
    t_target = rn.pick_target(3, t_layers, rng)
    markers = {lab: next(n for n in kids[turn.id]
                         if n.text == f"{lab}: the nearest reachable state so far")
               for lab in ("qubit", "qutrit")}
    worst = 0.0
    for k in range(rn.K_QUBIT + 1):
        eng.apply_frame(rn.f_stage(k) + 5)
        st = compute_world_transforms(nodes, 1.0)
        to_turn = local_frame(st, turn)
        for lab, layers, tgt, kd, pos in (("qubit", q_layers, q_target, rn.K_QUBIT,
                                           lambda v: rn.bloch_pos(qm.bloch(v))),
                                          ("qutrit", t_layers, t_target, rn.K_QUTRIT,
                                           rn.torus_pos)):
            allv = np.concatenate(layers[:min(k, kd) + 1])
            i = int(np.argmin(qm.state_distance(tgt[None, :], allv)[0]))
            worst = max(worst, np.linalg.norm(to_turn(markers[lab]) - pos(allv[i:i + 1])[0]))
    eng.reset()
    print(f"nearest-state markers: worst offset from the true nearest state over all "
          f"stages {worst:.1e}")
    assert worst < 2e-3
    return path, nodes, eng


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bake-dir", default=None)
    ap.add_argument("--frames", type=int, nargs="*", default=[])
    ap.add_argument("--scene", choices=("Cyclotomic_Search", "Reachable_Net"), default=None)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    runs = {"Cyclotomic_Search": check_cyclotomic, "Reachable_Net": check_reachable}
    for stem, fn in runs.items():
        if args.scene and stem != args.scene:
            continue
        path, nodes, eng = fn()
        if args.bake_dir:
            out = os.path.join(args.bake_dir, stem)
            os.makedirs(out, exist_ok=True)
            for f in args.frames:
                eng.apply_frame(f)
                p = os.path.join(out, f"frame{f:04d}_gv_node.csv")
                save_node_csv(nodes, p)
                print(f"baked frame {f} -> {p}")
            eng.reset()
    print("all checks passed")


if __name__ == "__main__":
    main()
