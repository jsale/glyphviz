"""
Graph structure and 3D force layout.

The layouts are stochastic, so nothing here asserts exact coordinates.  What
is pinned instead is the properties a layout has to have to be worth
rendering: connected nodes end up closer than unconnected ones, planted
communities separate in space, the result is reproducible for a fixed seed,
and the numba and numpy force kernels agree (they are two implementations of
one formula and only one of them runs on any given machine).
"""
import numpy as np
import pytest

from glyphviz_core import graph_layout
from glyphviz_core.graph import (
    Graph, core_numbers, filter_edges, from_edge_pairs, k_core,
    louvain_communities, modularity,
)
from glyphviz_core.graph_layout import (
    fit_to_radius, forceatlas2_3d, fruchterman_reingold_3d, layout_quality,
    pivot_mds_3d,
)


# --- fixtures --------------------------------------------------------------

def planted_partition(groups=4, per_group=25, p_in=0.35, p_out=0.004, seed=7):
    """
    Cliquey groups with sparse bridges between them — the standard test for
    "did the algorithm find the structure that is actually there".

    Returns `(graph, truth)` where `truth[i]` is node i's planted group.
    """
    rng = np.random.default_rng(seed)
    n = groups * per_group
    truth = np.repeat(np.arange(groups), per_group)
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            p = p_in if truth[i] == truth[j] else p_out
            if rng.random() < p:
                edges.append((i, j))
    # Guarantee connectivity: chain the groups so the giant component is all
    # of it, otherwise the test is measuring component splitting instead.
    for g in range(groups - 1):
        edges.append((g * per_group, (g + 1) * per_group))
    return Graph(n, np.array(edges, dtype=np.int64)), truth


def path_graph(n=30):
    return Graph(n, np.array([(i, i + 1) for i in range(n - 1)]))


# --- Graph container -------------------------------------------------------

def test_edges_are_canonicalized():
    g = Graph(4, [(1, 0), (0, 1), (2, 2), (3, 2)], [1.0, 2.0, 5.0, 1.0])
    # self-loop dropped, duplicate pair summed, orientation low->high, sorted
    assert g.edges.tolist() == [[0, 1], [2, 3]]
    assert g.weights.tolist() == [3.0, 1.0]


def test_degrees_and_strengths():
    g = Graph(4, [(0, 1), (0, 2), (0, 3)], [1.0, 2.0, 4.0])
    assert g.degrees().tolist() == [3, 1, 1, 1]
    assert g.strengths().tolist() == [7.0, 1.0, 2.0, 4.0]


def test_from_edge_pairs_keeps_first_appearance_order():
    g, labels = from_edge_pairs([("b", "a"), ("a", "c")])
    assert labels == ["b", "a", "c"]
    assert g.n == 3 and g.m == 2


def test_giant_component_drops_the_fringe():
    # A 5-node core, one detached pair, one isolate.
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 4), (5, 6)]
    g = Graph(8, np.array(edges))
    core, keep = g.giant_component()
    assert core.n == 5
    assert keep.tolist() == [0, 1, 2, 3, 4]
    assert core.m == 5


def test_subgraph_reindexes_and_drops_crossing_edges():
    g = Graph(5, [(0, 1), (1, 2), (2, 3), (3, 4)])
    sub, keep = g.subgraph([1, 2, 3])
    assert keep.tolist() == [1, 2, 3]
    assert sub.n == 3
    assert sub.edges.tolist() == [[0, 1], [1, 2]]  # (3,4) crossed out


# --- filters ---------------------------------------------------------------

def test_core_numbers_on_a_known_shape():
    # A 4-clique (core 3) with a pendant path hanging off it (core 1).
    edges = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3),   # K4
             (3, 4), (4, 5)]                                    # tail
    core = core_numbers(Graph(6, np.array(edges)))
    assert core[:4].tolist() == [3, 3, 3, 3]
    assert core[4] == 1 and core[5] == 1


def test_k_core_keeps_only_the_dense_part():
    edges = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3), (3, 4), (4, 5)]
    sub, keep = k_core(Graph(6, np.array(edges)), 3)
    assert keep.tolist() == [0, 1, 2, 3]
    assert sub.m == 6


def test_core_numbers_of_a_cycle_is_two():
    g = Graph(6, [(i, (i + 1) % 6) for i in range(6)])
    assert core_numbers(g).tolist() == [2] * 6


def test_filter_edges_keeps_nodes_and_drops_weak_edges():
    g = Graph(4, [(0, 1), (1, 2), (2, 3)], [0.5, 2.0, 1.0])
    out = filter_edges(g, 1.0)
    assert out.n == 4                       # nodes survive as isolates
    assert out.edges.tolist() == [[1, 2], [2, 3]]


# --- Louvain ---------------------------------------------------------------

def test_louvain_recovers_a_planted_partition():
    g, truth = planted_partition()
    found = louvain_communities(g, seed=3)
    # Same partition, up to relabeling: every planted group maps to exactly
    # one found community and vice versa.
    pairs = {(int(t), int(f)) for t, f in zip(truth, found)}
    assert len(pairs) == 4
    assert len(set(found.tolist())) == 4


def test_louvain_is_reproducible_for_a_fixed_seed():
    g, _ = planted_partition()
    a = louvain_communities(g, seed=11)
    b = louvain_communities(g, seed=11)
    assert a.tolist() == b.tolist()


def test_louvain_labels_ordered_largest_first():
    # Groups of deliberately different sizes.
    g, _ = planted_partition(groups=3, per_group=30)
    extra = Graph(g.n + 10,
                  np.vstack([g.edges,
                             [(g.n + i, g.n + i + 1) for i in range(9)]]))
    found = louvain_communities(extra, seed=5)
    counts = np.bincount(found)
    assert (np.diff(counts) <= 0).all(), "communities must be largest-first"


def test_modularity_prefers_the_real_partition():
    g, truth = planted_partition()
    found = louvain_communities(g, seed=3)
    rng = np.random.default_rng(0)
    random_part = rng.integers(0, 4, size=g.n)
    assert modularity(g, found) > 0.3
    assert modularity(g, found) > modularity(g, random_part) + 0.2
    assert modularity(g, found) == pytest.approx(modularity(g, truth), abs=0.05)


def test_isolated_nodes_get_their_own_communities():
    g = Graph(5, [(0, 1)])
    found = louvain_communities(g)
    assert len(set(found.tolist())) == 4  # {0,1} together, 2/3/4 separate


# --- force kernels ---------------------------------------------------------

def test_numba_and_numpy_repulsion_agree():
    rng = np.random.default_rng(0)
    pos = rng.normal(size=(60, 3))
    mass = rng.uniform(1, 8, size=60)
    a = np.zeros((60, 3))
    b = np.zeros((60, 3))
    graph_layout._repulsion_numpy(pos, mass, 2.0, 1.0, a, block=16)
    if not graph_layout._HAVE_NUMBA:
        pytest.skip("numba not installed")
    graph_layout._repulsion_numba(pos, mass, 2.0, 1.0, b)
    assert np.allclose(a, b, atol=1e-9)


def test_numba_and_numpy_attraction_agree():
    g, _ = planted_partition(groups=2, per_group=15)
    rng = np.random.default_rng(1)
    pos = rng.normal(size=(g.n, 3))
    mass = (g.degrees() + 1).astype(float)
    for linlog in (False, True):
        for dissuade in (False, True):
            a = np.zeros((g.n, 3))
            b = np.zeros((g.n, 3))
            graph_layout._attraction_numpy(pos, g.edges, g.weights, mass, a,
                                           1.0, linlog, dissuade)
            if not graph_layout._HAVE_NUMBA:
                pytest.skip("numba not installed")
            graph_layout._attraction_numba(pos, g.edges, g.weights, mass, b,
                                           1.0, linlog, dissuade)
            assert np.allclose(a, b, atol=1e-9), (linlog, dissuade)


def test_repulsion_falloff_changes_the_distance_law():
    # Two nodes 2 apart. Force magnitude must be coeff/d^falloff, so
    # doubling the distance divides the force by 2^falloff.
    for falloff in (1.0, 2.0, 2.5):
        mags = []
        for d in (2.0, 4.0):
            pos = np.array([[-d / 2, 0.0, 0.0], [d / 2, 0.0, 0.0]])
            force = np.zeros((2, 3))
            graph_layout._repulsion(pos, np.ones(2), 1.0, force, falloff)
            mags.append(abs(force[1, 0]))
        assert mags[0] / mags[1] == pytest.approx(2.0 ** falloff, rel=1e-6), \
            falloff


def test_repulsion_falloff_agrees_between_kernels():
    rng = np.random.default_rng(3)
    pos = rng.normal(size=(50, 3))
    mass = rng.uniform(1, 5, size=50)
    for falloff in (1.0, 2.0, 2.5):
        a = np.zeros((50, 3))
        b = np.zeros((50, 3))
        graph_layout._repulsion_numpy(pos, mass, 2.0, falloff, a, block=16)
        if not graph_layout._HAVE_NUMBA:
            pytest.skip("numba not installed")
        graph_layout._repulsion_numba(pos, mass, 2.0, falloff, b)
        assert np.allclose(a, b, rtol=1e-9, atol=1e-12), falloff


def test_falloff_2_spreads_more_evenly_than_the_2d_default():
    # The headline 3D finding: the published 1/d repulsion piles nodes into
    # a core, and the true 3D inverse square fills the volume.
    g, _ = planted_partition()
    flat = forceatlas2_3d(g, iterations=500, seed=3, repulsion_falloff=1.0,
                          gravity=1.0).positions
    cubed = forceatlas2_3d(g, iterations=500, seed=3, repulsion_falloff=2.0,
                           gravity=15.0).positions
    def concentration(p):
        r = np.linalg.norm(p - p.mean(axis=0), axis=1)
        return np.percentile(r, 50) / np.percentile(r, 98)
    assert concentration(cubed) > concentration(flat)


def test_step_limiter_prevents_ejection():
    # A steep falloff has a 1/d^3.5 singularity; without the displacement
    # cap a node that drifts too close to another gets launched and never
    # recovers.  Pin that the cap keeps everything in one body.
    g, _ = planted_partition()
    pos = forceatlas2_3d(g, iterations=400, seed=1, repulsion_falloff=2.5,
                         gravity=15.0).positions
    r = np.linalg.norm(pos - pos.mean(axis=0), axis=1)
    assert r.max() / np.percentile(r, 98) < 3.0, r.max()


def test_step_limiter_caps_displacement_but_keeps_direction():
    pos = np.array([[3.0, 4.0, 0.0], [-3.0, -4.0, 0.0]])   # RMS radius 5
    disp = np.array([[100.0, 0.0, 0.0], [0.01, 0.0, 0.0]])
    out = graph_layout._limited_step(pos, disp, 0.10)
    assert np.linalg.norm(out[0]) == pytest.approx(0.5)     # 10% of 5
    assert out[0][0] > 0                                    # direction kept
    assert out[1].tolist() == [0.01, 0.0, 0.0]              # under cap, intact


def test_step_limiter_disabled_is_a_passthrough():
    pos = np.ones((3, 3))
    disp = np.arange(9, dtype=float).reshape(3, 3)
    assert np.allclose(graph_layout._limited_step(pos, disp, 0.0), disp)


def test_repulsion_pushes_apart_along_the_separating_axis():
    pos = np.array([[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    force = np.zeros((2, 3))
    graph_layout._repulsion(pos, np.ones(2), 2.0, force)
    assert force[0, 0] < 0 and force[1, 0] > 0
    assert np.allclose(force[:, 1:], 0.0)


# --- ForceAtlas2 -----------------------------------------------------------

@pytest.mark.parametrize("linlog, dissuade", [
    (False, False),   # Gephi defaults
    (True, True),     # the cluster-revealing recipe
])
def test_forceatlas2_separates_planted_communities(linlog, dissuade):
    g, truth = planted_partition()
    res = forceatlas2_3d(g, iterations=400, linlog=linlog,
                         dissuade_hubs=dissuade, seed=2)
    pos = res.positions
    same, diff = _mean_pair_distances(pos, truth)
    assert same < diff * 0.7, (
        "communities did not separate: within=%.2f between=%.2f" % (same, diff))


def test_forceatlas2_uses_all_three_dimensions():
    g, _ = planted_partition()
    pos = forceatlas2_3d(g, iterations=300, seed=4).positions
    spread = pos.std(axis=0)
    # No axis may collapse: a "3D" layout that is really planar is the bug
    # this whole module exists to avoid.
    assert spread.min() > 0.25 * spread.max(), spread


def test_forceatlas2_is_reproducible():
    g, _ = planted_partition(groups=2, per_group=20)
    a = forceatlas2_3d(g, iterations=120, seed=9).positions
    b = forceatlas2_3d(g, iterations=120, seed=9).positions
    assert np.allclose(a, b)


def test_forceatlas2_puts_neighbors_closer_than_strangers():
    g = path_graph(40)
    pos = forceatlas2_3d(g, iterations=500, seed=1).positions
    d = np.linalg.norm(pos[g.edges[:, 0]] - pos[g.edges[:, 1]], axis=1)
    rng = np.random.default_rng(0)
    i, j = rng.integers(0, 40, 400), rng.integers(0, 40, 400)
    far = np.abs(i - j) > 5
    rand_d = np.linalg.norm(pos[i[far]] - pos[j[far]], axis=1)
    assert d.mean() < rand_d.mean()


def test_forceatlas2_gravity_bounds_the_layout():
    g, _ = planted_partition()
    loose = forceatlas2_3d(g, iterations=250, gravity=0.05, seed=6).positions
    tight = forceatlas2_3d(g, iterations=250, gravity=20.0, seed=6).positions
    assert np.linalg.norm(tight, axis=1).mean() < \
        np.linalg.norm(loose, axis=1).mean()


def test_forceatlas2_snapshots_track_the_run():
    g, _ = planted_partition(groups=2, per_group=15)
    res = forceatlas2_3d(g, iterations=100, seed=0, snapshot_every=20)
    assert len(res.snapshots) >= 5
    its = [i for i, _ in res.snapshots]
    assert its == sorted(its)
    assert all(p.shape == (g.n, 3) for _, p in res.snapshots)
    # The last snapshot is the final state, which is what a Channels track
    # replaying convergence has to end on.
    assert np.allclose(res.snapshots[-1][1], res.positions)


def test_forceatlas2_converges_early_on_a_settled_graph():
    g = Graph(6, [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0)])
    res = forceatlas2_3d(g, iterations=5000, seed=0, tolerance=1e-3)
    assert res.converged
    assert res.iterations < 5000


def test_forceatlas2_handles_an_empty_graph():
    res = forceatlas2_3d(Graph(0, []), iterations=10)
    assert res.positions.shape == (0, 3)


def test_forceatlas2_accepts_a_seed_layout():
    g, _ = planted_partition(groups=2, per_group=20)
    start = pivot_mds_3d(g, pivots=8)
    res = forceatlas2_3d(g, iterations=50, positions=start, seed=0)
    assert res.positions.shape == (g.n, 3)
    assert np.isfinite(res.positions).all()


# --- Fruchterman-Reingold --------------------------------------------------

def test_fruchterman_reingold_separates_communities():
    g, truth = planted_partition()
    pos = fruchterman_reingold_3d(g, iterations=300, seed=3).positions
    same, diff = _mean_pair_distances(pos, truth)
    assert same < diff


def test_fruchterman_reingold_is_finite_and_3d():
    g, _ = planted_partition()
    pos = fruchterman_reingold_3d(g, iterations=200, seed=1).positions
    assert np.isfinite(pos).all()
    assert pos.std(axis=0).min() > 0


# --- Pivot MDS -------------------------------------------------------------

def test_pivot_mds_reflects_graph_distance():
    g = path_graph(40)
    pos = pivot_mds_3d(g, pivots=8)
    # On a path, embedded distance should grow with hop distance.
    d_embed = np.linalg.norm(pos[0] - pos, axis=1)
    hops = np.arange(40, dtype=float)
    corr = np.corrcoef(d_embed, hops)[0, 1]
    assert corr > 0.9, corr


def test_pivot_mds_handles_more_pivots_than_nodes():
    g = path_graph(6)
    pos = pivot_mds_3d(g, pivots=50)
    assert pos.shape == (6, 3)
    assert np.isfinite(pos).all()


# --- layout_quality --------------------------------------------------------

def test_layout_quality_measures_spacing_and_overlap():
    # A regular lattice with a known 1.0 spacing.
    grid = np.stack(np.meshgrid(*[np.arange(5.0)] * 3), -1).reshape(-1, 3)
    q = layout_quality(grid, glyph_diameter=0.5)
    assert q["spacing_p50"] == pytest.approx(1.0)
    assert q["overlap"] == 0.0
    assert layout_quality(grid, glyph_diameter=1.5)["overlap"] == 1.0


def test_layout_quality_separation_detects_clustering():
    rng = np.random.default_rng(0)
    tight = np.concatenate([rng.normal(c, 0.1, size=(50, 3))
                            for c in (-20, 0, 20)])
    labels = np.repeat(np.arange(3), 50)
    mixed = rng.normal(0, 10, size=(150, 3))
    assert layout_quality(tight, labels)["separation"] < 0.1
    assert layout_quality(mixed, labels)["separation"] > 0.8


def test_layout_quality_survives_a_degenerate_input():
    q = layout_quality(np.zeros((1, 3)))
    assert q["spacing_p50"] == 0.0


# --- fitting ---------------------------------------------------------------

def test_fit_to_radius_centers_and_scales():
    rng = np.random.default_rng(0)
    pos = rng.normal(size=(500, 3)) * 3.0 + np.array([50.0, -20.0, 8.0])
    out = fit_to_radius(pos, radius=100.0)
    assert np.allclose(out.mean(axis=0), 0.0, atol=1e-9)
    r = np.linalg.norm(out, axis=1)
    assert np.percentile(r, 98.0) == pytest.approx(100.0)


def test_fit_to_radius_ignores_a_single_flung_outlier():
    pos = np.zeros((200, 3))
    pos[:, 0] = np.linspace(-1, 1, 200)
    pos[0] = [5000.0, 0.0, 0.0]        # one node flung far away
    out = fit_to_radius(pos, radius=100.0)
    bulk = np.linalg.norm(out[1:], axis=1)
    # The bulk must still fill the sphere rather than being crushed to a dot.
    assert bulk.max() > 50.0


def test_fit_to_radius_handles_empty():
    assert fit_to_radius(np.zeros((0, 3))).shape == (0, 3)


# --- helpers ---------------------------------------------------------------

def _mean_pair_distances(pos, labels):
    """Mean within-group and between-group pairwise distance."""
    d = np.linalg.norm(pos[:, None, :] - pos[None, :, :], axis=2)
    same = labels[:, None] == labels[None, :]
    off = ~np.eye(len(pos), dtype=bool)
    return d[same & off].mean(), d[~same].mean()
