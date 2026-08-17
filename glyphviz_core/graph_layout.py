"""
3D force-directed graph layout — the "Gephi filters", generalized to three
dimensions and producing world positions GlyphViz can use directly.

Every algorithm here is force-based on vector quantities, so the *form* of
the physics is dimension-agnostic: the published 2D formulas carry over to
3D unchanged, and these are ports rather than reinterpretations.

The constants inside them are a different matter, and one of them is not a
free parameter at all.  ForceAtlas2's repulsion falls off as 1/d, which is
the Coulomb law of the PLANE; the correct 3D law is 1/d^2, and using the
published exponent in three dimensions is what produces the dense
hairball-with-filaments that gives 3D graph layout its bad name.  See
`forceatlas2_3d`'s `repulsion_falloff`, which is the single most important
knob in this module and has no Gephi equivalent.

Output goes straight into a node CSV: a GlyphViz node with no parent has
`translate_x/y/z` = its world position with no topology offset applied, so a
graph scene is a flat list of ROOT nodes (topo None) plus type-7 link nodes.
Nothing about hierarchy, placement offsets, or topo_scale is involved.

Implemented
-----------
- `forceatlas2_3d`        - Jacomy, Venturini, Heymann & Bastian 2014,
                            "ForceAtlas2, a Continuous Graph Layout Algorithm
                            for Handy Network Visualization" (PLoS ONE).
                            Ported against Gephi's own implementation
                            (ForceFactory / ForceAtlas2.java), including the
                            adaptive speed and swing/traction controller,
                            which is the part that actually makes it settle.
- `fruchterman_reingold_3d` - Fruchterman & Reingold 1991.  Simpler,
                            annealed, no degree weighting; a good sanity
                            check and a good look for small graphs.
- `pivot_mds_3d`          - Brandes & Pich 2007.  Not a force layout: a
                            cheap global embedding from BFS distances to a
                            few pivots.  Its job here is INITIALIZATION —
                            starting ForceAtlas2 from an already globally
                            sane embedding rather than a random cloud
                            avoids the tangled-macrostructure local minima
                            that make 3D graph layouts look like hairballs.

Cost
----
Repulsion is exact all-pairs, O(n^2) per iteration, JIT-compiled with numba
when it is importable and run as chunked numpy when it is not.  That is
comfortable to roughly 20k nodes.  A Barnes-Hut octree is the documented
next step for larger graphs and would slot in behind `_repulsion` without
changing this module's interface.

numba is an OPTIONAL dependency: this module imports and produces identical
results without it, only slower.  Nothing in the GlyphViz application
imports this module — it is generator-side today.
"""

import math

import numpy as np
from scipy.sparse.csgraph import breadth_first_order

try:  # optional accelerator
    from numba import njit, prange
    _HAVE_NUMBA = True
except Exception:  # pragma: no cover - exercised only where numba is absent
    _HAVE_NUMBA = False

    def njit(*args, **kwargs):
        def wrap(fn):
            return fn
        return wrap(args[0]) if args and callable(args[0]) else wrap

    prange = range


class LayoutResult:
    """
    Positions plus what the run did to get them.

    `snapshots` is a list of `(iteration, positions)` when the caller asked
    for them — that is what feeds a Channels track replaying the solver
    converging, which is a thing GlyphViz can show and Gephi cannot.
    """

    def __init__(self, positions, iterations, snapshots=None, converged=False):
        self.positions = positions
        self.iterations = iterations
        self.snapshots = snapshots or []
        self.converged = converged

    def __repr__(self):
        return "LayoutResult(n=%d, iterations=%d, converged=%s)" % (
            len(self.positions), self.iterations, self.converged)


# ---------------------------------------------------------------------------
# Force kernels
# ---------------------------------------------------------------------------

@njit(parallel=True, fastmath=True, cache=True)
def _repulsion_numba(pos, mass, k_r, falloff, force):
    n = pos.shape[0]
    for i in prange(n):
        xi, yi, zi = pos[i, 0], pos[i, 1], pos[i, 2]
        mi = mass[i]
        fx = 0.0
        fy = 0.0
        fz = 0.0
        for j in range(n):
            if j == i:
                continue
            dx = xi - pos[j, 0]
            dy = yi - pos[j, 1]
            dz = zi - pos[j, 2]
            d2 = dx * dx + dy * dy + dz * dz
            if d2 > 0.0:
                # The vector factor is coeff/d^(falloff+1), so that the force
                # MAGNITUDE goes as 1/d^falloff.  The two integer cases get
                # closed forms because pow() in this inner loop costs more
                # than the whole rest of the kernel.
                if falloff == 1.0:
                    f = k_r * mi * mass[j] / d2
                elif falloff == 2.0:
                    f = k_r * mi * mass[j] / (d2 * math.sqrt(d2))
                else:
                    f = k_r * mi * mass[j] / (d2 ** (0.5 * falloff + 0.5))
                fx += dx * f
                fy += dy * f
                fz += dz * f
        force[i, 0] = fx
        force[i, 1] = fy
        force[i, 2] = fz


def _repulsion_numpy(pos, mass, k_r, falloff, force, block=256):
    """Chunked all-pairs repulsion; same result as the numba kernel."""
    n = len(pos)
    for start in range(0, n, block):
        stop = min(start + block, n)
        delta = pos[start:stop, None, :] - pos[None, :, :]
        d2 = np.einsum("ijk,ijk->ij", delta, delta)
        np.fill_diagonal(d2[:, start:stop], np.inf)  # skip self
        d2[d2 == 0.0] = np.inf                       # skip coincident
        pair = k_r * mass[start:stop, None] * mass[None, :]
        if falloff == 1.0:
            f = pair / d2
        else:
            f = pair / d2 ** (0.5 * falloff + 0.5)
        force[start:stop] = np.einsum("ij,ijk->ik", f, delta)


def _repulsion(pos, mass, k_r, force, falloff=1.0):
    if _HAVE_NUMBA:
        _repulsion_numba(pos, mass, k_r, falloff, force)
    else:
        _repulsion_numpy(pos, mass, k_r, falloff, force)


@njit(fastmath=True, cache=True)
def _attraction_numba(pos, edges, weights, mass, force, coeff, linlog,
                      dissuade):
    for e in range(edges.shape[0]):
        i = edges[e, 0]
        j = edges[e, 1]
        we = weights[e]
        dx = pos[i, 0] - pos[j, 0]
        dy = pos[i, 1] - pos[j, 1]
        dz = pos[i, 2] - pos[j, 2]
        c = coeff * we
        if dissuade:
            # Gephi divides by the SOURCE node's mass only (see module note
            # in forceatlas2_3d's docstring about edge order).
            c = c / mass[i]
        if linlog:
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if d <= 0.0:
                continue
            c = c * math.log(1.0 + d) / d
        force[i, 0] -= dx * c
        force[i, 1] -= dy * c
        force[i, 2] -= dz * c
        force[j, 0] += dx * c
        force[j, 1] += dy * c
        force[j, 2] += dz * c


def _attraction_numpy(pos, edges, weights, mass, force, coeff, linlog,
                      dissuade):
    i, j = edges[:, 0], edges[:, 1]
    delta = pos[i] - pos[j]
    c = coeff * weights
    if dissuade:
        c = c / mass[i]
    if linlog:
        d = np.linalg.norm(delta, axis=1)
        safe = d > 0
        c = np.where(safe, c * np.log1p(np.where(safe, d, 1.0)) /
                     np.where(safe, d, 1.0), 0.0)
    pull = delta * c[:, None]
    np.subtract.at(force, i, pull)
    np.add.at(force, j, pull)


def _attraction(pos, edges, weights, mass, force, coeff, linlog, dissuade):
    if _HAVE_NUMBA:
        _attraction_numba(pos, edges, weights, mass, force, coeff,
                          linlog, dissuade)
    else:
        _attraction_numpy(pos, edges, weights, mass, force, coeff,
                          linlog, dissuade)


# ---------------------------------------------------------------------------
# ForceAtlas2
# ---------------------------------------------------------------------------

def forceatlas2_3d(graph, iterations=800, scaling=2.0, gravity=1.0,
                   strong_gravity=False, linlog=False, dissuade_hubs=False,
                   edge_weight_influence=1.0, jitter_tolerance=1.0,
                   repulsion_falloff=1.0, max_step=0.10, positions=None,
                   seed=0, snapshot_every=None, tolerance=1e-4,
                   progress=None):
    """
    ForceAtlas2 in three dimensions.

    Forces, exactly as Gephi applies them (mass = degree + 1):

    - repulsion  between every pair,  magnitude `scaling * m_i * m_j / d`
    - attraction along every edge,    magnitude `w^influence * d`
      (or `w^influence * log(1+d)` in `linlog` mode)
    - gravity    toward the origin,   magnitude `gravity * m_i`
      (or `gravity * m_i * d` when `strong_gravity`)

    Step size is not fixed: the swing/traction controller ported from
    Gephi's ForceAtlas2.java raises speed while the layout is making
    coherent progress and cuts it when nodes start oscillating.  This is the
    single most important part of the algorithm to get right — a naive fixed
    step either crawls or explodes — and it is unchanged in 3D.

    Options worth knowing:

    - `repulsion_falloff` is the one parameter here that does NOT exist in
      Gephi, and **it is the most important one in 3D.**  ForceAtlas2's
      repulsion falls off as 1/d.  That is not an arbitrary choice: 1/d is
      the Coulomb law *of the plane*, the field of a charged line, and it is
      correct for the 2D layouts the algorithm was written for.  Carried
      into three dimensions unchanged it is far too long-ranged — distant
      nodes keep shoving each other — and the layout collapses into a dense
      ball with a few filaments whipping off it.  Setting the exponent to
      2.0 restores the actual 3D inverse-square law.  Measured on the
      3,931-node co-authorship graph (fitted to a 200-unit radius, so the
      numbers are directly comparable):

          falloff  gravity   spacing   separation   r_p50/r_p98
          1.0 (FA2)    1        2.61       0.451        0.33
          2.0         15       11.90       0.584        0.70
          2.5         15       16.15       0.603        0.73

      `r_p50/r_p98` is the tell: at the published exponent half the nodes
      sit inside a third of the radius — that is the dense core — and at
      2.0 the volume is evenly filled.  Rendered side by side the
      difference is not subtle; the 1/d layout is the "3D graphs are just
      hairballs" cliche, and the 1/d^2 layout is a legible network.  Values
      much past 2.0 keep spreading but start washing the community
      structure out, so 2.0 is the recommended 3D default even though 1.0
      is kept as the signature default for fidelity to the paper.

    - `linlog=True` tightens clusters and opens the space between them, and
      with `dissuade_hubs=True` it is the standard Gephi recipe for making
      community structure legible in 2D.  Once `repulsion_falloff` is set
      correctly for 3D, neither is usually needed, and LinLog in particular
      tends to overshoot: on the same graph it contracted communities to
      1/6th the nearest-neighbour spacing, so 85% of glyphs interpenetrated
      and each community rendered as one opaque blob.  Reach for them if a
      3D layout still fails to resolve its communities, not by default.

    The failure mode to watch for throughout is intra-cluster COLLAPSE — a
    community contracting to a knot far smaller than one glyph, so it
    renders as a blob no matter how far you zoom.  It shows up as spacing
    far below glyph diameter, and it is invisible in the separation score,
    which will happily report an excellent 0.13 for a layout made of
    unreadable dots.  `layout_quality` measures both; use it rather than
    guessing.
    - `dissuade_hubs` divides an edge's attraction by the mass of the
      endpoint listed FIRST in `graph.edges`.  That asymmetry is Gephi's
      (the option is "outbound attraction distribution", written for
      directed graphs); on undirected data the first endpoint is simply the
      lower node index, which `Graph` guarantees is stable.  Faithfulness to
      Gephi was preferred here over inventing a symmetric variant.
    - `positions` seeds the run.  Pass `pivot_mds_3d(graph)` for a globally
      sane start; omit it for Gephi's random cloud.

    `tolerance` stops early once mean per-node motion falls below that
    fraction of the layout's own radius, so a converged graph does not burn
    the remaining iterations.
    """
    n = graph.n
    if n == 0:
        return LayoutResult(np.zeros((0, 3)), 0, converged=True)

    rng = np.random.default_rng(seed)
    if positions is None:
        pos = rng.normal(scale=1.0, size=(n, 3))
    else:
        pos = np.array(positions, dtype=np.float64).reshape(n, 3).copy()
    # Coincident nodes have an undefined repulsion direction; a sub-unit
    # jitter is cheaper and more robust than special-casing d == 0.
    pos += rng.normal(scale=1e-3, size=pos.shape)

    mass = (graph.degrees() + 1).astype(np.float64)
    edges = np.ascontiguousarray(graph.edges)
    weights = graph.weights.astype(np.float64)
    if edge_weight_influence == 0.0:
        weights = np.ones_like(weights)
    elif edge_weight_influence != 1.0:
        weights = weights ** edge_weight_influence

    force = np.zeros((n, 3), dtype=np.float64)
    old_force = np.zeros((n, 3), dtype=np.float64)
    speed = 1.0
    speed_efficiency = 1.0
    snapshots = []
    converged = False
    done = 0

    for it in range(iterations):
        old_force, force = force, old_force
        force.fill(0.0)

        _repulsion(pos, mass, scaling, force, repulsion_falloff)
        _attraction(pos, edges, weights, mass, force, 1.0, linlog,
                    dissuade_hubs)

        # Gravity toward the origin keeps disconnected pieces and low-degree
        # fringe from drifting off to infinity.
        if gravity:
            if strong_gravity:
                force -= pos * (gravity * mass)[:, None]
            else:
                d = np.linalg.norm(pos, axis=1)
                safe = d > 0
                scale = np.zeros(n)
                scale[safe] = gravity * mass[safe] / d[safe]
                force -= pos * scale[:, None]

        speed, speed_efficiency, step = _adaptive_step(
            force, old_force, mass, speed, speed_efficiency, jitter_tolerance)
        pos += _limited_step(pos, force * step[:, None], max_step)
        done = it + 1

        if snapshot_every and (it % snapshot_every == 0 or it == iterations - 1):
            snapshots.append((it, pos.copy()))
        if progress is not None and it % 50 == 0:
            progress(it, iterations)

        radius = np.linalg.norm(pos, axis=1).mean()
        motion = np.linalg.norm(force * step[:, None], axis=1).mean()
        if radius > 0 and motion / radius < tolerance:
            converged = True
            if snapshot_every and (not snapshots or snapshots[-1][0] != it):
                snapshots.append((it, pos.copy()))
            break

    return LayoutResult(pos, done, snapshots, converged)


def _limited_step(pos, displacement, fraction):
    """
    Cap any single node's movement at a fraction of the layout's own size.

    Needed because a steep `repulsion_falloff` has a hard singularity: two
    nodes that drift within a hair of each other exchange a force like
    1/d^3.5, and the swing damping alone does not stop that from launching
    one of them.  Measured on the 3,931-node co-authorship graph at
    falloff 2.5, 40 nodes ended up past 1,000 world units with one at
    15,894, against a p98 radius of 200 — and the solver could not recover,
    because a single node carrying an enormous force dominates the global
    swing term and throttles the speed for everybody else.

    Clamping displacement rather than softening the force leaves the
    equilibrium physics exactly as published: this only limits how far a
    node may travel per iteration, so it changes the path to the solution
    and never the solution.  The cap is relative to the current RMS radius,
    so it needs no notion of the layout's absolute scale (which changes by
    orders of magnitude during a run).
    """
    if fraction is None or fraction <= 0:
        return displacement
    extent = float(np.sqrt((pos ** 2).sum(axis=1).mean()))
    limit = fraction * max(extent, 1e-9)
    norms = np.linalg.norm(displacement, axis=1)
    over = norms > limit
    if over.any():
        displacement = displacement.copy()
        displacement[over] *= (limit / norms[over])[:, None]
    return displacement


def _adaptive_step(force, old_force, mass, speed, speed_efficiency,
                   jitter_tolerance):
    """
    Gephi's swing/traction speed controller, verbatim in structure.

    "Swing" is how much a node's force vector reversed since last iteration
    (oscillation); "traction" is how much it stayed the same (progress).
    Global speed rises while traction dominates and is cut hard when swing
    does, and each node's own step is damped by its own swing — so a
    jittering hub slows down without slowing the whole layout.
    """
    n = len(force)
    swing_v = np.linalg.norm(force - old_force, axis=1)
    traction_v = np.linalg.norm(force + old_force, axis=1) * 0.5
    total_swing = float((mass * swing_v).sum())
    total_traction = float((mass * traction_v).sum())

    if total_swing <= 0 or total_traction <= 0:
        step = np.full(n, speed / (1.0 + speed))
        return speed, speed_efficiency, step

    estimated = 0.05 * math.sqrt(n)
    min_jt = math.sqrt(estimated)
    jt = jitter_tolerance * max(
        min_jt, min(10.0, estimated * total_traction / (n * n)))

    min_efficiency = 0.05
    if total_swing / total_traction > 2.0:
        if speed_efficiency > min_efficiency:
            speed_efficiency *= 0.5
        jt = max(jt, jitter_tolerance)

    target = jt * speed_efficiency * total_traction / total_swing
    if total_swing > jt * total_traction:
        if speed_efficiency > min_efficiency:
            speed_efficiency *= 0.7
    elif speed < 1000:
        speed_efficiency *= 1.3

    max_rise = 0.5
    speed = speed + min(target - speed, max_rise * speed)
    step = speed / (1.0 + np.sqrt(speed * swing_v))
    return speed, speed_efficiency, step


# ---------------------------------------------------------------------------
# Fruchterman-Reingold
# ---------------------------------------------------------------------------

def fruchterman_reingold_3d(graph, iterations=300, area=None, gravity=0.1,
                            positions=None, seed=0, snapshot_every=None):
    """
    Classic Fruchterman-Reingold, annealed, in 3D.

    The one dimension-aware constant is the ideal edge length: FR sets
    `k = C * (area / n)^(1/2)` in the plane, which in space becomes
    `k = C * (volume / n)^(1/3)` — the mean spacing of n points in the
    region, whatever its dimension.

    Attraction `d^2 / k` along edges, repulsion `k^2 / d` between all pairs,
    with a linearly cooled maximum displacement.  No degree weighting, so
    hubs are not pushed apart the way ForceAtlas2 pushes them: the result is
    rounder and more even, which reads well on small graphs and turns to
    porridge on large ones.
    """
    n = graph.n
    if n == 0:
        return LayoutResult(np.zeros((0, 3)), 0, converged=True)

    rng = np.random.default_rng(seed)
    if area is None:
        area = float(n)
    k = (area / n) ** (1.0 / 3.0) * max(1.0, n ** (1.0 / 3.0))

    if positions is None:
        pos = rng.uniform(-1.0, 1.0, size=(n, 3)) * k * n ** (1.0 / 3.0) * 0.5
    else:
        pos = np.array(positions, dtype=np.float64).reshape(n, 3).copy()
    pos += rng.normal(scale=1e-3, size=pos.shape)

    temp = k * n ** (1.0 / 3.0) * 0.1
    cool = temp / (iterations + 1)
    force = np.zeros((n, 3), dtype=np.float64)
    ones = np.ones(n, dtype=np.float64)
    edges = np.ascontiguousarray(graph.edges)
    snapshots = []

    for it in range(iterations):
        force.fill(0.0)
        # FR repulsion is k^2/d; the shared kernel supplies coeff/d^2 * delta
        # (magnitude coeff/d), so coeff = k^2 gives exactly k^2/d.
        _repulsion(pos, ones, k * k, force, 1.0)

        delta = pos[edges[:, 0]] - pos[edges[:, 1]]
        d = np.linalg.norm(delta, axis=1)
        safe = d > 0
        mag = np.zeros(len(edges))
        mag[safe] = d[safe] / k          # (d^2/k) / d, applied to delta
        pull = delta * (mag * graph.weights)[:, None]
        np.subtract.at(force, edges[:, 0], pull)
        np.add.at(force, edges[:, 1], pull)

        if gravity:
            force -= pos * gravity

        norm = np.linalg.norm(force, axis=1)
        limit = np.minimum(norm, temp)
        with np.errstate(invalid="ignore", divide="ignore"):
            step = np.where(norm > 0, limit / norm, 0.0)
        pos += force * step[:, None]
        temp = max(temp - cool, 1e-9)

        if snapshot_every and (it % snapshot_every == 0 or it == iterations - 1):
            snapshots.append((it, pos.copy()))

    return LayoutResult(pos, iterations, snapshots, False)


# ---------------------------------------------------------------------------
# Pivot MDS (initialization)
# ---------------------------------------------------------------------------

def pivot_mds_3d(graph, pivots=64, seed=0):
    """
    Brandes & Pich 2007 pivot MDS: an O(n * pivots) global embedding.

    Full stress majorization needs all-pairs shortest paths — O(n^2) memory,
    which is 220 MB at 5k nodes and hopeless past that.  Pivot MDS gets most
    of the global structure for a fraction of the cost by measuring every
    node's graph distance to a handful of well-spread pivots (chosen
    max-min, each new pivot as far as possible from those already chosen)
    and taking the top three eigenvectors of the double-centered result.

    On its own this looks flat and over-smoothed — it is not a finished
    layout.  Its value is as a STARTING POINT for ForceAtlas2: the global
    arrangement of clusters is already roughly right, so the force solver
    only has to do local work and cannot settle into a folded-over
    macrostructure that no amount of further iteration will undo.
    """
    n = graph.n
    if n == 0:
        return np.zeros((0, 3))
    if n <= 3 or graph.m == 0:
        return np.random.default_rng(seed).normal(size=(n, 3))

    adj = graph.adjacency()
    pivots = int(min(pivots, n))
    rng = np.random.default_rng(seed)

    chosen = [int(rng.integers(n))]
    dists = np.empty((pivots, n), dtype=np.float64)
    dists[0] = _hop_distances(adj, chosen[0], n)
    nearest = dists[0].copy()
    for p in range(1, pivots):
        # Max-min: the next pivot is whatever is currently worst-covered.
        nxt = int(np.argmax(np.where(np.isfinite(nearest), nearest, -1.0)))
        chosen.append(nxt)
        dists[p] = _hop_distances(adj, nxt, n)
        nearest = np.minimum(nearest, dists[p])

    # Unreachable nodes cannot happen inside a connected component, but a
    # caller may pass a fragmented graph; park them at the far edge.
    finite = dists[np.isfinite(dists)]
    far = (finite.max() + 1.0) if len(finite) else 1.0
    d = np.where(np.isfinite(dists), dists, far).T  # (n, pivots)

    # Double-centered squared distances, then the leading 3 singular vectors.
    d2 = d ** 2
    c = -0.5 * (d2 - d2.mean(axis=0, keepdims=True)
                - d2.mean(axis=1, keepdims=True) + d2.mean())
    u, s, _ = np.linalg.svd(c, full_matrices=False)
    return u[:, :3] * s[:3]


def _hop_distances(adj, source, n):
    """Unweighted hop distance from `source`, inf where unreachable."""
    order, preds = breadth_first_order(adj, source, directed=False,
                                       return_predecessors=True)
    dist = np.full(n, np.inf)
    dist[source] = 0.0
    for node in order:
        if node == source:
            continue
        dist[node] = dist[preds[node]] + 1.0
    return dist


# ---------------------------------------------------------------------------
# Fitting to world units
# ---------------------------------------------------------------------------

def layout_quality(positions, communities=None, glyph_diameter=None):
    """
    Measure whether a layout is actually renderable, not merely finished.

    A force layout can score well on every graph-theoretic criterion and
    still be unusable, because the thing that decides whether a viewer sees
    structure or a blob is the ratio between how far apart neighbouring
    nodes sit and how big a glyph is.  Returns a dict of:

      `spacing_p5/p50`   nearest-neighbour distance percentiles, in the same
                         world units as `positions`.  Compare against glyph
                         diameter: below it, glyphs interpenetrate.
      `overlap`          fraction of nodes closer to a neighbour than
                         `glyph_diameter` (only when that is given).
      `radius_p50/p98`   how concentrated the layout is around its centre.
      `separation`       mean within-community distance over mean
                         between-community distance (only with
                         `communities`).  Lower is tighter clustering — but
                         a very low score with tiny spacing means the
                         communities collapsed to points, which is a defect,
                         not a success.

    Sampled to 800 nodes for the O(n^2) separation term so this stays cheap
    enough to call inside a parameter sweep.
    """
    from scipy.spatial import cKDTree

    positions = np.asarray(positions, dtype=np.float64)
    n = len(positions)
    out = {}
    if n < 2:
        return {"spacing_p5": 0.0, "spacing_p50": 0.0,
                "radius_p50": 0.0, "radius_p98": 0.0}

    nn = cKDTree(positions).query(positions, k=2)[0][:, 1]
    out["spacing_p5"] = float(np.percentile(nn, 5))
    out["spacing_p50"] = float(np.median(nn))
    if glyph_diameter is not None:
        out["overlap"] = float(np.mean(nn < np.asarray(glyph_diameter)))

    r = np.linalg.norm(positions - positions.mean(axis=0), axis=1)
    out["radius_p50"] = float(np.percentile(r, 50))
    out["radius_p98"] = float(np.percentile(r, 98))

    if communities is not None:
        communities = np.asarray(communities)
        rng = np.random.default_rng(0)
        idx = (rng.choice(n, 800, replace=False) if n > 800
               else np.arange(n))
        d = np.linalg.norm(positions[idx][:, None] - positions[idx][None],
                           axis=2)
        same = communities[idx][:, None] == communities[idx][None]
        off = ~np.eye(len(idx), dtype=bool)
        within, between = d[same & off], d[~same]
        if len(within) and len(between) and between.mean() > 0:
            out["separation"] = float(within.mean() / between.mean())
    return out


def fit_to_radius(positions, radius=100.0, percentile=98.0):
    """
    Center a layout on the origin and scale it into a world-unit sphere.

    A force layout's absolute scale is an artifact of its force constants,
    not of the data, so it always needs rescaling before it becomes
    `translate_x/y/z`.  The radius is matched at a PERCENTILE rather than
    the maximum: force layouts routinely fling one weakly-attached node far
    past the rest, and matching the true maximum would shrink the entire
    structure to accommodate that single outlier.
    """
    positions = np.asarray(positions, dtype=np.float64)
    if not len(positions):
        return positions.copy()
    centered = positions - positions.mean(axis=0)
    r = np.linalg.norm(centered, axis=1)
    ref = np.percentile(r, percentile)
    if ref <= 0:
        ref = r.max() or 1.0
    return centered * (radius / ref)
