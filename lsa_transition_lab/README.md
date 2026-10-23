# Transitions Between Balanced Least-Squares Assignments

A 2-D GlyphViz animation illustrating Borgwardt & Semyonov, *An Iteration-Reducing
Approach for Transitions Between Least-Squares Assignments* (AMS contributed paper).

**Open:** `LSA_Transition/LSA_Transition_gv_node.csv`, then press **Space** to play
(about 18 s at 30 fps; one step every 20 frames).

## What you are looking at

- **72 points, 4 sites.** Points are coloured by the site they are assigned to.
  Each site (solid octahedron) slides in a straight line to its target (wire
  octahedron).
- **Coloured outlines = power-diagram cells.** Every frame is an *optimal
  balanced* assignment, and every such optimum is a power diagram: each point
  goes to the site minimising `|x - s|^2 - w`. The `|x|^2` cancels between any two
  sites, so **every boundary is a straight line** — the abstract's "separation
  property". The outlines are pulled in slightly so neighbours don't overprint.
- **Bars** = current cluster sizes; the white tick is each target size.
- **Swollen points** were just reassigned. A **step** is one change of assignment.
- **Step ruler** under each panel. Both panels advance one step per tick, so the
  one needing fewer steps finishes first and waits.

| Panel | Schedule | This case |
|---|---|---|
| SEQUENTIAL | slide the sites at the old sizes (each breakpoint forces an exchange), then resize one unit at a time at the target | 21 steps (6 sliding + 15 resizing), 41 point moves |
| COMBINED | slide the sites; when a cluster that must shrink is about to hand a point to one that must grow, let that move count toward the size change instead of forcing a return move | 17 steps, 24 point moves |

Over 40 random cases (`ensemble_lsa_transition.py`), COMBINED took fewer steps in
38, the same in 2, never more; median 20% fewer steps and 27% fewer point moves.
Seed 7 is the case closest to that median.

**Caveat:** COMBINED is a *reconstruction* of the abstract's one-sentence idea
("combines progress in the linear transition of sites with a desired change in
cluster sizes"), not the authors' algorithm, which the abstract does not give.

## Things the scene shows that are worth knowing

- **The weights are not unique.** Any weights consistent with the assignment are a
  valid picture; the scene picks the ones that put each boundary as far from the
  points as possible (a small LP). A non-negative margin is also the certificate
  that the frame really is an optimal balanced assignment.
- **A site can sit outside its own cell.** The size constraint, not proximity,
  decides who gets which point, and the weights can push a cell off its site.
  It happens in ~6% of site-frames here (worst 0.5 data units). With randomly
  scattered sites it was ~38%, which is why the scene uses one site per quadrant.
- **Both schedules end at the same assignment.** For fixed sites and sizes the
  optimum is (generically) unique; the schedules differ only in the path.

## Files

- `generate_lsa_transition.py` — exact balanced LSAs (an assignment problem), both
  schedules, power-diagram weights and cells, the scene.
- `verify_lsa_transition.py` — the Channels join, and through GlyphViz's own
  ChannelEngine + world transforms that every point renders inside its cell.
  `--bake-dir DIR --frames ...` writes static frames for `tools/export_frame.py`.
- `ensemble_lsa_transition.py` — the 40-case step and move counts.
