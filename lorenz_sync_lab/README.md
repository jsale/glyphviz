# Lorenz Synchronization: two chaotic systems on HCS tori

A demonstration of the **Hyperdimensional Coordinate System (HCS)**: Jeff
Sale's coordinate system in which every dimension is the real line folded onto
a circle (Dr. Art Springer's subsegment-ratio construction,
θ = 180·(v/s)/(1+|v/s|), so ±∞ is a reachable point), and dimensions nest as
circles on circles. Its subject is the synchronization of two coupled Lorenz
systems, the topic of Yan Wu's AMS talk *Synchronizability between two coupled
Lorenz systems*. Two Lorenz systems are a 6-D state (x1, y1, z1, x2, y2, z2).
Synchronization is the 3-D slice x1 = x2, y1 = y2, z1 = z2. The scene shows
that slice pulling the trajectory in, or failing to, for five controllers side
by side, in Lorenz space, on three 2-D HCS tori and as one 6-D HCS hyperglyph.

The HCS math here is a port of **hyperdims**, Jeff's interactive HCS
plotter, and the scene's checks hold GlyphViz to it; "hyperdims'" below
refers to that code.

![Five controllers, one row each: Lorenz space, three HCS tori, the 6-D HCS hyperglyph and the Lyapunov function](images/lorenz-synchronization.png)

## About this lab

This is one of four learning labs Jeff Sale built while preparing for the
Contributed Papers session of the **AMS 2026 Fall Western Sectional Meeting**
(Arizona State University, Tempe; Durham Hall L1-16, November 7, 2026), where
he presents the Hyperdimensional Coordinate System. Each lab turns the abstract
of a fellow presenter in that session into a GlyphViz scene, as a way to
understand the talk before hearing it.

| Lab | Talk |
| --- | --- |
| [`lorenz_sync_lab/`](../lorenz_sync_lab/) (this lab) | Yan Wu, *Synchronizability between two coupled Lorenz systems* |
| [`lsa_transition_lab/`](../lsa_transition_lab/) | Borgwardt & Semyonov, *An Iteration-Reducing Approach for Transitions Between Least-Squares Assignments* |
| [`conformal_fluid_lab/`](../conformal_fluid_lab/) | Paul T. Allen, *Specifying initial perfect fluid distributions in general relativity* |
| [`qudit_synthesis_lab/`](../qudit_synthesis_lab/) | Nguyen, Bregman & Nema, *Synthesis of Single-Qudit Circuits in Dimensions 3 and 5* |

The labs are study aids, not reproductions of the speakers' work. Each is built
from a short abstract alone: the models, simulations and numbers are the lab's
own, and where a lab has to guess at something the abstract doesn't give, its
README says so. Any errors are the lab's, not the speakers'. The labs live
here in the repository, not in the GlyphViz Examples Gallery, until the
speakers have given their talks.

This lab is also the one with a direct HCS connection: a torus *is* a
two-dimensional HCS, so synchronizing a pair of variables becomes landing on
the torus's diagonal loop.

## Open it

Drag `Lorenz_Sync.zip` onto the GlyphViz window; it extracts beside itself
and loads. (Or run `generate_lorenz_sync.py`, which writes the `Lorenz_Sync/`
folder, and open `Lorenz_Sync/Lorenz_Sync_gv_node.csv`.) It's a large scene,
about 217,000 nodes, and takes a few seconds to load. The Channels panel
appears; press **Space** to play. The run is 2,400 frames (24 Lorenz time
units, 80 s at 30 fps) and loops. The opening camera looks straight at the
wall. For the cleanest view, turn off **View > Show Grid**, then zoom into
one row to read the tori.

## What you're looking at

One row per controller. Every row starts from the **same** 6-D initial
condition, two systems 0.05 apart, and runs **uncoupled until t = 5.8**, so
the first stretch is identical in every row and shows chaos pulling the twins
apart. At t = 5.8 each row's controller switches on (its title light turns
from grey to colour).

| column | shows |
| --- | --- |
| **Lorenz space** | System 1 (orange) and system 2 (cyan halo), with fading comet tails over the faint attractor. The yellow cone is the error vector e = state1 − state2. Locking means the cone shrinks to nothing and the orange bead sits inside the cyan halo. |
| **x1 : x2, y1 : y2, z1 : z2** | One **HCS torus** per variable pair. The angle around the ring is system 1's value; the angle around the tube is system 2's, both with θ = 180·(v/s)/(1+\|v/s\|), exactly hyperdims' `valueToAngle`. The **white loop is the synchronization manifold** v1 = v2 (θ_ring = θ_tube). Red loops are ±∞, and the bright circles are 0. Trails are coloured by \|v1 − v2\|: red far, yellow closing, teal locked. |
| **6-D HCS** | The whole coupled state as **one hyperglyph**: six nested HCS circles in hyperdims' colours (R G B C M Y = x1 x2 y1 y2 z1 z2), each centred on its parent's chosen point in the parent's cross-section plane, exactly as hyperdims' `childFrame` does. The white leaf is the 6-D state. The white **ghost** is the nearest synchronized state (both systems at their mean, doubled into 6-D), and the yellow cone from ghost to leaf is the 6-D error. Locking means the cone vanishes and the leaf's trail lands on the ghost's. |
| **log10 V** | The Lyapunov function V = \|e\|²/2 over the whole run, same colour ramp, with a moving cursor. The vertical line marks the switch-on time. |

The torus is the HCS version of the classic "x1 vs x2" sync plot, with
infinity glued shut. Unlocked motion smears across the torus; locked motion
rides the diagonal. A torus *is* a two-dimension HCS: `verify_lorenz_sync.py`
checks that every trail point is exactly where GlyphViz's own Torus topology
would seat a child at translate (θ1, θ2). The angles in the geometry are
literally HCS angles.

![The x-coupled row (k = 10) at the end of the run, locked: every torus trail on its white loop, and the 6-D leaf's teal trail riding the ghost](images/lorenz-synchronization-locked.png)

**The 6-D hyperglyph** orders its dimensions x1, x2, y1, y2, z1, z2, so circles
1–2 are the same x torus as the 2-D glyph beside it, 3–4 the y torus, and 5–6
the z torus. In 6-D, synchronization isn't a single diagonal; it's a 3-D slice.
That's why the glyph carries the ghost: wherever the systems are, the ghost
shows where they would be if they agreed. It's a real GlyphViz node chain
(per dimension: a circle frame plus a spinner whose `rotate_z` is that
dimension's HCS angle, driven by Channels). The next circle hangs at the
spinner's rim with `rotate_x = 90`, which is hyperdims' cross-section plane.
`verify_lorenz_sync.py` drives it through the engine and checks the leaf
against a literal port of hyperdims' `geometry.ts` (worst error 6e-15). The
radius ratio is 0.7 rather than hyperdims' default 0.4, which would leave
circle 6 at 1% of circle 1. That's the same as moving its radius-ratio slider.

![The 6-D hyperglyph of the unlocked weak-x row: six nested circles, the leaf, the ghost and the long error cone between them](images/lorenz-synchronization-6d.png)

## The five rows, and how often each one locks

One run per row can't carry a success rate. In a chaotic system, moving the
switch-on time by a single 0.001 step flipped the z row from "never locks" to
"locks". So the captions come from `ensemble_lorenz_sync.py`: 200 independent
starts, 18 time units each, counted as locked if |e| < 0.1 over the last 2.
`pick_switch_time.py` chose t = 5.8 so that each row's run shows its
controller's **typical** outcome.

| row | controller | locks | still chaotic once locked? |
| --- | --- | --- | --- |
| 0 | weak x-coupling, k = 2 | 0.5% | n/a |
| 1 | x-coupling, k = 10 | 100% | yes (93%) |
| 2 | z-coupling, k = 20 | 25% (k = 2: 39%, k = 5: 44%, k = 50: 25%) | mostly |
| 3 | weak x (k = 2) + z (k = 20) | 56% | mostly |
| 4 | weak x (k = 2) + y-feedback g = 1 | 85% | **no** (0%): the feedback kills the chaos |

What the simulations suggest, and the questions they leave open:

- **z-coupling is a coin flip at every strength.** It locks in 25–44% of
  starts, and raising k from 20 to 50 doesn't help. That fits "influences
  synchronization but does not contribute directly to stabilization": z can't
  guarantee a lock, but it isn't useless. Row 2's V(t) shows it: the error
  dips toward lock, then bursts back out. Could an analysis predict a lock
  *probability*?
- **z helps once x is present.** Weak x alone locks 0.5% of the time; adding
  z = 20 makes it 56%. Is that the "interplay among the control parameters"?
- **y-feedback, in the form assumed here, tames the chaos.** Every locked
  run in row 4 had stopped switching lobes. Would a different form of
  decentralized y-feedback keep the synchronized state chaotic?
- Near threshold, x-coupling at k = 3 shows **on-off intermittency**: |e|
  falls to 0.03, then bursts back to 30. How close can a Lyapunov bound,
  which must guarantee a lock, come to a threshold like that?

## Assumptions (none of these come from the abstract)

- **Coupling forms**: bidirectional and diffusive
  (x1' += k(x2 − x1), mirrored). **y-feedback** is modeled as −g·yi on each
  system's own ẏ. This is a guess; the abstract doesn't give the form.
- σ = 10, b = 8/3, **r = 28**. The talk's "large Rayleigh numbers" may mean
  more. At r = 60, x-coupling k = 5 no longer locks. Change `RHO` at the top
  of `generate_lorenz_sync.py` to explore; the captions' rates would need
  re-running `ensemble_lorenz_sync.py`.
- HCS scale per pair is hyperdims' auto-scale (median |v| lands at 90°),
  shared by both systems so the diagonal means equality. **z is shown as
  z − 27** (the attractor's centre). Raw z only ever uses the positive half
  of the circle.
- Author at **Global Scale 1.0**. Trails and tori are Cartesian geometry, so
  a different Global Scale would resize the glyphs but not the trail layout.

## Files

| file | role |
| --- | --- |
| `generate_lorenz_sync.py` | simulation (RK4, dt = 0.001) + scene writer |
| `verify_lorenz_sync.py` | Channels join, trail-on-torus geometry, HCS-vs-engine equivalence, apply_frame cost; `--bake-dir/--frames` writes static frames for `tools/export_frame.py` |
| `ensemble_lorenz_sync.py` | the 200-start lock rates behind the captions |
| `pick_switch_time.py` | finds a switch-on time where each row shows its typical outcome |
| `time_playback.py` | headless playback timing through the real Viewport |
| `Lorenz_Sync.zip` | the scene, zipped (3.6 MB); drag it onto GlyphViz |
| `Lorenz_Sync/` | the generated scene (~19 MB node CSV, ~4 MB tracks); not committed, so unzip or regenerate it |
| `images/` | the three screenshots in this README |

## Performance notes (measured)

217k nodes and 8,550 channel bindings. Headless playback through the real
Viewport runs about 54 ms/frame (about 19 fps; the app skips the readback,
so it should be slightly faster). It ran about 25 fps before the 6-D column.
Nearly all the per-frame cost is re-emitting the live trail segments, so
`HYPER_MAX_STEP`, the trail windows (`BANDS`) and `SEG` are the knobs. Two
traps on the way there:

- **Labels on trail vertices cost 150 ms/frame.** The tag pass walks every
  node with `text` on every paint, even when only selected/pinned labels
  show. Vertices are zero-scale and unclickable, so only their carriers are
  labelled.
- **Per-vertex channel bindings cost 28 ms/frame** in `apply_frame`. Trails
  are built from short Plot segments, each with one bound `hide`, shared by
  every trail in the scene.
- Trails are densified with the integrator's true in-between states where
  samples are far apart. Otherwise fast stretches draw straight chords that
  cut through the torus and off the diagonal they are meant to follow.

## Credits

- **The talk:** Yan Wu (Georgia Southern University), *Synchronizability
  between two coupled Lorenz systems*, AMS 2026 Fall Western Sectional
  Meeting. The question this lab plays with is the talk's. The simulations,
  controller forms and lock rates here are the lab's own and aren't drawn
  from that work.
- **The Hyperdimensional Coordinate System:** Jeff Sale, built on Dr. Art
  Springer's subsegment-ratio construction. The HCS geometry is ported from
  Jeff's **hyperdims** plotter.
- **The Lorenz system:** Edward N. Lorenz, "Deterministic Nonperiodic Flow,"
  *Journal of the Atmospheric Sciences* 20 (1963).
- **Synchronized chaos:** the classic reference for coupling two chaotic
  systems into identical motion is Louis M. Pecora and Thomas L. Carroll,
  "Synchronization in Chaotic Systems," *Physical Review Letters* 64 (1990).
