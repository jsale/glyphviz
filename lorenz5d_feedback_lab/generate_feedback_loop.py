"""
Inside the Feedback Loop: the paper's Fig. 1 as a live graph, beside the whole
state drawn as one HCS hyperglyph, after Shen (2014).

Four rows, every one started from the paper's Y = 1:

    3DLM  r = 25     the trunk loop only (M2 <-> M3)           chaotic
    4DLM  r = 25     M5 added WITHOUT M6: half a branch        runs away to infinity
    5DLM  r = 25     the full loop (M3 <-> M5 <-> M6)          steady
    5DLM  r = 43.5   the full loop, heated harder               chaotic again

Left, the loop. Each mode is a tile of its spatial pattern, in order of
vertical wavenumber, so a DOWNSCALE transfer runs rightward along an arc
above the tiles and an UPSCALE one leftward along an arc below (Fig. 1's
downward and upward arrows). The arcs are the nonlinear terms of the model
(rX and sigma Y, the linear heat engine, join M1 and M2); the stub under each
tile is that mode's damping. A bead on every arc and stub is a live meter:
size = the term's magnitude, colour = what it does to the mode it feeds,
warm if it AMPLIFIES that mode (term and amplitude share a sign), cool if it
DAMPS it. The paper's negative feedback is the -XY1 bead turning cool. The
bar under each tile is the mode's amplitude, HCS-compressed (full length =
infinity, the tick = its steady value).

Right, the same run as a point in phase space: a nested-circle HCS
hyperglyph (Jeff Sale's Hyperdimensional Coordinate System; see hcs.py), one
circle per variable in the order X Y Z Y1 Z1, coarse to fine like the cascade
itself. Each variable is scaled by its critical value (the paper's
normalization), so a steady roll is every circle parked at a quarter turn
(+/-90 deg) and the ghost leaves mark those two steady states. A 3-D model is
visibly a glyph with two fewer circles.

The 4DLM row is where the HCS earns its keep. With no steady state to settle
on and no energy conservation, the 4DLM runs away: |state| passes 1,000 by
tau = 1.19 at r = 25 (converged in the time step). An ordinary plot cannot
draw that. On the HCS, infinity is the point at 180 deg of every circle, so
the leaf flies out to the red "all infinite" ghost. The run is held once
|state| passes ESCAPE: past that the integration is stiff and the numbers
mean nothing.

    python generate_feedback_loop.py [--out DIR]
"""
import argparse
import os

import numpy as np

import hcs
import scene_kit as kit
import shen_model as sm

HERE = os.path.dirname(os.path.abspath(__file__))

ROWS = (("3DLM", 25.0), ("4DLM", 25.0), ("5DLM", 25.0), ("5DLM", 43.5))
VERDICT = {("3DLM", 25.0): "the trunk loop only: chaotic",
           ("4DLM", 25.0): "M5 without M6, half a branch: runs away to infinity",
           ("5DLM", 25.0): "the full loop: steady",
           ("5DLM", 43.5): "the full loop, heated harder: chaotic again"}
T_END = 40.0
DT = 0.001
FRAME_DT = 0.025
SUB = int(round(FRAME_DT / DT))
FRAMES = int(round(T_END / FRAME_DT))
START = np.array([0.0, 1.0, 0.0, 0.0, 0.0])
ESCAPE = 1e4

# ---- modes: index into the state, the pattern, names ----
MODES = (("M1", 0, "X", "the roll"), ("M2", 1, "Y", "warm/cool sides"),
         ("M3", 2, "Z", "flattened profile"), ("M5", 3, "Y1", "finer sides"),
         ("M6", 4, "Z1", "finer profile"))
DIMS = {"3DLM": 3, "4DLM": 4, "5DLM": 5}
# hyperdims' dimension colours (the ANTz convention): R, G, B, C, M
DIM_COLORS = ((255, 34, 34), (34, 204, 34), (51, 102, 255), (0, 204, 204), (204, 0, 204))

# (label, source mode, target mode, term(state, r), models it exists in, above?)
TERMS = (
    ("rX: heating", 0, 1, lambda s, r: r * s[..., 0], "345", True),
    ("sigma Y", 1, 0, lambda s, r: sm.SIGMA * s[..., 1], "345", False),
    ("XY", 1, 2, lambda s, r: s[..., 0] * s[..., 1], "345", True),
    ("-XZ", 2, 1, lambda s, r: -s[..., 0] * s[..., 2], "345", False),
    ("XZ", 2, 3, lambda s, r: s[..., 0] * s[..., 2], "45", True),
    ("-XY1 (new)", 3, 2, lambda s, r: -s[..., 0] * s[..., 3], "45", False),
    ("2XY1", 3, 4, lambda s, r: 2 * s[..., 0] * s[..., 3], "5", True),
    ("-2XZ1", 4, 3, lambda s, r: -2 * s[..., 0] * s[..., 4], "5", False),
)
DAMPING = (("-sigma X", lambda s: -sm.SIGMA * s[..., 0]), ("-Y", lambda s: -s[..., 1]),
           ("-bZ", lambda s: -sm.B * s[..., 2]), ("-d Y1", lambda s: -sm.D_O * s[..., 3]),
           ("-4bZ1", lambda s: -4 * sm.B * s[..., 4]))

# ---- layout, board units (x right, y up, z toward the viewer) ----
ROW_PITCH = 4.4
MODE_X = (0.8, 3.4, 6.0, 8.6, 11.2)
TILE_W = 1.6
TILE_H = TILE_W / sm.WIDTH
ARC_H = 0.95                     # arc apex above / below the tile centre line
BAR_Y, BAR_HALF = -0.48, 0.75
SINK_Y = -1.85                   # below the upscale arcs' labels
HG_X, HG_R1, HG_RATIO = 16.6, 1.45, 0.62
HG_ROT = (20.0, 35.0, 0.0)       # the glyph frame turned so nested circles are not edge-on
LIFT = 30.0
BOARD_SCALE = 1.8
BOARD_CENTRE = (9.0, -7.2)

BG = (10, 12, 22)
ROW_COLOR = {"3DLM": (255, 145, 45), "4DLM": (240, 80, 80), "5DLM": (70, 200, 255)}
AMPLIFY, DAMP, NEUTRAL = (255, 150, 60), (90, 160, 255), (150, 150, 165)
ARC = (170, 180, 215)
INF = (255, 80, 80)
STOPS = [(-1.0, (80, 160, 255)), (-0.4, (45, 85, 170)), (0.0, (48, 50, 62)),
         (0.4, (175, 70, 40)), (1.0, (255, 140, 60))]
GREY_STOPS = [(-1.0, (95, 97, 110)), (0.0, (40, 42, 52)), (1.0, (95, 97, 110))]


def row_y(k):
    return -k * ROW_PITCH


def simulate(model, r):
    """Fine path from the paper's start, (FRAMES * SUB + 1, 5); a run that
    passes ESCAPE is held there. -> (path, escape step or None)."""
    n = FRAMES * SUB
    out = np.empty((n + 1, 5))
    s = START.copy()
    out[0] = s
    for i in range(n):
        s = sm.rk4_step(s, DT, r, model)
        out[i + 1] = s
        if np.abs(s).max() > ESCAPE:
            out[i + 1:] = s
            return out, i + 1
    return out, None


def scales(model, r):
    """Each variable's HCS scale: the magnitude of its critical value. The
    4DLM has none, so it borrows the 5DLM's at the same r."""
    c = np.abs(sm.critical_point(r, "5DLM" if model == "4DLM" else model))
    return np.where(c > 0, c, 1.0)


def angles(states, model, r):
    d = DIMS[model]
    return hcs.angle(states[:, :d], scales(model, r)[:d])


# --------------------------------------------------------------------------
# The loop graph
# --------------------------------------------------------------------------

def arc_points(x0, x1, y0, apex, n=24):
    """Quadratic Bezier from (x0, y0) to (x1, y0) peaking at y0 + apex."""
    t = np.linspace(0, 1, n)[:, None]
    p0, p2 = np.array([x0, y0]), np.array([x1, y0])
    p1 = np.array([0.5 * (x0 + x1), y0 + 2 * apex])
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2


def meter(sc, parent, pos, values, target, vmax, label):
    """A bead whose size is |term| and whose colour says amplify / damp."""
    mag = np.clip(np.abs(values) / vmax, 0.0, 1.0)
    size = 0.05 + 0.2 * np.sqrt(mag)
    effect = np.sign(values) * np.sign(target)
    rgb = np.array([AMPLIFY if e > 0 else DAMP if e < 0 else NEUTRAL for e in effect])
    ch = sc.channel([(sc.track(size), "scale_x"), (sc.track(size), "scale_y"),
                     (sc.track(size), "scale_z")]
                    + [(sc.track(rgb[:, c]), a) for c, a in
                       enumerate(("color_r", "color_g", "color_b"))])
    return sc.node(parent, pos=pos, scale=float(size[0]), color=(*rgb[0], 255), ch=ch,
                   text=label)


def mode_tile(sc, bd, k, mi, present, model):
    name, idx, var, what = MODES[mi]
    x, y0 = MODE_X[mi], row_y(k)
    tag = f"{var} ({name})" if present else f"{var} (absent)"
    tile = sc.node(bd, pos=(x - TILE_W / 2, y0 - TILE_H / 2, 0.0), geometry=kit.GEO_POINT,
                   topo=kit.TOPO_SURFACE, ratio=0.05,
                   text=f"mode {name}, amplitude {var}: {what}" +
                        ("" if present else f" (not in the {model})"))
    xs = [round(i * sm.WIDTH / 16, 9) for i in range(17)]
    zs = [round(j / 8, 9) for j in range(9)]
    s = TILE_W / sm.WIDTH
    for z in zs:
        for xx in xs:
            v = sm.modes(xx, z)[mi] / np.sqrt(2.0) * (1.0 if mi != 2 and mi != 4 else -1.0)
            col = kit.lerp_color(STOPS if present else GREY_STOPS, v)
            sc.node(tile, pos=(xx * s, z * s, 0.0), scale=0.0, geometry=kit.GEO_CUBE,
                    color=(*col, 255), text=f"{name} pattern at x = {xx:.2f} H, z = {z:.2f} H")
    sc.node(bd, pos=(x - TILE_W / 2, y0 + TILE_H / 2 + 0.17, 0.05), scale=0.04,
            geometry=kit.GEO_CIRCLE, color=(*(DIM_COLORS[mi] if present else NEUTRAL), 255),
            show_text=1, text=tag)


def amplitude_bar(sc, bd, k, mi, theta, label):
    """Signed bar, length BAR_HALF * theta / 180 (theta = the HCS angle)."""
    x, y = MODE_X[mi], row_y(k) + BAR_Y
    L = BAR_HALF * theta / 180.0
    h = 0.07
    sx = np.abs(L) / (2 * kit.CUBE_FACE)
    on = np.where(np.abs(L) > 0, 1.0, 0.0)
    ch = sc.channel([(sc.track(x + L / 2), "translate_x"), (sc.track(sx), "scale_x"),
                     (sc.track(on * h / (2 * kit.CUBE_FACE)), "scale_y"),
                     (sc.track(on * h / (2 * kit.CUBE_FACE)), "scale_z")])
    s0 = (sx[0], h / (2 * kit.CUBE_FACE), h / (2 * kit.CUBE_FACE)) if on[0] else 0.0
    sc.node(bd, pos=(x + L[0] / 2, y, 0.02), scale=s0, color=(*DIM_COLORS[mi], 255),
            geometry=kit.GEO_CUBE, ch=ch, text=label)
    for sgn in (-1, 1):
        kit.static_plot(sc, bd, [(x + sgn * BAR_HALF / 2, y - 0.08, 0),
                                 (x + sgn * BAR_HALF / 2, y + 0.08, 0)], (200, 200, 220, 160),
                        f"tick: {MODES[mi][2]} at {'+' if sgn > 0 else '-'}its steady value "
                        "(HCS 90 deg)", ratio=0.03)
    kit.static_plot(sc, bd, [(x - BAR_HALF, y, 0), (x + BAR_HALF, y, 0)], (90, 95, 120, 120),
                    f"{MODES[mi][2]} amplitude axis: ends = +/- infinity", ratio=0.02)


def loop_graph(sc, bd, k, model, r, st, vmax):
    present = DIMS[model]
    key = model[0]
    for mi in range(5):
        mode_tile(sc, bd, k, mi, mi < present, model)
    th = angles(st, model, r)
    for mi in range(present):
        amplitude_bar(sc, bd, k, mi, th[:, mi],
                      f"{MODES[mi][2]} now, HCS-compressed (full bar = infinity)  "
                      f"[{model}, r = {r:g}]")
    y0 = row_y(k)
    for label, a, b, fn, models, above in TERMS:
        lo, hi = sorted((a, b))
        xa, xb = MODE_X[lo] + TILE_W / 2, MODE_X[hi] - TILE_W / 2
        pts = arc_points(xa, xb, y0 + (0.12 if above else -0.12), ARC_H if above else -ARC_H)
        if (a > b):
            pts = pts[::-1]              # vertices run source -> target
        live = key in models
        kind = "downscale" if above and a > 0 else "upscale" if not above and b > 0 else "linear"
        n = len(pts)
        cols = [(*[int(c * (0.35 + 0.65 * i / (n - 1))) for c in ARC], 220 if live else 60)
                for i in range(n)]
        kit.static_plot(sc, bd, [(p[0], p[1], 0.0) for p in pts], None,
                        f"{label}: {MODES[a][0]} -> {MODES[b][0]} ({kind}; dim at the source, "
                        f"bright at the target)" + ("" if live else f" -- absent in the {model}"),
                        ratio=0.05 if live else 0.03, colors=cols)
        mid = pts[n // 2]
        if live:
            meter(sc, bd, (mid[0], mid[1], 0.03), fn(st, r), st[:, b], vmax,
                  f"meter {label}: size = |term|, warm = amplifies {MODES[b][2]}, "
                  f"cool = damps it  [{model}, r = {r:g}]")
        sc.node(bd, pos=(mid[0] + 0.12, mid[1] + (0.14 if above else -0.16), 0.05),
                scale=0.03, geometry=kit.GEO_CIRCLE,
                color=(*(ARC if live else NEUTRAL), 255 if live else 120),
                show_text=1 if live else 0,
                text=label if live else f"{label} (absent in the {model})")
    for mi in range(present):
        name, label = MODES[mi][0], DAMPING[mi][0]
        x = MODE_X[mi]
        kit.static_plot(sc, bd, [(x, y0 + BAR_Y - 0.12, 0), (x, y0 + SINK_Y, 0)],
                        (110, 120, 160, 150), f"{label}: damping of {name}", ratio=0.03)
        meter(sc, bd, (x, y0 + SINK_Y, 0.03), DAMPING[mi][1](st), st[:, mi], vmax,
              f"meter {label}: damping of {MODES[mi][2]} (always cool)  "
              f"[{model}, r = {r:g}]")
        sc.node(bd, pos=(x + 0.15, y0 + SINK_Y, 0.05), scale=0.03, geometry=kit.GEO_CIRCLE,
                color=(150, 155, 185, 255), show_text=1, text=label)


# --------------------------------------------------------------------------
# The HCS hyperglyph
# --------------------------------------------------------------------------

def hyperglyph(sc, bd, k, model, r, fine, comets):
    d = DIMS[model]
    sc_ = scales(model, r)
    st = fine[::SUB][:FRAMES]
    ang = angles(st, model, r)
    frame = sc.node(bd, pos=(HG_X, row_y(k), 0.0), rot=HG_ROT, hide=1, geometry=kit.GEO_POINT,
                    text=f"{d}-D HCS hyperglyph frame (0 deg at its right)  [{model}, r = {r:g}]")
    sc.node(bd, pos=(HG_X - 1.6, row_y(k) + 1.75, 0.05), scale=0.04, geometry=kit.GEO_CIRCLE,
            color=(220, 220, 235, 255), show_text=1,
            text=f"{d}-D state on the HCS: " + " ".join(m[2] for m in MODES[:d]))
    circle = [(np.cos(a), np.sin(a), 0.0) for a in np.radians(np.linspace(-180, 180, 61))]
    parent, radius, leaf = frame, HG_R1, 0
    for i in range(d):
        name, _idx, var, _what = MODES[i]
        level = sc.node(parent, pos=(1.0, 0.0, 0.0) if i else (0.0, 0.0, 0.0),
                        rot=(90.0, 0.0, 0.0) if i else (0.0, 0.0, 0.0),
                        scale=HG_RATIO if i else HG_R1, hide=1, geometry=kit.GEO_POINT,
                        text=f"circle {i + 1} ({var}) frame")
        kit.static_plot(sc, level, circle, (*DIM_COLORS[i], 210),
                        f"circle {i + 1}: {var} ({name}), HCS scale s = |{var}c| = {sc_[i]:.2f} "
                        "(steady value at +/-90 deg)", ratio=0.035)
        tick = 0.035 / radius
        for a, col, txt in ((0, (255, 255, 255, 220), f"{var} = 0"),
                            (90, (200, 200, 220, 200), f"{var} = +{sc_[i]:.2f}: steady"),
                            (-90, (200, 200, 220, 200), f"{var} = -{sc_[i]:.2f}: steady"),
                            (180, (*INF, 230), f"{var} = +/- infinity")):
            t = np.radians(a)
            sc.node(level, pos=(np.cos(t), np.sin(t), 0.0), scale=tick, color=col,
                    text=f"{txt}  [{model}, r = {r:g}]")
        spin = sc.node(level, rot=(0.0, 0.0, float(ang[0, i])), hide=1, geometry=kit.GEO_POINT,
                       ch=sc.channel([(sc.track(ang[:, i]), "rotate_z")]),
                       text=f"{var} spinner: rotate_z = the HCS angle of {var}")
        if i == d - 1:
            leaf = sc.node(spin, pos=(1.0, 0.0, 0.0), scale=0.08 / radius,
                           color=(255, 255, 255, 255),
                           text=f"{d}-D leaf: the whole state  [{model}, r = {r:g}]")
        else:
            sc.node(spin, pos=(1.0, 0.0, 0.0), scale=0.045 / radius,
                    color=(*DIM_COLORS[i], 255),
                    text=f"{var} now: the centre of the {MODES[i + 1][2]} circle")
        parent, radius = spin, radius * HG_RATIO
    # Ghosts: the two steady rolls, or for the 4DLM the all-infinite point.
    if model == "4DLM":
        g = hcs.chain(np.full((1, d), 180.0), HG_R1, HG_RATIO)[0]
        sc.node(frame, pos=tuple(g), scale=0.09, color=(*INF, 200),
                text="every variable at +/- infinity (no steady state exists)")
    else:
        for sgn, turn in ((1, "clockwise"), (-1, "counterclockwise")):
            c = sm.critical_point(r, model, sign=sgn)[:d]
            g = hcs.chain(hcs.angle(c, sc_[:d])[None, :], HG_R1, HG_RATIO)[0]
            sc.node(frame, pos=tuple(g), scale=0.09, color=(215, 215, 255, 150),
                    text=f"steady roll (left roll turning {turn}): every circle at a "
                         "quarter turn")
    fine_leaf = hcs.chain(angles(fine, model, r), HG_R1, HG_RATIO)
    comets.trail(frame, fine_leaf, SUB, ROW_COLOR[model],
                 f"leaf trail (last 4 tau)  [{model}, r = {r:g}]", max_step=0.05)
    return leaf


def build(out_dir):
    sc = kit.Scene(FRAMES)
    wall = kit.frames_of_reference(sc, BG, LIFT)
    bd = kit.board(sc, wall, (0.0, -BOARD_SCALE * BOARD_CENTRE[0],
                              -BOARD_SCALE * BOARD_CENTRE[1]), BOARD_SCALE)
    comets = kit.Comets(sc, FRAMES)
    runs = {row: simulate(*row) for row in ROWS}

    # One meter scale for the whole scene, from the rows that stay finite.
    later = int(2.0 / FRAME_DT)
    mags = []
    for (model, r), (fine, esc) in runs.items():
        if esc is None:
            st = fine[::SUB][later:FRAMES]
            mags += [np.abs(fn(st, r)) for _l, _a, _b, fn, ms, _ab in TERMS if model[0] in ms]
    vmax = float(np.percentile(np.concatenate(mags), 99))

    for k, (model, r) in enumerate(ROWS):
        fine, esc = runs[(model, r)]
        st = fine[::SUB][:FRAMES]
        y0 = row_y(k)
        sc.node(bd, pos=(-0.2, y0 + 1.55, 0.05), scale=0.08, geometry=kit.GEO_CIRCLE,
                color=(*ROW_COLOR[model], 255), show_text=1,
                text=f"{model}, r = {r:g}: {VERDICT[(model, r)]}")
        loop_graph(sc, bd, k, model, r, st, vmax)
        hyperglyph(sc, bd, k, model, r, fine, comets)
        if esc is not None:
            f_esc = int(np.ceil(esc / SUB))
            hide = np.where(np.arange(FRAMES) >= f_esc, 0, 1)
            sc.node(bd, pos=(HG_X - 1.6, y0 - 1.95, 0.05), scale=0.07,
                    geometry=kit.GEO_CIRCLE, color=(*INF, 255), hide=int(hide[0]),
                    ch=sc.channel([(sc.track(hide), "hide")]), show_text=1,
                    text=f"escaped: |state| > {ESCAPE:g} at tau = {esc * DT:.2f}, run held")

    legend = row_y(len(ROWS) - 1) - 2.6
    for i, txt in enumerate((
            "Tiles: each mode's pattern, coarse to fine. Arcs above: downscale transfer "
            "(rightward); below: upscale (leftward). Stubs: damping.",
            "Beads: live meters, size = |term|. Warm = it amplifies the mode it feeds, "
            "cool = it damps it. -XY1 turning cool is the new negative feedback.",
            "Bars: each amplitude HCS-compressed, theta = 180 u / (1 + |u|). "
            "Tick = its steady value (90 deg); bar end = infinity.",
            "Hyperglyph: one circle per variable (R G B C M = X Y Z Y1 Z1), each nested on "
            "the last; the leaf is the state. Ghosts: the steady rolls.",
            "HCS: Jeff Sale's Hyperdimensional Coordinate System (after Art Springer). "
            "Infinity is a point on every circle,",
            "which is how the 4DLM's escape to infinity can be drawn at all.")):
        sc.node(bd, pos=(-0.2, legend - 0.42 * i, 0.05), scale=0.04, geometry=kit.GEO_CIRCLE,
                color=(200, 200, 220, 255), show_text=1, text=txt)

    stem = "Feedback_Loop"
    sc.write(out_dir, stem)
    for (model, r), (fine, esc) in runs.items():
        st = fine[::SUB][:FRAMES]
        ang = angles(st, model, r)
        tail = ang[-200:]
        print(f"  {model} r={r:g}: escape step {esc}   last-5-tau HCS angle spread "
              f"{np.round(tail.max(0) - tail.min(0), 1).tolist()}   final angles "
              f"{np.round(ang[-1], 1).tolist()}")
    print(f"meter scale {vmax:.0f};  {len(sc.rows)} nodes, {len(sc.tracks)} tracks, "
          f"{FRAMES} frames -> {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=os.path.join(HERE, "Feedback_Loop"))
    build(ap.parse_args().out)
