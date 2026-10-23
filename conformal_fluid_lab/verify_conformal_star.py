"""
Check the Conformal_Star scene through GlyphViz's own objects, then bake chosen
frames into stand-alone node CSVs for tools/export_frame.py (which renders a
static file and knows nothing of Channels).

    python verify_conformal_star.py [--bake-dir DIR] [--frames 0 300 ...]

Checks:
  * the physics: case A's closed form against independent shooting (both roots,
    and no root above the fold); B and C each have exactly one root
  * the three-way Channels join (node ch_input_id -> map -> tracks column)
  * at every 10th frame, through ChannelEngine + compute_world_transforms:
      - each meridian's drawn length equals the slice's proper radial length
        int phi^2 dr -- the sheet is an isometric embedding, so this is the
        check that the rubber sheet's lengths are real
      - every meridian's r = 1 vertex lies on the star-surface ring (the
        scaled-unit-circle rings and the rotated meridians agree)
      - answer 1/2 sheets are fully transparent exactly when kappa > kappa_max
      - answer 2's throat ring sits at the analytic throat, coordinate r = s
"""
import argparse
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from glyphviz_core.csv_reader import load_node_csv, save_node_csv  # noqa: E402
from glyphviz_core.channel_loader import (find_channel_files, load_ch_map,  # noqa: E402
                                          load_ch_tracks)
from glyphviz_core.channel_engine import ChannelEngine, channel_id_of  # noqa: E402
from glyphviz_core.topology import compute_world_transforms  # noqa: E402

import generate_conformal_star as gen  # noqa: E402
import star_physics as sp  # noqa: E402

SCENE = HERE / "Conformal_Star" / "Conformal_Star_gv_node.csv"


def check_physics():
    worst = 0.0
    for k in (0.004, 0.01, 0.03, 0.06, 0.066):
        closed = sorted((1 + s) ** 1.5 for s in sp.fold_roots(k))
        # c <= 30: past that the series start is too coarse for phi^5 and the
        # scan reports spurious crossings (every regular solution of
        # Laplacian(phi) = -k phi^5 is the closed-form family, which has two).
        shot = sp.shoot_roots(k, 5, c_hi=30.0, n=300)
        assert len(shot) == 2, (k, shot)
        worst = max(worst, max(abs(a - b) for a, b in zip(closed, shot)))
    assert not sp.shoot_roots(0.08, 5, c_hi=30.0, n=300)
    for case in "BC":
        for k in (0.01, 0.07, 0.14):
            assert len(sp.shoot_roots(k, sp.POWER[case], c_hi=30.0, n=300)) == 1
    print(f"physics: A closed form vs shooting, worst phi(0) difference {worst:.2e}; "
          "no A solution at kappa = 0.08; B and C one root each")
    assert worst < 1e-6


def check_join(nodes, ch_map, id_to_col):
    bound = {channel_id_of(n) for n in nodes} - {0}
    missing_ch = bound - set(ch_map)
    missing_tracks = {tid for rows in ch_map.values() for tid, _ in rows} - set(id_to_col)
    unused = set(ch_map) - bound
    print(f"join: {len(bound)} channels referenced by nodes, {len(ch_map)} in map, "
          f"{len(id_to_col)} track columns")
    assert not missing_ch and not missing_tracks and not unused


def proper_length(phi, r):
    return float(np.trapezoid(phi(r) ** 2, r))


def check_geometry(nodes, eng, frames):
    kids = {}
    for n in nodes:
        kids.setdefault(n.parent_id, []).append(n)
    roots = [n for n in nodes if n.geometry == gen.GEO_POINT and n.hide
             and any(n.text.startswith(t[2] + ":") for t in gen.SHEETS)]
    assert len(roots) == len(gen.SHEETS)
    kappas = gen.kappa_track()
    fine = np.linspace(0, 1, 20001)
    worst_len = worst_ring = worst_throat = 0.0
    alpha_ok = 0
    for f in frames:
        eng.apply_frame(f)
        st = compute_world_transforms(nodes, 1.0)
        wp = lambda n: st.world_pos[st.row_of_id[n.id]]
        k = kappas[f]
        for si, root in enumerate(roots):
            case, branch = gen.SHEETS[si][:2]
            o = wp(root)
            ch = kids[root.id]
            meridians = [n for n in ch if "meridian" in n.text]
            rings = [n for n in ch if n.topo == gen.TOPO_PLOT and "meridian" not in n.text]
            surface = next(n for n in rings if "surface" in n.text)
            assert len(meridians) == gen.N_MERIDIANS
            alive = case != "A" or k <= sp.KAPPA_MAX
            alphas = {int(v.color_a) for m in meridians for v in kids[m.id]}
            assert alphas == ({255} if alive else {0}), (f, si, alphas)
            alpha_ok += 1
            if not alive:
                continue
            if case == "A":
                phi, dphi, M = sp.direct_solution(sp.fold_roots(k)[branch])
            else:
                phi, dphi, M = sp.shot_solution(k, sp.POWER[case])
            r = gen.R_MER
            want = proper_length(phi, np.concatenate([fine * 1.0, np.geomspace(1, 3, 20001)[1:]]))
            s_ring = surface.scale_x
            z_ring = wp(surface)[2]
            # The ring is a unit circle under a scaled Plot parent: its drawn
            # vertices must land at that scale (parent-scale inheritance).
            for v in kids[surface.id][::12]:
                q = wp(v) - o
                worst_ring = max(worst_ring, abs(np.hypot(q[0], q[1]) - s_ring))
            for m in meridians:
                P = np.array([wp(v) for v in kids[m.id]])
                drawn = np.linalg.norm(np.diff(P, axis=0), axis=1).sum()
                worst_len = max(worst_len, abs(drawn - want) / want)
                q = P[gen.N_IN - 1] - o                 # the r = 1 vertex
                worst_ring = max(worst_ring, abs(np.hypot(q[0], q[1]) - s_ring),
                                 abs(P[gen.N_IN - 1][2] - z_ring))
            if case == "A" and branch == 1:
                s = sp.fold_roots(k)[1]
                thr = [n for n in ch if "throat" in n.text and n.topo == gen.TOPO_PLOT]
                if s > 1 and thr:
                    # the throat at coordinate r = s: areal radius s (1 + s/s)^2 = 4 s
                    worst_throat = max(worst_throat, abs(thr[0].scale_x - 4 * s) / (4 * s))
    eng.reset()
    print(f"geometry: {len(frames)} frames x {len(roots)} sheets; drawn meridian length vs "
          f"proper length int phi^2 dr: worst {100 * worst_len:.2f}% (polyline chords)")
    print(f"  r = 1 meridian vertices vs surface ring: worst {worst_ring:.2e}; "
          f"throat ring vs analytic 4 s: worst {100 * worst_throat:.2f}%; "
          f"visibility correct in {alpha_ok} sheet-frames")
    assert worst_len < 0.01 and worst_ring < 2e-3 and worst_throat < 0.01


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bake-dir", default=None)
    ap.add_argument("--frames", type=int, nargs="*", default=[])
    ap.add_argument("--skip-physics", action="store_true")
    args = ap.parse_args()

    if not args.skip_physics:
        check_physics()
    nodes = load_node_csv(str(SCENE))
    map_path, tracks_path = find_channel_files(str(SCENE))
    ch_map = load_ch_map(map_path)
    tracks, id_to_col = load_ch_tracks(tracks_path)
    print(f"loaded {len(nodes)} nodes, tracks {tracks.shape}")
    check_join(nodes, ch_map, id_to_col)

    eng = ChannelEngine()
    eng.load(ch_map, tracks, id_to_col, nodes)
    check_geometry(nodes, eng, range(0, tracks.shape[0], 10))

    if args.bake_dir:
        os.makedirs(args.bake_dir, exist_ok=True)
        for f in args.frames:
            eng.apply_frame(f)
            out = os.path.join(args.bake_dir, f"frame{f:04d}_gv_node.csv")
            save_node_csv(nodes, out)
            print(f"baked frame {f} -> {out}")


if __name__ == "__main__":
    main()
