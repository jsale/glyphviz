"""
Epicycle chains: a Fourier series built out of nested TOPO_TORUS parents.

A chain of Torus-topology nodes, each the child of the last, each spinning its
own ``translate_x``, is exactly a truncated Fourier series -- the pen at the end
traces the sum of the arms. This module owns that construction: the design
model, the node builder, the path tracer, the spectrum analysis and the CSV
writer. Everything here is Qt-free; ``glyphviz_gl.epicycle_dialog`` is a GUI on
top of it, and ``examples/Fourier_Epicycles_Example`` generates its scenes from
it, so there is exactly one implementation of the math.

THE THREE MECHANISMS
--------------------
1. **The harmonic ladder** (``Arm.rate_x``). Each level's ``translate_x`` is an
   angle in its PARENT's rotating frame, so the angles compose down the chain::

       h_1 = r_1
       h_k = h_{k-1} + (-1)^(k-1) * r_k      (+ odd levels, - even ones)

   The alternating sign is real: ``rotate = (90, 90, 0)`` on every level cancels
   the base rotation TOPO_TORUS applies to its children, and the cancellation
   leaves the frame's handedness flipped at each step. Without that rotation the
   rings tip 90 degrees out of plane at every level, the chain corkscrews off
   the z = 0 plane, and the ladder collapses.

2. **Plane tilt** (``Arm.tilt``) -- the first way out of the plane. Measured:
   adding t degrees to a node's ``rotate_y`` tips its ring plane by exactly t,
   while ``rotate_x`` and ``rotate_z`` leave it alone. So each arm can orbit in
   its own inclined plane, which is a classical orrery with inclined orbits.

3. **The tube** (``Arm.tube`` + ``rate_y``/``phase_y``) -- the second way out,
   and the more interesting one. TOPO_TORUS places a child at (orbit angle u,
   tube angle v), so a fat tube gives the arm a SECOND circle riding the first.
   In spectrum terms it is a sideband generator: an arm at harmonic h with tube
   rate r_y contributes h, h - r_y and h + r_y in the plane and a pure r_y out
   of it. That is what turns a flat rosette into a genuine space curve.

UNITS, AND THE ONE CONVERSION
-----------------------------
``Arm.length`` and ``Arm.tube`` are WORLD units, because that is what an author
can reason about. The engine works in the parent's local frame, where the torus
base radius is 1 and everything is then multiplied by the parent's cumulative
scale -- so this module converts:

    node scale    = length[k+1] / length[k]     (telescoping, so the product
                                                 lands on each arm's length)
    parent ratio  = tube[k] / length[k]         (see _tube_ratio -- the tube is
                                                 the PARENT's torus thickness,
                                                 so the drawn ring is the
                                                 circle the child rides)

A node's rendered torus IS the circle its own child rides, and its radius is
that node's cumulative scale -- which is why ``length[k]`` is set by the scale
of the node one level UP, not by the node it belongs to.

WHAT THE CURVE IS CALLED
------------------------
Not a Lissajous figure -- that is a product of two independent 1-D oscillations.
This is a sum of rotating vectors: the epitrochoid family. Two terms give the
textbook epitrochoid / hypotrochoid (the Spirograph curve); n terms give an
epicyclic curve, or a truncated Fourier series curve. Adding tube and tilt takes
it off the plane, where the two-term case is a torus knot.
"""

from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Iterable, Sequence

from .node import Node, ROTATION_MODE_EULER_XYZ
from .scene import Scene

__all__ = [
    "Arm", "EpicycleDesign", "PRESETS", "preset", "random_design",
    "harmonics_of", "closure_frames", "build_nodes", "trace_path",
    "spectrum", "build_channels", "write_scene", "describe",
    "MAX_ARMS", "MIN_ARMS",
]

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

MIN_ARMS = 2
MAX_ARMS = 8

#: Torus glyph thickness. minor radius = ratio * size, so the ring a node wears
#: is a hairline at the default -- these are orbits, not doughnuts.
DEFAULT_RING_RATIO = 0.02

#: Trail beads are GEO_POINT sprites; `ratio * 20` px is the one control that
#: resizes them (scale cannot -- a point sprite ignores the modelview scale).
TRAIL_BEAD_RATIO = 0.10
#: The Plot parent's ratio, which sets the POLYLINE width the same way.
TRAIL_LINE_RATIO = 0.15

#: Beads sharing one alpha channel in a self-drawing scene. Keeps the tracks
#: file to frames/GROUP columns instead of one per bead; the cost is the line
#: lagging the pen by at most this many frames. It lags rather than leads
#: because a group lights when its LAST bead is reached -- a line running ahead
#: of the pen would be drawing a curve it has not travelled yet.
DEFAULT_BEAD_GROUP = 3

#: Upper bound for closure_frames' search before it gives up and says "does not
#: close". 3600 frames is two minutes at 30 fps -- past that, a trail is a
#: smear rather than a figure.
MAX_CLOSURE_FRAMES = 3600

#: Hard cap on trail beads, so a designer slider cannot author a 50k-node scene
#: by accident. 1440 beads at quarter-degree steps is already smoother than the
#: 3 px polyline can show.
MAX_TRAIL_POINTS = 1440

# Geometry / topology / type ids (see references/node-csv-format.md)
G_SPHERE, G_TORUS, G_CYLINDER, G_POINT = 3, 7, 19, 22
G_TORUS_WIRE = 6
T_NONE, T_TORUS, T_PLOT = 0, 3, 16
TYPE_WORLD, TYPE_GLYPH, TYPE_LINK = 0, 5, 7

# Palette -- the GlyphViz brand family, matching Topology_Animation_Examples.
BACKGROUND = (14, 14, 26, 255)
RING_COLORS = (
    (99, 140, 255, 150),     # indigo
    (38, 198, 181, 150),     # teal
    (167, 139, 250, 150),    # violet
    (255, 111, 97, 150),     # coral
    (120, 200, 120, 150),    # green
    (240, 160, 220, 150),    # pink
    (200, 200, 120, 150),    # olive
    (140, 200, 255, 150),    # ice
)
ARM_COLOR = (150, 160, 190, 220)
PEN_COLOR = (255, 255, 255, 255)
TRAIL_COLOR = (255, 193, 7, 235)


# --------------------------------------------------------------------------
# Design model
# --------------------------------------------------------------------------

@dataclass
class Arm:
    """One term of the series -- one circle, and the node that rides it.

    ``length`` and ``tube`` are world units; everything else is degrees, with
    the rates in degrees per frame.
    """

    length: float = 10.0     #: world radius of this arm's orbit circle
    rate_x: float = 1.0      #: orbit angle, deg/frame -- this is the harmonic
    phase_x: float = 0.0     #: starting orbit angle
    rate_y: float = 0.0      #: tube angle, deg/frame -- the out-of-plane spin
    phase_y: float = 0.0     #: starting tube angle
    #: World radius of a second circle this arm rides, around the torus tube.
    #: 0 = a flat arm. Carved OUT of `length` rather than added to it (see
    #: _tube_ratio), so the arm stays `length` long at phase_y 0 and the drawn
    #: ring is the tube the child actually travels. Capped at 0.95 * length.
    tube: float = 0.0
    tilt: float = 0.0        #: deg this arm's plane leans out of the last one

    def clamped(self) -> "Arm":
        return replace(
            self,
            length=max(1e-3, float(self.length)),
            tube=max(0.0, float(self.tube)),
        )


@dataclass
class EpicycleDesign:
    """A whole scene: the chain, and how to dress it."""

    name: str = "Epicycles"
    arms: list[Arm] = field(default_factory=lambda: [Arm(), Arm(rate_x=-1.0)])
    pen_size: float = 1.2            #: world radius of the pen sphere
    ring_ratio: float = DEFAULT_RING_RATIO
    show_rings: bool = True          #: draw each arm's orbit as a torus glyph
    show_arms: bool = True           #: draw the linkage as type-7 Link rods
    arm_ratio: float = 0.25          #: linkage rod thickness, world units
    trail: bool = True
    trail_points: int = 720
    self_drawing: bool = False       #: Channels + a per-bead alpha step
    bead_group: int = DEFAULT_BEAD_GROUP
    frames: int | None = None        #: None = the computed closure period

    # -- derived -------------------------------------------------------
    @property
    def n_arms(self) -> int:
        return len(self.arms)

    def normalized(self) -> "EpicycleDesign":
        return replace(self, arms=[a.clamped() for a in self.arms])

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "arms"}
        d["arms"] = [a.__dict__.copy() for a in self.arms]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EpicycleDesign":
        data = dict(data)
        arms = [Arm(**a) for a in data.pop("arms", [])]
        known = {f for f in cls().__dict__ if f != "arms"}
        return cls(arms=arms or [Arm()],
                   **{k: v for k, v in data.items() if k in known})


# --------------------------------------------------------------------------
# The ladder, and when the curve closes
# --------------------------------------------------------------------------

def harmonics_of(rates: Sequence[float]) -> list[float]:
    """World harmonic of each arm. ``h_k = h_{k-1} + (-1)^(k-1) * r_k``.

    The sign alternates because each level's ``rotate = (90, 90, 0)`` cancels
    TOPO_TORUS's base rotation and leaves the frame handedness flipped. Verified
    against the engine across seven rate vectors; see tests/test_epicycles.py.
    """
    out: list[float] = []
    h = 0.0
    for k, r in enumerate(rates, start=1):
        h += ((-1) ** (k - 1)) * float(r)
        out.append(h)
    return out


def _as_fraction(value: float, limit: int = 360) -> Fraction:
    return Fraction(value).limit_denominator(limit)


def closure_frames(design: EpicycleDesign,
                   cap: int = MAX_CLOSURE_FRAMES) -> int | None:
    """Frames after which every angle is back where it started, or None.

    An angle advancing r deg/frame returns after N frames iff ``r*N`` is a
    multiple of 360. Over all the rates at once that is
    ``N = 360 / gcd(rates)``, computed exactly in rationals so 0.5 or 1/3 give
    the right answer rather than a float near-miss. Returns None when the
    answer would exceed ``cap`` (or when nothing moves at all).
    """
    rates = [r for arm in design.arms for r in (arm.rate_x, arm.rate_y)
             if abs(r) > 1e-12]
    if not rates:
        return None
    g = _as_fraction(abs(rates[0]))
    for r in rates[1:]:
        g = Fraction(math.gcd(g.numerator, _as_fraction(abs(r)).numerator),
                     math.lcm(g.denominator, _as_fraction(abs(r)).denominator))
    if g == 0:
        return None
    n = Fraction(360) / g
    if n.denominator != 1:
        n = Fraction(math.ceil(n))
    n = int(n)
    return n if 0 < n <= cap else None


def frame_count(design: EpicycleDesign) -> int:
    """The frame count a scene should actually use: the author's override, the
    closure period, or a sane fallback for a curve that never closes."""
    if design.frames:
        return int(design.frames)
    return closure_frames(design) or 720


# --------------------------------------------------------------------------
# Node construction
# --------------------------------------------------------------------------

#: A tube may not swallow its own orbit: at ratio 1 the torus degenerates to a
#: sphere and the arm's inner reach passes through the hub.
MAX_TUBE_FRACTION = 0.95

#: Above this tube fraction a ring is drawn as WIREFRAME instead of solid.
#: A hairline orbit ring is a line and reads fine solid; a fat tube is a
#: SURFACE, and a solid one at 0.75 is an opaque doughnut that hides the very
#: mechanism it exists to show (measured by rendering it — it came out as a
#: featureless ball). Wire also matches the series convention where wireframe
#: means scaffolding.
TUBE_WIRE_THRESHOLD = 0.15


def _tube_ratio(design: "EpicycleDesign", k: int) -> float:
    """The `ratio` the node one level ABOVE arm k must wear.

    A torus glyph's tube radius is ``ratio * size``, and ``_torus_offset`` reads
    that SAME ratio to place children -- so setting the parent's ratio to the
    tube fraction makes the drawn ring literally be the circle its child rides,
    instead of a hairline next to an invisible one. That equality is the whole
    reason the tube is expressed this way rather than through the child's
    ``translate_z`` (which also works, but draws nothing and pushes the arm
    LONGER than its authored length).

    With ratio = T the child sits at local radius ``(1 - T) + T*cos v``: exactly
    1 at ``v = 0``, so ``Arm.length`` stays the true arm length, and the child
    sweeps a circle of world radius ``T * length`` around it.
    """
    if k >= len(design.arms):
        return design.ring_ratio
    arm = design.arms[k]
    if arm.tube <= 0.0 or arm.length <= 0.0:
        return design.ring_ratio
    return min(MAX_TUBE_FRACTION, max(design.ring_ratio, arm.tube / arm.length))


def _node(**kw) -> Node:
    base = dict(
        id=0, type=TYPE_GLYPH, parent_id=0, branch_level=0,
        translate_x=0.0, translate_y=0.0, translate_z=0.0,
        rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
        scale_x=1.0, scale_y=1.0, scale_z=1.0,
        color_r=255, color_g=255, color_b=255, color_a=255,
        geometry=G_SPHERE, hide=0, topo=T_NONE, ratio=0.1,
        # Euler XYZ and ANTz Heading/Tilt/Roll agree exactly at the rotations
        # this construction uses; Euler is the one that is friendlier to
        # hand-edit in the Properties panel afterwards.
        rotation_mode=ROTATION_MODE_EULER_XYZ,
    )
    base.update(kw)
    node = Node(**base)
    node.extras.setdefault("child_id", 0)
    node.extras.setdefault("ch_input_id", 0)
    return node


def _chain_nodes(design: EpicycleDesign, start_id: int, parent_id: int,
                 base_branch: int, animated: bool) -> list[Node]:
    """The hub plus one node per arm, with the linkage rods.

    Two indexing facts worth stating once, because both are easy to get
    backwards:

    * ``arms[k].length`` is the length of the arm leading TO node k, and it is
      produced by the SCALE of the node one level up -- a node's torus is the
      circle its child rides.
    * ``arms[k].tilt`` tips that same arm, so it is written as ``rotate_y`` on
      the PARENT, whose ring plane is the one being tipped.
    """
    arms = design.arms
    n = len(arms)
    def ring_geo_for(k: int) -> int:
        """Solid for a hairline orbit ring, wire once it is a real tube."""
        if not design.show_rings:
            return G_TORUS_WIRE
        return (G_TORUS_WIRE if _tube_ratio(design, k) > TUBE_WIRE_THRESHOLD
                else G_TORUS)

    nodes: list[Node] = []

    hub = _node(
        id=start_id, parent_id=parent_id, branch_level=base_branch,
        topo=T_TORUS, geometry=ring_geo_for(0), ratio=_tube_ratio(design, 0),
        scale_x=arms[0].length, scale_y=arms[0].length, scale_z=arms[0].length,
        # The hub is a plain root: no base rotation to cancel, so arm 0's tilt
        # is its whole rotate_y.
        rotate_y=arms[0].tilt,
        color_r=RING_COLORS[0][0], color_g=RING_COLORS[0][1],
        color_b=RING_COLORS[0][2], color_a=RING_COLORS[0][3],
        hide=0 if design.show_rings else 0,
    )
    hub.text = (f"hub - never moves. Its torus IS the circle arm 1 rides; the "
                f"radius is its own scale, {arms[0].length:g} = arm 1's length")
    nodes.append(hub)

    for k, arm in enumerate(arms):
        last = (k == n - 1)
        # Telescoping: this node's scale carries the frame from arm k's length
        # to arm k+1's, so the cumulative product lands on each arm's length.
        if last:
            scale = design.pen_size / arm.length
        else:
            scale = arms[k + 1].length / arm.length
        nodes.append(_node(
            id=start_id + 1 + k,
            parent_id=start_id + k,
            branch_level=base_branch + 1 + k,
            topo=T_TORUS,
            geometry=G_SPHERE if last else ring_geo_for(k + 1),
            # The NEXT arm's tube, because a node's `ratio` is what
            # _torus_offset reads for its CHILDREN's tube radius -- the same
            # reason the next arm's tilt rides on this node's rotate_y.
            ratio=_tube_ratio(design, k + 1),
            translate_x=arm.phase_x, translate_y=arm.phase_y, translate_z=0.0,
            # 90/90 is the cancellation; the NEXT arm's tilt rides on rotate_y,
            # because this node's ring plane is the one that arm orbits in.
            rotate_x=90.0,
            rotate_y=90.0 + (0.0 if last else arms[k + 1].tilt),
            scale_x=scale, scale_y=scale, scale_z=scale,
            translate_rate_x=0.0 if animated else arm.rate_x,
            translate_rate_y=0.0 if animated else arm.rate_y,
            color_r=(PEN_COLOR if last else RING_COLORS[(k + 1) % len(RING_COLORS)])[0],
            color_g=(PEN_COLOR if last else RING_COLORS[(k + 1) % len(RING_COLORS)])[1],
            color_b=(PEN_COLOR if last else RING_COLORS[(k + 1) % len(RING_COLORS)])[2],
            color_a=(PEN_COLOR if last else RING_COLORS[(k + 1) % len(RING_COLORS)])[3],
        ))

    harms = harmonics_of([a.rate_x for a in arms])
    for k, (arm, node) in enumerate(zip(arms, nodes[1:])):
        last = (k == n - 1)
        bits = [f"arm {k + 1}: harmonic {_num(harms[k])}",
                f"length {arm.length:g}",
                f"rate_x {arm.rate_x:+g}"]
        if arm.phase_x:
            bits.append(f"phase {arm.phase_x:g} deg")
        if arm.tube:
            bits.append(f"tube radius {arm.tube:g} at rate_y {arm.rate_y:+g} "
                        f"(sidebands at {_num(harms[k] - arm.rate_y)} and "
                        f"{_num(harms[k] + arm.rate_y)})")
        if arm.tilt:
            bits.append(f"plane tilted {arm.tilt:g} deg")
        node.text = ("pen - " if last else "") + ", ".join(bits)

    if design.show_arms:
        for k in range(n):
            a_id = start_id + k
            b_id = start_id + 1 + k
            link = _node(
                id=start_id + 1 + n + k, parent_id=a_id,
                branch_level=base_branch + 1 + k,
                type=TYPE_LINK, geometry=G_CYLINDER, ratio=design.arm_ratio,
                color_r=ARM_COLOR[0], color_g=ARM_COLOR[1],
                color_b=ARM_COLOR[2], color_a=ARM_COLOR[3],
            )
            link.extras["child_id"] = b_id
            link.text = (f"arm {k + 1} rod - a type=7 Link wearing Cylinder "
                         f"geometry, stretched between the two ring centres")
            nodes.append(link)
    return nodes


def _num(v: float) -> str:
    return f"{v:g}"


def trail_sampling(design: EpicycleDesign, frames: int) -> tuple[int, int]:
    """(frame step between beads, bead count) -- the ONE place the trail's
    sampling is decided, so the node builder and the alpha channels cannot
    disagree about which frame a given bead belongs to. They did, briefly:
    recomputing the step from the bead count instead of sharing it lit each
    group at the wrong moment whenever frames was not a multiple of it."""
    points = min(int(design.trail_points), MAX_TRAIL_POINTS, max(1, frames))
    step = max(1, frames // max(1, points))
    return step, len(range(0, frames, step))


def trace_path(design: EpicycleDesign, frames: int,
               base_scale: float = 1.0) -> list[tuple[float, float, float]]:
    """The pen's world position at each frame, read from the real engine.

    Deliberately NOT a reimplementation of the topology math: it builds a live
    Scene out of the chain and reads ``world_pos``. That is what makes the
    trail land on the curve to CSV write precision rather than approximately,
    and it means tilt/tube/ladder can never drift apart from what renders.
    """
    design = design.normalized()
    nodes = _chain_nodes(design, start_id=1, parent_id=0, base_branch=0,
                         animated=True)
    chain = [n for n in nodes if n.type == TYPE_GLYPH]
    by_id = {n.id: n for n in chain}
    scene = Scene(chain, base_scale=base_scale)
    pen = chain[-1].id
    ids = [n.id for n in chain[1:]]

    pts = []
    for f in range(frames):
        for arm, nid in zip(design.arms, ids):
            node = by_id[nid]
            node.translate_x = arm.phase_x + arm.rate_x * f
            node.translate_y = arm.phase_y + arm.rate_y * f
        scene.invalidate()
        pts.append(scene.world_pos(pen))
    return pts


def _trail_nodes(design: EpicycleDesign, pts: Sequence[tuple], start_id: int,
                 parent_id: int, base_branch: int) -> list[Node]:
    """A transparent Plot parent plus one Point bead per sampled position.

    Three things this depends on, all verified in tests/test_epicycles.py:

    * The Plot parent must be ``color_a = 0``, NOT ``hide = 1`` -- a hidden
      plot parent suppresses the polyline entirely.
    * The polyline takes its COLOUR from each child and its WIDTH from the
      parent's ``ratio * 20`` px.
    * Plot draws through its children in CSV ROW ORDER, which is why the beads
      are emitted frame by frame.
    """
    r, g, b, a = TRAIL_COLOR
    plot = _node(id=start_id, parent_id=parent_id, branch_level=base_branch,
                 topo=T_PLOT, geometry=G_POINT, ratio=TRAIL_LINE_RATIO,
                 color_r=r, color_g=g, color_b=b, color_a=0)
    plot.text = ("trail - a Plot-topology parent; its polyline runs through "
                 "the beads below in CSV row order")
    nodes = [plot]
    for i, (x, y, z) in enumerate(pts):
        ch = (1 + design.n_arms + i // max(1, design.bead_group)
              if design.self_drawing else 0)
        bead = _node(id=start_id + 1 + i, parent_id=start_id,
                     branch_level=base_branch + 1,
                     topo=T_NONE, geometry=G_POINT, ratio=TRAIL_BEAD_RATIO,
                     translate_x=x, translate_y=y, translate_z=z,
                     scale_x=0.2, scale_y=0.2, scale_z=0.2,
                     color_r=r, color_g=g, color_b=b,
                     color_a=0 if design.self_drawing else a)
        bead.extras["ch_input_id"] = ch
        nodes.append(bead)
    return nodes


def build_nodes(design: EpicycleDesign, *, start_id: int = 1,
                parent_id: int = 0, base_branch_level: int = 0,
                include_world: bool = False,
                path: Sequence[tuple] | None = None) -> list[Node]:
    """The whole scene as Node objects, ids allocated from ``start_id``.

    ``include_world`` adds the type=0 row that carries the background colour --
    right for a standalone scene file, wrong for Insert into Scene (the loaded
    scene already has one).
    """
    design = design.normalized()
    nodes: list[Node] = []
    next_id = start_id

    if include_world:
        world = _node(id=next_id, type=TYPE_WORLD, geometry=G_POINT, hide=1,
                      color_r=BACKGROUND[0], color_g=BACKGROUND[1],
                      color_b=BACKGROUND[2], color_a=BACKGROUND[3])
        world.text = "world - the background colour lives on this type=0 row"
        nodes.append(world)
        next_id += 1

    chain = _chain_nodes(design, next_id, parent_id, base_branch_level,
                         animated=design.self_drawing)
    nodes.extend(chain)
    next_id += len(chain)

    if design.self_drawing:
        for k, node in enumerate(n for n in chain if n.type == TYPE_GLYPH):
            if k:                      # skip the hub, which never moves
                node.extras["ch_input_id"] = k

    if design.trail:
        frames = frame_count(design)
        step, _ = trail_sampling(design, frames)
        if path is None:
            path = trace_path(design, frames)
        sampled = [path[f] for f in range(0, frames, step)]
        nodes.extend(_trail_nodes(design, sampled, next_id, parent_id,
                                  base_branch_level))
    return nodes


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

def spectrum(path: Sequence[tuple], top: int = 12,
             floor: float = 1e-4) -> list[tuple[float, float]]:
    """(harmonic, amplitude) of the traced curve's in-plane motion.

    The DFT of ``x + iy`` -- a COMPLEX transform, so it separates +h from -h,
    which is exactly the difference between a term rotating one way and the
    other. Out-of-plane motion does not appear here; ``describe`` reports the
    z extent separately.

    Harmonics come back in the SAME UNITS as ``Arm.rate_x`` -- turns per 360
    frames -- not as raw DFT bins. A path sampled over N frames advances
    ``rate * N`` degrees, so bin k means ``k * 360 / N``; reporting bins
    directly multiplied every harmonic by the number of periods traced, which
    was silently right only for the usual 360-frame case.
    """
    import numpy as np

    n = len(path)
    if n < 4:
        return []
    z = np.array([complex(p[0], p[1]) for p in path])
    f = np.fft.fft(z) / n
    scale = float(np.abs(f).max()) or 1.0
    per_bin = 360.0 / n
    out = []
    for k in np.argsort(-np.abs(f)):
        amp = float(np.abs(f[k]))
        if amp < floor * scale or len(out) >= top:
            break
        bin_index = float(k if k <= n // 2 else k - n)
        out.append((bin_index * per_bin, amp))
    return out


def describe(design: EpicycleDesign, path: Sequence[tuple] | None = None,
             frames: int | None = None) -> dict:
    """A report on what the design actually does -- for the designer's readout
    and for the generated README. Everything measured, nothing predicted."""
    design = design.normalized()
    frames = frames or frame_count(design)
    if path is None:
        path = trace_path(design, frames)
    xs = [p[0] for p in path]
    ys = [p[1] for p in path]
    zs = [p[2] for p in path]
    z_extent = max(zs) - min(zs)
    return {
        "arms": design.n_arms,
        "frames": frames,
        "closes": closure_frames(design),
        "harmonics": harmonics_of([a.rate_x for a in design.arms]),
        "spectrum": spectrum(path),
        "half_span": max(max(abs(v) for v in xs), max(abs(v) for v in ys)),
        "z_extent": z_extent,
        "planar": z_extent < 1e-6,
    }


# --------------------------------------------------------------------------
# Channels (the self-drawing trail)
# --------------------------------------------------------------------------

def build_channels(design: EpicycleDesign, frames: int
                   ) -> tuple[list[tuple[int, int, str]], dict[int, list[float]]]:
    """(ch-map rows, track columns) for a self-drawing scene.

    One channel per arm driving ``translate_x``/``translate_y``, then one alpha
    channel per bead GROUP. Grouping is what keeps the tracks file to a few
    hundred KB instead of several MB; several nodes may share a channel, so a
    group is just N beads pointing at the same ``ch_input_id``.
    """
    chmap: list[tuple[int, int, str]] = []
    tracks: dict[int, list[float]] = {}
    track_id = 1

    for k, arm in enumerate(design.arms, start=1):
        tracks[track_id] = [arm.phase_x + arm.rate_x * f for f in range(frames)]
        chmap.append((k, track_id, "translate_x"))
        track_id += 1
        if arm.rate_y or arm.phase_y:
            tracks[track_id] = [arm.phase_y + arm.rate_y * f for f in range(frames)]
            chmap.append((k, track_id, "translate_y"))
            track_id += 1

    group = max(1, design.bead_group)
    step, n_beads = trail_sampling(design, frames)
    n_groups = (n_beads + group - 1) // group
    for gidx in range(n_groups):
        ch = 1 + design.n_arms + gidx
        # The group lights when its LAST bead is reached, so the line trails
        # the pen instead of running ahead of it.
        last_bead = min(n_beads - 1, (gidx + 1) * group - 1)
        on = min(frames - 1, last_bead * step)
        tracks[track_id] = [0.0] * on + [float(TRAIL_COLOR[3])] * (frames - on)
        chmap.append((ch, track_id, "color_a"))
        track_id += 1
    return chmap, tracks


# --------------------------------------------------------------------------
# CSV output
# --------------------------------------------------------------------------

#: The authoring dialect: the 20 required native columns plus the handful this
#: construction actually uses. Everything omitted has a documented load default
#: (see glyphviz-skill/references/node-csv-format.md) -- a native gv_ file does
#: not need the 94-column ANTz layout, which is a compatibility WRITE format.
NODE_COLS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo",
    "ratio", "child_id", "ch_input_id",
    "translate_rate_x", "translate_rate_y", "rotation_mode",
]


def _fmt(v):
    return f"{v:.6f}" if isinstance(v, float) else v


def _row(node: Node) -> dict:
    row = {}
    for col in NODE_COLS:
        if col == "child_id":
            row[col] = int(node.extras.get("child_id", 0) or 0)
        elif col == "ch_input_id":
            row[col] = int(node.extras.get("ch_input_id", 0) or 0)
        else:
            row[col] = getattr(node, col)
    return row


def write_scene(design: EpicycleDesign, out_dir: str, stem: str | None = None
                ) -> dict[str, str]:
    """Write a complete, loadable scene: node CSV, tag CSV, and -- when the
    design is self-drawing -- the ch-map/ch-tracks pair beside them.

    One folder per scene is not decoration: GlyphViz auto-loads Channels only
    when it finds exactly one ch-map and one ch-tracks file in the node CSV's
    folder, and two candidates disable Channels entirely and silently.
    """
    design = design.normalized()
    stem = stem or _slug(design.name)
    os.makedirs(out_dir, exist_ok=True)
    paths: dict[str, str] = {}

    frames = frame_count(design)
    path = trace_path(design, frames)
    nodes = build_nodes(design, include_world=True, path=path)

    node_path = os.path.join(out_dir, f"{stem}_gv_node.csv")
    with open(node_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=NODE_COLS, lineterminator="\r\n")
        w.writeheader()
        for node in nodes:
            w.writerow({k: _fmt(v) for k, v in _row(node).items()})
    paths["node"] = node_path

    # The tag file's name IS its join: the node file's stem with `node` swapped
    # for `tag`. table_id is always 0 and record_id is the node id.
    tag_path = os.path.join(out_dir, f"{stem}_gv_tag.csv")
    with open(tag_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(["id", "table_id", "record_id", "title"])
        for i, node in enumerate(n for n in nodes if n.text):
            w.writerow([i, 0, node.id, node.text])
    paths["tag"] = tag_path

    if design.self_drawing:
        chmap, tracks = build_channels(design, frames)
        map_path = os.path.join(out_dir, f"{stem}_gv_ch-map.csv")
        with open(map_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(["channel_id", "track_id", "attribute"])
            w.writerows(chmap)
        paths["map"] = map_path

        ids = sorted(tracks)
        trk_path = os.path.join(out_dir, f"{stem}_gv_ch-tracks.csv")
        with open(trk_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(["cyclecount"] + [f"ch{i}" for i in ids])
            for f in range(frames):
                w.writerow([f] + [_fmt(tracks[i][f]) for i in ids])
        paths["tracks"] = trk_path
    return paths


def _slug(name: str) -> str:
    keep = [c if (c.isalnum() or c in "-_") else "_" for c in name.strip()]
    return ("".join(keep).strip("_") or "epicycles").lower()


# --------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------

def _square_wave(terms: int = 4, base: float = 12.0) -> list[Arm]:
    """Odd harmonics 1, 3, 5, 7 at amplitudes 1, 1/3, 1/5, 1/7.

    Rates follow from the ladder: to step the harmonic by 2 each level with the
    sign alternating, the rates are 1, -2, +2, -2, ...
    """
    arms = []
    for k in range(terms):
        h = 2 * k + 1
        rate = 1.0 if k == 0 else (2.0 if k % 2 == 0 else -2.0)
        # Rounded to the designer table's own displayed precision, so opening
        # this preset and reading it straight back is exact rather than
        # 12/7 -> 1.7143. Same reason the Composer's ANTz Topo Scale preset
        # has to bypass its 6-decimal spin box.
        arms.append(Arm(length=round(base / h, 4), rate_x=rate))
    return arms


PRESETS: dict[str, EpicycleDesign] = {
    "Jeff's ANTz original": EpicycleDesign(
        name="Fourier_V1",
        arms=[Arm(length=10, rate_x=1, phase_x=0),
              Arm(length=10, rate_x=-1, phase_x=90),
              Arm(length=10, rate_x=1, phase_x=90),
              Arm(length=10, rate_x=-1, phase_x=90)],
        pen_size=1.5),
    "Cardioid (2 terms)": EpicycleDesign(
        name="Cardioid",
        arms=[Arm(length=10, rate_x=1), Arm(length=10, rate_x=-1)]),
    "Spirograph (hypotrochoid)": EpicycleDesign(
        name="Spirograph",
        arms=[Arm(length=14, rate_x=1), Arm(length=6, rate_x=6)]),
    "Square wave (odd harmonics)": EpicycleDesign(
        name="Square_Wave", arms=_square_wave()),
    "Torus knot (tube)": EpicycleDesign(
        name="Torus_Knot",
        arms=[Arm(length=14, rate_x=2),
              Arm(length=6.0, rate_x=0, tube=4.5, rate_y=3)],
        pen_size=1.0),
    "Inclined orrery (tilt)": EpicycleDesign(
        name="Inclined_Orrery",
        arms=[Arm(length=14, rate_x=1),
              Arm(length=7, rate_x=-3, tilt=35),
              Arm(length=3.5, rate_x=5, tilt=-55)]),
    "Rose in space": EpicycleDesign(
        name="Rose_In_Space",
        arms=[Arm(length=12, rate_x=1),
              Arm(length=6, rate_x=-4, tilt=40),
              Arm(length=3, rate_x=4, tube=2.5, rate_y=7)]),
    "Deep chain (6 arms)": EpicycleDesign(
        name="Deep_Chain",
        arms=[Arm(length=12, rate_x=1), Arm(length=7, rate_x=-1),
              Arm(length=4.5, rate_x=1, tilt=25), Arm(length=3, rate_x=-1),
              Arm(length=2, rate_x=1, tube=1.2, rate_y=5),
              Arm(length=1.4, rate_x=-1)],
        pen_size=0.8),
}


def preset(name: str) -> EpicycleDesign:
    """A fresh copy of a named preset -- never the shared instance, so the
    designer can mutate it freely."""
    src = PRESETS[name]
    return EpicycleDesign.from_dict(src.to_dict())


def random_design(rng, n_arms: int | None = None, *, allow_3d: bool = True,
                  name: str | None = None) -> EpicycleDesign:
    """A random design that is still likely to be worth looking at.

    The tuning that matters: rates are small integers (so the curve closes in
    360 frames and reads as a rosette rather than a smear), and arm lengths
    decay, because a series whose later terms are as long as its first one is
    noise rather than a figure.
    """
    n = n_arms or rng.randint(3, 5)
    length = rng.uniform(10.0, 15.0)
    arms: list[Arm] = []
    for k in range(n):
        rate = rng.choice([1, -1, 2, -2, 3, -3, 4, -4, 5, -5])
        tube = 0.0
        rate_y = 0.0
        tilt = 0.0
        if allow_3d and k and rng.random() < 0.45:
            if rng.random() < 0.5:
                tilt = rng.choice([-60, -45, -35, -25, 25, 35, 45, 60])
            else:
                tube = length * rng.uniform(0.25, 0.7)
                rate_y = rng.choice([2, 3, 4, 5, -3, -5])
        arms.append(Arm(length=round(length, 3), rate_x=float(rate),
                        phase_x=float(rng.choice([0, 0, 0, 90, 180, 270])),
                        rate_y=float(rate_y), tube=round(tube, 3),
                        tilt=float(tilt)))
        length *= rng.uniform(0.45, 0.75)
    return EpicycleDesign(name=name or "Epicycles",
                          arms=arms,
                          pen_size=round(max(0.5, length * 0.8), 3))
