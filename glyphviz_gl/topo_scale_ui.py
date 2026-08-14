"""
Shared UI vocabulary for Node.topo_scale (Topology Scale).

Two surfaces edit the field — the Properties panel (main_window) and the Glyph
Composer's per-level form — and they must agree on the range and on how a
slider position maps to a value, or the same drag would mean different things
in the two places. That agreement lives here; the widgets themselves stay with
their panels, since the two rows differ (the Composer's carries an Auto
checkbox, the Properties panel's applies across a multi-selection).

Qt-free on purpose: these are plain float<->int conversions, testable without a
QApplication.
"""
from __future__ import annotations

import math

# The useful range spans several orders of magnitude — 1.0 ("a translate unit
# is a world unit") down past TOPO_SCALE_ANTZ (1/180, "360 units spans a cube
# facet") and up for deliberately exploded layouts — so the slider is
# logarithmic: a fixed number of steps per decade, which makes a drag feel the
# same at 0.005 as at 5. The spin box beside it takes exact values.
TOPO_SCALE_MIN = 1e-4
TOPO_SCALE_MAX = 1e2
TOPO_SCALE_STEPS_PER_DECADE = 100

TOPO_SCALE_SLIDER_MAX = int(
    round((math.log10(TOPO_SCALE_MAX) - math.log10(TOPO_SCALE_MIN))
          * TOPO_SCALE_STEPS_PER_DECADE))


def topo_scale_to_slider(value: float) -> int:
    """Node.topo_scale -> log slider position, clamped to the slider's range."""
    if value <= TOPO_SCALE_MIN:
        return 0
    pos = ((math.log10(value) - math.log10(TOPO_SCALE_MIN))
           * TOPO_SCALE_STEPS_PER_DECADE)
    return max(0, min(TOPO_SCALE_SLIDER_MAX, int(round(pos))))


def slider_to_topo_scale(pos: int) -> float:
    """Log slider position -> Node.topo_scale. Snaps the exact-decade
    positions (…, 0.01, 0.1, 1.0, 10.0) to clean values rather than the
    10**-15.999999 the float math would otherwise land on, so a user who
    drags to the 1.0 tick gets exactly 1.0 back — the value that omits the
    CSV column entirely."""
    exp = math.log10(TOPO_SCALE_MIN) + pos / TOPO_SCALE_STEPS_PER_DECADE
    if pos % TOPO_SCALE_STEPS_PER_DECADE == 0:
        return float(10.0 ** round(exp))
    return 10.0 ** exp
