# Radial_Spokes — the known-good scene for "which way does this glyph point?"

**What it teaches:** the direction a glyph faces is decided by **placement**, not
by `rotate_x/y/z`. The angle you want is a `translate_x`.

This is the smallest scene in which aim can be wrong, and it is the one that
keeps going wrong. If you are about to build rods, spokes, needles, rays, hands,
arrows, limbs, or anything else elongated that has to point somewhere — read the
numbers here first and calibrate against them. That is faster and more reliable
than probing with test renders, which is what this example exists to replace.

| | |
|---|---|
| `radial_spokes_gv_node.csv` | three hubs, thirty rods, 37 rows |
| `aim_report.txt` | the checker's own output, committed, so the numbers can be read without running anything |
| `build_radial_spokes.py` | the generator, and the proof — see "Verified" below |

## The scene

Three hubs, laid out along +Y so they read left to right in GlyphViz's overhead
**+Z View**. Every rod in all three is a Cylinder with
**`rotate_x = rotate_y = rotate_z = 0`**.

| hub | `topo` | what `translate_z` means |
|---|---|---|
| left | **Sphere (2)** | height **above the hub's surface** — the hub's own radius (1 × Global Scale) is already there |
| centre | **Point (7)** | the **full distance from the centre** — there is no base radius |
| right | **Cube (1)** | distance out from the **facet**; aim follows the facet normal, not the translate |

The Sphere hub is a working clock face: 12 up, 3 right, 6 down, 9 left.

## The one rule

A Sphere, Point, Torus, Ztorus or Cube parent gives every child a **base
rotation** that turns the child's local **+Z** along the outward direction at
that child's own coordinates. And **+Z is the pointing axis of every directional
geometry** — Cylinder, Cone and Pin are elongated along it; Grid, Circle, Cross
and Star face along it; a Torus or Flat Ring spins about it.

Put those two facts together and a Cylinder child of a Sphere parent with every
rotate field at zero is a spoke pointing straight out. Nothing else is needed.

```text
hub    topo = 2 (Sphere), scale 1
rod i  parent_id   = hub
       translate_x = i * 360/n     # the bearing -- THIS is the "rotation"
       translate_y = 0             # latitude 0 keeps every rod in the XY plane
       translate_z = <reach>       # Sphere: height above the surface
       rotate_x/y/z = 0            # <-- the topology aims it; do not touch
       geometry    = 19 (Cylinder)
       scale       = (thickness, thickness, half_length)
```

Under a Sphere hub, `translate_z = half_length` puts the rod's inner end exactly
flush with the hub's surface, because the rod's centre lands at
`1 + translate_z` and the rod reaches back `half_length` from its centre.

## Verified

`build_radial_spokes.py` refuses to write the CSV unless all of this holds,
re-derived through the app's own placement engine:

- every rod's world **+Z equals its own outward radial** — `+Z · radial = 1`
  to within 1e-12, on both the Sphere and the Point hub;
- bearings exactly `360/12 = 30°` apart;
- every rod level with its hub (`z` identical);
- **every rotate field in the scene is 0** — that is the lesson, so it is
  asserted rather than assumed;
- the Cube hub's six rods aim along the six facet normals.

`aim_report.txt` is the checker's output on the finished file. The payload is
the `AIM` section: twelve unit vectors, 30° apart, all in the XY plane.

```text
  parent 2 (Sphere (KML)) aims its 12 directional children -- all at the aim placement gave them
      id 3      +Z (+1.000, +0.000, +0.000)  Cylinder
      id 4      +Z (+0.866, +0.500, +0.000)  Cylinder
      id 5      +Z (+0.500, +0.866, +0.000)  Cylinder
      ...
```

**Read that section instead of rendering.** `python code/gv_extents.py
your_scene_gv_node.csv` prints it for any scene, so "are my spokes pointing
outward?" is a number you can check, not something to infer from a picture.

## Which way is clockwise

Longitude runs **counter-clockwise seen from +Z** (0 → +X, 90 → +Y), so a
clockwise dial needs *decreasing* longitude:

```text
translate_x = (lon12 - 30 * hour) mod 360
```

`lon12` is the longitude you want 12 o'clock to face, and it comes from **how
the scene will be viewed**, because "up" is a camera property and not a world
one. GlyphViz's overhead **+Z View** (azimuth 0, elevation 89) puts **−X** at
the top of the screen and **+Y** at the right, so `lon12 = 180` gives 12 up,
3 right, 6 down, 9 left. That is measured off a real render, not assumed — and
it is also why the three hubs in this scene are spaced along **Y**.

## The mistake this replaces

The failure is reaching for `rotate_*` to aim a rod. It is worth knowing exactly
what it looks like, because it fails *silently* — positions come out right and
bodies come out wrong, which no position check can see.

**Hand-posed under a Cartesian hub.** Twelve rods placed at computed x/y around
a `topo = 0` parent, each aimed with `rotate_x = 90` and the clock angle in
`rotate_z`. Measured, all twelve end up with the **identical** world
`+Z (0.000, −1.000, 0.000)` — an intended starburst rendering as a flat stacked
fan. The checker reports this one as a problem:

```text
  ! 1 set of glyphs was rotated by hand and all ended up pointing the same way
      parent 1 (topo None): all 12 directional children point (+0.000, -1.000, +0.000)
      while their positions fan out over 180 deg around it
```

**Belt and braces.** The right topology *and* a hand-posed rotation, which is
the more tempting version because the placement is correct. Rotations compose
**on top of** the base rotation rather than replacing it, so every rod comes out
a constant 90° off its own radial. The checker states the deflection in the AIM
section — it does not call it a fault, because a deliberate lean is authored the
same way and cannot be told apart (`Armillary_World` lays its pins along their
rings at `rotate_x = -90` on purpose).

If you meant it to point outward: set every rotate field to 0 and put the angle
in `translate_x`.

## See also

`SKILL.md` rule 12 · `references/topologies.md` → "Pointing a glyph: use
placement, not rotation" (per-topology aim table and the geometry-axis table) ·
`references/troubleshooting.md` entry 15.

Regenerate with `python build_radial_spokes.py`. Never hand-edit the CSV.
