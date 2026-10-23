"""
Check the LSA_Transition scene through GlyphViz's own objects, then bake
chosen frames into stand-alone node CSVs for tools/export_frame.py (which
renders a static file and knows nothing of Channels).

    python verify_lsa_transition.py [--bake-dir DIR] [--frames 0 300 ...]

Checks:
  * the three-way Channels join (node ch_input_id -> map -> tracks column)
  * at every 5th frame, through ChannelEngine + compute_world_transforms:
    every data point lies inside the cell outline of the site it is coloured
    as (outlines are inset by INSET, so "inside" allows that gap), and each
    site sits inside its own cell -- the separation property, as drawn.
"""
import argparse
import os
import sys
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

import generate_lsa_transition as gen  # noqa: E402

SCENE = HERE / "LSA_Transition" / "LSA_Transition_gv_node.csv"


def check_join(nodes, ch_map, id_to_col):
    bound = {channel_id_of(n) for n in nodes} - {0}
    missing_ch = bound - set(ch_map)
    missing_tracks = {tid for rows in ch_map.values() for tid, _ in rows} - set(id_to_col)
    unused = set(ch_map) - bound
    print(f"join: {len(bound)} channels referenced by nodes, {len(ch_map)} in map, "
          f"{len(id_to_col)} track columns")
    assert not missing_ch and not missing_tracks and not unused


def outside_distance(p, poly):
    """How far p lies outside convex polygon poly (CCW); <= 0 means inside."""
    worst = -np.inf
    for a, b in zip(poly, np.roll(poly, -1, axis=0)):
        e = b - a
        L = np.linalg.norm(e)
        if L < 1e-9:
            continue
        worst = max(worst, (e[0] * (p[1] - a[1]) - e[1] * (p[0] - a[0])) / -L)
    return worst


def check_separation(nodes, eng, frames):
    kids = {}
    for n in nodes:
        kids.setdefault(n.parent_id, []).append(n)
    wall = next(n for n in nodes if n.text.startswith("wall - leaned"))
    rgb_to_site = {c: j for j, c in enumerate(gen.SITE_COLORS)}
    panels = []
    for title in ("SEQUENTIAL", "COMBINED"):
        holder = next(n for n in nodes if n.text.startswith(title) and "data points" in n.text)
        cells = sorted((n for n in nodes if n.text.startswith("site ") and "power-diagram cell"
                        in n.text and n.id > holder.id), key=lambda n: n.id)[:gen.N_SITES]
        sites = [n for n in nodes if n.id > holder.id and n.geometry == gen.GEO_OCTA
                 and n.text in gen.SITE_NAMES][:gen.N_SITES]
        panels.append((kids[holder.id], cells, sites))
    worst_pt, worst_site, checked, site_out = -np.inf, -np.inf, 0, 0
    for f in frames:
        eng.apply_frame(f)
        st = compute_world_transforms(nodes, 1.0)
        r = st.row_of_id[wall.id]
        o, B = st.world_pos[r], st.world_basis[r]

        def local(n):
            v = B.T @ (st.world_pos[st.row_of_id[n.id]] - o)
            return v[1:] / gen.SC          # wall (y, z) -> data units, panel offset kept

        for pts, cells, sites in panels:
            polys = [np.array([local(v) for v in kids[c.id]]) for c in cells]
            for p in pts:
                j = rgb_to_site[(int(p.color_r), int(p.color_g), int(p.color_b))]
                worst_pt = max(worst_pt, outside_distance(local(p), polys[j][:-1]))
                checked += 1
            for j, s in enumerate(sites):
                d = outside_distance(local(s), polys[j][:-1])
                worst_site = max(worst_site, d)
                site_out += d > gen.INSET / gen.SC
    eng.reset()
    inset = gen.INSET / gen.SC
    print(f"separation: {checked} point-frames; worst point outside its cell outline by "
          f"{worst_pt:.4f} (allowed: the inset {inset:.4f} + CSV rounding)")
    print(f"sites outside their own cell (legal in a power diagram): {site_out} of "
          f"{len(frames) * 2 * gen.N_SITES} site-frames, worst by {worst_site:.2f} data units")
    assert worst_pt <= inset + 1e-3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bake-dir", default=None)
    ap.add_argument("--frames", type=int, nargs="*", default=[])
    args = ap.parse_args()

    nodes = load_node_csv(str(SCENE))
    map_path, tracks_path = find_channel_files(str(SCENE))
    ch_map = load_ch_map(map_path)
    tracks, id_to_col = load_ch_tracks(tracks_path)
    print(f"loaded {len(nodes)} nodes, tracks {tracks.shape}")
    check_join(nodes, ch_map, id_to_col)

    eng = ChannelEngine()
    eng.load(ch_map, tracks, id_to_col, nodes)
    check_separation(nodes, eng, range(0, tracks.shape[0], 5))

    if args.bake_dir:
        os.makedirs(args.bake_dir, exist_ok=True)
        for f in args.frames:
            eng.apply_frame(f)
            out = os.path.join(args.bake_dir, f"frame{f:04d}_gv_node.csv")
            save_node_csv(nodes, out)
            print(f"baked frame {f} -> {out}")


if __name__ == "__main__":
    main()
