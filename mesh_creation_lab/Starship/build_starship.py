#!/usr/bin/env python3
"""
Mesh Starship Example — a capital ship, a fleet, and procedural greebling.

WHAT THIS DEMONSTRATES
----------------------
**Greebling: detail generated rather than modelled.** The dagger hull is a
handful of lofted sections. Everything that makes it read as a 2 km warship
instead of a paper aeroplane is scattered afterwards by code — 1,600 boxes,
blisters and trenches, sized by a power law so there are a few big ones and a
great many small ones. That distribution is the trick: it is
what gives the eye something to judge scale against at every zoom level, and
it is the reason a nearly featureless silhouette suddenly looks enormous.

**A dense mesh, as a capacity check.** The greeble layer alone is about
19,000 triangles — a different regime from the jet's 2,700 — and it compiles
into one display list and draws as one node. Pass `--greebles` to push it
further if you want to see where your machine stops enjoying itself.

**Textures carrying detail the geometry does not.** The hull plating image is
generated as rectangular plates with recessed seams, rivet runs and streaked
weathering, tiled by real size (`uv_world`) so plate size stays constant
across the big hull and the small escorts. Greebles get their own busier map.

**Emissive-looking parts without any emissive support.** GlyphViz lights with
one eye-space headlight and has no emission channel, so engine bells and
window strips are separate meshes drawn in bright saturated colour with
`render_mode` left alone — the same trick a flat-shaded sprite uses. They
read as lit because everything around them is not.

THE SCENE
---------
One capital ship with its parts labelled, two escorts, and a scatter of
fighters on a patrol vector. Fog is set far out so the fleet has depth
without the near ship being washed.

Run:
    <glyphviz-env>\\python.exe mesh_creation_lab/Starship/build_starship.py
    <glyphviz-env>\\python.exe mesh_creation_lab/Starship/build_starship.py --greebles 400
"""
import argparse
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))   # the lab's toolkit

import meshkit as mk        # noqa: E402
import texkit as tk         # noqa: E402
from gvscene import SceneBuilder   # noqa: E402

STEM = "mesh_starship"

LEN = 200.0        # model units, nose (+Y) to engine deck


# --------------------------------------------------------------------------
# hull
# --------------------------------------------------------------------------

def hull_section(t: float, n: int = 22):
    """One station of the dagger hull.

    The cross-section is a flattened wedge: wide and thin, with a sharp keel
    below and a flat dorsal deck above. `t` runs 0 at the bow to 1 at the
    stern, and the half-width grows almost linearly — which is what makes the
    plan view a triangle rather than a cigar.
    """
    w = (0.020 + 0.150 * t ** 0.92) * LEN          # half-width
    h_up = (0.004 + 0.038 * t ** 1.10) * LEN       # deck height
    h_dn = (0.006 + 0.055 * t ** 1.05) * LEN       # keel depth

    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    cx, cz = np.cos(a), np.sin(a)
    # flat top, vee bottom: raise the exponent above the deck, lower it below
    x = np.sign(cx) * np.abs(cx) ** 0.55 * w
    z = np.where(cz >= 0,
                 np.abs(cz) ** 0.70 * h_up,
                 -np.abs(cz) ** 1.60 * h_dn)
    return np.stack([x, np.full(n, t * LEN), z], axis=1)


def build_hull() -> mk.Mesh:
    ts = np.concatenate([np.linspace(0.0, 0.25, 9) ** 1.0,
                         np.linspace(0.27, 1.0, 22)])
    return mk.loft([hull_section(float(t)) for t in ts],
                   closed=True, cap_start=True, cap_end=True,
                   uv_u_repeat=6.0)


def _surface_point(t, u):
    """A point on the hull surface at station *t*, angle index *u* in 0..1,
    plus an outward direction — used to plant greebles ON the hull rather
    than near it."""
    sec = hull_section(t, 64)
    i = int(u * 63) % 64
    p = sec[i]
    c = np.array([0.0, t * LEN, 0.0])
    d = p - c
    d[1] = 0.0
    nrm = np.linalg.norm(d)
    return p, (d / nrm if nrm > 1e-9 else np.array([0.0, 0.0, 1.0]))


def greeble(rng, n_boxes: int) -> mk.Mesh:
    """Scatter surface clutter over the hull.

    Sizes follow a power law (`rng.power`), so a few large structures anchor
    the silhouette and hundreds of small ones fill in — a uniform size
    distribution reads as gravel and conveys no scale at all, which is the
    single most common way greebling fails.

    Everything is planted on the real hull surface and oriented to its local
    outward normal, so nothing floats and nothing sinks in.
    """
    m = mk.Mesh("greebles")
    for _ in range(n_boxes):
        t = float(np.clip(rng.beta(2.2, 1.6), 0.06, 0.985))
        u = float(rng.random())
        p, out = _surface_point(t, u)

        # Size range matters more than count. The first pass ran to 5.5% of
        # ship length per greeble, and the boxes ate the dagger silhouette
        # entirely -- the ship read as a pile of crates. Surface clutter has
        # to stay SURFACE clutter: a big one here is ~2% of the hull, most
        # are a fraction of that, and the hull's own shape still governs.
        big = float(rng.power(0.35))            # skewed towards small
        size = (0.0015 + 0.019 * big) * LEN
        w = size * float(rng.uniform(0.5, 2.6))
        d = size * float(rng.uniform(0.6, 3.4))
        h = size * float(rng.uniform(0.22, 0.85))

        # a frame whose z is the hull's outward normal and y runs aft
        fz = out
        fy = np.array([0.0, 1.0, 0.0])
        fy = fy - fz * float(np.dot(fy, fz))
        ny = np.linalg.norm(fy)
        fy = fy / ny if ny > 1e-9 else np.array([0.0, 1.0, 0.0])
        fx = np.cross(fy, fz)
        basis = np.eye(4)
        basis[:3, 0], basis[:3, 1], basis[:3, 2] = fx, fy, fz
        basis[:3, 3] = p - fz * h * 0.45        # sink it slightly in

        box = mk.box(size=(w, d, h), uv_world=True, uv_scale=1.4 / LEN)
        m.extend(box, basis)
    return m


def build_ship(rng, n_greebles: int) -> mk.Model:
    m = mk.Model("ship")
    hull, greebles, towers, engines, lights = (
        m.part('hull'), m.part('greebles'), m.part('towers'),
        m.part('engines'), m.part('lights'))

    hull.extend(build_hull())
    greebles.extend(greeble(rng, n_greebles))

    # ---- command tower: the one piece of deliberate silhouette ----
    base = 0.80
    towers.extend(mk.prism(mk.rect(0.070 * LEN, 0.115 * LEN),
                           0.030 * LEN, 0.082 * LEN,
                           uv_world=True, uv_scale=1.4 / LEN)
                  .transform(mk.translate(0, base * LEN, 0)))
    towers.extend(mk.prism(mk.rect(0.048 * LEN, 0.080 * LEN),
                           0.082 * LEN, 0.115 * LEN,
                           uv_world=True, uv_scale=1.4 / LEN)
                  .transform(mk.translate(0, base * LEN, 0)))
    # the two sensor globes that say "bridge" in one shape
    for sx in (-1, 1):
        globe = mk.revolve([(0.0, -0.016), (0.013, -0.011), (0.017, 0.0),
                            (0.013, 0.011), (0.0, 0.016)], segments=12)
        towers.extend(globe.transform(mk.scale(LEN, LEN, LEN)),
                      mk.translate(sx * 0.030 * LEN, base * LEN,
                                   0.128 * LEN))
    # a comms mast
    towers.extend(mk.revolve([(0.004, 0.0), (0.003, 0.02), (0.001, 0.045)],
                             segments=6).transform(mk.scale(LEN, LEN, LEN)),
                  mk.translate(0, base * LEN, 0.115 * LEN))

    # ---- engine bank: bells recessed into the stern ----
    for i, (sx, r) in enumerate(((-2.1, 0.026), (-0.75, 0.034),
                                 (0.75, 0.034), (2.1, 0.026))):
        bell = mk.revolve([(r * 0.55, 0.0), (r * 0.95, 0.018),
                           (r * 1.0, 0.036), (r * 0.80, 0.040)],
                          segments=14).transform(mk.scale(LEN, LEN, LEN))
        pos = mk.compose(mk.rot_x(90),
                         mk.translate(sx * 0.038 * LEN, 0.995 * LEN,
                                      -0.006 * LEN))
        engines.extend(bell, pos)
        # the glowing disc inside it — its own mesh, drawn bright
        disc = mk.revolve([(0.0, 0.0), (r * 0.88, 0.0)], segments=14) \
            .transform(mk.scale(LEN, LEN, LEN))
        lights.extend(disc, mk.compose(
            mk.rot_x(90),
            mk.translate(sx * 0.038 * LEN, 0.978 * LEN, -0.006 * LEN)))

    # ---- window strips along the flanks, as bright thin boxes ----
    for side in (-1, 1):
        for t in np.linspace(0.42, 0.94, 11):
            p, out = _surface_point(float(t), 0.0 if side > 0 else 0.5)
            lights.extend(mk.box(size=(0.004 * LEN, 0.026 * LEN,
                                       0.0035 * LEN),
                                 center=(p[0] + out[0] * 0.002 * LEN,
                                         p[1],
                                         p[2] + 0.012 * LEN)))
    return m


def build_fighter() -> mk.Mesh:
    """A small escort fighter — deliberately simple, since it is only ever
    seen at a distance and there are a lot of them."""
    m = mk.Mesh("fighter")
    body = []
    for t, w, h in ((0.0, 0.05, 0.05), (0.25, 0.20, 0.16),
                    (0.70, 0.22, 0.17), (1.0, 0.16, 0.12)):
        a = np.linspace(0, 2 * math.pi, 8, endpoint=False)
        body.append(np.stack([np.cos(a) * w, np.full(8, t * 2.4),
                              np.sin(a) * h], axis=1))
    m.extend(mk.loft(body, closed=True, cap_start=True, cap_end=True))
    for side in (-1, 1):
        m.extend(mk.prism(np.array([(0, 0.3), (0, 1.5), (0.95, 1.15),
                                    (0.75, 0.35)]), -0.03, 0.03)
                 .transform(mk.compose(mk.scale(side, 1, 1),
                                       mk.rot_x(0))))
    return m


# --------------------------------------------------------------------------
# the scene
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--greebles', type=int, default=1600,
                    help="surface clutter boxes on the capital hull "
                         "(default 1600, about 19k triangles)")
    args = ap.parse_args()

    mesh_dir, media_dir = HERE / "meshes", HERE / "media"
    for d in (mesh_dir, media_dir):
        d.mkdir(parents=True, exist_ok=True)
    for old in list(mesh_dir.glob("*.obj")) + list(media_dir.glob("*.png")):
        old.unlink()

    rng = np.random.default_rng(11)

    print("modelling...")
    ship = build_ship(rng, args.greebles)
    ship.save(mesh_dir, prefix="ship_")
    for k, part in ship.parts.items():
        print(f"  {k:9s} {len(part):6d} tris")
    print(f"  total     {sum(len(p) for p in ship.parts.values()):6d} tris")
    fighter = build_fighter()
    fighter.save_obj(mesh_dir / "fighter.obj")
    print(f"  fighter   {len(fighter):6d} tris")

    print("painting textures...")
    tk.save(tk.hull_plating(1024, 1024, seed=5, cells=14),
            media_dir / "hull.png")
    tk.save(tk.greeble_panel(512, 512, seed=6, boxes=300),
            media_dir / "greeble.png")
    tk.save(tk.metal_panel(256, 256, seed=22, bands=5,
                           base=(0.40, 0.42, 0.46)), media_dir / "dark.png")
    # Starfield. Stars are drawn as small discs with a soft falloff rather
    # than single pixels: a one-pixel star is magnified into a smeared ellipse
    # wherever the sphere's UVs stretch, which near the poles is a lot.
    # Each disc is composited into its own 11x11 patch with np.take's wrap
    # mode -- the obvious version, masking the whole image per star, spends
    # a minute on 2,200 stars for no reason.
    N, R = 1024, 5
    stars = np.zeros((N, N, 3))
    sr = np.random.default_rng(2)
    oy, ox = np.mgrid[-R:R + 1, -R:R + 1]
    dist = np.sqrt(oy ** 2 + ox ** 2)
    for _ in range(2400):
        cy, cx = int(sr.integers(0, N)), int(sr.integers(0, N))
        v = float(sr.random()) ** 2.6
        rad = 0.7 + 2.0 * v
        falloff = np.clip(1.0 - dist / rad, 0, 1) ** 1.6 * v
        if falloff.max() <= 0:
            continue
        ys = (cy + oy[:, 0]) % N
        xs = (cx + ox[0]) % N
        warm = float(sr.random()) * 0.3
        tintv = (1.0, 1.0 - warm * 0.4, 1.0 - warm)
        patch = stars[np.ix_(ys, xs)]
        stars[np.ix_(ys, xs)] = np.maximum(
            patch, falloff[..., None] * np.array(tintv))
    tk.save(stars, media_dir / "stars.png")

    print("building scene...")
    # No fog: it would fade the starfield sphere to the background colour
    # and there is nothing in vacuum to scatter light anyway.
    sb = SceneBuilder(HERE, STEM, background=(3, 4, 8),
                      tag_rgb=(200, 218, 240))
    for k in ship.parts:
        sb.register_mesh(f"ship_{k}.obj")
    sb.register_mesh("fighter.obj")
    for t in ("dark.png", "greeble.png", "hull.png", "stars.png"):
        sb.register_texture(t)

    # No emission channel exists, so 'lights' is simply a bright saturated
    # flat colour on its own mesh. It reads as emissive because the plating
    # around it is dim — contrast is the whole effect.
    SKIN = {
        'hull':     ("hull.png",    (196, 202, 212), 255),
        'greebles': ("greeble.png", (170, 176, 186), 255),
        'towers':   ("hull.png",    (182, 190, 202), 255),
        'engines':  ("dark.png",    (120, 124, 134), 255),
        'lights':   (0,             (150, 225, 255), 255),
    }
    asm = ship.assembly(anchor=(0.0, LEN * 0.55, 0.0))

    def place(x, y, z, *, size, heading=0.0, pitch=0.0, bank=0.0,
              tint=1.0, label="", pin=False):
        rig = sb.rig(pos=(x, y, z), rot=(pitch, bank, heading),
                     scale=ship.rig_scale(size, axis=1),
                     text=label, pin_text=pin)
        for key, part in asm.items():
            tex, col, alpha = SKIN[key]
            sb.add(parent=rig.id, pos=part.offset, scale=part.scale,
                   mesh=f"ship_{key}.obj", texture=tex, alpha=alpha,
                   color=col if key == 'lights' else
                   tuple(int(np.clip(c * tint, 0, 255)) for c in col))
        return rig

    # ---- starfield, as an INTERIOR sphere around the whole fleet ----
    # geometry 30 is GEO_SPHERE_INTERIOR: the inside surface of a sphere,
    # mapped so the image reads the right way round from within, and drawn
    # unlit. That last part is why it suits a starfield — a lit backdrop
    # would carry the headlight's bright patch around with the camera.
    sb.add(pos=(0, 0, 0), scale=9000, color=(255, 255, 255),
           geometry=30, texture="stars.png",
           text="Starfield — a GEO_SPHERE_INTERIOR built-in glyph, not a mesh")

    # ---- the capital ship ----
    place(0, 0, 0, size=900, heading=-12, pitch=2, bank=-4,
          label=f"Capital ship — hull, {args.greebles} procedural greebles, "
                f"towers, engines and light strips: five meshes",
          pin=True)

    # ---- two escorts, smaller and trailing ----
    place(-620, -980, -120, size=420, heading=-16, pitch=4, bank=8, tint=0.92,
          label="Escort — the same five meshes at 47% rig scale", pin=True)
    place(700, -1240, 180, size=380, heading=-6, pitch=-3, bank=-12, tint=0.96)

    # ---- a fighter screen ----
    fp = fighter.placement()
    fs = fp.scale_for_length(26.0, axis=1)
    for i in range(22):
        a = i * 0.41
        r = 330 + 190 * (i % 5)
        x = math.cos(a) * r + 180
        y = -420 - 26 * i + math.sin(a) * r * 0.5
        z = 150 + math.sin(a * 1.7) * 160
        sb.add(pos=(x, y, z), rot=(float(rng.uniform(-14, 14)),
                                   float(rng.uniform(-30, 30)),
                                   -12 + float(rng.uniform(-8, 8))),
               scale=fs, mesh="fighter.obj", texture="dark.png",
               color=(178, 184, 196),
               text="Fighter screen — 22 nodes, one 200-triangle mesh"
                    if i == 0 else "",
               pin_text=(i == 0))

    sb.finish()
    print()
    print(f"Open {HERE.name}/{STEM}_gv_node.csv in GlyphViz "
          "(meshes/ and media/ load automatically).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
