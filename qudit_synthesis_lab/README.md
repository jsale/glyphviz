# Qudit Circuit Synthesis: Two Scenes

Two GlyphViz animations illustrating Nguyen, Bregman & Nema, *Synthesis of Single-Qudit
Circuits in Dimensions 3 and 5* (AMS contributed paper). Their starting point is
Gustafson et al., *Synthesis of Single Qutrit Circuits from Clifford+R*
([arXiv:2503.20203](https://arxiv.org/abs/2503.20203)).

A quantum computer can run only a small menu of gates fault-tolerantly: the **Clifford**
gates, plus one expensive non-Clifford gate (**T**, or for qutrits also **R** = diag(1, 1, -1)),
made by magic-state distillation. Every other gate must be approximated by a word in that
menu, and the cost is the number of non-Clifford gates. The talk's headline: that number
grows only like **log(1/ε)**. The two scenes show *how* a compiler searches, and *why* the
cost scales that way.

| Scene | Open | Plays |
|---|---|---|
| **Cyclotomic Search**: how a ququint (d = 5) Clifford+T compiler finds one gate entry | `Cyclotomic_Search/Cyclotomic_Search_gv_node.csv` | 21 s |
| **Reachable Net**: every qubit / qutrit state reachable with k non-Clifford gates | `Reachable_Net/Reachable_Net_gv_node.csv` | 26 s |

Press **Space** to play. Both open zoomed out; scroll in on the panel you are reading.

## 1. Cyclotomic Search

### The idea

Every entry of a gate the ququint Clifford+T menu can build has the form **u / √5^k**, where
u = a + bζ + cζ² + dζ³ with integer a, b, c, d and ζ = e^(2πi/5). (The Hadamard brings the
1/√5; everything else is fifth roots of unity; √5 = -1 - 2ζ² - 2ζ³ is itself in the ring.)
So the candidate entries form a **4-D lattice**, and k, the **level**, is how many times the
circuit divides by √5. Its length grows with k.

Each u also has a Galois **twin**: the same four integers with ζ replaced by ζ² = e^(4πi/5).
The column of a unitary must be a unit vector, and that equation, being made of integers,
holds for the twin too. So **a legal entry needs its twin inside the unit disc as well**.
This hidden constraint is what makes the search a lattice problem and not just rounding.

To approximate the phase e^(iθ) to column error ε, the entry must be near the target **and**
almost exactly unit length, because the rest of the column carries the shortfall
1 - |entry|². That region is a thin **sliver** of the disc: chord ≈ 2ε, depth ε²/2, area
(2/3)ε³. Each level makes the lattice 25× denser (5× in each of its two complex planes).
So the level at which a point first lands in the sliver grows like 3 log₂₅(1/ε), which is
**2.15 levels per decade of precision**.

### What you are looking at

- **Back wall, left: every legal entry** (twin inside its disc too), level by level:
  11 at level 0 (0 and the ten ±ζʲ), 111 at level 1, 2251 at level 2. That's close to the
  lattice-volume prediction π²·25^k / 2.795 (2207 at level 2).
- **Front: the zoom column.** Its floor is the window around the target e^i (θ = 1 rad),
  magnified 9× relative to the disc on the wall. Its **height is the twin's size r through
  the HCS map r/(1+r)**, the
  compactification from Jeff Sale's hyperdimensional coordinate system (after Springer's
  construction). It puts the **ceiling r = 1 at exactly half height and r = ∞ at the top**,
  so the whole unbounded lattice fits in a finite column. Bright points are under the
  ceiling (legal); dim points float above it. The **gold slot** is the sliver extruded up
  to the ceiling. A candidate must be inside the slot *and* under the ceiling.
- **The search:** level 0 puts 2 points in the window, neither legal. Level 1 adds 55, one
  legal, none in the slot. Level 2 adds 1399. Only 22 of the window's 1456 points are under
  the ceiling, and **2 land in the slot** (errors 0.051 and 0.077).
- **Twin plane:** the two candidates' twins, inside their unit disc.
- **The column, completed exactly:** for u = 2 + 2ζ + 2ζ² - 2ζ³ at level 2,
  25 - |u|² = (1 - 2g)² with g = ζ + ζ⁴. The column (u, 1 - 2g, 0, 0, 0)/5 is an exact
  unit vector: 0.9978 + 0.0022 = 1, and in the twin world 0.2822 + 0.7178 = 1. Compiling
  that column into Clifford+T gates is the next stage, not drawn.
- **Ladder** (`ensemble_cyclotomic_ladder.py`, 100 random targets per ε): mean level needed
  against log precision. For ε ≤ 0.03 the measured slope is **2.28 levels per decade**,
  against the predicted 2.15 (teal). At coarse ε the means fall below the line: a root of
  unity at level 0 is often already close enough (~32% of targets at ε = 0.1).

**Caveat:** this scene is *an illustration of the technique* (the qubit version is
Ross–Selinger "gridsynth"; the embedding lattice is standard number theory). It is not the
authors' code, and the abstract does not give their exact lattice construction. The
fillers are one valid completion, using real entries only. Every totally positive integer
of ℚ(√5) is a sum of three squares (Maass, 1941), so one always exists. "Level" is the
denominator exponent, not a T-count.

## 2. Reachable Net

### The idea

Start from |0⟩ and apply words of Clifford gates with k non-Clifford gates in between.
Layer k is every state first reachable with exactly k of them:

| | layer sizes | median distance to a random target, per gate |
|---|---|---|
| **qubit, Clifford+T** | 6, 12, 24, 48 … (×2 per T) | ×0.708 (1/√2 = 0.707) |
| **qutrit, Clifford+R** | 12, 108, 972, 8748, 78732, 708588 (×9 per R) | ×0.585 (1/√3 = 0.577) |

A fixed factor more states per gate, in a state space of fixed dimension (2 for the qubit,
4 for the qutrit), shrinks the gaps by a fixed factor per gate. So the gates needed to
come within ε grow like log(1/ε), the scaling the talk calls optimal. These are states,
the simpler cousin of what the talk compiles: gates live in SU(3), 8-dimensional.

### What you are looking at

- **Left: the Bloch sphere.** Exact; every reachable qubit state is a point on it, coloured
  by its T-count (the shared warm-to-cool palette), one layer per 2 s, up to 10 T
  (12,282 states).
- **Middle: the qutrit on a solid torus.** A qutrit has no sphere; its state space is 4-D.
  - **Drawn:**
    - **ring angle** = phase of |1⟩ relative to |0⟩
    - **tube angle** = phase of |2⟩ relative to |0⟩
    - **depth** = 1 - (weight on |0⟩): the core is all |0⟩, the surface is no |0⟩
  - **Not drawn:** how the remainder splits between |1⟩ and |2⟩.

  With depth = 1 - p₀, uniformly random qutrit states fill the tube's cross-section
  uniformly, so an even net looks even. The two phases form the same torus as the 2-D HCS
  torus of the Lorenz scene; phases are angles already. Up to 4 R gates (88,572 states).
  Layer 0 shows the structure: |0⟩ on the core, 9 states on a 3 × 3 grid of phases, and
  |1⟩, |2⟩ together at the seam (no |0⟩ part, so no phase relative to it).
- **Each panel** shows a target star with a line to its nearest reachable state, jumping as
  each layer arrives. The target is the most typical of 200 random ones.
- **Wall plot** (`ensemble_reachable_net.py`, 300 random targets, log scale): median
  distance to the nearest reachable state. Both are straight lines, which is the log(1/ε)
  law. A cursor and stars track the scene's own targets.

## Files

- `qudit_math.py`: exact ℤ[ζ₅] arithmetic, the embedding lattice and its enumerators
  (box and Fincke–Pohst), the sliver search, column completion, Clifford groups and the
  reachable-state layers.
- `scene_kit.py`: the node / Channels writer shared by both generators, plus polylines,
  captions and point clouds.
- `generate_cyclotomic_search.py`, `generate_reachable_net.py`: the scenes.
- `ensemble_cyclotomic_ladder.py` → `cyclotomic_ladder.csv` (~2 min);
  `ensemble_reachable_net.py` → `reachable_net.csv` (~1 min). The generators read these.
- `verify_qudit_scenes.py`: both scenes through GlyphViz's own loader, ChannelEngine and
  world transforms, checked against independent recomputation:
  - every drawn lattice point read back from its world position
  - the legal-entry count
  - candidates inside the slot
  - the exact integer column
  - level timing
  - brute-force reachable layers
  - points on the sphere / in the tube
  - nearest-state markers at every stage

  `--bake-dir DIR --frames ...` writes static frames for `tools/export_frame.py`.
