"""
Transitions between balanced least-squares assignments (LSAs), drawn in GlyphViz.

An illustration for Borgwardt & Semyonov's AMS talk "An Iteration-Reducing
Approach for Transitions Between Least-Squares Assignments".

A balanced LSA assigns every data point to one of k sites so that each site
gets a prescribed number of points (its cluster size) and the total squared
point-to-site distance is as small as possible. Every such optimum is a POWER
DIAGRAM: there are weights w_j such that each point sits with the site that
minimises |x - s_j|^2 - w_j. The |x|^2 terms cancel between any two sites, so
every boundary is a straight line (a hyperplane in d dimensions) -- the
"separation property". Each panel draws the cells of that diagram.

The transition: four sites slide in a straight line from their start to their
target positions, s(t) = (1 - t) s0 + t s1, and the cluster sizes must change
from (18, 18, 18, 18) to the target sizes. Every intermediate state must
itself be a balanced LSA, so the clusters stay separated by straight lines the
whole way. A STEP is one change of assignment.

    left   SEQUENTIAL  slide the sites at the old sizes (each breakpoint forces
                       an exchange: a point leaves a cluster and another
                       arrives to keep the size fixed), then change the sizes
                       one unit at a time at the target sites.
    right  COMBINED    slide the sites, and at each breakpoint, when a cluster
                       that must shrink is about to hand a point to a cluster
                       that must grow, let that move count toward the size
                       change instead of forcing the return move.

The combined schedule is a RECONSTRUCTION of the abstract's idea ("combines
progress in the linear transition of sites with a desired change in cluster
sizes"), not the authors' algorithm, which the abstract does not give.
ensemble_lsa_transition.py measures it over 40 random cases (fewer steps in
38, the same in 2, never more; median 20% fewer); SEED is the case closest to
that median, so the scene does not oversell the effect.

Both panels share one clock, one step per STEP_FRAMES frames, so the panel
that needs fewer steps finishes first and waits.

Usage:
    python generate_lsa_transition.py [--out DIR] [--seed N]
Writes LSA_Transition_gv_node.csv + _gv_ch-map.csv + _gv_ch-tracks.csv into
DIR (default: ./LSA_Transition beside this script).
"""
import argparse
import csv
import os

import numpy as np
from scipy.optimize import linear_sum_assignment, linprog

# --------------------------------------------------------------------------
# Balanced least-squares assignments
# --------------------------------------------------------------------------

N_POINTS = 72
N_SITES = 4
SEED = 7                      # the 40-case ensemble's closest-to-median case (21 -> 17 steps)
DOMAIN = 10.0                 # data in [-DOMAIN, DOMAIN]^2
BOX = 10.5                    # the drawn cells are clipped to this square
SHIFT = 5.0                   # how far (per axis) a site may move


def problem(seed, n=N_POINTS, k=N_SITES):
    """Points, start/target sites, start/target sizes. Uniform points; the
    sites start one per quadrant (jittered) and each shifts by up to SHIFT
    per axis -- depots relocating, not scattering. Start sizes are equal,
    target sizes random but summing to n."""
    rng = np.random.default_rng(seed)
    X = rng.uniform(-DOMAIN, DOMAIN, size=(n, 2))
    quad = np.array([(-5.0, 5.0), (5.0, 5.0), (-5.0, -5.0), (5.0, -5.0)])[:k]
    S0 = quad + rng.uniform(-1.5, 1.5, size=(k, 2))
    S1 = np.clip(S0 + rng.uniform(-SHIFT, SHIFT, size=(k, 2)), -8.0, 8.0)
    k0 = round_sizes(np.full(k, n / k), n)
    w = rng.uniform(0.4, 1.6, size=k)
    k1 = round_sizes(w / w.sum() * n, n)
    return X, S0, S1, k0, k1


def round_sizes(v, n):
    """Largest-remainder rounding of real sizes v to integers summing to n.
    Snapped first: (1 - u) 21 + u 21 can come out 20.9999999, and that fuzz
    made the size vector flicker near a breakpoint -- which trace() then
    dutifully recorded as dozens of spurious steps."""
    v = np.round(v, 9)
    f = np.floor(v).astype(int)
    order = np.argsort(-(v - f), kind="stable")
    f[order[:n - f.sum()]] += 1
    return f


def lsa(X, S, sizes):
    """The optimal balanced assignment: point i -> site index. Exact, as a
    square assignment problem against each site's slots repeated sizes[j]
    times."""
    slot = np.repeat(np.arange(len(S)), sizes)
    d2 = ((X[:, None, :] - S[None, slot, :]) ** 2).sum(-1)
    r, c = linear_sum_assignment(d2)
    a = np.empty(len(X), int)
    a[r] = slot[c]
    return a


def sites_at(S0, S1, t):
    return (1.0 - t) * S0 + t * S1


def trace(state_at, ngrid=400):
    """Every distinct assignment along u in [0, 1], in order, as (u, A).
    A grid scan with bisection between differing neighbours, so breakpoints
    closer together than the grid are still separated."""
    seq = [(0.0, state_at(0.0))]

    def rec(ta, Aa, tb, Ab):
        if np.array_equal(Aa, Ab):
            return []
        if tb - ta < 1e-7:
            return [(tb, Ab)]
        tm = 0.5 * (ta + tb)
        Am = state_at(tm)
        return rec(ta, Aa, tm, Am) + rec(tm, Am, tb, Ab)

    prev = seq[0]
    for u in np.linspace(0, 1, ngrid + 1)[1:]:
        A = state_at(u)
        seq += rec(prev[0], prev[1], u, A)
        prev = (u, A)
    return seq


def next_break(X, S0, S1, k, t0, A0, h=1 / 400):
    """First t > t0 where LSA(s(t), k) differs from A0 -> (t, A) or None."""
    ta = t0
    while ta < 1.0:
        tb = min(1.0, ta + h)
        Ab = lsa(X, sites_at(S0, S1, tb), k)
        if not np.array_equal(Ab, A0):
            while tb - ta > 1e-7:
                tm = 0.5 * (ta + tb)
                Am = lsa(X, sites_at(S0, S1, tm), k)
                if np.array_equal(Am, A0):
                    ta = tm
                else:
                    tb, Ab = tm, Am
            return tb, Ab
        ta = tb
    return None


def resize_at_target(X, S1, k_from, k_to, t):
    """Change sizes k_from -> k_to with the sites parked at S1, one unit at a
    time (largest-remainder rounding of the straight line between them)."""
    n = len(X)
    seq = trace(lambda u: lsa(X, S1, round_sizes((1 - u) * k_from + u * k_to, n)))
    return [(t, A) for _u, A in seq]


def sequential(X, S0, S1, k0, k1):
    """Slide the sites at sizes k0, then resize at the target. -> [(t, A)]"""
    slide = trace(lambda t: lsa(X, sites_at(S0, S1, t), k0))
    return slide + resize_at_target(X, S1, k0, k1, 1.0)[1:]


def combined(X, S0, S1, k0, k1):
    """Slide the sites; at each breakpoint, try every one-unit size change
    from a cluster with surplus to one with a deficit and take it if it makes
    the step move fewer points than the forced exchange. Any size change left
    at t = 1 happens at the target sites. -> [(t, A)]"""
    k = k0.copy()
    t, A = 0.0, lsa(X, S0, k)
    seq = [(t, A)]
    while True:
        nb = next_break(X, S0, S1, k, t, A)
        if nb is None:
            break
        t, best = nb
        best_k, best_m = k, int((best != A).sum())
        for a in np.where(k > k1)[0]:
            for b in np.where(k < k1)[0]:
                kk = k.copy()
                kk[a] -= 1
                kk[b] += 1
                Ak = lsa(X, sites_at(S0, S1, t), kk)
                m = int((Ak != A).sum())
                if m < best_m:
                    best, best_k, best_m = Ak, kk, m
        A, k = best, best_k
        seq.append((t, A))
    return seq + resize_at_target(X, S1, k, k1, 1.0)[1:]


def point_moves(seq):
    return sum(int((a[1] != b[1]).sum()) for a, b in zip(seq, seq[1:]))


def power_weights(X, S, A):
    """Weights w making A a power diagram of sites S, chosen to put the
    boundaries as far from the points as possible (max-min distance). Returns
    (w, margin); margin >= 0 certifies A is an optimal balanced assignment
    for its own sizes (LP duality), and it is the clearance drawn on screen."""
    k = len(S)
    rows, rhs = [], []
    for j in range(k):
        P = X[A == j]
        if not len(P):
            continue
        dj = ((P - S[j]) ** 2).sum(1)
        for l in range(k):
            if l == j:
                continue
            c = (((P - S[l]) ** 2).sum(1) - dj).min()
            row = np.zeros(k + 1)
            row[l], row[j] = 1.0, -1.0
            row[k] = 2.0 * np.linalg.norm(S[l] - S[j])
            rows.append(row)
            rhs.append(c)
    eq = np.zeros((1, k + 1))
    eq[0, 0] = 1.0
    res = linprog(np.r_[np.zeros(k), -1.0], A_ub=np.array(rows), b_ub=np.array(rhs),
                  A_eq=eq, b_eq=[0.0], bounds=[(None, None)] * k + [(None, 5.0)],
                  method="highs")
    assert res.status == 0, res.message
    return res.x[:k], res.x[k]


def clip(poly, a, b):
    """Sutherland-Hodgman: keep the part of convex polygon poly with a.x <= b."""
    out = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        fp, fq = a @ p - b, a @ q - b
        if fp <= 0:
            out.append(p)
        if fp * fq < 0:
            out.append(p + (q - p) * (fp / (fp - fq)))
    return out


def power_cell(S, w, j, inset=0.0, box=BOX):
    """Site j's power cell, clipped to the box, every edge pulled in by
    `inset` (so neighbouring outlines don't overprint). Edge between j and l:
    2 x.(s_l - s_j) <= |s_l|^2 - |s_j|^2 - w_l + w_j."""
    poly = [np.array(p, float) for p in ((-box, -box), (box, -box), (box, box), (-box, box))]
    poly = [p * (box - inset) / box for p in poly]
    for l in range(len(S)):
        if l == j:
            continue
        a = 2.0 * (S[l] - S[j])
        b = S[l] @ S[l] - S[j] @ S[j] - w[l] + w[j]
        poly = clip(poly, a, b - inset * np.linalg.norm(a))
        if not poly:
            break
    return poly


# --------------------------------------------------------------------------
# Timeline
# --------------------------------------------------------------------------

INTRO = 40                    # frames holding the start state
STEP_FRAMES = 20              # frames per step
SWITCH = 12                   # within a step: sites glide for SWITCH frames, then the switch
OUTRO = 80

def schedule_frames(seq, frames):
    """Per frame: (t, assignment, steps done, step index of a switch in the
    last STEP_FRAMES - SWITCH frames or -1, frames since that switch)."""
    out = []
    n = len(seq) - 1
    for f in range(frames):
        g = f - INTRO
        if g < 0:
            out.append((seq[0][0], seq[0][1], 0, -1, 0))
            continue
        i, p = g // STEP_FRAMES + 1, g % STEP_FRAMES
        if i > n:
            out.append((seq[n][0], seq[n][1], n, -1, 0))
        elif p < SWITCH:
            t = seq[i - 1][0] + (seq[i][0] - seq[i - 1][0]) * (p + 1) / SWITCH
            out.append((t, seq[i - 1][1], i - 1, -1, 0))
        else:
            out.append((seq[i][0], seq[i][1], i, i, p - SWITCH))
    return out


# --------------------------------------------------------------------------
# Layout (wall-local: +X toward the viewer, +Y screen right, +Z up)
# --------------------------------------------------------------------------

WALL_LIFT = 16.0              # keeps the wall above the app's ground grid
SC = 0.5                      # data units -> world
PANEL_Y = (-6.8, 6.8)
TITLE_Z = 7.2
BAR_BASE_Z = -9.2
BAR_UNIT = 0.09               # world height per point of cluster size
BAR_W = 0.9
STEP_Z = -11.0
STEP_LEN = 10.0               # world length of the step ruler (the longer schedule fills it)
LEGEND_Z = -13.2

POINT_R = 0.17
PULSE_R = 0.36
SITE_R = 0.42
INSET = 0.13                  # world gap between neighbouring cell outlines
VERTS = 9                     # cell outline vertex budget (closed: last = first)

BG = (12, 14, 24)
FRAME_COL = (90, 95, 120, 160)
SITE_COLORS = ((255, 105, 90), (80, 170, 255), (120, 215, 105), (250, 195, 60))
SITE_NAMES = "ABCD"

GEO_CUBE, GEO_SPHERE, GEO_OCTA_WIRE, GEO_OCTA, GEO_POINT, GEO_CIRCLE = 1, 3, 10, 11, 22, 24
TOPO_NONE, TOPO_PLOT = 0, 16
CUBE_HALF = 0.57735           # a cube's face is 1/sqrt(3) out at scale 1


def wall_pos(panel, p):
    """Data point (2,) -> wall-local position inside a panel."""
    return (0.0, PANEL_Y[panel] + SC * p[0], SC * p[1])


# --------------------------------------------------------------------------
# Scene assembly
# --------------------------------------------------------------------------

NODE_COLS = ["id", "type", "parent_id", "branch_level",
             "translate_x", "translate_y", "translate_z",
             "rotate_x", "rotate_y", "rotate_z",
             "scale_x", "scale_y", "scale_z",
             "color_r", "color_g", "color_b", "color_a",
             "geometry", "hide", "topo", "ratio",
             "ch_input_id", "show_text", "rotation_mode", "text"]


def num(v):
    """Compact float: 4 dp, trailing zeros trimmed, never '-0'."""
    s = f"{float(v):.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


class Scene:
    def __init__(self, frames):
        self.frames = frames
        self.rows = []
        self.level = {0: -1}
        self.tracks = []          # formatted columns, track id = index + 1
        self.track_ids = {}       # formatted column -> track id (identical tracks shared)
        self.chmap = []           # (channel_id, track_id, attribute)
        self.next_ch = 1

    def node(self, parent=0, *, type=5, pos=(0, 0, 0), rot=(0, 0, 0), scale=1.0,
             color=(255, 255, 255, 255), geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE,
             ratio=0.1, ch=0, show_text=0, text=""):
        nid = len(self.rows) + 1
        self.level[nid] = self.level[parent] + 1
        sc = scale if isinstance(scale, (tuple, list)) else (scale,) * 3
        c = tuple(color) + (255,) * (4 - len(color))
        self.rows.append([nid, type, parent, self.level[nid], *pos, *rot, *sc, *c,
                          geometry, hide, topo, ratio, ch, show_text, 0, text])
        return nid

    def track(self, values):
        col = tuple(num(v) for v in values)
        assert len(col) == self.frames
        if col not in self.track_ids:
            self.tracks.append(col)
            self.track_ids[col] = len(self.tracks)
        return self.track_ids[col]

    def channel(self, bindings):
        """bindings: [(values, attribute), ...] -> new channel id."""
        ch = self.next_ch
        self.next_ch += 1
        for values, attr in bindings:
            self.chmap.append((ch, self.track(values), attr))
        return ch

    def write(self, out_dir, stem):
        os.makedirs(out_dir, exist_ok=True)
        # Companions first, node CSV last (Watch-and-Reload safe).
        with open(os.path.join(out_dir, f"{stem}_gv_ch-map.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(["channel_id", "track_id", "attribute"])
            w.writerows(self.chmap)
        with open(os.path.join(out_dir, f"{stem}_gv_ch-tracks.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            fh.write(",".join(["cyclecount"] + [f"ch{i + 1}" for i in range(len(self.tracks))])
                     + "\r\n")
            for f in range(self.frames):
                fh.write(str(f) + "," + ",".join(c[f] for c in self.tracks) + "\r\n")
        with open(os.path.join(out_dir, f"{stem}_gv_node.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(NODE_COLS)
            for row in self.rows:
                w.writerow([num(v) if isinstance(v, float) else v for v in row])


def line(sc, parent, pts, color, label, ratio=0.06):
    """A fixed polyline; zero-scale vertices, label on the parent only."""
    plot = sc.node(parent, geometry=GEO_POINT, topo=TOPO_PLOT, ratio=ratio,
                   color=(255, 255, 255, 0), text=label)
    for p in pts:
        sc.node(plot, pos=tuple(float(v) for v in p), scale=0.0, color=color)
    return plot


def caption(sc, parent, pos, text, show=1):
    return sc.node(parent, pos=pos, scale=0.06, geometry=GEO_CIRCLE,
                   color=(200, 200, 220), show_text=show, text=text)


def panel(sc, wall, pi, title, subtitle, X, S0, S1, k1, seq, frames, n_steps_max):
    """One panel: frame, points, sites, power cells, size bars, step bar."""
    y0 = PANEL_Y[pi]
    tl = schedule_frames(seq, frames)
    n_steps = len(seq) - 1
    moves = point_moves(seq)
    F = range(frames)

    # Per-frame state.
    S_f = np.array([sites_at(S0, S1, t) for t, *_ in tl])            # (F, k, 2)
    A_f = np.array([a for _t, a, *_ in tl])                           # (F, n)
    steps_f = np.array([s for *_, s, _i, _p in tl], float)
    margins = np.empty(frames)
    W_f = np.empty((frames, N_SITES))
    for f in F:
        W_f[f], margins[f] = power_weights(X, S_f[f], A_f[f])

    # Labels are a fixed pixel size and draw to the RIGHT of their anchor, so
    # everything pinned must fit inside its panel at the opening zoom (~23 px
    # per unit at 1600 px wide); longer prose lives in the legend and hovers.
    caption(sc, wall, (0, y0 - 5.3, TITLE_Z), title)
    caption(sc, wall, (0, y0 - 5.3, TITLE_Z - 0.75), subtitle)
    line(sc, wall, [wall_pos(pi, p) for p in ((-BOX, -BOX), (BOX, -BOX), (BOX, BOX),
                                              (-BOX, BOX), (-BOX, -BOX))],
         FRAME_COL, f"{title}: the data square", ratio=0.04)

    # Data points: colour = current cluster, pulse when reassigned.
    pts = sc.node(wall, hide=1, geometry=GEO_POINT, text=f"{title}: the {N_POINTS} data points")
    for i, x in enumerate(X):
        rgb = np.array([SITE_COLORS[a] for a in A_f[:, i]], float)
        r = np.full(frames, POINT_R)
        for f, (_t, _a, _s, sw, age) in enumerate(tl):
            if sw > 0 and seq[sw][1][i] != seq[sw - 1][1][i]:
                r[f] = PULSE_R - (PULSE_R - POINT_R) * age / (STEP_FRAMES - SWITCH)
        sc.node(pts, pos=wall_pos(pi, x), scale=POINT_R,
                color=(*SITE_COLORS[A_f[0, i]], 255),
                ch=sc.channel([(rgb[:, 0], "color_r"), (rgb[:, 1], "color_g"),
                               (rgb[:, 2], "color_b"), (r, "scale_x"), (r, "scale_y"),
                               (r, "scale_z")]),
                text=f"data point {i + 1} at ({x[0]:.2f}, {x[1]:.2f}); colour = the site "
                     "it is assigned to now; it swells when it is reassigned")

    # Sites, their straight paths, and their targets.
    for j in range(N_SITES):
        col, nm = SITE_COLORS[j], SITE_NAMES[j]
        line(sc, wall, [wall_pos(pi, S0[j]), wall_pos(pi, S1[j])], (*col, 90),
             f"site {nm}'s straight path, s(t) = (1 - t) s0 + t s1", ratio=0.05)
        sc.node(wall, pos=wall_pos(pi, S1[j]), scale=SITE_R, geometry=GEO_OCTA_WIRE,
                color=(*col, 200),
                text=f"site {nm} target; target cluster size {k1[j]}")
        yz = np.array([wall_pos(pi, s) for s in S_f[:, j]])
        sc.node(wall, pos=wall_pos(pi, S0[j]), scale=SITE_R, geometry=GEO_OCTA,
                color=(*col, 255),
                ch=sc.channel([(yz[:, 1], "translate_y"), (yz[:, 2], "translate_z")]),
                show_text=1, text=nm)

    # Power-diagram cells: one closed outline per site, edges straight.
    for j in range(N_SITES):
        col, nm = SITE_COLORS[j], SITE_NAMES[j]
        V = np.empty((frames, VERTS, 2))
        for f in F:
            poly = power_cell(S_f[f, :], W_f[f], j, inset=INSET / SC)
            assert 3 <= len(poly) < VERTS, (f, j, len(poly))
            poly = poly + [poly[0]] * (VERTS - len(poly))
            V[f] = poly
        plot = sc.node(wall, geometry=GEO_POINT, topo=TOPO_PLOT, ratio=0.09,
                       color=(255, 255, 255, 0),
                       text=f"site {nm}'s power-diagram cell. Its edges are where "
                            f"|x - s{nm}|^2 - w{nm} ties with a neighbour's: straight lines")
        for v in range(VERTS):
            yz = np.array([wall_pos(pi, p) for p in V[:, v]])
            sc.node(plot, pos=tuple(yz[0]), scale=0.0, color=(*col, 235),
                    ch=sc.channel([(yz[:, 1], "translate_y"), (yz[:, 2], "translate_z")]))

    # Cluster-size bars with target ticks.
    sizes_f = np.array([np.bincount(a, minlength=N_SITES) for a in A_f])
    caption(sc, wall, (0, y0 - 5.3, BAR_BASE_Z + 3.4), "cluster sizes (tick = target)", show=1)
    for j in range(N_SITES):
        col, nm = SITE_COLORS[j], SITE_NAMES[j]
        by = y0 - 3.0 + 2.0 * j
        h = sizes_f[:, j] * BAR_UNIT
        sc.node(wall, pos=(0, by, BAR_BASE_Z + h[0] / 2),
                scale=(0.1, BAR_W / (2 * CUBE_HALF), h[0] / (2 * CUBE_HALF)),
                geometry=GEO_CUBE, color=(*col, 255),
                ch=sc.channel([(BAR_BASE_Z + h / 2, "translate_z"),
                               (h / (2 * CUBE_HALF), "scale_z")]),
                text=f"site {nm} cluster size: {sizes_f[0, j]} at the start, "
                     f"{k1[j]} at the target")
        tz = BAR_BASE_Z + k1[j] * BAR_UNIT
        line(sc, wall, [(0.08, by - 0.7, tz), (0.08, by + 0.7, tz)], (255, 255, 255, 230),
             f"site {nm} target size {k1[j]}", ratio=0.08)
        caption(sc, wall, (0, by - 0.3, tz + 0.4), f"{k1[j]}")
        caption(sc, wall, (0, by - 0.2, BAR_BASE_Z - 0.55), nm)

    # Step counter: a bar that grows one unit per step.
    x0 = y0 - 5.0
    unit = STEP_LEN / n_steps_max
    line(sc, wall, [(0.0, x0, STEP_Z), (0.0, x0 + n_steps_max * unit, STEP_Z)],
         FRAME_COL, "step ruler", ratio=0.03)
    for s in range(0, n_steps_max + 1, 5):
        line(sc, wall, [(0.0, x0 + s * unit, STEP_Z - 0.25),
                        (0.0, x0 + s * unit, STEP_Z + 0.25)], FRAME_COL,
             f"step {s}", ratio=0.03)
    caption(sc, wall, (0, x0 - 0.2, STEP_Z + 0.75), "steps")
    L = steps_f * unit
    sc.node(wall, pos=(0.05, x0, STEP_Z), scale=0.0, geometry=GEO_CUBE,
            color=(235, 235, 245, 255),
            ch=sc.channel([(x0 + L / 2, "translate_y"),
                           (L / (2 * CUBE_HALF), "scale_y"),
                           (np.where(L > 0, 0.2 / (2 * CUBE_HALF), 0.0), "scale_z"),
                           (np.where(L > 0, 0.1, 0.0), "scale_x")]),
            text=f"steps so far ({title})")
    line(sc, wall, [(0.0, x0 + n_steps * unit, STEP_Z - 0.45),
                    (0.0, x0 + n_steps * unit, STEP_Z + 0.45)], (255, 255, 255, 230),
         f"finish: {n_steps} steps", ratio=0.06)
    caption(sc, wall, (0, x0 - 0.2, STEP_Z - 1.0), f"{n_steps} steps, {moves} point moves")
    return dict(steps=n_steps, moves=moves, min_margin=float(margins.min()),
                margins=margins, tl=tl)


def build(out_dir, seed=SEED):
    X, S0, S1, k0, k1 = problem(seed)
    seq_a = sequential(X, S0, S1, k0, k1)
    seq_b = combined(X, S0, S1, k0, k1)
    n_max = max(len(seq_a), len(seq_b)) - 1
    frames = INTRO + n_max * STEP_FRAMES + OUTRO
    sc = Scene(frames)
    sc.node(0, type=0, color=(*BG, 255), geometry=GEO_POINT, hide=1, text="World - background")
    turn = sc.node(0, pos=(0, 0, WALL_LIFT), rot=(0, 0, 45), hide=1, geometry=GEO_POINT,
                   text="wall frame - turned to the default camera's azimuth (45)")
    wall = sc.node(turn, rot=(0, -25, 0), hide=1, geometry=GEO_POINT,
                   text="wall - leaned back to the default camera's elevation (25)")

    phase1 = sum(1 for t, _ in seq_a[1:] if t < 1.0)
    a = panel(sc, wall, 0, "SEQUENTIAL", "slide at fixed sizes, then resize",
              X, S0, S1, k1, seq_a, frames, n_max)
    b = panel(sc, wall, 1, "COMBINED", "resize while the sites slide",
              X, S0, S1, k1, seq_b, frames, n_max)
    # Where the sequential schedule stops sliding and starts resizing.
    x0 = PANEL_Y[0] - 5.0
    line(sc, wall, [(0.0, x0 + phase1 * STEP_LEN / n_max, STEP_Z - 0.45),
                    (0.0, x0 + phase1 * STEP_LEN / n_max, STEP_Z + 0.45)], (250, 195, 60, 230),
         f"sequential: sites arrive after step {phase1}; the resizing steps follow",
         ratio=0.06)

    for i, txt in enumerate((
            f"{N_POINTS} points, {N_SITES} sites. Each site slides in a straight line from its start "
            "(solid) to its target (wire).",
            f"Every cluster starts at {k0[0]} points and must end at its target size (white tick).",
            "Every frame is a balanced least-squares assignment: its cells are a power diagram,",
            "|x - s|^2 - w, so every boundary is a straight line. Reassigned points swell.",
            "A step = one change of assignment. One step per tick in both panels, so the shorter "
            "transition finishes first.",
            "COMBINED is a reconstruction of the abstract's idea, not the authors' algorithm: when a "
            "shrinking cluster",
            "hands a point to a growing one, that move counts toward the size change instead of "
            "being undone by a return move.",
            "40 random cases: fewer steps in 38, never more, median 20% fewer. This is the "
            "median case.")):
        caption(sc, wall, (0, PANEL_Y[0] - 5.3, LEGEND_Z - 0.9 * i), txt)

    stem = "LSA_Transition"
    sc.write(out_dir, stem)
    print(f"seed {seed}: sizes {k0.tolist()} -> {k1.tolist()}")
    print(f"  sequential: {a['steps']} steps ({phase1} sliding + {a['steps'] - phase1} "
          f"resizing), {a['moves']} point moves, min margin {a['min_margin']:.2e}")
    print(f"  combined:   {b['steps']} steps, {b['moves']} point moves, "
          f"min margin {b['min_margin']:.2e}")
    print(f"{len(sc.rows)} nodes, {len(sc.tracks)} tracks, {sc.next_ch - 1} channels, "
          f"{frames} frames -> {out_dir}")
    return dict(X=X, S0=S0, S1=S1, k0=k0, k1=k1, seq_a=seq_a, seq_b=seq_b, a=a, b=b)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   "LSA_Transition"))
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    build(args.out, args.seed)
