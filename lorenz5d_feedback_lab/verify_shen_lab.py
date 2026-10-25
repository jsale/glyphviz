"""
Check this lab's model against the paper, and its scenes through GlyphViz's
own objects; optionally bake frames into stand-alone node CSVs for
tools/export_frame.py (which renders a static file and knows nothing of
Channels).

    python verify_shen_lab.py [--scene cells|tower|both] [--bake-dir DIR --frames F ...]

Model checks (shen_model.py against Shen 2014):
  * critical points solve the equations; eq. (19c)'s two forms agree
  * linear r_c = 24.74 / 43.54 / 45.94 (3DLM / 3DLMP / 5DLM, Fig. 10b)
  * 3DLMP at r = 35, q = 0.17 settles at X / X3d = -1.098 (Fig. 9a)
  * appendix A's energy budget: d/dtau [X^2/2 - sigma (Z + Z1/2)]
    = sigma (-X^2 + bZ + 2 b Z1) along a 5DLM trajectory
  * warm fluid rises: w and theta correlate positively at the steady roll
Scene checks:
  * the Channels join; frame 0 of every track equals the static file
  * the board frame really is x = right, y = up, z = toward the viewer
  * cells: every heat-map lattice is complete (no holes), and every vertex's
    colour at sampled frames is temp_color of conduction + the mode sum there
  * cells: every bead stays on its streamline (|M1| constant along it)
  * tower: every slice's vertices are the model's normalized trajectory
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

import shen_model as sm  # noqa: E402

ATTRS = ("translate_x", "translate_y", "translate_z", "rotate_x", "rotate_y", "rotate_z",
         "scale_x", "scale_y", "scale_z", "color_r", "color_g", "color_b", "color_a", "hide")


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------

def check_model():
    for r in (25.0, 35.0, 43.5):
        c = sm.critical_point(r)
        res = np.abs(sm.rhs(c, r)).max()
        Zc, Z1c = c[2], c[4]
        alt = np.sqrt(2 * sm.B * sm.D_O * Z1c / (Zc - 2 * Z1c))
        assert res < 1e-10 and abs(alt - c[0]) < 1e-10, (r, res, alt, c[0])
    rcs = {}
    for model, want in (("3DLM", 24.74), ("3DLMP", 43.54), ("5DLM", 45.94)):
        lo, hi = 20.0, 60.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if sm.linear_growth(mid, model) < 0 else (lo, mid)
        rcs[model] = lo
        assert abs(lo - want) < 0.006, (model, lo, want)
    tr = sm.integrate([0, 1.0, 0, 0, 0], 0.001, 50000, 35.0, "3DLMP")
    ratio = tr[-1, 0] / sm.normalization(35.0, "3DLMP")[0]
    assert abs(ratio + 1.098) < 0.001, ratio
    # Appendix A
    dt = 0.001
    tr = sm.integrate([0, 1.0, 0, 0, 0], dt, 20000, 43.5, "5DLM")
    X, Y, Z, Y1, Z1 = tr.T
    d = sm.rhs(tr, 43.5, "5DLM")
    dE = X * d[:, 0] - sm.SIGMA * (d[:, 2] + d[:, 4] / 2)    # eq. (A5) / C3
    want = sm.SIGMA * (-X ** 2 + sm.B * Z + 2 * sm.B * Z1)   # eq. (A9) / C3
    energy_err = np.abs(dE - want).max() / np.abs(want).max()
    assert energy_err < 1e-12, energy_err
    # Warm rises: at the 5DLM steady roll, w and theta share their sign pattern.
    c = sm.critical_point(25.0, sign=-1.0)
    xs, zs = np.meshgrid(np.linspace(0, sm.WIDTH, 41), np.linspace(0.05, 0.95, 19))
    w = sm.velocity(c[0], xs, zs)[1]
    parts = sm.theta_parts(c, 25.0, xs, zs)
    side = parts["Y M2"] + parts["Y1 M5"]          # the part that varies across x
    corr = float(np.corrcoef(w.ravel(), side.ravel())[0, 1])
    flux = float(np.mean(w * sm.theta(c, 25.0, xs, zs)))
    assert corr > 0.9 and flux > 0, (corr, flux)
    print(f"model: critical points OK; linear r_c 3DLM {rcs['3DLM']:.2f}, 3DLMP "
          f"{rcs['3DLMP']:.2f}, 5DLM {rcs['5DLM']:.2f}; 3DLMP X/X3d {ratio:.4f}; "
          f"energy budget rel. err {energy_err:.1e}; warm rises: corr(w, sideways theta) "
          f"{corr:.2f}, heat flux <w theta> {flux:+.3f} > 0")


# --------------------------------------------------------------------------
# Scene plumbing
# --------------------------------------------------------------------------

def load_scene(path):
    t0 = time.perf_counter()
    nodes = load_node_csv(str(path))
    map_path, tracks_path = find_channel_files(str(path))
    ch_map = load_ch_map(map_path)
    tracks, id_to_col = load_ch_tracks(tracks_path)
    print(f"{path.name}: {len(nodes)} nodes, tracks {tracks.shape}, "
          f"loaded in {time.perf_counter() - t0:.1f} s")
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
    assert worst < 2e-4, f"frame 0 differs from the static file by {worst}"
    t0 = time.perf_counter()
    for f in range(0, tracks.shape[0], max(1, tracks.shape[0] // 50)):
        eng.apply_frame(f)
    per = (time.perf_counter() - t0) / 50 * 1000
    print(f"  join OK; frame 0 = static file (worst {worst:.1e}); apply_frame "
          f"{len(eng._bindings)} bindings, {per:.1f} ms/frame")
    return nodes, eng


def children(nodes):
    kids = {}
    for n in nodes:
        kids.setdefault(n.parent_id, []).append(n)
    return kids


def check_board(nodes):
    st = compute_world_transforms(nodes, 1.0)
    b = next(n for n in nodes if n.text.startswith("board frame: x = right"))
    w = next(n for n in nodes if n.text.startswith("wall - leaned"))
    Bb, Bw = st.world_basis[st.row_of_id[b.id]], st.world_basis[st.row_of_id[w.id]]
    local = Bw.T @ Bb                        # board axes in wall coords
    local /= np.linalg.norm(local[:, 0])     # the board may be uniformly scaled
    want = np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0]], dtype=float)
    assert np.allclose(local, want, atol=1e-9), local
    print("  board frame: x -> wall right, y -> wall up, z -> wall toward viewer")


# --------------------------------------------------------------------------
# Convection Cells
# --------------------------------------------------------------------------

def check_cells(nodes, eng):
    import generate_convection_cells as gen
    kids = children(nodes)
    worst_col, n_cells = 0, 0
    frames = (0, 400, 1000, gen.FRAMES - 1)
    cells = [n for n in nodes if n.text.startswith("fluid temperature, ")]
    for cell in cells:
        model, r = cell.text.split(", ")[1], float(cell.text.split("r = ")[1])
        verts = kids[cell.id]
        xs = {round(v.translate_x, 6) for v in verts}
        ys = {round(v.translate_y, 6) for v in verts}
        assert len(xs) == gen.NX and len(ys) == gen.NZ and len(verts) == gen.NX * gen.NZ, \
            (cell.text, len(xs), len(ys), len(verts))
        states = gen.simulate(model, r)[::gen.SUB][:gen.FRAMES]
        for f in frames:
            eng.apply_frame(f)
            for v in verts:
                x, z = v.translate_x / gen.CELL_S, v.translate_y / gen.CELL_S
                theta = sum(sm.theta_parts(states[f], r, x, z).values())   # mode sum
                want = gen.temp_color(0.5 - z + theta)
                got = (v.color_r, v.color_g, v.color_b)
                worst_col = max(worst_col, max(abs(int(a) - b) for a, b in zip(got, want)))
        n_cells += 1
    assert n_cells == 4 and worst_col <= 1, worst_col
    print(f"  cells: {n_cells} complete {gen.NX}x{gen.NZ} lattices; vertex colour vs "
          f"conduction + mode sum over frames {frames}: worst {worst_col} / 255")

    # Beads ride their streamlines.
    worst = 0.0
    beads = [n for n in nodes if n.text.startswith("fluid parcel")]
    cell_y = {}
    for cell in cells:
        cell_y[cell.text.split("fluid temperature, ")[1]] = cell.translate_y
    track = {b.id: [] for b in beads}
    for f in range(0, gen.FRAMES, 40):
        eng.apply_frame(f)
        for b in beads:
            tag = b.text.split("[")[1].rstrip("]")
            x = b.translate_x / gen.CELL_S
            z = (b.translate_y - cell_y[tag]) / gen.CELL_S
            track[b.id].append(abs(sm.stream_shape(x, z)))
    for vals in track.values():
        worst = max(worst, max(vals) - min(vals))
    assert worst < 2e-3, worst
    eng.reset()
    print(f"  cells: {len(beads)} beads, worst drift off their streamline (|M1|) {worst:.1e}")


# --------------------------------------------------------------------------
# r-Sweep Tower
# --------------------------------------------------------------------------

def check_tower(nodes):
    import generate_r_sweep_tower as gen
    kids = children(nodes)
    slices = [n for n in nodes if n.text.startswith("slice ")]
    worst = 0.0
    rng = np.random.default_rng(5)
    for s in rng.choice(slices, size=min(12, len(slices)), replace=False):
        model = s.text.split()[1]
        r = float(s.text.split("r = ")[1].split()[0])
        path = gen.slice_path(model, r)
        got = np.array([[v.translate_x, v.translate_y, v.translate_z] for v in kids[s.id]])
        worst = max(worst, np.abs(got - path).max())
    assert worst < 2e-4, worst
    print(f"  tower: {len(slices)} slices; 12 sampled match their model's normalized "
          f"trajectory to {worst:.1e}")


# --------------------------------------------------------------------------
# Feedback Loop
# --------------------------------------------------------------------------

def check_loop(nodes, eng):
    import generate_feedback_loop as gen
    import hcs
    rng = np.random.default_rng(3)
    for row in rng.uniform(-179, 179, size=(20, 5)):
        a = hcs.chain(row[None, :], gen.HG_R1, gen.HG_RATIO)[0]
        b = hcs.ts_leaf(row, gen.HG_R1, gen.HG_RATIO)
        assert np.abs(a - b).max() < 1e-12, (a, b)
    # The 4DLM escape is real and converged in the time step.
    for dt in (1e-3, 2e-4):
        s, t = gen.START.copy(), 0.0
        while np.abs(s).max() < 1e3:
            s = sm.rk4_step(s, dt, 25.0, "4DLM")
            t += dt
        assert abs(t - 1.187) < 0.002, (dt, t)
    # Engine leaf vs hcs.chain of the generator's own angles, at sampled frames.
    kids = children(nodes)
    frames_ = [n for n in nodes if "HCS hyperglyph frame" in n.text]
    glyphs = []
    for fr in frames_:
        tag = fr.text.split("[")[1].rstrip("]")
        model, r = tag.split(", r = ")[0], float(tag.split("r = ")[1])
        spins, leaf, stack = [], None, [fr]
        while stack:
            n = stack.pop()
            for c in kids.get(n.id, []):
                if "spinner" in c.text:
                    spins.append(c)
                if "-D leaf:" in c.text:
                    leaf = c
                stack.append(c)
        spins.sort(key=lambda s_: s_.branch_level)
        assert leaf is not None and len(spins) == gen.DIMS[model], (fr.text, len(spins))
        fine, _ = gen.simulate(model, r)
        glyphs.append((fr, leaf, gen.angles(fine[::gen.SUB][:gen.FRAMES], model, r)))
    worst = 0.0
    for f in (0, 50, 700, gen.FRAMES - 1):
        eng.apply_frame(f)
        st = compute_world_transforms(nodes, 1.0)
        for fr, leaf, ang in glyphs:
            row = st.row_of_id[fr.id]
            B = st.world_basis[row]
            local = np.linalg.solve(B, st.world_pos[st.row_of_id[leaf.id]] - st.world_pos[row])
            want = hcs.chain(ang[f][None, :], gen.HG_R1, gen.HG_RATIO)[0]
            worst = max(worst, np.abs(local - want).max())
    eng.reset()
    assert worst < 2e-4, worst
    print(f"  loop: hcs.chain = hyperdims geometry.ts (20 random 5-D points); 4DLM passes "
          f"|state| 1e3 at tau 1.187 for dt 1e-3 and 2e-4; {len(glyphs)} hyperglyphs, "
          f"engine leaf vs HCS chain worst {worst:.1e}")


# --------------------------------------------------------------------------
# Stability Landscape
# --------------------------------------------------------------------------

def check_landscape(nodes):
    import generate_stability_landscape as gen
    kids = children(nodes)
    rng = np.random.default_rng(9)
    worst_h = 0.0
    for model in gen.MODELS:
        surf = next(n for n in nodes if n.text == f"{gen.TITLE[model]}: largest Re(lambda) "
                                                  "over (sigma, r)")
        verts = kids[surf.id]
        assert len(verts) == len(gen.SIG) * len(gen.RS)
        for v in rng.choice(verts, 40, replace=False):
            s = gen.SIG[0] + v.translate_x / gen.SX
            r = gen.RS[0] + v.translate_y / gen.SY
            worst_h = max(worst_h, abs(v.translate_z - gen.height(gen.growth(model, s, r))))
    assert worst_h < 2e-4, worst_h
    # The contour is Re(lambda) = 0; the eigenvalue r_c is Lorenz's closed form.
    worst_c = max(abs(sm.linear_growth(r, m, sigma=s))
                  for m in gen.MODELS for s, r in gen.rc_curve(m, step=2.0))
    worst_l = max(abs(sm.linear_rc("3DLM", sigma=float(s)) - gen.lorenz_rc(s))
                  for s in range(5, 26))
    assert worst_c < 1e-8 and worst_l < 1e-8, (worst_c, worst_l)
    # Every ensemble onset lies on the stable side of its linear r_c.
    sweep = gen.load_sweep()
    for m in gen.MODELS:
        sw = sweep["models"][m]
        for s, on, rc, steady in zip(sweep["sigmas"], sw["onset"], sw["linear_rc"],
                                     sw["window_near_steady"]):
            assert on < rc and steady, (m, s, on, rc, steady)
    print(f"  landscape: sampled heights = Re(lambda) (worst {worst_h:.1e}); contour "
          f"|Re(lambda)| <= {worst_c:.0e}; eigenvalue r_c = Lorenz's closed form "
          f"(worst {worst_l:.0e}); every ensemble onset below its linear r_c, the roll "
          f"holding a 1e-3 kick in between")


def bake(nodes, eng, out_dir, frames, stem):
    os.makedirs(out_dir, exist_ok=True)
    for f in frames:
        eng.apply_frame(f)
        out = os.path.join(out_dir, f"{stem}_frame{f:04d}_gv_node.csv")
        save_node_csv(nodes, out)
        print(f"  baked frame {f} -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", choices=("cells", "tower", "loop", "landscape", "all"),
                    default="all")
    ap.add_argument("--bake-dir", default=None)
    ap.add_argument("--frames", type=int, nargs="*", default=[])
    args = ap.parse_args()

    check_model()
    if args.scene in ("cells", "all"):
        nodes, eng = load_scene(HERE / "Convection_Cells" / "Convection_Cells_gv_node.csv")
        check_board(nodes)
        check_cells(nodes, eng)
        if args.bake_dir:
            bake(nodes, eng, args.bake_dir, args.frames, "cells")
    if args.scene in ("tower", "all"):
        path = HERE / "R_Sweep_Tower" / "R_Sweep_Tower_gv_node.csv"
        nodes, eng = load_scene(path)
        check_board(nodes)
        check_tower(nodes)
        if args.bake_dir:
            bake(nodes, eng, args.bake_dir, args.frames, "tower")
    if args.scene in ("loop", "all"):
        nodes, eng = load_scene(HERE / "Feedback_Loop" / "Feedback_Loop_gv_node.csv")
        check_board(nodes)
        check_loop(nodes, eng)
        if args.bake_dir:
            bake(nodes, eng, args.bake_dir, args.frames, "loop")
    if args.scene in ("landscape", "all"):
        nodes = load_node_csv(str(HERE / "Stability_Landscape" /
                                  "Stability_Landscape_gv_node.csv"))
        print(f"Stability_Landscape_gv_node.csv: {len(nodes)} nodes (static)")
        check_board(nodes)
        check_landscape(nodes)


if __name__ == "__main__":
    main()
