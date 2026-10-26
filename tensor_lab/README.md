# Tensors, from the arrow up

A GlyphViz learning lab built from a concept, not a paper. It's for someone
comfortable with vectors, orthonormal bases and components who never made the
step up to tensors. The idea: **a tensor is a geometric thing that doesn't
care about your basis. Its components are the numbers you get when you ask it
questions with basis vectors, and the rank is how many basis vectors each
question takes.**

The lab has three scenes, each building on the one before:

1. **One Arrow, Many Shadows:** what vector components really are.
2. **From Vector to Tensor:** a rank-2 tensor as a machine with two slots.
3. **The Spinning Book:** the inertia tensor at work. Why a book thrown
   spinning about its middle axis flips over.

## About this lab

It follows the AMS 2026 session labs ([`lorenz_sync_lab/`](../lorenz_sync_lab/),
[`lsa_transition_lab/`](../lsa_transition_lab/), …) and the paper lab
[`lorenz5d_feedback_lab/`](../lorenz5d_feedback_lab/), with one difference: it
starts from a concept rather than an abstract or a paper. So there is no
author's work to stay faithful to, only standard physics. The checks hold every
scene to the mathematics it claims (see below).

The lab sticks to **Cartesian tensors**: orthonormal bases, related by
rotations. That is everything the inertia tensor, the stress tensor or a
conductivity tensor needs. The upper/lower index distinction of general
relativity only appears once the basis is allowed to be skewed or stretched.
That is the natural next scene (see the end).

## Open it

```bash
python generate_vectors.py          # -> Vectors_and_Bases/      (~2 s)
python generate_tensor.py           # -> Vector_to_Tensor/       (~3 s)
python generate_spinning_book.py    # -> Spinning_Book/          (~20 s)
python verify_tensor_lab.py         # optional: every check below (~16 s)
python zip_scenes.py                # optional: the gallery's download zips
```

The scene folders are gitignored, because they regenerate in seconds. The
same scenes are on the [Examples Gallery page](https://www.iluvdata.org/glyphviz/examples/tensors/)
as ready-made downloads.

Open the `*_gv_node.csv` in any of the three folders. The Channels panel
appears; press **Space** to play. Every scene loops. Turn off **View > Show
Grid** for the cleanest view. The captions are pinned labels on a board that
faces the default camera, so they read best from the view the scene opens with.

| Scene | Length | Acts |
| --- | --- | --- |
| Vectors and Bases | 66 s (1,980 frames) | 3 |
| Vector to Tensor | 105 s (3,150 frames) | 5 |
| Spinning Book | 60 s (1,800 frames) | one continuous run |

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

The small residuals are the track values' 4-decimal rounding.

## Files

| File | Role |
| --- | --- |
| `tensor_kit.py` | Node/channel writer; Euler XYZ, slerp, the shared basis tour; arrows built from two Link glyphs (cylinder shaft, cone head); bars, captions, painted paths |
| `rigid_body.py` | Box inertia tensor, Euler's equations + quaternion orientation (RK4), polhodes, the separatrix |
| `generate_vectors.py` | Scene 1 |
| `generate_tensor.py` | Scene 2 |
| `generate_spinning_book.py` | Scene 3 |
| `verify_tensor_lab.py` | The checks above |
| `render_frames.py` | Renders Channels frames through the real Viewport to PNG (`--frames`), or times playback (`--time`) |
| `zip_scenes.py` | One `Tensors_<scene>.zip` per scene for the gallery's downloads, each checked the way a dropped zip loads |

## Performance (headless paint proxy)

| Scene | Size | Playback |
| --- | --- | --- |
| Vectors and Bases | 1.1k nodes, 88 tracks (1 MB) | ~190 fps |
| Vector to Tensor | 1.3k nodes, 237 tracks (3.3 MB) | ~150 fps |
| Spinning Book | 10.5k nodes, 648 tracks (5.8 MB) | ~65 fps |

## Design notes and traps

- **Wire, not translucent, ellipsoids.** A translucent solid writes depth, and
  the arrows inside it are Links, which draw after the glyphs, so they fail the
  depth test and vanish. Every ellipsoid in the lab is wire.
- **Pin an arrow's label at its tip, not on the link.** A link labels at its
  midpoint, and arrows sharing a tail crowd their midpoints into one smear.
  `kit.arrow(show_text=1)` puts a small bead at the tip and pins the label
  there.
- **Labels are fixed-pixel; the auto-framed camera is not.** The app frames the
  scene from its node positions, so making the geometry bigger only moves the
  camera back. The only lever on a crowded board is shorter text or more space
  between panels.

## Where it could go next

- **Skewed bases: upper and lower indices.** Let the basis stretch and shear,
  and a vector gets two sets of components: the walking directions (Scene 1's
  legs, contravariant) and the shadows (the drop lines, covariant). They stop
  agreeing, and the metric tensor g_ij = e_i · e_j is what converts one to the
  other. This is the real door to general relativity, and it would build
  directly on Scene 1's legs-versus-shadows picture.
- **The stress tensor** (where the word *tensor* comes from: Latin *tendere*,
  to stretch). Cut a loaded block with a plane of normal n; the force per area
  on the cut is t = σ n. It is generally not along n, and splits into pull and
  shear. Turning the cut plane sweeps Mohr's circle, and the shear vanishes on
  the principal planes. This is Scene 2's machine in engineering form.
- **A tensor field.** One ellipsoid per point (stress around a hole in a
  plate, or diffusion tensors in white matter). This is glyph-based
  visualization at its most natural.
