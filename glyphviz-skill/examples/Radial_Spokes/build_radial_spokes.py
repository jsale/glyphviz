#!/usr/bin/env python3
"""Radial_Spokes — the known-good scene for "which way does this glyph point?"

Rods radiating from a hub is the smallest scene in which aim can be wrong, and
it is the one that keeps going wrong. The mistake is always the same: reaching
for `rotate_x/y/z` to point a rod, when the direction a glyph faces is decided
by **placement**. The angle you want is a `translate_x`.

Three hubs, twelve rods each, all built the same way and all with
**`rotate_x = rotate_y = rotate_z = 0`**:

    left    Sphere hub (topo 2)  translate_z = height ABOVE the surface
    centre  Point hub  (topo 7)  translate_z = the FULL distance from the centre
    right   Cube hub   (topo 1)  one rod per facet, aimed along the facet
                                 normal, showing that "outward" is per-topology

(left/centre/right as seen from the overhead +Z View, where screen-right is
+Y and screen-up is -X -- which is why the hubs are spaced along Y.)

The Sphere hub is also a working clock face: hour 12 is up, 3 is right, 6 is
down and 9 is left when viewed from GlyphViz's overhead +Z View. Longitude runs
counter-clockwise seen from +Z, so a clockwise dial needs *decreasing*
longitude -- `translate_x = (180 - 30 * hour) % 360`.

Nothing in this scene carries data. It exists to be measured, and
`aim_report.txt` beside it is that measurement, produced by the checker:
every rod's world +Z, which for the Sphere and Point hubs is its own outward
radial to 16 decimal places.

    python build_radial_spokes.py
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "code"))

from gv_kernel import load_node_csv, compute_world_transforms  # noqa: E402
from gv_extents import analyse, report  # noqa: E402

GEO_SPHERE, GEO_CYLINDER, GEO_CIRCLE, GEO_CUBE = 3, 19, 24, 1
TOPO_NONE, TOPO_CUBE, TOPO_SPHERE, TOPO_POINT = 0, 1, 2, 7
TYPE_WORLD, TYPE_GLYPH = 0, 5
ROT_EULER = 0

BG = (12, 12, 24, 255)
QUARTER = (255, 190, 60)          # 12, 3, 6, 9 -- the cardinal hours
HOUR = (110, 160, 220)
FACET = (150, 200, 150)

ROD_HALF = 2.0        # scale_z; a Cylinder spans -1..1 in z, so length = 2 x this
ROD_RADIUS = 0.2      # scale_x/y, at the minimum-glyph-size clamp so it is a no-op
HUB_PITCH = 16.0      # world units between the three hubs
N = 12

# 12 o'clock faces longitude 180 because GlyphViz's overhead +Z View (azimuth 0,
# elevation 89) puts -X at the top of the screen and +Y at the right. "Up" is a
# camera property, not a world one, so this number follows from the view you
# intend -- measured off a real render, not assumed.
LON_12 = 180.0

COLUMNS = ["id", "type", "parent_id", "branch_level",
           "translate_x", "translate_y", "translate_z",
           "rotate_x", "rotate_y", "rotate_z",
           "scale_x", "scale_y", "scale_z",
           "color_r", "color_g", "color_b", "color_a",
           "geometry", "hide", "topo", "ratio", "facet", "show_text", "text"]

DEFAULTS = dict(translate_x=0.0, translate_y=0.0, translate_z=0.0,
                rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                scale_x=1.0, scale_y=1.0, scale_z=1.0,
                color_r=255, color_g=255, color_b=255, color_a=255,
                geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE, ratio=0.1,
                facet=1, show_text=0, text="")


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


def sanitize(s: str) -> str:
    return "".join(c for c in s if c.isprintable() and c not in '",')


def rod(sb, hub, lon, lat, reach, rgb, label, show=0) -> int:
    """One rod. The ONLY thing that decides which way it points is `lon`/`lat`.

    Note what is absent: every rotate field stays 0. The parent's topology
    supplies a base rotation that puts this rod's local +Z along the outward
    direction at (lon, lat), and +Z is a Cylinder's long axis, so the rod
    points straight out with no rotation of its own.
    """
    return sb.add(type=TYPE_GLYPH, parent_id=hub, branch_level=1,
                  translate_x=lon, translate_y=lat, translate_z=reach,
                  rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                  scale_x=ROD_RADIUS, scale_y=ROD_RADIUS, scale_z=ROD_HALF,
                  geometry=GEO_CYLINDER, topo=TOPO_NONE,
                  color_r=rgb[0], color_g=rgb[1], color_b=rgb[2],
                  show_text=show, text=sanitize(label))


def caption(sb, x, y, z, text, size=1.1) -> int:
    return sb.add(type=TYPE_GLYPH, parent_id=0, branch_level=0,
                  translate_x=x, translate_y=y, translate_z=z,
                  scale_x=size, scale_y=size, scale_z=size, ratio=0.02,
                  geometry=GEO_CIRCLE, color_r=228, color_g=232, color_b=240,
                  color_a=200, show_text=1, text=sanitize(text))


def build() -> pd.DataFrame:
    sb = SceneBuilder()
    sb.add(type=TYPE_WORLD, parent_id=0, branch_level=0, geometry=0,
           color_r=BG[0], color_g=BG[1], color_b=BG[2], color_a=BG[3],
           text="World row: background colour only")

    # ---- Sphere hub: a working clock face --------------------------------
    # translate_z is height ABOVE the surface, so the hub's own radius (1 x
    # Global Scale) puts the rod's centre at 1 + reach. reach = ROD_HALF sets
    # the rod's inner end exactly flush with the hub.
    hub_s = sb.add(type=TYPE_GLYPH, parent_id=0, branch_level=0,
                   translate_y=-HUB_PITCH,
                   geometry=GEO_SPHERE, topo=TOPO_SPHERE,
                   color_r=225, color_g=228, color_b=238,
                   text="Sphere hub (topo 2) -- translate_z is height above the surface")
    for i in range(N):
        lon = i * 360.0 / N
        hour = int((LON_12 - lon) / 30.0) % 12 or 12
        rgb = QUARTER if hour % 3 == 0 else HOUR
        rod(sb, hub_s, lon, 0.0, ROD_HALF, rgb,
            f"{hour} o'clock  lon {lon:g}", show=1 if hour == 12 else 0)
    caption(sb, 7.0, -HUB_PITCH, 0.0,
            "Sphere hub (topo 2) - a clock face; every rotate field is 0")

    # ---- Point hub: same spokes, different reach convention ---------------
    # A Point parent has no base radius: translate_z IS the centre distance.
    hub_p = sb.add(type=TYPE_GLYPH, parent_id=0, branch_level=0,
                   geometry=GEO_SPHERE, topo=TOPO_POINT,
                   color_r=225, color_g=228, color_b=238,
                   text="Point hub (topo 7) -- translate_z is the full reach")
    for i in range(N):
        lon = i * 360.0 / N
        rod(sb, hub_p, lon, 0.0, 1.0 + ROD_HALF, HOUR, f"bearing {lon:g} deg")
    caption(sb, 10.0, 0.0, 0.0,
            "Point hub (topo 7) - translate_z measured from the centre")

    # ---- Cube hub: "outward" is the FACET normal, not the radial ----------
    # Worth seeing next to the other two: a Cube parent aims each child along
    # the normal of the facet it sits on, so six rods point along the axes
    # however their in-face translate_x/y are set.
    hub_c = sb.add(type=TYPE_GLYPH, parent_id=0, branch_level=0,
                   translate_y=HUB_PITCH,
                   geometry=GEO_CUBE, topo=TOPO_CUBE,
                   color_r=225, color_g=228, color_b=238,
                   text="Cube hub (topo 1) -- aim is the facet normal, per facet")
    for f in range(1, 7):
        sb.add(type=TYPE_GLYPH, parent_id=hub_c, branch_level=1,
               translate_x=0.0, translate_y=0.0, translate_z=ROD_HALF,
               scale_x=ROD_RADIUS, scale_y=ROD_RADIUS, scale_z=ROD_HALF,
               geometry=GEO_CYLINDER, topo=TOPO_NONE, facet=f,
               color_r=FACET[0], color_g=FACET[1], color_b=FACET[2],
               text=sanitize(f"facet {f} normal"))
    caption(sb, 13.0, HUB_PITCH, 0.0,
            "Cube hub (topo 1) - aim follows the facet, not the translate")

    return sb.to_dataframe()


# ---------------------------------------------------------------------------
# VERIFY -- the claims in the README, re-derived through the real engine
# ---------------------------------------------------------------------------
def verify(path: Path) -> list[str]:
    nodes = load_node_csv(str(path))
    tr = compute_world_transforms(nodes, 1.0)
    by_id = {n.id: n for n in nodes}
    errs: list[str] = []

    for hub in [n for n in nodes if n.topo in (TOPO_SPHERE, TOPO_POINT)]:
        kids = [n for n in nodes
                if n.parent_id == hub.id and n.geometry == GEO_CYLINDER]
        if len(kids) != N:
            errs.append(f"hub {hub.id}: {len(kids)} rods, expected {N}")
            continue
        hc = tr.world_pos[tr.row_of_id[hub.id]]
        bearings = []
        for k in kids:
            pos = tr.world_pos[tr.row_of_id[k.id]]
            z = tr.world_basis[tr.row_of_id[k.id]][:, 2]
            z = z / np.linalg.norm(z)
            radial = pos - hc
            radial = radial / np.linalg.norm(radial)
            # THE claim of this whole example: +Z is the outward radial, exactly.
            if abs(float(z @ radial) - 1.0) > 1e-12:
                errs.append(f"hub {hub.id} rod {k.id}: +Z . radial = "
                            f"{float(z @ radial):.15f}, not 1")
            if abs(pos[2] - hc[2]) > 1e-9:
                errs.append(f"hub {hub.id} rod {k.id}: z = {pos[2]:.6f}, "
                            f"not level with the hub")
            bearings.append(math.degrees(math.atan2(radial[1], radial[0])) % 360.0)
        gaps = sorted(bearings)
        step = 360.0 / N
        for a, b in zip(gaps, gaps[1:]):
            if abs((b - a) - step) > 1e-9:
                errs.append(f"hub {hub.id}: bearings {a:.4f} and {b:.4f} are "
                            f"{b - a:.4f} apart, not {step:g}")

    # The clock reading, from the render's point of view: +Z View puts -X up
    # and +Y right, so screen-up is the -X axis.
    hub_s = next(n for n in nodes if n.topo == TOPO_SPHERE)
    hc = tr.world_pos[tr.row_of_id[hub_s.id]]
    for label, want in (("12", np.array([-1.0, 0.0, 0.0])),
                        ("3", np.array([0.0, 1.0, 0.0])),
                        ("6", np.array([1.0, 0.0, 0.0])),
                        ("9", np.array([0.0, -1.0, 0.0]))):
        k = next(n for n in nodes
                 if n.parent_id == hub_s.id and n.text.startswith(label + " o'clock"))
        d = tr.world_pos[tr.row_of_id[k.id]] - hc
        d = d / np.linalg.norm(d)
        if float(d @ want) < 1 - 1e-9:
            errs.append(f"{label} o'clock points {np.round(d, 4)}, "
                        f"screen direction wants {want}")

    # Every rod in the scene must be at zero rotation -- that IS the lesson.
    for n in nodes:
        if n.geometry == GEO_CYLINDER and any((n.rotate_x, n.rotate_y, n.rotate_z)):
            errs.append(f"rod {n.id} carries a rotation; this scene must not")

    # And the Cube hub aims along facet normals, one per axis direction.
    hub_c = next(n for n in nodes if n.topo == TOPO_CUBE)
    normals = []
    for k in [n for n in nodes if n.parent_id == hub_c.id]:
        z = tr.world_basis[tr.row_of_id[k.id]][:, 2]
        normals.append(np.round(z / np.linalg.norm(z), 9))
    axes = {tuple(v) for v in normals}
    want = {(1., 0., 0.), (-1., 0., 0.), (0., 1., 0.),
            (0., -1., 0.), (0., 0., 1.), (0., 0., -1.)}
    if axes != want:
        errs.append(f"cube hub normals {sorted(axes)}, expected the six axes")
    return errs


def main() -> int:
    scene = build()
    out = HERE / "radial_spokes_gv_node.csv"
    scene.to_csv(out, index=False, encoding="utf-8", lineterminator="\r\n",
                 float_format="%.4f")
    print(f"{out.name}: {len(scene)} rows")

    errs = verify(out)
    if errs:
        print("\n".join("  !! " + e for e in errs))
        out.unlink()
        return 1
    print("  every rod's +Z equals its own outward radial to 1e-12,")
    print("  bearings exactly 30 deg apart, all rods level, all rotations 0,")
    print("  cube hub aimed along the six facet normals")

    txt = HERE / "aim_report.txt"
    txt.write_text(
        "radial_spokes_gv_node.csv -- the checker's own output, committed so the\n"
        "numbers can be read without running anything.\n\n"
        "Regenerate with:  python ../../code/gv_extents.py "
        "radial_spokes_gv_node.csv --all\n\n"
        + report(analyse(str(out), 1.0), show_all=True) + "\n",
        encoding="utf-8")
    print(f"  {txt.name} written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
