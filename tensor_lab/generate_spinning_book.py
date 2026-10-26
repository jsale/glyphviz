"""
Scene 3 -- The Spinning Book: the inertia tensor at work.

Three identical books float in free space. Each is spun at the same rate
about one of its three principal axes, with the same 1% nudge off it:

    book 1   long axis   (smallest moment, I1)   spins steadily
    book 2   middle axis (intermediate, I2)      flips over, again and again
    book 3   thin axis   (largest moment, I3)    spins steadily

That is the tennis-racket theorem (the Dzhanibekov effect), and it is the
inertia tensor's doing. Angular momentum is L = I w with I a rank-2 tensor
-- Scene 2's machine -- so L and w point the same way only along a principal
axis. With no torque L is fixed in the room (gold arrow); w (white) wanders.

Under each book, its numbers in the ROOM's basis: the nine components of I
swing (twice per turn, Scene 2's rank-2 signature), the three of w swing,
and the three of L = I w never move. In the BOOK's own basis I is diagonal
and constant -- the same tensor, two bases.

On the right, L as the book sees it (body frame). It must stay on a sphere
(|L| is fixed) and on an energy surface, so it rides the curves where the
two meet: small loops around e1 and e3 (stable), and the separatrix through
e2, which carries book 2 from +e2 to -e2 and back -- each crossing is a flip.

    python generate_spinning_book.py [--out DIR]
"""
import argparse
import os

import numpy as np

import rigid_body as rb
import tensor_kit as kit

HERE = os.path.dirname(os.path.abspath(__file__))

FRAMES = 1800
DT = 1 / 30                    # physics time = playback time at 30 fps
W0 = 2 * np.pi / 3.0           # one turn every 3 s
EPS = 0.01                     # the nudge, as a fraction of W0
I = rb.I_BODY
SB = 2.0                       # world units per metre of book
ARROW = 5.5                    # the L arrow's length
W_DRAW = 0.72 * ARROW          # w is drawn W_DRAW * |w| / W0 long, so the tips part
ELL_K = 3.8                    # inertia-ellipsoid semi-axes = ELL_K * I_i
LIFT = 7.0
BOOK_Y = (-20.0, -8.0, 4.0)    # turn-frame positions (screen right)
SPHERE_Y, RS = 17.5, 4.5
BOARD_AT = (0.0, -26.0, 15.0)
BG = (10, 12, 22)

BOOK_COLORS = ((100, 210, 255), (255, 90, 170), (150, 230, 90))
BOOK_NAMES = ("long axis, smallest I", "middle axis", "thin axis, largest I")
VERDICT = ("steady", "flips, again and again", "steady")
PAGES = (236, 228, 205)
PANEL_Y = -24.0
UI, UW, UL = 1.6, 1.2, 1.2     # board units per kg m^2, per W0, per |L|


def runs():
    """For each book: (R (F, 3, 3) body -> room, w body (F, 3))."""
    out = []
    for k in range(3):
        w = np.full(3, EPS * W0)
        w[k] = W0
        R0 = kit.rot_z(25.0) @ rb.align_to_z(I * w)   # L straight up; a quarter-ish turn for the view
        out.append(rb.integrate(R0, w, DT, FRAMES - 1))
    return out


def book(sc, frame, k, Rs, ws):
    """The book on its own stage frame: body, axes, ellipsoid, arrows."""
    col = BOOK_COLORS[k]
    tag = f"book {k + 1}"
    body = sc.node(frame, rot=kit.euler_xyz(Rs[0]), hide=1, geometry=kit.GEO_POINT,
                   ch=kit.rot_channel(sc, Rs),
                   text=f"{tag}'s body frame: turned by R(t), so its local axes are e1, e2, e3")
    h = rb.H * SB
    sc.node(body, scale=h / kit.CUBE_FACE, color=(*PAGES, 255), geometry=kit.GEO_CUBE,
            text=f"{tag}: pages ({2 * rb.H[0]:g} x {2 * rb.H[1]:g} x {2 * rb.H[2]:g} m, mass 1)")
    cov = np.array([h[0] * 1.02, h[1] * 1.03, 0.03])
    sc.node(body, pos=(0, 0, h[2] + 0.03), scale=cov / kit.CUBE_FACE, color=(*col, 255),
            geometry=kit.GEO_CUBE, text=f"{tag}: front cover (+e3 side)")
    sc.node(body, pos=(0, 0, -h[2] - 0.03), scale=cov / kit.CUBE_FACE, color=(70, 72, 90, 255),
            geometry=kit.GEO_CUBE, text=f"{tag}: back cover (-e3 side)")
    sc.node(body, pos=(h[0] * 0.62, 0, h[2] + 0.07), scale=np.array([0.25, h[1] * 0.8, 0.02])
            / kit.CUBE_FACE, color=(255, 255, 255, 255), geometry=kit.GEO_CUBE,
            text=f"{tag}: title stripe (marks the +e1 end of the front cover)")
    for i in range(3):
        e = np.zeros(3)
        e[i] = max(1.3 * h[i], 1.0)
        a = sc.node(body, pos=-e, hide=1, geometry=kit.GEO_POINT, text=f"{tag}: -e{i + 1} end")
        b = sc.node(body, pos=e, scale=0.09, color=(*kit.E_RGB[i], 255),
                    text=f"{tag}: body axis e{i + 1} (I{i + 1} = {I[i]:.3f} kg m^2)")
        kit.rod(sc, a, b, (*kit.E_RGB[i], 255), f"{tag}: body axis e{i + 1}", radius=0.045)
    sc.node(body, scale=ELL_K * I, color=(*col, 70), geometry=kit.GEO_SPHERE_WIRE,
            text=f"{tag}'s inertia tensor as Scene 2 draws it: semi-axes "
                 f"{I[0]:.2f}, {I[1]:.2f}, {I[2]:.2f} (fattest about the thin axis)")
    # Arrows in the room frame.
    Lr = np.einsum("fij,fj->fi", Rs, I * ws)
    wr = np.einsum("fij,fj->fi", Rs, ws)
    Lhat = Lr / np.linalg.norm(Lr, axis=1, keepdims=True)
    kit.arrow(sc, frame, np.zeros(3), Lhat[0] * ARROW, (*kit.GOLD, 255), "L",
              radius=0.09, head=0.8, show_text=1)
    kit.arrow(sc, frame, np.zeros(3), wr * W_DRAW / W0, (*kit.WHITE, 255), "w",
              radius=0.07, head=0.65, show_text=1)
    return Lr, wr


def panel(sc, bd, k, cx, Rs, ws, Lr, wr):
    col = BOOK_COLORS[k]
    F = FRAMES
    kit.caption(sc, bd, (cx - 5.0, PANEL_Y + 3.6), f"Book {k + 1}: {BOOK_NAMES[k]}", color=col,
                size=0.05)
    kit.caption(sc, bd, (cx - 5.0, PANEL_Y + 2.8), VERDICT[k], color=col, size=0.03)
    # I in the room's basis: R I_body R^T.
    Ir = np.einsum("fik,k,fjk->fij", Rs, I, Rs)
    kit.caption(sc, bd, (cx - 5.0, PANEL_Y + 1.8), "I (room basis)",
                color=(190, 190, 210), size=0.03)
    for i in range(3):
        y = PANEL_Y - i * 1.9
        kit.hline(sc, bd, cx - 5.0, cx - 1.4, y, (110, 110, 130),
                  f"book {k + 1}: I grid zero line, row {i + 1}", ratio=0.01)
        for j in range(3):
            vals = Ir[:, i, j]
            kit.signed_bar(sc, bd, cx - 4.4 + 1.2 * j, y, vals, kit.WARM,
                           f"book {k + 1}: I_{'xyz'[i]}{'xyz'[j]} in the room's basis",
                           unit=UI, width=0.55 if i == j else 0.4,
                           colors=kit.sign_colors(vals))
    for i, name in enumerate("xyz"):
        kit.caption(sc, bd, (cx - 1.25, PANEL_Y - i * 1.9 + 0.05), name, color=(150, 150, 175),
                    size=0.02)
    # w and L in the room's basis.
    base = PANEL_Y - 2.4
    kit.hline(sc, bd, cx - 0.2, cx + 4.6, base, (110, 110, 130),
              f"book {k + 1}: w and L zero line", ratio=0.01)
    Lmag = np.linalg.norm(Lr[0])
    for i in range(3):
        kit.signed_bar(sc, bd, cx + 0.3 + 0.6 * i, base, wr[:, i] / W0, kit.E_RGB[i],
                       f"book {k + 1}: w_{'xyz'[i]} (room), in units of the spin rate",
                       unit=UW * 1.5, width=0.4)
        kit.signed_bar(sc, bd, cx + 2.6 + 0.6 * i, base, Lr[:, i] / Lmag, kit.E_RGB[i],
                       f"book {k + 1}: L_{'xyz'[i]} (room), in units of |L|: never moves",
                       unit=UL * 1.5, width=0.4)
    kit.caption(sc, bd, (cx + 0.1, base + 2.2), "w", color=kit.WHITE, size=0.03)
    kit.caption(sc, bd, (cx + 2.4, base + 2.2), "L = I w", color=kit.GOLD, size=0.03)
    # The angle between w and L.
    cosang = np.einsum("fi,fi->f", wr, Lr) / (np.linalg.norm(wr, axis=1) * np.linalg.norm(Lr, axis=1))
    ang = np.degrees(np.arccos(np.clip(cosang, -1, 1)))
    gy = PANEL_Y - 6.0
    unit = 5.4 / 90.0
    kit.hline(sc, bd, cx - 5.0, cx + 0.4, gy, (110, 110, 130),
              f"book {k + 1}: angle gauge, 0 to 90 deg", ratio=0.01)
    L = unit * ang
    s = 0.25 / (2 * kit.CUBE_FACE)
    on = L > 1e-6
    ch = sc.channel([(sc.track(cx - 5.0 + L / 2), "translate_x"),
                     (sc.track(np.where(on, L / (2 * kit.CUBE_FACE), 0.0)), "scale_x"),
                     (sc.track(np.where(on, s, 0.0)), "scale_y"),
                     (sc.track(np.where(on, s, 0.0)), "scale_z")])
    sc.node(bd, pos=(cx - 5.0 + L[0] / 2, gy, 0.0),
            scale=(L[0] / (2 * kit.CUBE_FACE), s, s) if on[0] else 0.0, color=(*col, 255),
            geometry=kit.GEO_CUBE, ch=ch,
            text=f"book {k + 1}: angle between w and L right now (0 = lined up)")
    kit.caption(sc, bd, (cx - 5.0, gy + 0.7), "angle(w, L), 0-90 deg",
                color=(170, 175, 200), size=0.02)
    return ang


def l_sphere(sc, turn, bd, rs):
    frame = kit.stage(sc, turn, (0.0, SPHERE_Y, 0.0), "L-sphere frame")
    sc.node(frame, scale=RS, color=(150, 155, 185, 60), geometry=kit.GEO_SPHERE_WIRE,
            text="the sphere |L| = constant, in the book's own basis (body frame)")
    for i in range(3):
        e = np.zeros(3)
        e[i] = RS * 1.25
        kit.polyline(sc, frame, [-e, e], (*kit.E_RGB[i], 200), f"body axis e{i + 1}",
                     ratio=0.03)
        for sgn in (1, -1):
            stable = i != 1
            sc.node(frame, pos=sgn * e / 1.25, scale=0.16,
                    color=(*kit.E_RGB[i], 255),
                    show_text=1 if sgn > 0 else 0,
                    text=f"{'+' if sgn > 0 else '-'}e{i + 1}: "
                         + ("stable spin" if stable else "unstable spin"))
    # Polhodes: loops around +/-e1 and +/-e3, started on the L2 = 0 circle.
    for deg in (15, 30, 45, 58, 73, 80, 86):
        a = np.radians(deg)
        p = rb.polhode([np.cos(a), 0.0, np.sin(a)])
        around = "e1" if deg < 67 else "e3"
        for sgn in (1, -1):
            pts = sgn * p[::4] * RS
            kit.polyline(sc, frame, pts, (175, 180, 210, 130),
                         f"polhode around {'+' if sgn > 0 else '-'}{around}: one energy level",
                         ratio=0.02)
    for m, n in enumerate(rb.separatrix_normals()):
        u = np.array([0.0, 1.0, 0.0])
        v = np.cross(n, u)
        t = np.radians(np.arange(0, 361, 3))
        pts = RS * (np.outer(np.cos(t), u) + np.outer(np.sin(t), v))
        kit.polyline(sc, frame, pts, (255, 120, 120, 220),
                     f"separatrix {m + 1}: the energy of a pure e2 spin; it divides the loops",
                     ratio=0.035)
    for k, (Rs, ws) in enumerate(rs):
        Lb = I * ws
        Lb = Lb / np.linalg.norm(Lb, axis=1, keepdims=True) * RS * 1.01
        col = BOOK_COLORS[k]
        kit.marker(sc, frame, Lb[0], (*col, 255), f"book {k + 1}: L as the book sees it",
                   scale=0.22, ch=kit.pos_channel(sc, Lb))
        f_on = np.arange(0, FRAMES, 2)
        kit.reveal(sc, frame, Lb[f_on], (*col, 230), f"book {k + 1}: where L has been (body frame)",
                   f_on, FRAMES, ratio=0.05, seg=8)
    kit.caption(sc, bd, (SPHERE_Y + 26.0 - 4.5, PANEL_Y + 1.2), "L as the book sees it",
                color=(190, 190, 210), size=0.05)
    kit.caption(sc, bd, (SPHERE_Y + 26.0 - 4.5, PANEL_Y + 0.4), "(body frame: I is diagonal here)",
                color=(170, 175, 200), size=0.03)


def build(out_dir):
    sc = kit.Scene(FRAMES)
    rs = runs()
    turn, wall = kit.frames_of_reference(sc, BG, LIFT)
    bd = kit.board(sc, wall, BOARD_AT)

    kit.caption(sc, bd, (0, 0), "THE SPINNING BOOK: the inertia tensor at work",
                color=(255, 225, 120), size=0.09)
    for j, line in enumerate((
            "Three identical books in free space, spun at the same rate about each principal axis, "
            "each with the same 1% nudge.",
            "Gold = L, the angular momentum: no torque, so it never moves. White = w, the angular "
            "velocity. L = I w, and I is a tensor",
            "(Scene 2's machine), so L and w line up only along a principal axis. Long and thin axes: "
            "steady. Middle axis: it flips (tennis-racket theorem).",
            "Under each book, its numbers in the ROOM's basis: I swings twice per turn (rank 2), w "
            "swings, and their product L = I w never moves.",
            "Right: L as the BOOK sees it. It must stay on the sphere |L| = const AND on an energy "
            "surface, so it rides the curves where they meet:",
            "loops around e1 and e3 (stable), and the red separatrix through e2, which carries book 2 "
            "from +e2 to -e2 and back. Every crossing is a flip.")):
        kit.caption(sc, bd, (0.4, -1.1 - 1.0 * j), line)

    angs = []
    for k, (Rs, ws) in enumerate(rs):
        frame = kit.stage(sc, turn, (0.0, BOOK_Y[k], 0.0), f"book {k + 1} room frame")
        for i, name in enumerate("xyz"):
            a = np.zeros(3)
            a[i] = 4.0
            kit.polyline(sc, frame, [-a, a], (*kit.GREY, 70),
                         f"book {k + 1}: room {name} axis (the basis of the numbers below)",
                         ratio=0.015)
        Lr, wr = book(sc, frame, k, Rs, ws)
        angs.append(panel(sc, bd, k, BOOK_Y[k] + 26.0, Rs, ws, Lr, wr))
    l_sphere(sc, turn, bd, rs)

    stem = "Spinning_Book"
    sc.write(out_dir, stem)
    for k, (Rs, ws) in enumerate(rs):
        ax = Rs[:, 2, k]
        flips = int(np.sum(np.diff(np.sign(ax)) != 0))
        print(f"book {k + 1}: max angle(w, L) {angs[k].max():5.1f} deg, axis flips {flips}")
    print(f"{len(sc.rows)} nodes, {len(sc.tracks)} tracks, {FRAMES} frames -> {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=os.path.join(HERE, "Spinning_Book"))
    build(ap.parse_args().out)
