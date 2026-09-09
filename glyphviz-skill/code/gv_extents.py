#!/usr/bin/env python3
"""gv_extents.py — how big is everything, and what is wrong with this scene?

    python gv_extents.py scene_gv_node.csv
    python gv_extents.py scene_gv_node.csv --base-scale 3 --all

Answers the question a CSV cannot: what does this scene actually *render* as.
Every number comes from `gv_kernel`, which is the app's own placement math
vendored verbatim — so these are the sizes and positions GlyphViz will draw,
not an estimate.

It leads with problems, because that is what you are usually looking for:
children buried inside their parent, children flung far away, glyphs that will
shear, alpha-0 nodes mistaken for carriers, links with an unresolvable end, and
anything that would change if the optional minimum-glyph-size clamp were on.
Then it reports scene extents, rendered size per hierarchy level, root spacing,
and what a Global Scale change would do.

Sizes come from each geometry's own silhouette: a box for cubes, grids, flat
markers and rings, a cylinder for cones, tori, pins and cylinders, an ellipsoid
for everything else. Every glyph is built to fit inside RADIUS 1, which is not
the same as spanning −1…+1 per axis — a cube's faces are 1/√3 out, a Pin is a
needle 0.1 wide and 1.1 tall, a flat square reaches 0.707 — so the per-axis
half-extents come from the measured `LOCAL_BOX` table below.

Burial is only judged under topologies where a child is meant to sit *on* its
parent. A Rod parent threads its children along its own axis and the Z-variants
place them at the centre on purpose, so neither counts as buried.
"""
from __future__ import annotations

import argparse
import copy
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gv_kernel import (  # noqa: E402
    load_node_csv, compute_world_transforms, Scene, node_world_matrix,
    TOPO_NAMES, GEO_NAMES, DEFAULT_SCALE_FLOOR, NO_SCALE_FLOOR,
    NODE_TYPE_GRID, NODE_TYPE_LINK, NON_VISUAL_TYPES,
)

# A big translate is only suspicious under a plainly Cartesian parent. Plot,
# Surface and Point Cloud parents hold scan data whose coordinates are properly
# huge, and the angular topologies bound their own placement.
CARTESIAN_TOPOS = {0, 8}          # None, Plane

# Burial only means something when the child is supposed to sit ON the parent.
# A Rod parent threads its children along its own axis, and the Z-variants place
# them at the centre on purpose, so neither can be "buried". Plot/Surface/Point
# Cloud parents are containers for data points, not bodies.
SEATED_TOPOS = {0, 1, 2, 3, 4, 5, 7, 8, 14}   # None Cube Sphere Torus Cylinder Pin Point Plane Spiral
FLUNG_RATIO = 20.0                # child distance / parent radius, to be considered at all
FLUNG_ABSURD = 100.0              # ... beyond this it is wrong however it was authored
FLUNG_OUTLIER = 10.0              # ... or this many times its own siblings' median
DEGREES_HINT = 45.0               # a Cartesian translate this large may be degrees
SHEAR_COS = 0.09                  # |cos| between a node's own basis axes (~5 deg off square)
SHOW = 4                          # problem rows printed before truncating

# --------------------------------------------------------------------------
# Aim. Placement decides which way a glyph POINTS, not `rotate_*`, and getting
# that wrong is the one error a position check cannot see: a set of perfectly
# placed rods can still be aimed into a flat fan. So it gets measured here.
#
# +Z is the pointing axis of every directional geometry -- these are the
# geometries that HAVE an aim to get wrong. A sphere or a cube has none.
DIRECTIONAL_GEOMETRIES = {
    4, 5,                    # Cone: long axis, apex at +Z
    16, 17,                  # Pin: the shaft, tip at the origin
    18, 19, 31, 32,          # Cylinder (and its interiors): the long axis
    6, 7, 33, 34,            # Torus, Flat Ring: the ring's axis
    20, 21, 24, 25, 26,      # Grid/square, Circle, Cross, Star: the facing normal
}
# Topologies that hand a child a base rotation turning its +Z outward. Measured
# through the engine: Sphere (2) and Point (7) aim exactly outward (dot 1.0000
# with the radial), Torus (3) and Ztorus (11) at the tube's own normal, Cube (1)
# at the facet's normal. Zsphere (10) deliberately does NOT aim, and the axis
# family (Cylinder, Rod, Spiral and their Z variants) sends +X radial while
# leaving +Z along the parent's axis.
AIMING_TOPOS = {1, 2, 3, 7, 11}
AIM_FIGHT_DEG = 15.0              # deflection off the placed aim worth reporting


# --------------------------------------------------------------------- geometry

# Every glyph is built to FIT INSIDE RADIUS 1, which is not the same thing as
# spanning -1..+1 on each axis: a cube's eight corners sit on that sphere, so
# its faces are only 1/sqrt(3) = 0.577 out. Placement is unaffected -- a
# topology seats its children on the radius-1 sphere whatever geometry the
# parent wears -- but rendered SIZE is per-geometry, and getting this wrong is
# how a Pin bar comes out ten times too thin beside a cube of the same scale.
#
# geometry id -> (x half, y half, z low, z high) in local units, before scale.
# Measured from the app's own builders in glyphviz_gl/geometry.py; the repo
# test tests/test_skill_kernel.py re-measures them and fails if they drift.
_C = 1.0 / math.sqrt(3.0)           # cube: corners on the unit sphere
_SQ = 1.0 / math.sqrt(2.0)          # flat square: corners on the unit circle
_UNIT = (1.0, 1.0, -1.0, 1.0)
_FLAT = (1.0, 1.0, 0.0, 0.0)

LOCAL_BOX = {
    0: (_C, _C, -_C, _C), 1: (_C, _C, -_C, _C),           # Cube, Cube Wire
    2: _UNIT, 3: _UNIT,                                    # Sphere
    4: _UNIT, 5: _UNIT,                                    # Cone  (r 1, h 2)
    6: _UNIT, 7: _UNIT,                                    # Torus (z is ratio)
    8: (0.9342, 0.9342, -0.9342, 0.9342),                  # Dodecahedron
    9: (0.9342, 0.9342, -0.9342, 0.9342),
    10: _UNIT, 11: _UNIT,                                  # Octahedron
    12: (0.9428, 0.8165, -0.3333, 1.0),                    # Tetrahedron
    13: (0.9428, 0.8165, -0.3333, 1.0),
    14: (0.8507, 0.8507, -0.8507, 0.8507),                 # Icosahedron
    15: (0.8507, 0.8507, -0.8507, 0.8507),
    16: (0.1, 0.1, 0.0, 1.1), 17: (0.1, 0.1, 0.0, 1.1),    # Pin: a NEEDLE
    18: _UNIT, 19: _UNIT,                                  # Cylinder (r 1, h 2)
    20: (_SQ, _SQ, 0.0, 0.0), 21: (_SQ, _SQ, 0.0, 0.0),    # flat square
    22: _UNIT,                                             # Point: screen-space
    23: _UNIT,                                             # Mesh: model-dependent
    24: _FLAT, 25: _FLAT, 26: _FLAT,                       # Circle, Cross, Star
    27: _UNIT, 28: _UNIT,                                  # Line, Line Prism
    29: (_C, _C, -_C, _C),                                 # Cube Interior
    30: _UNIT, 31: _UNIT, 32: _UNIT,                       # interior sphere/cyl
    33: _UNIT, 34: _UNIT,                                  # Flat Ring (z is ratio)
}
# These two carry their z half-extent in the node's own `ratio` instead.
RATIO_SHAPED = {6, 7, 33, 34}
# A flat glyph has no thickness at all; give it a sliver so a support width of
# exactly zero never divides into anything.
FLAT_EPS = 1e-6


def local_box(geometry, ratio=0.14):
    """(half(3), centre(3)) of one geometry's local bounding box, before scale."""
    hx, hy, zlo, zhi = LOCAL_BOX.get(int(geometry), _UNIT)
    if int(geometry) in RATIO_SHAPED:
        zlo, zhi = -abs(ratio), abs(ratio)
    hz = max((zhi - zlo) / 2.0, FLAT_EPS)
    return (np.array([max(hx, FLAT_EPS), max(hy, FLAT_EPS), hz]),
            np.array([0.0, 0.0, (zhi + zlo) / 2.0]))


def _boxes(nodes, scene):
    """id -> (centre_world(3), cols(3,3), half(3)) for every drawable node.

    `cols` are the draw matrix's basis columns (already carrying the node's own
    scale, every ancestor's, Global Scale, rod factors and the scale floor).
    `half` is the geometry's local half-size along each axis.
    """
    out = {}
    for n in nodes:
        if n.type in NON_VISUAL_TYPES or n.type == NODE_TYPE_LINK or n.hide:
            continue
        m = node_world_matrix(n, scene)
        half, local_centre = local_box(n.geometry, n.ratio)
        centre = m[:3, 3] + m[:3, :3] @ local_centre
        out[n.id] = (centre, m[:3, :3], half)
    return out


# Geometry families, so the support function matches the actual silhouette. A
# box support applied to a sphere over-estimates by up to 1.73x, which would
# report perfectly-seated children as buried.
_BOXY = {0, 1, 20, 21, 24, 25, 26, 29, 33, 34}          # cube, grid, flat markers, ring
_ROUND_AXIS = {4, 5, 6, 7, 16, 17, 18, 19, 31, 32}      # cone, torus, pin, cylinder


def _support(cols, half, u, geometry=None):
    """Half-width of the node's silhouette along unit vector u.

    Exact for a box, an ellipsoid and a cylinder respectively; the default is
    the ellipsoid form, which covers sphere/icosa/dodeca/octa/tetra.
    """
    a = [float(cols[:, i] @ u) * half[i] for i in range(3)]
    if geometry in _BOXY:
        return abs(a[0]) + abs(a[1]) + abs(a[2])
    if geometry in _ROUND_AXIS:
        return math.hypot(a[0], a[1]) + abs(a[2])
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _radius(cols, half):
    """Largest half-extent in any direction."""
    return float(np.linalg.norm(cols * half[None, :], axis=0).max())


def _placed_aim(nodes, base_scale, rotated):
    """World +Z each of `rotated` would have if its own rotate_* were 0.

    That is the direction its parent's topology aims it, which is the thing a
    hand-written rotation is composed on top of -- never replaces. Only the
    named nodes are zeroed; ancestors keep their own rotations, because the
    question is what THIS node's rotation is doing.
    """
    ids = {n.id for n in rotated}
    probe = []
    for n in nodes:
        if n.id in ids:
            m = copy.copy(n)
            m.rotate_x = m.rotate_y = m.rotate_z = 0.0
            probe.append(m)
        else:
            probe.append(n)
    t = compute_world_transforms(probe, base_scale)
    out = {}
    for n in rotated:
        z = t.world_basis[t.row_of_id[n.id]][:, 2]
        nz = float(np.linalg.norm(z))
        if nz > 1e-12:
            out[n.id] = z / nz
    return out


# --------------------------------------------------------------------- checks

def analyse(path, base_scale=1.0):
    nodes = load_node_csv(path)
    scene = Scene(nodes, base_scale, NO_SCALE_FLOOR)
    tr = compute_world_transforms(nodes, base_scale)
    by_id = {n.id: n for n in nodes}
    boxes = _boxes(nodes, scene)
    kids = defaultdict(list)
    for n in nodes:
        if n.parent_id:
            kids[n.parent_id].append(n)

    r = {"path": path, "base_scale": base_scale, "nodes": nodes, "scene": scene,
         "tr": tr, "by_id": by_id, "boxes": boxes, "kids": kids}

    buried, cand, flung, sheared, degrees = [], [], [], [], []
    sib_dist = defaultdict(list)
    for n in nodes:
        p = by_id.get(n.parent_id)
        if p is None or n.id not in boxes or p.id not in boxes:
            continue
        if p.type == NODE_TYPE_GRID:
            continue                      # grid children place by lon/lat, not on a surface
        (cc, ccols, chalf), (pc, pcols, phalf) = boxes[n.id], boxes[p.id]
        d = float(np.linalg.norm(cc - pc))
        prad = _radius(pcols, phalf)
        sib_dist[p.id].append(d)
        if d > 1e-12 and p.topo in SEATED_TOPOS:
            u = (cc - pc) / d
            reach = _support(pcols, phalf, u, p.geometry)
            creach = _support(ccols, chalf, u, n.geometry)
            crad = _radius(ccols, chalf)
            if crad < 1e-6:
                pass          # a zero-size node is absent, not buried
            elif d + crad <= reach:
                buried.append((n, p, d, reach, creach, "swallowed"))
            elif d < reach:
                buried.append((n, p, d, reach, creach, "centre"))
            elif d < reach + creach:
                buried.append((n, p, d, reach, creach, "surface"))
        if (p.topo in CARTESIAN_TOPOS and prad > 1e-12
                and d / prad > FLUNG_RATIO):
            cand.append((n, p, d, prad))
        # Shear is measured on the child's OWN basis rather than guessed from
        # "is rotated under a stretched parent" -- a spin about the parent's
        # long axis is harmless and must not be reported.
        if any((n.rotate_x, n.rotate_y, n.rotate_z)):
            B = tr.world_basis[tr.row_of_id[n.id]]
            L = np.linalg.norm(B, axis=0)
            if L.min() > 1e-12:
                cos = max(abs(float(B[:, i] @ B[:, j]) / (L[i] * L[j]))
                          for i, j in ((0, 1), (1, 2), (0, 2)))
                if cos > SHEAR_COS:
                    sheared.append((n, p, math.degrees(math.acos(min(cos, 1.0)))))
    # A wide scatter under a small hub is a layout, not a bug. Only escalate a
    # far-flung child when it is absurd in absolute terms, or a clear outlier
    # among its own siblings.
    for n, p, d, prad in cand:
        sibs = sib_dist[p.id]
        med = float(np.median(sibs)) if sibs else d
        outlier = med > 1e-12 and d / med > FLUNG_OUTLIER
        if d / prad > FLUNG_ABSURD or outlier:
            t = max(abs(n.translate_x), abs(n.translate_y), abs(n.translate_z))
            flung.append((n, p, d, prad, t))
            if t > DEGREES_HINT:
                degrees.append(n)
    r["buried"], r["flung"] = buried, flung
    r["sheared"], r["degrees"] = sheared, degrees
    r["flung_considered"] = len(cand)

    # alpha 0 is the correct way to hide a Plot/Surface vertex: hide = 1 would
    # drop it from the polyline or mesh as well, so only flag it elsewhere.
    # A Plot/Surface overlay is drawn from its children, so an alpha-0 vertex --
    # or an alpha-0 hub carrying the polyline -- is the correct idiom there.
    # hide = 1 would drop the node from the overlay as well.
    OVERLAY = {16, 17}
    r["alpha_carriers"] = [
        n for n in nodes
        if n.color_a == 0 and not n.hide
        and n.type not in NON_VISUAL_TYPES
        and n.topo not in OVERLAY
        and getattr(by_id.get(n.parent_id), "topo", None) not in OVERLAY]

    ids = set(by_id)
    r["dead_links"] = [n for n in nodes if n.type == NODE_TYPE_LINK
                       and (n.parent_id not in ids
                            or int(n.extras.get("child_id", 0) or 0) not in ids)]

    # --- which way does everything point? ---------------------------------
    # A position check cannot see this: correctly placed rods can still be
    # aimed into a flat fan. Skipped entirely when the scene has no directional
    # geometry, which is what keeps a 400k-point scan fast.
    aimable = [n for n in nodes
               if n.geometry in DIRECTIONAL_GEOMETRIES
               and n.type not in NON_VISUAL_TYPES
               and n.type != NODE_TYPE_LINK      # a link aims from its endpoints
               and n.type != NODE_TYPE_GRID
               and not n.hide]
    aim, fighting = [], []
    if aimable:
        # A node with no rotation of its own IS already at its placed aim, so
        # only the rotated ones need the counterfactual pass.
        rotated = [n for n in aimable
                   if any((n.rotate_x, n.rotate_y, n.rotate_z))]
        ref = _placed_aim(nodes, base_scale, rotated) if rotated else {}
        for n in aimable:
            z = tr.world_basis[tr.row_of_id[n.id]][:, 2]
            nz = float(np.linalg.norm(z))
            if nz < 1e-12:
                continue
            z = z / nz
            placed = ref.get(n.id, z)
            dev = math.degrees(math.acos(min(1.0, max(-1.0, float(z @ placed)))))
            p = by_id.get(n.parent_id)
            aims = p is not None and p.topo in AIMING_TOPOS
            aim.append((n, p, z, dev, aims))
            if aims and dev > AIM_FIGHT_DEG:
                # Reported, but NOT as a fault. Measured across the example
                # gallery, "rotated off the aim its parent gave it" is
                # indistinguishable from a deliberate lean: an armillary
                # sphere's pins lie along their ring at rotate_x = -90, an
                # inclined orrery's planes are tilted on purpose. Both look
                # exactly like the bug. So this is information, not a verdict.
                fighting.append((n, p, dev, placed, z))
    # Spokes that were placed by hand and aimed by hand: their positions fan out
    # around the parent, but every one of them points the same way. That is the
    # "flat stacked fan" -- correct positions, wrong bodies -- and it is
    # invisible to every other check here.
    #
    # Four conditions together, because each one alone has a legitimate scene
    # behind it, all found in the example gallery:
    #   parent is plainly Cartesian   - a Rod parent threads children along its
    #                                   own axis, so shared aim is correct there
    #   the children carry rotations  - nobody was trying to aim them by hand if
    #                                   every rotate field is 0 (a ring of pins
    #                                   lying flat is authored exactly that way)
    #   positions fan out > 45 deg    - otherwise it is a row, not a fan
    #   some sibling sits ALONG the   - a forest of upright trees is spread in
    #   shared direction                the plane perpendicular to its shared
    #                                   +Z, so this never happens there
    fan = []
    sibs = defaultdict(list)
    for a in aim:
        p = a[1]
        if (p is not None and p.topo in CARTESIAN_TOPOS
                and any((a[0].rotate_x, a[0].rotate_y, a[0].rotate_z))):
            sibs[a[0].parent_id].append(a)
    for pid, items in sibs.items():
        if len(items) < 3:
            continue
        zs = np.array([a[2] for a in items])
        if float(np.abs(zs @ zs[0]).min()) < math.cos(math.radians(5.0)):
            continue                       # they do not share one direction
        p = by_id[pid]
        pc = tr.world_pos[tr.row_of_id[pid]]
        dirs = []
        for a in items:
            v = tr.world_pos[tr.row_of_id[a[0].id]] - pc
            d = float(np.linalg.norm(v))
            if d > 1e-9:
                dirs.append(v / d)
        if len(dirs) < 3:
            continue
        dirs = np.array(dirs)
        spread = math.degrees(math.acos(min(1.0, max(-1.0,
                                                     float((dirs @ dirs.T).min())))))
        along = float(np.abs(dirs @ zs[0]).max())
        if spread > 45.0 and along > 0.5:
            fan.append((p, len(items), spread, zs[0]))
    r["aim"], r["fighting_aim"], r["aim_fan"] = aim, fighting, fan

    # what would move if View > Enforce Minimum Glyph Size were switched on
    floored = []
    for n in nodes:
        if n.type in NON_VISUAL_TYPES or n.type == NODE_TYPE_GRID or n.hide:
            continue
        s = np.array([n.scale_x, n.scale_y, n.scale_z]) * base_scale
        if s.min() <= 0 or s.min() >= DEFAULT_SCALE_FLOOR:
            continue
        after = np.maximum(s, DEFAULT_SCALE_FLOOR)
        # the shape changes if the axes are lifted by *different* factors
        lift = after / s
        distorts = float(lift.max() / lift.min()) > 1.01
        floored.append((n, float(s.max() / s.min()),
                        float(after.max() / after.min()), distorts))
    r["floored"] = floored

    # roots and their subtree bounding spheres
    roots = [n for n in nodes if not n.parent_id and n.id in boxes
             and n.type != NODE_TYPE_GRID]
    spheres = []
    for root in roots:
        centre = boxes[root.id][0]
        rad, stack, seen = 0.0, [root], {root.id}
        while stack:
            cur = stack.pop()
            if cur.id in boxes:
                c, cols, half = boxes[cur.id]
                rad = max(rad, float(np.linalg.norm(c - centre)) + _radius(cols, half))
            for k in kids.get(cur.id, []):
                if k.id not in seen:
                    seen.add(k.id)
                    stack.append(k)
        spheres.append((root, centre, rad, len(seen)))
    r["root_spheres"] = spheres
    overlaps, touching_roots = [], []
    for i in range(len(spheres)):
        for j in range(i + 1, len(spheres)):
            _, c1, r1, _ = spheres[i]
            _, c2, r2, _ = spheres[j]
            gap = float(np.linalg.norm(c1 - c2)) - r1 - r2
            if gap < -min(r1, r2):
                overlaps.append((spheres[i][0], spheres[j][0], gap))
            elif gap < 0:
                touching_roots.append(1)
    overlaps.sort(key=lambda o: o[2])
    r["root_overlaps"] = overlaps
    r["root_envelope_touch"] = len(touching_roots)

    # rendered size per hierarchy level
    per_level = defaultdict(list)
    for n in nodes:
        if n.id in boxes:
            c, cols, half = boxes[n.id]
            per_level[n.branch_level].append(_radius(cols, half))
    r["per_level"] = per_level

    pts = np.array([boxes[i][0] for i in boxes]) if boxes else np.zeros((1, 3))
    r["bbox"] = (pts.min(axis=0), pts.max(axis=0))

    # Global Scale comparison
    tr3 = compute_world_transforms(nodes, base_scale * 3.0)
    moved = 0
    worst = 0.0
    for n in nodes:
        a = tr.world_pos[tr.row_of_id[n.id]]
        b = tr3.world_pos[tr3.row_of_id[n.id]]
        d = float(np.linalg.norm(a - b))
        if d > 1e-9:
            moved += 1
            worst = max(worst, d)
    r["gs_moved"], r["gs_worst"] = moved, worst
    return r


# --------------------------------------------------------------------- report

def _vec(v):
    return f"({v[0]:+.3f}, {v[1]:+.3f}, {v[2]:+.3f})"


def _aim_section(r, say, lim):
    """Which way every directional glyph points, grouped by parent.

    This is the answer to "are my spokes pointing outward?" as a number, so it
    does not have to be guessed from a render -- which is exactly the check the
    workflow asks for and nothing else here could perform.
    """
    if not r["aim"]:
        return
    by_id = r["by_id"]
    say("AIM")
    say("  +Z is the pointing axis of a cone, pin, cylinder, torus, ring or flat")
    say("  marker. Sphere, Point, Torus, Ztorus and Cube parents turn each child's")
    say("  +Z outward from its own translate; rotate_x/y/z then turns it off that.")

    groups = defaultdict(list)
    for a in r["aim"]:
        groups[a[0].parent_id].append(a)

    for pid, items in sorted(groups.items()):
        p = by_id.get(pid)
        n = len(items)
        word = "child" if n == 1 else "children"
        if p is not None and p.topo in AIMING_TOPOS:
            worst = max(a[3] for a in items)
            verdict = ("all at the aim placement gave them"
                       if worst <= 1e-6 else
                       f"up to {worst:.1f} deg off it")
            say(f"  parent {pid} ({TOPO_NAMES.get(p.topo, p.topo)}) aims its "
                f"{n} directional {word} -- {verdict}")
        elif p is None:
            say(f"  {n} directional root {word} -- no parent to aim "
                f"{'it' if n == 1 else 'them'}; +Z comes from rotate_* alone")
        else:
            say(f"  parent {pid} ({TOPO_NAMES.get(p.topo, p.topo)}) does not aim "
                f"its {n} directional {word}; +Z comes from rotate_* alone")
        for a in (items if lim is None else items[:lim]):
            say(f"      id {a[0].id:<6} +Z {_vec(a[2])}  "
                f"{GEO_NAMES.get(a[0].geometry, a[0].geometry)}")
        if lim is not None and n > lim:
            say(f"      ... {n - lim} more (--all to list)")
        off = [f for f in r["fighting_aim"] if f[1] is not None and f[1].id == pid]
        if off:
            say(f"      ^ {len(off)} of these carry a rotation that turns them off "
                f"that aim,")
            say(f"        by up to {max(f[2] for f in off):.0f} deg. That is how a "
                f"deliberate lean is")
            say("        authored AND how the classic mistake looks, so it is stated,")
            say("        not judged: rotate_* composes on top of the placed aim rather")
            say("        than replacing it. If you meant these to point outward, set")
            say("        every rotate field to 0 and put the angle in translate_x.")
    say("")


def report(r, show_all=False):
    out = []
    say = out.append
    lim = None if show_all else SHOW
    nodes = r["nodes"]
    drawable = len(r["boxes"])
    roots = len(r["root_spheres"])

    say(f"GlyphViz extent report -- {os.path.basename(r['path'])}")
    say(f"  {len(nodes):,} rows | {drawable:,} drawable | {roots:,} roots | "
        f"Global Scale {r['base_scale']:g}")
    say("  sizes are rendered half-extents from each geometry's own measured "
        "silhouette:")
    say("  every glyph fits inside RADIUS 1, so a cube reaches 0.577 and a Pin "
        "is 0.1 wide by 1.1 tall")
    say("")

    problems = 0

    def block(items, sing, plur, fmt):
        nonlocal problems
        if not items:
            return
        problems += 1
        say(f"  ! {len(items)} {sing if len(items) == 1 else plur}")
        for it in (items if lim is None else items[:lim]):
            say("      " + fmt(it))
        if lim is not None and len(items) > lim:
            say(f"      ... {len(items) - lim} more (--all to list)")
        say("")

    say("PROBLEMS")
    swallowed = [b for b in r["buried"] if b[5] == "swallowed"]
    inside = [b for b in r["buried"] if b[5] == "centre"]
    touching = [b for b in r["buried"] if b[5] == "surface"]
    block(sorted(swallowed, key=lambda b: b[2] / max(b[3], 1e-9)),
          "child is completely inside its parent and cannot be seen",
          "children are completely inside their parent and cannot be seen",
          lambda b: (f"id {b[0].id} ({GEO_NAMES.get(b[0].geometry, b[0].geometry)}) "
                     f"is {b[2]:.3f} from parent {b[1].id}, whose surface that way is "
                     f"at {b[3]:.3f} -- {b[2] / max(b[3], 1e-9):.0%} of the way out; "
                     f"clear it at {b[3] + b[4]:.3f}"))
    block(sorted(inside, key=lambda b: b[2] / max(b[3], 1e-9)),
          "child has its centre inside its parent, so only the part that pokes out shows",
          "children have their centre inside their parent, so only the part that pokes out shows",
          lambda b: (f"id {b[0].id} ({GEO_NAMES.get(b[0].geometry, b[0].geometry)}) "
                     f"is {b[2]:.3f} from parent {b[1].id}, whose surface that way is "
                     f"at {b[3]:.3f} -- {b[2] / max(b[3], 1e-9):.0%} of the way out; "
                     f"clear it at {b[3] + b[4]:.3f}"))
    block(sorted(r["flung"], key=lambda f: -f[2] / max(f[3], 1e-9)),
          "child sits far outside its parent's layout",
          "children sit far outside their parent's layout",
          lambda f: (f"id {f[0].id} is {f[2]:.1f} from parent {f[1].id} "
                     f"(topo {TOPO_NAMES.get(f[1].topo, f[1].topo)}, radius {f[3]:.2f}) "
                     f"-- {f[2] / max(f[3], 1e-9):.0f}x, largest translate {f[4]:g}"))
    if r["degrees"]:
        say(f"      ^ {len(r['degrees'])} of those hang off a Cartesian parent with a "
            f"translate over {DEGREES_HINT:g}.")
        say("        If those numbers were meant as degrees, this parent's topology "
            "reads them as distances.")
        say("        Either give the parent an angular topology, or set its "
            "topo_scale (1/180 for degrees).")
        say("")
    block(r["sheared"],
          "rotated child of a non-uniformly scaled parent will shear",
          "rotated children of non-uniformly scaled parents will shear",
          lambda s: (f"id {s[0].id} under parent {s[1].id}: its own axes meet at "
                     f"{s[2]:.0f} deg instead of 90 -- rotating under a stretched "
                     f"parent skews it"))
    block(sorted(r["aim_fan"], key=lambda f: -f[1]),
          "set of glyphs was rotated by hand and all ended up pointing the same way",
          "sets of glyphs were rotated by hand and all ended up pointing the same way",
          lambda f: (f"parent {f[0].id} (topo {TOPO_NAMES.get(f[0].topo, f[0].topo)}): "
                     f"all {f[1]} directional children point {_vec(f[3])} while their "
                     f"positions fan out over {f[2]:.0f} deg around it"))
    if r["aim_fan"]:
        say("      If they were meant to radiate, they do not -- this is the flat")
        say("      stacked fan: right positions, wrong bodies. Aiming is the")
        say("      topology's job. Give the parent topo 2 (Sphere) or 7 (Point), put")
        say("      each child's bearing in its translate_x, and set every rotate")
        say("      field to 0.")
        say("")
    block(r["alpha_carriers"],
          "node has color_a = 0 but is not hidden",
          "nodes have color_a = 0 but are not hidden",
          lambda n: (f"id {n.id} -- alpha 0 still draws and still takes clicks; "
                     f"use hide = 1 for a carrier"))
    block(r["dead_links"],
          "link has an end that does not resolve, so it will not draw",
          "links have an end that does not resolve, so they will not draw",
          lambda n: f"id {n.id} -- parent {n.parent_id}, child_id "
                    f"{n.extras.get('child_id', '(missing)')}")
    distorting = [f for f in r["floored"] if f[3]]
    if distorting:
        problems += 1
        say(f"  ! {len(r['floored'])} "
            f"{'node' if len(r['floored']) == 1 else 'nodes'} would change if "
            f"View > Enforce Minimum Glyph Size were switched on")
        say(f"      that clamp is OFF by default, so this is not a bug today; "
            f"{len(distorting)} of these would also lose their proportions")
        for n, b, a, _ in (distorting if lim is None else distorting[:lim]):
            say(f"      id {n.id} aspect {b:.1f}:1 would become {a:.1f}:1 "
                f"-- a counter-scaled child cannot survive that clamp")
        if lim is not None and len(distorting) > lim:
            say(f"      ... {len(distorting) - lim} more (--all to list)")
        say("")

    if not problems:
        say("  none found -- no buried or flung children, no shear, no dead links,")
        say("  no alpha-0 carriers, no root overlaps, no hand-aimed fans,")
        say("  nothing riding the size clamp.")
        say("")

    _aim_section(r, say, lim)

    lo, hi = r["bbox"]
    say("SCENE")
    say(f"  extents      x {lo[0]:>9.2f} ... {hi[0]:<9.2f}  "
        f"y {lo[1]:>9.2f} ... {hi[1]:<9.2f}  z {lo[2]:>9.2f} ... {hi[2]:<9.2f}")
    if r["root_spheres"]:
        rads = sorted(s[2] for s in r["root_spheres"])
        say(f"  root glyphs  {len(rads)}, bounding radius "
            f"{rads[0]:.2f} ... {rads[-1]:.2f}")
    if touching:
        say(f"  contact      {len(touching):,} children overlap their parent's surface "
            f"without their")
        say("               centre going inside it -- normal when parts are meant to touch")
    if r["root_overlaps"]:
        w = r["root_overlaps"][0]
        say(f"  crowding     {len(r['root_overlaps'])} root pairs have interpenetrating "
            f"bounding spheres,")
        say(f"               worst roots {w[0].id} and {w[1].id} by {-w[2]:.2f}. A bounding "
            f"sphere over a")
        say("               sprawling glyph over-reports, so treat this as a hint to look, "
            "not a defect.")
    if r["flung_considered"]:
        say(f"  spread       {r['flung_considered']:,} children sit over "
            f"{FLUNG_RATIO:g}x their parent's radius out;")
        say(f"               {len(r['flung'])} of those look wrong rather than "
            f"deliberate (see above)")
    say("  rendered half-extent by branch_level")
    for lvl in sorted(r["per_level"]):
        v = r["per_level"][lvl]
        say(f"      level {lvl:<3d} {min(v):8.3f} ... {max(v):<8.3f}  {len(v):>7,} nodes")
    say("")

    say(f"GLOBAL SCALE {r['base_scale']:g} -> {r['base_scale'] * 3:g}")
    say(f"  every glyph's rendered size scales by 3")
    say(f"  {r['gs_moved']:,} of {len(nodes):,} nodes also change world position "
        f"(largest move {r['gs_worst']:.2f})")
    say("  root and Cartesian coordinates do not move; surface-riding placement does,")
    say("  so a distance written as parent scale and one written as translate drift apart.")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Rendered sizes, seating and scene problems for a GlyphViz node CSV.")
    ap.add_argument("csv", help="the scene's *_gv_node.csv")
    ap.add_argument("--base-scale", type=float, default=1.0,
                    help="Global Scale to evaluate at (viewer default 1.0)")
    ap.add_argument("--all", action="store_true", help="list every problem row")
    a = ap.parse_args(argv)
    print(report(analyse(a.csv, a.base_scale), a.all))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
