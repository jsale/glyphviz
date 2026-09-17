#!/usr/bin/env python3
"""
Mesh Whale Example — a humpback pod, as smooth lofted organic meshes.

WHAT THIS DEMONSTRATES
----------------------
**Smooth shading, and why it is not the same thing as a smooth model.** The
city example is all hard edges; this one is the opposite case, and both come
out of the same importer without a switch being thrown. GlyphViz works out
each edge from its own dihedral angle (`mesh_loader.DEFAULT_CREASE_ANGLE`,
40 degrees), so the whale's body — a loft whose neighbouring sections differ
by a few degrees — shades as one continuous surface, while the trailing edge
of a fluke, where two faces meet at 170 degrees, stays a crisp line.

Before 2026-09-17 this was not possible either way round: the importer welded
vertices and averaged every normal at them, so *every* imported model came out
uniformly smoothed. A cube shaded like a beach ball. The whale would have
looked roughly right and the city would not have.

**Organic form from a stack of cross-sections.** The body is one `meshkit.loft`
over 34 stations, each an ellipse whose width, height and vertical offset are
given by a profile table — the way a boat's lines plan works, and a very
compact way to describe an animal. Flippers and flukes are lofted aerofoils
with real taper and sweep; nothing here is a deformed sphere.

**One mesh, many animals.** Five whales from one 4-part model, varying only in
rig scale, orientation and colour — plus one calf at 40% scale swimming beside
its mother.

THE SCENE
---------
An underwater column: a seabed, a shaft of surface light overhead, drifting
plankton, and the pod. The water colour comes from the World row's fog, which
is what gives the depth cue that makes an underwater scene read as underwater.

Run:
    <glyphviz-env>\\python.exe mesh_creation_lab/Whale/build_whale.py
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

STEM = "mesh_whale"

# Humpback lines plan: (station along body 0..1, half-width, half-height,
# centreline z), as FRACTIONS OF LENGTH. Station 0 is the snout, 1.0 the
# fluke notch.
#
# The proportions are the whole model. A humpback is about a fifth as wide as
# it is long and slightly deeper than it is wide, with maximum girth a third
# of the way back and a long hard taper into the peduncle. The first draft of
# this table was twice as wide as that and rendered a convincing balloon --
# nothing about the lofting was wrong, the numbers were.
LINES = [
    (0.000, 0.006, 0.006,  0.000),
    (0.030, 0.034, 0.033, -0.008),
    (0.070, 0.056, 0.058, -0.016),
    (0.120, 0.074, 0.082, -0.020),
    (0.180, 0.086, 0.100, -0.018),
    (0.250, 0.094, 0.112, -0.010),
    (0.320, 0.095, 0.115,  0.000),
    (0.400, 0.091, 0.111,  0.008),
    (0.480, 0.083, 0.101,  0.013),
    (0.560, 0.072, 0.088,  0.016),
    (0.640, 0.059, 0.073,  0.017),
    (0.720, 0.046, 0.058,  0.016),
    (0.790, 0.035, 0.046,  0.014),
    (0.850, 0.026, 0.036,  0.012),
    (0.900, 0.019, 0.028,  0.010),
    (0.945, 0.014, 0.022,  0.007),
    (0.975, 0.010, 0.017,  0.004),
    (1.000, 0.006, 0.012,  0.000),
]

LENGTH = 14.0      # metres, a grown humpback


def _profile(t: float):
    """Interpolate the lines plan at station *t*."""
    ts = [row[0] for row in LINES]
    i = int(np.clip(np.searchsorted(ts, t) - 1, 0, len(LINES) - 2))
    t0, w0, h0, z0 = LINES[i]
    t1, w1, h1, z1 = LINES[i + 1]
    f = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
    f = float(np.clip(f, 0.0, 1.0))
    s = f * f * (3 - 2 * f)          # smoothstep, so stations don't kink
    return (w0 + (w1 - w0) * s, h0 + (h1 - h0) * s, z0 + (z1 - z0) * s)


def _section(t: float, segments: int, flex: float = 0.0):
    """One elliptical station, with a belly that is flatter than the back —
    a circular cross-section reads as a sausage, not as an animal."""
    w, h, zc = _profile(t)
    # a gentle swim curve down the body: the tail leads the head
    yaw = flex * math.sin(t * 2.4) * (t ** 1.6)
    a = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    x = np.cos(a) * w
    z = np.sin(a) * h
    # flatten the belly (z < 0) and round the back
    z = np.where(z < 0, z * 0.82, z * 1.05)
    y = np.full(segments, t * LENGTH)
    pts = np.stack([x * LENGTH, y, (z + zc) * LENGTH], axis=1)
    # apply the swim curve as a lateral offset
    pts[:, 0] += yaw * LENGTH
    return pts


def aerofoil(span, root, tip, sweep, thickness, twist=0.0, sections=9,
             segments=10) -> mk.Mesh:
    """A tapered, swept fin — flipper, fluke or dorsal.

    Lofting a real aerofoil section rather than extruding a flat plate is what
    stops a fin reading as cardboard: it has a rounded leading edge and a thin
    trailing one, so the light runs along it."""
    secs = []
    for i in range(sections):
        u = i / (sections - 1)
        c = root + (tip - root) * u                       # chord
        th = thickness * c * (1.0 - 0.55 * u)
        a = np.linspace(0, 2 * math.pi, segments, endpoint=False)
        # a crude but effective aerofoil: chord-wise cosine, thickness-wise
        # weighted to the front third
        cx = np.cos(a)
        cz = np.sin(a) * (0.5 + 0.5 * np.clip(1.0 - (cx + 1) / 2, 0, 1))
        pts = np.stack([cx * c / 2, np.zeros(segments), cz * th], axis=1)
        ang = math.radians(twist * u)
        ca, sa = math.cos(ang), math.sin(ang)
        rot = np.array([[ca, 0, -sa], [0, 1, 0], [sa, 0, ca]])
        pts = pts @ rot.T
        pts[:, 0] += sweep * u
        pts[:, 1] = span * u
        secs.append(pts)
    return mk.loft(secs, closed=True, cap_start=True, cap_end=True)


def build_whale() -> mk.Model:
    """Four parts: body, the pale belly/throat, flippers, flukes+dorsal."""
    m = mk.Model("whale")
    body, belly, fins, tail = (m.part('body'), m.part('belly'),
                               m.part('fins'), m.part('tail'))

    stations = np.linspace(0.0, 1.0, 34)
    body.extend(mk.loft([_section(t, 16, flex=0.05) for t in stations],
                        closed=True, cap_start=True, cap_end=True,
                        uv_u_repeat=1.0))

    # ---- the throat: pleated underside, its own mesh so it can be pale ----
    # A shell just inside the belly, from the snout to the navel.
    pleat = []
    for t in np.linspace(0.02, 0.44, 14):
        w, h, zc = _profile(t)
        a = np.linspace(math.pi * 1.18, math.pi * 1.82, 9)
        x = np.cos(a) * w * 0.97
        z = np.sin(a) * h * 0.80 + zc
        pleat.append(np.stack([x * LENGTH, np.full(9, t * LENGTH),
                               z * LENGTH], axis=1))
    belly.extend(mk.loft(pleat, closed=False, uv_u_repeat=1.0))

    # ---- flippers and flukes ---------------------------------------------
    # Both pairs are placed on the +X side only and mirrored through x = 0
    # (meshkit.mirror_pair). The first version used `rot_z(-90 * side)`, which
    # rotates instead of reflecting — so the left flipper came out swept the
    # opposite way from the right one, with its round leading edge trailing.
    # Negating an angle makes a pinwheel, not a mirror image.
    #
    # `aerofoil` spans +Y with its chord on X; rot_z(-90) turns the span
    # outboard to +X and the chord fore-aft. The snout is y=0 and the flukes
    # y=LENGTH, so a NEGATIVE sweep is the one that sweeps aft.

    # A humpback's flippers are a third of its body, and that IS the animal.
    mk.mirror_pair(fins,
                   aerofoil(span=LENGTH * 0.31, root=LENGTH * 0.085,
                            tip=LENGTH * 0.032, sweep=-LENGTH * 0.085,
                            thickness=0.20, twist=-10),
                   mk.compose(mk.rot_z(-90),
                              mk.rot_y(14),      # a little dihedral
                              mk.translate(LENGTH * 0.075, LENGTH * 0.285,
                                           -LENGTH * 0.030)))

    mk.mirror_pair(tail,
                   aerofoil(span=LENGTH * 0.205, root=LENGTH * 0.150,
                            tip=LENGTH * 0.026, sweep=-LENGTH * 0.095,
                            thickness=0.10, twist=-3),
                   mk.compose(mk.rot_z(-90), mk.rot_y(-4),
                              mk.translate(LENGTH * 0.008, LENGTH * 0.975,
                                           0.0)))

    # ---- dorsal fin: span turned up (+z), chord still fore-aft ----
    tail.extend(aerofoil(span=LENGTH * 0.030, root=LENGTH * 0.060,
                         tip=LENGTH * 0.016, sweep=-LENGTH * 0.032,
                         thickness=0.28),
                mk.compose(mk.rot_z(-90), mk.rot_y(-90),
                           mk.translate(0.0, LENGTH * 0.620, LENGTH * 0.088)))
    return m


def build_plankton(rng, n=260) -> mk.Mesh:
    """One mesh holding a whole drift of particles — a tetrahedron each.

    Deliberately ONE mesh rather than 260 nodes: they never move
    independently, and this is the cheapest way to fill water with something
    for the eye to judge distance against."""
    m = mk.Mesh("plankton")
    for _ in range(n):
        p = rng.normal(0, 1, 3) * np.array([46, 46, 20])
        s = float(rng.uniform(0.10, 0.34))
        tet = np.array([(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]) * s
        base = len(m._v)
        for v in tet:
            m.vert(tuple(np.asarray(p) + v), (0.5, 0.5))
        for a, b, c in ((0, 1, 2), (0, 3, 1), (0, 2, 3), (1, 3, 2)):
            m.tri(base + a, base + b, base + c)
    return m


def main() -> int:
    mesh_dir, media_dir = HERE / "meshes", HERE / "media"
    for d in (mesh_dir, media_dir):
        d.mkdir(parents=True, exist_ok=True)
    for old in list(mesh_dir.glob("*.obj")) + list(media_dir.glob("*.png")):
        old.unlink()

    rng = np.random.default_rng(8)

    print("modelling...")
    whale = build_whale()
    whale.save(mesh_dir, prefix="whale_")
    for k, part in whale.parts.items():
        print(f"  {k:8s} {len(part):5d} tris")
    plankton = build_plankton(rng)
    plankton.save_obj(mesh_dir / "plankton.obj")
    print(f"  plankton {len(plankton):5d} tris")

    print("painting textures...")
    # NOT texkit.scales: dimples read as a golf ball on a 14 m animal. Whale
    # skin is mottled and scarred, so this is broad low-frequency blotching
    # plus a scatter of pale rake marks.
    mott = tk.fbm(256, 256, period=5, octaves=6, seed=3)
    skin = tk.tint(mott, (0.22, 0.26, 0.31), (0.46, 0.51, 0.56))
    scar = tk.fbm(256, 512, period=30, octaves=2, seed=19)[:, ::2]
    skin = tk.overlay(skin, skin * 2.4, np.clip((scar - 0.74) * 5, 0, 1) * 0.55)
    tk.save(skin, media_dir / "skin.png")
    # barnacle-mottled pale throat: bright noise with dark speckle
    pl = tk.fbm(256, 256, period=18, octaves=5, seed=12)
    throat = tk.tint(pl, (0.62, 0.64, 0.62), (0.88, 0.89, 0.86))
    speck = tk.fbm(256, 256, period=40, octaves=2, seed=30)
    throat = tk.overlay(throat, throat * 0.55,
                        np.clip((speck - 0.72) * 4, 0, 1) * 0.8)
    tk.save(throat, media_dir / "throat.png")
    sand = tk.fbm(512, 512, period=9, octaves=6, seed=21)
    tk.save(tk.tint(sand, (0.30, 0.31, 0.27), (0.52, 0.51, 0.44)),
            media_dir / "seabed.png")
    caustic = tk.fbm(256, 256, period=7, octaves=4, seed=44)
    tk.save(tk.tint(caustic ** 2, (0.10, 0.26, 0.34), (0.55, 0.85, 0.92)),
            media_dir / "caustics.png")

    print("building scene...")
    # The fog IS the water: everything fades into the background colour with
    # distance, which is the whole depth cue an underwater scene runs on.
    sb = SceneBuilder(HERE, STEM, background=(10, 38, 56),
                      tag_rgb=(200, 235, 245), fog=(50.0, 260.0))
    for f in (*[f"whale_{k}.obj" for k in whale.parts], "plankton.obj"):
        sb.register_mesh(f)
    for t in ("caustics.png", "seabed.png", "skin.png", "throat.png"):
        sb.register_texture(t)

    SKIN = {
        'body':  ("skin.png",   (215, 232, 242)),
        'belly': ("throat.png", (235, 240, 238)),
        'fins':  ("throat.png", (215, 228, 230)),
        'tail':  ("skin.png",   (195, 215, 230)),
    }
    asm = whale.assembly(anchor=(0.0, LENGTH * 0.5, 0.0))   # rig at mid-body

    def swim(x, y, z, *, size=1.0, heading=0.0, pitch=0.0, roll=0.0,
             tint=1.0, label="", pin=False):
        rig = sb.rig(pos=(x, y, z), rot=(pitch, roll, heading),
                     scale=whale.rig_scale(LENGTH * size, axis=1),
                     text=label, pin_text=pin)
        for key, part in asm.items():
            tex, col = SKIN[key]
            sb.add(parent=rig.id, pos=part.offset, scale=part.scale,
                   mesh=f"whale_{key}.obj", texture=tex,
                   color=tuple(int(np.clip(c * tint, 0, 255)) for c in col))
        return rig

    # ---- seabed and the surface above --------------------------------------
    # Sized to the POD, not to the idea of an ocean. These slabs were 150 (300
    # units across) and 100 apart in the first pass, and since Viewport
    # auto-frames on the scene's bounding box, opening the file put the camera
    # outside the water column looking at a big blue rectangle with the whales
    # lost underneath. A scene's extents are its opening shot.
    sb.add(pos=(0, 0, -30), scale=(62, 62, 1.0), color=(210, 205, 190),
           geometry=1, texture="seabed.png",
           text="Seabed — a built-in Cube glyph")
    sb.add(pos=(0, 0, 34), scale=(62, 62, 0.5), color=(190, 235, 245),
           alpha=110, geometry=1, texture="caustics.png",
           text="Surface — the light the pod is heading for")

    # ---- plankton drift ----------------------------------------------------
    pk = plankton.placement()
    sb.add(pos=(0, 0, 4), scale=pk.radius * 0.62, color=(160, 215, 225), alpha=150,
           mesh="plankton.obj",
           text="Plankton — 260 particles in a single mesh, one node")

    # ---- the pod -----------------------------------------------------------
    swim(0, 0, 4, size=1.0, heading=14, pitch=-8,
         label="Humpback — body, throat, flippers and flukes are four meshes",
         pin=True)
    swim(-19, -13, -7, size=0.92, heading=26, pitch=-3, roll=12, tint=0.92)
    swim(21, 15, -3, size=1.06, heading=4, pitch=-12, roll=-8, tint=1.04)
    swim(-9, 27, 13, size=0.86, heading=-8, pitch=-18, roll=6, tint=0.96)
    # the calf, tucked beside its mother on her right flank
    swim(7.5, -4, -2.4, size=0.40, heading=16, pitch=-7, tint=1.1,
         label="Calf — the same four meshes at 40% rig scale", pin=True)

    sb.finish()
    print()
    print(f"Open {HERE.name}/{STEM}_gv_node.csv in GlyphViz "
          "(meshes/ and media/ load automatically).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
