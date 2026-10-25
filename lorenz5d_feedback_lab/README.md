# Nonlinear feedback in a 5-D Lorenz model

A GlyphViz learning lab built from one published paper: Bo-Wen Shen, "Nonlinear
Feedback in a Five-Dimensional Lorenz Model," *Journal of the Atmospheric
Sciences* 71, 1701–1723 (2014), doi:10.1175/JAS-D-13-0223.1 (open access).

Lorenz's famous 1963 model shrinks a layer of fluid heated from below to three
numbers. **X** is how fast the convection rolls turn, **Y** is the warm-side /
cool-side temperature contrast, and **Z** is how far the rolls have flattened
the layer's vertical temperature profile. Shen adds two finer vertical
temperature patterns, **Y1** and **Z1**. You might expect more detail to mean
more chaos. Instead the extra modes **calm the flow**: the onset of chaos moves
from r ≈ 24.7 to r ≈ 43–46. The cause is one term, **−XY1** in dZ/dτ. It drains
the M3 pattern into the M6 pattern, which is strongly damped. The paper calls
this extending the model's nonlinear feedback loop. It also shows that replacing
−XY1 with an eddy-damping term −qX² (the "3DLMP") reproduces most of the effect,
which is what weather models call a parameterization.

The lab has four scenes:

1. **Two Convection Cells:** the fluid itself.
2. **The r-Sweep Tower:** where each model turns chaotic.
3. **Inside the Feedback Loop:** the paper's Fig. 1 as a live graph, beside the
   whole state drawn as one Hyperdimensional Coordinate System (HCS)
   hyperglyph.
4. **The Stability Landscape:** where the steady roll holds, over the whole
   (σ, r) plane.

## About this lab

This lab is a test of a broader idea: start from a research paper rather than a
talk abstract, and turn it into a GlyphViz scene that helps a reader understand
it. It follows the four AMS 2026 session labs ([`lorenz_sync_lab/`](../lorenz_sync_lab/),
[`lsa_transition_lab/`](../lsa_transition_lab/),
[`conformal_fluid_lab/`](../conformal_fluid_lab/),
[`qudit_synthesis_lab/`](../qudit_synthesis_lab/)). Unlike those, it had the
whole paper to work from, so its models are the paper's own equations, and its
checks hold them to the paper's published numbers. The simulations, the ensemble
and its one extra finding (the coexistence window below) are the lab's own. Any
errors are the lab's, not the author's.

## Open it

The two ensemble results are tracked in the repo, so the generators run
straight away (about 20 s each). Re-run the ensembles only to change them:

```bash
python ensemble_shen.py                  # ~70 s  -> ensemble_shen.json
python ensemble_shen.py --sigma-sweep    # ~3 min -> ensemble_sigma.json
python generate_convection_cells.py      # -> Convection_Cells/
python generate_r_sweep_tower.py         # -> R_Sweep_Tower/
python generate_feedback_loop.py         # -> Feedback_Loop/
python generate_stability_landscape.py   # -> Stability_Landscape/
python verify_shen_lab.py                # optional: every check below
```

Open the `*_gv_node.csv` in any of the four folders. For the three animated
scenes, the Channels panel appears; press **Space** to play. Each run is 1,600
frames (40 time units, about 53 s at 30 fps) and loops. The Stability
Landscape is static. Turn off **View > Show Grid** for the cleanest view.

## Scene 1: Two Convection Cells

The fluid behind the letters, rebuilt from the mode amplitudes with the paper's
own spatial modes (eqs. 5–9). Two heating levels, r = 25 and r = 35, and at each
the 3DLM above the 5DLM. Every run starts from rest with the paper's nudge,
Y = 1.

| Piece | Shows |
| --- | --- |
| **Fluid cell** | Temperature (red hot, blue cool) between the hot lower plate and the cool upper plate: conduction plus the mode sum Y·M2 − Z·M3 + Y1·M5 − Z1·M6. The domain is one horizontal wavelength, so it holds two counter-rotating rolls. White beads are fluid parcels, advected by the model's own velocity field (from ψ = C1·X·M1) along the roll's streamlines. **A roll reversal, where the beads turn around, is a lobe switch of the butterfly.** |
| **dZ/dτ budget** | The paper's Fig. 6: forcing XY (white) against damping bZ (orange) and, in the 5DLM only, the new sink XY1 (blue). Beside it, a live tug-of-war: XY pulls up, bZ and XY1 pull down. Balanced bars mean a steady roll. |
| **Phase panel** | The paper's Fig. 3: Y/Yc against Z/Zc for both models, each normalized by its own critical point, so both models' steady rolls sit at (±1, 1). |
| **Mode atlas** | The four temperature patterns, as each enters for a positive amplitude. The last two exist only in the 5DLM. |

What it shows: at r = 25 the 3DLM's rolls reverse 9 times in 40 time units, and
at r = 35, 28 times. The 5DLM settles to a steady roll at both (Y/Yc → −1.000),
with the warm plume rising up the middle of the cell.

## Scene 2: The r-Sweep Tower

One tower per model: 3DLM, 3DLMP (q = 0.17) and 5DLM. Each tower is a stack of
61 phase-portrait slices, one per r = 20, 20.5, …, 50. Each slice is the run
from Y = 1 over 40 time units in the plane (Y/Yc across, Z/Zc depth), drawn dim
early and bright late, with a bead riding it during playback.

- From the front it reads as a **bifurcation diagram**: below the onset of
  chaos, each slice ends in a bright dot at a steady roll, so the tower is a
  thin needle. Above it, each slice is a band. Orbit the camera to see the
  bands as butterflies.
- Beside each tower is the paper's **Fig. 7 on its side**: one bar per slice for
  the ensemble Lyapunov exponent (blue < 0 stable, red > 0 chaotic).
- A **white line** marks the linear r_c (the steady roll loses stability), a
  **gold line** the ensemble onset (random starts find chaos), and a **gold
  bracket** the window between them.

The 3DLMP is normalized by the 3DLM's critical point, as in the paper, so its
steady rolls sit at ±1.098 (Fig. 9a). The parameterization buys the 5DLM's
stability at the price of a roughly 10% shift in the steady state.

## Scene 3: Inside the Feedback Loop

Four rows, all started from Y = 1:

| Row | Loop | Outcome |
| --- | --- | --- |
| 3DLM, r = 25 | the trunk only (M2 ↔ M3) | chaotic |
| 4DLM, r = 25 | M5 without M6: half a branch | runs away toward infinity |
| 5DLM, r = 25 | the full loop | steady |
| 5DLM, r = 43.5 | the full loop, heated harder | chaotic again |

**The loop (left).** Each mode is a tile of its spatial pattern, ordered coarse
to fine. A downscale transfer runs rightward along an arc above the tiles, and
an upscale transfer runs leftward along an arc below. These are the paper's
Fig. 1 arrows, and each arc is one nonlinear term of the model. The linear heat
engine, rX and σY, joins M1 and M2. The stub under each tile is that mode's
damping.

A bead on every arc and stub is a live meter:

- **Size** is the term's magnitude.
- **Colour** is what the term does to the mode it feeds: warm if it amplifies
  that mode (the term and the amplitude share a sign), cool if it damps it.

The paper's negative feedback is the −XY1 bead running cool. The bar under each
tile is the mode's amplitude, compressed with the HCS map: its tick is the
steady value and its end is infinity.

**The state, as one HCS hyperglyph (right).** A 5-D model's state at any
instant is one point (X, Y, Z, Y1, Z1) in phase space. The hyperglyph draws that
point as nested circles, one per variable, ordered coarse to fine like the
cascade itself. The colours are R G B C M for X Y Z Y1 Z1, and the leaf is the
state. Each variable is scaled by its own critical value (the paper's
normalization), and the HCS map θ = 180·u/(1+|u|) puts u = ±1 at exactly ±90°.
So **a steady roll is every circle parked at a quarter turn**. The 5DLM at
r = 25 settles at exactly (−90°, −90°, 90°, −90°, 90°), and the ghost leaves
mark the two steady rolls. A 3-D model is visibly a glyph with two fewer
circles.

**Where the HCS earns its keep: the 4DLM.** The paper notes in passing that the
4DLM (M5 added, M6 not) has no real steady state for r > d_o + 1 and doesn't
conserve energy. Run from the paper's start, it runs away: |state| passes 1,000
by τ = 1.19 at r = 25, a time that holds steady as the step size shrinks. An
ordinary plot can't draw a state heading to infinity. On the HCS, infinity is
the point at 180° on every circle, so the leaf flies out to the red "all
infinite" ghost and the bars hit their ends. The run is held once |state|
passes 10⁴, because past that the integration is stiff and the numbers mean
nothing. This row turns the paper's remark into something you can watch:
adding half of a feedback loop is worse than adding none.

## Scene 4: The Stability Landscape

For each model (3DLM, 3DLMP, 5DLM), the steady roll is linearized (the paper's
appendix C), and its largest Re(λ) is drawn as relief over σ = 5…25 (the
Prandtl number) and r = 20…55. Blue valleys are where the roll is stable, red
where it isn't. The panels lie back like terrain, with σ across and r running
away from the viewer. Each panel shows:

- a **gold line** where Re(λ) = 0, the linear r_c(σ) curve of Fig. 10a;
- **white dots** for the ensemble onset at the paper's σ values (Fig. 10a's
  solid circles), from `ensemble_shen.py --sigma-sweep`;
- on the 3DLM panel, **crosses** at Lorenz's own closed form,
  r_c = σ(σ + b + 3)/(σ − b − 1), as a check;
- a faint line at σ = 10, the value the other scenes use.

Below the panels, Fig. 10a itself: all three r_c(σ) curves with their dots on
one flat panel. The curves reproduce the paper's: the 5DLM's r_c bottoms out at
38.06 near σ = 16.5, and the 3DLMP's at 40.40 near σ = 13. Every dot sits on
the stable side of its gold line, which is the coexistence window below,
present at every σ.

## What the ensemble found

`ensemble_shen.py` measures the leading Lyapunov exponent for 64 random starts
at each r, for all three models. A second probe starts a hair (10⁻³) off the
steady roll.

| Model | Ensemble onset (here) | Paper, ensemble | Linear r_c (here = paper) | Coexistence window |
| --- | --- | --- | --- | --- |
| 3DLM | 24.0 | 23.7 | 24.74 | 24.0 – 24.74 |
| 3DLMP, q = 0.17 | 42.0 | 41.8 | 43.54 | 42.0 – 43.54 |
| 5DLM | 43.0 | 42.9 | 45.94 | 43.0 – 45.94 |

**The coexistence window is the lab's own finding, not the paper's.** Inside it,
the steady roll is still linearly stable, and starts placed near it stay there,
yet nearly every random start falls onto the chaotic attractor instead. This is
the classic Lorenz picture (24.06–24.74 for the 3DLM), and it explains why the
paper's ensemble r_c for the 5DLM (42.9) sits below its linear r_c (45.94).

The σ sweep (32 starts per r) repeats this at the paper's other Prandtl numbers.
The onsets match Fig. 10a's dots. The window appears at every σ for all three
models, with the steady roll holding a 10⁻³ kick throughout it, and it widens
as σ grows:

| σ | 3DLM onset / linear r_c | 3DLMP | 5DLM |
| --- | --- | --- | --- |
| 10 | 24.0 / 24.74 | 42.0 / 43.54 | 43.0 / 45.94 |
| 13 | 25.5 / 26.00 | 40.0 / 40.42 | 37.5 / 39.37 |
| 16 | 27.0 / 28.11 | 40.0 / 41.26 | 36.0 / 38.08 |
| 19 | 28.5 / 30.57 | 40.0 / 43.40 | 36.0 / 38.43 |
| 22 | 30.0 / 33.20 | 40.5 / 46.15 | 36.5 / 39.50 |
| 25 | 31.5 / 35.94 | 42.0 / 49.20 | 37.5 / 40.93 |

## Checks (`verify_shen_lab.py`)

- **Model against the paper:** the critical points solve the equations and the
  two forms of eq. 19c agree; the linear r_c values are 24.74 / 43.54 / 45.94
  (Fig. 10b); the 3DLMP settles at X/X3d = −1.098 (Fig. 9a); the energy budget
  of appendix A (eqs. A5 and A9) holds to 6e-16.
- **Warm rises:** at the steady roll, upward velocity matches the sideways part
  of the temperature field (correlation 0.91), and the heat flux ⟨wθ⟩ is
  positive. This checks the sign conventions linking ψ and θ.
- **Scenes, through GlyphViz's own objects:**
  - the Channels join holds, and frame 0 equals the static file;
  - the board frame is oriented as intended;
  - every heat-map lattice is complete, with no holes;
  - each vertex's colour is within 1/255 of conduction plus the mode sum at
    sampled frames;
  - the 72 beads stay on their streamlines (|M1| drift 2e-4);
  - sampled tower slices match their model's normalized trajectory to 5e-5;
  - the vectorized HCS chain equals a literal port of hyperdims' geometry.ts,
    and each channel-driven hyperglyph leaf lands on it (1.4e-6);
  - the 4DLM's escape time is the same at two step sizes;
  - landscape heights equal Re(λ), the gold contour has |Re(λ)| ≤ 7e-15, the
    eigenvalue r_c equals Lorenz's closed form to 1e-13, and every ensemble
    dot lies below its linear r_c.

## Assumptions and differences from the paper

- **Ensemble size:** 64 starts per r, τ = 250 (50 discarded), dτ = 0.01. The
  paper used 10,000 starts, τ = 1000 and dτ = 10⁻⁴. The onsets agree to within
  one grid step (0.5 in r).
- **Spread of the random starts:** the paper doesn't give it; this lab uses unit
  Gaussian noise about the origin.
- **Units:** H = 1 and temperatures in units of ΔT, with C2 = ΔT/(π r) from
  eq. 9. Parcel velocities are ψ's, divided by the τ scaling.
- **Colour scale:** the cells colour the *total* temperature, so they look like
  real convection. The mode atlas shows the perturbation patterns themselves.

## Files

| File | Role |
| --- | --- |
| `shen_model.py` | The 3DLM / 3DLMP / 4DLM / 5DLM equations, critical points, Jacobians, linear r_c, spatial modes and fields |
| `ensemble_shen.py` → `ensemble_shen.json`, `ensemble_sigma.json` | Lyapunov exponents and the coexistence probe, at σ = 10 and across the paper's σ values |
| `hcs.py` | The HCS map and nested-circle chain, ported from hyperdims |
| `scene_kit.py` | Node/channel writer, comet trails, board frame |
| `generate_convection_cells.py` | Scene 1 |
| `generate_r_sweep_tower.py` | Scene 2 |
| `generate_feedback_loop.py` | Scene 3 |
| `generate_stability_landscape.py` | Scene 4 (static) |
| `verify_shen_lab.py` | The checks above; `--bake-dir/--frames` writes static frames for `tools/export_frame.py` |
| `time_playback.py` | Headless playback timing |

## Performance notes (measured, headless proxy)

| Scene | Size | Playback |
| --- | --- | --- |
| Convection Cells | 35k nodes, 2,805 tracks (17 MB) | ~31 fps |
| r-Sweep Tower | 152k nodes, 549 tracks | ~81 fps |
| Feedback Loop | 46k nodes, 504 tracks | ~43 fps |
| Stability Landscape | 9k nodes, static | n/a |

The cells' cost is the four channel-bound heat-map Surfaces, which re-emit every
frame rather than replaying a display list. The temperature field is
mirror-symmetric across the cell (cos lx), so mirrored vertices share one
channel, which halves the tracks. The plate rows never change and aren't bound.
Stable tower slices are cut once they converge, so a needle doesn't pile up
hundreds of vertices on one point.

## Credits

- **The paper:** Bo-Wen Shen, "Nonlinear Feedback in a Five-Dimensional Lorenz
  Model," *J. Atmos. Sci.* 71 (2014) 1701–1723. Equations, modes, critical
  points, normalizations and the figures the scenes re-draw are all from it.
- **The Lorenz system:** Edward N. Lorenz, "Deterministic Nonperiodic Flow,"
  *J. Atmos. Sci.* 20 (1963), after B. Saltzman (1962).
- **The Hyperdimensional Coordinate System:** Jeff Sale, built on Dr. Art
  Springer's subsegment-ratio construction. The HCS geometry is ported from
  Jeff's **hyperdims** plotter.
