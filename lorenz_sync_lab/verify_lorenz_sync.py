"""
Check the Lorenz_Sync scene through GlyphViz's own objects, then bake chosen
frames into stand-alone node CSVs for tools/export_frame.py (which renders a
static file and knows nothing of Channels).

    python verify_lorenz_sync.py [--bake-dir DIR] [--frames 0 590 ...]

Checks:
  * the three-way Channels join (node ch_input_id -> map -> tracks column)
  * every torus-trail vertex sits on its torus tube at the trail lift, using
    the engine's world transforms and the torus glyph's own world matrix
  * per-frame cost of ChannelEngine.apply_frame on this scene
"""
import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

from glyphviz_core.csv_reader import load_node_csv, save_node_csv  # noqa: E402
from glyphviz_core.channel_loader import (find_channel_files, load_ch_map,  # noqa: E402
                                          load_ch_tracks)
from glyphviz_core.channel_engine import ChannelEngine, channel_id_of  # noqa: E402
from glyphviz_core.topology import compute_world_transforms  # noqa: E402
from glyphviz_core.node import Node  # noqa: E402

import generate_lorenz_sync as gen  # noqa: E402

SCENE = HERE / "Lorenz_Sync" / "Lorenz_Sync_gv_node.csv"


def check_join(nodes, ch_map, id_to_col):
    bound = {channel_id_of(n) for n in nodes} - {0}
    missing_ch = bound - set(ch_map)
    missing_tracks = {tid for rows in ch_map.values() for tid, _ in rows} - set(id_to_col)
    unused = set(ch_map) - bound
    print(f"join: {len(bound)} channels referenced by nodes, {len(ch_map)} in map, "
          f"{len(id_to_col)} track columns")
    assert not missing_ch, f"nodes point at unmapped channels: {sorted(missing_ch)[:10]}"
    assert not missing_tracks, f"map rows with no track column: {sorted(missing_tracks)[:10]}"
    assert not unused, f"mapped channels no node uses: {sorted(unused)[:10]}"


def check_torus_trails(nodes):
    """Distance from each trail vertex to its torus tube's centre circle."""
    st = compute_world_transforms(nodes, 1.0)
    by_id = {n.id: n for n in nodes}
    kids = {}
    for n in nodes:
        kids.setdefault(n.parent_id, []).append(n)
    worst = 0.0
    count = 0
    major = gen.TORUS_SIZE * (1 - gen.TORUS_RATIO)
    tube = gen.TORUS_SIZE * gen.TORUS_RATIO + gen.TRAIL_LIFT
    for frame in (n for n in nodes if n.text.endswith("(0 deg at screen right)")):
        r = st.row_of_id[frame.id]
        centre = st.world_pos[r]
        axes = st.world_basis[r]                # columns = torus local axes in world
        assert np.allclose(axes.T @ axes, np.eye(3), atol=1e-9), "torus frame is not orthonormal"
        for plot in kids.get(frame.id, []):
            if "coloured by" not in plot.text:
                continue
            for v in (v for seg in kids[plot.id] for v in kids[seg.id]):
                p = st.world_pos[st.row_of_id[v.id]] - centre
                local = axes.T @ p
                rho = np.hypot(local[0], local[1])
                d = np.hypot(rho - major, local[2])
                worst = max(worst, abs(d - tube))
                count += 1
    print(f"torus trails: {count} vertices, worst |distance from tube - expected| = {worst:.2e}")
    assert count and worst < 1e-3


def check_torus_topology_equivalence():
    """The generator's HCS torus point must be exactly where GlyphViz's own
    Torus topology seats a child at translate (theta1, theta2, lift / S) under a
    torus of scale S and the same ratio (the engine reads translate_z in the
    parent's units) -- i.e. the CSV angles ARE HCS angles."""
    def mk(**kw):
        base = dict(id=0, type=5, parent_id=0, branch_level=0,
                    translate_x=0.0, translate_y=0.0, translate_z=0.0,
                    rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                    scale_x=1.0, scale_y=1.0, scale_z=1.0,
                    color_r=255, color_g=255, color_b=255, color_a=255,
                    geometry=3, hide=0, topo=0)
        base.update(kw)
        return Node(**base)

    rng = np.random.default_rng(7)
    th = rng.uniform(-179, 179, size=(50, 2))
    s = gen.TORUS_SIZE
    parent = mk(id=1, topo=3, scale_x=s, scale_y=s, scale_z=s)
    parent.ratio = gen.TORUS_RATIO
    kids = [mk(id=i + 2, parent_id=1, branch_level=1, translate_x=float(a),
               translate_y=float(b), translate_z=gen.TRAIL_LIFT / s)
            for i, (a, b) in enumerate(th)]
    st = compute_world_transforms([parent] + kids, 1.0)
    engine = np.array([st.world_pos[st.row_of_id[c.id]] for c in kids])
    ours = gen.torus_point(th[:, 0], th[:, 1])
    err = np.abs(engine - ours).max()
    print(f"HCS point vs engine Torus topology: max difference {err:.2e} over 50 random angle pairs")
    assert err < 1e-9


def ts_leaf(angles_deg, base_radius, ratio):
    """Literal port of hyperdims/src/hcs/geometry.ts (baseFrame / childFrame /
    circlePoint), one row at a time -- deliberately NOT the generator's
    vectorized hcs_chain, so the two can check each other. Base frame u=X,
    v=Y, w=Z (hyperdims' own is the same up to a rigid rotation)."""
    c, u, v, w = (np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                  np.array([0, 0, 1.0]))
    radius = base_radius

    def circle_point(theta):
        t = np.radians(theta)
        return c + np.cos(t) * radius * u + np.sin(t) * radius * v

    for theta in angles_deg[:-1]:
        t = np.radians(theta)
        n = np.cos(t) * u + np.sin(t) * v
        c = circle_point(theta)
        u, v, w = n, w, np.cross(n, w)
        radius *= ratio
    return circle_point(angles_deg[-1])


def check_hyperglyph(nodes, eng, frames):
    """The 6-D node chain, driven by its channels, must put the leaf exactly
    where hyperdims' geometry puts it for the spinners' angles."""
    rng = np.random.default_rng(3)
    for row in rng.uniform(-179, 179, size=(20, 6)):
        a = gen.hcs_chain(row[None, :])[0]
        b = ts_leaf(row, gen.HYPER_R1, gen.HYPER_RATIO)
        assert np.abs(a - b).max() < 1e-12, (a, b)
    kids = {}
    for n in nodes:
        kids.setdefault(n.parent_id, []).append(n)
    glyphs = []
    for frame in (n for n in nodes if n.text.startswith("6-D hyperglyph frame (0 deg")):
        spins, leaf, stack = [], None, [frame]
        while stack:
            n = stack.pop()
            for k in kids.get(n.id, []):
                if "spinner" in k.text:
                    spins.append(k)
                if k.text.startswith("6-D leaf:"):
                    leaf = k
                stack.append(k)
        spins.sort(key=lambda s: s.branch_level)
        assert len(spins) == 6 and leaf is not None
        glyphs.append((frame, spins, leaf))
    worst = 0.0
    for f in frames:
        eng.apply_frame(f)
        st = compute_world_transforms(nodes, 1.0)
        for frame, spins, leaf in glyphs:
            r = st.row_of_id[frame.id]
            local = st.world_basis[r].T @ (st.world_pos[st.row_of_id[leaf.id]] - st.world_pos[r])
            want = ts_leaf([s.rotate_z for s in spins], gen.HYPER_R1, gen.HYPER_RATIO)
            worst = max(worst, np.abs(local - want).max())
    eng.reset()
    print(f"6-D hyperglyph: {len(glyphs)} glyphs x {len(frames)} frames, engine leaf vs "
          f"hyperdims geometry.ts: worst {worst:.2e}")
    assert worst < 1e-9


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bake-dir", default=None)
    ap.add_argument("--frames", type=int, nargs="*", default=[])
    args = ap.parse_args()

    t0 = time.perf_counter()
    nodes = load_node_csv(str(SCENE))
    map_path, tracks_path = find_channel_files(str(SCENE))
    ch_map = load_ch_map(map_path)
    tracks, id_to_col = load_ch_tracks(tracks_path)
    print(f"loaded {len(nodes)} nodes, tracks {tracks.shape} in {time.perf_counter() - t0:.1f} s")

    check_join(nodes, ch_map, id_to_col)
    check_torus_trails(nodes)
    check_torus_topology_equivalence()

    eng = ChannelEngine()
    eng.load(ch_map, tracks, id_to_col, nodes)
    check_hyperglyph(nodes, eng, [0, 700, 1500, 2399])
    t0 = time.perf_counter()
    for f in range(0, 2400, 24):
        eng.apply_frame(f)
    per = (time.perf_counter() - t0) / 100 * 1000
    print(f"apply_frame: {len(eng._bindings)} bindings, {per:.1f} ms/frame")

    if args.bake_dir:
        os.makedirs(args.bake_dir, exist_ok=True)
        for f in args.frames:
            eng.apply_frame(f)
            out = os.path.join(args.bake_dir, f"frame{f:04d}_gv_node.csv")
            save_node_csv(nodes, out)
            print(f"baked frame {f} (t = {f * gen.FRAME_DT:.2f}) -> {out}")


if __name__ == "__main__":
    main()
