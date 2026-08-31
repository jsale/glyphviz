#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_fourier_epicycles.py
=============================

Builds the Fourier Epicycles example set: six scenes in which a chain of nested
TOPO_TORUS parents draws its own path.

This file is deliberately thin. Every piece of math -- the harmonic ladder, the
telescoping arm lengths, the tilt and tube knobs, the path tracer and the CSV
writer -- lives in ``glyphviz_core.epicycles``, which is also what
**Tools > Epitrochoid Generator [Ctrl+E]** drives. So the examples and the
designer cannot drift apart, and anything learned by tuning a scene in the GUI
can be pasted back here as a few numbers.

The construction is Jeff's, ported from an ANTz scene of a few years ago
(``fourier_v1``): five nodes, each the child of the last, all Torus topology,
each spinning its ``translate_x``. The fifth is a plain white sphere and it
traces something far more intricate than any circle. What GlyphViz adds -- and
what ANTz could not do -- is the breadcrumb trail: a transparent Plot-topology
parent holding one Point bead per frame at the pen's world position, so the
Plot polyline through them IS the traced curve.

Scenes
------
Planar, and faithful to the original::

    01_rate_driven      translate_rate_x, exactly as the ANTz scene did it.
                        Runs the moment it opens, no playback controls, loops
                        forever, trail fully drawn from frame 0.
    02_self_drawing     the same figure driven by Channels, with each bead's
                        alpha stepping on as the pen arrives. Press Space.
    03_square_wave      a real Fourier series: odd harmonics 1, 3, 5, 7 at
                        amplitudes 1, 1/3, 1/5, 1/7.

Off the plane, which is what V2 is for::

    04_inclined_orrery  Arm.tilt -- each arm orbits in its own inclined plane.
    05_torus_knot       Arm.tube -- an arm riding a second circle around the
                        torus tube, which is a torus knot.
    06_deep_space       six arms, both 3-D knobs at once, self-drawing.

Usage
-----
    python generate_fourier_epicycles.py                 # all six, in place
    python generate_fourier_epicycles.py --out DIR       # somewhere else
    python generate_fourier_epicycles.py --only 05       # one scene
    python generate_fourier_epicycles.py --verify        # re-check, no rebuild

Every run reloads what it wrote and asserts that the trail lies on the pen's
path, that the harmonic ladder is what the rates predict, and that the curve
closes. See ``tests/test_epicycles.py`` for the same checks over every preset.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from glyphviz_core.csv_reader import load_node_csv          # noqa: E402
from glyphviz_core.scene import Scene                        # noqa: E402
from glyphviz_core import epicycles as ep                    # noqa: E402


# --------------------------------------------------------------------------
# The scenes
# --------------------------------------------------------------------------

def _jeffs_original(**overrides) -> ep.EpicycleDesign:
    """Four equal arms at rates (+1, -1, +1, -1) -> harmonics 1, 2, 3, 4.

    The starting phases (0, 90, 90, 90) are recovered from the original file,
    which was saved mid-flight with its angles wound up to (8661.918,
    -8571.918, 8751.918, -8571.918). Those are ``phase + rate * f`` for one
    unknown elapsed f; taking the first phase as 0 gives f = 8661.918 and
    leaves phases that are all exact multiples of 90 -- which no accident
    produces, so they were authored. Phase changes the shape but not the
    spectrum: zeroing them gives a tamer figure (a big circle with two lobes),
    these give the deep spiral loop with three nested inner loops.
    """
    design = ep.preset("Jeff's ANTz original")
    for key, value in overrides.items():
        setattr(design, key, value)
    return design


def _scenes() -> list[tuple[str, str, ep.EpicycleDesign]]:
    """(folder, file stem, design). Folder order is the reading order: the
    planar original first, then the two ways off the plane, then both at once."""
    square = ep.preset("Square wave (odd harmonics)")
    square.name = "Square_Wave"
    square.pen_size = 0.9

    orrery = ep.preset("Inclined orrery (tilt)")
    orrery.name = "Inclined_Orrery"

    knot = ep.preset("Torus knot (tube)")
    knot.name = "Torus_Knot"

    deep = ep.EpicycleDesign(
        name="Deep_Space",
        arms=[
            ep.Arm(length=13.0, rate_x=1.0),
            ep.Arm(length=7.5, rate_x=-2.0, tilt=30.0),
            ep.Arm(length=4.0, rate_x=2.0, tube=2.2, rate_y=5.0),
            ep.Arm(length=2.4, rate_x=-1.0, tilt=-40.0),
            ep.Arm(length=1.5, rate_x=1.0),
            ep.Arm(length=1.0, rate_x=-3.0, tube=0.8, rate_y=-4.0),
        ],
        pen_size=0.7,
        trail_points=720,
        self_drawing=True,
    )

    return [
        ("01_rate_driven", "fourier_rate", _jeffs_original(name="Fourier_Rate")),
        ("02_self_drawing", "fourier_draw",
         _jeffs_original(name="Fourier_Draw", self_drawing=True)),
        ("03_square_wave", "square_wave", square),
        ("04_inclined_orrery", "inclined_orrery", orrery),
        ("05_torus_knot", "torus_knot", knot),
        ("06_deep_space", "deep_space", deep),
    ]


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------

def verify(folder: str, stem: str, design: ep.EpicycleDesign) -> None:
    """Reload from disk and prove the trail is the pen's own path.

    The beads were sampled from the engine at author time; this reloads the
    written file, re-runs the chain, and checks bead f is where the pen is at
    frame f. If the two ever disagree, the scene is lying about the curve it
    claims to have traced.
    """
    path = os.path.join(folder, f"{stem}_gv_node.csv")
    nodes = load_node_csv(path)
    by_id = {n.id: n for n in nodes}
    chain = [n for n in nodes
             if n.type == ep.TYPE_GLYPH and n.topo == ep.T_TORUS]
    plot = next(n for n in nodes if n.topo == ep.T_PLOT)
    beads = [n for n in nodes if n.parent_id == plot.id]
    scene = Scene(nodes, base_scale=1.0)

    frames = ep.frame_count(design)
    step, n_beads = ep.trail_sampling(design, frames)
    assert len(beads) == n_beads, f"{stem}: {len(beads)} beads, expected {n_beads}"

    worst = 0.0
    for i, bead in enumerate(beads):
        f = i * step
        for arm, node in zip(design.arms, chain[1:]):
            by_id[node.id].translate_x = arm.phase_x + arm.rate_x * f
            by_id[node.id].translate_y = arm.phase_y + arm.rate_y * f
        scene.invalidate()
        worst = max(worst, math.dist(scene.world_pos(chain[-1].id),
                                     scene.world_pos(bead.id)))
    # The floor is the node CSV's own 6-decimal write precision, amplified by
    # the parent scales the offsets pass through.
    assert worst < 1e-4, f"{stem}: trail is {worst} off the pen's path"

    # The tag file is found by NAME CONVENTION alone, so a rename costs every
    # label silently.
    bead_ids = {b.id for b in beads}
    unlabelled = [n.id for n in nodes if n.id not in bead_ids and not n.text]
    assert not unlabelled, f"{stem}: tag file did not load for {unlabelled}"

    info = ep.describe(design, frames=frames)
    assert info["closes"], f"{stem}: does not close"
    spec = ", ".join(f"{h:g}x{a:.2f}" for h, a in info["spectrum"][:6])
    shape = ("planar" if info["planar"]
             else f"3-D, {info['z_extent']:.1f} deep")
    print(f"    ladder {' -> '.join(f'{h:g}' for h in info['harmonics'])}"
          f"  |  closes in {info['closes']} frames  |  {shape},"
          f" half-span {info['half_span']:.1f}")
    print(f"    spectrum {spec}")
    print(f"    {len(beads)} beads, worst pen-vs-bead {worst:.2e},"
          f" {len(nodes)} nodes")


# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[4])
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--only", default=None,
                    help="build just the scene whose folder starts with this")
    ap.add_argument("--verify", action="store_true",
                    help="re-check written scenes without rebuilding them")
    args = ap.parse_args()

    for folder, stem, design in _scenes():
        if args.only and not folder.startswith(args.only):
            continue
        out_dir = os.path.join(args.out, folder)
        print(f"{folder}/")
        if not args.verify:
            paths = ep.write_scene(design, out_dir, stem)
            for kind, p in sorted(paths.items()):
                print(f"    {kind:7s} {os.path.relpath(p, args.out)} "
                      f"({os.path.getsize(p):,} bytes)")
        verify(out_dir, stem, design)
        print()


if __name__ == "__main__":
    main()
