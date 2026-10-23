# One Star, Three Ways to Ask for It

A GlyphViz animation illustrating Paul T. Allen, *Specifying initial perfect fluid
distributions in general relativity* (AMS contributed paper; work with David Maxwell,
building on Isenberg & Maxwell's conformal method for Lagrangian matter,
[arXiv:2106.15027](https://arxiv.org/abs/2106.15027)).

**Open:** `Conformal_Star/Conformal_Star_gv_node.csv`, then press **Space** to play
(23 s at 30 fps). The file opens on frame 0, where answer 2 is at its deepest.

## The setup

A uniform ball of dust, **momentarily at rest**, in general relativity. Before Einstein's
equations can evolve anything, the first instant has to satisfy the constraint
equations, the GR version of Gauss's law. With the star at rest and the geometry
conformally flat (`g = phi^4 x flat`), they reduce to the **Lichnerowicz equation**
for the conformal factor phi:

    Laplacian(phi) = -2 pi rho phi^5,     phi -> 1 far away

Here rho is the *physical* density. What you choose to hold fixed decides the power
of phi in the matter term, and that power decides whether the equation can be solved:

| Sheet | You fix | Matter term | Solutions | You get |
|---|---|---|---|---|
| **A** direct | the physical density rho | phi^+5 | two, then none past the fold | the density you typed in |
| **B** textbook | a seed rho~ = phi^8 rho | phi^-3 | exactly one, always | neither the density nor the matter |
| **C** densitized | rho* = phi^6 rho, the matter in each coordinate cell | phi^-1 | exactly one, always | exactly the matter you typed in |

A negative power keeps the maximum principle, which gives existence and uniqueness. The
+5 power does not. Case A also has an exact solution: the inside of the star is a cap
of a round 3-sphere, and the knob kappa = 2 pi rho R^2 / 3 equals s / (1 + s)^6.
That expression peaks at the **fold**, kappa_max = 5^5 / 6^6 = 0.0670. Below the fold the
same density has two solutions, at the fold one, and above it none.

## What you are looking at

- **Four rubber sheets.** Each one is the star's equatorial plane drawn as an
  embedding diagram, a surface of revolution whose lengths are the slice's **true
  proper lengths**. The rim is pinned at coordinate radius 3 (the star has
  coordinate radius 1). Gold means inside the star, and brighter gold means denser
  (physical density / the number you specified). The thick pale ring is the star's
  surface.
- **Answer 2, "the bag of gold"** (Wheeler's name). The same density as answer 1, but
  most of a closed 3-sphere hangs off a Schwarzschild funnel. While its throat exists
  (magenta, the first ~3 s), that throat is a minimal surface. In time-symmetric data
  a minimal surface is an apparent horizon, so this "star" is already inside a black hole.
- **One knob for all four.** kappa sweeps from 0.006 to 0.14, the same number typed
  into A, B and C. A's two answers approach each other, become identical at the fold
  (~frame 306, 10 s in), and vanish ("NO SOLUTION"). B and C keep going.
- **Backdrop plots** against kappa, with a dot for each sheet:
  1. **ADM mass** (what a distant orbit would weigh, log scale). A's curve is the fold.
  2. **Central density, got / asked.** A is exactly 1. B and C fall, to 0.33 and 0.37.
  3. **Matter in the star, got / asked.** C is exactly 1. B falls to 0.80. A's answer 1
     rises to 3.5 and answer 2 runs from x4 to x797, off the top.

At small kappa all three agree: that is the Newtonian limit, where gravity barely
stretches space. They part ways as gravity strengthens.

**Caveat:** C is a *toy in the spirit of* Isenberg-Maxwell, for dust at rest. Their
perfect-fluid system also carries momentum and entropy, and the abstract's "physically
natural hypotheses" are about that harder, general case. What the scene shows is the
mechanism: a conformally invariant matter variable gives the matter term a good sign.

## Things the scene shows that are worth knowing

- **Pressure never appears.** With the star at rest, the constraints see only the
  energy density. Whether the star can hold itself up is the evolution equations' job.
- **The bag is not a height field**, because its areal radius grows, shrinks through
  the throat, and grows again. That is why the sheets are built from meridians (TOPO_PLOT
  lines rotated about the axis) and rings (unit circles under a Plot node scaled to the
  areal radius), not from a TOPO_SURFACE. All 24 meridians share one set of
  vertex tracks.
- **C's density still drops.** You fixed the matter, not the density. Where space
  stretches (phi^6 per unit volume), the same matter is spread thinner. That is the
  honest content of "specify the fluid distribution directly": you say *how much
  matter is where*, and geometry decides how dense it is.

## Files

- `star_physics.py`: the three Lichnerowicz problems (A in closed form, B and C by
  shooting), the embedding, the delivered ratios, and the throat.
- `generate_conformal_star.py`: the scene.
- `verify_conformal_star.py`: checks case A's closed form against independent shooting
  (both roots, and none above the fold) and that B and C have one root each; checks the
  Channels join. Then, through GlyphViz's own ChannelEngine + world transforms at every
  10th frame, it checks that each drawn meridian is as long as the slice's proper radial
  length (worst 0.02%), that the rings and meridians meet, that A's sheets vanish exactly
  past the fold, and that the throat ring sits at the analytic throat.
  `--bake-dir DIR --frames ...` writes static frames for `tools/export_frame.py`.
