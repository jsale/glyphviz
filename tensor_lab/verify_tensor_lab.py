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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", choices=("vectors", "tensor", "book", "all"), default="all")
    args = ap.parse_args()
    check_conventions()
    if args.scene in ("vectors", "all"):
        check_vectors()
    if args.scene in ("tensor", "all"):
        check_tensor()
    if args.scene in ("book", "all"):
        check_book()
    print("all checks passed")


if __name__ == "__main__":
    main()
