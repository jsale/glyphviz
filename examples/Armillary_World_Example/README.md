# The Armillary World

A teaching space built out of nested rings: an armillary sphere at the centre,
and eight concentric **topic zones** around it, each a ring carrying exhibits
that connect a piece of mathematics to something you can look at.

It is also the first scene built on the **Flat Ring** geometry (ids 33 / 34,
added 2026-08-26) — a torus whose cross-section is a rectangle instead of a
circle. A rounded torus reads as soft tubing; an instrument is made of machined
bands with square edges, and only a flat face will hold a legible texture.

Open `Armillary_World/armillary_world_gv_node.csv` (or drop the folder on the
window). 991 nodes, ~300 KB including its textures.

## What to look at

**The instrument, at the centre.** Horizon, meridian, celestial equator,
ecliptic, the two tropics and the two polar circles, plus a globe and a polar
axis. Three of the rings are *graduated*: the horizon carries an azimuth dial
marked every 5°, the meridian carries declination from -90 to +90, and the
ecliptic carries the twelve signs of the zodiac at 30° each. Those markings are
textures wrapped around flat bands — the thing the geometry exists to make
possible.

The declination numbering is worth a look if you like this sort of thing:
declination is *not* linear in the angle around the ring (it runs up to +90 and
back down), so every round value except the poles appears twice, at
`th = acos(-sin(dec))`. The generator solves for those positions rather than
spacing the numbers evenly.

**The zones, around it.** Each is a thin **rail** carrying its exhibits, a wide
textured **band** with the zone's name wrapped around it, and one **gateway** —
a pin glyph with the zone's name pinned on, sitting on the rail. The gateway is
the thing to click, or to press **F** on.

| Zone | | |
|---|---|---|
| 1 | Number & Proportion | φ, Fibonacci, the primes, π, Pascal, the golden rectangle |
| 2 | Geometry & Form | the five Platonic solids, the conic sections, the kissing number |
| 3 | Wave & Harmony | the harmonic series, octaves, fifths and fourths, standing waves, beats |
| 4 | Symmetry & Pattern | rosettes of 3-, 4-, 5-, 6-, 8- and 12-fold symmetry |
| 5 | Light & Colour | the visible spectrum, additive and subtractive primaries, refraction, the rainbow |
| 6 | Growth & Life | phyllotaxis at 137.5°, a branching tree, cell division, the nautilus, a double helix |
| 7 | Motion & Time | a working orrery, pendulums, a turning clock face, Kepler's second law |
| 8 | Scale & Cosmos | twenty-six powers of ten, from a nucleus to the observable universe |

Every node carries a label, so hovering or turning tags on (**T**) explains any
glyph. Only the ten gateway and instrument-ring labels are pinned, or the
overview would be unreadable.

Several things move: each zone rail turns at its own slow rate, the orrery's
four planets keep their real period ratios, and the clock face turns.

## Authoring notes — the three rules this scene is built on

These are the non-obvious parts, and they are the parts worth reusing.

### 1. A ring that carries children is scaled uniformly

A Flat Ring's radial width comes from `ratio` and its height from `scale_z`, so
a wide thin dial needs `scale_z != scale_x`. But children of an ordinary parent
inherit its per-axis scale, so a child of a `(S, S, Z)` ring comes out
stretched. Hence the split used throughout:

- **Rails** — uniform scale, small `ratio`. The cross-section comes out square
  (side `2 * ratio * S`), which is exactly the thin machined hoop you want
  anyway, and exhibits riding it inherit a clean uniform `S`.
- **Bands** — wide (large `ratio`), thin (small `scale_z`), textured, and
  childless.

`World.add_band()` takes the three numbers an instrument maker would use —
outer radius, radial width, thickness — and converts.

### 2. A ring's texture must be built at the ring's own aspect ratio

`u` runs once around the whole circumference and `v` across the narrow reading
face, so the canvas a ring hands its texture is enormously wide:

```
band aspect = 2 * pi * radius / (the reading face's width)
```

For a thin hoop that is 150:1 or worse. Two ways to get it wrong, both of which
this scene hit on the way here: give the image the wrong aspect (a 12:1 image on
a 180:1 band smears every letter sideways by 15×), or fix the aspect by
repeating the content more times, which is right in principle but starves each
copy of pixels — 22 copies of a name in a 1024-wide image is 46px each, i.e. a
solid white streak.

So `strip_size()` builds each image at its band's aspect, and the repeat count
follows from how many legible copies fit. **The consequence is a design
constraint, not a coding one: a ring that carries readable text has to be a wide
band, on the order of 10-20% of its own radius.** Which is exactly what a real
armillary's zodiac ring is.

Note also that the reading face differs by ring type: for a flat dial read
face-on it is the band's radial *width*; for a tall hoop read on its outer wall
it is the band's *thickness*.

### 3. Tilting a ring takes two angles, not one

`rotation_mode = EULER_XYZ` composes as `Rx·Ry·Rz` applied to a column vector,
so `rotate_z` turns *first* and cannot swing a tilt's direction around
afterwards. `aim_normal(tilt, azimuth)` solves `Rx(a)·Ry(b)·(0,0,1)` for the
wanted ring axis and returns the pair. Every tilted ring here goes through it.

Two more facts the generator relies on, both verified against
`scene.node_world_matrix` rather than assumed:

- A child of a `TOPO_TORUS` parent at `translate_y = 0, translate_z = 0` lands
  exactly on the parent's own radius; `translate_z` pushes it outward as a
  *fraction* of that radius.
- An exhibit's **local +Z points radially outward** from the world centre (the
  torus topology's outward base rotation). That is why the tree in Zone 6 grows
  outward from its ring.

## Rebuilding

```
python build_armillary_world.py [--out-dir DIR]
```

Regenerates the CSV and all eleven textures. Needs Pillow; everything else is
plain Python.

## Known limits of this first pass

- The eight gateway labels still crowd near the middle in a whole-world
  overview. They are spread around their rings (each at a different angle), but
  a nested system seen from outside projects its inner rings into a small part
  of the frame no matter what.
- The zones are *thematic*, not spatial: an exhibit's distance from the centre
  says which topic it belongs to and nothing else. A world that used radius to
  mean scale — the Zone 8 idea applied to everything — would be a different and
  probably better scene.
- Nothing is animated with Channels yet; the motion here is all `rotate_rate_z`.
