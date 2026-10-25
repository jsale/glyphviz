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

The lab has two scenes, one for the fluid and one for the onset of chaos.

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

Run the ensemble once, then the two generators (about 20 s each):

```
python ensemble_shen.py              # ~70 s; writes ensemble_shen.json (tracked)
python generate_convection_cells.py  # writes Convection_Cells/
python generate_r_sweep_tower.py     # writes R_Sweep_Tower/
python verify_shen_lab.py            # optional: every check below
```

Open `Convection_Cells/Convection_Cells_gv_node.csv` or
`R_Sweep_Tower/R_Sweep_Tower_gv_node.csv`. The Channels panel appears; press
**Space** to play. Both runs are 1,600 frames (40 time units, about 53 s at 30
fps) and loop. Turn off **View > Show Grid** for the cleanest view.

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
  - sampled tower slices match their model's normalized trajectory to 5e-5.

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
| `shen_model.py` | The 3DLM / 3DLMP / 5DLM equations, critical points, Jacobians, spatial modes and fields |
| `ensemble_shen.py` → `ensemble_shen.json` | Lyapunov exponents and the coexistence probe |
| `scene_kit.py` | Node/channel writer, comet trails, board frame |
| `generate_convection_cells.py` | Scene 1 |
| `generate_r_sweep_tower.py` | Scene 2 |
| `verify_shen_lab.py` | The checks above; `--bake-dir/--frames` writes static frames for `tools/export_frame.py` |
| `time_playback.py` | Headless playback timing |

## Performance notes (measured, headless proxy)

| Scene | Size | Playback |
| --- | --- | --- |
| Convection Cells | 35k nodes, 2,805 tracks (17 MB) | ~31 fps |
| r-Sweep Tower | 152k nodes, 549 tracks | ~81 fps |

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
