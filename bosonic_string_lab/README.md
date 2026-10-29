# Bosonic string theory, through the HCS

A GlyphViz lab on the 26-dimensional bosonic string, and on what in it can be
drawn with real data. No one has measured anything in 26 dimensions: the
theory has no fermions and an unstable vacuum, so it isn't a candidate for our
universe. What it does have is exact mathematics, and the most striking piece
of that mathematics lives in its 24 vibrating directions: the **Leech
lattice**. Every number in these scenes is computed from scratch and checked.

The lab draws with Jeff Sale's **Hyperdimensional Coordinate System (HCS)**,
built on Dr. Art Springer's subsegment-ratio construction. Every dimension is
the real line folded onto a circle, θ = 180 u / (1 + |u|) with u = value /
scale, so the scale lands at 90° and ±∞ meet at 180°. Dimensions nest as
circles riding on circles. Scene 1 uses 24 nested circles; Scene 2 uses one
circle to hold an infinite tower.

1. **Kissing in 24 Dimensions** (`Leech_Kissing`, 60 s, Channels): 759 points
   of the Leech lattice, each a single point in 24-D, drawn on 24 nested HCS
   circles.
2. **The String Tower** (`String_Tower`, static): why the theory needs 26
   dimensions, its infinite tower of states on one HCS circle, and the
   Monstrous Moonshine link back to Scene 1.

## Open it

```bash
python generate_leech_kissing.py    # -> Leech_Kissing/   (~2 s)
python generate_string_tower.py     # -> String_Tower/    (~1 s)
python verify_bosonic_lab.py        # optional: every check below (~15 s)
python verify_bosonic_lab.py --full # the same, with all 196,560^2 lattice pairs (~3 min)
```

The scene folders are gitignored, because they regenerate in seconds. Open
`Leech_Kissing/Leech_Kissing_gv_node.csv` and press **Space** to play (it
loops). `String_Tower` has no animation. Turn off **View > Show Grid** for
the cleanest view. The captions are pinned labels laid out for the view each
scene opens with.

## Scene 1: Kissing in 24 Dimensions

The string vibrates in 24 directions; the other 2 of its 26 are the sheet it
sweeps out (time, and the string's own length). The Leech lattice is the most
symmetric arrangement of points in those 24 directions. Put a sphere on every
lattice point and each one touches **196,560** others, the most possible in
24-D (proved in 1979).

The 759 glyphs are one family of those 196,560 neighbours: **2 on the eight
places of a Golay octad, 0 on the other sixteen.** (The Golay code is a
24-bit error-correcting code; its 759 eight-bit words are the octads.)

- **The HCS cloud.** Every coordinate is one circle with scale s = 2, so 0
  sits at 0° and 2 at 90°. Circle k+1 rides the point chosen on circle k and
  is 0.85× smaller. A glyph's position is the leaf at the end of its 24
  circles.
- **The chain.** The 24 circles are a real node chain, one spinner per
  dimension, coloured by dimension. Its white leaf walks from octad to octad;
  at each stop it lands exactly on that octad's glyph.
- **The colours are angles to the walked octad.** Two octads sharing 4 places
  have dot product 4 × 2 × 2 = 16, half their squared length of 32, so they
  are 60° apart. **Equal spheres 60° apart just touch.** Orange = touching
  (280), blue = 75.5° (448), violet = 90° (30). Orange threads join the walked
  octad to everything it touches.
- **The places board** (right) shows the 24 coordinates as a 4 × 6 grid (the
  layout of Conway's Miracle Octad Generator), with the walked octad's eight
  places lit.

Every octad sees the same crowd (280 / 448 / 30). That sameness is symmetry:
the Mathieu group M24 carries any octad onto any other.

## Scene 2: The String Tower

- **Why 26.** Each vibration mode keeps a zero-point energy. Summed over the
  D − 2 transverse directions, 1 + 2 + 3 + … is regularized to ζ(−1) = −1/12,
  so the ground state sits at −(D − 2)/24. One quantum of vibration gives just
  D − 2 states, too few for a massive particle in D dimensions, so they must
  be massless: (D − 2)/24 = 1, D = 26.
- **An infinite tower on one circle.** Mass² = N − 1 (units of 4/α′) on one
  HCS circle with s = 1: the tachyon at −90°, massless at 0°, level 2 at 90°,
  and every higher level crowding toward ∞ at 180°. Bars give log₁₀ of the
  number of states at each level: 1, 24, 324, 3,200, … 10,914,317,934 at
  level 12. Level 2's 324 = 25 × 26 / 2 − 1 is exactly one massive spin-2
  particle in 26-D, the counting that only works in 26.
- **Moonshine.** Curl the 24 directions up on the Leech lattice and level 2
  gains the lattice's 196,560 kissing vectors: **324 + 196,560 = 196,884 =
  1 + 196,883**, the first coefficient of the j-function and the dimension of
  the Monster group's smallest representation plus one. That coincidence
  started Monstrous Moonshine; Borcherds proved the conjecture (1992) using
  this 26-D string.

## What the checks hold

`verify_bosonic_lab.py` loads each scene with the app's own loaders, plays
frames with the app's ChannelEngine, resolves transforms with
`compute_world_transforms`, and holds what is drawn to the mathematics:

- **The lattice** (`leech.py`): the Golay code's weights are 1, 759, 2576,
  759, 1; the 196,560 minimal vectors are distinct, all of squared length 32,
  all pass Conway's membership test, and no two are closer than 60°
  (`--full` checks every pair).
- **The numbers** (`string_math.py`): states per level from
  ∏(1 − qⁿ)⁻²⁴; j = E₄³/Δ computed independently (1/q + 744 + 196,884 q);
  Leech θ / Δ = j − 720.
- **Scene 1**: every glyph sits on its octad's 24-D HCS leaf (two independent
  ports of the HCS agree); the chain's leaf lands on the walked octad; every
  glyph's colour is its angle to the walked octad; exactly 280 threads show,
  each to an octad sharing 4 places; the lit cells are the octad's places.
- **Scene 2**: every bar starts on the HCS circle at θ(N − 1) and is
  BAR_UNIT × log₁₀(states) long.

## Files

| File | What it is |
| --- | --- |
| `string_kit.py` | Node/Channels writer, frames, captions, and the HCS (shared with `10d_superstring_lab/`) |
| `leech.py` | Golay code, the 196,560 minimal vectors, and their checks |
| `string_math.py` | States per level, the critical dimension, j and Moonshine |
| `generate_leech_kissing.py`, `generate_string_tower.py` | The two scenes |
| `verify_bosonic_lab.py` | Every check above |

## Credits

HCS: Jeff Sale, on Dr. Art Springer's construction (the `hyperdims`
plotter). Leech lattice construction and membership test: Conway & Sloane,
*Sphere Packings, Lattices and Groups*, ch. 4. Kissing-number bound: Levenshtein
(1979) and Odlyzko & Sloane (1979). Moonshine: Conway & Norton (1979),
Frenkel, Lepowsky & Meurman (1988), Borcherds (1992).
