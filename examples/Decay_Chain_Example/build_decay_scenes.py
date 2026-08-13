#!/usr/bin/env python3
"""
build_decay_scenes.py — radioactive decay chains as recursive hyperglyphs.

A decay chain is a tree whose depth is not a design choice: it is the data.
U-238 takes fourteen steps to reach lead; caesium-137 takes one.  Bismuth-212
genuinely forks, going beta-minus 64% of the time and alpha the other 36%,
and the two branches rejoin at Pb-208.  So the glyph nests as deeply as the
physics does, and comparing two glyphs compares two nuclear histories.

Each chain member is built from four levels of real quantities:

    hub        invisible placement frame, always scale 1 so that nesting
               fourteen deep never compounds a scale factor
    +- body    sphere sized by log half-life, coloured by dominant decay mode
    +- ring    Cylinder-topo frame carrying one petal per decay mode
    |  +- petal   azimuth = which mode, length = branching ratio
    |     +- tip  cone sized by the energy released (Q value)
    +- daughter hub ... and the chain descends from here

Horizontal offsets are the real chart-of-nuclides displacement (alpha steps
-2 protons and -2 neutrons, beta-minus +1 and -1) while each decay step rises
by a fixed height, so a chain glyph is a spiral staircase whose shadow is the
familiar zigzag on the chart of nuclides.

  Chain_Forest/        Sixteen chains side by side: the four natural series
                       plus radon, the reactor and fallout nuclides, the
                       americium in a smoke detector, and the dating clocks.
                       Depth ranges from one step to fourteen, and that
                       variation is the finding.

  Secular_Equilibrium/ The four natural series animated across thirteen
                       decades of logarithmic time, each member's activity
                       solved from the Bateman equations.  Watch equilibrium
                       fill a chain from the top down: every daughter climbs
                       until its activity matches its parent's, fast ones
                       almost at once, Th-230 and Pa-231 taking a hundred
                       thousand years.

Usage:
    python build_decay_scenes.py
    python build_decay_scenes.py --only Chain_Forest

Requires: numpy, pandas.  No network — reads the vendored IAEA table in data/.
"""
from __future__ import annotations

import argparse
import math
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import decay                                                       # noqa: E402

# ---------------------------------------------------------------------------
# 1. CONSTANTS
# ---------------------------------------------------------------------------
STEP_RISE = 11.0         # world units gained per decay step
CHART_XY = 1.5           # world units per unit of N or Z displacement

CUBE_HALF = 1.0 / math.sqrt(3.0)
LEN_TO_SCALE = 1.0 / (2.0 * CUBE_HALF)
SCALE_FLOOR = 0.2

GEO_CUBE, GEO_SPHERE, GEO_CONE = 1, 3, 5
GEO_ICOSA, GEO_CIRCLE, GEO_LINE = 15, 24, 27
TOPO_NONE, TOPO_CYLINDER = 0, 4
ROT_EULER, ROT_HTR = 0, 1

# Decay-mode identity: colour, ring azimuth, and a short label.
MODE_STYLE = {
    "A":     ((242, 138, 58), 0.0, "alpha"),
    "B-":    ((92, 158, 235), 120.0, "beta-"),
    "EC":    ((118, 205, 140), 240.0, "EC"),
    "B+":    ((118, 205, 140), 240.0, "beta+"),
    "EC+B+": ((118, 205, 140), 240.0, "EC/beta+"),
    "SF":    ((214, 106, 214), 60.0, "fission"),
}
MODE_DEFAULT = ((170, 170, 180), 300.0, "other")
STABLE_RGB = (247, 214, 118)

BG = (9, 10, 16, 255)
ACCENT = (232, 238, 250)

# The render floor applies to each node's OWN scale, so both of these must
# clear 0.2 in their own right.  The product matters for a different reason:
# a tip is drawn at petal_scale x tip_scale world units, and at the old
# 0.30 x 0.30 it was a nearly invisible 0.09.  These keep it legible.
PETAL_Y, PETAL_Z, TIP_MIN = 0.55, 0.45, 0.50
assert min(PETAL_Y, PETAL_Z) * TIP_MIN >= SCALE_FLOOR,     "petal x tip scale falls under the render floor"

# Half-life -> body size.  Real half-lives in these chains span 164 us to
# 14 Gyr, so the map is logarithmic; stable nuclides get the top of the range.
HL_LOG_LO, HL_LOG_HI = -6.0, 17.5
BODY_LO, BODY_HI = 0.85, 3.1
STABLE_BODY = 3.4


def sanitize(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t))
    return "".join(c for c in t if 32 <= ord(c) < 127).strip()


def body_scale(nuc) -> float:
    if nuc.stable:
        return STABLE_BODY
    hl = nuc.half_life_s or 1e-6
    f = (math.log10(max(hl, 1e-9)) - HL_LOG_LO) / (HL_LOG_HI - HL_LOG_LO)
    return BODY_LO + (BODY_HI - BODY_LO) * min(1.0, max(0.0, f))


def mode_style(mode: str):
    return MODE_STYLE.get(mode, MODE_DEFAULT)


def dominant_mode(nuc) -> str:
    if nuc.stable or not nuc.modes:
        return ""
    return max(nuc.modes, key=lambda m: m[1])[0]


def half_life_text(nuc) -> str:
    if nuc.stable:
        return "stable"
    s = nuc.half_life_s or 0.0
    for div, unit in ((3.156e16, "Gyr"), (3.156e13, "Myr"), (3.156e10, "kyr"),
                      (3.156e7, "yr"), (86400.0, "d"), (3600.0, "h"),
                      (60.0, "min")):
        if s >= div:
            return f"{s / div:.3g} {unit}"
    if s >= 1.0:
        return f"{s:.3g} s"
    if s >= 1e-3:
        return f"{s * 1e3:.3g} ms"
    return f"{s * 1e6:.3g} us"


# ---------------------------------------------------------------------------
# 2. SCENE BUILDER
# ---------------------------------------------------------------------------
COLUMNS = ["id", "type", "parent_id", "branch_level", "child_id",
           "translate_x", "translate_y", "translate_z",
           "rotate_x", "rotate_y", "rotate_z",
           "scale_x", "scale_y", "scale_z",
           "color_r", "color_g", "color_b", "color_a", "color_index",
           "geometry", "hide", "topo", "ratio", "texture_id",
           "ch_input_id", "show_text", "rotation_mode", "text"]

DEFAULTS = dict(child_id=0, translate_x=0.0, translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=255, color_g=255, color_b=255, color_a=255,
                color_index=0, geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE,
                ratio=0.1, texture_id=0, ch_input_id=0, show_text=0,
                rotation_mode=ROT_EULER, text="")


@dataclass
class SceneBuilder:
    rows: list[dict] = field(default_factory=list)
    next_id: int = 1

    def add(self, **kw) -> int:
        self.rows.append({**DEFAULTS, "id": self.next_id, **kw})
        self.next_id += 1
        return self.next_id - 1

    def world(self) -> int:
        return self.add(type=0, parent_id=0, branch_level=0, geometry=0,
                        color_r=BG[0], color_g=BG[1], color_b=BG[2],
                        color_a=BG[3])

    def caption(self, text, size=2.0, rgb=ACCENT, ch=0, **pos) -> int:
        return self.add(type=5, parent_id=0, branch_level=0,
                        scale_x=size, scale_y=size, scale_z=size,
                        geometry=GEO_CIRCLE, ratio=0.02,
                        color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                        color_a=205, show_text=1, text=sanitize(text),
                        ch_input_id=ch, **pos)

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=COLUMNS)


# ---------------------------------------------------------------------------
# 3. CHAIN GLYPH
# ---------------------------------------------------------------------------
def spanning_tree(nodes, root):
    """BFS spanning tree over the decay DAG.

    A chain is a DAG, not a tree — Bi-212's two branches both end at Pb-208 —
    but a node can only have one parent_id.  Each node is therefore attached
    to the first parent that reaches it, and every remaining edge is drawn as
    a Link so the fork is still visible.
    """
    parent = {root: None}
    order = [root]
    queue = [root]
    while queue:
        k = queue.pop(0)
        for ckey, mode, frac in nodes[k].children:
            if ckey not in parent:
                parent[ckey] = (k, mode, frac)
                order.append(ckey)
                queue.append(ckey)
    extra = [(k, ckey, mode, frac) for k in nodes
             for ckey, mode, frac in nodes[k].children
             if parent.get(ckey, (None,))[0] != k]
    return parent, order, extra


@dataclass
class ChainStats:
    members: int = 0
    max_depth: int = 0
    forks: int = 0
    petals: int = 0


def add_chain(sb: SceneBuilder, parent_id: int, base_level: int,
              nodes, root, stats: ChainStats, *,
              root_kw: dict, label: str = "", label_lift: float = 0.0,
              activity_nodes: dict | None = None,
              show_member_text: bool = False,
              pin_all_members: bool = False) -> dict:
    """Build one chain glyph.  Returns {(z,n): hub node id}."""
    parent, order, extra = spanning_tree(nodes, root)
    step_of = {root: 0}
    hub_of: dict[tuple[int, int], int] = {}

    # centre the glyph on its own chart footprint so neighbours do not collide
    dn = [nodes[k].nuc.n - nodes[root].nuc.n for k in order]
    dz = [nodes[k].nuc.z - nodes[root].nuc.z for k in order]
    off_x = -(max(dn) + min(dn)) / 2.0 * CHART_XY
    off_y = -(max(dz) + min(dz)) / 2.0 * CHART_XY

    # Level of this chain's own root hub. GlyphViz roots are branch_level 0
    # (GaiaViz's convention of 1 does not apply), so a chain attached straight
    # to the scene root sits at base_level; one hanging off a real parent node
    # sits one deeper.
    lvl0 = base_level + 1 if parent_id else base_level

    for key in order:
        nuc = nodes[key].nuc
        par = parent[key]
        if par is None:
            step_of[key] = 0
            hub = sb.add(type=5, parent_id=parent_id,
                         branch_level=lvl0, topo=TOPO_NONE,
                         hide=1, geometry=GEO_CUBE, **root_kw)
            # shift the whole glyph so its footprint is centred on root_kw
            sb.rows[hub - 1]["translate_x"] += off_x
            sb.rows[hub - 1]["translate_y"] += off_y
        else:
            pkey, _mode, _frac = par
            step_of[key] = step_of[pkey] + 1
            pnuc = nodes[pkey].nuc
            hub = sb.add(type=5, parent_id=hub_of[pkey],
                         branch_level=lvl0 + step_of[key],
                         topo=TOPO_NONE, hide=1, geometry=GEO_CUBE,
                         translate_x=(nuc.n - pnuc.n) * CHART_XY,
                         translate_y=(nuc.z - pnuc.z) * CHART_XY,
                         translate_z=STEP_RISE)
        hub_of[key] = hub
        lvl = lvl0 + step_of[key]
        stats.members += 1
        stats.max_depth = max(stats.max_depth, step_of[key])

        # --- body: size = log half-life, colour = dominant decay mode ------
        dm = dominant_mode(nuc)
        rgb = STABLE_RGB if nuc.stable else mode_style(dm)[0]
        bs = body_scale(nuc)
        txt = f"{nuc.name}  {half_life_text(nuc)}"
        pinned = show_member_text and (pin_all_members or nuc.stable
                                       or key == root)
        sb.add(type=5, parent_id=hub, branch_level=lvl + 1,
               geometry=GEO_ICOSA if nuc.stable else GEO_SPHERE,
               scale_x=bs, scale_y=bs, scale_z=bs,
               color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=245,
               show_text=1 if pinned else 0, text=sanitize(txt))

        # --- activity sphere (animated in Secular_Equilibrium) --------------
        if activity_nodes is not None and not nuc.stable:
            aid = sb.add(type=5, parent_id=hub, branch_level=lvl + 1,
                         geometry=GEO_SPHERE, scale_x=0.4, scale_y=0.4,
                         scale_z=0.4, color_r=255, color_g=248, color_b=210,
                         color_a=150)
            activity_nodes[key] = aid

        if nuc.stable:
            continue

        # --- ring of decay-mode petals -------------------------------------
        kept = [(m, f) for m, f in nuc.modes
                if f >= 0.005 and decay.MODE_DELTA.get(m, "x") is not None]
        if not kept:
            kept = [(dm, 1.0)] if dm else []
        if len(kept) > 1:
            stats.forks += 1
        ring = sb.add(type=5, parent_id=hub, branch_level=lvl + 1,
                      topo=TOPO_CYLINDER, hide=1, geometry=GEO_CUBE)
        for mode, frac in kept:
            prgb, azim, _lab = mode_style(mode)
            plen = 1.1 + 3.2 * frac
            petal = sb.add(type=5, parent_id=ring, branch_level=lvl + 2,
                           translate_x=azim, translate_y=0.0,
                           translate_z=plen / 2.0 - 1.0,
                           geometry=GEO_CUBE,
                           scale_x=plen * 0.5 * LEN_TO_SCALE,
                           scale_y=PETAL_Y, scale_z=PETAL_Z,
                           color_r=prgb[0], color_g=prgb[1], color_b=prgb[2],
                           color_a=240)
            stats.petals += 1
            # --- tip: the energy released by this mode ---------------------
            q = nuc.q_alpha if mode == "A" else nuc.q_beta
            q_mev = abs(float(q)) / 1000.0
            ts = TIP_MIN + 0.20 * min(6.0, q_mev)
            sb.add(type=5, parent_id=petal, branch_level=lvl + 3,
                   translate_x=1.05, translate_y=0.0, translate_z=0.0,
                   geometry=GEO_CONE, rotation_mode=ROT_HTR, rotate_x=90.0,
                   scale_x=ts, scale_y=ts, scale_z=ts * 1.6,
                   color_r=min(255, prgb[0] + 25), color_g=min(255, prgb[1] + 25),
                   color_b=min(255, prgb[2] + 25), color_a=235)

    # --- links along every decay edge, tree and non-tree alike -------------
    for key in order:
        par = parent[key]
        if par is None:
            continue
        pkey, mode, frac = par
        prgb = mode_style(mode)[0]
        sb.add(type=7, parent_id=hub_of[pkey], child_id=hub_of[key],
               branch_level=lvl0, geometry=GEO_LINE,
               ratio=0.05 + 0.10 * frac,
               color_r=prgb[0], color_g=prgb[1], color_b=prgb[2], color_a=170)
    for pkey, ckey, mode, frac in extra:
        prgb = mode_style(mode)[0]
        sb.add(type=7, parent_id=hub_of[pkey], child_id=hub_of[ckey],
               branch_level=lvl0, geometry=GEO_LINE,
               ratio=0.05 + 0.10 * frac,
               color_r=prgb[0], color_g=prgb[1], color_b=prgb[2], color_a=170)

    if label:
        top = max(step_of.values()) * STEP_RISE + 6.0 + label_lift
        sb.add(type=5, parent_id=hub_of[root], branch_level=lvl0 + 1,
               translate_x=-off_x, translate_y=-off_y, translate_z=top,
               geometry=GEO_CIRCLE, ratio=0.02,
               scale_x=0.9, scale_y=0.9, scale_z=0.9,
               color_r=ACCENT[0], color_g=ACCENT[1], color_b=ACCENT[2],
               color_a=215, show_text=1, text=sanitize(label))
    return hub_of


# ---------------------------------------------------------------------------
# 4. SCENE 1 — CHAIN FOREST
# ---------------------------------------------------------------------------
FOREST = [
    ("Th-232", "thorium series (4n) - 14 Gyr, the commonest actinide"),
    ("U-235", "actinium series (4n+3) - the fissile one"),
    ("U-238", "uranium series (4n+2) - 99.3% of natural uranium"),
    ("Np-237", "neptunium series (4n+1) - extinct in nature"),
    ("Pu-239", "reactor and weapons plutonium"),
    ("Am-241", "the smoke detector nuclide"),
    ("Ra-226", "Curie's radium"),
    ("Rn-222", "radon gas - 2nd leading cause of lung cancer"),
    ("Cs-137", "fallout and reactor accidents"),
    ("Sr-90", "bone-seeking fission product"),
    ("I-131", "thyroid dose, and thyroid therapy"),
    ("Mo-99", "the Tc-99m generator of nuclear medicine"),
    ("Co-60", "sterilisation and radiotherapy"),
    ("K-40", "in every banana - and it branches"),
    ("C-14", "radiocarbon dating"),
    ("H-3", "tritium - the simplest chain of all"),
]


def build_chain_forest(tbl):
    sb = SceneBuilder()
    sb.world()
    stats = ChainStats()

    # Sort by how many decay steps the chain takes, so the forest reads as a
    # skyline climbing from tritium's single step to uranium's fourteen.
    prepared = []
    for name, note in FOREST:
        nuc = tbl.by_name(name)
        if nuc is None:
            print(f"  !! {name} not in the nuclide table")
            continue
        nodes = decay.build_chain(tbl, nuc)
        root = (nuc.z, nuc.n)
        steps = max(n.depth for n in nodes.values())
        prepared.append((steps, name, note, nuc, nodes, root))
    prepared.sort(key=lambda r: (r[0], r[1]))

    pitch_x = 44.0
    for i, (_steps, _name, note, nuc, nodes, root) in enumerate(prepared):
        cy = (i - (len(prepared) - 1) / 2.0) * pitch_x
        add_chain(sb, 0, 0, nodes, root, stats,
                  root_kw=dict(translate_x=0.0, translate_y=cy,
                               translate_z=0.0),
                  label=f"{nuc.name} - {note}",
                  # neighbouring chains of similar height would otherwise put
                  # their titles on the same line and collide
                  label_lift=(i % 2) * 13.0,
                  show_member_text=True)
    built = len(prepared)

    sb.caption("Radioactive decay chains - depth is the data, not a design "
               "choice", size=3.0,
               translate_x=0.0,
               translate_y=-pitch_x * len(prepared) / 2.0,
               translate_z=118.0)
    sb.caption("body size = log half-life | colour = decay mode (orange alpha,"
               " blue beta-, green EC, gold stable) | petal = branching ratio"
               " | tip = energy released", size=1.7,
               translate_x=0.0,
               translate_y=-pitch_x * len(prepared) / 2.0,
               translate_z=110.0)
    return sb.to_dataframe(), stats, built


# ---------------------------------------------------------------------------
# 5. SCENE 2 — SECULAR EQUILIBRIUM
# ---------------------------------------------------------------------------
SERIES = [("Th-232", "thorium series"), ("U-235", "actinium series"),
          ("U-238", "uranium series"), ("Np-237", "neptunium series")]

T_LOG_LO, T_LOG_HI, N_FRAMES = 3.0, 16.0, 120


def time_label(sec: float) -> str:
    for div, unit in ((3.156e16, "Gyr"), (3.156e13, "Myr"), (3.156e10, "kyr"),
                      (3.156e7, "yr"), (86400.0, "d"), (3600.0, "h")):
        if sec >= div:
            return f"{sec / div:.3g} {unit}"
    return f"{sec:.3g} s"


def build_secular_equilibrium(tbl):
    times = list(np.logspace(T_LOG_LO, T_LOG_HI, N_FRAMES))
    sb = SceneBuilder()
    sb.world()
    stats = ChainStats()

    map_rows: list[dict] = []
    data: dict[str, list] = {"cyclecount": list(range(1, N_FRAMES + 1))}
    chan = [1]

    def bind(c: int, track: int, attr: str) -> None:
        map_rows.append(dict(id=len(map_rows) + 1, channel_id=c,
                             track_id=track, attribute=attr,
                             track_table_id=0, ch_map_table_id=0, record_id=0))

    pitch_x = 76.0
    for i, (name, note) in enumerate(SERIES):
        nuc = tbl.by_name(name)
        nodes = decay.build_chain(tbl, nuc)
        root = (nuc.z, nuc.n)
        acts = decay.activities(nodes, root, times)
        act_nodes: dict = {}
        cy = (i - (len(SERIES) - 1) / 2.0) * pitch_x
        add_chain(sb, 0, 0, nodes, root, stats,
                  root_kw=dict(translate_x=0.0, translate_y=cy,
                               translate_z=0.0),
                  label=f"{nuc.name} - {note}",
                  activity_nodes=act_nodes, show_member_text=True,
                  # only four chains here and their members are well separated
                  # vertically, so every one can carry a permanent label
                  pin_all_members=True)

        for key, node_id in act_nodes.items():
            series = acts.get(key, [0.0] * len(times))
            c = chan[0]
            chan[0] += 1
            track = c
            # one channel, three attributes, one shared track: a sphere has to
            # grow on all three axes at once
            for attr in ("scale_x", "scale_y", "scale_z"):
                bind(c, track, attr)
            vals = [round(0.35 + 2.4 * math.sqrt(min(1.35, max(0.0, v))), 4)
                    for v in series]
            data[f"ch{track}"] = vals
            sb.rows[node_id - 1]["ch_input_id"] = c
            # the unplayed scene should already show frame 0 (a pure parent
            # sample) rather than an arbitrary placeholder size
            for ax in ("scale_x", "scale_y", "scale_z"):
                sb.rows[node_id - 1][ax] = vals[0]

    # --- logarithmic time axis with a tracking cursor ----------------------
    axis_x = 34.0
    x0, x1 = -150.0, 150.0

    def x_of(log_t: float) -> float:
        f = (log_t - T_LOG_LO) / (T_LOG_HI - T_LOG_LO)
        return x0 + (x1 - x0) * f

    for d in range(int(T_LOG_LO), int(T_LOG_HI) + 1):
        if d % 2:
            continue
        sb.add(type=5, parent_id=0, branch_level=0,
               translate_x=axis_x, translate_y=x_of(d),
               translate_z=0.0,
               geometry=GEO_CIRCLE, ratio=0.02,
               scale_x=0.8, scale_y=0.8, scale_z=0.8,
               color_r=130, color_g=142, color_b=170, color_a=190,
               show_text=1, text=sanitize(time_label(10.0 ** d)))

    cursor_ch = chan[0]
    chan[0] += 1
    cursor = sb.add(type=5, parent_id=0, branch_level=0,
                    translate_x=axis_x, translate_y=x_of(T_LOG_LO),
                    translate_z=4.0, geometry=GEO_CONE,
                    rotation_mode=ROT_HTR, rotate_x=180.0,
                    scale_x=2.0, scale_y=2.0, scale_z=3.0,
                    color_r=255, color_g=224, color_b=120, color_a=250,
                    show_text=1, text="time since the sample was pure parent",
                    ch_input_id=cursor_ch)
    bind(cursor_ch, cursor_ch, "translate_y")
    data[f"ch{cursor_ch}"] = [round(x_of(math.log10(t)), 3) for t in times]
    _ = cursor

    sb.caption("Secular equilibrium - the Bateman equations across thirteen "
               "decades of time", size=3.0,
               translate_x=0.0, translate_y=-150.0, translate_z=186.0)
    sb.caption("pale sphere = activity relative to the parent's initial "
               "activity; equilibrium is reached when it stops growing",
               size=1.7,
               translate_x=0.0, translate_y=-150.0, translate_z=178.0)

    return (sb.to_dataframe(), pd.DataFrame(map_rows), pd.DataFrame(data),
            stats, len(SERIES))


# ---------------------------------------------------------------------------
# 6. VALIDATION + OUTPUT
# ---------------------------------------------------------------------------
def validate(df: pd.DataFrame) -> list[str]:
    errs = []
    if df.id.duplicated().any():
        errs.append("duplicate node ids")
    ids = set(df.id)
    bad = df[(df.parent_id != 0) & (~df.parent_id.isin(ids))]
    if len(bad):
        errs.append(f"{len(bad)} rows reference a missing parent")
    links = df[df.type == 7]
    if len(links) and not links.child_id.isin(ids).all():
        errs.append("a link points at a missing child_id")
    for c in ("color_r", "color_g", "color_b", "color_a"):
        if not df[c].between(0, 255).all():
            errs.append(f"{c} out of range")
    if not df.geometry.between(0, 28).all():
        errs.append("geometry id out of range")
    vis = df[(df.hide == 0) & (df.type == 5)]
    for c in ("scale_x", "scale_y", "scale_z"):
        if (vis[c] < SCALE_FLOOR - 1e-9).any():
            errs.append(f"{c} below the {SCALE_FLOOR} render floor")
    return errs


def write_csv(df: pd.DataFrame, path: Path, float_format="%.4f") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\r\n",
              float_format=float_format)
    back = pd.read_csv(path, encoding="utf-8", low_memory=False)
    assert len(back) == len(df), f"{path.name} did not round-trip"


def emit(name: str, stem: str, node_df, ch_map=None, ch_tracks=None) -> bool:
    errs = validate(node_df)
    if errs:
        print(f"  !! {name}: " + "; ".join(errs))
        return False
    out = HERE / name
    write_csv(node_df, out / f"{stem}_gv_node.csv")
    if ch_map is not None and len(ch_map):
        write_csv(ch_map, out / f"{stem}_gv_ch-map.csv", float_format="%.6g")
        write_csv(ch_tracks, out / f"{stem}_gv_ch-tracks.csv")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e6
    print(f"  wrote {name}/  {len(node_df):,} nodes  ({size:.1f} MB)")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    tbl = decay.NuclideTable()
    print(f"nuclide table: {len(tbl)} ground states")

    ok = True
    if args.only in ("", "Chain_Forest"):
        df, stats, n = build_chain_forest(tbl)
        print(f"Chain_Forest: {n} chains, {stats.members} members, "
              f"deepest chain {stats.max_depth} decay steps, "
              f"{stats.forks} branching nuclides, {stats.petals} mode petals")
        ok &= emit("Chain_Forest", "chain_forest", df)

    if args.only in ("", "Secular_Equilibrium"):
        df, cmap, ctr, stats, n = build_secular_equilibrium(tbl)
        print(f"Secular_Equilibrium: {n} series, {stats.members} members, "
              f"deepest {stats.max_depth} steps, "
              f"{len(ctr.columns) - 1} tracks x {len(ctr)} frames")
        ok &= emit("Secular_Equilibrium", "secular_equilibrium", df, cmap, ctr)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
