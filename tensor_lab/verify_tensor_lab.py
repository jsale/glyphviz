"""
Check the tensor lab's three scenes through GlyphViz's own objects: load each
node CSV and its Channels files with the app's loaders, play frames with the
app's ChannelEngine, resolve transforms with compute_world_transforms, and
hold what the scene DRAWS to the math it claims.

    python verify_tensor_lab.py [--scene vectors|tensor|book|all]

Common to every scene:
  * the Channels join holds; frame 0 of every track equals the static file
  * Euler XYZ is what the kit assumes (world basis = Rx Ry Rz diag(scale))
  * the board frame really is x = right, y = up, z = toward the viewer
Scene 1, Vectors and Bases:
  * the drawn basis frame IS R(t); the legs end exactly on v's tip; every
    drop line meets its axis at a right angle; the bars are v . e_i';
    the |v|^2 stack never changes height; Act 3 replays Act 2's bars
Scene 2, Vector to Tensor:
  * the ellipsoid glyph is the image of the unit sphere under T
  * every output arrow tip (the probe's T n and each T e_j') lies on it
  * the nine bars are R^T T R; tr T holds; Act 5 ends diagonal (2, 1.2, 0.5)
  * Act 4's scope: tr T has no wave, v1' one per turn, T11' and T12' two
Scene 3, Spinning Book:
  * the integrator conserves L (room) and kinetic energy; R stays orthonormal
  * the drawn book IS R(t); the L arrow never moves; the w arrow is w(t)
  * the I bars are R I_body R^T, and L = I w holds in the room's numbers
  * book 2 flips, books 1 and 3 never tilt past a few degrees
  * every polhode keeps its energy; every L-sphere bead is on the sphere
Scene 4, Current Across the Grain:
  * the E and J tips are E and sigma E; every J_i waterfall lands on row . E;
    the beads drift along J; J is parallel to E only on the crystal's axes;
    the 4-D shadow is the projected 4-D lattice
Scene 5, Slanted Rulers:
  * the lattice is m e1 + n e2; legs end at v^1 e1, shadows drop at right
    angles; g_ij v^j lands on v_i; v^i v_i never moves; e^i . e_j = delta
Scene 6, The Cut:
  * the traction tips are sigma n and its two parts; the Mohr point turns
    exactly -2 theta; every 3-D cut lands in the arbelos; Act 3 ends diagonal
Scene 7, A Field of Machines:
  * every voxel's ellipsoid is its D; the dye fills the drawn 2-sigma
    ellipsoid; every track step follows the local long axis
"""
import argparse
import sys
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

import tensor_kit as kit  # noqa: E402

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
    unlabelled = [n.id for n in nodes if not n.text.strip()]
    assert not unlabelled, f"{len(unlabelled)} nodes without a label"
    print(f"{path.name}: {len(nodes)} nodes, every one labelled; {tracks.shape[1]} tracks x "
          f"{tracks.shape[0]} frames; join OK; frame 0 = static file (worst {worst:.1e})")
    return nodes, eng


class Lookup:
    def __init__(self, nodes):
        self.nodes = nodes
        self.by_id = {n.id: n for n in nodes}

    def one(self, text, parent=None, type_=None):
        hits = [n for n in self.nodes if n.text == text
                and (parent is None or n.parent_id == parent)
                and (type_ is None or n.type == type_)]
        assert len(hits) == 1, (text, len(hits))
        return hits[0]

    def starts(self, prefix):
        return [n for n in self.nodes if n.text.startswith(prefix)]


def world(nodes):
    st = compute_world_transforms(nodes, 1.0)
    return lambda n: (st.world_pos[st.row_of_id[n.id]], st.world_basis[st.row_of_id[n.id]])


def bar_value(n, unit):
    """Signed value of a kit.signed_bar from its scale and its colour/offset."""
    return n.scale_y * 2 * kit.CUBE_FACE / unit


def check_conventions():
    for e in ((30, 40, 50), (-120, 75, 10), (5, -89.5, 170)):
        R = kit.from_euler_xyz(e)
        assert np.allclose(kit.from_euler_xyz(kit.euler_xyz(R)), R, atol=1e-12)
    Rs = np.array([kit.tour(s) for s in np.linspace(0, 1, 101)])
    assert np.allclose(np.einsum("fij,fkj->fik", Rs, Rs), np.eye(3), atol=1e-12)
    assert np.allclose(Rs[0], np.eye(3)) and np.allclose(Rs[-1], np.eye(3), atol=1e-12)
    print("conventions: Euler XYZ round-trips; the tour is a closed loop of rotations")


def check_board(look, w):
    b = look.starts("board: x = right")[0]
    wl = look.starts("wall - leaned")[0]
    Bb, Bw = w(b)[1], w(wl)[1]
    local = Bw.T @ Bb
    local /= np.linalg.norm(local[:, 0])
    assert np.allclose(local, [[0, 0, 1], [1, 0, 0], [0, 1, 0]], atol=1e-9), local


def stage_of(look, w, prefix="stage:"):
    s = look.starts(prefix)[0]
    p, B = w(s)
    assert np.allclose(B, kit.stage_world_rotation(), atol=1e-9)
    return p, B


# --------------------------------------------------------------------------

def check_vectors():
    import generate_vectors as gen
    nodes, eng = load_scene(HERE / "Vectors_and_Bases" / "Vectors_and_Bases_gv_node.csv")
    look = Lookup(nodes)
    Rs, vs, g, comps = gen.timeline()
    basis = look.starts("the basis frame:")[0]
    v_tip = look.one("v", type_=5)
    leg3 = look.one("leg 3: v3 e3'  (walk v3 along e3'): tip")
    feet = [look.one(f"shadow of v on e{i + 1}': v{i + 1} = v . e{i + 1}'") for i in range(3)]
    tip_b = look.one("v's tip, in basis coordinates")
    bars = [look.one(f"v{i + 1} = v . e{i + 1}'  (component {i + 1}, right now)") for i in range(3)]
    stack = look.starts("v1^2: its share")[0], look.starts("v2^2")[0], look.starts("v3^2")[0]
    worst = dict(basis=0.0, legs=0.0, perp=0.0, bars=0.0, stack=0.0)
    frames = list(range(0, gen.FRAMES, 37)) + [gen.FRAMES - 1]
    rec = {}
    for f in frames:
        eng.apply_frame(f)
        w = world(nodes)
        if f == 0:
            check_board(look, w)
        p0, B0 = stage_of(look, w)
        worst["basis"] = max(worst["basis"], np.abs(B0.T @ w(basis)[1] - Rs[f]).max())
        tip = w(v_tip)[0]
        assert np.allclose(B0.T @ (tip - p0), vs[f] * gen.S, atol=2e-3)
        if f >= gen.GROW[2][1]:
            worst["legs"] = max(worst["legs"], np.linalg.norm(w(leg3)[0] - tip))
            assert np.linalg.norm(w(tip_b)[0] - tip) < 2e-3
            for i, foot in enumerate(feet):
                e = B0 @ Rs[f][:, i]
                worst["perp"] = max(worst["perp"], abs(np.dot(tip - w(foot)[0], e)))
        vals = [np.sign(b.translate_y - gen.BARS_Y) * bar_value(b, gen.BAR_UNIT) for b in bars]
        worst["bars"] = max(worst["bars"], np.abs(np.array(vals) - comps[f]).max())
        top = max(n.translate_y + n.scale_y * kit.CUBE_FACE for n in stack if n.scale_y > 0)
        worst["stack"] = max(worst["stack"], abs(top - (gen.BARS_Y + gen.STACK_UNIT * 3.85)))
        rec[f] = vals
    shift = gen.ACT3[0] - gen.ACT2[0]
    replay = 0.0
    for f in range(gen.ACT2[0], gen.ACT2[1], 25):
        eng.apply_frame(f)
        a = [b.scale_y for b in bars]
        eng.apply_frame(f + shift)
        b_ = [b.scale_y for b in bars]
        replay = max(replay, max(abs(x - y) for x, y in zip(a, b_)))
    eng.reset()
    assert worst["basis"] < 1e-4 and worst["legs"] < 2e-3 and worst["perp"] < 2e-3
    assert worst["bars"] < 1e-3 and worst["stack"] < 1e-3 and replay < 1e-9
    print(f"  basis frame = R(t) (worst {worst['basis']:.1e}); legs end on v's tip "
          f"({worst['legs']:.1e}); drop lines perpendicular ({worst['perp']:.1e}); bars = v . e_i' "
          f"({worst['bars']:.1e}); |v|^2 stack height fixed ({worst['stack']:.1e}); "
          f"Act 3 replays Act 2 ({replay:.0e})")


# --------------------------------------------------------------------------

def check_tensor():
    import generate_tensor as gen
    nodes, eng = load_scene(HERE / "Vector_to_Tensor" / "Vector_to_Tensor_gv_node.csv")
    look = Lookup(nodes)
    Rs, n, sweep = gen.timeline()
    Tp = gen.components(Rs)
    ell = look.starts("the tensor T, drawn with no basis")[0]
    basis = look.starts("the basis frame:")[0]
    probe = look.one("T n (output)", type_=5)
    outs = [look.one(f"T e{j + 1}'", parent=basis.id, type_=5) for j in range(3)]
    grid = [[look.one(f"T_{i + 1}{j + 1} = e{i + 1}' . T e{j + 1}'"
                      + ("  (diagonal)" if i == j else "  (off-diagonal)")) for j in range(3)]
            for i in range(3)]
    Tinv = np.linalg.inv(gen.T)

    def on_ellipsoid(x):
        y = x / gen.S
        return abs(np.sqrt(y @ Tinv @ Tinv @ y) - 1)

    eng.apply_frame(gen.ELLIPSOID_ON + 1)
    w = world(nodes)
    check_board(look, w)
    p0, B0 = stage_of(look, w)
    Be = B0.T @ w(ell)[1]
    assert np.allclose(Be @ Be.T, gen.S ** 2 * gen.T @ gen.T, atol=1e-6), "ellipsoid shape"
    worst_probe = 0.0
    for f in range(0, sweep, 13):
        eng.apply_frame(f)
        w = world(nodes)
        worst_probe = max(worst_probe, on_ellipsoid(B0.T @ (w(probe)[0] - p0)))
    worst_out, worst_bar = 0.0, 0.0
    for f in list(range(gen.ACT2[0], gen.FRAMES, 29)) + [gen.FRAMES - 1]:
        eng.apply_frame(f)
        w = world(nodes)
        assert np.abs(B0.T @ w(basis)[1] - Rs[f]).max() < 1e-4
        for j, o in enumerate(outs):
            x = B0.T @ (w(o)[0] - p0)
            worst_out = max(worst_out, on_ellipsoid(x))
            assert np.allclose(x, gen.T @ Rs[f][:, j] * gen.S, atol=2e-3)
        for i in range(3):
            for j in range(3):
                b = grid[i][j]
                sgn = np.sign(b.translate_y - (gen.MY0 - i * gen.CH)) or 1.0
                worst_bar = max(worst_bar, abs(sgn * bar_value(b, gen.MUNIT) - Tp[f, i, j]))
    eng.apply_frame(gen.FRAMES - 1)
    off = max(grid[i][j].scale_y for i in range(3) for j in range(3) if i != j)
    diag = [bar_value(grid[i][i], gen.MUNIT) for i in range(3)]
    eng.reset()
    assert worst_probe < 2e-3 and worst_out < 2e-3 and worst_bar < 1e-3
    assert off < 1e-3 and np.allclose(diag, gen.LAM, atol=1e-3), (off, diag)
    # Act 4: harmonic content per turn.
    ks = np.arange(*gen.ACT4)[:-1]
    vp = np.einsum("fki,k->fi", Rs, gen.V0)
    tr = np.trace(Tp, axis1=1, axis2=2)

    def harmonic(x):
        spec = np.abs(np.fft.rfft(x - x.mean()))
        return int(np.argmax(spec)) if spec.max() > 1e-9 else 0

    h = (harmonic(tr[ks]), harmonic(vp[ks, 0]), harmonic(Tp[ks, 0, 0]), harmonic(Tp[ks, 0, 1]))
    assert h == (0, 1, 2, 2), h
    assert np.ptp(tr) < 1e-12
    print(f"  ellipsoid = T applied to the unit sphere; probe tips on it (worst {worst_probe:.1e}), "
          f"T e_j' tips on it ({worst_out:.1e}); bars = R^T T R ({worst_bar:.1e}); tr T fixed; "
          f"Act 5 ends diagonal {np.round(diag, 3).tolist()}, off-diagonal scale <= {off:.0e}; "
          f"Act 4 waves per turn: tr 0, v1' 1, T11' 2, T12' 2")


# --------------------------------------------------------------------------

def check_book():
    import generate_spinning_book as gen
    import rigid_body as rb
    rs = gen.runs()
    I = rb.I_BODY
    for k, (Rs, ws) in enumerate(rs):
        L = np.einsum("fij,fj->fi", Rs, I * ws)
        E = 0.5 * (I * ws ** 2).sum(1)
        orth = np.abs(np.einsum("fij,fkj->fik", Rs, Rs) - np.eye(3)).max()
        assert np.abs(L - L[0]).max() < 1e-9 and np.ptp(E) < 1e-9 and orth < 1e-12
        # Same answer at half the substep.
        R2, w2 = rb.integrate(Rs[0], ws[0], gen.DT, 300, sub=20)
        assert np.abs(R2 - Rs[:301]).max() < 1e-7, k
    print("  physics: L (room) and energy conserved to 1e-9 over 60 s; R orthonormal; "
          "halving the step changes nothing above 1e-7")
    nodes, eng = load_scene(HERE / "Spinning_Book" / "Spinning_Book_gv_node.csv")
    look = Lookup(nodes)
    worst = dict(body=0.0, L=0.0, w=0.0, I=0.0, LIw=0.0)
    tilt = []
    for k, (Rs, ws) in enumerate(rs):
        frame = look.starts(f"book {k + 1} room frame")[0]
        body = look.starts(f"book {k + 1}'s body frame")[0]
        Ltip = look.one("L", parent=frame.id, type_=5)
        wtip = look.one("w", parent=frame.id, type_=5)
        Ibars = [[look.one(f"book {k + 1}: I_{'xyz'[i]}{'xyz'[j]} in the room's basis")
                  for j in range(3)] for i in range(3)]
        wbars = [look.one(f"book {k + 1}: w_{'xyz'[i]} (room), in units of the spin rate")
                 for i in range(3)]
        Lbars = [look.one(f"book {k + 1}: L_{'xyz'[i]} (room), in units of |L|: never moves")
                 for i in range(3)]
        Lr = np.einsum("fij,fj->fi", Rs, I * ws)
        wr = np.einsum("fij,fj->fi", Rs, ws)
        Lhat = Lr[0] / np.linalg.norm(Lr[0])
        for f in range(0, gen.FRAMES, 23):
            eng.apply_frame(f)
            w = world(nodes)
            p0, B0 = w(frame)
            worst["body"] = max(worst["body"], np.abs(B0.T @ w(body)[1] - Rs[f]).max())
            worst["L"] = max(worst["L"], np.abs(B0.T @ (w(Ltip)[0] - p0) - Lhat * gen.ARROW).max())
            worst["w"] = max(worst["w"], np.abs(B0.T @ (w(wtip)[0] - p0)
                                                - wr[f] * gen.W_DRAW / gen.W0).max())
            Ir = Rs[f] @ np.diag(I) @ Rs[f].T
            base = [gen.PANEL_Y - i * 1.9 for i in range(3)]
            drawn = np.array([[(np.sign(Ibars[i][j].translate_y - base[i]) or 1.0)
                               * bar_value(Ibars[i][j], gen.UI) for j in range(3)]
                              for i in range(3)])
            worst["I"] = max(worst["I"], np.abs(drawn - Ir).max())
            b0 = gen.PANEL_Y - 2.4
            wd = np.array([(np.sign(b.translate_y - b0) or 1.0) * bar_value(b, gen.UW * 1.5)
                           for b in wbars]) * gen.W0
            Ld = np.array([(np.sign(b.translate_y - b0) or 1.0) * bar_value(b, gen.UL * 1.5)
                           for b in Lbars]) * np.linalg.norm(Lr[0])
            worst["LIw"] = max(worst["LIw"], np.abs(drawn @ wd - Ld).max())
        tilt.append(np.degrees(np.arccos(np.clip(np.abs(Rs[:, :, k] @ Lhat), -1, 1))).max())
    eng.reset()
    flips = [int(np.sum(np.diff(np.sign(Rs[:, :, k] @ [0, 0, 1.0])) != 0))
             for k, (Rs, _w) in enumerate(rs)]
    assert worst["body"] < 1e-4 and worst["L"] < 2e-3 and worst["w"] < 2e-3
    assert worst["I"] < 1e-3 and worst["LIw"] < 1e-2
    assert flips[1] >= 4 and flips[0] == flips[2] == 0 and tilt[0] < 5 and tilt[2] < 5, (flips, tilt)
    # The L-sphere.
    worst_e = 0.0
    for deg in (15, 30, 45, 58, 73, 80, 86):
        a = np.radians(deg)
        p = rb.polhode([np.cos(a), 0.0, np.sin(a)])
        e = (p ** 2 / I).sum(1)
        worst_e = max(worst_e, np.ptp(e) / e.mean())
    for nvec in rb.separatrix_normals():
        u = np.array([0.0, 1.0, 0.0])
        v = np.cross(nvec, u)
        t = np.linspace(0, 2 * np.pi, 50)
        pts = np.outer(np.cos(t), u) + np.outer(np.sin(t), v)
        assert np.allclose((pts ** 2 / I).sum(1), 1 / I[1], atol=1e-12)
    sph = look.starts("L-sphere frame")[0]
    beads = [look.one(f"book {k + 1}: L as the book sees it") for k in range(3)]
    worst_r = 0.0
    for f in range(0, gen.FRAMES, 97):
        eng.apply_frame(f)
        w = world(nodes)
        p0, _ = w(sph)
        for b in beads:
            worst_r = max(worst_r, abs(np.linalg.norm(w(b)[0] - p0) - gen.RS * 1.01))
    eng.reset()
    assert worst_e < 1e-6 and worst_r < 2e-3
    print(f"  books drawn at R(t) (worst {worst['body']:.1e}); L arrow fixed ({worst['L']:.1e}); "
          f"w arrow = w(t) ({worst['w']:.1e}); I bars = R I R^T ({worst['I']:.1e}); drawn "
          f"I . w = drawn L ({worst['LIw']:.1e})")
    print(f"  flips: {flips}; worst tilt off L: book 1 {tilt[0]:.2f} deg, book 3 {tilt[2]:.2f} deg; "
          f"polhodes keep their energy ({worst_e:.0e}); separatrix = the e2 energy exactly; "
          f"beads on the sphere ({worst_r:.1e})")


# --------------------------------------------------------------------------

def check_crystal():
    import generate_crystal as gen
    nodes, eng = load_scene(HERE / "Current_Across_the_Grain"
                            / "Current_Across_the_Grain_gv_node.csv")
    look = Lookup(nodes)
    M, Qc, E, E4 = gen.timeline()
    Sg = gen.sigma_lab(Qc)
    J = np.einsum("fij,fj->fi", Sg, E)
    J4 = E4 @ gen.SIGMA4.T
    assert np.linalg.eigvalsh(gen.SIGMA4).min() > 0
    turn = look.starts("turn frame")[0]
    lab = look.starts("lab frame:")[0]
    cry = look.starts("crystal frame:")[0]
    e_tip = look.one("E (field)", type_=5)
    j_tip = look.one("J (current)", type_=5)
    beads = look.starts("charge carrier ")
    atoms4 = {n.text: n for n in look.starts("4-D atom ")}
    tags = {2: "2-D: 4 numbers", 3: "3-D: 9 numbers", 4: "4-D: 16 numbers"}
    totals = {N: [look.one(f"J_{gen.AX_NAME[i]} = the sum of its row's pieces ({tags[N]})")
                  for i in range(N)] for N in tags}
    worst = dict(frame=0.0, arrows=0.0, totals=0.0, hyper=0.0, sigma=0.0)
    grid4 = np.array([(a, b, c, d) for a in (-1, 0, 1) for b in (-1, 0, 1)
                      for c in (-1, 0, 1) for d in (-1, 0, 1)])
    for f in list(range(0, gen.FRAMES, 31)) + [gen.FRAMES - 1]:
        eng.apply_frame(f)
        w = world(nodes)
        if f == 0:
            check_board(look, w)
        Bt = w(turn)[1]
        pl, Bl = w(lab)
        worst["frame"] = max(worst["frame"], np.abs(Bt.T @ Bl - M[f]).max(),
                             np.abs(Bl.T @ w(cry)[1] - Qc[f]).max())
        if f < gen.HYPER_ON:
            worst["arrows"] = max(worst["arrows"],
                                  np.abs(Bl.T @ (w(e_tip)[0] - pl) - E[f] * gen.S).max(),
                                  np.abs(Bl.T @ (w(j_tip)[0] - pl) - J[f] * gen.S).max())
            N = 2 if f < gen.ACT1[1] else 3
            Jn = J[f, :N]
        else:
            N = 4
            Jn = J4[f]
            P = gen.hyper_projection(f)[:3]
            for x in grid4:
                key = tuple(int(v) for v in x)
                a = atoms4[f"4-D atom (x, y, z, w) = {key}: w = {key[3]} sets its colour"]
                want = P @ (x * gen.HYP)
                worst["hyper"] = max(worst["hyper"], np.abs(Bl.T @ (w(a)[0] - pl) - want).max())
        if (f < gen.ACT1[1] or gen.SWING[1] <= f < gen.HYPER_ON or f >= gen.HYPER_ON):
            for i, t in enumerate(totals[N]):
                drawn = (t.translate_y - (gen.MY0 - i * gen.CH)) / gen.MUNIT
                worst["totals"] = max(worst["totals"], abs(drawn - Jn[i]))
    # sigma bars: one frame per block.
    for N, f, sig in ((2, 100, Sg[100, :2, :2]), (3, 1200, Sg[1200]), (4, 2400, gen.SIGMA4)):
        eng.apply_frame(f)
        for i in range(N):
            for j in range(N):
                a, b = gen.AX_NAME[i], gen.AX_NAME[j]
                bar = look.one(f"sigma_{a}{b} ({tags[N]}): how much E_{b} drives J_{a}"
                               + ("  (diagonal)" if i == j else ""))
                sgn = np.sign(bar.translate_y - (gen.MY0 - i * gen.CH)) or 1.0
                worst["sigma"] = max(worst["sigma"], abs(sgn * bar_value(bar, gen.MUNIT) - sig[i, j]))
    # The charges drift along J: over a 1 s hold, each un-wrapped bead moves J * DRIFT.
    drift_ok, drift_n = 0, 0
    for h0, _h1 in gen.EXPTS + gen.PRINC + ((300, 330),):
        f0, f1 = h0 + 20, h0 + 50
        eng.apply_frame(f0)
        w = world(nodes)
        pl, Bl = w(lab)
        p0 = [Bl.T @ (w(b)[0] - pl) for b in beads]
        eng.apply_frame(f1)
        w = world(nodes)
        p1 = [Bl.T @ (w(b)[0] - pl) for b in beads]
        want = J[f0:f1].sum(0) * gen.DRIFT / 30.0
        for a, b in zip(p0, p1):
            drift_n += 1
            drift_ok += np.linalg.norm((b - a) - want) < 0.03
    eng.reset()
    ang = np.degrees(np.arccos(np.clip(np.einsum("fi,fi->f", E, J) / np.linalg.norm(J, axis=1),
                                       -1, 1)))[:gen.HYPER_ON]
    par = max(ang[h0:h1].max() for h0, h1 in gen.PRINC)
    assert worst["frame"] < 1e-4 and worst["arrows"] < 2e-3 and worst["totals"] < 1e-3
    assert worst["hyper"] < 1e-2 and worst["sigma"] < 1e-3, worst
    assert drift_ok >= 0.8 * drift_n, (drift_ok, drift_n)
    assert abs(ang[0] - 20.2) < 0.1 and ang.max() < 90 and par < 1e-6, (ang[0], ang.max(), par)
    print(f"  lab + crystal frames drawn as M(t), Q(t) ({worst['frame']:.1e}); E, J tips = E, "
          f"sigma E ({worst['arrows']:.1e}); sigma bars ({worst['sigma']:.1e}); every J_i "
          f"waterfall total = row . E ({worst['totals']:.1e}); 4-D shadow = P(t) x "
          f"({worst['hyper']:.1e})")
    print(f"  {drift_ok}/{drift_n} bead moves = J x drift over 1 s (the rest wrapped); "
          f"E-J angle {ang[0]:.1f} deg at the start, never past {ang.max():.1f} deg; "
          f"J parallel to E on the crystal's axes ({par:.0e} deg)")


def check_metric():
    import generate_metric as gen
    nodes, eng = load_scene(HERE / "Slanted_Rulers" / "Slanted_Rulers_gv_node.csv")
    look = Lookup(nodes)
    Eb, up, low, g, Db = gen.timeline()
    assert np.allclose(np.einsum("fki,fkj->fij", Db, Eb), np.eye(2), atol=1e-12)
    assert np.allclose(np.einsum("fij,fj->fi", g, up), low, atol=1e-12)
    lab = look.starts("lab plane: x = right")[0]
    atoms = {(m, n): look.one(f"lattice point {m} e1 + {n} e2") for m in gen.LAT for n in gen.LAT}
    corner = look.one("leg 1: v^1 e1 (v^1 steps of e1): tip")
    dcorner = look.one("dual leg 1: v_1 e^1 (v_1 steps of e^1): tip")
    feet = [look.starts(f"foot of v's shadow on the e{i + 1} line")[0] for i in range(2)]
    duals = [look.one(f"e^{i + 1} (dual)", type_=5) for i in range(2)]
    ups = [look.one(f"v^{i + 1} (upper): how many steps of e{i + 1}") for i in range(2)]
    lows = [look.one(f"v_{i + 1} (lower): v . e{i + 1}") for i in range(2)]
    rebuilt = [look.one(f"v_{i + 1} rebuilt from the upper components by g") for i in range(2)]
    inv = look.one("v^1 v_1 + v^2 v_2 = |v|^2: never moves")
    naive = look.one("(v^1)^2 + (v^2)^2: drifts (wrong in a slanted basis)")
    worst = dict(lattice=0.0, legs=0.0, perp=0.0, bars=0.0, rebuilt=0.0, inv=0.0, dual=0.0)
    naive_h = []
    for f in list(range(0, gen.FRAMES, 29)) + [gen.FRAMES - 1]:
        eng.apply_frame(f)
        w = world(nodes)
        if f == 0:
            check_board(look, w)
        p0, B0 = w(lab)

        def at(n):
            return (B0.T @ (w(n)[0] - p0))[:2] / gen.S
        for (m, n), a in atoms.items():
            worst["lattice"] = max(worst["lattice"],
                                   np.abs(at(a) - (m * Eb[f, :, 0] + n * Eb[f, :, 1])).max())
        worst["legs"] = max(worst["legs"], np.abs(at(corner) - up[f, 0] * Eb[f, :, 0]).max())
        for i, foot in enumerate(feet):
            worst["perp"] = max(worst["perp"], abs((gen.V - at(foot)) @ Eb[f, :, i]))
        for i in range(2):
            worst["bars"] = max(worst["bars"],
                                abs(bar_value(ups[i], gen.BUNIT) - up[f, i]),
                                abs(bar_value(lows[i], gen.BUNIT) - low[f, i]))
        if f >= gen.ACT4[0]:
            for i in range(2):
                worst["rebuilt"] = max(worst["rebuilt"],
                                       abs((rebuilt[i].translate_y - gen.WY0) / gen.BUNIT - low[f, i]))
            worst["inv"] = max(worst["inv"], abs((inv.translate_y - gen.IY0) / gen.IUNIT
                                                 - gen.V @ gen.V))
            naive_h.append((naive.translate_y - gen.IY0) / gen.IUNIT)
        if f >= gen.DUAL_ON:
            for i in range(2):
                for j in range(2):
                    worst["dual"] = max(worst["dual"],
                                        abs(at(duals[i]) @ Eb[f, :, j] - (i == j)))
            worst["dual"] = max(worst["dual"],
                                np.abs(at(dcorner) - low[f, 0] * Db[f, :, 0]).max())
    eng.reset()
    assert worst["lattice"] < 3e-3 and worst["legs"] < 1e-3 and worst["perp"] < 1e-3
    assert worst["bars"] < 1e-3 and worst["rebuilt"] < 1e-3 and worst["inv"] < 1e-3
    assert worst["dual"] < 1e-3 and np.ptp(naive_h) > 1.0, (worst, np.ptp(naive_h))
    i_str = gen.STRETCH[1] + 10
    assert abs(up[i_str, 0] - up[0, 0] / 2) < 1e-9 and abs(low[i_str, 0] - 2 * low[0, 0]) < 1e-9
    print(f"  lattice = m e1 + n e2 ({worst['lattice']:.1e}); leg corner = v^1 e1 "
          f"({worst['legs']:.1e}); shadows drop at right angles ({worst['perp']:.1e}); bars = v^i, "
          f"v_i ({worst['bars']:.1e}); stretch x2: v^1 halves, v_1 doubles")
    print(f"  waterfalls g_ij v^j land on v_i ({worst['rebuilt']:.1e}); v^i v_i = |v|^2 "
          f"({worst['inv']:.1e}) while (v^1)^2 + (v^2)^2 swings {np.ptp(naive_h):.2f}; dual "
          f"e^i . e_j = delta and the dual legs reach v ({worst['dual']:.1e})")


def check_stress():
    import generate_stress as gen
    nodes, eng = load_scene(HERE / "The_Cut" / "The_Cut_gv_node.csv")
    look = Lookup(nodes)
    th, n2, s2, t2, sn2, tau2, n3, t3, sn3, sh3, Rc = gen.timeline()
    lab = look.starts("lab plane: x = right")[0]
    st = look.starts("stage:")[0]
    tips2 = {k: look.one(k, type_=5) for k in ("t = sigma n (traction)", "sigma_n: the pull",
                                               "tau: the shear")}
    pt2 = look.one("this cut, right now: (sigma_n, tau)")
    t3_tip = look.one("t = sigma n", type_=5)
    pull3, shear3 = look.one("pull: tip"), look.one("shear: tip")
    pt3 = look.one("this 3-D cut, right now: (sigma_n, |tau|)")
    ring = look.one("the cut plane (its rim), normal n")
    cube = look.starts("the cube of material")[0]
    c2 = 0.5 * np.trace(gen.SIG2)
    r2 = np.hypot(0.5 * (gen.SIG2[0, 0] - gen.SIG2[1, 1]), gen.SIG2[0, 1])
    ps = np.sort(gen.P3)[::-1]
    worst = dict(arrows=0.0, mohr=0.0, ring=0.0, cube=0.0)
    for f in list(range(gen.CUT_ON, gen.FRAMES, 23)) + [gen.FRAMES - 1]:
        eng.apply_frame(f)
        w = world(nodes)
        if f < gen.ACT1[1]:
            p0, B0 = w(lab)

            def at(n):
                return (B0.T @ (w(n)[0] - p0))[:2]
            want = {"t = sigma n (traction)": t2[f], "sigma_n: the pull": sn2[f] * n2[f],
                    "tau: the shear": tau2[f] * s2[f]}
            for k, n in tips2.items():
                if k == "tau: the shear" and abs(tau2[f]) <= 0.03:
                    continue
                worst["arrows"] = max(worst["arrows"], np.abs(at(n) / gen.S - want[k]).max())
            sv = (pt2.translate_x - gen.MX0) / gen.MU
            tv = (pt2.translate_y - gen.MY0) / gen.MU
            worst["mohr"] = max(worst["mohr"], abs(np.hypot(sv - c2, tv) - r2),
                                abs(sv - sn2[f]) + abs(tv - tau2[f]))
        elif f >= gen.ACT2[0]:
            p0, B0 = w(st)

            def at3(n):
                return B0.T @ (w(n)[0] - p0)
            worst["arrows"] = max(worst["arrows"], np.abs(at3(t3_tip) / gen.S - t3[f]).max(),
                                  np.abs(at3(pull3) / gen.S - sn3[f] * n3[f]).max())
            if np.linalg.norm(sh3[f]) > 0.03:
                worst["arrows"] = max(worst["arrows"], np.abs(at3(shear3) / gen.S - sh3[f]).max())
            Br = B0.T @ w(ring)[1]
            worst["ring"] = max(worst["ring"], 1 - abs(Br[:, 2] @ n3[f]) / np.linalg.norm(Br[:, 2]))
            Bc = B0.T @ w(cube)[1]
            worst["cube"] = max(worst["cube"], np.abs(Bc / np.linalg.norm(Bc[:, 0]) - Rc[f]).max())
            sv = (pt3.translate_x - gen.MX0) / gen.MU
            tv = (pt3.translate_y - gen.MY0) / gen.MU
            worst["mohr"] = max(worst["mohr"], abs(sv - sn3[f]) + abs(tv - np.linalg.norm(sh3[f])))
    eng.reset()
    # Mohr geometry, exactly: the point turns -2 theta; tau = 0 on the principal planes.
    k = np.arange(gen.KEYS[0][0], gen.KEYS[-1][0])
    phi = np.unwrap(np.arctan2(tau2[k], sn2[k] - c2))
    turn = np.degrees(phi - phi[0]) + 2 * (th[k] - th[k[0]])
    assert np.abs(turn).max() < 1e-9
    held = [f0 for (f0, a0), (f1, a1) in zip(gen.KEYS, gen.KEYS[1:]) if a0 == a1]
    taus = [abs(tau2[f]) for f in held]
    tau3 = np.linalg.norm(sh3, axis=1)
    sw = slice(*gen.SWEEP3)
    d = [((sn3[sw] - 0.5 * (ps[a] + ps[b])) ** 2 + tau3[sw] ** 2) - (0.5 * (ps[a] - ps[b])) ** 2
         for a, b in ((0, 2), (0, 1), (1, 2))]
    assert d[0].max() < 1e-9 and d[1].min() > -1e-9 and d[2].min() > -1e-9
    end = np.einsum("ki,kl,lj->ij", Rc[-1], gen.SIG3, Rc[-1])
    assert np.allclose(end, np.diag(gen.P3), atol=1e-9)
    assert worst["arrows"] < 2e-3 and worst["mohr"] < 2e-3 and worst["ring"] < 1e-6
    assert worst["cube"] < 1e-4 and taus[0] < 1e-12 and taus[2] < 1e-12, (worst, taus)
    print(f"  traction, pull and shear tips = sigma n and its two parts ({worst['arrows']:.1e}); "
          f"Mohr points on the drawn circle / at (sigma_n, |tau|) ({worst['mohr']:.1e}); ring normal "
          f"= n; cube = R(t) ({worst['cube']:.1e})")
    print(f"  the Mohr point turns exactly -2 theta; tau = 0 on the 22.5 and 112.5 deg cuts, "
          f"|tau| = {taus[1]:.4f} = radius at 67.5; every 3-D cut inside the outer circle and "
          f"outside both inner ones; Act 3 ends diagonal {np.round(np.diag(end), 6).tolist()}")


def check_field():
    import generate_field as gen
    nodes, eng = load_scene(HERE / "A_Field_of_Machines" / "A_Field_of_Machines_gv_node.csv")
    look = Lookup(nodes)
    D, kinds = gen.field()
    sl = look.starts("slice plane: x = right")[0]
    eng.apply_frame(gen.ACT3[0])
    w = world(nodes)
    check_board(look, w)
    p0, B0 = w(sl)
    worst_shape, worst_col = 0.0, 0
    for i in range(gen.NX):
        for j in range(gen.NY):
            n = look.starts(f"voxel ({i + 1}, {j + 1}), ")[0]
            B = B0.T @ w(n)[1]
            worst_shape = max(worst_shape,
                              np.abs(B @ B.T / (gen.GLYPH * gen.S) ** 2 - D[i, j]).max())
            assert np.allclose(B0.T @ (w(n)[0] - p0), [gen.XS[i] * gen.S, gen.YS[j] * gen.S, 0],
                               atol=1e-4)
            lam, vec = gen.eig_sorted(D[i, j])
            worst_col = max(worst_col, np.abs(np.array([n.color_r, n.color_g, n.color_b])
                                              - gen.dti_color(lam, vec)).max())
    # The drop: about three quarters of the dye inside the drawn 2-sigma ellipsoid,
    # and the cloud's long axis along D's.
    f = gen.MOVE[0] - 1
    eng.apply_frame(f)
    w = world(nodes)
    p0, B0 = w(sl)
    ell = look.starts("the shape D predicts")[0]
    pe, Be = w(ell)
    Binv = np.linalg.inv(Be)
    dye = np.array([w(n)[0] for n in look.starts("dye molecule ")])
    inside = np.mean(np.linalg.norm((dye - pe) @ Binv.T, axis=1) <= 1)
    lam_d, vec_d = gen.eig_sorted(D[gen.DEMO_VOX])
    cloud = (dye - pe) @ B0
    lam_c, vec_c = np.linalg.eigh(np.cov(cloud.T))
    tilt = np.degrees(np.arccos(abs(vec_c[:, -1] @ vec_d[:, 0])))
    # The tracks step along the local long axis.
    worst_dir = 0.0
    for seed, head, name in gen.SEEDS:
        pts, why = gen.streamline(D, seed, head)
        for a, b in zip(pts[:-1], pts[1:]):
            e = gen.eig_sorted(gen.interp(D, *a))[1][:, 0][:2]
            d = (b - a) / np.linalg.norm(b - a)
            worst_dir = max(worst_dir, 1 - abs(d @ e) / np.linalg.norm(e))
    names = {name: gen.streamline(D, seed, head)[1] for seed, head, name in gen.SEEDS}
    eng.reset()
    assert worst_shape < 2e-3 and worst_col <= 1, (worst_shape, worst_col)
    assert 0.6 <= inside <= 0.9 and tilt < 15, (inside, tilt)
    assert worst_dir < 1e-9
    assert "edge" in names["arch, outer"] and "edge" in names["arch, inner"]
    assert "leave" in names["through-slice bundle"] and "round" in names["fluid pocket"]
    print(f"  every voxel's ellipsoid is D (B B^T = k^2 D, worst {worst_shape:.1e}); colours = "
          f"the DTI direction code; {inside:.0%} of the dye inside the drawn 2-sigma ellipsoid "
          f"(Gaussian: 74%); cloud long axis {tilt:.1f} deg from D's")
    print(f"  every track step is along the local long axis; arches reach the edge, the "
          f"through-slice and fluid seeds stop at once")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", choices=("vectors", "tensor", "book", "crystal", "metric", "stress", "field", "all"),
                    default="all")
    args = ap.parse_args()
    check_conventions()
    if args.scene in ("vectors", "all"):
        check_vectors()
    if args.scene in ("tensor", "all"):
        check_tensor()
    if args.scene in ("book", "all"):
        check_book()
    if args.scene in ("crystal", "all"):
        check_crystal()
    if args.scene in ("metric", "all"):
        check_metric()
    if args.scene in ("stress", "all"):
        check_stress()
    if args.scene in ("field", "all"):
        check_field()
    print("all checks passed")


if __name__ == "__main__":
    main()
