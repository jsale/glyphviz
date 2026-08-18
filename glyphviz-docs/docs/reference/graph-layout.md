# 3D Graph Layout

A network arrives as an edge list — who is connected to whom — and nothing else. Nothing in it says where anything goes. Turning that into a scene means running a layout, and GlyphViz ships one: force-directed layout generalized to three dimensions, plus the structural analysis a graph scene needs first.

This is **generator-side**. Nothing in the application imports these modules; they run in the script that writes your node CSV, and what they produce is a set of world positions the CSV takes directly. A root node's `translate_x/y/z` *is* its world position, so a laid-out graph is a file full of roots with topology None and one Link per edge — no hierarchy, no placement offsets, no `topo_scale`.

Two modules, deliberately split:

| Module | Answers |
|---|---|
| `glyphviz_core/graph.py` | *What shape is this network?* — connectivity, filters, communities |
| `glyphviz_core/graph_layout.py` | *Where does each node go?* — the solvers |

Only numpy and scipy are required, so both import cleanly in a headless generator. [numba](https://numba.pydata.org/) is picked up if present and accelerates the force kernels; the two code paths are pinned equal by tests, so installing or not installing it changes only the speed.

See the [Collaboration Networks](../examples/collaboration-networks.md) and [Trust Network](../examples/trust-network.md) examples for complete generators built on this.

## The one thing to know

**ForceAtlas2's repulsion falls off as 1/d, and that is the Coulomb law of the *plane*.** It is the right law for the 2D layouts the algorithm was written for. Carried into three dimensions unchanged it is far too long-ranged — distant nodes keep shoving each other — and the layout collapses into a dense ball with a few filaments whipping off it. That is the cliché that gives 3D graph drawing its bad name, and it is a wrong constant rather than a property of three dimensions.

`repulsion_falloff=2.0` restores the actual inverse-square law. Measured on a 3,931-node co-authorship graph, every layout fitted to the same 200-unit radius so the numbers compare directly:

| repulsion | nearest-neighbour spacing | r(50%) / r(98%) |
|---|---|---|
| 1/d — ForceAtlas2 as published | 2.61 | 0.33 |
| 1/d² — the 3D law | 11.90 | 0.70 |
| 1/d^2.5 | 16.15 | 0.73 |

The right-hand column is the tell: at the published exponent half the nodes sit inside a third of the radius, which is a core; at 1/d² the volume is evenly filled. There is no Gephi equivalent for this parameter — **1.0 remains the signature default for fidelity to the published algorithm, and 2.0 is what you should almost always pass in 3D.** Values much past 2.0 keep spreading but start washing the community structure out.

Two related traps, both worth knowing before you tune anything:

- **A steep falloff can eject a node.** A 1/d^3.5 vector force has a real singularity, so two nodes drifting within a hair of each other can launch one of them into the far distance — where its enormous force then dominates the global speed controller and freezes the whole layout. `forceatlas2_3d` caps any single node's per-iteration displacement (`max_step`, a fraction of the layout's own radius), which clamps the *path* without touching the equilibrium the solver is converging to.
- **LinLog and dissuade-hubs are 2D folklore.** Together they are the standard Gephi recipe for making community structure legible, and in 3D they overshoot: on the same graph LinLog contracted communities to a sixth of the nearest-neighbour spacing, so 85% of glyphs interpenetrated and each community rendered as one opaque blob. Once the falloff is right, neither is usually needed. Reach for them if a 3D layout still fails to resolve its communities, not by default.

## Building a graph

```python
from glyphviz_core.graph import (
    Graph, from_edge_pairs, filter_edges, k_core, louvain_communities,
)

# Node labels can be anything hashable; labels[i] recovers the original.
graph, labels = from_edge_pairs(pairs, weights)

graph = filter_edges(graph, min_weight=0.8)     # Gephi's edge-weight filter
graph, keep = k_core(graph, 3)                  # Gephi's K-core filter
graph, keep2 = graph.giant_component()          # drop the isolated fragments
community = louvain_communities(graph, seed=0)  # a label per node
```

`Graph` stores edges canonically — deduplicated, self-loops dropped, each pair recorded once with the lower index first, sorted. That order is stable, which matters because generated scenes assign link node ids by edge index: a rebuild has to reproduce the same file.

Every filter returns `(graph, keep)` where `keep[new_index]` is the original index, which is how you carry names, dates and metadata across a filter.

| Call | What it is for |
|---|---|
| `giant_component()` | Real networks arrive with a core plus a scatter of isolated pairs. Those have no edges tying them to anything, so a force layout can only fling them to whatever radius gravity balances at — a meaningless shell around the real structure. Take the giant component first. |
| `filter_edges(g, w)` | Keeps *repeated* connection and discards the one-off. On a weighted co-authorship network this is the more meaningful of the two filters: it discards the single forty-author paper that would otherwise drop a forty-clique of strangers into the scene. |
| `k_core(g, k)` | Removes what survives on one or two threads — nodes that add rows and no structure. May leave the result disconnected; take `giant_component()` afterwards. |
| `louvain_communities(g)` | Modularity communities, the same family as Gephi's Modularity Class, so a scene coloured by this is directly comparable. Labels are renumbered largest-first, so a palette's first and most legible entries land on the clusters a viewer actually notices. Pass a fixed `seed` — Louvain is order-dependent, and a generated scene has to be reproducible. |
| `core_numbers(g)`, `modularity(g, c)`, `degrees()`, `strengths()`, `subgraph(keep)` | The rest of the structural toolkit. |

## Laying it out

```python
from glyphviz_core.graph_layout import (
    forceatlas2_3d, pivot_mds_3d, fit_to_radius, layout_quality,
)

start  = pivot_mds_3d(graph)                    # a globally sane seed
result = forceatlas2_3d(graph, iterations=900, positions=start,
                        repulsion_falloff=2.0, gravity=15.0, seed=0)
pos    = fit_to_radius(result.positions, radius=200.0)
```

### `forceatlas2_3d(graph, ...)`

ForceAtlas2 ported against Gephi's own implementation, swing/traction speed controller included. Mass is `degree + 1`, exactly as Gephi has it, and the forces are vector quantities so they carry into 3D untouched.

| Parameter | Notes |
|---|---|
| `repulsion_falloff` | **See above.** Pass 2.0 in three dimensions. |
| `iterations`, `tolerance` | Stops early once mean per-node motion falls below `tolerance` × the layout's own radius, so a converged graph doesn't burn the rest. |
| `scaling`, `gravity`, `strong_gravity` | Gephi's, unchanged. A steeper falloff wants more gravity to hold the cloud together — 15 against the default 1 in the shipped examples. |
| `positions` | Seeds the run. Pass `pivot_mds_3d(graph)` for a globally sane start; omit for Gephi's random cloud. |
| `linlog`, `dissuade_hubs`, `edge_weight_influence` | Gephi's, unchanged; see the trap above before enabling the first two. |
| `max_step` | Per-iteration displacement cap, as a fraction of the layout radius (default 0.10). Tighten it hard — 0.004 — for an incremental run, where many iterations compound inside one animation frame. |
| `snapshot_every` | Records `(iteration, positions)` into `result.snapshots`. This is what feeds a Channels track replaying the solver converging. |
| `speed`, `speed_efficiency` | Resume state. |
| `seed`, `progress` | Reproducibility, and a callback for long runs. |

`LayoutResult` carries `positions`, `iterations`, `converged`, `snapshots`, and the controller's final `speed` / `speed_efficiency`.

**Resuming matters for streaming layouts.** If you re-run the solver frame by frame on the graph that existed at each moment — which is what makes a growth animation look like a layout chasing its data — feed the previous `LayoutResult`'s `speed` and `speed_efficiency` back in. Restarting the adaptive controller cold on every call lets the speed ramp from scratch each time, which shows up as the whole layout twitching once per batch. Defaults are unchanged, so a cold start is bit-identical to before.

### The other solvers

- **`fruchterman_reingold_3d(graph, ...)`** — classic FR, annealed. The one dimension-aware constant is the ideal edge length: `k = C·(area/n)^½` in the plane becomes `k = C·(volume/n)^⅓` in space. No degree weighting, so hubs are not pushed apart the way ForceAtlas2 pushes them; rounder and more even, which reads well on small graphs and turns to porridge on large ones.
- **`pivot_mds_3d(graph, pivots=64)`** — Brandes & Pich pivot MDS, O(n × pivots). Not a finished layout on its own: it looks flat and over-smoothed. Its value is as a *starting point*, because the global arrangement of clusters is already roughly right before the force solver begins.

### Finishing

- **`fit_to_radius(positions, radius=200.0)`** centres the layout on the origin and scales it into a world-unit sphere. A force layout's absolute scale is an artifact of its force constants, not of the data, so it always needs this before it becomes `translate_x/y/z`. The radius is matched at the 98th percentile rather than the maximum — force layouts routinely fling one weakly-attached node far past the rest, and matching the true maximum would shrink the whole structure to accommodate it.

    If you are animating a *growing* graph, compute one fit transform from the final frame and apply it to every frame. Re-fitting each frame renormalises the cloud, so a network that is actually expanding appears to stand still.

## Checking the layout before you render it

**Separation scores lie.** A layout of unreadable collapsed dots scores an excellent 0.13, because the thing that decides whether a viewer sees structure or a blob is not a graph-theoretic criterion — it is the ratio between how far apart neighbouring nodes sit and how big a glyph is.

```python
q = layout_quality(pos, communities=community, glyph_diameter=2.0)
```

| Key | Meaning |
|---|---|
| `spacing_p5`, `spacing_p50` | Nearest-neighbour distance percentiles, in world units. **Compare against glyph diameter**: below it, glyphs interpenetrate. |
| `overlap` | Fraction of nodes closer to a neighbour than `glyph_diameter`. |
| `radius_p50`, `radius_p98` | How concentrated the layout is around its centre — the hairball tell. |
| `separation` | Mean within-community distance over mean between-community distance. Lower is tighter clustering — *but* a very low score with tiny spacing means the communities collapsed to points, which is a defect, not a success. |

Print these from your generator rather than checking them once in a notebook: changing a filter or a fit radius will silently break a scene otherwise.

## Encoding a graph as a scene

What the shipped examples do, and what generalizes:

- **Encode community twice — as colour *and* as geometry.** Colour is what a viewer reads; shape is what they can *act* on, because **Select By → Geometry** then pulls out a whole sub-network in one action. There are 18 usable shapes (9 solids and the same 9 as wireframes). Hold one out — Sphere — as the "no shape of its own" fallback, so "select all spheres" means the unnamed remainder rather than colliding with a real community.
- **Four geometries are the wrong choice for a solver-placed node.** Pin stands on its apex instead of straddling its origin, so it sits visibly off the position computed for it; Grid is a flat plate that disappears edge-on; Point is a fixed-pixel sprite that ignores scale, so it cannot carry a size encoding and does not foreshorten with distance; Mesh needs an imported file.
- **Label every node, and pin almost none.** Put the name in `text` on all of them — a glyph that cannot say what it is has thrown the data away — and use `show_text` to pin only the handful of hubs that should be legible from outside. Everything else appears on selection or with **T**.
- **Put the legend in the scene.** GlyphViz draws no screen-space overlay, so a key is a column of real glyphs in each community's actual colour and shape, hung off one title node as children so dragging the title moves the whole thing. Tag text is drawn to the *right* of its anchor and is not counted in auto-framing, so split long headings into short lines or they run off the edge.
- **Stretched-glyph links are for edges that carry meaning, not for bulk.** A solid geometry is solid along its whole length, so one passing near the camera is a girder however thin it is in world units. Ration the shape to the edges that earn it and draw the rest as geometry `27` (Line). See [Geometry on a Link node](geometries.md#geometry-on-a-link-node).

## Scale

Repulsion is exact all-pairs, which is comfortable to roughly **20,000 nodes** — 900 ForceAtlas2 iterations on a 3,931-node graph take about 20 seconds with numba installed, and Louvain on the same graph is 0.3 seconds. Past that the module wants a Barnes–Hut octree, which would slot in behind the repulsion kernel without changing any interface.
