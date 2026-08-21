#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
glyphviz_topology_anim.py
=========================

Generates GlyphViz Channels animations that *teach* how a parent's topology
places and orients its children.

Every scene follows the same grammar so that scenes are comparable to each
other -- a viewer who has watched the Grid animation can read the Sphere
animation without being re-taught the visual language:

    * one PARENT glyph at the origin, carrying the topology under test
    * one PROBE child (a cone, so its *orientation* is legible) whose
      translate_x / translate_y / translate_z are driven by three channel
      tracks
    * three phases of equal length -- axis 1 sweeps, then axis 2, then
      axis 3 -- each returning home before the next begins
    * a shared reach constant (REACH = 10) so scenes share a ruler

The interesting part is what *differs*: the same three numbers mean
Cartesian units under Grid, degrees of longitude / degrees of latitude /
altitude-above-surface under Sphere, orbital angle / tube angle / tube
offset under Torus, and so on. The probe is a cone rather than a sphere
because half of the lesson is orientation: under Sphere/Point/Torus the
engine pre-rotates children so +Z tracks the outward surface normal, and a
cone makes that visible. Under Grid the cone never tips. Same data, same
sweep, different world.

Output layout (one folder per scene -- REQUIRED, because GlyphViz only
auto-loads Channels when exactly one *ch-map* and one *ch-tracks* file are
present in the node CSV's folder):

    <out>/topo03_torus_probe/torus_probe_gv_node.csv
                             /torus_probe_gv_ch-map.csv
                             /torus_probe_gv_ch-tracks.csv

A probe folder is named for the topology it teaches (topo01_cube_probe ..
topo08_grid_probe); the concept scenes -- the ones teaching channel mechanics
rather than a topology -- keep their own 03..06 numbering. See TopoSpec.folder
for why the Cartesian probe is filed under 8 rather than 0.

Usage
-----
    python glyphviz_topology_anim.py                    # the whole series
    python glyphviz_topology_anim.py --probe-topo 3     # torus probe only
    python glyphviz_topology_anim.py --no-probes        # concept scenes only
    python glyphviz_topology_anim.py --scenes triad comb
    python glyphviz_topology_anim.py --screen           # add a video-screen
                                                        # plate to each scene
    python glyphviz_topology_anim.py --frames-per-axis 210

Author: written for Jeff's GlyphViz topology instructional series.
"""

from __future__ import annotations

import argparse
import colorsys
import csv
import math
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Sequence, Tuple

# --------------------------------------------------------------------------
# Scene constants
# --------------------------------------------------------------------------

REACH = 10.0          # the shared ruler: every scene's linear axes reach this far
B = 1.0               # GlyphViz Global Scale (app default 1.0) -- the parent's
                      # unscaled base size, as it appears in the topology math

# ANTz convention, kept deliberately: SOLID geometry for the base topologies,
# WIREFRAME for their z-variants. That contrast is the whole visual tell when
# the series reaches Zsphere/Ztorus/Zcylinder, so nothing else in these scenes
# is allowed to spend it. Parents are translucent so the probe stays readable
# as it passes behind (and through) them.
PARENT_ALPHA = 150
Z_TOPOS = {9, 10, 11, 12, 13}

# The probe is a marker riding the parent, not a rival to it. At B = 1 a
# parent glyph is one unit across; the probe is roughly a quarter of that.
# Note the 0.2-per-axis render floor: to go smaller than this, scale the
# PARENT up rather than the probe down, or the renderer quietly ignores you.
PROBE_SCALE = (0.28, 0.28, 0.48)
GHOST_SCALE = (0.22, 0.22, 0.22)

# Half the probe's own length along its +Z. Surface-riding topologies seat the
# probe this far off the surface so it *rides* the surface instead of being
# buried to the waist in it -- a sphere parent should read as a planet with
# something travelling over it.
STANDOFF = 0.25

# Palette (GlyphViz brand family: indigo / teal / coral, on deep indigo)
BG        = (14, 14, 26, 255)
INDIGO    = (63, 81, 181, 255)
INDIGO_D  = (63, 81, 181, 70)      # translucent scaffolding
RULER     = (63, 81, 181, 45)      # the reach wireframe: dimmer still
TEAL      = (38, 198, 181, 255)
CORAL     = (255, 111, 97, 255)
VIOLET    = (167, 139, 250, 255)
AMBER     = (255, 193, 7, 255)
CHALK     = (236, 240, 255, 235)
GHOST     = (236, 240, 255, 255)

AXIS_COLORS = (CORAL, TEAL, VIOLET)   # axis 1, 2, 3 -- consistent across scenes

# Geometry ids (see references/node-csv-format.md)
G_CUBE_WIRE, G_CUBE = 0, 1
G_SPHERE_WIRE, G_SPHERE = 2, 3
G_CONE_WIRE, G_CONE = 4, 5
G_TORUS_WIRE, G_TORUS = 6, 7
G_OCTA_WIRE, G_OCTA = 10, 11
G_PIN, G_PIN_WIRE = 16, 17   # note: solid comes FIRST in the geometry table
G_ICOSA = 15
G_CYL_WIRE, G_CYL = 18, 19
G_GRID_WIRE, G_GRID = 20, 21
G_POINT = 22
G_CIRCLE, G_CROSS, G_STAR = 24, 25, 26

# Topology ids
T_NONE, T_CUBE, T_SPHERE, T_TORUS = 0, 1, 2, 3
T_CYLINDER, T_PIN, T_ROD, T_POINT = 4, 5, 6, 7
T_PLANE = 8
T_ZCUBE, T_ZSPHERE, T_ZTORUS, T_ZCYL, T_ZROD = 9, 10, 11, 12, 13
T_SPIRAL, T_VIDEO, T_PLOT, T_SURFACE = 14, 15, 16, 17

# The authoring dialect: 20 required columns + the four optional ones we use.
NODE_COLS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo",
    "ratio", "facet", "texture_id", "ch_input_id", "text",
]

MIN_SCALE = 0.2       # renderer floors rendered scale per axis; never author below


# --------------------------------------------------------------------------
# Topology placement math
#
# Mirrors glyphviz_core/topology.py (see references/topologies.md). Used here
# for two purposes: (a) documenting each topology's coordinate meanings in one
# place, and (b) computing *world* positions for the chalk-line scene, where a
# Plot-topology overlay has to retrace a Sphere-topology path in Cartesian
# space.
# --------------------------------------------------------------------------

def _kml(lon_deg: float, lat_deg: float, radius: float) -> Tuple[float, float, float]:
    lon, lat = math.radians(lon_deg), math.radians(lat_deg)
    return (radius * math.cos(lat) * math.cos(lon),
            radius * math.cos(lat) * math.sin(lon),
            radius * math.sin(lat))


def off_cartesian(tx, ty, tz, ratio=0.1, facet=0):
    """None (0), Plane (8), Video (15), Plot (16), Surface (17)."""
    return (tx, ty, tz)


def off_sphere(tx, ty, tz, ratio=0.1, facet=0):
    """Sphere (2): lon / lat / altitude above the surface."""
    return _kml(tx, ty, B + tz)


def off_point(tx, ty, tz, ratio=0.1, facet=0):
    """Point (7) and Zsphere (10): lon / lat / distance from the centre."""
    return _kml(tx, ty, tz)


def off_torus(tx, ty, tz, ratio=0.1, facet=0):
    """Torus (3): orbital angle / tube angle / offset from the tube surface."""
    major, minor = B * (1.0 - ratio), B * ratio
    tube = minor + tz
    a, b_ = math.radians(tx), math.radians(ty)
    rr = major + tube * math.cos(b_)
    return (rr * math.cos(a), rr * math.sin(a), tube * math.sin(b_))


def off_ztorus(tx, ty, tz, ratio=0.1, facet=0):
    """Ztorus (11): no tube -- tz offsets from the major ring itself."""
    major = B * (1.0 - ratio)
    a, b_ = math.radians(tx), math.radians(ty)
    rr = major + tz * math.cos(b_)
    return (rr * math.cos(a), rr * math.sin(a), tz * math.sin(b_))


def off_cylinder(tx, ty, tz, ratio=0.1, facet=0):
    """Cylinder (4): angle / height along the axis / radial offset from surface."""
    a = math.radians(tx)
    r = B + tz
    return (r * math.cos(a), r * math.sin(a), ty)


def off_zcylinder(tx, ty, tz, ratio=0.1, facet=0):
    """Zcylinder (12) and Zrod (13): radius is tz alone (0 = on the axis)."""
    a = math.radians(tx)
    return (tz * math.cos(a), tz * math.sin(a), ty)


def off_pin(tx, ty, tz, ratio=0.1, facet=0):
    """Pin (5): height above the pin top / sideways X / sideways Y."""
    return (ty, tz, B + tx)


def off_rod(tx, ty, tz, ratio=0.1, facet=0):
    """Rod (6): normalized 0-180 along the rod / angle / radial from the axis."""
    a = math.radians(ty)
    return (tz * math.cos(a), tz * math.sin(a), (tx / 180.0) * 10.0 * B)


def off_spiral(tx, ty, tz, ratio=0.1, facet=0):
    """Spiral (14): helix angle (keeps counting past 360) / extra height / radial."""
    a = math.radians(tx)
    r = B + tz
    return (r * math.cos(a), r * math.sin(a), (tx / 360.0) * B + ty)


_CUBE_FACES = {           # facet -> (normal, u, v)
    1: ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    2: ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
    3: ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
    4: ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    5: ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    6: ((0, 0, -1), (1, 0, 0), (0, -1, 0)),
}


def off_cube(tx, ty, tz, ratio=0.1, facet=1):
    """Cube (1): slide within a face (tx along u, ty along v), tz lifts off it."""
    n, u, v = _CUBE_FACES.get(int(facet) or 1, _CUBE_FACES[1])
    d = B + tz
    return tuple(d * n[i] + tx * u[i] + ty * v[i] for i in range(3))


def off_zcube(tx, ty, tz, ratio=0.1, facet=1):
    """Zcube (9): distance along the face normal is tz alone."""
    n, u, v = _CUBE_FACES.get(int(facet) or 1, _CUBE_FACES[1])
    return tuple(tz * n[i] + tx * u[i] + ty * v[i] for i in range(3))


# --------------------------------------------------------------------------
# Per-topology sweep specification
# --------------------------------------------------------------------------

@dataclass
class Axis:
    """One sweepable axis of a topology's child-coordinate system."""
    field: str          # "translate_x" | "translate_y" | "translate_z"
    name: str           # human label, e.g. "longitude"
    lo: float
    hi: float
    home: float = 0.0
    cyclic: bool = False   # angular axes sweep home -> home+360 monotonically
    unit: str = ""


@dataclass
class TopoSpec:
    topo: int
    key: str            # folder-safe key
    title: str
    offset: Callable
    axes: Tuple[Axis, Axis, Axis]
    geom_solid: int = G_SPHERE      # used for the base topologies
    geom_wire: int = G_SPHERE_WIRE  # reserved for the z-variants
    ratio: float = 0.1
    facet: int = 0
    note: str = ""
    series_no: int = -1  # folder number; -1 means "use the topology id"

    @property
    def parent_geometry(self) -> int:
        """ANTz convention: solid for base topologies, wireframe for z-variants."""
        return self.geom_wire if self.topo in Z_TOPOS else self.geom_solid

    @property
    def folder(self) -> str:
        """The scene folder name, e.g. 'topo03_torus_probe'.

        Numbered by topology id, with one deliberate exception: the Cartesian
        probe is filed under Plane (8) rather than None (0). It teaches five
        topologies at once -- None, Plane, Video, Plot and Surface all share
        _cartesian_offset -- and filing it at 8 keeps the series reading 01..08
        as the first eight topologies rather than opening on a zero.
        """
        n = self.topo if self.series_no < 0 else self.series_no
        return f"topo{n:02d}_{self.key}_probe"


# The first eight topologies (ids 0-7), pre-specified so that any of them can
# be emitted with --probe-topo N. Grid and Sphere are the two built by default.
TOPOS: Dict[int, TopoSpec] = {
    T_NONE: TopoSpec(
        topo=T_NONE, key="grid", title="Grid / None -- plain Cartesian",
        offset=off_cartesian, geom_solid=G_GRID, geom_wire=G_GRID_WIRE,
        series_no=8,
        axes=(Axis("translate_x", "x", -REACH, REACH, 0.0, False, "units"),
              Axis("translate_y", "y", -REACH, REACH, 0.0, False, "units"),
              Axis("translate_z", "z", -REACH, REACH, 0.0, False, "units")),
        note="Identity orientation, and no surface to ride -- the origin is a "
             "real place here, so the probe sits at (0,0,0) with no standoff. "
             "Plane (8), Video (15), Plot (16) and Surface (17) share this "
             "exact placement math: one animation teaches five topologies.",
    ),
    T_CUBE: TopoSpec(
        topo=T_CUBE, key="cube", title="Cube -- six faces",
        offset=off_cube, geom_solid=G_CUBE, geom_wire=G_CUBE_WIRE, facet=1,
        axes=(Axis("translate_x", "u (along the face)", -REACH / 2, REACH / 2),
              Axis("translate_y", "v (along the face)", -REACH / 2, REACH / 2),
              Axis("translate_z", "lift off the face", STANDOFF, REACH, STANDOFF)),
        note="The child's face is chosen by its own facet column (1-6), not by "
             "a coordinate. Orientation is fixed per face: +Z is the face normal.",
    ),
    T_SPHERE: TopoSpec(
        topo=T_SPHERE, key="sphere", title="Sphere -- lon / lat / altitude",
        offset=off_sphere, geom_solid=G_SPHERE, geom_wire=G_SPHERE_WIRE,
        axes=(Axis("translate_x", "longitude", -180, 180, 0.0, True, "deg"),
              Axis("translate_y", "latitude", -90, 90, 0.0, False, "deg"),
              Axis("translate_z", "altitude", STANDOFF, REACH, STANDOFF, False, "radii")),
        note="Orientation: the engine pre-rotates each child by Rz(lon)*Ry(90-lat) "
             "so +Z stays on the outward surface normal. Altitude 0 puts the "
             "child's ORIGIN on the surface, which buries a glyph to its waist, "
             "so the probe rests at altitude = STANDOFF and travels over the "
             "surface like a satellite. Altitude -1 lands exactly at the "
             "parent's centre; below -1 the child emerges antipodal.",
    ),
    T_TORUS: TopoSpec(
        topo=T_TORUS, key="torus", title="Torus -- orbital / tube / offset",
        offset=off_torus, geom_solid=G_TORUS, geom_wire=G_TORUS_WIRE, ratio=0.25,
        axes=(Axis("translate_x", "orbital angle", 0, 360, 0.0, True, "deg"),
              Axis("translate_y", "tube angle", 0, 360, 0.0, True, "deg"),
              Axis("translate_z", "offset from tube", STANDOFF, REACH / 3, STANDOFF)),
        note="Reads the PARENT's ratio for the tube radius -- set it on the parent.",
    ),
    T_CYLINDER: TopoSpec(
        topo=T_CYLINDER, key="cylinder", title="Cylinder -- angle / height / radial",
        offset=off_cylinder, geom_solid=G_CYL, geom_wire=G_CYL_WIRE,
        axes=(Axis("translate_x", "angle", 0, 360, 0.0, True, "deg"),
              Axis("translate_y", "height", -REACH, REACH, 0.0),
              Axis("translate_z", "radial from surface", STANDOFF, REACH, STANDOFF)),
        note="Height is a literal offset; radial is measured from the surface "
             "(radius B), unlike Zcylinder which measures from the axis.",
    ),
    T_PIN: TopoSpec(
        topo=T_PIN, key="pin", title="Pin -- stack height / sideways",
        offset=off_pin, geom_solid=G_PIN, geom_wire=G_PIN_WIRE,
        axes=(Axis("translate_x", "height above the pin top", STANDOFF, REACH, STANDOFF),
              Axis("translate_y", "sideways (local X)", -REACH, REACH),
              Axis("translate_z", "sideways (local Y)", -REACH, REACH)),
        note="Note the reshuffle: translate_x is the vertical axis here.",
    ),
    T_ROD: TopoSpec(
        topo=T_ROD, key="rod", title="Rod -- normalized length / angle / radial",
        offset=off_rod, geom_solid=G_CYL, geom_wire=G_CYL_WIRE,
        axes=(Axis("translate_x", "along the rod (0-180 spans it)", 0, 180, 0.0),
              Axis("translate_y", "angle about the axis", 0, 360, 0.0, True, "deg"),
              Axis("translate_z", "radial from the axis", STANDOFF, REACH / 3, STANDOFF)),
        note="translate_x is normalized: 0-180 spans the rod's full rendered "
             "length (10*B at scale 1). The only topology with a normalized axis.",
    ),
    T_POINT: TopoSpec(
        topo=T_POINT, key="point", title="Point -- pure direction",
        offset=off_point, geom_solid=G_OCTA, geom_wire=G_OCTA_WIRE,
        axes=(Axis("translate_x", "longitude", -180, 180, 0.0, True, "deg"),
              Axis("translate_y", "latitude", -90, 90, 0.0, False, "deg"),
              Axis("translate_z", "distance from centre", B + STANDOFF, REACH, B + STANDOFF)),
        note="Sphere without the base radius: tz is the whole distance, so tz=0 "
             "collapses the child into the parent's centre. The probe therefore "
             "rests at B + STANDOFF to sit just clear of a unit hub. Spokes.",
    ),
}


# --------------------------------------------------------------------------
# Sweep scheduling
# --------------------------------------------------------------------------

def smoothstep(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def _eased_keys(keys: Sequence[Tuple[float, float]], n: int) -> List[float]:
    """Sample a keyframed curve at n frames, easing between keys."""
    out: List[float] = []
    for i in range(n):
        u = i / max(1, n - 1)
        for k in range(len(keys) - 1):
            u0, v0 = keys[k]
            u1, v1 = keys[k + 1]
            if u <= u1 or k == len(keys) - 2:
                span = max(1e-9, u1 - u0)
                local = smoothstep((u - u0) / span)
                out.append(v0 + (v1 - v0) * local)
                break
    return out


def axis_phase(axis: Axis, n: int) -> List[float]:
    """Values for `axis` during its own phase (the other two sit at home)."""
    if axis.cyclic:
        # A full monotonic turn at constant speed reads better than a
        # there-and-back on an angular axis: the child comes home by wrapping.
        span = 360.0
        return [axis.home + span * (i / max(1, n - 1)) for i in range(n)]
    if abs(axis.home - axis.lo) < 1e-9:
        # One-sided axis (altitude, height above a pin): out and back.
        keys = [(0.00, axis.home), (0.08, axis.home),
                (0.55, axis.hi), (0.94, axis.home), (1.00, axis.home)]
    else:
        keys = [(0.00, axis.home), (0.08, axis.home), (0.36, axis.hi),
                (0.76, axis.lo), (1.00, axis.home)]
    return _eased_keys(keys, n)


def probe_tracks(spec: TopoSpec, frames_per_axis: int) -> Tuple[List[float], List[float], List[float]]:
    """Three tracks: one per translate axis, three sequential phases."""
    homes = [a.home for a in spec.axes]
    tx: List[float] = []
    ty: List[float] = []
    tz: List[float] = []
    lanes = (tx, ty, tz)
    for active, axis in enumerate(spec.axes):
        vals = axis_phase(axis, frames_per_axis)
        for i in range(frames_per_axis):
            for lane_i, lane in enumerate(lanes):
                lane.append(vals[i] if lane_i == active else homes[lane_i])
    return tx, ty, tz


# --------------------------------------------------------------------------
# Node / file plumbing
# --------------------------------------------------------------------------

_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def clean_text(s: str) -> str:
    """Strip control characters -- one bad byte can silently kill all labels."""
    s = unicodedata.normalize("NFC", str(s))
    return _CTRL.sub("", s)


class Scene:
    """Accumulates nodes, channel-map rows and track columns for one folder."""

    def __init__(self, key: str, title: str, background=BG):
        self.key = key
        self.title = title
        self.nodes: List[dict] = []
        self.chmap: List[Tuple[int, int, str]] = []
        self.tracks: Dict[int, List[float]] = {}
        self._next_id = 1
        self.world(background)

    # -- nodes ------------------------------------------------------------
    def add(self, *, parent=0, t=(0.0, 0.0, 0.0), r=(0.0, 0.0, 0.0),
            s=(1.0, 1.0, 1.0), color=CHALK, geometry=G_SPHERE, topo=T_NONE,
            ratio=0.1, facet=0, texture_id=0, ch=0, text="", type_=5,
            hide=0) -> int:
        nid = self._next_id
        self._next_id += 1
        self.nodes.append(dict(
            id=nid, type=type_, parent_id=parent, branch_level=0,
            translate_x=float(t[0]), translate_y=float(t[1]), translate_z=float(t[2]),
            rotate_x=float(r[0]), rotate_y=float(r[1]), rotate_z=float(r[2]),
            scale_x=float(s[0]), scale_y=float(s[1]), scale_z=float(s[2]),
            color_r=int(color[0]), color_g=int(color[1]),
            color_b=int(color[2]), color_a=int(color[3]),
            geometry=geometry, hide=hide, topo=topo, ratio=float(ratio),
            facet=facet, texture_id=int(texture_id),
            ch_input_id=ch, text=clean_text(text),
        ))
        return nid

    def world(self, color) -> int:
        """One optional type=0 row carries the scene background. Never drawn."""
        return self.add(type_=0, color=color, geometry=G_POINT, hide=1,
                        text="world")

    # -- channels ---------------------------------------------------------
    def track(self, track_id: int, values: Sequence[float]) -> int:
        self.tracks[track_id] = list(values)
        return track_id

    def bind(self, channel_id: int, track_id: int, attribute: str) -> None:
        self.chmap.append((channel_id, track_id, attribute))

    # -- finalize ---------------------------------------------------------
    def _resolve_levels(self) -> None:
        by_id = {n["id"]: n for n in self.nodes}
        def level(n):
            p = n["parent_id"]
            depth = 0
            while p:
                depth += 1
                n = by_id[p]
                p = n["parent_id"]
            return depth
        for n in self.nodes:
            n["branch_level"] = level(n)

    def write(self, out_dir: str) -> Dict[str, str]:
        self._resolve_levels()
        os.makedirs(out_dir, exist_ok=True)
        stem = self.key
        paths = {}

        # A file WITHOUT a rotation_mode column loads in ANTz Heading/Tilt/Roll
        # (Z-X-Z) mode. So: omit the column while every rotation is zero (the
        # two conventions agree there, and the file stays minimal), and write
        # an explicit 0 -- Euler XYZ, each field spinning its own axis -- the
        # moment any node is hand-posed.
        needs_rot_mode = any(n["rotate_x"] or n["rotate_y"] or n["rotate_z"]
                             for n in self.nodes)
        cols = list(NODE_COLS) + (["rotation_mode"] if needs_rot_mode else [])

        node_path = os.path.join(out_dir, f"{stem}_gv_node.csv")
        with open(node_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\r\n")
            w.writeheader()
            for n in self.nodes:
                row = {k: _fmt(n[k]) for k in NODE_COLS}
                if needs_rot_mode:
                    row["rotation_mode"] = 0
                w.writerow(row)
        paths["node"] = node_path

        if self.chmap:
            map_path = os.path.join(out_dir, f"{stem}_gv_ch-map.csv")
            with open(map_path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh, lineterminator="\r\n")
                w.writerow(["channel_id", "track_id", "attribute"])
                for row in self.chmap:
                    w.writerow(row)
            paths["map"] = map_path

            n_frames = max(len(v) for v in self.tracks.values())
            ids = sorted(self.tracks)
            trk_path = os.path.join(out_dir, f"{stem}_gv_ch-tracks.csv")
            with open(trk_path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh, lineterminator="\r\n")
                w.writerow(["cyclecount"] + [f"ch{i}" for i in ids])
                for f in range(n_frames):
                    row = [f]
                    for i in ids:
                        col = self.tracks[i]
                        row.append(_fmt(col[f] if f < len(col) else col[-1]))
                    w.writerow(row)
            paths["tracks"] = trk_path
        return paths


def _fmt(v):
    if isinstance(v, float):
        if abs(v - round(v)) < 1e-9:
            return f"{v:.6f}"
        return f"{v:.6f}"
    return v


# --------------------------------------------------------------------------
# Shared scene furniture
# --------------------------------------------------------------------------

def add_bounds(scene: Scene, kind="cube", reach=REACH, color=RULER) -> None:
    """A faint wireframe at the reach radius: the shared ruler, as a root node.

    This is the one wireframe in a base scene, and it is deliberately dim and
    ten times the parent's size so it never gets mistaken for the solid-vs-wire
    distinction that marks a z-variant.
    """
    geom = {"cube": G_CUBE_WIRE, "sphere": G_SPHERE_WIRE}[kind]
    scene.add(parent=0, t=(0, 0, 0), s=(reach, reach, reach),
              color=color, geometry=geom, topo=T_NONE)


def add_axis_ticks(scene: Scene, spec: TopoSpec, reach=REACH) -> None:
    """Small star markers, in world space, labelling each axis extreme."""
    for i, axis in enumerate(spec.axes):
        col = AXIS_COLORS[i]
        # A cyclic axis has no extremes -- lo and hi are the same place. Mark
        # the quarter turns instead, which is what actually reads as a ruler.
        marks = ([axis.home + 90.0 * q for q in range(4)] if axis.cyclic
                 else [axis.hi, axis.lo])
        for value in marks:
            coords = [a.home for a in spec.axes]
            coords[i] = value
            wx, wy, wz = spec.offset(*coords, ratio=spec.ratio, facet=spec.facet or 1)
            label = f"{axis.name} = {value:g}{(' ' + axis.unit) if axis.unit else ''}"
            scene.add(parent=0, t=(wx, wy, wz), s=(0.45, 0.45, 0.45),
                      color=(col[0], col[1], col[2], 200), geometry=G_STAR,
                      topo=T_NONE, text=label)


def add_screen(scene: Scene, distance=REACH * 1.9, width=REACH * 1.1) -> int:
    """An upright plate wired for a video texture -- lesson video goes in media/.

    rotate_x = 90 stands the plate vertically, facing back down -Y at the
    scene. That single non-zero rotation is what triggers the rotation_mode
    column on save (see Scene.write): the plate is posed in Euler XYZ, so the
    file has to say so or ANTz's Heading/Tilt/Roll fallback will misread it.

    texture_id is a 1-based index into the scene's media/ folder, sorted images
    first then videos; topo 15 (Video) marks the plate as a screen. 16:9 at
    `width` across, lifted clear of the ground plane.
    """
    return scene.add(parent=0, t=(0.0, distance, width * 0.42),
                     r=(90.0, 0.0, 0.0),
                     s=(width, width * 0.5625, 1.0),
                     color=(255, 255, 255, 255), geometry=G_GRID,
                     topo=T_VIDEO, texture_id=1, text="lesson video")


# --------------------------------------------------------------------------
# Scenes
# --------------------------------------------------------------------------

def add_scribe(sc: Scene, parent: int, spec: TopoSpec,
               tx: List[float], ty: List[float], tz: List[float],
               next_track: int, ghosts=8, chalk_points=120) -> int:
    """Give any topology the scribe treatment: a comet, and a self-drawing path.

    Two independent effects, both topology-agnostic because both are derived
    from the same three probe tracks:

    * **Comet** -- `ghosts` glyphs parented to the same node, reading the same
      three tracks delayed a few frames each and fading out behind the probe.
      They live in the parent's topology coordinates, so the tail bends
      through the topology exactly as the probe does. No extra math.

    * **Chalk line** -- a transparent Plot-topology parent holding beads at the
      probe's *Cartesian world* positions, computed here with the topology's
      own offset function. Each bead's alpha is a step function that flips on
      as the probe arrives and stays on, so the curve draws itself. Plot draws
      its polyline through children in row order, which is why the beads are
      emitted in path order.

    That second effect is the one worth the trouble: the probe moves in the
    topology's coordinates while the line accumulates in world space, so the
    mapping between the two is on screen simultaneously rather than narrated.

    Returns the next free track id.
    """
    n = len(tx)
    homes = tuple(a.home for a in spec.axes)
    ch_id = 2   # channel 1 is the probe

    for k in range(1, ghosts + 1):
        delay = k * 3
        alpha = int(200 * (1.0 - k / (ghosts + 1.0)) ** 1.6) + 12
        sc.add(parent=parent, t=homes, s=GHOST_SCALE,
               color=(GHOST[0], GHOST[1], GHOST[2], alpha),
               geometry=G_ICOSA, topo=T_NONE, facet=spec.facet, ch=ch_id)
        for lane, attr in ((tx, "translate_x"), (ty, "translate_y"),
                           (tz, "translate_z")):
            sc.track(next_track, [lane[max(0, f - delay)] for f in range(n)])
            sc.bind(ch_id, next_track, attr)
            next_track += 1
        ch_id += 1

    plot_parent = sc.add(parent=0, t=(0, 0, 0), s=(1, 1, 1),
                         color=(255, 255, 255, 0), geometry=G_POINT,
                         topo=T_PLOT, ratio=0.22, text="path (Plot overlay)")

    step = max(1, n // chalk_points)
    for f in range(0, n, step):
        wx, wy, wz = spec.offset(tx[f], ty[f], tz[f],
                                 ratio=spec.ratio, facet=spec.facet or 1)
        sc.add(parent=plot_parent, t=(wx, wy, wz), s=(0.22, 0.22, 0.22),
               color=(CHALK[0], CHALK[1], CHALK[2], 0), geometry=G_POINT,
               ratio=0.09, topo=T_NONE, ch=ch_id)
        sc.track(next_track, [0.0] * f + [235.0] * (n - f))
        sc.bind(ch_id, next_track, "color_a")
        next_track += 1
        ch_id += 1

    return next_track


def scene_probe(spec: TopoSpec, frames_per_axis: int, screen=False,
                scribe=True, ghosts=8, chalk_points=120) -> Scene:
    """THE base grammar: one parent, one probe, three tracks, three phases.

    With `scribe` on (the default) the probe also grows a comet and writes its
    own path -- see add_scribe. The three probe tracks are unchanged either
    way, so the lesson and its embellishment stay separable.
    """
    sc = Scene(spec.key + "_probe", spec.title)

    add_bounds(sc, "sphere" if spec.topo in (T_SPHERE, T_POINT) else "cube")

    parent = sc.add(parent=0, t=(0, 0, 0), s=(1, 1, 1),
                    color=(INDIGO[0], INDIGO[1], INDIGO[2], PARENT_ALPHA),
                    geometry=spec.parent_geometry, topo=spec.topo,
                    ratio=spec.ratio, text=spec.title)

    # A cone, so orientation is legible: its +Z apex reveals the topology's
    # built-in outward rotation (or its absence). Its home coordinates carry
    # the topology's seating standoff, so it rides the surface rather than
    # sinking into it.
    sc.add(parent=parent,
           t=tuple(a.home for a in spec.axes), s=PROBE_SCALE,
           color=CORAL, geometry=G_CONE, topo=T_NONE,
           facet=spec.facet, ch=1, text="probe")

    add_axis_ticks(sc, spec)
    if screen:
        add_screen(sc)

    tx, ty, tz = probe_tracks(spec, frames_per_axis)
    sc.track(1, tx); sc.track(2, ty); sc.track(3, tz)
    sc.bind(1, 1, "translate_x")
    sc.bind(1, 2, "translate_y")
    sc.bind(1, 3, "translate_z")

    if scribe:
        add_scribe(sc, parent, spec, tx, ty, tz, next_track=4,
                   ghosts=ghosts, chalk_points=chalk_points)
    return sc


def scene_axis_triad(frames=210, screen=False) -> Scene:
    """Three probes, three channels -- and exactly ONE track.

    The map is the point of this scene: several channels may read the same
    track, so a single sweep column drives motion along three different axes.
    The three probes' common corner traces the volume diagonal.
    """
    sc = Scene("grid_axis_triad", "Grid -- one track, three axes")
    add_bounds(sc, "cube")
    parent = sc.add(parent=0, s=(1, 1, 1),
                    color=(INDIGO[0], INDIGO[1], INDIGO[2], PARENT_ALPHA),
                    geometry=G_GRID, topo=T_NONE, text="Cartesian parent")

    for i, (axis_name, col) in enumerate(zip("XYZ", AXIS_COLORS)):
        sc.add(parent=parent, t=(0, 0, 0), s=PROBE_SCALE, color=col,
               geometry=G_CONE, topo=T_NONE, ch=i + 1, text=f"probe {axis_name}")

    add_axis_ticks(sc, TOPOS[T_NONE])
    if screen:
        add_screen(sc)

    sweep = _eased_keys([(0.0, 0.0), (0.06, 0.0), (0.34, REACH),
                         (0.74, -REACH), (1.0, 0.0)], frames)
    sc.track(1, sweep)
    sc.bind(1, 1, "translate_x")   # channel 1 -> track 1 -> x
    sc.bind(2, 1, "translate_y")   # channel 2 -> the SAME track -> y
    sc.bind(3, 1, "translate_z")   # channel 3 -> the SAME track -> z
    return sc


def scene_meridian_comb(n_probes=12, frames=260, screen=False) -> Scene:
    """One channel, many nodes: a comb of glyphs sweeping pole to pole.

    Each probe keeps its own longitude from the node CSV; the channel only
    overwrites latitude, altitude and colour. Twelve glyphs, six tracks.
    This is the compression pattern -- animate 1,700 glyphs with 200 channels.
    """
    sc = Scene("sphere_meridian_comb", "Sphere -- one channel, twelve children")
    add_bounds(sc, "sphere", reach=REACH * 0.42)
    parent = sc.add(parent=0, s=(1, 1, 1),
                    color=(INDIGO[0], INDIGO[1], INDIGO[2], PARENT_ALPHA),
                    geometry=G_SPHERE, topo=T_SPHERE, text="Sphere parent")

    for i in range(n_probes):
        lon = i * 360.0 / n_probes
        sc.add(parent=parent, t=(lon, -90.0, STANDOFF), s=PROBE_SCALE,
               color=TEAL, geometry=G_CONE, topo=T_NONE, ch=1,
               text=f"lon {lon:g}")

    if screen:
        add_screen(sc, distance=REACH * 1.2, width=REACH * 0.7)

    lat = _eased_keys([(0.0, -90.0), (0.06, -90.0), (0.50, 90.0),
                       (0.94, -90.0), (1.0, -90.0)], frames)
    alt = [STANDOFF + 0.35 * (1.0 - math.cos(2 * math.pi * 3 * i / frames))
           for i in range(frames)]
    r, g, b = [], [], []
    for i in range(frames):
        hue = (i / frames) % 1.0
        cr, cg, cb = colorsys.hsv_to_rgb(hue, 0.62, 1.0)
        r.append(round(cr * 255)); g.append(round(cg * 255)); b.append(round(cb * 255))

    sc.track(1, lat); sc.track(2, alt)
    sc.track(3, r); sc.track(4, g); sc.track(5, b)
    sc.bind(1, 1, "translate_y")
    sc.bind(1, 2, "translate_z")
    sc.bind(1, 3, "color_r")
    sc.bind(1, 4, "color_g")
    sc.bind(1, 5, "color_b")
    return sc


def scene_rosetta(frames_per_axis=150, screen=False) -> Scene:
    """The lesson in one shot: identical numbers, two topologies, one channel.

    Both probes carry ch_input_id = 1. They receive byte-identical values --
    the Grid sweep, -10..10 on each axis. Under Grid that paints a cross
    through a 20-unit cube. Under Sphere, +-10 degrees of longitude is a
    whisker, +-10 degrees of latitude is another whisker, and +-10 of
    altitude is ten radii -- so the third phase fires the probe straight out,
    through the parent's centre at alt = -1, and out the antipodal side.
    Angles wrap; distances do not.
    """
    sep = REACH * 1.55
    sc = Scene("rosetta_grid_vs_sphere", "Same numbers, two topologies")

    # Grid station
    sc.add(parent=0, t=(-sep, 0, 0), s=(REACH, REACH, REACH),
           color=RULER, geometry=G_CUBE_WIRE, topo=T_NONE)
    gparent = sc.add(parent=0, t=(-sep, 0, 0), s=(1, 1, 1),
                     color=(INDIGO[0], INDIGO[1], INDIGO[2], PARENT_ALPHA),
                     geometry=G_GRID, topo=T_NONE, text="topo 0  Grid")
    sc.add(parent=gparent, t=(0, 0, 0), s=PROBE_SCALE, color=CORAL,
           geometry=G_CONE, topo=T_NONE, ch=1, text="probe")

    # Sphere station
    sc.add(parent=0, t=(sep, 0, 0), s=(REACH, REACH, REACH),
           color=RULER, geometry=G_SPHERE_WIRE, topo=T_NONE)
    sparent = sc.add(parent=0, t=(sep, 0, 0), s=(1, 1, 1),
                     color=(TEAL[0], TEAL[1], TEAL[2], PARENT_ALPHA),
                     geometry=G_SPHERE, topo=T_SPHERE, text="topo 2  Sphere")
    # No standoff here on purpose: the whole point of this scene is that both
    # probes receive byte-identical numbers, so the sphere probe starts with
    # its origin exactly on the surface, as altitude 0 literally means.
    sc.add(parent=sparent, t=(0, 0, 0), s=PROBE_SCALE, color=CORAL,
           geometry=G_CONE, topo=T_NONE, ch=1, text="probe")

    if screen:
        add_screen(sc, distance=REACH * 2.4, width=REACH * 1.4)

    tx, ty, tz = probe_tracks(TOPOS[T_NONE], frames_per_axis)
    sc.track(1, tx); sc.track(2, ty); sc.track(3, tz)
    sc.bind(1, 1, "translate_x")
    sc.bind(1, 2, "translate_y")
    sc.bind(1, 3, "translate_z")
    return sc


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

BINDABLE = {f"{g}_{a}" for g in ("translate", "rotate", "scale") for a in "xyz"} | \
           {f"{g}_rate_{a}" for g in ("translate", "rotate", "scale") for a in "xyz"} | \
           {"color_r", "color_g", "color_b", "color_a", "texture_id"}


def validate(scene: Scene) -> List[str]:
    problems: List[str] = []
    ids = [n["id"] for n in scene.nodes]
    if len(ids) != len(set(ids)):
        problems.append("duplicate node ids")
    idset = set(ids)
    for n in scene.nodes:
        if n["parent_id"] and n["parent_id"] not in idset:
            problems.append(f"node {n['id']}: parent {n['parent_id']} missing")
        if n["type"] not in (0, 1) and not n["hide"]:
            if min(n["scale_x"], n["scale_y"], n["scale_z"]) < MIN_SCALE:
                problems.append(f"node {n['id']}: scale below the {MIN_SCALE} render floor")
        for c in ("color_r", "color_g", "color_b", "color_a"):
            if not 0 <= n[c] <= 255:
                problems.append(f"node {n['id']}: {c} out of range")
    # three-way channel join
    channels = {c for c, _, _ in scene.chmap}
    for n in scene.nodes:
        if n["ch_input_id"] and n["ch_input_id"] not in channels:
            problems.append(f"node {n['id']}: ch_input_id {n['ch_input_id']} has no map row")
    for c, t, attr in scene.chmap:
        if t not in scene.tracks:
            problems.append(f"map row ({c},{t},{attr}): no ch{t} column")
        if attr not in BINDABLE:
            problems.append(f"map row ({c},{t},{attr}): '{attr}' is not bindable")
    if scene.tracks:
        lengths = {len(v) for v in scene.tracks.values()}
        if len(lengths) > 1:
            problems.append(f"tracks disagree on frame count: {sorted(lengths)}")
    return problems


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

# The CONCEPT scenes: what Channels can do, rather than what a topology does.
# Their numbering is a separate series from the topo* probe folders -- the two
# were once one sequence, but 01_grid_probe and 02_sphere_probe were retired
# once every topology got a probe scene of its own (they are topo08 and topo02
# now), and renumbering the survivors would break links to them.
SCENE_ORDER = ["triad", "comb", "rosetta", "screen"]
FOLDER = {"triad": "03_grid_axis_triad", "comb": "04_sphere_meridian_comb",
          "rosetta": "05_rosetta_grid_vs_sphere",
          "screen": "06_sphere_probe_with_screen"}


def build(name: str, args) -> Tuple[str, Scene]:
    if name == "triad":
        # Multi-child scenes stay clean: with three probes already in flight,
        # a comet and a chalk line each would read as clutter, not as clarity.
        return FOLDER[name], scene_axis_triad(screen=args.screen)
    if name == "comb":
        return FOLDER[name], scene_meridian_comb(screen=args.screen)
    if name == "rosetta":
        return FOLDER[name], scene_rosetta(args.frames_per_axis, args.screen)
    if name == "screen":
        return FOLDER[name], scene_probe(TOPOS[T_SPHERE], args.frames_per_axis,
                                         screen=True,
                                         scribe=not args.no_scribe,
                                         ghosts=args.ghosts,
                                         chalk_points=args.chalk_points)
    raise SystemExit(f"unknown scene: {name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="topology_animations")
    ap.add_argument("--scenes", nargs="*", default=SCENE_ORDER,
                    help=f"the concept scenes to build; any of: "
                         f"{' '.join(SCENE_ORDER)}")
    ap.add_argument("--probe-topo", type=int, default=None,
                    help="emit ONLY the probe scene for this topology id "
                         "(0 Grid, 1 Cube, 2 Sphere, 3 Torus, 4 Cylinder, "
                         "5 Pin, 6 Rod, 7 Point)")
    ap.add_argument("--no-probes", action="store_true",
                    help="skip the per-topology probe scenes; build only the "
                         "concept scenes")
    ap.add_argument("--frames-per-axis", type=int, default=150)
    ap.add_argument("--chalk-points", type=int, default=120)
    ap.add_argument("--ghosts", type=int, default=8)
    ap.add_argument("--screen", action="store_true",
                    help="add an upright video-screen plate on media/ texture 1")
    ap.add_argument("--no-scribe", action="store_true",
                    help="plain probe scenes: no comet, no self-drawing path")
    args = ap.parse_args()

    def probe(spec: TopoSpec) -> Tuple[str, Scene]:
        return spec.folder, scene_probe(
            spec, args.frames_per_axis, args.screen,
            scribe=not args.no_scribe, ghosts=args.ghosts,
            chalk_points=args.chalk_points)

    built = []
    if args.probe_topo is not None:
        built.append(probe(TOPOS[args.probe_topo]))
    else:
        # A plain run reproduces the published series exactly: one probe scene
        # per topology, in folder order, then the concept scenes.
        if not args.no_probes:
            built.extend(probe(s) for s in
                         sorted(TOPOS.values(), key=lambda s: s.folder))
        for name in args.scenes:
            built.append(build(name, args))

    for folder, sc in built:
        problems = validate(sc)
        out_dir = os.path.join(args.out, folder)
        paths = sc.write(out_dir)
        frames = max((len(v) for v in sc.tracks.values()), default=0)
        status = "OK" if not problems else "PROBLEMS: " + "; ".join(problems)
        print(f"{folder:32s} {len(sc.nodes):5d} nodes  "
              f"{len(sc.tracks):4d} tracks  {frames:5d} frames  [{status}]")

    print(f"\nWrote to {os.path.abspath(args.out)}")
    print("Open any <scene>_gv_node.csv in GlyphViz (File > Open); the ch-map "
          "and ch-tracks files in the same folder load automatically.")


if __name__ == "__main__":
    main()
