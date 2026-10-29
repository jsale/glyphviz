"""
Check the bosonic string lab through GlyphViz's own objects: load each node
CSV (and its Channels files) with the app's loaders, play frames with the
app's ChannelEngine, resolve transforms with compute_world_transforms, and
hold what the scene DRAWS to the mathematics it claims.

    python verify_bosonic_lab.py [--full]

The mathematics (leech.py, string_math.py):
  * the Golay code's weights are 1, 759, 2576, 759, 1; the 196,560 minimal
    vectors are distinct, of length^2 32, pass Conway's membership test, and
    no two are closer than 60 deg (--full: all 196,560^2 pairs; otherwise a
    3,000-row sample against all)
  * around every octad: 280 at 60 deg, 448 at 75.5 deg, 30 at 90 deg
  * states per level 1, 24, 324, 3200, ...; j = E4^3/Delta starts
    1/q + 744 + 196,884 q; Leech theta / Delta = j - 720
Scene 1, Leech Kissing:
  * the Channels join holds; frame 0 equals the static file
  * every cloud glyph sits at its octad's 24-D HCS leaf (both ports agree)
  * at every hold, the chain's leaf lands exactly on the walked octad's glyph
  * the colours are the angles: 1 gold, 280 orange, 448 blue, 30 violet,
    each glyph's colour matching its own angle to the walked octad
  * exactly 280 threads show, each joining the walked octad to an octad
    sharing 4 places; the lit board cells are the walked octad's places
Scene 2, String Tower:
  * every level's bar starts on the HCS circle at angle theta(N - 1), points
    radially out, and is BAR_UNIT x log10(states) long
"""
import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from glyphviz_core.channel_engine import ChannelEngine, channel_id_of  # noqa: E402
from glyphviz_core.channel_loader import (find_channel_files, load_ch_map,  # noqa: E402
                                          load_ch_tracks)
from glyphviz_core.csv_reader import load_node_csv  # noqa: E402
from glyphviz_core.topology import compute_world_transforms  # noqa: E402

import generate_leech_kissing as g1  # noqa: E402
import generate_string_tower as g2  # noqa: E402
import leech  # noqa: E402
import string_kit as kit  # noqa: E402
import string_math as sm  # noqa: E402

ATTRS = ("translate_x", "translate_y", "translate_z", "rotate_x", "rotate_y", "rotate_z",
         "scale_x", "scale_y", "scale_z", "color_r", "color_g", "color_b", "color_a", "hide")


def load_scene(path):
    nodes = load_node_csv(str(path))
    map_path, tracks_path = find_channel_files(str(path))
    ch_map = load_ch_map(map_path)
    tracks, id_to_col = load_ch_tracks(tracks_path)
    bound = {channel_id_of(n) for n in nodes} - {0}
    assert bound == set(ch_map), (len(bound), len(ch_map))
    assert not {tid for rows in ch_map.values() for tid, _ in rows} - set(id_to_col)
    eng = ChannelEngine()
    eng.load(ch_map, tracks, id_to_col, nodes)
    before = [[getattr(n, a) for a in ATTRS] for n in nodes]
    eng.apply_frame(0)
    after = [[getattr(n, a) for a in ATTRS] for n in nodes]
    worst = max(abs(float(a) - float(b)) for ra, rb in zip(before, after)
                for a, b in zip(ra, rb))
    assert worst < 2e-3, f"frame 0 differs from the static file by {worst}"
    return nodes, eng


def world(nodes):
    w = compute_world_transforms(nodes, 1.0)
    return lambda nid: w.world_pos[w.row_of_id[nid]], w


def check_leech_kissing():
    path = HERE / g1.STEM / f"{g1.STEM}_gv_node.csv"
    nodes, eng = load_scene(path)
    by_id = {n.id: n for n in nodes}
    o = leech.octads()
    caps = o @ o.T
    ang = kit.hcs_angle(2 * o, g1.S)
    leaves = kit.hcs_chain(ang, g1.R1, g1.RATIO)
    for k in range(0, len(o), 97):
        ts = kit.hcs_ts_leaf(ang[k], g1.R1, g1.RATIO)
        assert np.allclose(ts, leaves[k], atol=1e-12)

    cloud = [n for n in nodes if n.text.startswith("octad ") and "Leech-lattice vector" in n.text]
    assert len(cloud) == 759
    cloud_k = {n.id: int(n.text.split(":")[0].split()[1]) - 1 for n in cloud}
    leaf = next(n for n in nodes if n.text.startswith("the leaf:"))
    hcs = next(n for n in nodes if n.text.startswith("HCS origin"))
    threads = [n for n in nodes if n.type == kit.TYPE_LINK]
    lit = {n.id: int(n.text.split()[1]) - 1 for n in nodes if n.text.startswith("place ")}
    assert len(threads) == 280 * g1.STEPS and len(lit) == 24

    tour = g1.pick_tour(o)
    want_color = {c: g1.CAT_COLOR[c] for c in g1.CAT_COLOR}
    worst_leaf = worst_cloud = 0.0
    for j, a in enumerate(tour):
        f = j * (g1.HOLD + g1.MOVE) + g1.MOVE + 10            # inside step j's hold
        eng.apply_frame(f)
        pos, w = world(nodes)
        # The cloud sits at its leaves: the HCS frame's world basis maps
        # local leaf coordinates to world.
        B = w.world_basis[w.row_of_id[hcs.id]]
        p0 = pos(hcs.id)
        for n in cloud[::37]:
            k = cloud_k[n.id]
            worst_cloud = max(worst_cloud, float(np.linalg.norm(pos(n.id) - (p0 + B @ leaves[k]))))
        target = next(n for n in cloud if cloud_k[n.id] == a)
        worst_leaf = max(worst_leaf, float(np.linalg.norm(pos(leaf.id) - pos(target.id))))
        # Colours are the angles.
        counts = {}
        for n in cloud:
            c = int(caps[a, cloud_k[n.id]])
            assert (n.color_r, n.color_g, n.color_b) == want_color[c], (f, n.text, c)
            counts[c] = counts.get(c, 0) + 1
        assert counts == {8: 1, 4: 280, 2: 448, 0: 30}, counts
        # Threads.
        shown = [t for t in threads if not t.hide]
        assert len(shown) == 280, len(shown)
        for t in shown:
            ka, kb = cloud_k[t.parent_id], cloud_k[int(t.extras["child_id"])]
            assert ka == a and caps[ka, kb] == 4
        # Board.
        on = {d for nid, d in lit.items() if not by_id[nid].hide}
        assert on == set(np.flatnonzero(o[a])), (on, a)
    # The CSV keeps 4 decimals of position and 3 of angle: 1e-3 world units
    # is far below a glyph's 0.3.
    assert worst_leaf < 1e-3, worst_leaf
    assert worst_cloud < 1e-3, worst_cloud
    return f"leaf on target within {worst_leaf:.1e}, cloud on its leaves within {worst_cloud:.1e}"


def check_string_tower():
    nodes = load_node_csv(str(HERE / g2.STEM / f"{g2.STEM}_gv_node.csv"))
    pos, w = world(nodes)
    counts = sm.states(g2.LEVELS)
    board = next(n for n in nodes if n.text.startswith("HCS circle board:"))
    B = w.world_basis[w.row_of_id[board.id]]
    c0 = pos(board.id)
    tips = [n for n in nodes if n.geometry == kit.GEO_SPHERE and n.text.startswith("level ")
            and not n.text.startswith("level 0")]
    assert len(tips) == g2.LEVELS - 1
    worst = 0.0
    for n in tips:
        # Board-local position of the tip, then compare with theory.
        local = np.linalg.solve(B, pos(n.id) - c0)
        N = int(n.text.split(":")[0].split()[1])
        th = math.radians(float(kit.hcs_angle(N - 1, 1.0)))
        r = g2.RC + g2.BAR_UNIT * math.log10(counts[N])
        want = np.array([r * math.cos(th), r * math.sin(th), 0.0])
        worst = max(worst, float(np.linalg.norm(local - want)))
    assert worst < 1e-3, worst
    return f"{len(tips)} bar tips on theory within {worst:.1e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="all 196,560^2 inner products")
    args = ap.parse_args()
    t = time.perf_counter()
    leech.check(full=args.full)
    print(f"Leech lattice: OK ({time.perf_counter() - t:.1f} s)")
    print("states per level:", sm.check()[:6], "...; moonshine identities OK")
    print("Leech_Kissing:", check_leech_kissing())
    print("String_Tower:", check_string_tower())
    print("all checks pass")


if __name__ == "__main__":
    main()
