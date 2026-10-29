# Tensors, from the arrow up

A GlyphViz learning lab built from a concept, not a paper. It's for someone
comfortable with vectors, orthonormal bases and components who never made the
step up to tensors. The idea: **a tensor is a geometric thing that doesn't
care about your basis. Its components are the numbers you get when you ask it
questions with basis vectors, and the rank is how many basis vectors each
question takes.**

The lab has seven scenes, each building on the ones before:

1. **One Arrow, Many Shadows:** what vector components really are.
2. **From Vector to Tensor:** a rank-2 tensor as a machine with two slots.
3. **The Spinning Book:** the inertia tensor at work. Why a book thrown
   spinning about its middle axis flips over.
4. **Current Across the Grain:** the conductivity tensor of a crystal, in
   2-D, 3-D and a 4-D "hypercrystal". Current doesn't follow the field.
5. **Slanted Rulers:** a skewed basis splits components into upper and lower
   indices, and the metric tensor joins them again.
6. **The Cut:** the stress tensor, where the word comes from, and Mohr's
   circle.
7. **A Field of Machines:** a diffusion tensor at every point (DTI), and
   tractography.

Scenes 1-3 came first; 4-7 continue the series (2026-10-29). Scene 4 grew
from a video Jeff watched that explains tensors through crystal
conductivity, J against E, in 2-D crystals, 3-D crystals and then N-D
"hypercrystals".

## About this lab

It follows the AMS 2026 session labs ([`lorenz_sync_lab/`](../lorenz_sync_lab/),
[`lsa_transition_lab/`](../lsa_transition_lab/), …) and the paper lab
[`lorenz5d_feedback_lab/`](../lorenz5d_feedback_lab/), with one difference: it
starts from a concept rather than an abstract or a paper. So there is no
author's work to stay faithful to, only standard physics. The checks hold every
scene to the mathematics it claims (see below).

Scenes 1-4, 6 and 7 stick to **Cartesian tensors**: orthonormal bases,
related by rotations. That is everything the inertia, conductivity, stress and
diffusion tensors need. The upper/lower index distinction of general
relativity only appears once the basis is allowed to be skewed or stretched,
which is Scene 5.

## Open it

```bash
python generate_vectors.py          # -> Vectors_and_Bases/      (~2 s)
python generate_tensor.py           # -> Vector_to_Tensor/       (~3 s)
python generate_spinning_book.py    # -> Spinning_Book/          (~20 s)
python generate_crystal.py          # -> Current_Across_the_Grain/ (~10 s)
python generate_metric.py           # -> Slanted_Rulers/         (~2 s)
python generate_stress.py           # -> The_Cut/                (~3 s)
python generate_field.py            # -> A_Field_of_Machines/    (~4 s)
python verify_tensor_lab.py         # optional: every check below (~20 s)
python zip_scenes.py [SCENE ...]    # optional: the gallery's download zips
```

The scene folders are gitignored, because they regenerate in seconds. All
seven scenes are on the [Examples Gallery page](https://www.iluvdata.org/glyphviz/examples/tensors/)
as ready-made downloads.

Open the `*_gv_node.csv` in any of the scene folders. The Channels panel
appears; press **Space** to play. Every scene loops. Turn off **View > Show
Grid** for the cleanest view. The captions are pinned labels on a board that
faces the default camera, so they read best from the view the scene opens with.

| Scene | Length | Acts |
| --- | --- | --- |
| Vectors and Bases | 66 s (1,980 frames) | 3 |
| Vector to Tensor | 105 s (3,150 frames) | 5 |
| Spinning Book | 60 s (1,800 frames) | one continuous run |
| Current Across the Grain | 92 s (2,760 frames) | 3 |
| Slanted Rulers | 102 s (3,060 frames) | 5 |
| The Cut | 92 s (2,760 frames) | 3 |
| A Field of Machines | 95 s (2,850 frames) | 4 |

Colours are the same in every scene: **e1, e2, e3 = red, green, blue**
(ANTz's x/y/z convention), the vector v is **gold**, and on the boards **warm
bars are positive, cool bars negative**.

## Scene 1: One Arrow, Many Shadows

A fixed gold arrow v and an orthonormal basis that turns around it.

| Act | What happens | What to notice |
| --- | --- | --- |
| 1 (0–11 s) | The basis is the room's axes. v is rebuilt one leg at a time: v1 along e1, then v2 along e2, then v3 along e3. | v = v1 e1 + v2 e2 + v3 e3: the components are walking directions. |
| 2 (11–36 s) | The basis tours a closed loop of rotations. | The gold arrow never moves. The legs, the drop lines ("shadows") and the bars all change. **v_i = v · e_i is a question the basis asks the arrow.** |
| 3 (38–63 s) | The basis holds still and the *arrow* turns the opposite way. | The bars and the history replay Act 2 exactly. Components only know the arrow *relative to* the basis. |

The board shows the three components, a **stacked |v|² bar** that trades its
colours but never changes height (v1² + v2² + v3² is the same in every basis),
and the whole component history with a time cursor. The caption gives the
transformation law, **v′_i = R_ji v_j: one rotation matrix for the one
index.** That one R is what "rank 1" means.

## Scene 2: From Vector to Tensor

The tensor is a symmetric T with principal values 2.0, 1.2 and 0.5, turned to
an arbitrary orientation.

| Act | What happens | What to notice |
| --- | --- | --- |
| 1 (0–24 s) | A probe direction n (white) sweeps every direction. The output T n (orange) paints a trail. | **A tensor is a linear machine: direction in, vector out.** The outputs paint an ellipsoid, which *is* the tensor, with no basis anywhere. T n points along n only on the ellipsoid's own axes. |
| 2 (24–34 s) | A basis appears, with T e1, T e2, T e3 and the 3×3 grid. | **Column j of the grid is T e_j, read along e1, e2, e3: T_ij = e_i · (T e_j).** Drop lines show column 1 being read. Every component uses *two* basis vectors, one fed in and one read out. |
| 3 (34–59 s) | Scene 1's tour, again. | The ellipsoid never moves; all nine numbers change. tr T = T11 + T22 + T33 never changes (the |v|² of Scene 1). Scene 1's v rides along for comparison. |
| 4 (61–79 s) | One steady turn about e3. | **The scope:** tr T never waves, a vector component waves *once* per turn, a tensor component *twice*. An ellipsoid has no arrowhead, so it is back to itself after half a turn. Rank shows up as frequency. |
| 5 (81–105 s) | The basis turns onto the ellipsoid's own axes. | The off-diagonal bars shrink to zero and the diagonal ones become 2.0, 1.2, 0.5, the semi-axes. **Diagonalizing is choosing a basis; T never changed.** |

The board's rank ladder shows the pattern: rank 0 is one number that never
moves, rank 1 is three numbers with one R, and rank 2 is nine numbers with two
R's (T′_ij = R_ki R_lj T_kl).

## Scene 3: The Spinning Book

Three identical books (a uniform box 2.4 × 1.5 × 0.36 m, mass 1, so
I1 : I2 : I3 = 0.198 : 0.491 : 0.668 kg m²) float in free space. Each is spun
once every 3 s about one principal axis, with the same 1% nudge off it:

| Book | Spin axis | Result |
| --- | --- | --- |
| 1 | long axis (smallest I) | steady: tilts at most 2.5° |
| 2 | middle axis | flips, 7 times in 60 s, the first after about 5 s |
| 3 | thin axis (largest I) | steady: tilts at most 0.6° |

That is the **tennis-racket theorem** (the Dzhanibekov effect, after the T-handle
filmed tumbling on the space station). It comes from the inertia tensor:

- **L = I ω, and I is a tensor** (Scene 2's machine), so L and ω point the
  same way only along a principal axis. With no torque L is fixed in the room
  (the **gold** arrow). ω (**white**) wanders, and during a flip it swings
  about 30° off L (the gauge under each book).
- **Same tensor, two bases.** In the book's own basis, I is diagonal and
  constant. In the room's basis (the 3×3 grid under each book) its nine
  components swing twice per turn, the rank-2 signature from Scene 2's scope.
  Beside the grid, ω's room components swing too, yet **L = I ω, their
  product, never moves.**
- **The book carries its tensor around.** The wire ellipsoid on each book is
  its inertia tensor drawn as in Scene 2. It is fattest about the *thin* axis,
  because that is the axis the mass is farthest from.
- **Stability is the tensor's geometry.** On the right is L as the book sees
  it (body frame). It must stay on the sphere |L| = constant *and* on an
  energy surface Σ L_i²/(2 I_i) = E, so it rides the curves where they meet.
  Those curves are small loops around ±e1 and ±e3, which are stable. Between
  them runs the red **separatrix** through ±e2: two great circles, at exactly
  the energy of a pure e2 spin. Book 2 rides near it from +e2 to −e2 and back,
  and every crossing is a flip.

A real book also loses energy to flexing. That turns the long-axis spin
unstable too, and only the largest-I axis survives (Explorer 1's lesson, 1958).
The scene is the ideal rigid body.

## Scene 4: Current Across the Grain

Ohm's law for a wire is J = σE: the current runs along the field. A crystal
is not a wire. Its atoms sit in chains and layers, and charge moves easily
along a chain, less easily across one, and hardly at all between layers. So
the current leans toward the easy directions, and the one number σ has to
become a machine, **J_i = σ_ij E_j**. That is Scene 2's machine with a
physical job. The charge carriers (small beads) drift along J, not E, the
whole way through. The conductivities (2.0, 0.6 and 0.25 along, across and
between) are illustrative; a real layered conductor such as graphite has a
contrast of thousands to one.

| Act | What happens | What to notice |
| --- | --- | --- |
| 1 (0–28 s) | A 2-D crystal, facing you, with its chains 30° above x. E along x, then one full turn. | J leans 20° toward the chains. As E turns, J's tip draws an ellipse, and J lines up with E only along or straight across the chains. J_x needs E_y too: **2 × 2 = 4 numbers.** |
| 2 (28–63 s) | The sheet lies down, the layers stack, and the crystal tilts. E along x, then y, then z. Then E along the crystal's own three axes. | **Each experiment fills one column of the 3 × 3 grid** (the column is boxed). On the crystal's axes J finally follows E, 2.0, 0.6 and 0.25 times as strong. 3 conductivities + 3 tilt angles = 6 free numbers, because σ_ij = σ_ji. |
| 3 (64–92 s) | A "hypercrystal": 3-D crystals stacked along a fourth direction, drawn as its rotating shadow (colour = the 4th coordinate). | Arrows can't be drawn in 4-D, but the bars can. J_i = σ_i1 E_1 + … + σ_i4 E_4 works unchanged. The ladder counts N² numbers and N(N+1)/2 free ones for N = 1 to 5. |

The board writes J = σE as a matrix equation: J's column, then σ's grid,
then E's column. Each J_i is a **waterfall**: its row's pieces σ_ij E_j
stacked one after another, with the total marked. A gauge shows the angle
from E to J. It never reaches 90°: current never runs against the push,
because σ is positive definite.

## Scene 5: Slanted Rulers

Scene 1 had two pictures of a component: walk along the axes (the legs) or
drop a perpendicular (the shadows). In an orthonormal basis they agree. Here
the basis is a crystal's lattice vectors, which can stretch and slant, and the
two pictures come apart:

- **v^i (upper index) counts steps:** v = v^1 e1 + v^2 e2. A longer ruler
  needs fewer steps, so v^i scales *against* the basis (contravariant).
- **v_i (lower index) is a dot product:** v_i = v · e_i. A longer ruler gives
  a bigger dot product, so v_i scales *with* the basis (covariant).

| Act | What happens | What to notice |
| --- | --- | --- |
| 1 (0–15 s) | A square lattice, rulers of length 1. | Legs and shadows give the same numbers; g = identity. |
| 2 (15–35 s) | e1 stretches to twice its length, then back. | **v^1 halves, v_1 doubles.** Same arrow, opposite responses. |
| 3 (35–60 s) | e2 slants 40° toward e1 (unit rulers). | The legs walk the slanted grid; the shadows still drop at right angles. v^i ≠ v_i even with unit rulers. |
| 4 (60–82 s) | The basis wanders (stretch and slant together). | **The metric g_ij = e_i · e_j converts:** v_i = g_i1 v^1 + g_i2 v^2 (a waterfall that lands on v_i). v^1 v_1 + v^2 v_2 = \|v\|² never moves, while (v^1)² + (v^2)² swings by 1.4. |
| 5 (82–102 s) | The dual basis e^1, e^2 appears (e^1 ⟂ e2, e^1 · e1 = 1). | Walking v_1 steps of e^1 and v_2 of e^2 also reaches v. In a crystal the dual lattice is the **reciprocal lattice**; X-ray diffraction spots sit on its points (the crosses). |

General relativity is this picture with a g_ij at every point of spacetime,
changing from place to place.

## Scene 6: The Cut

Stress is where the word *tensor* comes from: Latin *tendere*, to stretch.
Woldemar Voigt gave it its modern meaning in 1898, writing about the physics
of crystals. Cut a loaded solid with a plane of normal n. The far side pulls
on the cut with a force per area, **t = σ n**, which is generally not along n.
It splits into a **pull** σ_n = t · n (red) and a **shear** τ along the cut
(cyan). Stresses are illustrative, in MPa.

| Act | What happens | What to notice |
| --- | --- | --- |
| 1 (0–40 s) | A square in plane stress (σ_xx = 3, σ_yy = 1, τ_xy = 1), with its face tractions. A cut line turns 180°, pausing at 22.5°, 67.5° and 112.5°. | (σ_n, τ) runs once round **Mohr's circle**. Turn the cut by θ and the point turns 2θ, which is rank 2's two waves per turn. τ = 0 at 22.5° and 112.5° (the principal planes: 3.41 and 0.59 MPa); the shear peaks at 45° between them. |
| 2 (42–76 s) | A cube in 3-D stress (principal 3, 1, −1.5). The cut plane (the white ring) sweeps every direction. | Each cut lands at (σ_n, \|τ\|), and every one falls **between three circles**: inside the big one, outside the two small ones (Mohr's arbelos). |
| 3 (76–92 s) | The cube turns onto the principal directions. | The shear arrows on its faces vanish and the grid goes diagonal. Metals slip where shear peaks; chalk snaps where pull peaks (twist a stick of chalk and it breaks on a 45° helix). |

## Scene 7: A Field of Machines

Diffusion is conductivity for molecules: Fick's law **J_i = −D_ij ∂c/∂x_j**
is Scene 4's machine with D in place of σ. In fibrous tissue water moves easily
along the fibres, so D is an ellipsoid, and it changes from place to place.
That makes it a **tensor field**. Diffusion MRI (DTI) measures one D per
voxel. The tissue is a **synthetic phantom, not a scan**: an arching bundle, a
vertical bundle crossing its top, a bundle running through the slice, a fluid
pocket, and grey matter. Diffusivities are typical brain values (in units of
10⁻³ mm²/s).

| Act | What happens | What to notice |
| --- | --- | --- |
| 1 (0–24 s) | One point's machine: a drop of dye (90 random walkers) spreads. | The cloud fills the ellipsoid D predicts: two standard deviations along each axis, holding about three quarters of the dye. |
| 2 (24–42 s) | The ellipsoid flies to its voxel, and the field scans in. | One D per voxel, coloured by the DTI convention: the long axis's direction (red left-right, green up-down, blue through the slice), greyed as the ellipsoid rounds. |
| 3 (42–58 s) | Two scalar maps appear on the board. | **Rank 0 from rank 2**, like tr T in Scene 2: mean diffusivity tr D / 3 (blind to the fibres: white matter and grey matter score about the same) and fractional anisotropy (it sees every bundle). |
| 4 (58–95 s) | Tractography from six seeds: step along the local long axis. | The arch tracks follow the bundle end to end. At the crossing, the ellipsoid is a flattened disc whose long axis belongs to the arch, so **both vertical tracks take a wrong turn**. The through-slice and fluid seeds stop at once. One tensor per voxel can't hold two fibre directions; newer methods fit several. |

## Checks (`verify_tensor_lab.py`)

Everything is checked through GlyphViz's own objects: the app's CSV and
Channels loaders, its ChannelEngine playing the frames, and its
`compute_world_transforms` resolving what is drawn.

- **Every scene:** the Channels join holds; frame 0 equals the static file;
  every node carries a label; Euler XYZ round-trips; the board frame is
  oriented as intended.
- **Scene 1:** the drawn basis frame is R(t) (1e-5); the three legs end on v's
  tip (1.2e-4); every drop line meets its axis at a right angle (5e-5); the bars
  are v · e_i′ (4e-5); the |v|² stack never changes height (7e-5); and Act 3's
  bars equal Act 2's exactly.
- **Scene 2:** the ellipsoid glyph's matrix B satisfies B Bᵀ = S² T², so it is
  T applied to the unit sphere. Every probe tip and every T e_j′ tip lies on it
  (3e-5). The nine bars are Rᵀ T R (7e-5), and tr T is fixed. Act 5 ends
  exactly diagonal (2.0, 1.2, 0.5). In Act 4 the dominant harmonic per turn is
  0 for tr T, 1 for v1′, and 2 for T11′ and T12′.
- **Scene 3:** the integrator conserves the room-frame L and the energy to 1e-9
  over 60 s, and halving the step changes the orientation by under 1e-7. The
  drawn books are R(t) (2e-5). The L arrow never moves, and the ω arrow is
  ω(t). The I bars are R I_body Rᵀ (1.3e-4). The *drawn* I bars times the
  *drawn* ω bars equal the *drawn* L bars (3e-4). Book 2 flips and books 1
  and 3 don't. Every polhode keeps its energy to 4e-13, and the separatrix sits
  at exactly the e2 energy.
- **Scene 4:** the lab and crystal frames are drawn as M(t) and Q(t) (8e-6).
  The E and J tips are E and σE (5e-5). The σ bars match (6e-5), and every
  J_i waterfall total equals its row times E (5e-5). The 4-D shadow is P(t)x
  (5e-3, at the 2-decimal track rounding). Over 1-s holds, 89% of the bead
  moves equal J × drift (the rest wrapped round the box). The E–J angle starts
  at 20.2° and never passes 50.2°, and on the crystal's axes J ∥ E (1e-6°).
- **Scene 5:** the lattice points are m e1 + n e2 (2e-3). The leg corner is
  v^1 e1, and the shadows drop at right angles (2e-5). The bars are v^i and
  v_i (6e-5). A ×2 stretch halves v^1 and doubles v_1 exactly. The g_ij
  waterfalls land on v_i (5e-5), and v^i v_i = |v|² holds while the naive sum
  swings 1.38. The dual basis satisfies e^i · e_j = δ, and the dual legs reach v.
- **Scene 6:** the traction, pull and shear tips are σn and its two parts
  (5e-5). The Mohr points sit on the drawn circle (4e-5) and turn exactly −2θ.
  τ = 0 on the principal cuts, and |τ| = radius at 67.5°. Every 3-D cut lies
  inside the outer circle and outside both inner ones. The ring's normal is n,
  and Act 3 ends exactly diagonal.
- **Scene 7:** every voxel's ellipsoid is D (B Bᵀ = k² D, 2e-4), coloured by
  the DTI direction code. 77% of the dye ends inside the drawn 2σ ellipsoid (a
  Gaussian gives 74%), and the cloud's long axis is within 3° of D's. Every
  track step follows the local long axis.

The small residuals are the track values' 4-decimal rounding.

## Files

| File | Role |
| --- | --- |
| `tensor_kit.py` | Node/channel writer (optionally de-duplicating identical tracks); Euler XYZ, slerp, the shared basis tour; arrows built from two Link glyphs (cylinder shaft, cone head); bars, waterfalls (a sum drawn piece by piece), captions, painted paths |
| `rigid_body.py` | Box inertia tensor, Euler's equations + quaternion orientation (RK4), polhodes, the separatrix |
| `generate_vectors.py` | Scene 1 |
| `generate_tensor.py` | Scene 2 |
| `generate_spinning_book.py` | Scene 3 |
| `generate_crystal.py` | Scene 4 |
| `generate_metric.py` | Scene 5 |
| `generate_stress.py` | Scene 6 |
| `generate_field.py` | Scene 7 |
| `verify_tensor_lab.py` | The checks above |
| `render_frames.py` | Renders Channels frames through the real Viewport to PNG (`--frames`), or times playback (`--time`) |
| `zip_scenes.py` | One `Tensors_<scene>.zip` per scene for the gallery's downloads, each checked the way a dropped zip loads |

## Performance (headless paint proxy)

| Scene | Size | Playback |
| --- | --- | --- |
| Vectors and Bases | 1.1k nodes, 88 tracks (1 MB) | ~190 fps |
| Vector to Tensor | 1.3k nodes, 237 tracks (3.3 MB) | ~150 fps |
| Spinning Book | 10.5k nodes, 648 tracks (5.8 MB) | ~65 fps |
| Current Across the Grain | 1.7k nodes, 551 tracks (8.1 MB) | ~64 fps |
| Slanted Rulers | 0.2k nodes, 167 tracks (2.8 MB) | ~200 fps |
| The Cut | 1.1k nodes, 255 tracks (2.9 MB) | ~170 fps |
| A Field of Machines | 1.7k nodes, 430 tracks (5.1 MB) | ~155 fps |

## Design notes and traps

- **Wire, not translucent, ellipsoids.** A translucent solid writes depth, and
  the arrows inside it are Links, which draw after the glyphs, so they fail the
  depth test and vanish. Every ellipsoid in the lab is wire.
- **Pin an arrow's label at its tip, not on the link.** A link labels at its
  midpoint, and arrows sharing a tail crowd their midpoints into one smear.
  `kit.arrow(show_text=1)` puts a small bead at the tip and pins the label
  there.
- **Shared tracks.** Scenes 4-7 pass `dedupe=True` to `kit.Scene`, so a hide
  window or constant used by many channels is written once. Scenes 1-3 keep
  the old writer and regenerate byte for byte.
- **Rounded tracks need rounded static values.** Beads and atoms whose tracks
  use 2 decimals must write their static position at 2 decimals too, or frame
  0 disagrees with the file.
- **Labels are fixed-pixel; the auto-framed camera is not.** The app frames the
  scene from its node positions, so making the geometry bigger only moves the
  camera back. The only lever on a crowded board is shorter text or more space
  between panels.

## Where it could go next

Scenes 4-7 built the three suggestions that closed the first round (skewed
bases, stress, a tensor field), plus the crystal-conductivity scene. Natural
next steps:

- **Rank 3 and 4.** The piezoelectric tensor (rank 3: squeeze a quartz crystal
  and it makes a voltage) and the elasticity tensor (rank 4: 81 numbers, 21
  free). Crystal symmetry would zero most of them, which ties back to Scene 4's
  counting.
- **Curvature.** Scene 5's g_ij, varying over a curved surface (a sphere, a
  saddle): parallel transport turns an arrow carried around a loop, which is
  the step from the metric to the Riemann tensor.
- **A real DTI volume** in place of Scene 7's phantom, if one with an open
  licence turns up.
