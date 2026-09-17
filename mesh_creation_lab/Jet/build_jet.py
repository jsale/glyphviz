#!/usr/bin/env python3
"""
Mesh Jet Example — a twin-tail fighter, and a formation of them.

WHAT THIS DEMONSTRATES
----------------------
**Hard surfaces and smooth ones on the same model.** An aircraft is the
awkward case: the fuselage is a smoothly lofted body, the wings are thin
plates with knife trailing edges, and the two meet at a chine that must stay
crisp. One crease angle handles all three (`mesh_loader.DEFAULT_CREASE_ANGLE`)
— there is no per-face smoothing-group data in an OBJ and none is needed.

**Six materials, six meshes, one aircraft.** Airframe, radome, canopy glass,
intakes, exhaust cans and ordnance are separate meshes for exactly one reason:
a GlyphViz node paints its mesh in a single colour. That is also what lets the
canopy be translucent (`color_a`) while the airframe beside it is opaque, and
what lets the leader wear a different skin from its wingmen without a second
set of files.

**Orientation is the whole scene.** All six aircraft use the same rig pattern,
but the model is built nose-along-+Y so that a rig's `rotate_z` is its heading
and `rotate_x` its pitch — which makes a banking echelon turn three numbers per
aircraft instead of a matrix. Building to an axis convention on purpose is
worth more than any amount of fixing up afterwards.

THE SCENE
---------
A four-ship echelon in a banking turn, a single aircraft in clean level flight
with its parts labelled, and one 90 m below turning the other way. The
formation's stationing is drawn with Link nodes rather than meshes — a link is
already the right object for "this one is flying on that one".

Run:
    <glyphviz-env>\\python.exe mesh_creation_lab/Jet/build_jet.py
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

STEM = "mesh_jet"

LEN = 18.0          # metres, nose to tailpipe — roughly an F/A-18


# --------------------------------------------------------------------------
# parts
# --------------------------------------------------------------------------

def _superellipse(n, w, h, power=2.6):
    """A rounded-rectangle cross-section. A fuselage built from circles reads
    as a pipe; real ones are flat-sided with rounded corners, and one exponent
    covers the whole family."""
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    c, s = np.cos(a), np.sin(a)
    x = np.sign(c) * np.abs(c) ** (2.0 / power) * w
    z = np.sign(s) * np.abs(s) ** (2.0 / power) * h
    return x, z


def build_fuselage() -> mk.Mesh:
    """Lofted along +Y: a pointed radome, a wide cockpit section, a flat-sided
    mid body carrying the intakes, and a tapered tail."""
    # (station 0..1, half-width, half-height, centre z, section power)
    lines = [
        (0.000, 0.004, 0.004,  0.000, 2.0),
        (0.030, 0.022, 0.021,  0.002, 2.2),
        (0.080, 0.040, 0.038,  0.004, 2.4),
        (0.150, 0.055, 0.052,  0.008, 2.6),
        (0.230, 0.064, 0.060,  0.010, 2.8),
        (0.320, 0.070, 0.062,  0.008, 3.2),
        (0.430, 0.072, 0.060,  0.004, 3.6),
        (0.560, 0.070, 0.057,  0.000, 3.6),
        (0.680, 0.066, 0.054, -0.002, 3.4),
        (0.790, 0.062, 0.051, -0.003, 3.2),
        (0.880, 0.058, 0.049, -0.004, 3.0),
        (0.960, 0.054, 0.047, -0.004, 2.8),
        (1.000, 0.052, 0.046, -0.004, 2.8),
    ]
    secs = []
    for t, w, h, zc, pw in lines:
        x, z = _superellipse(18, w * LEN, h * LEN, pw)
        secs.append(np.stack([x, np.full(18, t * LEN), z + zc * LEN], axis=1))
    return mk.loft(secs, closed=True, cap_start=True, cap_end=True)


def wing(span, root, tip, sweep, thickness, dihedral=0.0, twist=0.0,
         sections=7, segments=12) -> mk.Mesh:
    """A swept tapered flying surface with a sharp trailing edge.

    The section is deliberately NOT symmetric fore-and-aft: the thickness
    distribution is biased to the front third, so the leading edge is round
    and the trailing edge closes to a line. That single asymmetry is most of
    what makes a wing look like a wing rather than a wedge."""
    secs = []
    for i in range(sections):
        u = i / (sections - 1)
        c = root + (tip - root) * u
        a = np.linspace(0, 2 * math.pi, segments, endpoint=False)
        cx = np.cos(a)
        chordwise = (cx + 1) / 2                       # 1 at LE, 0 at TE
        th = thickness * c * (0.25 + 0.75 * chordwise ** 0.6) * (1 - 0.4 * u)
        cz = np.sin(a) * th
        pts = np.stack([cx * c / 2 + sweep * u,
                        np.full(segments, span * u),
                        cz + span * u * math.tan(math.radians(dihedral))],
                       axis=1)
        if twist:
            ang = math.radians(twist * u)
            ca, sa = math.cos(ang), math.sin(ang)
            rot = np.array([[ca, 0, -sa], [0, 1, 0], [sa, 0, ca]])
            pts = pts @ rot.T
        secs.append(pts)
    return mk.loft(secs, closed=True, cap_start=True, cap_end=True)


def build_jet() -> mk.Model:
    m = mk.Model("jet")
    air, radome, glass, intake, exhaust, stores = (
        m.part('airframe'), m.part('radome'), m.part('canopy'),
        m.part('intake'), m.part('exhaust'), m.part('stores'))

    air.extend(build_fuselage())

    # ---- radome: its own mesh so it can be the matte black one ----
    radome.extend(mk.revolve([(0.0, 0.0), (0.30, 0.25), (0.55, 0.75),
                              (0.72, 1.45), (0.78, 2.1)], segments=16)
                  .transform(mk.rot_x(-90)))

    # ---- flying surfaces -------------------------------------------------
    # Every left/right pair is placed on the +X side ONLY and mirrored, via
    # meshkit.mirror_pair. The first version placed each side with
    # `rot_z(-90 * side)`, which ROTATES rather than reflects: the left wing
    # came out turned 180 degrees about the vertical, so it swept FORWARD
    # while the right swept aft, and its aerofoil put the round leading edge
    # at the back. A pinwheel, not an aeroplane. Negating an angle is never
    # a mirror.
    #
    # `wing` builds outboard along +Y with its chord on X; rot_z(-90) turns
    # the span to +X and the chord fore-aft. Nose is y=0 and tail y=LEN, so
    # after that turn a NEGATIVE `sweep` is the one that sweeps aft.

    # main wing: mid-mounted, swept, slight anhedral
    mk.mirror_pair(air, wing(span=LEN * 0.30, root=LEN * 0.30, tip=LEN * 0.085,
                             sweep=-LEN * 0.135, thickness=0.085,
                             dihedral=-3, twist=-2),
                   mk.compose(mk.rot_z(-90),
                              mk.translate(LEN * 0.068, LEN * 0.470,
                                           -LEN * 0.012)))

    # leading-edge extension running forward to the cockpit
    mk.mirror_pair(air, wing(span=LEN * 0.075, root=LEN * 0.30, tip=LEN * 0.20,
                             sweep=LEN * 0.055, thickness=0.05),
                   mk.compose(mk.rot_z(-90),
                              mk.translate(LEN * 0.066, LEN * 0.410,
                                           -LEN * 0.004)))

    # horizontal tails
    mk.mirror_pair(air, wing(span=LEN * 0.145, root=LEN * 0.165,
                             tip=LEN * 0.060, sweep=-LEN * 0.090,
                             thickness=0.075, dihedral=-6),
                   mk.compose(mk.rot_z(-90),
                              mk.translate(LEN * 0.052, LEN * 0.865,
                                           -LEN * 0.010)))

    # canted twin vertical tails: the two 90 degree turns stand the span up
    # at +Z, then rot_y(+18) cants it outboard toward +X. Mirroring carries
    # the cant to the other side for free, which is what the old per-side
    # sign was trying and failing to do.
    mk.mirror_pair(air, wing(span=LEN * 0.165, root=LEN * 0.175,
                             tip=LEN * 0.070, sweep=-LEN * 0.105,
                             thickness=0.070),
                   mk.compose(mk.rot_z(-90), mk.rot_y(-90), mk.rot_y(18),
                              mk.translate(LEN * 0.048, LEN * 0.760,
                                           LEN * 0.045)))

    # ---- intakes: a rectangular duct each side, under the LEX ----
    duct = mk.Mesh("duct")
    secs = []
    for t, w, h, xo in ((0.00, 0.030, 0.034, 0.072),
                        (0.35, 0.034, 0.036, 0.076),
                        (1.00, 0.030, 0.030, 0.066)):
        x, z = _superellipse(12, w * LEN, h * LEN, 3.2)
        secs.append(np.stack([x + xo * LEN,
                              np.full(12, (0.315 + t * 0.20) * LEN),
                              z - 0.016 * LEN], axis=1))
    duct.extend(mk.loft(secs, closed=True, cap_start=True, cap_end=False))
    mk.mirror_pair(intake, duct, mk.identity())

    # ---- exhaust cans ----
    can = mk.revolve([(0.44, 0.0), (0.46, 0.35), (0.40, 1.05),
                      (0.42, 1.30), (0.30, 1.34)], segments=14)
    mk.mirror_pair(exhaust, can,
                   mk.compose(mk.rot_x(-90),
                              mk.translate(LEN * 0.030, LEN * 0.985,
                                           -LEN * 0.004)))

    # ---- canopy: a separate mesh so it can be translucent ----
    cano = []
    for t, w, h in ((0.00, 0.010, 0.004), (0.12, 0.030, 0.022),
                    (0.40, 0.038, 0.030), (0.72, 0.036, 0.026),
                    (1.00, 0.020, 0.008)):
        a = np.linspace(0, math.pi, 9)
        x = np.cos(a) * w * LEN
        z = np.sin(a) * h * LEN
        y = (0.135 + t * 0.185) * LEN
        cano.append(np.stack([x, np.full(9, y), z + 0.056 * LEN], axis=1))
    glass.extend(mk.loft(cano, closed=False))

    # ---- underwing stores: a short pylon and a tank on each of two stations
    # The pylons were twice this long in the first pass, which stood the
    # tanks off far enough that a head-on view read them as landing gear.
    # Ordnance hangs close under a wing; keep it there.
    for xo, yo in ((0.120, 0.500), (0.185, 0.520)):
        station = mk.Mesh("station")
        station.extend(mk.box(size=(0.14, 1.4, 0.34),
                              center=(xo * LEN, yo * LEN, -0.028 * LEN)))
        tank = mk.revolve([(0.0, -1.5), (0.28, -1.1), (0.33, 0.9),
                           (0.20, 1.6), (0.0, 1.9)], segments=10)
        station.extend(tank, mk.compose(
            mk.rot_x(-90),
            mk.translate(xo * LEN, yo * LEN, -0.052 * LEN)))
        mk.mirror_pair(stores, station, mk.identity())
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

    print("modelling...")
    jet = build_jet()
    jet.save(mesh_dir, prefix="jet_")
    for k, part in jet.parts.items():
        print(f"  {k:9s} {len(part):5d} tris")
    print(f"  total     {sum(len(p) for p in jet.parts.values()):5d} tris")

    print("painting textures...")
    tk.save(tk.metal_panel(512, 512, seed=4, bands=7,
                           base=(0.60, 0.63, 0.67)), media_dir / "airframe.png")
    tk.save(tk.metal_panel(256, 256, seed=18, bands=3,
                           base=(0.34, 0.35, 0.38)), media_dir / "dark_metal.png")
    # burnt titanium for the exhaust cans: a hot-to-cold ramp with streaks
    ramp = np.linspace(0, 1, 256)[:, None] * np.ones((1, 256))
    burn = tk.tint(ramp, (0.30, 0.26, 0.24), (0.62, 0.48, 0.34))
    burn = tk.overlay(burn, burn * 0.6,
                      (tk.fbm(256, 256, period=28, octaves=3, seed=7) > 0.62)
                      .astype(float) * 0.6)
    tk.save(burn, media_dir / "burnt.png")
    sky = tk.fbm(512, 512, period=4, octaves=6, seed=33)
    tk.save(tk.tint(sky, (0.42, 0.55, 0.72), (0.86, 0.90, 0.96)),
            media_dir / "cloud.png")

    print("building scene...")
    sb = SceneBuilder(HERE, STEM, background=(96, 132, 180),
                      tag_rgb=(16, 24, 38), fog=(500.0, 1800.0))
    for k in jet.parts:
        sb.register_mesh(f"jet_{k}.obj")
    for t in ("airframe.png", "burnt.png", "cloud.png", "dark_metal.png"):
        sb.register_texture(t)

    SKIN = {
        'airframe': ("airframe.png",   (196, 204, 214), 255),
        'radome':   ("dark_metal.png", (120, 124, 132), 255),
        'canopy':   ("dark_metal.png", (150, 210, 235), 140),
        'intake':   ("dark_metal.png", (120, 126, 134), 255),
        'exhaust':  ("burnt.png",      (215, 205, 190), 255),
        'stores':   ("dark_metal.png", (150, 152, 158), 255),
    }
    # Rig at the aircraft's balance point, a bit ahead of mid-length: a rig
    # that sits at the nose makes a roll look like a barrel roll around the
    # radome, which is not how aeroplanes move.
    asm = jet.assembly(anchor=(0.0, LEN * 0.46, 0.0))

    def fly(x, y, z, *, heading=0.0, pitch=0.0, bank=0.0, size=LEN,
            tint=1.0, label="", pin=False):
        rig = sb.rig(pos=(x, y, z), rot=(pitch, bank, heading),
                     scale=jet.rig_scale(size, axis=1),
                     text=label, pin_text=pin)
        for key, part in asm.items():
            tex, col, alpha = SKIN[key]
            sb.add(parent=rig.id, pos=part.offset, scale=part.scale,
                   mesh=f"jet_{key}.obj", texture=tex, alpha=alpha,
                   color=tuple(int(np.clip(c * tint, 0, 255)) for c in col))
        return rig

    # ---- cloud deck, far below ----
    sb.add(pos=(0, 0, -150), scale=(600, 600, 2), color=(235, 240, 248),
           geometry=1, texture="cloud.png",
           text="Cloud deck — a built-in Cube glyph")

    # ---- the lead aircraft, clean and level ----
    lead = fly(0, 0, 0, heading=0, pitch=2, bank=0, tint=1.06,
               label="Lead — six meshes: airframe, radome, canopy, "
                     "intakes, exhaust, stores",
               pin=True)

    # ---- a four-ship echelon, stepped back and down in a banking turn ----
    wingmen = []
    for i in range(1, 5):
        bank = -26.0
        # stepped along the leader's right wing line, each lower than the last
        off = i * 1.0
        x = off * 26.0
        y = -off * 19.0
        z = -off * 6.0
        wingmen.append(fly(x, y, z, heading=-14, pitch=3, bank=bank,
                           tint=1.0 - 0.03 * i,
                           label="Echelon — same six meshes, different rig"
                           if i == 1 else ""))

    # ---- formation spacing, drawn as Link nodes ----
    # Not contrails: a contrail trails an aircraft, it does not join two of
    # them, and drawing one as a link would be a picture of something untrue.
    # What the links do say is the thing a formation actually has — who is
    # stationed on whom — so they run lead-to-wingman down the echelon.
    prev = lead
    for i, w in enumerate(wingmen):
        sb.link(prev, w, color=(210, 228, 248), alpha=70, ratio=0.018,
                geometry=27,
                text="Formation spacing — a Link node, not a mesh" if not i else "")
        prev = w

    # ---- one aircraft low and slow, banked the other way ----
    fly(-58, 62, -74, heading=38, pitch=-6, bank=34, size=LEN, tint=0.94,
        label="Same model, 90 m below and turning the other way", pin=True)

    sb.finish()
    print()
    print(f"Open {HERE.name}/{STEM}_gv_node.csv in GlyphViz "
          "(meshes/ and media/ load automatically).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
