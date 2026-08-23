#!/usr/bin/env python
"""Render a rough preview of a scene straight from the transform engine.

This exists because of a bug that a CSV cannot show you.  Every satellite in
Orbital_Shells was authored at scale ~1.5 and every validator passed, while
the glyphs actually drew at up to 190 world units — bigger than the Earth —
because a torus parent's scale multiplies its children's *rendered* size.
Nothing in the file looked wrong.  Only a picture showed it.

So: pull world positions and world *scales* out of `glyphviz_core`, project
them with a simple camera, and draw. It is not a renderer and does not try to
be one — no lighting, no depth-correct geometry, no textures. It answers one
question: is anything absurdly the wrong size or in the wrong place?

    python preview_scene.py                                  # all three scenes
    python preview_scene.py Orbital_Shells/..._node.csv       # just one
    python preview_scene.py --elev 8 --azim 40 --out shot.png
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for candidate in (os.environ.get("GLYPHVIZ_PATH"),
                  os.path.abspath(os.path.join(HERE, "..", "..")),
                  r"C:\Users\jsale\source\repos\glyphviz"):
    if candidate and os.path.isdir(os.path.join(candidate, "glyphviz_core")):
        sys.path.insert(0, candidate)
        break
else:
    raise SystemExit("cannot find glyphviz_core — set GLYPHVIZ_PATH")

import matplotlib                                              # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                # noqa: E402
from matplotlib.patches import Circle                          # noqa: E402

from glyphviz_core import csv_reader                           # noqa: E402
from glyphviz_core import scene as scene_mod                   # noqa: E402

DEFAULTS = [
    ("Live_Sky/live_sky_gv_node.csv", "Live Sky"),
    ("One_Orbit/one_orbit_gv_node.csv", "One Orbit"),
    ("Orbital_Shells/orbital_shells_gv_node.csv", "Orbital Shells"),
]


def camera(elev_deg, azim_deg):
    """Right-handed view basis: returns (right, up, forward)."""
    e, a = math.radians(elev_deg), math.radians(azim_deg)
    fwd = np.array([math.cos(e) * math.cos(a),
                    math.cos(e) * math.sin(a),
                    math.sin(e)])
    world_up = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, world_up)
    if np.linalg.norm(right) < 1e-9:
        right = np.array([1.0, 0.0, 0.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    return right, up, fwd


def render(path, title, ax, elev, azim):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    nodes = csv_reader.load_node_csv(path)
    sc = scene_mod.Scene(nodes)

    right, up, fwd = camera(elev, azim)
    pts, sizes, colors, depth = [], [], [], []
    ring_paths = []

    for r in rows:
        if int(r["type"]) not in (5,) or int(r["hide"]):
            continue
        nid = int(r["id"])
        w = np.asarray(sc.world_pos(nid), dtype=float)
        ws = float(np.mean(np.asarray(sc.world_scale(nid), dtype=float)))
        rgb = (int(r["color_r"]) / 255, int(r["color_g"]) / 255,
               int(r["color_b"]) / 255)

        # A visible torus is a ring: draw it as a ring, not a dot.
        if int(r["topo"]) == 3 and int(r["geometry"]) in (6, 7):
            ring_paths.append((_ring_points(sc, r, rows), rgb))
            continue

        pts.append([float(w @ right), float(w @ up)])
        sizes.append(ws)
        colors.append(rgb)
        depth.append(float(w @ fwd))

    pts = np.array(pts) if pts else np.zeros((0, 2))
    sizes = np.array(sizes) if len(sizes) else np.zeros(0)

    for poly, rgb in ring_paths:
        p2 = np.stack([poly @ right, poly @ up], axis=-1)
        ax.plot(p2[:, 0], p2[:, 1], color=rgb, lw=0.7, alpha=0.55, zorder=1)

    if len(pts):
        order = np.argsort(depth)          # far first
        # Marker area in points^2, scaled so world size reads honestly.
        span = max(np.abs(pts).max() * 2.0, 1.0)
        px_per_unit = 640.0 / span
        area = np.clip((sizes * px_per_unit) ** 2, 0.4, 8000.0)
        ax.scatter(pts[order, 0], pts[order, 1], s=area[order],
                   c=[colors[i] for i in order], linewidths=0, zorder=2)

    ax.set_aspect("equal")
    ax.set_facecolor("#06080f")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#2a2f45")
    ax.set_title(f"{title}\n{len(pts)} glyphs, {len(ring_paths)} rings",
                 color="#c8d0e8", fontsize=9)
    return sizes


def _ring_points(sc, ring_row, rows, n=160):
    """Sample a visible torus by asking the engine where its children would go.

    Rather than re-deriving the ring's orientation from its rotation fields —
    which is the very thing under test — this reads the ring's own basis out
    of the scene.
    """
    nid = int(ring_row["id"])
    centre = np.asarray(sc.world_pos(nid), dtype=float)
    scale = float(ring_row["scale_x"]) * 3.0     # base_scale
    got = sc.basis_matrices(nid)
    m = np.asarray(got[0], dtype=float) if got else np.eye(3)
    # Normalise: the basis carries the node's own scale, which we apply here.
    for k in range(3):
        nk = np.linalg.norm(m[:, k])
        if nk > 1e-12:
            m[:, k] /= nk
    t = np.linspace(0.0, 2.0 * math.pi, n)
    local = np.stack([np.cos(t) * scale, np.sin(t) * scale, np.zeros_like(t)],
                     axis=-1)
    return centre + local @ m.T


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", help="node CSVs (default: all three)")
    ap.add_argument("--elev", type=float, default=22.0)
    ap.add_argument("--azim", type=float, default=35.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    targets = ([(p, os.path.basename(p)) for p in args.paths] if args.paths
               else [(os.path.join(HERE, p), t) for p, t in DEFAULTS
                     if os.path.exists(os.path.join(HERE, p))])
    if not targets:
        raise SystemExit("no scenes found — build them first")

    fig, axes = plt.subplots(1, len(targets),
                             figsize=(6.2 * len(targets), 6.4))
    fig.patch.set_facecolor("#06080f")
    if len(targets) == 1:
        axes = [axes]

    for ax, (path, title) in zip(axes, targets):
        sizes = render(path, title, ax, args.elev, args.azim)
        print(f"{title}: rendered glyph size "
              f"{sizes.min():.2f} .. {sizes.max():.2f} world units"
              if len(sizes) else f"{title}: no glyphs")

    fig.tight_layout()
    out = args.out or os.path.join(HERE, "preview.png")
    fig.savefig(out, dpi=110, facecolor=fig.get_facecolor())
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
