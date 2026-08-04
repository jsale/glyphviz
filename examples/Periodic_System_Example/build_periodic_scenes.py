#!/usr/bin/env python3
"""
build_periodic_scenes.py — the periodic system as a hyperglyph, not a table
===========================================================================

The periodic table is a spreadsheet with a ragged left edge and two rows
exiled to a footnote. That shape is a printing compromise, not the physics.
This builds the same information as a **helix of nested atoms**, where the
periodicity is geometry rather than a caption.

  Madelung_Helix/    All 118 elements on a GlyphViz Spiral topology, one turn
                     per Madelung (n+l) filling group. Each element is a
                     hyperglyph: a nucleus sized by atomic radius and coloured
                     by electronegativity, wrapped in its **real** electron
                     configuration — one glyph per electron, on concentric
                     Sphere-topology shells. 7,021 electrons in all.

  Aufbau_Sequence/   The same helix, built one element at a time in atomic
                     order. Watch the shells fill, the 4s slot take an
                     electron before 3d does, and the f-block appear.

## Why a helix, and why this helix

Order the subshells the way nature fills them — by increasing n+l, and
within equal n+l by increasing n — and they fall into groups of length
2, 2, 8, 8, 18, 18, 32, 32. Every group is a *suffix* of the longest one:

    n+l=1   [s]              2      <- 1s
    n+l=3   [p][s]           8      <- 2p 3s
    n+l=5   [d][p][s]       18      <- 3d 4p 5s
    n+l=7   [f][d][p][s]    32      <- 4f 5d 6p 7s

So if each turn of the helix is one n+l group, and every turn is
**right-aligned** onto a common 32-slot angular grid, then all eight turns
line up: the s-block is always the last two slots, the p-block the six
before that, and so on. Groups become exact vertical columns — not by
construction, but because the filling rule is nested.

This is the Janet "left-step" arrangement, wound up. It has two consequences
worth looking at rather than arguing about:

  * **Helium lands above beryllium**, not above neon, because helium's
    valence structure is s2. That is the left-step table's most contested
    claim, and here it is a position rather than an opinion.
  * **The f-block stops being a footnote.** It is simply the first fourteen
    slots of the two longest turns, in the same column system as everything
    else.

## Layout is idealised; the atoms are real

Elements are *placed* by the idealised Madelung rule, but *drawn* from their
observed configuration (PubChem's, anomalies included). So the nineteen
elements that break the rule — chromium, copper, gadolinium, the platinum
group — visibly differ from the column they are standing in. Each is marked
with a white cross.

Data: PubChem Periodic Table of Elements (public domain, NCBI/NLM),
vendored as data/pubchem_periodictable.csv. See elements.py for the
configuration parsing, Madelung layout and Hund's-rule filling.

Usage:
    python build_periodic_scenes.py
    python build_periodic_scenes.py --only Madelung_Helix

Requires: pandas
"""

from __future__ import annotations

import argparse
import math
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import elements as E                                              # noqa: E402

# ---------------------------------------------------------------------------
# 1. GEOMETRY CONSTANTS (the knobs)
# ---------------------------------------------------------------------------
HELIX_R = 64.0                 # radius of the helix, world units
# Rise per turn only has to clear one atom's diameter (~9 units at the
# largest); keeping it tight stops the helix stretching into a diagonal
# sheet that reads as a lattice rather than a winding.
TURN_RISE = 20.0
SLOT_DEG = 360.0 / E.SLOTS_PER_TURN     # 11.25 deg per slot

# Atom sizing. The element node's scale carries its whole subtree, so this
# one number sets the nucleus size AND the electron-shell radii together —
# which is the physically right coupling: a bigger atom is bigger all through.
ATOM_SCALE_LO, ATOM_SCALE_HI = 0.50, 0.95
SHELL_R0, SHELL_DR = 1.90, 0.52         # shell radius = R0 + DR*n
ELECTRON_SCALE = 0.32          # big enough to read from outside the atom,
#                                small enough that shells stay separate

# Arc length between neighbouring slots is 2*pi*R/32 = 13.4 units; the
# widest atom is SHELL_R(7) * ATOM_SCALE_HI ~ 4.8, so atoms clear each other.
LAT_BAND = {0: 14.0, 1: 36.0, 2: 58.0, 3: 78.0}     # latitude band per l
LON_PHASE = {0: 0.0, 1: 17.0, 2: 34.0, 3: 51.0}     # separates the subshells
# Successive principal shells are also twisted, because without this every
# subshell of a given l sits at the same longitude and latitude and differs
# only in radius — so all six s electrons of a heavy atom line up into one
# radial spike and the atom reads as a sea urchin instead of a set of shells.
LON_TWIST_PER_N = 21.0

BLOCK_RGB = {"s": (255, 214, 92), "p": (255, 122, 106),
             "d": (96, 214, 235), "f": (186, 130, 255)}
BLOCK_IDX = {"s": 4, "p": 6, "d": 7, "f": 5}        # palette-0 equivalents

EN_LO, EN_HI = 0.7, 3.98       # Pauling electronegativity range (Cs .. F)
EN_COLD = (72, 132, 255)       # electropositive metals
EN_HOT = (255, 74, 52)         # fluorine, oxygen
EN_NONE = (135, 135, 148)      # no published value (noble gases, superheavy)

BG_COLOR = (7, 7, 18, 255)
ACCENT = (255, 200, 110)

HOLD_FRAMES = 40               # tail frames after the last element appears


def sanitize(t: str) -> str:
    return "".join(c for c in str(t)
                   if unicodedata.category(c)[0] != "C").strip()


# ---------------------------------------------------------------------------
# 2. ENCODINGS
# ---------------------------------------------------------------------------
def shell_radius(n: int) -> float:
    return SHELL_R0 + SHELL_DR * n


def en_color(en: float | None) -> tuple[tuple[int, int, int], int]:
    """Electronegativity -> (rgb, color_index on palette 8 Blue->Red)."""
    if en is None:
        return EN_NONE, 0
    t = min(max((en - EN_LO) / (EN_HI - EN_LO), 0.0), 1.0)
    rgb = tuple(int(round(a + (b - a) * t))
                for a, b in zip(EN_COLD, EN_HOT))
    return rgb, int(round(t * 127))


def atom_scale(radius_pm: float | None, lo: float, hi: float) -> float:
    if radius_pm is None:
        return (ATOM_SCALE_LO + ATOM_SCALE_HI) / 2.0
    t = (radius_pm - lo) / (hi - lo) if hi > lo else 0.5
    t = min(max(t, 0.0), 1.0)
    return round(ATOM_SCALE_LO + t * (ATOM_SCALE_HI - ATOM_SCALE_LO), 4)


def resolve_radii(els: list[E.Element]) -> dict[int, float]:
    """Atomic radius per element, filling PubChem's gaps (Z >= 100) from the
    element directly above in the same column — a group trend, which is the
    least-invented substitute available. Documented in the README."""
    lay = E.madelung_layout()
    by_slot: dict[int, list[E.Element]] = {}
    for e in els:
        by_slot.setdefault(lay[e.z].slot, []).append(e)
    out: dict[int, float] = {}
    for e in els:
        if e.radius_pm is not None:
            out[e.z] = e.radius_pm
            continue
        column = sorted(by_slot[lay[e.z].slot], key=lambda x: x.z)
        above = [c for c in column if c.z < e.z and c.radius_pm is not None]
        out[e.z] = above[-1].radius_pm if above else 200.0
    return out


def helix_coords(turn: int, slot: int) -> tuple[float, float, float]:
    """Spiral-topology coordinates for a slot on a turn.

    Spiral places a child at ((B+tz)cos tx, (B+tz)sin tx, (tx/360)B + ty)
    with B = 1, so tz carries the radius and ty corrects the pitch. tx keeps
    counting past 360, which is exactly what a multi-turn helix wants.
    """
    tx = 360.0 * turn + SLOT_DEG * slot
    tz = HELIX_R - 1.0
    ty = (tx / 360.0) * (TURN_RISE - 1.0)
    return tx, ty, tz


# ---------------------------------------------------------------------------
# 3. SCENE BUILDER
# ---------------------------------------------------------------------------
COLUMNS = ["id", "type", "parent_id", "branch_level", "child_id",
           "translate_x", "translate_y", "translate_z",
           "rotate_x", "rotate_y", "rotate_z",
           "scale_x", "scale_y", "scale_z",
           "color_r", "color_g", "color_b", "color_a", "color_index",
           "palette_id", "geometry", "hide", "topo", "ratio", "texture_id",
           "ch_input_id", "rotate_rate_z", "show_text",
           "segments_x", "segments_y", "rotation_mode", "text", "link"]

DEFAULTS = dict(child_id=0, translate_x=0.0, translate_y=0.0,
                translate_z=0.0, rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=255, color_g=255, color_b=255, color_a=255,
                color_index=0, palette_id=0, geometry=3, hide=0, topo=0,
                ratio=0.1, texture_id=0, ch_input_id=0, rotate_rate_z=0.0,
                show_text=0, segments_x=16, segments_y=16, rotation_mode=0,
                text="", link="")

TOPO_SPHERE, TOPO_SPIRAL = 2, 14


@dataclass
class SceneBuilder:
    rows: list[dict] = field(default_factory=list)
    next_id: int = 1

    def add(self, **kw) -> int:
        self.rows.append({**DEFAULTS, "id": self.next_id, **kw})
        self.next_id += 1
        return self.next_id - 1

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=COLUMNS)


def build(els: list[E.Element], animate: bool):
    lay = E.madelung_layout()
    radii = resolve_radii(els)
    r_lo, r_hi = min(radii.values()), max(radii.values())
    n_turns = max(p.turn for p in lay.values()) + 1

    sb = SceneBuilder()
    sb.add(type=0, parent_id=0, branch_level=0, geometry=0,
           color_r=BG_COLOR[0], color_g=BG_COLOR[1], color_b=BG_COLOR[2],
           color_a=BG_COLOR[3])

    # The helix itself. Centred vertically so the camera frames it squarely.
    z0 = -(n_turns - 1) * TURN_RISE / 2.0
    spiral = sb.add(type=5, parent_id=0, branch_level=0,
                    translate_x=0.0, translate_y=0.0, translate_z=z0,
                    scale_x=1.0, scale_y=1.0, scale_z=1.0,
                    geometry=11, topo=TOPO_SPIRAL, ratio=0.1,
                    color_r=120, color_g=120, color_b=140, color_a=150,
                    text="Madelung helix (one turn per n+l group)")

    node_of: dict[int, int] = {}
    n_electrons = 0
    for e in els:
        p = lay[e.z]
        tx, ty, tz = helix_coords(p.turn, p.slot)
        s = atom_scale(radii[e.z], r_lo, r_hi)
        rgb, cidx = en_color(e.electronegativity)
        ch = e.z if animate else 0

        eid = sb.add(type=5, parent_id=spiral, branch_level=1,
                     translate_x=round(tx, 4), translate_y=round(ty, 4),
                     translate_z=round(tz, 4),
                     scale_x=s, scale_y=s, scale_z=s,
                     geometry=3, topo=TOPO_SPHERE,
                     color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                     color_a=255, color_index=cidx, palette_id=8,
                     ch_input_id=ch, show_text=1,
                     text=sanitize(e.symbol),
                     link=f"https://pubchem.ncbi.nlm.nih.gov/element/{e.z}")
        node_of[e.z] = eid

        # One glyph per electron, on its real shell.
        for (n, l), q in sorted(e.config.items()):
            for (orbital, spin) in E.hund_fill(l, q):
                lon = (360.0 * orbital / (2 * l + 1) + LON_PHASE[l]
                       + LON_TWIST_PER_N * n)
                lat = LAT_BAND[l] * (1.0 if spin == 0 else -1.0)
                brgb = BLOCK_RGB[E.ORBITALS[l]]
                sb.add(type=5, parent_id=eid, branch_level=2,
                       translate_x=round(lon % 360.0, 3),
                       translate_y=round(lat, 3),
                       translate_z=round(shell_radius(n) - 1.0, 4),
                       scale_x=ELECTRON_SCALE, scale_y=ELECTRON_SCALE,
                       scale_z=ELECTRON_SCALE, geometry=11,
                       color_r=brgb[0], color_g=brgb[1], color_b=brgb[2],
                       color_a=255, color_index=BLOCK_IDX[E.ORBITALS[l]],
                       ch_input_id=ch)
                n_electrons += 1

        # Mark the elements whose real configuration breaks the rule that
        # decided where they are standing.
        if e.is_anomalous:
            sb.add(type=5, parent_id=eid, branch_level=2,
                   translate_x=0.0, translate_y=90.0,
                   translate_z=round(shell_radius(7) - 1.0, 4),
                   scale_x=0.75, scale_y=0.75, scale_z=0.75, geometry=25,
                   color_r=255, color_g=255, color_b=255, color_a=255,
                   ch_input_id=ch,
                   # Short on purpose: nineteen sentences pinned around a
                   # helix is a wall of text. The key explains the cross.
                   text=f"{e.symbol} breaks aufbau")

    # Group columns: a link from each element to the one directly above it.
    by_slot: dict[int, list[E.Element]] = {}
    for e in els:
        by_slot.setdefault(lay[e.z].slot, []).append(e)
    n_links = 0
    for slot, members in sorted(by_slot.items()):
        members = sorted(members, key=lambda x: x.z)
        for a, b in zip(members, members[1:]):
            brgb = BLOCK_RGB[lay[b.z].block]
            sb.add(type=7, parent_id=node_of[a.z], child_id=node_of[b.z],
                   branch_level=2, geometry=27,
                   color_r=brgb[0], color_g=brgb[1], color_b=brgb[2],
                   color_a=110, ch_input_id=b.z if animate else 0)
            n_links += 1

    # --- captions and keys --------------------------------------------------
    top = z0 + (n_turns - 1) * TURN_RISE + TURN_RISE * 0.55

    def caption(z, text, size=2.2, rgb=ACCENT, x=0.0):
        sb.add(type=5, parent_id=0, branch_level=0,
               translate_x=x, translate_y=0.0, translate_z=z,
               scale_x=size, scale_y=size, scale_z=size, geometry=11,
               color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=235,
               show_text=1, text=sanitize(text))

    # Separated in x as well as z: viewed straight down the axis — which is
    # the view that shows the periodicity best — a purely vertical stack of
    # captions projects onto the same point and the two lines overprint.
    caption(top + 16.0, "The periodic system as a helix — one turn per "
                        "Madelung (n+l) group", size=2.6)
    caption(top + 8.0, "every turn right-aligned on 32 slots, so each group "
                       "is a true vertical column", size=1.6, x=-44.0)

    key_x = -(HELIX_R + 46.0)
    sb.add(type=5, parent_id=0, branch_level=0,
           translate_x=key_x, translate_y=0.0, translate_z=34.0,
           scale_x=1.7, scale_y=1.7, scale_z=1.7, geometry=11,
           color_r=ACCENT[0], color_g=ACCENT[1], color_b=ACCENT[2],
           color_a=225, show_text=1,
           text="electron colour = subshell")
    for k, blk in enumerate("spdf"):
        rgb = BLOCK_RGB[blk]
        sb.add(type=5, parent_id=0, branch_level=0,
               translate_x=key_x, translate_y=0.0, translate_z=24.0 - k * 9.0,
               scale_x=2.2, scale_y=2.2, scale_z=2.2, geometry=11,
               color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=255,
               color_index=BLOCK_IDX[blk], show_text=1,
               text=f"{blk}-block  ({2*(2*'spdf'.index(blk)+1)} electrons)")
    for k, (label, rgb) in enumerate((
            ("nucleus size = atomic radius", EN_NONE),
            ("nucleus colour = electronegativity (blue low, red high)",
             EN_HOT),
            ("north hemisphere = spin up, south = spin down", (220, 220, 235)),
            ("shell radius = principal quantum number n", (220, 220, 235)),
            ("white cross = observed configuration breaks strict aufbau",
             (255, 255, 255)))):
        sb.add(type=5, parent_id=0, branch_level=0,
               translate_x=key_x, translate_y=0.0,
               translate_z=-22.0 - k * 9.0,
               scale_x=1.6, scale_y=1.6, scale_z=1.6, geometry=11,
               color_r=rgb[0], color_g=rgb[1], color_b=rgb[2], color_a=225,
               show_text=1, text=label)

    info = {"elements": len(els), "electrons": n_electrons,
            "links": n_links, "turns": n_turns,
            "anomalous": sum(1 for e in els if e.is_anomalous)}
    return sb.to_dataframe(), info


# ---------------------------------------------------------------------------
# 4. CHANNELS — the aufbau sequence
# ---------------------------------------------------------------------------
def build_channels(els: list[E.Element]):
    """One channel per element, keyed on atomic number: an element (and every
    electron it owns) is invisible until its turn, flashes when it arrives,
    then settles."""
    total = len(els) + HOLD_FRAMES
    rows = []
    for e in els:
        # Two bindings off ONE track. Alpha alone is not enough: a pinned
        # label draws whenever its node draws, and a node at alpha 0 still
        # draws — so without gating show_text as well, every element's
        # symbol hangs in space long before the element exists. The alpha
        # track is 0 before birth and positive after, which is exactly the
        # on/off flag show_text wants.
        for attr in ("color_a", "show_text"):
            rows.append(dict(id=len(rows) + 1, channel_id=e.z, track_id=e.z,
                             attribute=attr, track_table_id=0,
                             ch_map_table_id=0, record_id=0))
    ch_map = pd.DataFrame(rows)

    data: dict[str, list] = {"cyclecount": list(range(1, total + 1))}
    for e in els:
        birth = e.z - 1
        track = []
        for f in range(total):
            if f < birth:
                track.append(0)
            elif f == birth:
                track.append(255)
            else:
                age = f - birth
                track.append(int(round(max(200 * math.exp(-age / 30.0), 165))))
        data[f"ch{e.z}"] = track
    return ch_map, pd.DataFrame(data)


# ---------------------------------------------------------------------------
# 5. VALIDATION AND OUTPUT
# ---------------------------------------------------------------------------
BINDABLE = ({f"{p}_{a}" for p in ("translate", "rotate", "scale") for a in "xyz"}
            | {f"{p}_rate_{a}" for p in ("translate", "rotate", "scale")
               for a in "xyz"}
            | {"color_r", "color_g", "color_b", "color_a", "color_index",
               "palette_id", "texture_id", "ratio", "topo", "geometry",
               "mesh_id", "hide", "show_text", "render_mode", "fog_enabled",
               "fog_start", "fog_end"})


def validate(df: pd.DataFrame) -> list[str]:
    p = []
    if df.id.duplicated().any():
        p.append("duplicate ids")
    known = set(df.id)
    if len(df[(df.parent_id != 0) & (~df.parent_id.isin(known))]):
        p.append("rows with unknown parent_id")
    links = df[df.type == 7]
    if len(links) and (~links.child_id.isin(known)).any():
        p.append("link child_id references a missing node")
    for c in ("color_r", "color_g", "color_b", "color_a"):
        if ((df[c] < 0) | (df[c] > 255)).any():
            p.append(f"{c} out of 0..255")
    vis = df[(df.hide == 0) & (df.type.isin([5, 7]))]
    if (vis[["scale_x", "scale_y", "scale_z"]] < 0.2).any(axis=None):
        p.append("visible glyph with raw scale < 0.2")
    kids = df[df.parent_id.isin(set(df.loc[df.topo == TOPO_SPHERE, "id"]))]
    if len(kids) and kids.translate_y.abs().max() > 90.0:
        p.append("sphere child outside -90..90 latitude")
    return p


def validate_channels(df, ch_map, ch_tracks) -> list[str]:
    p = []
    channels = set(ch_map.channel_id)
    used = set(df.loc[df.ch_input_id != 0, "ch_input_id"])
    if used - channels:
        p.append(f"ch_input_id with no map row: {sorted(used - channels)[:5]}")
    if channels - used:
        p.append(f"map channel with no node: {sorted(channels - used)[:5]}")
    cols = {int(c[2:]) for c in ch_tracks.columns
            if c.startswith("ch") and c[2:].isdigit()}
    if set(ch_map.track_id) - cols:
        p.append("map track_id with no ch<id> column")
    if set(ch_map.attribute) - BINDABLE:
        p.append(f"unbindable attributes: "
                 f"{sorted(set(ch_map.attribute) - BINDABLE)}")
    for t in ch_map.loc[ch_map.attribute == "color_a", "track_id"]:
        col = ch_tracks[f"ch{t}"]
        if ((col < 0) | (col > 255)).any():
            p.append(f"ch{t}: alpha out of 0..255")
            break
    return p


def write_csv(df: pd.DataFrame, path: Path, float_format="%.4f") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\r\n",
              float_format=float_format)
    back = pd.read_csv(path, encoding="utf-8", low_memory=False)
    assert len(back) == len(df), f"round-trip row-count mismatch: {path}"


def emit(name, stem, node_df, ch_map=None, ch_tracks=None) -> bool:
    problems = validate(node_df)
    if ch_map is not None:
        problems += validate_channels(node_df, ch_map, ch_tracks)
    if problems:
        for x in problems:
            print(f"  VALIDATION FAILURE [{name}]: {x}", file=sys.stderr)
        return False
    out = HERE / name
    write_csv(node_df, out / f"{stem}_gv_node.csv")
    msg = f"  {name}: {len(node_df):,} nodes"
    if ch_map is not None:
        write_csv(ch_map, out / f"{stem}_gv_ch-map.csv", float_format=None)
        write_csv(ch_tracks, out / f"{stem}_gv_ch-tracks.csv",
                  float_format=None)
        msg += (f", {len(ch_map):,} bindings, {len(ch_tracks):,} frames x "
                f"{len(ch_tracks.columns)-1:,} tracks")
    print(msg + "  [validation clean]")
    return True


SCENES = ("Madelung_Helix", "Aufbau_Sequence")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--only", choices=SCENES, action="append")
    args = ap.parse_args()

    els = E.load_elements()
    print(f"Loaded {len(els)} elements; "
          f"{sum(e.electrons for e in els):,} electrons total; "
          f"{sum(1 for e in els if e.is_anomalous)} anomalous configurations")

    wanted = args.only or list(SCENES)
    ok = True

    if "Madelung_Helix" in wanted:
        node, info = build(els, animate=False)
        ok &= emit("Madelung_Helix", "PeriodicHelix", node)
        print(f"     {info['electrons']:,} electron glyphs, "
              f"{info['links']} group-column links, {info['turns']} turns, "
              f"{info['anomalous']} anomalies marked")

    if "Aufbau_Sequence" in wanted:
        node, info = build(els, animate=True)
        cmap, ctr = build_channels(els)
        ok &= emit("Aufbau_Sequence", "AufbauSequence", node, cmap, ctr)

    print("\nOpen either scene's node CSV in GlyphViz. In Aufbau_Sequence, "
          "Space builds the system one element at a time.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
