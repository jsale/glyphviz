"""
The Stability Landscape: where each Lorenz model's steady roll holds, over the
whole (sigma, r) plane, after Shen (2014) Fig. 10 and appendix C.

For each model (3DLM, 3DLMP with q = 0.17, 5DLM), the steady roll is linearized
(appendix C's A matrices) and its largest Re(lambda) is drawn as relief over
sigma = 5..25 (the Prandtl number) and r = 20..55: blue valleys where the roll
is stable (Re < 0), red where it is not. The panels lie back like terrain,
sigma across and r running away from the viewer.

On each panel:

    gold line      Re(lambda) = 0: the linear r_c(sigma) curve of Fig. 10a
    white dots     the ensemble onset of chaos at the paper's sigmas, from
                   ensemble_shen.py --sigma-sweep (Fig. 10a's solid circles)
    crosses        (3DLM only) Lorenz's closed form r = sigma (sigma + b + 3) /
                   (sigma - b - 1), a check on the eigenvalue computation

Every dot sits on the blue (stable) side of its gold line: between the two,
the steady roll is still stable, yet random starts fall onto the chaotic
attractor -- the coexistence window, which the ensemble shows at every sigma
for all three models, widening as sigma grows.

Below, the paper's Fig. 10a itself: the three r_c(sigma) curves and the dots
on one flat panel. For every sigma the 5DLM and 3DLMP need far more heating
than the 3DLM before the roll goes unstable.

Static scene (no Channels).

    python generate_stability_landscape.py [--out DIR]
"""
import argparse
import json
import os

import numpy as np

import scene_kit as kit
import shen_model as sm

HERE = os.path.dirname(os.path.abspath(__file__))

MODELS = ("3DLM", "3DLMP", "5DLM")
TITLE = {"3DLM": "3DLM (Lorenz)", "3DLMP": "3DLMP (q = 0.17)", "5DLM": "5DLM (Shen)"}
COLOR = {"3DLM": (255, 145, 45), "3DLMP": (235, 110, 200), "5DLM": (70, 200, 255)}
SIG = [round(5.0 + 0.5 * i, 6) for i in range(41)]          # 5 .. 25
RS = [round(20.0 + 0.5 * j, 6) for j in range(71)]          # 20 .. 55
SX, SY = 0.5, 0.24               # sigma, r -> panel x, y
HGAIN, HCLIP = 2.0, 0.8          # Re(lambda) -> height, clipped to +/- HCLIP
TILT = -62.0                     # panels lie back: r runs away, height points up
PANEL_PITCH = 12.5
FIG_X0, FIG_Y0 = 8.5, -13.0      # the flat Fig. 10a panel's lower-left corner
FIG_SX, FIG_SY = 0.75, 0.2       # sigma, r -> flat panel x, y
LIFT = 30.0
BOARD_SCALE = 1.5
BOARD_CENTRE = (16.0, -5.0)

BG = (10, 12, 22)
GOLD = (250, 205, 80)
STOPS = [(-1.0, (60, 110, 230)), (-0.15, (60, 150, 210)), (0.0, (235, 235, 210)),
         (0.15, (240, 150, 80)), (1.0, (220, 60, 50))]


def growth(model, sigma, r):
    return sm.linear_growth(r, model, sigma=sigma)


def height(g):
    return HGAIN * float(np.clip(g, -HCLIP, HCLIP))


def colour(g):
    return kit.lerp_color(STOPS, g / 0.6)


def lorenz_rc(sigma):
    """Lorenz (1963)'s closed form for the 3DLM's r_c."""
    return sigma * (sigma + sm.B + 3) / (sigma - sm.B - 1)


def rc_curve(model, step=0.25):
    """(sigma, r_c) points of the Re(lambda) = 0 contour inside the panel."""
    pts = []
    for s in np.arange(SIG[0], SIG[-1] + 1e-9, step):
        rc = sm.linear_rc(model, sigma=float(s))
        if rc is not None and RS[0] <= rc <= RS[-1]:
            pts.append((float(s), rc))
    return pts


def load_sweep():
    path = os.path.join(HERE, "ensemble_sigma.json")
    if not os.path.exists(path):
        raise SystemExit("ensemble_sigma.json missing: run ensemble_shen.py --sigma-sweep")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def panel(sc, bd, t, model, sweep):
    x0 = t * PANEL_PITCH
    frame = sc.node(bd, pos=(x0, 0.0, 0.0), rot=(TILT, 0.0, 0.0), hide=1,
                    geometry=kit.GEO_POINT,
                    text=f"{TITLE[model]} landscape (laid back {-TILT:g} deg)")
    sc.node(bd, pos=(x0, 5.2, 0.0), scale=0.08, geometry=kit.GEO_CIRCLE,
            color=(*COLOR[model], 255), show_text=1,
            text=f"{TITLE[model]}: max Re(lambda)")
    surf = sc.node(frame, geometry=kit.GEO_POINT, topo=kit.TOPO_SURFACE, ratio=0.05,
                   text=f"{TITLE[model]}: largest Re(lambda) over (sigma, r)")
    for i, s in enumerate(SIG):
        for j, r in enumerate(RS):
            g = growth(model, s, r)
            sc.node(surf, pos=(round(i * 0.5 * SX, 6), round(j * 0.5 * SY, 6), height(g)),
                    scale=0.0, geometry=kit.GEO_CUBE, color=(*colour(g), 255),
                    text=f"{model}, sigma = {s:g}, r = {r:g}: max Re(lambda) = {g:+.3f} "
                         f"({'stable' if g < 0 else 'unstable'} steady roll)")

    def at(s, r, lift=0.05):
        return ((s - SIG[0]) * SX, (r - RS[0]) * SY, height(growth(model, s, r)) + lift)

    curve = rc_curve(model)
    kit.static_plot(sc, frame, [at(s, r) for s, r in curve], (*GOLD, 255),
                    f"{model}: Re(lambda) = 0, the linear r_c(sigma)", ratio=0.12)
    sw = sweep["models"][model]
    for s, on, rc in zip(sweep["sigmas"], sw["onset"], sw["linear_rc"]):
        if on is None:
            continue
        sc.node(frame, pos=at(s, on, 0.12), scale=0.11, color=(255, 255, 255, 255),
                text=f"{model}, sigma = {s:g}: ensemble onset r = {on:g} "
                     f"(linear r_c {rc:.2f}; between them the two coexist)")
    if model == "3DLM":
        for s in range(6, 26):
            r = lorenz_rc(s)
            if r <= RS[-1]:
                sc.node(frame, pos=at(s, r, 0.1), scale=0.1, geometry=25,
                        color=(255, 255, 255, 230),
                        text=f"Lorenz's closed form at sigma = {s}: r_c = {r:.2f}")
    # sigma = 10, the value the rest of the lab uses
    kit.static_plot(sc, frame, [at(10.0, r, 0.03) for r in RS[::2]], (255, 255, 255, 110),
                    "sigma = 10 (the paper's main value)", ratio=0.03)
    for s in (5, 10, 15, 20, 25):
        sc.node(frame, pos=((s - SIG[0]) * SX, -0.35, 0.0), scale=0.04,
                geometry=kit.GEO_CIRCLE, color=(170, 175, 205, 255), show_text=1,
                text=f"{s}" + ("  sigma" if s == 25 else ""))
    for r in (20, 30, 40, 50):
        sc.node(frame, pos=(-1.5, (r - RS[0]) * SY, 0.0), scale=0.04,
                geometry=kit.GEO_CIRCLE, color=(170, 175, 205, 255), show_text=1,
                text=f"r {r}")


def fig10a(sc, bd, sweep):
    """The flat comparison panel."""
    w, h = (SIG[-1] - SIG[0]) * FIG_SX, (RS[-1] - RS[0]) * FIG_SY

    def p(s, r):
        return (FIG_X0 + (s - SIG[0]) * FIG_SX, FIG_Y0 + (r - RS[0]) * FIG_SY, 0.0)

    sc.node(bd, pos=(FIG_X0, FIG_Y0 + h + 0.5, 0.0), scale=0.07, geometry=kit.GEO_CIRCLE,
            color=(220, 220, 235, 255), show_text=1,
            text="Fig. 10a: r_c against sigma. Lines = linear r_c, dots = ensemble onset")
    kit.static_plot(sc, bd, [p(SIG[0], RS[0]), p(SIG[-1], RS[0]), p(SIG[-1], RS[-1]),
                             p(SIG[0], RS[-1])], (110, 120, 160, 150),
                    "Fig. 10a frame: sigma 5..25 across, r 20..55 up", ratio=0.03, closed=True)
    for s in (5, 10, 15, 20, 25):
        sc.node(bd, pos=p(s, RS[0] - 1.8), scale=0.04, geometry=kit.GEO_CIRCLE,
                color=(170, 175, 205, 255), show_text=1, text=f"sigma {s}")
        kit.static_plot(sc, bd, [p(s, RS[0]), p(s, RS[-1])], (90, 95, 125, 70),
                        f"sigma = {s}", ratio=0.02)
    for r in (20, 30, 40, 50):
        sc.node(bd, pos=p(SIG[0] - 2.6, r), scale=0.04, geometry=kit.GEO_CIRCLE,
                color=(170, 175, 205, 255), show_text=1, text=f"r {r}")
        kit.static_plot(sc, bd, [p(SIG[0], r), p(SIG[-1], r)], (90, 95, 125, 70),
                        f"r = {r}", ratio=0.02)
    for model in MODELS:
        kit.static_plot(sc, bd, [p(s, r) for s, r in rc_curve(model)], (*COLOR[model], 255),
                        f"{model}: linear r_c(sigma)", ratio=0.1)
        sw = sweep["models"][model]
        for s, on in zip(sweep["sigmas"], sw["onset"]):
            if on is not None:
                sc.node(bd, pos=p(s, on), scale=0.13, color=(*COLOR[model], 255),
                        text=f"{model}, sigma = {s:g}: ensemble onset r = {on:g}")
        last = rc_curve(model)[-1]
        sc.node(bd, pos=(p(*last)[0] + 0.3, p(*last)[1], 0.0), scale=0.05,
                geometry=kit.GEO_CIRCLE, color=(*COLOR[model], 255), show_text=1,
                text=model)


def build(out_dir):
    sweep = load_sweep()
    sc = kit.Scene(1)
    wall = kit.frames_of_reference(sc, BG, LIFT)
    bd = kit.board(sc, wall, (0.0, -BOARD_SCALE * BOARD_CENTRE[0],
                              -BOARD_SCALE * BOARD_CENTRE[1]), BOARD_SCALE)
    for t, model in enumerate(MODELS):
        panel(sc, bd, t, model, sweep)
    fig10a(sc, bd, sweep)
    for i, txt in enumerate((
            "Relief: the steady roll's largest Re(lambda). Blue below zero = the roll is "
            "stable; red above = it is not. Gold line: Re(lambda) = 0.",
            "White dots: where random starts first turn chaotic (ensemble). They sit on the "
            "stable side: there the steady roll and chaos coexist.",
            "Crosses: Lorenz's closed-form r_c for the 3DLM. Faint white line: sigma = 10, "
            "the value the other scenes use.")):
        sc.node(bd, pos=(-1.0, FIG_Y0 - 1.6 - 0.6 * i, 0.0), scale=0.04,
                geometry=kit.GEO_CIRCLE, color=(200, 200, 220, 255), show_text=1, text=txt)
    stem = "Stability_Landscape"
    os.makedirs(out_dir, exist_ok=True)
    # Static: write only the node CSV (Scene.write would add empty channel files).
    import csv
    with open(os.path.join(out_dir, f"{stem}_gv_node.csv"), "w", newline="",
              encoding="utf-8") as fh:
        wr = csv.writer(fh, lineterminator="\r\n")
        wr.writerow(kit.NODE_COLS)
        for row in sc.rows:
            wr.writerow([kit.num(v) if isinstance(v, float) else v for v in row])
    for model in MODELS:
        c = rc_curve(model)
        lo = min(c, key=lambda p: p[1])
        print(f"  {model}: linear r_c at sigma 10 = {sm.linear_rc(model):.2f}; minimum "
              f"{lo[1]:.2f} at sigma {lo[0]:.2f}")
    print(f"{len(sc.rows)} nodes (static) -> {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=os.path.join(HERE, "Stability_Landscape"))
    build(ap.parse_args().out)
