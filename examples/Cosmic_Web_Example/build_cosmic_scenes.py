#!/usr/bin/env python3
"""
build_cosmic_scenes.py — the local universe out of 2MRS, two ways.

The cosmic web is the one structure in astronomy that a flat picture cannot
tell the truth about.  Filaments, sheets and voids are defined by how they
connect in three dimensions; project them onto the sky and the filaments
overlap into a uniform haze, which is exactly why every published "cosmic
web" image is either a thin slice or a simulation.  2MRS gives 43,414 real
galaxies with real distances, all-sky, and that is a thing to fly through
rather than a thing to plot.

  Local_Universe/   Every galaxy in the catalogue, placed in supergalactic
                    Cartesian coordinates at 1 world unit per megaparsec and
                    coloured by how crowded its own neighbourhood is, so the
                    voids go dark and the filaments light up.  Nine named
                    structures are marked, and so is the Milky Way at the
                    origin.  The radial spikes all pointing at that origin
                    are fingers of God, and they are honest: see the README.

  Cluster_Anatomy/  The same sky, restructured.  A volume-limited subsample
                    inside 120 Mpc is run through a friends-of-friends
                    percolation, and every group it finds becomes a
                    hyperglyph — a frame at the group's centre carrying its
                    member galaxies, wrapped in a wire shell at the group's
                    own radius.  Selecting a knot of the web now selects a
                    structure instead of a pixel.  The four richest groups it
                    finds are Perseus, Coma, Norma and Centaurus, which is
                    the check that it works.

Usage:
    python build_cosmic_scenes.py
    python build_cosmic_scenes.py --only Local_Universe

Requires: numpy, pandas, scipy.  No network — reads the vendored catalogue in
data/.  Refresh it with `python fetch_2mrs.py`.
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import skymap                                                      # noqa: E402

# ---------------------------------------------------------------------------
# 1. CONSTANTS
# ---------------------------------------------------------------------------
MPC = 1.0                # world units per megaparsec, both scenes

# --- galaxy glyphs ---------------------------------------------------------
GAL_MIN, GAL_MAX = 0.30, 1.05      # world units; comfortably over the 0.2 floor
ABS_K_BRIGHT, ABS_K_FAINT = -26.5, -21.5

# --- friends of friends ----------------------------------------------------
VL_DEPTH = 120.0         # Mpc; the volume-limited subsample's outer radius
FOF_B = 0.20             # linking length as a fraction of the mean separation
FOF_STRETCH = 3.0        # ...times longer along the line of sight
GROUP_MIN = 5            # members needed to be drawn as a hyperglyph
SHELL_MIN = 8            # ...and to get a wire shell around it
NAME_RADIUS = 10.0       # Mpc; a group this close to a landmark takes its name
TOP_LABELLED = 10        # richest groups whose labels are pinned on
GROUP_TONE_FLOOR = 0.34  # even the smallest group outranks the field visually

# --- landmarks -------------------------------------------------------------
MARK_SCALE = 4.0

BG = (6, 7, 14, 255)
TAG_RGB = (226, 230, 240)
MARK_RGB = (255, 236, 176)
FIELD_RGB = (78, 86, 116)
SHELL_RGB = (150, 190, 225)

GEO_CUBE, GEO_SPHERE_WIRE, GEO_SPHERE = 1, 2, 3
GEO_OCTA_WIRE, GEO_ICOSA_WIRE = 10, 14
GEO_POINT, GEO_CIRCLE, GEO_CROSS, GEO_LINE = 22, 24, 25, 27
TOPO_NONE = 0
ROT_EULER = 0

#: Void to filament to cluster core.  Deliberately not a rainbow: the eye
#: reads brightness as density much more reliably than it reads hue, so the
#: ramp climbs in luminance the whole way and uses hue only to separate the
#: empty end from the crowded one.
DENSITY_RAMP = (
    (0.00, (22, 26, 62)),      # void
    (0.30, (30, 84, 132)),     # wall
    (0.58, (48, 156, 148)),    # filament
    (0.80, (196, 192, 96)),    # group
    (1.00, (255, 240, 196)),   # cluster core
)


def ramp(t: float) -> tuple[int, int, int]:
    t = min(max(t, 0.0), 1.0)
    for (t0, c0), (t1, c1) in zip(DENSITY_RAMP, DENSITY_RAMP[1:]):
        if t <= t1:
            f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(int(round(a + (b - a) * f)) for a, b in zip(c0, c1))
    return DENSITY_RAMP[-1][1]


def galaxy_scale(abs_k: np.ndarray) -> np.ndarray:
    """Absolute K magnitude -> glyph size.

    A glyph is a symbol, not a scale model: real galaxies are ~0.03 Mpc
    across and would be invisible at any zoom that shows the web.  What the
    size does carry is honest ordering — brighter galaxies draw bigger — and
    it doubles as a depth cue, which a point cloud badly needs.
    """
    t = (ABS_K_FAINT - np.asarray(abs_k)) / (ABS_K_FAINT - ABS_K_BRIGHT)
    return np.round(GAL_MIN + (GAL_MAX - GAL_MIN) * np.clip(t, 0.0, 1.0), 3)


# ---------------------------------------------------------------------------
# 2. SCENE BUILDER
# ---------------------------------------------------------------------------
COLUMNS = ["id", "type", "parent_id", "branch_level", "child_id",
           "translate_x", "translate_y", "translate_z",
           "rotate_x", "rotate_y", "rotate_z",
           "scale_x", "scale_y", "scale_z",
           "color_r", "color_g", "color_b", "color_a",
           "geometry", "hide", "topo", "ratio", "show_text",
           "segments_x", "segments_y", "rotation_mode",
           "tag_color_mode", "tag_color_r", "tag_color_g", "tag_color_b",
           "text", "link"]

DEFAULTS = dict(child_id=0, translate_x=0.0, translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=255, color_g=255, color_b=255, color_a=255,
                geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE, ratio=0.1,
                show_text=0, segments_x=16, segments_y=16,
                rotation_mode=ROT_EULER, tag_color_mode=0,
                tag_color_r=TAG_RGB[0], tag_color_g=TAG_RGB[1],
                tag_color_b=TAG_RGB[2], text="", link="")


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

    def write(self, folder: Path, stem: str) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{stem}_gv_node.csv"
        pd.DataFrame(self.rows, columns=COLUMNS).to_csv(
            path, index=False, encoding="utf-8", lineterminator="\r\n")
        return path


def clean(text: str) -> str:
    out = "".join(c for c in str(text) if c.isprintable() and c not in "\r\n")
    return " ".join(out.split()).replace('"', "'")


def add_landmarks(sb: SceneBuilder, parent: int, level: int,
                  max_dist: float = 1e9) -> int:
    """The named structures, plus us.  `max_dist` drops the ones a scene does
    not actually contain, so no marker floats in empty space."""
    sb.add(type=5, parent_id=parent, branch_level=level,
           scale_x=2.0, scale_y=2.0, scale_z=2.0,
           geometry=GEO_CROSS, ratio=0.6,
           color_r=255, color_g=255, color_b=255, color_a=255,
           show_text=1, text="Milky Way (observer)")
    n = 1
    for lm in skymap.LANDMARKS:
        p = skymap.landmark_xyz(lm)
        if float(np.linalg.norm(p)) > max_dist:
            continue
        n += 1
        sb.add(type=5, parent_id=parent, branch_level=level,
               translate_x=round(float(p[0]) * MPC, 3),
               translate_y=round(float(p[1]) * MPC, 3),
               translate_z=round(float(p[2]) * MPC, 3),
               scale_x=MARK_SCALE, scale_y=MARK_SCALE, scale_z=MARK_SCALE,
               geometry=GEO_ICOSA_WIRE,
               color_r=MARK_RGB[0], color_g=MARK_RGB[1], color_b=MARK_RGB[2],
               color_a=210, show_text=1,
               text=f"{lm.name} ({np.linalg.norm(p):.0f} Mpc)")
    return n


# ---------------------------------------------------------------------------
# 3. SCENE ONE — the whole catalogue
# ---------------------------------------------------------------------------
def build_local_universe(cat: skymap.Catalogue, out: Path) -> Path:
    df = cat.df
    xyz = cat.xyz
    dens = skymap.knn_density(xyz, k=6)
    # Most galaxies live in the field, so a linear stretch between extremes
    # leaves the whole catalogue sitting at the dark end of the ramp and the
    # web never lights up.  Clamp to the working percentiles and pull the
    # midtones up; the ordering is untouched, only the contrast.
    lo, hi = np.percentile(dens, [8.0, 99.0])
    t = np.clip((dens - lo) / (hi - lo), 0.0, 1.0) ** 0.70
    scale = galaxy_scale(df.abs_k.to_numpy())

    sb = SceneBuilder()
    sb.world()
    anchor = sb.add(type=5, parent_id=0, branch_level=0, geometry=0, hide=1,
                    topo=TOPO_NONE,
                    text="2MRS - the local universe, supergalactic frame")

    colours = [ramp(float(v)) for v in t]
    ids = df.ID.to_numpy()
    dist = df.dist.to_numpy()
    for i in range(len(df)):
        r, g, b = colours[i]
        s = float(scale[i])
        sb.add(type=5, parent_id=anchor, branch_level=1,
               translate_x=round(float(xyz[i, 0]) * MPC, 3),
               translate_y=round(float(xyz[i, 1]) * MPC, 3),
               translate_z=round(float(xyz[i, 2]) * MPC, 3),
               scale_x=s, scale_y=s, scale_z=s,
               geometry=GEO_SPHERE, color_r=r, color_g=g, color_b=b,
               color_a=255,
               text=f"2MASX J{clean(ids[i])}  {dist[i]:.0f} Mpc")

    n_marks = add_landmarks(sb, anchor, 1)
    path = sb.write(out, "LocalUniverse")
    print(f"  Local_Universe    {len(sb.rows):,} nodes  "
          f"({len(df):,} galaxies to {df.dist.max():.0f} Mpc, "
          f"{n_marks} markers)")
    return path


# ---------------------------------------------------------------------------
# 4. SCENE TWO — groups as hyperglyphs
# ---------------------------------------------------------------------------
@dataclass
class Group:
    gid: int
    members: np.ndarray       # row indices into the volume-limited frame
    centre: np.ndarray        # supergalactic Mpc
    radius: float             # rms distance of members from the centre
    name: str


def find_groups(vl: pd.DataFrame) -> tuple[np.ndarray, list[Group], float]:
    xyz = vl[["sgx", "sgy", "sgz"]].to_numpy()
    volume = (4.0 / 3.0) * math.pi * VL_DEPTH ** 3
    mean_sep = (len(xyz) / volume) ** (-1.0 / 3.0)
    b_perp = FOF_B * mean_sep
    gid = skymap.friends_of_friends(xyz, b_perp, FOF_STRETCH * b_perp)

    groups: list[Group] = []
    for g in range(gid.max() + 1 if gid.max() >= 0 else 0):
        idx = np.where(gid == g)[0]
        if len(idx) < GROUP_MIN:
            continue
        pts = xyz[idx]
        centre = pts.mean(axis=0)
        radius = float(np.sqrt(((pts - centre) ** 2).sum(axis=1).mean()))
        groups.append(Group(g, idx, centre, radius, ""))
    groups.sort(key=lambda gr: -len(gr.members))

    # A landmark names exactly one group: the richest within NAME_RADIUS.
    # Percolation happily splits an extended cluster into a dominant clump
    # and a few outliers, and labelling all of them "Coma Cluster" would be
    # three lies for every truth.
    for lm in skymap.LANDMARKS:
        p = skymap.landmark_xyz(lm)
        near = [gr for gr in groups
                if not gr.name and np.linalg.norm(gr.centre - p) <= NAME_RADIUS]
        if near:
            near[0].name = lm.name          # groups are already richest-first
    return gid, groups, mean_sep


def build_cluster_anatomy(cat: skymap.Catalogue, out: Path) -> Path:
    vl = cat.volume_limited(VL_DEPTH).reset_index(drop=True)
    gid, groups, mean_sep = find_groups(vl)
    xyz = vl[["sgx", "sgy", "sgz"]].to_numpy()
    scale = galaxy_scale(vl.abs_k.to_numpy())
    in_group = np.zeros(len(vl), dtype=bool)
    for gr in groups:
        in_group[gr.members] = True

    sb = SceneBuilder()
    sb.world()
    anchor = sb.add(type=5, parent_id=0, branch_level=0, geometry=0, hide=1,
                    topo=TOPO_NONE,
                    text=f"2MRS groups inside {VL_DEPTH:.0f} Mpc")

    # --- the field: everything percolation left on its own -----------------
    field_anchor = sb.add(type=5, parent_id=anchor, branch_level=1,
                          geometry=0, hide=1, topo=TOPO_NONE,
                          text="field galaxies (in no group)")
    ids = vl.ID.to_numpy()
    n_field = 0
    for i in np.where(~in_group)[0]:
        s = float(scale[i]) * 0.7
        sb.add(type=5, parent_id=field_anchor, branch_level=2,
               translate_x=round(float(xyz[i, 0]) * MPC, 3),
               translate_y=round(float(xyz[i, 1]) * MPC, 3),
               translate_z=round(float(xyz[i, 2]) * MPC, 3),
               scale_x=s, scale_y=s, scale_z=s, geometry=GEO_SPHERE,
               color_r=FIELD_RGB[0], color_g=FIELD_RGB[1],
               color_b=FIELD_RGB[2], color_a=255,
               text=f"2MASX J{clean(ids[i])}")
        n_field += 1

    # --- one hyperglyph per group ------------------------------------------
    richest = max(len(gr.members) for gr in groups)
    for rank, gr in enumerate(groups):
        n = len(gr.members)
        # Richness drives colour along the same ramp the other scene uses for
        # density, so the two scenes read consistently.
        t = math.log(n / GROUP_MIN + 1.0) / math.log(richest / GROUP_MIN + 1.0)
        rgb = ramp(GROUP_TONE_FLOOR + (1.0 - GROUP_TONE_FLOOR) * t)

        hub = sb.add(type=5, parent_id=anchor, branch_level=1,
                     translate_x=round(float(gr.centre[0]) * MPC, 3),
                     translate_y=round(float(gr.centre[1]) * MPC, 3),
                     translate_z=round(float(gr.centre[2]) * MPC, 3),
                     geometry=0, hide=1, topo=TOPO_NONE)

        label = gr.name or f"group of {n}"
        pin = 1 if rank < TOP_LABELLED else 0
        if n >= SHELL_MIN:
            sh = max(gr.radius * MPC, 1.0)
            sb.add(type=5, parent_id=hub, branch_level=2,
                   scale_x=sh, scale_y=sh, scale_z=sh,
                   geometry=GEO_SPHERE_WIRE,
                   color_r=SHELL_RGB[0], color_g=SHELL_RGB[1],
                   color_b=SHELL_RGB[2], color_a=70,
                   show_text=pin,
                   text=f"{label}: {n} galaxies, {gr.radius:.1f} Mpc across")

        for i in gr.members:
            s = float(scale[i])
            d = (xyz[i] - gr.centre) * MPC
            sb.add(type=5, parent_id=hub, branch_level=2,
                   translate_x=round(float(d[0]), 3),
                   translate_y=round(float(d[1]), 3),
                   translate_z=round(float(d[2]), 3),
                   scale_x=s, scale_y=s, scale_z=s, geometry=GEO_SPHERE,
                   color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                   color_a=255,
                   text=f"2MASX J{clean(ids[i])}  {label}")

    # No landmark markers here: every in-volume landmark has already named
    # a group, and drawing both put two labels on every cluster.
    add_landmarks(sb, anchor, 1, max_dist=0.0)
    path = sb.write(out, "ClusterAnatomy")
    named = sum(1 for gr in groups if gr.name)
    print(f"  Cluster_Anatomy   {len(sb.rows):,} nodes  "
          f"({len(vl):,} volume-limited galaxies, {len(groups):,} groups "
          f"of {GROUP_MIN}+, {named} named, {n_field:,} field; "
          f"mean separation {mean_sep:.2f} Mpc)")
    return path


# ---------------------------------------------------------------------------
# 5. MAIN
# ---------------------------------------------------------------------------
SCENES = {"Local_Universe": build_local_universe,
          "Cluster_Anatomy": build_cluster_anatomy}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=sorted(SCENES))
    ap.add_argument("--out", type=Path, default=HERE)
    args = ap.parse_args()

    cat = skymap.load()
    print(f"loaded {len(cat):,} galaxies with usable distances")
    for name, fn in SCENES.items():
        if args.only and name != args.only:
            continue
        fn(cat, args.out / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
