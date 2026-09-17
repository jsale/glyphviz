#!/usr/bin/env python3
"""
Mesh Tree Example — a procedurally grown tree, exported as GEO_MESH shapes.

WHAT THIS DEMONSTRATES
----------------------
The first thing to know about meshes in GlyphViz is that a node paints its
mesh in ONE flat colour. That sounds like a limitation and is really a
statement about where the seam belongs: a multi-coloured model is built as
several meshes, one per material, assembled as nodes. This tree is the
smallest honest example — bark and canopy are two meshes, two nodes, two
colours, two textures, one tree.

The second thing is that a mesh is a *shape*, not an *object*. One trunk mesh
is instanced across the whole grove at different scales and rotations, so a
15-tree grove costs two OBJ files, not fifteen. That is the same economy the
built-in glyphs have always had, extended to arbitrary geometry.

The grove also carries a deliberate contrast: the big oak on the right is the
same two meshes as its neighbours, just scaled up and re-coloured, while the
bare winter tree uses the trunk mesh alone with no canopy node at all.

HOW THE TREE IS GROWN
---------------------
A recursive branching walk (the classic "space colonization lite": each branch
splits into 2-3 children with a randomized angle, length and taper). Branches
are swept tubes along their own path -- meshkit.tube, which uses
parallel-transport frames so a branch curving over vertically doesn't spin.
Leaves are not modelled individually; the canopy is a set of overlapping
irregular blobs at the branch tips, which is what a tree reads as at any
distance you would actually view a scene from.

Run:
    <glyphviz-env>\\python.exe mesh_creation_lab/Tree/build_tree.py
"""
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))   # the lab's toolkit

import meshkit as mk        # noqa: E402
import texkit as tk         # noqa: E402
from gvscene import SceneBuilder   # noqa: E402

STEM = "mesh_tree"


# --------------------------------------------------------------------------
# growth
# --------------------------------------------------------------------------

def grow(rng, *, depth=6, base_len=9.0, base_rad=0.62,
         split=(2, 3), spread=(22, 46), taper=0.70, shrink=0.76,
         droop=0.0):
    """Recursively grow branch segments.

    Returns (branches, tips): branches are (path, radii) pairs ready to sweep;
    tips are the end points of the outermost branches, where canopy blobs go.

    `droop` bends a branch downward along its own length — the difference
    between a poplar (0) and a willow (large).
    """
    branches, tips = [], []

    def branch(origin, direction, length, radius, level):
        # Curve the branch a little along its run rather than drawing a
        # straight stick: real branches bend, and a swept tube shows it.
        n_seg = max(3, 7 - level)
        bend = rng.normal(0, 0.16, size=3)
        bend[2] -= droop
        path = [np.array(origin, dtype=float)]
        d = np.array(direction, dtype=float)
        for s in range(n_seg):
            d = d + bend / n_seg
            d /= np.linalg.norm(d)
            path.append(path[-1] + d * (length / n_seg))
        path = np.array(path)
        radii = np.linspace(radius, radius * taper, len(path))
        branches.append((path, radii))

        if level >= depth or radius < 0.035:
            tips.append((path[-1], length))
            return

        n_kids = int(rng.integers(split[0], split[1] + 1))
        # A branch that always split symmetrically would read as a fractal
        # diagram; one child continues near the parent's heading and the rest
        # fan off it, which is what gives a tree a leader and side branches.
        for k in range(n_kids):
            ang = math.radians(rng.uniform(*spread) * (0.35 if k == 0 else 1.0))
            azi = rng.uniform(0, 2 * math.pi) + k * (2 * math.pi / n_kids)
            # tilt `d` away from itself by `ang` about a perpendicular axis
            perp = np.cross(d, [0, 0, 1.0])
            if np.linalg.norm(perp) < 1e-6:
                perp = np.array([1.0, 0, 0])
            perp /= np.linalg.norm(perp)
            axis = (perp * math.cos(azi)
                    + np.cross(d, perp) * math.sin(azi))
            axis /= np.linalg.norm(axis)
            ca, sa = math.cos(ang), math.sin(ang)
            nd = d * ca + np.cross(axis, d) * sa + axis * float(np.dot(axis, d)) * (1 - ca)
            branch(path[-1], nd / np.linalg.norm(nd),
                   length * shrink * rng.uniform(0.85, 1.12),
                   radius * taper * rng.uniform(0.86, 1.0), level + 1)

    branch((0, 0, 0), (0, 0, 1), base_len, base_rad, 0)
    return branches, tips


def build_trunk(branches, segments=7) -> mk.Mesh:
    """Sweep every branch into one mesh. Segment count falls with radius —
    a twig needs 5 sides, the trunk wants more, and paying for the trunk's
    resolution on every twig is how a tree becomes a 200k-triangle file."""
    m = mk.Mesh("trunk")
    for path, radii in branches:
        segs = 5 if radii[0] < 0.12 else (segments if radii[0] < 0.4 else segments + 5)
        # uv_u_repeat spreads the bark texture around the branch proportional
        # to its girth, so bark grain stays one size across trunk and twig.
        m.extend(mk.tube(path, radii, segments=segs,
                         cap_start=False, cap_end=False,
                         uv_u_repeat=max(1.0, radii[0] * 6)))
    return m


def build_canopy(rng, tips, blob_scale=1.0) -> mk.Mesh:
    """Irregular blobs at the branch tips. Each is a low-frequency deformed
    sphere, so the canopy has silhouette rather than reading as bubbles."""
    m = mk.Mesh("canopy")
    for tip, length in tips:
        r = length * 0.62 * blob_scale * rng.uniform(0.8, 1.25)
        # three random lobes per blob, combined into the radius function
        lobes = rng.normal(0, 1, (3, 3))
        lobes /= np.linalg.norm(lobes, axis=1, keepdims=True)
        amps = rng.uniform(0.12, 0.30, 3)

        def shape(u, v, r=r, lobes=lobes, amps=amps):
            th, ph = u * 2 * math.pi, v * math.pi
            d = np.array([math.sin(ph) * math.cos(th),
                          math.sin(ph) * math.sin(th), math.cos(ph)])
            rr = r * (1.0 + sum(a * float(np.dot(d, L)) ** 2 - a * 0.4
                                for a, L in zip(amps, lobes)))
            return tuple(d * rr)

        # 8x6 is deliberately coarse. These are overlapping lumps read at
        # tree distance, and the canopy is by far the biggest file in the
        # scene -- at 11x8 the oak's canopy alone was a 2.3 MB OBJ, which is
        # a lot of bytes to ship for silhouette nobody can resolve.
        blob = mk.surface(shape, 8, 6, wrap_u=True, name="blob")
        m.extend(blob, mk.translate(*tip))
    return m


# --------------------------------------------------------------------------
# the scene
# --------------------------------------------------------------------------

# A textured node's color_r/g/b MULTIPLIES its texture (GL_MODULATE), so
# these are near-white TINTS, not the colours you see. Writing the real bark
# brown here would multiply brown by brown and render the grove nearly black —
# which is exactly what the first draft of this scene did. The rule for the
# whole mesh series: **texture carries the hue, the node colour only shades
# it.** An untextured mesh is the opposite case and takes a real colour.
#
# (label, seed, growth kwargs, canopy scale, trunk tint, leaf tint)
SPECIES = [
    ("Oak",          7, dict(depth=6, base_len=9.0, base_rad=0.62,
                             spread=(26, 52), shrink=0.74), 1.0,
     (245, 238, 230), (230, 250, 225)),
    ("Pine",        21, dict(depth=6, base_len=13.0, base_rad=0.48,
                             spread=(14, 30), shrink=0.70, taper=0.62), 0.55,
     (225, 215, 205), (205, 245, 225)),
    ("Willow",      33, dict(depth=6, base_len=8.0, base_rad=0.55,
                             spread=(30, 62), shrink=0.78, droop=0.55), 0.85,
     (250, 242, 225), (245, 255, 210)),
]


def main() -> int:
    mesh_dir, media_dir = HERE / "meshes", HERE / "media"
    for d in (mesh_dir, media_dir):
        d.mkdir(parents=True, exist_ok=True)
    for old in list(mesh_dir.glob("*.obj")) + list(media_dir.glob("*.png")):
        old.unlink()

    print("growing trees...")
    built = {}
    for name, seed, kwargs, canopy_scale, bark_rgb, leaf_rgb in SPECIES:
        r = np.random.default_rng(seed)
        branches, tips = grow(r, **kwargs)
        model = mk.Model(name.lower())
        model.parts['trunk'] = build_trunk(branches)
        model.parts['canopy'] = build_canopy(r, tips, canopy_scale)
        model.save(mesh_dir, prefix=f"{name.lower()}_")
        # The rig sits at the middle of the trunk's base, so placing a tree is
        # just "put the rig where the tree goes" — no ground offset to work out.
        built[name] = dict(
            model=model,
            files={k: f"{name.lower()}_{k}.obj" for k in model.parts},
            asm=model.assembly(anchor=(0.0, 0.0, 0.0)),
            bark=bark_rgb, leaf=leaf_rgb,
        )
        print(f"  {name:8s} trunk {len(model.parts['trunk']):6d} tris"
              f"   canopy {len(model.parts['canopy']):6d} tris"
              f"   ({len(branches)} branches, {len(tips)} tips)")

    print("painting textures...")
    tk.save(tk.bark(256, 256, seed=2), media_dir / "bark.png")
    tk.save(tk.foliage(256, 256, seed=5), media_dir / "leaves.png")
    tk.save(tk.foliage(256, 256, seed=11, base=(0.34, 0.30, 0.12)),
            media_dir / "leaves_autumn.png")
    grass = tk.fbm(256, 256, period=10, octaves=5, seed=3)
    tk.save(tk.tint(grass, (0.13, 0.20, 0.10), (0.26, 0.36, 0.16)),
            media_dir / "ground.png")

    print("building scene...")
    sb = SceneBuilder(HERE, STEM, background=(96, 122, 150),
                      tag_rgb=(20, 26, 34), fog=(220.0, 780.0))
    for spec in built.values():
        for f in spec['files'].values():
            sb.register_mesh(f)
    for t in ("bark.png", "ground.png", "leaves.png", "leaves_autumn.png"):
        sb.register_texture(t)

    def plant(name, x, y, height, yaw, *, bark=None, leaf=None,
              leaf_tex="leaves.png", canopy=True, label="", pin=False):
        """One tree: a hidden rig node carrying position/rotation/size, with
        the trunk and canopy meshes hung off it by Model.assembly()."""
        spec = built[name]
        S = spec['model'].rig_scale(height, axis=2)
        rig = sb.rig(pos=(x, y, 0.0), rot=(0, 0, yaw), scale=S,
                     text=label, pin_text=pin)
        for key, part in spec['asm'].items():
            if key == 'canopy' and not canopy:
                continue
            sb.add(parent=rig.id, pos=part.offset, scale=part.scale,
                   mesh=spec['files'][key],
                   color=(bark or spec['bark']) if key == 'trunk'
                         else (leaf or spec['leaf']),
                   texture="bark.png" if key == 'trunk' else leaf_tex,
                   alpha=255 if key == 'trunk' else 248)
        return rig

    # ---- ground ----------------------------------------------------------
    sb.add(pos=(0, 0, -0.5), scale=(230, 230, 0.5), color=(220, 230, 205),
           geometry=1, texture="ground.png",
           text="Ground — a built-in Cube glyph, not a mesh")

    # ---- the grove: 14 trees from 6 mesh files ---------------------------
    names = list(built)
    rng = np.random.default_rng(12)
    for i in range(14):
        ang = i * (2 * math.pi / 14) + rng.uniform(-0.25, 0.25)
        rad = 42 + rng.uniform(-12, 30)
        plant(names[i % len(names)],
              rad * math.cos(ang), rad * math.sin(ang),
              height=float(rng.uniform(20, 34)),
              yaw=float(rng.uniform(0, 360)),
              leaf_tex="leaves_autumn.png" if i % 5 == 3 else "leaves.png",
              label=f"{names[i % len(names)]} — instance {i + 1} of the same two meshes"
                    if i < 3 else "")

    # ---- the specimen oak: same meshes, twice the size -------------------
    plant("Oak", -78, 14, height=56.0, yaw=25,
          bark=(255, 246, 232), leaf=(220, 250, 205),
          label="Specimen oak — the same two meshes as the grove, scaled 2x",
          pin=True)

    # ---- the winter willow: trunk mesh alone, no canopy node -------------
    plant("Willow", 74, -44, height=30.0, yaw=200,
          bark=(210, 205, 200), canopy=False,
          label="Winter willow — the trunk mesh with its canopy node left off",
          pin=True)

    sb.finish()
    print()
    print(f"Open {HERE.name}/{STEM}_gv_node.csv in GlyphViz "
          "(meshes/ and media/ load automatically).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
