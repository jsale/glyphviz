"""
The Superstring Landscape: 30,108 Calabi-Yau Hodge pairs on an HCS torus.

Superstrings live in 10 dimensions: our 4 plus 6 curled up into a tiny
Calabi-Yau shape, and the shape sets the 4-D physics. A Calabi-Yau threefold's
two Hodge numbers h11 and h21 count its shape and size moduli; its Euler
number is chi = 2 (h11 - h21). Mirror symmetry swaps h11 and h21, so chi ->
-chi.

    torus     a 2-D HCS (two nested circles: the ring and the tube), built
              CSV-native: every glyph is a child of a Torus-topology node,
              translate_x = the HCS angle of chi (scale 152, the median |chi|),
              translate_y = the HCS angle of h11 + h21 (scale 184, the
              median). chi = 0 faces the viewer, so mirror symmetry is a true
              mirror: the torus's left and right halves are each other's
              reflection, and chi = +/- infinity meet at the back.
    plot      the same 30,108 pairs in the classic flat view (chi across,
              h11 + h21 up), as one Point Cloud
    gold      |chi| = 6: three generations of quarks and leptons in the
              simplest heterotic models (208 pairs)
    cyan      the 7,890 CICY manifolds' 265 distinct pairs (all chi <= 0)
    Tian-Yau  CICY (14, 23), chi = -18, and its Z3 quotient (6, 9), chi = -6

    python landscape_data.py                          # fetch the data once
    python generate_landscape.py [--out DIR]          -> Superstring_Landscape/
"""
import argparse
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "bosonic_string_lab"))

import landscape_data as ld  # noqa: E402
import string_kit as kit  # noqa: E402
from string_kit import GEO_POINT, GEO_SPHERE, GEO_TORUS, TOPO_TORUS  # noqa: E402

STEM = "Superstring_Landscape"
TOPO_POINTCLOUD = 18

S_CHI = 152.0               # median |chi|: lands at +/-90 deg on the ring
S_SUM = 184.0               # median h11 + h21: lands at 90 deg (the top of the tube)
TORUS_SIZE = 15.0           # torus glyph scale: major radius 9.75, tube 5.25
TORUS_RATIO = 0.35
TORUS_AT = (0.0, -17.0, 0.0)   # turn frame (toward viewer, right, up)
LIFT = 0.06                 # glyphs ride this far above the tube (world units)
PLOT_AT = (0.0, 21.0, -8.0)    # wall (toward viewer, right, up) of the flat plot's origin
X_PER_CHI = 1.0 / 46.0      # flat plot: chi across
Y_PER_SUM = 1.0 / 30.0      # flat plot: h11 + h21 up
WIDTH = 74.0
WORLD_LIFT = 26.0
LINE = 1.8

BG = (8, 9, 20)
NEG, POS, ZERO = (80, 150, 255), (255, 145, 60), (235, 235, 245)
GOLD, CYAN = (255, 210, 60), (40, 240, 230)
SURFACE = (34, 38, 62, 255)
GUIDE = (200, 205, 235, 170)

STORY = (
    "Superstrings live in 10 dimensions: our 4, plus 6 curled up into a tiny Calabi-Yau shape,",
    "and the shape sets the 4-D physics. Kreuzer and Skarke built 473,800,776 such shapes from",
    "4-D polytopes (2000); they share just 30,108 distinct Hodge-number pairs (h11, h21). One glyph each.",
    "HCS torus: chi = 2(h11 - h21) around the ring (+/-152 at +/-90 deg, +/- infinity at the back),",
    "h11 + h21 around the tube (184 at the top). Right: the same pairs in the classic flat view.",
)
NOTES = (
    ("Mirror symmetry swaps h11 and h21, so chi -> -chi: the torus is its own mirror image across", None),
    ("the chi = 0 plane facing you. Every one of the 30,108 pairs has its mirror in the list (checked).", None),
    ("gold: |chi| = 6, three generations of quarks and leptons in the simplest heterotic models (208 pairs)",
     GOLD),
    ("cyan: the 7,890 CICY manifolds (Candelas et al. 1988): 265 distinct pairs, every one with chi <= 0",
     CYAN),
    ("Tian-Yau (1986): CICY (14, 23), chi = -18, divided by a free Z3 symmetry gives (6, 9), chi = -6.", None),
)


def chi_color(chi):
    return NEG if chi < 0 else POS if chi > 0 else ZERO


def torus_angles(h11, h21):
    chi = 2 * (np.asarray(h11) - np.asarray(h21))
    return kit.hcs_angle(chi, S_CHI), kit.hcs_angle(np.asarray(h11) + np.asarray(h21), S_SUM)


def torus_point(th1, th2, lift=LIFT):
    """(ring, tube) angles in degrees -> the torus node's local coordinates,
    the same formula as glyphviz_core.topology._torus_offset at scale 1,
    used only for the guide circles (the glyphs are placed by the app)."""
    major, tube = 1.0 - TORUS_RATIO, TORUS_RATIO + lift / TORUS_SIZE
    u, v = np.broadcast_arrays(np.radians(th1), np.radians(th2))
    radial = major + tube * np.cos(v)
    return np.stack([radial * np.cos(u), radial * np.sin(u), tube * np.sin(v)], axis=-1)


def build(out_dir):
    ks, cy = ld.check()
    real = ~cy["product"]
    cicy_pairs = {}
    for a, b in zip(cy["h11"][real], cy["h21"][real]):
        cicy_pairs[(int(a), int(b))] = cicy_pairs.get((int(a), int(b)), 0) + 1

    sc = kit.Scene()
    turn, wall = kit.frames_of_reference(sc, BG, WORLD_LIFT)
    for side in (-1, 1):
        sc.node(wall, pos=(0.0, side * WIDTH / 2, 0.0), hide=1, geometry=GEO_POINT,
                text=f"framing anchor ({'left' if side < 0 else 'right'} edge of the opening view)")

    # ---- the HCS torus ----
    torus = sc.node(turn, pos=TORUS_AT, scale=TORUS_SIZE, color=SURFACE, geometry=GEO_TORUS,
                    topo=TOPO_TORUS, ratio=TORUS_RATIO,
                    text="HCS torus: ring = chi (s = 152), tube = h11 + h21 (s = 184)")
    lift = LIFT / TORUS_SIZE                 # a Torus child's translate_z is in the parent's units
    th1, th2 = torus_angles(ks[:, 0], ks[:, 1])
    for (h11, h21, chi), a, b in zip(ks, th1, th2):
        sc.node(torus, pos=(float(a), float(b), lift), color=(*chi_color(chi), 255),
                geometry=GEO_POINT, ratio=0.12,
                text=f"(h11, h21) = ({h11}, {h21}), chi = {chi}")
    for (h11, h21), n in sorted(cicy_pairs.items()):
        a, b = torus_angles(h11, h21)
        sc.node(torus, pos=(float(a), float(b), 2 * lift), color=(*CYAN, 255),
                geometry=GEO_POINT, ratio=0.22,
                text=f"CICY: {n} manifold{'s' if n > 1 else ''} with (h11, h21) = ({h11}, {h21}), "
                     f"chi = {2 * (h11 - h21)}")
    for h11, h21, chi in ks[np.abs(ks[:, 2]) == 6]:
        a, b = torus_angles(h11, h21)
        sc.node(torus, pos=(float(a), float(b), 3 * lift), color=(*GOLD, 255),
                geometry=GEO_POINT, ratio=0.25,
                text=f"three generations: (h11, h21) = ({h11}, {h21}), chi = {chi}")
    for (h11, h21), lbl in (((14, 23), "Tian-Yau's parent: CICY (14, 23), chi = -18"),
                            ((6, 9), "Tian-Yau: (14, 23) / Z3 = (6, 9), chi = -6")):
        a, b = torus_angles(h11, h21)
        sc.node(torus, pos=(float(a), float(b), 4 * lift), scale=0.025,
                color=(*(GOLD if h11 == 6 else CYAN), 255), geometry=GEO_SPHERE,
                show_text=int(h11 == 6),
                text=lbl)

    # Guide circles: the mirror plane, chi = +/-152, +/- infinity, the tube's top.
    # They hang off a plain frame matching the torus node, because a Torus
    # node's own children read their translate as angles.
    tframe = sc.node(turn, pos=TORUS_AT, scale=TORUS_SIZE, hide=1, geometry=GEO_POINT,
                     text="torus guide frame: the torus node's frame, Cartesian")
    guides = (("ring", 0.0, "chi = 0: the mirror plane", 1),
              ("ring", 90.0, "chi = +152 (+90 deg)", 0),
              ("ring", -90.0, "chi = -152 (-90 deg)", 0),
              ("ring", 180.0, "chi = +/- infinity (180 deg)", 0),
              ("tube", 90.0, "h11 + h21 = 184 (the tube's top, 90 deg)", 0))
    for kind, th, lbl, pin in guides:
        t = np.linspace(0.0, 180.0, 61) if kind == "ring" else np.linspace(-180.0, 180.0, 181)
        pts = torus_point(th, t) if kind == "ring" else torus_point(t, th)
        kit.polyline(sc, tframe, pts, GUIDE, f"HCS guide: {lbl}", ratio=0.06)
        tip = torus_point(th, 90.0, lift=1.2) if kind == "ring" else torus_point(150.0, th, 1.2)
        sc.node(tframe, pos=tuple(tip), scale=0.012, color=GUIDE, show_text=pin, text=lbl)

    # ---- the flat plot (a Point Cloud) ----
    pb = kit.board(sc, wall, PLOT_AT, label="flat plot")
    cloud = sc.node(pb, geometry=GEO_POINT, topo=TOPO_POINTCLOUD, ratio=0.12,
                    color=(255, 255, 255, 255),
                    text="the classic view: chi across, h11 + h21 up (Kreuzer-Skarke)")
    for h11, h21, chi in ks:
        sc.node(cloud, pos=(chi * X_PER_CHI, (h11 + h21) * Y_PER_SUM, 0.0),
                color=(*chi_color(chi), 255), geometry=GEO_POINT,
                text=f"(h11, h21) = ({h11}, {h21}), chi = {chi}")
    for (h11, h21), n in sorted(cicy_pairs.items()):
        chi = 2 * (h11 - h21)
        sc.node(pb, pos=(chi * X_PER_CHI, (h11 + h21) * Y_PER_SUM, 0.08), color=(*CYAN, 255),
                geometry=GEO_POINT, ratio=0.22,
                text=f"CICY: {n} manifold{'s' if n > 1 else ''} with (h11, h21) = ({h11}, {h21})")
    for h11, h21, chi in ks[np.abs(ks[:, 2]) == 6]:
        sc.node(pb, pos=(chi * X_PER_CHI, (h11 + h21) * Y_PER_SUM, 0.1), color=(*GOLD, 255),
                geometry=GEO_POINT, ratio=0.25,
                text=f"three generations: (h11, h21) = ({h11}, {h21}), chi = {chi}")
    top = 520 * Y_PER_SUM
    kit.polyline(sc, pb, [(-960 * X_PER_CHI, 0, -0.05), (960 * X_PER_CHI, 0, -0.05)], GUIDE,
                 "chi axis", ratio=0.05)
    kit.polyline(sc, pb, [(0, 0, -0.05), (0, top, -0.05)], GUIDE,
                 "chi = 0: the mirror line", ratio=0.05)
    for x, y, t in ((0.0, top, "chi = 0: mirror line; h11 + h21 up"),
                    (-960 * X_PER_CHI, -1.2, "chi = -960"),
                    (960 * X_PER_CHI - 4.0, -1.2, "chi = +960")):
        kit.caption(sc, pb, (x, y), t, size=0.15)

    # ---- top: the story; bottom: the notes ----
    tb = kit.board(sc, wall, (0.0, -0.5 * WIDTH, 25.0), label="story board")
    kit.caption(sc, tb, (0.0, 0.0),
                "The superstring landscape: 30,108 Calabi-Yau shapes on an HCS torus",
                color=kit.TITLE, size=0.3)
    for i, t in enumerate(STORY):
        kit.caption(sc, tb, (0.0, -LINE * (i + 1.5)), t, size=0.2)
    bb = kit.board(sc, wall, (0.0, -0.5 * WIDTH, -15.0), label="notes board")
    for i, (t, c) in enumerate(NOTES):
        kit.caption(sc, bb, (0.0, -LINE * i), t, color=c or kit.CAPTION, size=0.25 if c else 0.2)

    sc.write(out_dir, STEM)
    return sc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / STEM))
    args = ap.parse_args()
    sc = build(args.out)
    print(f"{STEM}: {len(sc.rows):,} nodes -> {args.out}")


if __name__ == "__main__":
    main()
