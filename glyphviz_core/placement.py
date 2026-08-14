"""
Where a newly created object lands — the N / Shift+N / New Node / New Child
(and paste, and mesh-import) auto-placement rule.

ANTz distributed new nodes by stepping translate_x and wrapping the row:
`npNodeNew` (sdk/src/data/npnode.c:363-384) gave each new child
`translate_x = -15 * (siblings)` and bumped `translate_y` by 15 every 24
children — 24 x 15 deg = one full 360 deg lap — then folded the result back
into -180..180.  The point is the wrap, not the numbers: on a Cartesian
parent the objects array into a grid instead of a runaway line, and on a
circular topology (Sphere, Torus, Cylinder...) the 25th child starts a new
ring above the first instead of landing on top of it.

GlyphViz keeps that behavior and makes the one thing ANTz hardcoded — the
step — adjustable (Properties > Create > Placement Step).  Two entry points,
because the two callers know different things:

- `wrapped_grid_offset(index, step)` — placement by ORDINAL, used for
  children (the parent knows how many it already has).
- `step_from(x, y, step)`           — placement RELATIVE to the previous
  object, used for root-level nodes (there is no ordinal; each new root
  steps on from the last one created, wherever the user has since dragged
  it).

Both walk the same lattice, so a run of N presses and a run of Shift+N
presses lay out identically.  Only x wraps: y keeps climbing, so a long run
of creations grows a taller grid rather than folding back onto row 0.
"""

import math

# One full lap.  translate_x is degrees on every circular topology, so this
# is the value at which a new object would land on the first one; on
# Cartesian parents it is simply the row width.  Not user-facing: the step is
# the knob, the lap is the geometry.
PLACEMENT_WRAP = 360.0

# Historical GlyphViz spacing for a new child (Shift+N), kept as the default
# so existing muscle memory and the guided tour's screenshots still hold.
# ANTz used 15.0; type it into the Placement Step box for ANTz's own lattice.
DEFAULT_PLACEMENT_STEP = 5.0

# translate_z for a new object.  Roots land on the world plane; children stand
# off their parent, because a child at 0 under a topology-None parent would be
# swallowed by it — on a Sphere/Torus/Cylinder parent the same number lifts the
# child radially off the surface instead.  Both are adjustable (Properties >
# Create > Placement Z); only the DEFAULTS differ, since the axis means
# different things at the two levels.
DEFAULT_ROOT_Z = 0.0
DEFAULT_CHILD_Z = 5.0


def columns_per_row(step: float, wrap: float = PLACEMENT_WRAP) -> int:
    """How many objects fit in one row before x wraps: the count of
    multiples of *step* strictly below *wrap* (so a 5-unit step gives 72
    columns, 0..355, and ANTz's 15 gives 24, 0..345).

    A step at or above a full lap gives 1 — every object on its own row."""
    step = abs(float(step))
    if step <= 0.0:
        return 1
    return max(1, math.ceil(wrap / step))


def wrapped_grid_offset(index: int, step: float,
                        wrap: float = PLACEMENT_WRAP) -> tuple[float, float]:
    """(translate_x, translate_y) for the *index*-th object (0-based) placed
    at *step* spacing, wrapping to a new row every `columns_per_row` objects.

    A step of 0 stacks everything at the origin, which is what asking for no
    spacing means."""
    step = abs(float(step))
    i = max(0, int(index))
    if step <= 0.0:
        return (0.0, 0.0)
    cols = columns_per_row(step, wrap)
    return ((i % cols) * step, (i // cols) * step)


def step_from(x: float, y: float, step: float,
              wrap: float = PLACEMENT_WRAP) -> tuple[float, float]:
    """(translate_x, translate_y) one *step* on from an object sitting at
    (*x*, *y*) — the same lattice as `wrapped_grid_offset`, reached
    incrementally: x + step, unless that would reach a full lap, in which
    case x restarts at 0 and y takes the step instead."""
    step = abs(float(step))
    if step <= 0.0:
        return (float(x), float(y))
    next_x = float(x) + step
    if next_x >= wrap:
        return (0.0, float(y) + step)
    return (next_x, float(y))
