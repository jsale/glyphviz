#!/usr/bin/env python3
"""
build_ybco_scene.py -- GlyphViz materials-science storytelling exemplar (V1+V2)
================================================================================

YBa2Cu3O7 (YBCO), the 1987 "liquid-nitrogen superconductor" (Tc ~ 92 K,
orthorhombic Pmmm, space group #47) -- GlyphViz's first crystallography
exemplar. This is deliberately NOT a general CIF importer: it hand-builds one
real, well-documented structure to test whether "crystal structure + physical
property plot + literature links in one glyph scene" is a compelling format
before any general symmetry-operator infrastructure gets built.

STRUCTURE
    One conventional unit cell, drawn textbook-style: a full atom is placed
    at every symmetry-equivalent corner/edge site within the drawn box
    (rather than fractional corner-sharing occupancies), matching how every
    published YBCO structure figure presents it. Layer stack along c, in the
    classic "1-2-3" perovskite order:

        CuO chain (Cu1 + O1)      z=0
        BaO                        z~0.184
        CuO2 plane (Cu2+O2+O3)     z~0.378
        Y                          z=0.5
        CuO2 plane                z~0.622
        BaO                        z~0.816
        CuO chain                  z=1 (next cell's chain layer, drawn to
                                        close the box)

    Cu-O nearest-neighbor bonds are drawn (chain, apical, and in-plane) --
    the network that actually matters physically -- via GEO_LINE_PRISM.
    Ba and Y are left unbonded (highly ionic, many-coordinate, and not part
    of the conduction-relevant network); this simplification keeps the
    scene readable and is called out in-scene via node text.

    Lattice parameters and fractional coordinates are representative
    published values (Jorgensen et al., Phys. Rev. B 41, 1863 (1990); cross-
    checked against Materials Project mp-20674 and the original Nature
    structure paper) -- NOT digitized from one single source, and rounded
    for a clean illustrative model rather than a research-grade refinement.

PROPERTY PLOT
    A TOPO_PLOT polyline of illustrative rho_ab(T): linear normal-state
    resistivity (the famous "strange metal" T-linear behavior, unlike an
    ordinary Fermi liquid's T^2) dropping sharply to exactly zero at Tc.
    The transition width is visually widened (2 K) from real single-crystal
    data (often < 1 K) for legibility at this plot scale -- noted in-scene.

TAGS
    Two verified real URLs (Materials Project entry + the original Nature
    structure paper) attached via inline text/link columns -- no separate
    gv_tag.csv needed for a scene this size.

OXYGEN-CONTENT CHANNELS ANIMATION (V2)
    A Channels time-replay (gv_ch-map.csv/gv_ch-tracks.csv) sweeps the
    oxygen-deficiency parameter delta in YBa2Cu3O(7-delta) back and forth
    between 0 (the V1 structure: fully oxygenated, orthorhombic, Tc~92.5 K)
    and 1 (fully reduced: tetragonal, a=b, non-superconducting) -- the
    structural transition that IS the mechanism turning superconductivity
    on. Chain-oxygen (O1) occupancy fades exactly as (1-delta) (real
    stoichiometry, not an assumption); the a/b lattice split and the
    Tc(delta) curve are illustrative interpolations of the well-documented
    qualitative shape (see build_oxygen_channels/tc_of_delta), not a
    digitization of one dataset. A small marker on the resistivity plot
    slides along the temperature axis to Tc(delta) during playback; the
    static rho(T) curve itself always stays the delta=0 reference case.
    Every node's authored (rest-state) values equal delta=0, so a
    stopped/reset scene is pixel-identical to V1. Press Space to play.

Usage:
    python build_ybco_scene.py                    # writes ybco_gv_node.csv here
    python build_ybco_scene.py --out PATH.csv      # custom output path

Requires: pandas
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# 1. CRYSTALLOGRAPHIC DATA (representative published values)
# ---------------------------------------------------------------------------
SPACE_GROUP = "Pmmm (#47)"
A_ANGSTROM, B_ANGSTROM, C_ANGSTROM = 3.8227, 3.8872, 11.6802

# World-unit scale factor applied uniformly to all crystal coordinates --
# purely a visual-presence choice (real Angstrom bond lengths render too
# small to read next to the property plot's ~50-unit span). Ratios/geometry
# are untouched; the cell's real c/a ~ 3.05 anisotropy (the layered,
# quasi-2D character that IS the physics) is preserved exactly.
SCALE = 4.0
A, B, C = A_ANGSTROM * SCALE, B_ANGSTROM * SCALE, C_ANGSTROM * SCALE

CORNERS = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]

# Fractional z-heights per site (Jorgensen et al. 1990; Cu2/O4 cross-checked
# against search results this session). O2 and O3 use the same nominal
# in-plane z (~0.378/0.622); the real ~0.02 buckling between them is below
# this model's illustrative resolution.
Z_CU1 = (0.0, 1.0)                 # chain copper: bottom + top (closes box)
Z_BA = (0.1843, 0.8157)
Z_CU2 = (0.3547, 0.6453)
Z_O1 = (0.0, 1.0)                  # chain oxygen, same layers as Cu1
Z_O4 = (0.1590, 0.8410)            # apical oxygen
Z_O23 = (0.3780, 0.6220)           # in-plane oxygens (O2 along a, O3 along b)

ELEMENTS = {
    # color chosen for readability / chain-vs-plane distinction, not CPK;
    # scale is ball-and-stick radius (world units), not literal ionic radius.
    "Y":   dict(color=(120, 210, 200), scale=1.30),
    "Ba":  dict(color=(150, 175, 90), scale=1.60),
    "Cu1": dict(color=(195, 90, 40), scale=1.00),   # chain copper
    "Cu2": dict(color=(230, 150, 45), scale=1.00),  # CuO2-plane copper
    "O":   dict(color=(215, 60, 55), scale=0.75),
}
BOND_COLOR = (225, 215, 200, 255)
BOND_RATIO = 0.35

MP_URL = "https://legacy.materialsproject.org/materials/mp-20674/"
NATURE_URL = "https://www.nature.com/articles/328606a0"

# ---------------------------------------------------------------------------
# 2. RESISTIVITY-VS-TEMPERATURE CURVE (illustrative)
# ---------------------------------------------------------------------------
TC_KELVIN = 92.5            # accepted textbook YBCO transition temperature
TRANS_WIDTH = 2.0           # widened from real (<1 K) single-crystal data for legibility
T_MIN, T_MAX = 10.0, 300.0
RHO_300 = 300.0             # representative order-of-magnitude uOhm*cm at 300 K
RHO_ONSET = 55.0            # representative value at the top of the transition
# Linear "strange metal" normal state: rho(T) = RHO0 + SLOPE * T
SLOPE = (RHO_300 - RHO_ONSET) / (T_MAX - (TC_KELVIN + TRANS_WIDTH))
RHO0 = RHO_ONSET - SLOPE * (TC_KELVIN + TRANS_WIDTH)


def resistivity(t: float) -> float:
    """Illustrative rho_ab(T) in uOhm*cm: T-linear normal state, smooth
    (cosine-eased) drop to exactly zero across TRANS_WIDTH at Tc."""
    if t <= TC_KELVIN:
        return 0.0
    top = TC_KELVIN + TRANS_WIDTH
    if t >= top:
        return RHO0 + SLOPE * t
    f = (t - TC_KELVIN) / TRANS_WIDTH
    ease = 0.5 - 0.5 * math.cos(f * math.pi)
    return ease * (RHO0 + SLOPE * top)


def temperature_samples() -> list[float]:
    """Denser sampling near the transition for a crisp visual drop."""
    pts = set()
    t = T_MIN
    while t <= T_MAX:
        pts.add(round(t, 3))
        t += 8.0
    t = TC_KELVIN - 12.0
    while t <= TC_KELVIN + 12.0:
        pts.add(round(t, 3))
        t += 0.5
    return sorted(p for p in pts if T_MIN <= p <= T_MAX)


# Plot layout (local units relative to the plot's own anchor node)
PLOT_W, PLOT_H = 55.0, 26.0
PLOT_ORIGIN_X = A + 20.0   # world x of the plot anchor -- crystal width + gap


def plot_x(t: float) -> float:
    """Higher T -> larger x (left-to-right increasing temperature)."""
    return (t - T_MIN) / (T_MAX - T_MIN) * PLOT_W


def plot_y(rho: float) -> float:
    return rho / RHO_300 * PLOT_H


# ---------------------------------------------------------------------------
# 2b. OXYGEN-CONTENT CHANNELS ANIMATION (V2) -- illustrative
# ---------------------------------------------------------------------------
# YBa2Cu3O(7-delta): delta sweeps the structure between the fully-oxygenated
# orthorhombic superconductor (delta=0, the V1 structure above, Tc~92.5 K)
# and the fully-reduced tetragonal non-superconductor (delta=1, chain-oxygen
# site vacant, a=b). Chain-oxygen (O1) site occupancy is exactly (1-delta)
# by the stoichiometry itself -- not an extra illustrative assumption, unlike
# the lattice-parameter interpolation and the Tc(delta) curve below, which
# ARE simplified/illustrative (real data show a sharper, first-order-like
# orthorhombic-tetragonal transition near delta~0.6-0.65 and a small c-axis
# shift with delta that this model omits for clarity).
A_TET = 3.8560   # representative tetragonal a=b (Angstrom) at delta->1

HOLD_FRAMES_OX = 30   # pause at each end state so it reads before it moves on
RAMP_FRAMES_OX = 90   # frames to sweep delta 0<->1
TOTAL_OX_FRAMES = 2 * HOLD_FRAMES_OX + 2 * RAMP_FRAMES_OX


def _smoothstep(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


def delta_at_frame(f: int) -> float:
    """Loop schedule: hold@delta=0 -> ramp to 1 -> hold@1 -> ramp back to 0."""
    f = f % TOTAL_OX_FRAMES
    if f < HOLD_FRAMES_OX:
        return 0.0
    f -= HOLD_FRAMES_OX
    if f < RAMP_FRAMES_OX:
        return _smoothstep(f / RAMP_FRAMES_OX)
    f -= RAMP_FRAMES_OX
    if f < HOLD_FRAMES_OX:
        return 1.0
    f -= HOLD_FRAMES_OX
    return 1.0 - _smoothstep(f / RAMP_FRAMES_OX)


def a_of_delta(delta: float) -> float:
    return A_ANGSTROM + (A_TET - A_ANGSTROM) * _smoothstep(delta)


def b_of_delta(delta: float) -> float:
    return B_ANGSTROM + (A_TET - B_ANGSTROM) * _smoothstep(delta)


def occupancy_alpha(delta: float) -> float:
    """Chain-O (O1) site alpha: 255 fully occupied (delta=0) down to a dim
    25 'vacancy ghost' (delta=1) -- occupancy fraction is exactly 1-delta."""
    occ = 1.0 - delta
    return 25.0 + (255.0 - 25.0) * occ


_TC_VS_DELTA = [  # (delta, Tc_K) control points, illustrative -- captures the
    (1.00, 0.0),   # well-known qualitative shape (non-SC tetragonal region,
    (0.65, 0.0),   # rise, the famous "60 K plateau", final rise to ~92 K)
    (0.55, 45.0),  # without claiming to digitize one specific dataset.
    (0.40, 59.0),
    (0.20, 61.0),
    (0.00, 92.5),
]


def tc_of_delta(delta: float) -> float:
    for (d0, t0), (d1, t1) in zip(_TC_VS_DELTA, _TC_VS_DELTA[1:]):
        if d1 <= delta <= d0:
            f = (d0 - delta) / (d0 - d1)
            return t0 + (t1 - t0) * _smoothstep(f)
    return 92.5 if delta <= 0.0 else 0.0


# Channel-bundle ids (a node's ch_input_id) and the raw-track ids they bundle
# together (glyphviz_core/channel_engine.py: one channel_id may bind several
# (track_id, attribute) pairs at once -- see gv_ch-map.csv). Position tracks
# are shared across every atom with the same (x_frac, y_frac): since
# translate_x = x_frac * a(delta) * SCALE, an x_frac of 0 never needs a
# channel (always 0), and there are only two other distinct x_frac values
# (0.5, 1) and two y_frac values (0.5, 1) -- so ~39 atoms collapse onto a
# handful of shared tracks, the same "shared channel" compression used in
# examples/SD_Seismicity_Example (events sharing a birth month share a
# channel). Cu-O bond edges need no position channel at all: Link edges are
# drawn from their endpoints' LIVE world positions every frame
# (glyphviz_gl/viewport.py's `_draw_topology_overlays`), so animating the
# atoms automatically drags every bond along for free.
TR_X_HALF, TR_X_FULL, TR_Y_HALF, TR_Y_FULL, TR_OCC_ALPHA = 1, 2, 3, 4, 5
TR_BOX_SCALE_X, TR_BOX_SCALE_Y, TR_TC_MARKER_X = 6, 7, 8

CH_NONE = 0
CH_X_FULL_ONLY, CH_Y_FULL_ONLY, CH_XY_FULL = 1, 2, 3
CH_XY_HALF, CH_X_HALF_ONLY, CH_XY_HALF_FULL = 4, 5, 6
CH_Y_HALF_ONLY, CH_XY1_HALF = 7, 8
CH_Y_HALF_O1, CH_XY1_HALF_O1 = 9, 10
CH_O1_BOND, CH_BOX, CH_TC_MARKER = 11, 12, 13

CHANNEL_DEFS: dict[int, list[tuple[int, str]]] = {
    CH_X_FULL_ONLY:   [(TR_X_FULL, "translate_x")],
    CH_Y_FULL_ONLY:   [(TR_Y_FULL, "translate_y")],
    CH_XY_FULL:       [(TR_X_FULL, "translate_x"), (TR_Y_FULL, "translate_y")],
    CH_XY_HALF:       [(TR_X_HALF, "translate_x"), (TR_Y_HALF, "translate_y")],
    CH_X_HALF_ONLY:   [(TR_X_HALF, "translate_x")],
    CH_XY_HALF_FULL:  [(TR_X_HALF, "translate_x"), (TR_Y_FULL, "translate_y")],
    CH_Y_HALF_ONLY:   [(TR_Y_HALF, "translate_y")],
    CH_XY1_HALF:      [(TR_X_FULL, "translate_x"), (TR_Y_HALF, "translate_y")],
    CH_Y_HALF_O1:     [(TR_Y_HALF, "translate_y"), (TR_OCC_ALPHA, "color_a")],
    CH_XY1_HALF_O1:   [(TR_X_FULL, "translate_x"), (TR_Y_HALF, "translate_y"),
                       (TR_OCC_ALPHA, "color_a")],
    CH_O1_BOND:       [(TR_OCC_ALPHA, "color_a")],
    CH_BOX:           [(TR_X_HALF, "translate_x"), (TR_Y_HALF, "translate_y"),
                       (TR_BOX_SCALE_X, "scale_x"), (TR_BOX_SCALE_Y, "scale_y")],
    CH_TC_MARKER:     [(TR_TC_MARKER_X, "translate_x")],
}


def std_channel(xfrac: float, yfrac: float) -> int:
    """Position-only channel for a given (x_frac, y_frac) -- covers every
    atom except the two O1 chain-oxygen sites, which need occupancy alpha
    bundled in too (see CH_Y_HALF_O1 / CH_XY1_HALF_O1, assigned directly)."""
    return {
        (0.0, 0.0): CH_NONE,
        (1.0, 0.0): CH_X_FULL_ONLY,
        (0.0, 1.0): CH_Y_FULL_ONLY,
        (1.0, 1.0): CH_XY_FULL,
        (0.5, 0.5): CH_XY_HALF,
        (0.5, 0.0): CH_X_HALF_ONLY,
        (0.5, 1.0): CH_XY_HALF_FULL,
        (0.0, 0.5): CH_Y_HALF_ONLY,
        (1.0, 0.5): CH_XY1_HALF,
    }[(xfrac, yfrac)]


# ---------------------------------------------------------------------------
# 3. SCENE BUILDER (COLUMNS/DEFAULTS pattern shared with other gv_ examples)
# ---------------------------------------------------------------------------
COLUMNS = ["id", "type", "parent_id", "branch_level", "child_id",
           "translate_x", "translate_y", "translate_z",
           "rotate_x", "rotate_y", "rotate_z",
           "scale_x", "scale_y", "scale_z",
           "color_r", "color_g", "color_b", "color_a", "color_index",
           "geometry", "hide", "topo", "ratio", "texture_id", "ch_input_id",
           "trigger_lo_x", "trigger_hi_x", "trigger_lo_y", "trigger_hi_y",
           "segments_x", "segments_y", "text", "link"]

DEFAULTS = dict(child_id=0, translate_x=0.0, translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=255, color_g=255, color_b=255, color_a=255,
                color_index=0, geometry=3, hide=0, topo=0, ratio=0.1,
                texture_id=0, ch_input_id=0, trigger_lo_x=0, trigger_hi_x=0,
                trigger_lo_y=0, trigger_hi_y=0, segments_x=16, segments_y=16,
                text="", link="")

GEO_CUBE_WIRE, GEO_SPHERE, GEO_POINT, GEO_STAR, GEO_LINE_PRISM = 0, 3, 22, 26, 28
TOPO_NONE, TOPO_PLOT = 0, 16

# The base cube is inscribed in a unit sphere (half-width 1/sqrt(3), not 1
# -- see glyphviz_gl/geometry.py's _CUBE_VERTS), so a wireframe box's scale
# must be its desired half-width divided by this constant.
CUBE_HALF_WIDTH = 1.0 / (3.0 ** 0.5)


@dataclass
class SceneBuilder:
    rows: list[dict] = field(default_factory=list)
    next_id: int = 1

    def add(self, **kw) -> int:
        row = {**DEFAULTS, "id": self.next_id, **kw}
        self.rows.append(row)
        self.next_id += 1
        return row["id"]

    def bond(self, a_id: int, b_id: int, branch_level: int,
             ch_input_id: int = 0) -> int:
        return self.add(type=7, parent_id=a_id, child_id=b_id,
                        branch_level=branch_level, geometry=GEO_LINE_PRISM,
                        ratio=BOND_RATIO, ch_input_id=ch_input_id,
                        color_r=BOND_COLOR[0], color_g=BOND_COLOR[1],
                        color_b=BOND_COLOR[2], color_a=BOND_COLOR[3])

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=COLUMNS)


def build_crystal(sb: SceneBuilder) -> dict:
    """Unit cell wireframe box + all atoms + Cu-O bond network.
    Returns atom-id lookup keyed by (element, x_frac, y_frac, z_frac)."""
    atoms: dict[tuple, int] = {}

    def place(elem: str, xf: float, yf: float, zf: float, label: str = "",
              link: str = "", ch: int | None = None) -> int:
        e = ELEMENTS[elem]
        if ch is None:
            ch = std_channel(xf, yf)
        nid = sb.add(type=5, parent_id=0, branch_level=0,
                     translate_x=round(xf * A, 4),
                     translate_y=round(yf * B, 4),
                     translate_z=round(zf * C, 4),
                     scale_x=e["scale"], scale_y=e["scale"], scale_z=e["scale"],
                     color_r=e["color"][0], color_g=e["color"][1],
                     color_b=e["color"][2], color_a=255,
                     geometry=GEO_SPHERE, text=label, link=link,
                     ch_input_id=ch)
        atoms[(elem, round(xf, 4), round(yf, 4), round(zf, 4))] = nid
        return nid

    # Unit cell wireframe box (a single anisotropically-scaled cube-wire glyph).
    sb.add(type=5, parent_id=0, branch_level=0,
           translate_x=round(A / 2, 4), translate_y=round(B / 2, 4),
           translate_z=round(C / 2, 4),
           scale_x=round((A / 2) / CUBE_HALF_WIDTH, 4),
           scale_y=round((B / 2) / CUBE_HALF_WIDTH, 4),
           scale_z=round((C / 2) / CUBE_HALF_WIDTH, 4),
           color_r=180, color_g=190, color_b=210, color_a=140,
           geometry=GEO_CUBE_WIRE, ch_input_id=CH_BOX,
           text=(f"Unit cell: a={A_ANGSTROM:.4f} A, b={B_ANGSTROM:.4f} A, "
                 f"c={C_ANGSTROM:.4f} A -- {SPACE_GROUP}"),
           link=MP_URL)

    # Y -- body center, between the two CuO2 planes.
    place("Y", 0.5, 0.5, 0.5, "Y -- yttrium, between the CuO2 bilayer",
          link=NATURE_URL)

    # Ba -- two layers, body-centered in xy.
    for z in Z_BA:
        place("Ba", 0.5, 0.5, z,
              "Ba -- barium" if z == Z_BA[0] else "")

    # Cu1 (chain copper) -- 4 corners, bottom + top layer.
    for z in Z_CU1:
        for i, (x, y) in enumerate(CORNERS):
            place("Cu1", x, y, z,
                  "Cu(1) -- chain copper" if (x, y, z) == (0, 0, 0) else "")

    # Cu2 (CuO2-plane copper) -- 4 corners, two plane layers.
    for z in Z_CU2:
        for x, y in CORNERS:
            place("Cu2", x, y, z,
                  "Cu(2) -- CuO2-plane copper" if (x, y, z) == (0, 0, Z_CU2[0])
                  else "")

    # O1 (chain oxygen) -- along b, bridges adjacent Cu1. Occupancy is
    # oxygen-content-dependent (see CH_Y_HALF_O1/CH_XY1_HALF_O1), unlike
    # every other site here.
    for z in Z_O1:
        for x in (0.0, 1.0):
            place("O", x, 0.5, z,
                  "O(1) -- chain oxygen (occupancy tracks oxygen content)"
                  if (x, z) == (0.0, 0.0) else "",
                  ch=(CH_Y_HALF_O1 if x == 0.0 else CH_XY1_HALF_O1))

    # O4 (apical oxygen) -- bridges chain-Cu to plane-Cu vertically.
    for z in Z_O4:
        for x, y in CORNERS:
            place("O", x, y, z,
                  "O(4) -- apical oxygen" if (x, y, z) == (0, 0, Z_O4[0])
                  else "")

    # O2 (in-plane oxygen along a) and O3 (in-plane oxygen along b).
    for z in Z_O23:
        for y in (0.0, 1.0):
            place("O", 0.5, y, z,
                  "O(2) -- CuO2-plane oxygen (a)" if (y, z) == (0.0, Z_O23[0])
                  else "")
        for x in (0.0, 1.0):
            place("O", x, 0.5, z,
                  "O(3) -- CuO2-plane oxygen (b)" if (x, z) == (0.0, Z_O23[0])
                  else "")

    # -- Cu-O bond network (chain, apical, in-plane) --------------------
    # Chain bonds (Cu1-O1) fade with the same occupancy alpha as their O1
    # endpoint (CH_O1_BOND); their endpoints already move for free each
    # frame since bond geometry is computed from live world positions, not
    # baked in at authoring time.
    n_bonds = 0
    for z in Z_CU1:
        for x in (0.0, 1.0):
            o1 = atoms[("O", x, 0.5, z)]
            n_bonds += 1
            sb.bond(atoms[("Cu1", x, 0.0, z)], o1, 1, ch_input_id=CH_O1_BOND)
            n_bonds += 1
            sb.bond(atoms[("Cu1", x, 1.0, z)], o1, 1, ch_input_id=CH_O1_BOND)

    for z_cu1, z_o4 in zip(Z_CU1, Z_O4):
        for x, y in CORNERS:
            n_bonds += 1
            sb.bond(atoms[("Cu1", x, y, z_cu1)], atoms[("O", x, y, z_o4)], 1)
    for z_cu2, z_o4 in zip(Z_CU2, Z_O4):
        for x, y in CORNERS:
            n_bonds += 1
            sb.bond(atoms[("Cu2", x, y, z_cu2)], atoms[("O", x, y, z_o4)], 1)

    for z_cu2, z_o23 in zip(Z_CU2, Z_O23):
        for x, y in CORNERS:
            n_bonds += 1
            sb.bond(atoms[("Cu2", x, y, z_cu2)], atoms[("O", 0.5, y, z_o23)], 1)
            n_bonds += 1
            sb.bond(atoms[("Cu2", x, y, z_cu2)], atoms[("O", x, 0.5, z_o23)], 1)

    return {"atoms": atoms, "n_bonds": n_bonds}


def build_plot(sb: SceneBuilder, origin_x: float) -> int:
    """TOPO_PLOT resistivity-vs-temperature curve, offset to the right of
    the crystal. Returns sample-point count.

    IMPORTANT: the viewport connects EVERY type=5 child of a TOPO_PLOT
    parent into the polyline (glyphviz_gl/viewport.py's
    `_draw_topology_overlays`, `children_of` -> `any_plot` block) -- it
    does not distinguish "data" children from decoration. So axis/tick/
    callout nodes must NOT be parent_id=anchor; they're independent
    branch_level=0 nodes at absolute world coordinates, wired to the
    anchor only via ordinary type=7 Link edges (which the same function
    handles in a separate pass and never folds into the polyline). Only
    the actual curve samples are parent_id=anchor.

    The anchor itself must stay hide=0: a hidden TOPO_PLOT node is skipped
    entirely by that same block (its polyline never draws) and by the tag
    projector, so "hide the organizing node" -- the usual trick for an
    invisible parent -- does not apply here.
    """
    anchor = sb.add(type=5, parent_id=0, branch_level=0,
                    translate_x=origin_x, translate_y=0.0, translate_z=C / 2,
                    color_r=170, color_g=175, color_b=185, color_a=255,
                    geometry=GEO_POINT, hide=0, topo=TOPO_PLOT,
                    text=("YBa2Cu3O7 resistivity rho_ab(T), illustrative -- "
                          "linear normal state, sharp drop to zero at Tc"))

    def world(lx: float, ly: float) -> tuple[float, float, float]:
        return (origin_x + lx, ly, C / 2)

    # Axes: independent nodes at the two axis ends, linked back to the
    # anchor (the plot's origin) with ordinary Link edges.
    wx, wy, wz = world(PLOT_W, 0.0)
    ax_x = sb.add(type=5, parent_id=0, branch_level=0,
                 translate_x=wx, translate_y=wy, translate_z=wz,
                 scale_x=0.01, scale_y=0.01, scale_z=0.01, geometry=GEO_POINT,
                 hide=1)
    wx, wy, wz = world(0.0, PLOT_H)
    ax_y = sb.add(type=5, parent_id=0, branch_level=0,
                 translate_x=wx, translate_y=wy, translate_z=wz,
                 scale_x=0.01, scale_y=0.01, scale_z=0.01, geometry=GEO_POINT,
                 hide=1)
    sb.bond(anchor, ax_x, 1)
    sb.bond(anchor, ax_y, 1)

    # Tc marker line (from the temperature axis up through the transition).
    tc_x = plot_x(TC_KELVIN)
    wx, wy, wz = world(tc_x, 0.0)
    tc_bot = sb.add(type=5, parent_id=0, branch_level=0,
                    translate_x=wx, translate_y=wy, translate_z=wz,
                    scale_x=0.01, scale_y=0.01, scale_z=0.01, geometry=GEO_POINT,
                    hide=1)
    wx, wy, wz = world(tc_x, PLOT_H * 0.5)
    tc_top = sb.add(type=5, parent_id=0, branch_level=0,
                    translate_x=wx, translate_y=wy, translate_z=wz,
                    scale_x=0.3, scale_y=0.3, scale_z=0.3, geometry=GEO_POINT,
                    hide=0, color_r=140, color_g=210, color_b=255, color_a=255,
                    text=f"Tc = {TC_KELVIN:g} K")
    sb.add(type=7, parent_id=tc_bot, child_id=tc_top, branch_level=0,
          geometry=GEO_LINE_PRISM, ratio=0.15,
          color_r=140, color_g=210, color_b=255, color_a=200)

    # Temperature-axis tick labels (independent, visible-but-small markers
    # so their text tags render).
    for t_tick in (100.0, 200.0, 300.0):
        wx, wy, wz = world(plot_x(t_tick), -1.5)
        sb.add(type=5, parent_id=0, branch_level=0,
              translate_x=wx, translate_y=wy, translate_z=wz,
              scale_x=0.25, scale_y=0.25, scale_z=0.25, geometry=GEO_POINT,
              hide=0, color_r=170, color_g=175, color_b=185, color_a=255,
              text=f"{t_tick:g} K")

    # "Strange metal" callout near the linear normal-state region.
    callout_t = 220.0
    wx, wy, wz = world(plot_x(callout_t), plot_y(resistivity(callout_t)) + 2.0)
    sb.add(type=5, parent_id=0, branch_level=0,
          translate_x=wx, translate_y=wy, translate_z=wz,
          scale_x=0.25, scale_y=0.25, scale_z=0.25, geometry=GEO_POINT,
          hide=0, color_r=255, color_g=200, color_b=120, color_a=255,
          text=("linear rho(T) -- 'strange metal' behavior, unlike an "
                "ordinary Fermi liquid's T^2"))

    # Tc(delta) marker: an independent node whose translate_x is driven by
    # the oxygen-content Channels animation (CH_TC_MARKER), sliding along
    # the temperature axis to show where Tc sits for the currently-shown
    # structure. The static curve above always stays the delta=0 (best
    # case, Tc=92.5 K) reference; this marker is the only thing that moves
    # with playback. Its rest/CSV-authored position matches delta=0 (the
    # V1 baseline), so a stopped/reset scene looks identical to before.
    wx, wy, wz = world(plot_x(TC_KELVIN), -3.5)
    sb.add(type=5, parent_id=0, branch_level=0,
          translate_x=wx, translate_y=wy, translate_z=wz,
          scale_x=0.35, scale_y=0.35, scale_z=0.35, geometry=GEO_STAR,
          hide=0, color_r=255, color_g=80, color_b=210, color_a=255,
          ch_input_id=CH_TC_MARKER,
          text="Tc at current oxygen content (Channels playback)")

    # Curve samples -- the ONLY nodes parented to the anchor, so these are
    # the only ones swept into the TOPO_PLOT polyline.
    samples = temperature_samples()
    for t in samples:
        rho = resistivity(t)
        superconducting = t <= TC_KELVIN
        color = (60, 200, 255) if superconducting else (
            255, int(140 + 80 * (1 - t / T_MAX)), 60)
        sb.add(type=5, parent_id=anchor, branch_level=1,
              translate_x=round(plot_x(t), 3),
              translate_y=round(plot_y(rho), 3), translate_z=0.0,
              scale_x=0.45, scale_y=0.45, scale_z=0.45,
              geometry=GEO_SPHERE,
              color_r=color[0], color_g=color[1], color_b=color[2],
              color_a=255)
    return len(samples)


# ---------------------------------------------------------------------------
# 3b. OXYGEN-CONTENT CHANNEL FILES (gv_ch-map.csv / gv_ch-tracks.csv)
# ---------------------------------------------------------------------------
def build_oxygen_channels() -> tuple[pd.DataFrame, pd.DataFrame]:
    """ch_map_df (channel_id -> track_id/attribute bindings) and
    ch_tracks_df (one row per frame, one column per raw track) for the
    delta-driven oxygen-content animation."""
    map_rows = [dict(id=i + 1, channel_id=ch, track_id=tid, attribute=attr,
                     track_table_id=0, ch_map_table_id=0, record_id=0)
                for i, (ch, bindings) in enumerate(CHANNEL_DEFS.items())
                for tid, attr in bindings]
    ch_map_df = pd.DataFrame(map_rows)

    data: dict[str, list] = {"cyclecount": list(range(1, TOTAL_OX_FRAMES + 1))}
    x_half, x_full, y_half, y_full, occ = [], [], [], [], []
    box_sx, box_sy, tc_x = [], [], []
    for f in range(TOTAL_OX_FRAMES):
        delta = delta_at_frame(f)
        a_t, b_t = a_of_delta(delta), b_of_delta(delta)
        x_half.append(round(0.5 * a_t * SCALE, 4))
        x_full.append(round(1.0 * a_t * SCALE, 4))
        y_half.append(round(0.5 * b_t * SCALE, 4))
        y_full.append(round(1.0 * b_t * SCALE, 4))
        occ.append(round(occupancy_alpha(delta), 2))
        box_sx.append(round((a_t * SCALE / 2) / CUBE_HALF_WIDTH, 4))
        box_sy.append(round((b_t * SCALE / 2) / CUBE_HALF_WIDTH, 4))
        tc_k = max(tc_of_delta(delta), T_MIN)
        tc_x.append(round(PLOT_ORIGIN_X + plot_x(tc_k), 4))
    data[f"ch{TR_X_HALF}"] = x_half
    data[f"ch{TR_X_FULL}"] = x_full
    data[f"ch{TR_Y_HALF}"] = y_half
    data[f"ch{TR_Y_FULL}"] = y_full
    data[f"ch{TR_OCC_ALPHA}"] = occ
    data[f"ch{TR_BOX_SCALE_X}"] = box_sx
    data[f"ch{TR_BOX_SCALE_Y}"] = box_sy
    data[f"ch{TR_TC_MARKER_X}"] = tc_x
    ch_tracks_df = pd.DataFrame(data)
    return ch_map_df, ch_tracks_df


def channel_paths(node_out: str) -> tuple[str, str]:
    """Derive ch-map/ch-tracks paths from the node CSV path (gv naming
    convention: swap a trailing 'node' stem for the channel names)."""
    p = Path(node_out)
    stem = p.stem
    base = stem[:-len("node")] if stem.endswith("node") else stem + "_"
    return (str(p.with_name(f"{base}ch-map{p.suffix}")),
            str(p.with_name(f"{base}ch-tracks{p.suffix}")))


BINDABLE = {f"translate_{a}" for a in "xyz"} | \
    {f"scale_{a}" for a in "xyz"} | {"color_r", "color_g", "color_b", "color_a"}


def validate_channels(df: pd.DataFrame, ch_map_df: pd.DataFrame,
                      ch_tracks_df: pd.DataFrame) -> list[str]:
    """The three-way join the engine never checks for you: node
    ch_input_id -> map channel_id -> tracks ch<id> column, and the
    attribute names must be bindable."""
    problems = []
    channels = set(ch_map_df["channel_id"])
    used = set(df.loc[df.ch_input_id != 0, "ch_input_id"])
    orphaned = used - channels
    if orphaned:
        problems.append(f"ch_input_id with no map row: {sorted(orphaned)}")
    track_cols = {int(c[2:]) for c in ch_tracks_df.columns
                  if c.startswith("ch") and c[2:].isdigit()}
    missing = set(ch_map_df["track_id"]) - track_cols
    if missing:
        problems.append(f"map track_id with no ch<id> column: {sorted(missing)}")
    bad_attr = set(ch_map_df["attribute"]) - BINDABLE
    if bad_attr:
        problems.append(f"unbindable attributes: {sorted(bad_attr)}")
    alpha_cols = [f"ch{t}" for t in
                  ch_map_df.loc[ch_map_df.attribute == "color_a", "track_id"]]
    for c in set(alpha_cols):
        if ((ch_tracks_df[c] < 0) | (ch_tracks_df[c] > 255)).any():
            problems.append(f"tracks column {c}: alpha out of 0..255")
    return problems


# ---------------------------------------------------------------------------
# 4. VALIDATION (same checks as other gv_ example generators)
# ---------------------------------------------------------------------------
def validate(df: pd.DataFrame) -> list[str]:
    problems = []
    if df["id"].duplicated().any():
        problems.append("duplicate ids")
    if (df["id"] < 1).any():
        problems.append("ids must be >= 1")
    known = set(df["id"])
    bad_parents = df[(df.parent_id != 0) & (~df.parent_id.isin(known))]
    if len(bad_parents):
        problems.append(f"{len(bad_parents)} rows with unknown parent_id")
    links = df[df.type == 7]
    if len(links) and (~links.child_id.isin(known)).any():
        problems.append("link child_id references a missing node")
    for c in ("color_r", "color_g", "color_b", "color_a"):
        if ((df[c] < 0) | (df[c] > 255)).any():
            problems.append(f"{c} out of 0..255")
    vis = df[(df.hide == 0) & (df.type.isin([5, 7]))]
    if (vis[["scale_x", "scale_y", "scale_z"]] < 0.2).any(axis=None):
        problems.append("visible glyph with raw scale < 0.2")
    return problems


def write_csv(df: pd.DataFrame, path: str, float_format=None) -> None:
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\r\n",
              float_format=float_format)
    back = pd.read_csv(path, encoding="utf-8")
    assert len(back) == len(df), f"round-trip row-count mismatch: {path}"


# ---------------------------------------------------------------------------
# 5. MAIN
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--out", default="ybco_gv_node.csv",
                    help="output node CSV path")
    args = ap.parse_args()

    sb = SceneBuilder()
    sb.add(type=0, parent_id=0, branch_level=0,
          color_r=12, color_g=13, color_b=22, color_a=255, geometry=0,
          text="YBa2Cu3O7 (YBCO) -- the first liquid-nitrogen superconductor, Tc~92 K (1987)")

    crystal = build_crystal(sb)
    n_samples = build_plot(sb, origin_x=PLOT_ORIGIN_X)

    df = sb.to_dataframe()
    ch_map_df, ch_tracks_df = build_oxygen_channels()

    problems = validate(df)
    problems += validate_channels(df, ch_map_df, ch_tracks_df)
    if problems:
        for p in problems:
            print(f"VALIDATION FAILURE: {p}", file=sys.stderr)
        return 1

    write_csv(df, args.out, float_format="%.6f")
    map_path, tracks_path = channel_paths(args.out)
    write_csv(ch_map_df, map_path)
    write_csv(ch_tracks_df, tracks_path)
    print(f"Wrote {args.out}: {len(df)} rows "
          f"({len(crystal['atoms'])} atoms, {crystal['n_bonds']} Cu-O bonds, "
          f"{n_samples} resistivity samples). Validation clean.")
    print(f"Wrote {map_path}: {len(ch_map_df)} bindings")
    print(f"Wrote {tracks_path}: {len(ch_tracks_df)} frames x "
          f"{len(ch_tracks_df.columns) - 1} tracks "
          f"(oxygen-content delta 0<->1 sweep, {TOTAL_OX_FRAMES} frames)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
