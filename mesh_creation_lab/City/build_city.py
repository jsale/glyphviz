#!/usr/bin/env python3
"""
Mesh City Example — a city block grid: streets, towers, traffic, street trees.

WHAT THIS DEMONSTRATES
----------------------
**Instancing, and why a mesh is a shape rather than an object.** The scene is
roughly 90 buildings, 60 vehicles and 70 street trees, and it is built from
*fourteen* OBJ files. Every building on the map is one of six massings, placed
by a rig node that carries its position, orientation and height; every car is
the same 300-triangle mesh wearing a different flat colour. A GlyphViz scene
pays for mesh *shapes*, not mesh *instances*, which is what makes a city
tractable at all.

**Two material regimes side by side.** The buildings are UV-textured — their
windows are texels, and `uv_world=True` means one facade image serves a
12-storey block and a 40-storey tower at the same window size. The cars are
the opposite case: a flat-coloured mesh with no texture at all, where the
node's `color_r/g/b` IS the paint. Both are meshes; they just answer different
questions.

**Street layout drives placement, not a random scatter.** Roads are laid as
one mesh with an asphalt texture and a dashed centre line, the blocks between
them are sized from the same grid, and buildings are set back inside their
own block — so the city reads as a plan rather than as noise.

A NOTE ON NON-UNIFORM SCALE
---------------------------
Building height varies by scaling the rig node UP only in z, which stretches
the facade's UVs with it and would make the windows tall. So height variation
here comes from *uniform* rig scale plus six different massings, and the one
deliberately stretched tower is labelled as such — it is the clearest way to
show what the trap looks like.

Run:
    <glyphviz-env>\\python.exe mesh_creation_lab/City/build_city.py
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

STEM = "mesh_city"

STOREY = 3.8
UV_PER_M = 1.0 / STOREY

BLOCK = 78.0          # block pitch, metres (building plot + street)
ROAD_W = 20.0         # street width
GRID = 5              # blocks per side


# --------------------------------------------------------------------------
# buildings
# --------------------------------------------------------------------------

def massing(kind: str, rng) -> mk.Model:
    """One building type, as a 2-part model: glazed body plus concrete trim.

    Six massings is enough for a skyline because the eye reads a city by
    SILHOUETTE and rhythm, not by counting distinct buildings — and the rig
    node's yaw gives each instance a different pair of visible faces anyway.
    """
    m = mk.Model(kind)
    body, trim = m.part('body'), m.part('trim')

    def block(w, d, z0, z1, cx=0.0, cy=0.0):
        body.extend(mk.prism(mk.rect(w, d, cx, cy), z0, z1,
                             uv_world=True, uv_scale=UV_PER_M))

    def band(w, d, z, t=0.8, cx=0.0, cy=0.0):
        trim.extend(mk.prism(mk.rect(w + 1.2, d + 1.2, cx, cy), z - t, z + t,
                             uv_world=True, uv_scale=UV_PER_M))

    if kind == 'slab':                      # a long mid-rise
        w, d, h = 44.0, 18.0, 14 * STOREY
        block(w, d, 0, h)
        band(w, d, h)
        trim.extend(mk.prism(mk.rect(6, 6, -12, 0), h, h + 4,
                             uv_world=True, uv_scale=UV_PER_M))

    elif kind == 'setback':                 # classic stepped tower
        z = 0.0
        for w, d, n in ((34, 30, 12), (26, 23, 10), (18, 16, 9)):
            block(w, d, z, z + n * STOREY)
            z += n * STOREY
            band(w, d, z)
        trim.extend(mk.prism(mk.rect(5, 5), z, z + 9,
                             uv_world=True, uv_scale=UV_PER_M))

    elif kind == 'tower':                   # a tall plain shaft on a podium
        block(40, 34, 0, 3 * STOREY)
        band(40, 34, 3 * STOREY)
        block(26, 24, 3 * STOREY, 36 * STOREY)
        band(26, 24, 36 * STOREY)

    elif kind == 'cylinder':                # a round tower, for silhouette
        poly = mk.polygon_regular(18, 15.0)
        body.extend(mk.prism(poly, 0, 30 * STOREY,
                             uv_world=True, uv_scale=UV_PER_M))
        trim.extend(mk.prism(mk.polygon_regular(18, 16.2), 30 * STOREY,
                             30 * STOREY + 1.6,
                             uv_world=True, uv_scale=UV_PER_M))

    elif kind == 'lowrise':                 # street-wall commercial
        w, d, h = 40.0, 26.0, 5 * STOREY
        block(w, d, 0, h)
        band(w, d, h, t=1.1)

    elif kind == 'twin':                    # two shafts on a shared base
        block(42, 26, 0, 2 * STOREY)
        band(42, 26, 2 * STOREY)
        for cx in (-11.0, 11.0):
            block(16, 20, 2 * STOREY, 24 * STOREY, cx=cx)
            band(16, 20, 24 * STOREY, cx=cx)

    # Rooftop clutter on everything, because a flat capped box reads as a
    # placeholder and three boxes read as a building.
    lo, hi = m.bounds()
    for _ in range(int(rng.integers(2, 5))):
        bw, bd = float(rng.uniform(2, 5)), float(rng.uniform(2, 4))
        bh = float(rng.uniform(1.5, 4.0))
        trim.extend(mk.box(size=(bw, bd, bh),
                           center=(float(rng.uniform(-6, 6)),
                                   float(rng.uniform(-5, 5)),
                                   hi[2] + bh / 2),
                           uv_world=True, uv_scale=0.3))
    return m


KINDS = ('slab', 'setback', 'tower', 'cylinder', 'lowrise', 'twin')


# --------------------------------------------------------------------------
# streets, vehicles, trees
# --------------------------------------------------------------------------

def build_streets() -> mk.Mesh:
    """The whole street grid as ONE mesh: a flat slab per carriageway.

    One mesh rather than one per street because the roads never move
    independently — and a single node is one draw call for the entire
    network."""
    m = mk.Mesh("streets")
    span = GRID * BLOCK
    half = span / 2
    for i in range(GRID + 1):
        c = -half + i * BLOCK
        # A road's UVs run ALONG the street (v) so the dashed centre line
        # repeats down its length, and only once across (u) so the line stays
        # in the middle. That is why streets are their own mesh and not part
        # of the ground plane.
        n = span / ROAD_W
        m.add_quad((-half, c - ROAD_W / 2, 0), (half, c - ROAD_W / 2, 0),
                   (half, c + ROAD_W / 2, 0), (-half, c + ROAD_W / 2, 0),
                   uvs=[(0, 0), (0, n), (1, n), (1, 0)])
        m.add_quad((c - ROAD_W / 2, -half, 0.02), (c + ROAD_W / 2, -half, 0.02),
                   (c + ROAD_W / 2, half, 0.02), (c - ROAD_W / 2, half, 0.02),
                   uvs=[(0, 0), (1, 0), (1, n), (0, n)])
    return m


def build_car() -> mk.Mesh:
    """A small saloon: a lofted body with a cabin and four wheels. Untextured
    in the scene, so the node colour is the paint."""
    m = mk.Mesh("car")
    # body: a tapered box lofted along its length
    secs = []
    for t, w, h, z in ((0.00, 0.62, 0.30, 0.34), (0.12, 0.86, 0.42, 0.30),
                       (0.40, 0.92, 0.50, 0.28), (0.72, 0.90, 0.46, 0.29),
                       (0.95, 0.70, 0.34, 0.33), (1.00, 0.60, 0.26, 0.36)):
        y = (t - 0.5) * 4.3
        secs.append(np.array([(-w, y, z - h), (w, y, z - h),
                              (w, y, z + h), (-w, y, z + h)]))
    m.extend(mk.loft(secs, closed=True, cap_start=True, cap_end=True))
    # cabin
    cab = []
    for t, w, h in ((0.0, 0.72, 0.30), (0.25, 0.80, 0.42),
                    (0.75, 0.78, 0.42), (1.0, 0.66, 0.26)):
        y = (t - 0.5) * 2.1 - 0.15
        cab.append(np.array([(-w, y, 0.78 - h * 0.6), (w, y, 0.78 - h * 0.6),
                             (w * 0.86, y, 0.78 + h), (-w * 0.86, y, 0.78 + h)]))
    m.extend(mk.loft(cab, closed=True, cap_start=True, cap_end=True))
    # wheels
    for sx in (-1, 1):
        for sy in (-1, 1):
            wheel = mk.revolve([(0.0, -0.16), (0.36, -0.16),
                                (0.36, 0.16), (0.0, 0.16)], segments=10)
            m.extend(wheel, mk.compose(mk.rot_y(90),
                                       mk.translate(sx * 0.92, sy * 1.35, 0.34)))
    return m


def build_street_tree() -> mk.Model:
    """A stylised plane tree: straight trunk, one lobed crown."""
    m = mk.Model("street_tree")
    m.part('trunk').extend(mk.revolve(
        [(0.30, 0), (0.24, 3.0), (0.20, 4.6), (0.16, 5.4)], segments=7))

    def crown(u, v):
        th, ph = u * 2 * math.pi, v * math.pi
        d = np.array([math.sin(ph) * math.cos(th),
                      math.sin(ph) * math.sin(th), math.cos(ph)])
        r = 2.9 * (1.0 + 0.16 * math.sin(3 * th) + 0.12 * math.cos(2 * ph))
        return tuple(d * r * np.array([1.0, 1.0, 0.82]) + np.array([0, 0, 7.6]))

    m.part('crown').extend(mk.surface(crown, 14, 9, wrap_u=True))
    return m


# --------------------------------------------------------------------------
# the scene
# --------------------------------------------------------------------------

def main() -> int:
    mesh_dir, media_dir = HERE / "meshes", HERE / "media"
    for d in (mesh_dir, media_dir):
        d.mkdir(parents=True, exist_ok=True)
    for old in list(mesh_dir.glob("*.obj")) + list(media_dir.glob("*.png")):
        old.unlink()

    rng = np.random.default_rng(17)

    print("modelling...")
    buildings = {}
    total = 0
    for kind in KINDS:
        model = massing(kind, np.random.default_rng(abs(hash(kind)) % 9999))
        model.save(mesh_dir, prefix=f"bldg_{kind}_")
        lo, hi = model.bounds()
        buildings[kind] = dict(
            model=model,
            files={k: f"bldg_{kind}_{k}.obj" for k in model.parts},
            asm=model.assembly(anchor=(0.0, 0.0, 0.0)),
            height=float(hi[2] - lo[2]),
            footprint=float(max(hi[0] - lo[0], hi[1] - lo[1])),
        )
        n = sum(len(p) for p in model.parts.values())
        total += n
        print(f"  {kind:9s} {n:5d} tris   {buildings[kind]['height']:6.1f} m")

    streets = build_streets(); streets.save_obj(mesh_dir / "streets.obj")
    car = build_car(); car.save_obj(mesh_dir / "car.obj")
    tree = build_street_tree(); tree.save(mesh_dir, prefix="tree_")
    print(f"  streets   {len(streets):5d} tris")
    print(f"  car       {len(car):5d} tris")
    print(f"  tree      {sum(len(p) for p in tree.parts.values()):5d} tris")

    print("painting textures...")
    tk.save(tk.asphalt(512, 256, seed=5, stripe=(0.86, 0.82, 0.42)),
            media_dir / "asphalt.png")
    for i, (seed, wall, lit, frac) in enumerate((
            (12, (0.32, 0.34, 0.39), (1.00, 0.86, 0.55), 0.40),
            (44, (0.40, 0.36, 0.32), (1.00, 0.92, 0.70), 0.30),
            (71, (0.26, 0.29, 0.33), (0.80, 0.90, 1.00), 0.48))):
        tk.save(tk.facade(512, 512, cols=3, rows=1, seed=seed,
                          wall=wall, lit=lit, lit_fraction=frac),
                media_dir / f"facade_{i + 1}.png")
    conc = tk.fbm(256, 256, period=6, octaves=5, seed=9)
    tk.save(tk.tint(conc, (0.42, 0.42, 0.41), (0.62, 0.61, 0.59)),
            media_dir / "concrete.png")
    grnd = tk.fbm(256, 256, period=12, octaves=5, seed=2)
    tk.save(tk.tint(grnd, (0.20, 0.21, 0.23), (0.32, 0.32, 0.34)),
            media_dir / "ground.png")
    tk.save(tk.bark(128, 128, seed=6), media_dir / "bark.png")
    tk.save(tk.foliage(256, 256, seed=14), media_dir / "leaves.png")

    print("building scene...")
    sb = SceneBuilder(HERE, STEM, background=(10, 13, 22),
                      tag_rgb=(220, 230, 245), fog=(300.0, 1200.0))
    for spec in buildings.values():
        for f in spec['files'].values():
            sb.register_mesh(f)
    for f in ("streets.obj", "car.obj", "tree_trunk.obj", "tree_crown.obj"):
        sb.register_mesh(f)
    for t in ("asphalt.png", "bark.png", "concrete.png", "facade_1.png",
              "facade_2.png", "facade_3.png", "ground.png", "leaves.png"):
        sb.register_texture(t)

    span = GRID * BLOCK

    # ---- ground and streets ---------------------------------------------
    sb.add(pos=(0, 0, -0.5), scale=(span * 0.78, span * 0.78, 0.5),
           color=(190, 195, 200), geometry=1, texture="ground.png",
           text="Ground — a built-in Cube glyph")

    st_pl = streets.placement()
    sb.add(pos=(0, 0, 0.12), scale=st_pl.radius, color=(225, 225, 228),
           mesh="streets.obj", texture="asphalt.png",
           text="Street grid — one mesh, one node, the whole network",
           pin_text=True)

    # ---- buildings -------------------------------------------------------
    # Every plot on the grid, minus a few left as squares.
    plots = []
    half = span / 2
    for i in range(GRID):
        for j in range(GRID):
            cx = -half + BLOCK * (i + 0.5)
            cy = -half + BLOCK * (j + 0.5)
            plots.append((cx, cy, i, j))

    facades = ("facade_1.png", "facade_2.png", "facade_3.png")
    built = 0
    for cx, cy, i, j in plots:
        if (i, j) in {(2, 2), (0, 4)}:        # public squares
            continue
        # Downtown is tall in the middle and falls off to the edges, which is
        # what makes a skyline instead of a field of boxes.
        r = math.hypot(cx, cy) / half
        tall = r < 0.45
        # 2-4 buildings per plot, set back inside it
        for k in range(int(rng.integers(2, 5))):
            kind = str(rng.choice(
                ('tower', 'setback', 'twin', 'cylinder') if tall
                else ('lowrise', 'slab', 'setback', 'lowrise')))
            spec = buildings[kind]
            size = float(rng.uniform(0.55, 0.85) * (1.25 if tall else 0.8))
            ox = float(rng.uniform(-1, 1) * (BLOCK - ROAD_W) * 0.22)
            oy = float(rng.uniform(-1, 1) * (BLOCK - ROAD_W) * 0.22)
            yaw = float(rng.choice((0, 90, 180, 270)) + rng.uniform(-3, 3))
            rig = sb.rig(pos=(cx + ox, cy + oy, 0.0), rot=(0, 0, yaw),
                         scale=size)
            tex = str(rng.choice(facades))
            for key, part in spec['asm'].items():
                sb.add(parent=rig.id, pos=part.offset, scale=part.scale,
                       mesh=spec['files'][key],
                       texture=tex if key == 'body' else "concrete.png",
                       color=(212, 224, 238) if key == 'body' else (224, 222, 216))
            built += 1

    # ---- the UV-stretch exhibit, set apart from the city ----------------
    # Two copies of the SAME massing on their own apron beside the grid: one
    # at uniform rig scale, one stretched only in z. Standing them together
    # off to one side is deliberate — dropped into the skyline the stretched
    # one just looks like a mistake, which is the opposite of the point.
    spec = buildings['setback']
    apron_x = -half - BLOCK * 1.35
    sb.add(pos=(apron_x, 0, -0.35), scale=(58, 92, 0.4), color=(196, 200, 206),
           geometry=1, texture="ground.png")

    for dy, rig_scale, label in (
            (-34.0, (0.85, 0.85, 0.85),
             "Uniform rig scale — one texture tile is one storey"),
            (34.0, (0.85, 0.85, 1.7),
             "Same mesh, rig scaled 2x in z only — the facade UVs stretch "
             "with it and every storey is twice as tall")):
        rig = sb.rig(pos=(apron_x, dy, 0.0), rot=(0, 0, -20),
                     scale=rig_scale, text=label, pin_text=True)
        for key, part in spec['asm'].items():
            sb.add(parent=rig.id, pos=part.offset, scale=part.scale,
                   mesh=spec['files'][key],
                   texture="facade_1.png" if key == 'body' else "concrete.png",
                   color=(212, 224, 238) if key == 'body' else (224, 222, 216))

    # ---- traffic: one mesh, many colours ---------------------------------
    car_pl = car.placement()
    car_s = car_pl.scale_for_length(4.6, axis=1)
    PAINT = [(196, 58, 48), (232, 232, 236), (36, 42, 56), (48, 96, 168),
             (220, 176, 48), (40, 110, 76), (150, 152, 158), (24, 26, 30)]
    lanes = []
    for i in range(GRID + 1):
        c = -half + i * BLOCK
        lanes.append(('x', c))
        lanes.append(('y', c))
    for n in range(64):
        axis, c = lanes[int(rng.integers(0, len(lanes)))]
        t = float(rng.uniform(-half, half))
        side = float(rng.choice((-1.0, 1.0)))
        off = side * ROAD_W * 0.24
        if axis == 'x':
            pos, yaw = (t, c + off, 0.0), (90.0 if side > 0 else 270.0)
        else:
            pos, yaw = (c - off, t, 0.0), (0.0 if side > 0 else 180.0)
        sb.add(pos=(pos[0], pos[1], car_pl.ground_z * car_s + 0.16),
               rot=(0, 0, yaw), scale=car_s, mesh="car.obj",
               color=PAINT[n % len(PAINT)],
               text="Untextured mesh — the node colour IS the paint"
                    if n == 0 else "")

    # ---- street trees ----------------------------------------------------
    tree_asm = tree.assembly(anchor=(0.0, 0.0, 0.0))
    tree_s = tree.rig_scale(11.0, axis=2)
    for i in range(GRID + 1):
        c = -half + i * BLOCK
        for t in np.arange(-half + 12, half - 8, 17.0):
            for axis in ('x', 'y'):
                if rng.random() > 0.42:
                    continue
                off = ROAD_W * 0.62 * float(rng.choice((-1.0, 1.0)))
                x, y = (t, c + off) if axis == 'x' else (c + off, t)
                rig = sb.rig(pos=(float(x), float(y), 0.0),
                             rot=(0, 0, float(rng.uniform(0, 360))),
                             scale=tree_s * float(rng.uniform(0.85, 1.15)))
                for key, part in tree_asm.items():
                    sb.add(parent=rig.id, pos=part.offset, scale=part.scale,
                           mesh=f"tree_{key}.obj",
                           texture="bark.png" if key == 'trunk' else "leaves.png",
                           color=(228, 216, 200) if key == 'trunk'
                                 else (196, 226, 180))

    sb.finish()
    print(f"  {built} buildings placed from {len(KINDS)} massings")
    print()
    print(f"Open {HERE.name}/{STEM}_gv_node.csv in GlyphViz "
          "(meshes/ and media/ load automatically).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
