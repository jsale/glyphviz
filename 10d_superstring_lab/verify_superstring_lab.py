"""
Check the superstring lab through GlyphViz's own objects: load the node CSV
with the app's loader, resolve transforms with compute_world_transforms, and
hold what the scene DRAWS to the data and the HCS.

    python verify_superstring_lab.py [--paint]

  * the data: 30,108 Kreuzer-Skarke pairs, chi = 2 (h11 - h21), the list
    closed under mirror symmetry; 7,890 CICYs, every configuration a
    threefold, chi <= 0 (landscape_data.check)
  * every torus glyph sits where the HCS puts it: the app's Torus topology
    seats (h11, h21) at ring angle theta(chi; 152) and tube angle
    theta(h11 + h21; 184), checked against an independent torus formula
  * mirror symmetry is a true mirror in the drawing: each pair's glyph is
    the reflection of its mirror pair's glyph across the torus's chi = 0
    plane (the plane through its axis and the viewer)
  * the flat plot's points are (chi, h11 + h21) at the stated scales
  * 208 gold glyphs per view, all |chi| = 6; 265 cyan, all CICY pairs
  --paint: time a few full repaints through the real Viewport
"""
import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from glyphviz_core.csv_reader import load_node_csv  # noqa: E402
from glyphviz_core.topology import compute_world_transforms  # noqa: E402

import generate_landscape as g  # noqa: E402
import landscape_data as ld  # noqa: E402


def torus_local(th1, th2, lift):
    """Independent torus formula in the torus node's own units."""
    major, tube = 1.0 - g.TORUS_RATIO, g.TORUS_RATIO + lift
    u, v = math.radians(th1), math.radians(th2)
    return np.array([(major + tube * math.cos(v)) * math.cos(u),
                     (major + tube * math.cos(v)) * math.sin(u), tube * math.sin(v)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paint", action="store_true")
    args = ap.parse_args()
    ks, cy = ld.check()
    print("data: OK")
    path = HERE / g.STEM / f"{g.STEM}_gv_node.csv"
    nodes = load_node_csv(str(path))
    w = compute_world_transforms(nodes, 1.0)

    def pos(n):
        return w.world_pos[w.row_of_id[n.id]]

    torus = next(n for n in nodes if n.text.startswith("HCS torus"))
    B = w.world_basis[w.row_of_id[torus.id]]
    c0 = pos(torus)
    kids = [n for n in nodes if n.parent_id == torus.id]
    land = [n for n in kids if n.text.startswith("(h11, h21)")]
    assert len(land) == 30108

    def pair(n):
        a, b = n.text.split("(h11, h21) = (")[1].split(")")[0].split(", ")
        return int(a), int(b)

    worst = 0.0
    at = {}
    for n in land:
        h11, h21 = pair(n)
        th1 = float(g.kit.hcs_angle(2 * (h11 - h21), g.S_CHI))
        th2 = float(g.kit.hcs_angle(h11 + h21, g.S_SUM))
        want = c0 + B @ torus_local(th1, th2, g.LIFT / g.TORUS_SIZE)
        p = pos(n)
        worst = max(worst, float(np.linalg.norm(p - want)))
        at[(h11, h21)] = p
    assert worst < 1e-3, worst
    print(f"torus: 30,108 glyphs on their HCS points within {worst:.1e}")

    # The chi = 0 plane: through the torus centre, spanned by its axis and
    # ring angle 0. Reflect across it: flip the component along ring angle 90.
    n90 = B @ np.array([0.0, 1.0, 0.0])
    n90 /= np.linalg.norm(n90)
    worst = 0.0
    for (h11, h21), p in at.items():
        q = at[(h21, h11)]
        r = p - 2 * np.dot(p - c0, n90) * n90
        worst = max(worst, float(np.linalg.norm(r - q)))
    assert worst < 1e-3, worst
    print(f"mirror: every glyph is its mirror pair's reflection within {worst:.1e}")

    board = next(n for n in nodes if n.text.startswith("flat plot:"))
    Bp = w.world_basis[w.row_of_id[board.id]]
    p0 = pos(board)
    cloud = next(n for n in nodes if n.text.startswith("the classic view"))
    pts = [n for n in nodes if n.parent_id == cloud.id]
    assert len(pts) == 30108
    worst = 0.0
    for n in pts[::7]:
        h11, h21 = pair(n)
        local = np.linalg.solve(Bp, pos(n) - p0)
        want = np.array([2 * (h11 - h21) * g.X_PER_CHI, (h11 + h21) * g.Y_PER_SUM, 0.0])
        worst = max(worst, float(np.linalg.norm(local - want)))
    assert worst < 1e-3, worst
    print(f"flat plot: points on (chi, h11 + h21) within {worst:.1e}")

    gold = [n for n in nodes if n.text.startswith("three generations")]
    cyan = [n for n in nodes if n.text.startswith("CICY:")]
    assert len(gold) == 2 * 208 and len(cyan) == 2 * 265
    for n in gold:
        h11, h21 = pair(n)
        assert abs(2 * (h11 - h21)) == 6
    real = ~cy["product"]
    cpairs = {(int(a), int(b)) for a, b in zip(cy["h11"][real], cy["h21"][real])}
    assert {pair(n) for n in cyan} == cpairs
    print("highlights: 208 gold (|chi| = 6) and 265 cyan (CICY) in each view")

    if args.paint:
        sys.path.insert(0, str(REPO / "tools"))
        import export_frame  # noqa: E402
        from PySide6.QtWidgets import QApplication  # noqa: E402
        app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
        vp, *_ = export_frame._build_viewport(str(path), 1.0, False, False, False, None, 1444, 800)
        vp.grabFramebuffer()
        times = []
        for _ in range(10):
            t = time.perf_counter()
            vp.update()
            vp.grabFramebuffer()
            times.append(time.perf_counter() - t)
        times.sort()
        print(f"paint: {len(nodes):,} nodes, median {times[5] * 1000:.0f} ms per repaint")
    print("all checks pass")


if __name__ == "__main__":
    main()
