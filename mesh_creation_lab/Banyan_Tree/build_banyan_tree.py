#!/usr/bin/env python3
"""
The Banyan Tree Community School — a community and school that was drawn,
dreamed and never built, built here from its drawings.

SOURCE MATERIAL
---------------
Three black-and-white drawings by Jeff Sale and Jodi Reed (drawings/) and the
web page that carried them, describing a co-housing community of a few
families outside San Diego with a school at its heart:

* the community plan ("The Initial Community") — dwellings, a Main Hall and
  school, garden/orchard/husbandry, greenhouse, water reclamation, a lake, a
  pool, a playground, hills and forests;
* the school's floor plan ("Top View") — traced pixel for pixel into walls,
  rooms and roof by plan_trace.py and organic.py;
* the school's elevation — a stone tower with an observation deck and
  telescope, built of stone, mortar, reinforced concrete, redwood and cedar,
  in the spirit of the Julian architect James Hubbell.

Everything the drawings don't say — colour, materials, furnishings, terrain,
the trees — is interpretation, taken from the page's own wish list wherever
it offers one (a hearth for after-dinner discussions, a truly awesome
library, an observatory, a pond ecosystem, computers, a tree house).

SCALE AND FRAME
---------------
Metres. +x east, +y north, z up. The origin is the Main Hall's hearth. The
floor plan is read at 0.06 m/px (an 18 m Main Hall); the community plan at
0.39 m/px, which makes the school the same size on both drawings and the
site about 11 acres.

Run:
    <glyphviz-env>\\python.exe mesh_creation_lab/Banyan_Tree/build_banyan_tree.py
    ... --only school      (the building alone, for fast iteration)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))      # the lab's toolkit
sys.path.insert(0, str(HERE))

import texkit as tk                       # noqa: E402
from gvscene import SceneBuilder          # noqa: E402

import plan_trace as pt                   # noqa: E402
import textures as tx                     # noqa: E402
from kit import Kit                       # noqa: E402
from school import School, furniture_pieces   # noqa: E402

STEM = "banyan_tree"


def paint_textures(media_dir: Path, plan, only_school=False):
    """Write every texture; returns {role: filename}."""
    t0 = time.time()
    T = {}

    def put(role, fname, img):
        tk.save(img, media_dir / fname)
        T[role] = fname

    put('wall', "school_wall.png", tx.school_wall())
    put('stone', "fieldstone.png", tx.fieldstone())
    put('roof', "roof_plaster.png", tx.roof_plaster())
    put('planks', "redwood_planks.png", tx.wood_planks(256, 256, seed=3))
    put('floor', "school_floor.png", tx.floor_plan_texture(plan))
    put('books', "books.png", tx.books())
    put('cubbies', "cubbies.png", tx.cubbies())
    for role, src in (('drawing_community', 'banyan_community'),
                      ('drawing_elevation', 'banyan_elevation'),
                      ('drawing_floor_plan', 'banyan_floor_plan')):
        put(role, f"{role}.png", tx.load_drawing(HERE / "drawings" / f"{src}.png"))
    if not only_school:
        import site_plan
        T.update(site_plan.paint_textures(media_dir, put))
    print(f"  textures: {len(T)} in {time.time() - t0:.1f}s")
    return T


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', choices=['school'], default=None)
    args = ap.parse_args()
    only_school = args.only == 'school'

    mesh_dir, media_dir = HERE / "meshes", HERE / "media"
    for d in (mesh_dir, media_dir):
        d.mkdir(parents=True, exist_ok=True)
    for old in list(mesh_dir.glob("*.obj")) + list(media_dir.glob("*.png")):
        old.unlink()

    print("tracing the floor plan...")
    plan = pt.trace()
    print(f"  rooms: {', '.join(plan.room_names)}")

    print("painting textures...")
    tex = paint_textures(media_dir, plan, only_school)

    kit = Kit(mesh_dir)
    print("modelling the school...")
    school = School(plan)
    school.build(kit, tex)
    pieces = furniture_pieces(kit)
    school.furnish(kit, tex, pieces)

    if not only_school:
        import site_plan
        print("modelling the site...")
        site_plan.build(kit, tex, school, pieces)

    print("writing the scene...")
    sb = SceneBuilder(HERE, STEM, background=(168, 196, 222),
                      tag_rgb=(24, 30, 40), fog=None if only_school else (260.0, 900.0))
    kit.emit(sb)
    sb.finish()
    print(f"  {len(kit.meshes)} mesh files, {kit.tris:,} triangles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
