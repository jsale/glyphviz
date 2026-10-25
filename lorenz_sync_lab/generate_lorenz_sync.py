"""
Two coupled Lorenz systems falling into synchrony, drawn in GlyphViz.

A demonstration of the Hyperdimensional Coordinate System (HCS), on the
subject of Yan Wu's AMS talk "Synchronizability between two coupled Lorenz
systems". The
coupled pair lives in a 6-D phase space (x1, y1, z1, x2, y2, z2); perfect
synchronization is the 3-D slice x1 = x2, y1 = y2, z1 = z2. The scene shows
that slice attracting the trajectory -- or failing to -- for five control
designs, one per row, all starting from the same 6-D initial condition:

    row 0  weak x-coupling k = 2            locks in 0.5% of starts
    row 1  x-coupling  k = 10               100%, and the locked motion stays chaotic
    row 2  z-coupling  k = 20               25% -- and no better at k = 2, 5 or 50
    row 3  weak x (k = 2) + z (k = 20)      56%: z helps once x is there
    row 4  weak x (k = 2) + y-feedback g=1  85%, but the feedback kills the chaos

Those rates come from ensemble_lorenz_sync.py (200 independent starts). One
run per row cannot carry a rate -- a single 0.001 shift of the switch-on time
flips the z row -- so T_ON was chosen (pick_switch_time.py) so that each row's
run shows its controller's typical outcome, and the captions carry the rate.

Every row runs uncoupled until T_ON, so the first stretch is identical across
rows: two systems started a hair apart diverge exponentially. At T_ON each
row's controller switches on.

Columns, left to right:

    Lorenz space   both systems' beads with fading comet tails, and the error
                   vector e = state1 - state2 as a cone pointing from system 2
                   to system 1. Locking = the cone shrinks to nothing.
    HCS tori       one per variable pair. A torus IS a two-dimension HCS
                   (Springer compactification, theta = 180 (v/s) / (1 + |v/s|)):
                   major angle = x1, tube angle = x2. The synchronization
                   manifold x1 = x2 is the diagonal theta_major = theta_tube,
                   drawn as a white loop through the (0, 0) and (inf, inf)
                   points. Unsynchronized motion smears across the torus;
                   locked motion rides the diagonal.
    6-D HCS        the whole state as ONE hyperglyph: six nested HCS circles
                   in the order x1 x2 y1 y2 z1 z2 (so each consecutive pair is
                   that pair's torus), built as a node chain driven by six
                   rotate_z channels. A ghost leaf marks the nearest
                   synchronized state; a cone joins it to the real leaf.
                   Locked = the leaf rides the ghost. See hyper_glyph().
    Lyapunov V     log10 of V = |e|^2 / 2 over the whole run, coloured by the
                   same error ramp as the torus trails, with a moving cursor.

Coupling forms (bidirectional, diffusive):
    x-coupling:   x1' += k (x2 - x1),   x2' += k (x1 - x2)
    z-coupling:   z1' += k (z2 - z1),   z2' += k (z1 - z2)
    y-feedback:   yi' -= g yi on each system's own y equation (decentralized:
                  each controller sees only its own state). This form is an
                  ASSUMPTION -- the abstract does not give it.

Usage:
    python generate_lorenz_sync.py [--out DIR]
Writes Lorenz_Sync_gv_node.csv + _gv_ch-map.csv + _gv_ch-tracks.csv into DIR
(default: ./Lorenz_Sync beside this script).
"""
import argparse
import csv
import math
import os

import numpy as np

# --------------------------------------------------------------------------
# Dynamics
# --------------------------------------------------------------------------

SIGMA, BETA, RHO = 10.0, 8.0 / 3.0, 28.0
Z_CENTER = RHO - 1.0          # the attractor's z centre; HCS wants values about 0

DT = 0.001                    # RK4 step
SUBSTEPS = 10                 # integration steps per animation frame
FRAME_DT = DT * SUBSTEPS      # 0.01 Lorenz time units per frame
T_ON = 5.8                    # controllers switch on here (see pick_switch_time.py)
T_END = 24.0
FRAMES = int(round(T_END / FRAME_DT))
F_ON = int(round(T_ON / FRAME_DT))
DELTA = np.array([0.05, -0.05, 0.05])   # "a hair apart"

MECHANISMS = [
    dict(key="xweak", title="weak x-coupling  k = 2", kx=2.0, kz=0.0, g=0.0,
         color=(150, 150, 165),
         verdict="locks in 0.5% of starts"),
    dict(key="x", title="x-coupling  k = 10", kx=10.0, kz=0.0, g=0.0,
         color=(90, 225, 120),
         verdict="locks in 100% of starts, still chaotic"),
    dict(key="z", title="z-coupling  k = 20", kx=0.0, kz=20.0, g=0.0,
         color=(230, 95, 210),
         verdict="locks in only 25% of starts, at any k (this run: no)"),
    dict(key="xz", title="weak x (k = 2) + z (k = 20)", kx=2.0, kz=20.0, g=0.0,
         color=(120, 160, 255),
         verdict="locks in 56% of starts (weak x alone: 0.5%)"),
    dict(key="xy", title="weak x (k = 2) + y-feedback (g = 1)", kx=2.0, kz=0.0, g=1.0,
         color=(250, 200, 60),
         verdict="locks in 85% of starts, but the chaos dies"),
]


def rhs(s, kx, kz, g):
    x1, y1, z1, x2, y2, z2 = s
    return np.array([
        SIGMA * (y1 - x1) + kx * (x2 - x1),
        RHO * x1 - y1 - x1 * z1 - g * y1,
        x1 * y1 - BETA * z1 + kz * (z2 - z1),
        SIGMA * (y2 - x2) + kx * (x1 - x2),
        RHO * x2 - y2 - x2 * z2 - g * y2,
        x2 * y2 - BETA * z2 + kz * (z1 - z2),
    ])


def integrate_steps(s, steps, kx=0.0, kz=0.0, g=0.0):
    """States after each of `steps` RK4 steps of DT, shape (steps, 6)."""
    out = np.empty((steps, 6))
    for i in range(steps):
        k1 = rhs(s, kx, kz, g)
        k2 = rhs(s + DT / 2 * k1, kx, kz, g)
        k3 = rhs(s + DT / 2 * k2, kx, kz, g)
        k4 = rhs(s + DT * k3, kx, kz, g)
        s = s + DT / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        out[i] = s
    return out


def integrate(s, frames, kx=0.0, kz=0.0, g=0.0):
    """States at the END of each of `frames` frames, shape (frames, 6)."""
    return integrate_steps(s, frames * SUBSTEPS, kx, kz, g)[SUBSTEPS - 1::SUBSTEPS]


def simulate():
    """(initial 6-D state, {mechanism key: (FRAMES * SUBSTEPS, 6) states}).

    Fine-grained: row j is the state at time j * DT, so frame f is row
    f * SUBSTEPS. The trails need the in-between states (see trail()); the
    animation reads every SUBSTEPS-th row."""
    # Burn in onto the attractor so frame 0 already looks like Lorenz.
    s = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    s = integrate(s, 3000)[-1]
    s0 = np.concatenate([s[:3], s[:3] + DELTA])
    n_on = F_ON * SUBSTEPS
    shared = np.vstack([s0, integrate_steps(s0, n_on)])   # rows 0 .. n_on, t = 0 .. T_ON
    runs = {}
    for m in MECHANISMS:
        # Controllers act from exactly T_ON (row n_on) onward.
        tail = integrate_steps(shared[-1], FRAMES * SUBSTEPS - n_on - 1,
                               m["kx"], m["kz"], m["g"])
        runs[m["key"]] = np.vstack([shared, tail])
    return s0, runs


def reference_attractor(n=1500, every=2):
    """System 1 alone on the plain Lorenz attractor -- the faint ghost curve."""
    s = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    s = integrate(s, 3000)[-1]
    return integrate(s, n * every)[::every, :3]


# --------------------------------------------------------------------------
# HCS mapping (hyperdims/src/hcs/mapping.ts, valueToAngle)
# --------------------------------------------------------------------------

def hcs_angle(v, s):
    u = np.asarray(v, dtype=float) / s
    return 180.0 * u / (1.0 + np.abs(u))


def hcs_scales(ref):
    """Per-pair HCS scale: the median magnitude lands at 90 deg (hyperdims'
    auto-scale). One scale per PAIR, so x1 and x2 share it and the diagonal
    means equality."""
    centered = ref - np.array([0.0, 0.0, Z_CENTER])
    return np.median(np.abs(centered), axis=0)


# --------------------------------------------------------------------------
# Layout (wall-local: +X toward the viewer, +Y screen right, +Z up)
# --------------------------------------------------------------------------

ROW_PITCH = 7.0
WALL_LIFT = 35.0              # world z of the wall's origin: keeps it all above the ground grid
PHASE_SCALE = 0.1             # Lorenz units -> world
PHASE_Y = 3.5
TORUS_Y = (9.0, 12.8, 16.6)
TORUS_SIZE = 1.55             # torus glyph scale
TORUS_RATIO = 0.38
TORUS_TILT = 48.0             # rotate_y of each torus frame: axis 42 deg off the wall normal, so both tube faces read
TRAIL_LIFT = 0.025            # trail rides just above the tube surface
HYPER_Y = 21.4                # the 6-D hyperglyph's column
HYPER_R1 = 1.0                # radius of dimension 1's circle
HYPER_MAX_STEP = 0.1           # 6-D trails: longest chord. The leaf is fast, so this sets most of the playback cost
HYPER_RATIO = 0.7             # each nested circle's radius / its parent's (hyperdims' slider; its default 0.4 leaves dim 6 at 1%)
V_Y0, V_Y1 = 25.4, 31.4
V_LOG_MIN, V_LOG_MAX = -10.0, 3.0
V_HALF = 2.2

TRAIL_STEP = 2                # one trail vertex every 2 frames
SEG = 10                      # vertices per trail segment (each its own Plot parent)
# A comet is two consecutive copies of its path: a bright thick head that
# hands over to a dim thin tail, so no stretch is drawn twice.
# (from age, to age in frames, vertex alpha, Plot ratio = width / 20 px)
BANDS = ((0, 40, 255, 0.13), (40, 160, 105, 0.07))

BG = (10, 12, 22)
SYS1 = (255, 145, 45)
SYS2 = (70, 200, 255)
ARROW = (255, 240, 130)
GHOST = (120, 130, 160, 45)
DIAG = (235, 235, 255, 150)
INF = (255, 90, 90, 130)
LATTICE = (110, 125, 175, 55)
LATTICE_ZERO = (165, 175, 215, 120)
# hyperdims' dimension-circle colours (the ANTz convention): R, G, B, C, M, Y
DIM_COLORS = ((255, 34, 34), (34, 204, 34), (51, 102, 255), (0, 204, 204), (204, 0, 204), (204, 204, 0))
SYNC_GHOST = (215, 215, 255)       # the nearest synchronized state, in the 6-D glyph

PAIR_NAMES = ("x", "y", "z")

GEO_SPHERE, GEO_CONE, GEO_TORUS, GEO_POINT, GEO_CIRCLE = 3, 5, 7, 22, 24
TOPO_NONE, TOPO_PLOT = 0, 16


def row_z(r):
    return -ROW_PITCH * r


def phase_pos(p, r):
    """Lorenz point -> wall-local. Lorenz x -> right, z -> up, y -> away from
    the viewer (a proper rotation, so the butterfly is not mirrored)."""
    x, y, z = p[..., 0], p[..., 1], p[..., 2]
    return np.stack([-PHASE_SCALE * y,
                     PHASE_Y + PHASE_SCALE * x,
                     row_z(r) + PHASE_SCALE * (z - Z_CENTER)], axis=-1)


def torus_point(th1, th2, lift=TRAIL_LIFT):
    """(theta_major, theta_tube) in degrees -> the torus frame's local coords.
    Same formula as glyphviz_core.topology._torus_offset, i.e. exactly where a
    Torus-topology child at translate (th1, th2, lift / TORUS_SIZE) would sit
    (the engine reads a Torus child's translate_z in the parent's units)."""
    major = TORUS_SIZE * (1.0 - TORUS_RATIO)
    tube = TORUS_SIZE * TORUS_RATIO + lift
    u, v = np.radians(th1), np.radians(th2)
    radial = major + tube * np.cos(v)
    return np.stack([radial * np.cos(u), radial * np.sin(u), tube * np.sin(v)], axis=-1)


def hcs_chain(angles):
    """Leaf of the nested-circle HCS for rows of angles (deg), shape (N, D) ->
    (N, 3) in the hyperglyph frame's local coords. A vectorized port of
    hyperdims/src/hcs/geometry.ts leafPosition: circle 1 lies in the frame's
    XY plane; circle k+1 is centred on circle k's chosen point, in the plane
    of circle k's outward radial N and its normal w (the torus cross-section),
    radius scaled by HYPER_RATIO. Base frame u=X, v=Y, w=Z -- hyperdims' own
    base frame up to a rigid rotation."""
    n = len(angles)
    c = np.zeros((n, 3))
    u = np.tile([1.0, 0.0, 0.0], (n, 1))
    v = np.tile([0.0, 1.0, 0.0], (n, 1))
    w = np.tile([0.0, 0.0, 1.0], (n, 1))
    radius = HYPER_R1
    for d in range(angles.shape[1]):
        t = np.radians(angles[:, d])[:, None]
        radial = np.cos(t) * u + np.sin(t) * v
        point = c + radius * radial
        if d == angles.shape[1] - 1:
            return point
        c, u, v, w = point, radial, w, np.cross(radial, w)
        radius *= HYPER_RATIO


def six_d_angles(states, scales):
    """(N, 6) Lorenz pair states -> (N, 6) HCS angles in hyperglyph order
    x1, x2, y1, y2, z1, z2: consecutive dimensions are a pair, so each pair of
    nested circles is the same torus as that pair's 2-D glyph."""
    cols = []
    for j in range(3):
        off = Z_CENTER if j == 2 else 0.0
        cols += [hcs_angle(states[:, j] - off, scales[j]),
                 hcs_angle(states[:, 3 + j] - off, scales[j])]
    return np.stack(cols, axis=1)


def v_pos(f, logv, r):
    y = V_Y0 + (V_Y1 - V_Y0) * f / (FRAMES - 1)
    t = (np.clip(logv, V_LOG_MIN, V_LOG_MAX) - V_LOG_MIN) / (V_LOG_MAX - V_LOG_MIN)
    return y, row_z(r) - V_HALF + 2 * V_HALF * t


def error_color(err):
    """Teal when locked, yellow mid-way, red when far apart (log10 |error|)."""
    u = (np.clip(np.log10(max(err, 1e-12)), -4.0, 1.5) + 4.0) / 5.5
    stops = [(70, 220, 190), (250, 215, 80), (255, 75, 60)]
    if u < 0.5:
        a, b, w = stops[0], stops[1], u / 0.5
    else:
        a, b, w = stops[1], stops[2], (u - 0.5) / 0.5
    return tuple(int(round(a[i] + (b[i] - a[i]) * w)) for i in range(3))


# --------------------------------------------------------------------------
# Scene assembly
# --------------------------------------------------------------------------

NODE_COLS = ["id", "type", "parent_id", "branch_level",
             "translate_x", "translate_y", "translate_z",
             "rotate_x", "rotate_y", "rotate_z",
             "scale_x", "scale_y", "scale_z",
             "color_r", "color_g", "color_b", "color_a",
             "geometry", "hide", "topo", "ratio",
             "child_id", "ch_input_id", "show_text", "rotation_mode", "text"]


def num(v):
    """Compact float: 4 dp, trailing zeros trimmed, never '-0'."""
    s = f"{float(v):.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


class Scene:
    def __init__(self):
        self.rows = []
        self.level = {0: -1}
        self.tracks = []          # list of numpy arrays, track id = index + 1
        self.chmap = []           # (channel_id, track_id, attribute)
        self.next_ch = 1

    def node(self, parent=0, *, type=5, pos=(0, 0, 0), rot=(0, 0, 0), scale=1.0,
             color=(255, 255, 255, 255), geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE,
             ratio=0.1, child_id=0, ch=0, show_text=0, text=""):
        nid = len(self.rows) + 1
        lvl = self.level[parent] + 1
        self.level[nid] = lvl
        sc = scale if isinstance(scale, (tuple, list)) else (scale,) * 3
        c = tuple(color) + (255,) * (4 - len(color))
        self.rows.append([nid, type, parent, lvl, *pos, *rot, *sc, *c, geometry, hide,
                          topo, ratio, child_id, ch, show_text, 0, text])
        return nid

    def track(self, values):
        self.tracks.append(np.asarray(values, dtype=float))
        return len(self.tracks)

    def channel(self, bindings):
        """bindings: [(track_id, attribute), ...] -> new channel id."""
        ch = self.next_ch
        self.next_ch += 1
        for tid, attr in bindings:
            self.chmap.append((ch, tid, attr))
        return ch

    def write(self, out_dir, stem):
        os.makedirs(out_dir, exist_ok=True)
        # Companions first, node CSV last (Watch-and-Reload safe).
        with open(os.path.join(out_dir, f"{stem}_gv_ch-map.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(["channel_id", "track_id", "attribute"])
            w.writerows(self.chmap)
        cols = [[num(v) if not float(v).is_integer() else str(int(v)) for v in t]
                for t in self.tracks]
        with open(os.path.join(out_dir, f"{stem}_gv_ch-tracks.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            fh.write(",".join(["cyclecount"] + [f"ch{i + 1}" for i in range(len(cols))]) + "\r\n")
            for f in range(FRAMES):
                fh.write(str(f) + "," + ",".join(c[f] for c in cols) + "\r\n")
        with open(os.path.join(out_dir, f"{stem}_gv_node.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(NODE_COLS)
            for row in self.rows:
                w.writerow([num(v) if isinstance(v, float) else v for v in row])


N_VERTS = FRAMES // TRAIL_STEP
N_SEGS = (N_VERTS - 1 + SEG - 1) // SEG


def seg_span(k):
    """First and last vertex index of trail segment k (consecutive segments
    share their boundary vertex, so the polyline is unbroken)."""
    return k * SEG, min((k + 1) * SEG, N_VERTS - 1)


def build_segment_channels(sc):
    """One hide channel per (band, segment index), shared by every trail in
    the scene. Binding a whole segment rather than each vertex is what keeps
    playback cheap: ChannelEngine.apply_frame costs ~0.5 us per binding, and
    per-vertex alpha+hide on 25 trails was 60k bindings = 28 ms a frame.
    A segment is live in a band while its first vertex's age is inside the
    band's range -- except that the head band lights it only once the bead has
    passed its midpoint, so the line never runs ahead of the bead.
    -> [band][segment] = channel id"""
    f = np.arange(FRAMES)
    out = []
    for age0, age1, _alpha, _ratio in BANDS:
        chans = []
        for k in range(N_SEGS):
            i0, i1 = seg_span(k)
            start = i0 * TRAIL_STEP
            on = max(start + age0, (i0 + i1) * TRAIL_STEP // 2)
            live = (f >= on) & (f < start + age1)
            chans.append(sc.channel([(sc.track(np.where(live, 0, 1)), "hide")]))
        out.append(chans)
    return out


def densify(fine, j0, j1, max_step):
    """Fine-row indices strictly between j0 and j1, spaced so no chord of the
    polyline is longer than max_step. A straight chord between two samples
    cuts through the inside of a torus (and off the diagonal it is meant to
    ride), so fast stretches get the TRUE in-between states, not a lerp."""
    seg = fine[j0:j1 + 1]
    length = np.linalg.norm(np.diff(seg, axis=0), axis=1).sum()
    n = int(math.ceil(length / max_step)) - 1
    if n <= 0:
        return []
    return sorted(set(int(round(j)) for j in np.linspace(j0, j1, n + 2)[1:-1]) - {j0, j1})


def trail(sc, parent, fine, colors, seg_channels, label, max_step):
    """A comet: a hidden carrier holding, per band, one Plot parent per
    segment. Each segment parent is a transparent Point whose `hide` is
    channel-bound (a hidden Plot parent suppresses its polyline, which is the
    switch); its vertices are static, zero-scale, and carry the band alpha.
    `fine` is the path at integrator resolution (row j = time j * DT).

    Segments and vertices carry NO text, deliberately. The tag pass walks every
    node that has text on every paint, labels shown or not; with all ~230k
    vertices labelled it cost 150 ms a frame (6 fps). Zero-scale vertices can't
    be clicked anyway -- the label lives on the carrier and the moving bead."""
    holder = sc.node(parent, hide=1, geometry=GEO_POINT, text=label)
    extra = {}
    for (_age0, _age1, alpha, ratio), chans in zip(BANDS, seg_channels):
        for k, ch in enumerate(chans):
            i0, i1 = seg_span(k)
            seg = sc.node(holder, geometry=GEO_POINT, topo=TOPO_PLOT, ratio=ratio,
                          color=(255, 255, 255, 0), hide=1, ch=ch)
            for i in range(i0, i1 + 1):
                b = i * TRAIL_STEP
                c = colors[b] if not isinstance(colors, tuple) else colors
                j0 = b * SUBSTEPS
                sc.node(seg, pos=tuple(float(v) for v in fine[j0]), scale=0.0,
                        color=(*c[:3], alpha))
                if i == i1:
                    continue
                j1 = (b + TRAIL_STEP) * SUBSTEPS
                if j0 not in extra:
                    extra[j0] = densify(fine, j0, j1, max_step)
                for j in extra[j0]:
                    sc.node(seg, pos=tuple(float(v) for v in fine[j]), scale=0.0,
                            color=(*c[:3], alpha))
    return holder


def static_plot(sc, parent, pts, color, label, ratio=0.06, colors=None):
    """A fixed polyline. The label goes on the parent only (see trail())."""
    plot = sc.node(parent, geometry=GEO_POINT, topo=TOPO_PLOT, ratio=ratio,
                   color=(255, 255, 255, 0), text=label)
    for i, p in enumerate(pts):
        c = colors[i] if colors is not None else color
        sc.node(plot, pos=tuple(float(v) for v in p), scale=0.0, color=c)
    return plot


def pos_channel(sc, xyz):
    """A channel driving translate_x/y/z from an (FRAMES, 3) array."""
    return sc.channel([(sc.track(xyz[:, i]), a)
                       for i, a in enumerate(("translate_x", "translate_y", "translate_z"))])


DIM_NAMES = ("x1", "x2", "y1", "y2", "z1", "z2")


def hyper_glyph(sc, wall, r, m, fine, scales, err, segs):
    """The whole 6-D state as ONE hyperglyph: six nested HCS circles.

    A real node chain, so GlyphViz itself carries the nesting. Per dimension d:
      level_d  hidden frame; circle d is its unit circle (local XY plane).
               Level 0 sits on the hyperglyph frame at scale HYPER_R1; every
               later level sits at (1, 0, 0) of the previous spinner -- the
               chosen point -- with rotate_x = 90 and scale HYPER_RATIO.
      spin_d   hidden, channel-driven rotate_z = HCS angle of dimension d.
    Rz(theta) then Rx(90) is exactly hyperdims' childFrame (u' = N, v' = w),
    so the leaf lands on hcs_chain()'s point -- verify_lorenz_sync.py checks
    that against a literal port of geometry.ts, through the engine.

    The order x1 x2 y1 y2 z1 z2 makes circles 1-2 the x torus, 3-4 the y torus,
    5-6 the z torus. Synchronization has no single "diagonal" in 6-D, so the
    glyph also carries a GHOST leaf -- the nearest synchronized state, both
    systems at their mean -- and a cone from ghost to leaf: the 6-D error made
    visible as a distance in the HCS. Locking = leaf and ghost merge."""
    z0 = row_z(r)
    st = fine[::SUBSTEPS]
    ang = six_d_angles(st, scales)
    mean = 0.5 * (fine[:, :3] + fine[:, 3:])
    ghost_fine = hcs_chain(six_d_angles(np.hstack([mean, mean]), scales))
    leaf_fine = hcs_chain(six_d_angles(fine, scales))

    outer = sc.node(wall, pos=(0, HYPER_Y, z0), rot=(0, TORUS_TILT, 0), hide=1,
                    geometry=GEO_POINT, text="6-D hyperglyph frame (tilt)")
    frame = sc.node(outer, rot=(0, 0, 90), hide=1, geometry=GEO_POINT,
                    text=f"6-D hyperglyph frame (0 deg at screen right)  [{m['title']}]")
    circle = [(math.cos(a), math.sin(a), 0.0) for a in np.radians(np.linspace(-180.0, 180.0, 61))]
    parent, radius, leaf = frame, HYPER_R1, 0
    for d, name in enumerate(DIM_NAMES):
        level = sc.node(parent, pos=(1.0, 0.0, 0.0) if d else (0.0, 0.0, 0.0),
                        rot=(90.0, 0.0, 0.0) if d else (0.0, 0.0, 0.0),
                        scale=HYPER_RATIO if d else HYPER_R1, hide=1, geometry=GEO_POINT,
                        text=f"dimension {d + 1} ({name}) circle frame")
        static_plot(sc, level, circle, (*DIM_COLORS[d], 200),
                    f"dimension {d + 1}: {name}  (HCS circle; s = {scales[d // 2]:.2f} "
                    "lands at 90 deg)", ratio=0.035)
        tick = 0.03 / radius                      # world size / this level's scale
        sc.node(level, pos=(1.0, 0.0, 0.0), scale=tick, color=(255, 255, 255, 200),
                text=f"{name} = 0")
        sc.node(level, pos=(-1.0, 0.0, 0.0), scale=tick, color=(*INF[:3], 230),
                text=f"{name} = +/- infinity")
        spin = sc.node(level, rot=(0.0, 0.0, float(ang[0, d])), hide=1, geometry=GEO_POINT,
                       ch=sc.channel([(sc.track(ang[:, d]), "rotate_z")]),
                       text=f"{name} spinner: rotate_z = the HCS angle of {name}")
        if d == len(DIM_NAMES) - 1:
            leaf = sc.node(spin, pos=(1.0, 0.0, 0.0), scale=0.075 / radius,
                           color=(255, 255, 255, 255),
                           text=f"6-D leaf: the coupled state (x1, x2, y1, y2, z1, z2)  "
                                f"[{m['title']}]")
        else:
            sc.node(spin, pos=(1.0, 0.0, 0.0), scale=0.04 / radius,
                    color=(*DIM_COLORS[d], 255),
                    text=f"{name} now -- the centre of the {DIM_NAMES[d + 1]} circle")
        parent, radius = spin, radius * HYPER_RATIO

    ghost = sc.node(frame, pos=tuple(ghost_fine[0]), scale=0.06, color=(*SYNC_GHOST, 170),
                    ch=pos_channel(sc, ghost_fine[::SUBSTEPS]),
                    text="nearest synchronized state: both systems at their mean, "
                         "doubled into 6-D")
    sc.node(ghost, type=7, geometry=GEO_CONE, ratio=0.035, color=(*ARROW, 230), child_id=leaf,
            text="6-D error, seen in the HCS: nearest synchronized state -> actual state")
    trail(sc, frame, leaf_fine, [error_color(e) for e in err], segs,
          f"6-D leaf trail, coloured by |e|  [{m['title']}]", max_step=HYPER_MAX_STEP)
    trail(sc, frame, ghost_fine, SYNC_GHOST, segs,
          f"nearest-synchronized-state trail: the sync manifold's path in 6-D  [{m['title']}]",
          max_step=HYPER_MAX_STEP)


def build(out_dir):
    s0, runs = simulate()
    ref = reference_attractor()
    scales = hcs_scales(ref)
    sc = Scene()
    sc.node(0, type=0, color=(*BG, 255), geometry=GEO_POINT, hide=1,
            text="World - background")
    # Lifted so the whole wall stands above the app's ground grid (z = 0),
    # which would otherwise slice through the top rows.
    turn = sc.node(0, pos=(0, 0, WALL_LIFT), rot=(0, 0, 45), hide=1, geometry=GEO_POINT,
                   text="wall frame - turned to the default camera's azimuth (45)")
    wall = sc.node(turn, rot=(0, -25, 0), hide=1, geometry=GEO_POINT,
                   text="wall - leaned back to the default camera's elevation (25)")
    segs = build_segment_channels(sc)
    t = np.arange(FRAMES) * FRAME_DT

    # Column headers above the top row. Labels are a fixed pixel size and
    # draw to the RIGHT of their anchor, so each header must fit inside its
    # column at the opening zoom (~25 px per unit); the prose is in the legend.
    top = 4.5
    hdr = dict(scale=0.1, geometry=GEO_CIRCLE, color=(200, 200, 220), show_text=1)
    sc.node(wall, pos=(0, PHASE_Y - 3.2, top), **hdr, text="Lorenz space")
    for j, name in enumerate(PAIR_NAMES):
        sc.node(wall, pos=(0, TORUS_Y[j] - 1.1, top), **hdr,
                text=f"{name}1 : {name}2")
    sc.node(wall, pos=(0, HYPER_Y - 1.6, top), **hdr, text="6-D HCS")
    sc.node(wall, pos=(0, V_Y0, top), **hdr, text="log10 V")
    bottom = row_z(len(MECHANISMS) - 1) - 3.6
    for i, txt in enumerate((
            "orange = system 1, cyan = system 2, yellow cone = error e = state1 - state2."
            f"  All rows run uncoupled until t = {T_ON:g}, then their controller switches on.",
            "HCS torus: around the ring = system 1, around the tube = system 2,"
            f"  theta = 180 (v/s) / (1 + |v/s|).  z is shown as z - {int(Z_CENTER)}.",
            "white loop = synchronization manifold v1 = v2.  red loops = +/- infinity."
            "  Bright circles = 0;  faint ones every 45 deg (90 deg = +/- s).",
            "6-D hyperglyph: six nested HCS circles, R G B C M Y = x1 x2 y1 y2 z1 z2; the white leaf is the 6-D state.",
            "White ghost = nearest synchronized state (both systems at their mean); the cone from it to the leaf is the error.",
            "trail + V colour: red = far apart, yellow = closing, teal = locked.   V = |e|^2 / 2, the Lyapunov function.")):
        sc.node(wall, pos=(0, PHASE_Y - 2.4, bottom - 1.1 * i), **hdr, text=txt)

    switch_on = (t >= T_ON).astype(float)
    for r, m in enumerate(MECHANISMS):
        fine = runs[m["key"]]
        st = fine[::SUBSTEPS]
        s1, s2 = st[:, :3], st[:, 3:]
        e = s1 - s2
        err = np.linalg.norm(e, axis=1)
        logv = np.log10(np.maximum(0.5 * err ** 2, 1e-30))
        z0 = row_z(r)

        # Row title + coupling switch light: grey until T_ON, then the mechanism colour.
        grey = np.array([90, 90, 100])
        on_col = np.array(m["color"])
        rgb = grey[None, :] + (on_col - grey)[None, :] * switch_on[:, None]
        sw = sc.channel([(sc.track(rgb[:, i]), a)
                         for i, a in enumerate(("color_r", "color_g", "color_b"))])
        sc.node(wall, pos=(0, 0.6, z0 + 3.1), scale=0.2, color=(*grey, 255), ch=sw,
                show_text=1,
                text=f"{m['title']}  (on at t = {T_ON:g}): {m['verdict']}")

        # ---- Lorenz space ----
        static_plot(sc, wall, phase_pos(ref, r), GHOST,
                    "the Lorenz attractor (sigma=10, b=8/3, r=28), for reference")
        p1, p2 = phase_pos(s1, r), phase_pos(s2, r)
        b1 = sc.node(wall, pos=tuple(p1[0]), scale=0.085, color=(*SYS1, 255),
                     ch=pos_channel(sc, p1),
                     text=f"system 1 now  [{m['title']}]")
        b2 = sc.node(wall, pos=tuple(p2[0]), scale=0.13, color=(*SYS2, 150),
                     ch=pos_channel(sc, p2),
                     text=f"system 2 now  [{m['title']}]  (the halo: when it "
                          "surrounds the orange bead, the systems are locked)")
        sc.node(b2, type=7, geometry=GEO_CONE, ratio=0.05, color=(*ARROW, 230),
                child_id=b1, text="error vector e = state1 - state2 (points at system 1)")
        for k, (col, name) in enumerate(((SYS1, "system 1"), (SYS2, "system 2"))):
            trail(sc, wall, phase_pos(fine[:, 3 * k:3 * k + 3], r), col, segs,
                  f"{name} trail (last {BANDS[-1][1] * FRAME_DT:g} time units)  [{m['title']}]",
                  max_step=0.12)

        # ---- HCS tori, one per variable pair ----
        for j, name in enumerate(PAIR_NAMES):
            off = Z_CENTER if name == "z" else 0.0
            v1, v2 = s1[:, j] - off, s2[:, j] - off
            th1, th2 = hcs_angle(v1, scales[j]), hcs_angle(v2, scales[j])
            pair_err = np.abs(v1 - v2)
            lbl = f"{name}-{int(Z_CENTER)}" if off else name
            outer = sc.node(wall, pos=(0, TORUS_Y[j], z0), rot=(0, TORUS_TILT, 0), hide=1,
                            geometry=GEO_POINT, text=f"{lbl} torus frame (tilt)")
            frame = sc.node(outer, rot=(0, 0, 90), hide=1, geometry=GEO_POINT,
                            text=f"{lbl} torus frame (0 deg at screen right)")
            # The torus is drawn as HCS guide circles, not a surface: a solid
            # torus (even translucent) writes depth and hides every trail on
            # its far side, which is half the diagonal.
            s_j = scales[j]
            ring = np.linspace(-180.0, 180.0, 49)
            for th in (-135, -90, -45, 0, 45, 90, 135, 180):
                val = ("+/- infinity" if th == 180 else
                       f"{np.sign(th) * s_j * abs(th) / (180 - abs(th)):+.2f}" if th else "0")
                static_plot(sc, frame, torus_point(np.full_like(ring, float(th)), ring, 0.0),
                            INF if th == 180 else LATTICE_ZERO if th == 0 else LATTICE,
                            f"{lbl}1 = {val}  (HCS angle {th} deg)",
                            ratio=0.04 if th in (0, 180) else 0.025)
            for th in (-90, 0, 90, 180):
                val = ("+/- infinity" if th == 180 else
                       f"{np.sign(th) * s_j:+.2f}" if th else "0")
                static_plot(sc, frame, torus_point(ring, np.full_like(ring, float(th)), 0.0),
                            INF if th == 180 else LATTICE_ZERO if th == 0 else LATTICE,
                            f"{lbl}2 = {val}  (HCS angle {th} deg)",
                            ratio=0.04 if th in (0, 180) else 0.025)
            diag = np.linspace(-179.0, 179.0, 181)
            static_plot(sc, frame, torus_point(diag, diag, 0.012), DIAG,
                        f"synchronization manifold {lbl}1 = {lbl}2 (the diagonal); "
                        f"HCS scale s = {s_j:.2f} lands at 90 deg", ratio=0.05)
            sc.node(frame, pos=tuple(torus_point(0.0, 0.0, 0.02)), scale=0.05,
                    color=(255, 255, 255, 255), text=f"{lbl}1 = {lbl}2 = 0")
            pts = torus_point(th1, th2)
            fine_pts = torus_point(hcs_angle(fine[:, j] - off, scales[j]),
                                   hcs_angle(fine[:, 3 + j] - off, scales[j]))
            cols = [error_color(pair_err[b]) for b in range(FRAMES)]
            trail(sc, frame, fine_pts, cols, segs,
                  f"{lbl} pair on its HCS torus, coloured by |{lbl}1 - {lbl}2|  [{m['title']}]",
                  max_step=0.12)
            sc.node(frame, pos=tuple(pts[0]), scale=0.06, color=(255, 255, 255, 255),
                    ch=pos_channel(sc, pts),
                    text=f"{lbl} pair now: one point = ({lbl}1, {lbl}2)")

        # ---- 6-D HCS hyperglyph ----
        hyper_glyph(sc, wall, r, m, fine, scales, err, segs)

        # ---- Lyapunov V(t) ----
        idx = np.arange(0, FRAMES, TRAIL_STEP)
        vy, vz = v_pos(idx, logv[idx], r)
        static_plot(sc, wall, [(0.0, a, b) for a, b in zip(vy, vz)], None,
                    f"log10 V over the run [{m['title']}]", ratio=0.1,
                    colors=[(*error_color(err[i]), 255) for i in idx])
        zero_y, zero_z = v_pos(np.array([0, FRAMES - 1]), np.array([0.0, 0.0]), r)
        static_plot(sc, wall, [(0.0, zero_y[0], zero_z[0]), (0.0, zero_y[1], zero_z[1])],
                    (110, 110, 130, 140), "V = 1 (log10 V = 0)", ratio=0.03)
        on_y, _ = v_pos(np.array([F_ON]), np.array([0.0]), r)
        static_plot(sc, wall, [(0.0, on_y[0], z0 - V_HALF), (0.0, on_y[0], z0 + V_HALF)],
                    (*m["color"], 160), f"controller switches on, t = {T_ON:g}", ratio=0.03)
        cy, cz = v_pos(np.arange(FRAMES), logv, r)
        cur = np.stack([np.full(FRAMES, 0.05), cy, cz], axis=1)
        sc.node(wall, pos=tuple(cur[0]), scale=0.09, color=(255, 255, 255, 255),
                ch=pos_channel(sc, cur), text=f"now  [{m['title']}]")

    stem = "Lorenz_Sync"
    sc.write(out_dir, stem)
    print(f"6-D initial condition (x1,y1,z1,x2,y2,z2) = {np.round(s0, 4).tolist()}")
    print(f"HCS scales (x, y, z-{int(Z_CENTER)}) = {np.round(scales, 3).tolist()}")
    for m in MECHANISMS:
        st = runs[m["key"]][::SUBSTEPS]
        err = np.linalg.norm(st[:, :3] - st[:, 3:], axis=1)
        far = np.where(err >= 0.1)[0]
        lock = (far[-1] + 1) * FRAME_DT if len(far) and far[-1] + 1 < FRAMES else None
        flips = int(np.sum(np.diff(np.sign(st[F_ON:, 0])) != 0))
        print(f"  {m['key']:5s} |e| at t_on = {err[F_ON]:6.3g}   final |e| = {err[-1]:9.3g}"
              f"   |e| < 0.1 for good from t = {lock}   lobe switches after t_on = {flips}")
    print(f"{len(sc.rows)} nodes, {len(sc.tracks)} tracks, {sc.next_ch - 1} channels, "
          f"{FRAMES} frames -> {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   "Lorenz_Sync"))
    build(ap.parse_args().out)
