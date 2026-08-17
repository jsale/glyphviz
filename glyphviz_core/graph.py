"""
Graph structure for network visualization: an edge-list container plus the
structural analysis a graph scene needs before it can be laid out.

This module is deliberately *positional-free* — it knows nothing about 3D,
translate columns, or GlyphViz nodes.  It answers "what shape is this
network" (which nodes are connected, how central are they, which cluster
does each belong to); `graph_layout.py` answers "where does each node go".
Keeping the split means a layout can be swapped without touching community
detection, and community detection can be tested without running a solver.

Only numpy and scipy are used, so this imports cleanly in a headless
generator with no Qt and no optional graph library present.

The community detection is Louvain (Blondel, Guillaume, Lambiotte &
Lefebvre 2008, "Fast unfolding of communities in large networks"), which is
the same family Gephi's Modularity statistic uses — so a GlyphViz scene
colored by `louvain_communities` is directly comparable to the same graph
colored by Modularity Class in Gephi.  Resolution is the Lambiotte 2009
generalization, matching Gephi's resolution slider.
"""

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.csgraph import connected_components


class Graph:
    """
    An undirected, optionally weighted graph over nodes 0..n-1.

    `edges` is an (m, 2) int array of endpoint indices and `weights` an (m,)
    float array.  Edges are stored **canonically** — deduplicated, self-loops
    dropped, each pair recorded once with `edges[:, 0] < edges[:, 1]`, sorted
    — because two things downstream depend on a stable edge order: the
    ForceAtlas2 "dissuade hubs" option is asymmetric in the endpoint listed
    first (see `graph_layout.forceatlas2_3d`), and generated scenes assign
    link node ids by edge index, so a rebuild must reproduce the same file.
    """

    def __init__(self, n, edges, weights=None):
        self.n = int(n)
        edges = np.asarray(edges, dtype=np.int64).reshape(-1, 2)
        if weights is None:
            weights = np.ones(len(edges), dtype=np.float64)
        weights = np.asarray(weights, dtype=np.float64).reshape(-1)
        if len(weights) != len(edges):
            raise ValueError("weights length must match edges length")
        if len(edges) and (edges.min() < 0 or edges.max() >= self.n):
            raise ValueError("edge endpoint out of range for n=%d" % self.n)
        self.edges, self.weights = _canonical_edges(edges, weights)

    @property
    def m(self):
        """Number of unique undirected edges."""
        return len(self.edges)

    def __repr__(self):
        return "Graph(n=%d, m=%d)" % (self.n, self.m)

    # -- structure ----------------------------------------------------------

    def degrees(self):
        """Unweighted degree (number of distinct neighbors) per node."""
        d = np.zeros(self.n, dtype=np.int64)
        if self.m:
            np.add.at(d, self.edges[:, 0], 1)
            np.add.at(d, self.edges[:, 1], 1)
        return d

    def strengths(self):
        """Weighted degree (sum of incident edge weights) per node."""
        s = np.zeros(self.n, dtype=np.float64)
        if self.m:
            np.add.at(s, self.edges[:, 0], self.weights)
            np.add.at(s, self.edges[:, 1], self.weights)
        return s

    def adjacency(self):
        """Symmetric CSR adjacency matrix (weights, no self-loops)."""
        if not self.m:
            return csr_matrix((self.n, self.n), dtype=np.float64)
        rows = np.concatenate([self.edges[:, 0], self.edges[:, 1]])
        cols = np.concatenate([self.edges[:, 1], self.edges[:, 0]])
        vals = np.concatenate([self.weights, self.weights])
        return coo_matrix((vals, (rows, cols)),
                          shape=(self.n, self.n)).tocsr()

    def subgraph(self, keep):
        """
        Induced subgraph on the node indices in `keep`.

        Returns `(graph, keep)` where `keep` is the (sorted, unique) original
        index of each new node — so `keep[new_index]` recovers the original,
        which is what callers need to carry labels and metadata across.
        """
        keep = np.unique(np.asarray(keep, dtype=np.int64))
        remap = np.full(self.n, -1, dtype=np.int64)
        remap[keep] = np.arange(len(keep))
        if self.m:
            a, b = remap[self.edges[:, 0]], remap[self.edges[:, 1]]
            inside = (a >= 0) & (b >= 0)
            sub_edges = np.stack([a[inside], b[inside]], axis=1)
            sub_w = self.weights[inside]
        else:
            sub_edges = np.zeros((0, 2), dtype=np.int64)
            sub_w = np.zeros(0, dtype=np.float64)
        return Graph(len(keep), sub_edges, sub_w), keep

    def components(self):
        """Connected-component label per node."""
        _, labels = connected_components(self.adjacency(), directed=False)
        return labels

    def giant_component(self):
        """
        The largest connected component, as `(graph, keep)`.

        Almost every real network arrives with a large core plus a scatter of
        isolated pairs and singletons.  Those fragments have no edges tying
        them to anything, so a force layout can only fling them to whatever
        radius gravity balances at — they form a meaningless shell around the
        real structure and blow out the scene's scale.  Extract the giant
        component first.
        """
        labels = self.components()
        if self.n == 0:
            return self, np.zeros(0, dtype=np.int64)
        biggest = np.argmax(np.bincount(labels))
        return self.subgraph(np.flatnonzero(labels == biggest))


def _canonical_edges(edges, weights):
    """Drop self-loops, orient low->high, sum duplicate pairs, sort."""
    if not len(edges):
        return (np.zeros((0, 2), dtype=np.int64),
                np.zeros(0, dtype=np.float64))
    lo = np.minimum(edges[:, 0], edges[:, 1])
    hi = np.maximum(edges[:, 0], edges[:, 1])
    keep = lo != hi
    lo, hi, weights = lo[keep], hi[keep], weights[keep]
    if not len(lo):
        return (np.zeros((0, 2), dtype=np.int64),
                np.zeros(0, dtype=np.float64))
    # Fold each pair to one integer key so duplicates collapse in one pass.
    order = np.lexsort((hi, lo))
    lo, hi, weights = lo[order], hi[order], weights[order]
    new = np.ones(len(lo), dtype=bool)
    new[1:] = (lo[1:] != lo[:-1]) | (hi[1:] != hi[:-1])
    group = np.cumsum(new) - 1
    summed = np.zeros(group[-1] + 1, dtype=np.float64)
    np.add.at(summed, group, weights)
    return np.stack([lo[new], hi[new]], axis=1), summed


def from_edge_pairs(pairs, weights=None):
    """
    Build a Graph from arbitrary hashable node labels.

    Returns `(graph, labels)` where `labels[i]` is the original label of node
    `i`.  Labels are ordered by first appearance, which keeps a generated
    scene stable across runs for a stable input file.
    """
    labels = []
    index = {}
    a_idx, b_idx = [], []
    for a, b in pairs:
        for lab in (a, b):
            if lab not in index:
                index[lab] = len(labels)
                labels.append(lab)
        a_idx.append(index[a])
        b_idx.append(index[b])
    edges = np.stack([np.array(a_idx, dtype=np.int64),
                      np.array(b_idx, dtype=np.int64)], axis=1) \
        if a_idx else np.zeros((0, 2), dtype=np.int64)
    return Graph(len(labels), edges, weights), labels


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def core_numbers(graph):
    """
    k-core decomposition: the largest k for which each node survives repeated
    removal of every node with fewer than k neighbors.

    This is Gephi's K-core filter, and on a collaboration network it is the
    honest way to separate the working core from the fringe — a node with
    core number 1 is somebody who published once with one collaborator, and
    they make up most of the file and none of the structure.

    Peeling with lazy heap deletion, O((n + m) log n).
    """
    n = graph.n
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    adj = graph.adjacency()
    indptr, indices = adj.indptr, adj.indices
    deg = np.diff(indptr).astype(np.int64)

    import heapq
    heap = [(int(deg[i]), int(i)) for i in range(n)]
    heapq.heapify(heap)
    removed = np.zeros(n, dtype=bool)
    core = np.zeros(n, dtype=np.int64)
    level = 0
    while heap:
        d, v = heapq.heappop(heap)
        if removed[v] or d > deg[v]:
            continue  # stale entry: degree dropped after this was pushed
        removed[v] = True
        level = max(level, int(deg[v]))
        core[v] = level
        for u in indices[indptr[v]:indptr[v + 1]]:
            if not removed[u]:
                deg[u] -= 1
                heapq.heappush(heap, (int(deg[u]), int(u)))
    return core


def k_core(graph, k):
    """
    The k-core as `(graph, keep)`, same shape as `subgraph`.

    Note the result may be disconnected even when the input was not — take
    `giant_component()` afterwards if a single body is wanted.
    """
    return graph.subgraph(np.flatnonzero(core_numbers(graph) >= k))


def filter_edges(graph, min_weight):
    """
    Drop edges below a weight, keeping every node (isolates included).

    Gephi's edge-weight filter.  On a weighted collaboration network this is
    the more meaningful filter of the two: it keeps *repeated* collaboration
    and discards the one-off many-author paper, which is what turns a
    co-authorship hairball into a backbone.
    """
    keep = graph.weights >= min_weight
    return Graph(graph.n, graph.edges[keep], graph.weights[keep])


# ---------------------------------------------------------------------------
# Community detection (Louvain)
# ---------------------------------------------------------------------------

def modularity(graph, communities, resolution=1.0):
    """
    Newman-Girvan modularity Q of a partition, with Lambiotte resolution.

    Q = sum_c [ w_in(c)/m - resolution * (k_tot(c) / 2m)^2 ]

    Reported so a caller (or a test) can check that a partition is actually
    good rather than merely well-formed.  Typical strong community structure
    lands around 0.4-0.7; below ~0.3 the graph has little modular structure
    and coloring by community will not tell the viewer much.
    """
    communities = np.asarray(communities, dtype=np.int64)
    m = graph.weights.sum()
    if m <= 0:
        return 0.0
    k = graph.strengths()
    ncom = communities.max() + 1 if len(communities) else 0
    internal = np.zeros(ncom, dtype=np.float64)
    same = communities[graph.edges[:, 0]] == communities[graph.edges[:, 1]]
    np.add.at(internal, communities[graph.edges[:, 0]][same],
              graph.weights[same])
    tot = np.zeros(ncom, dtype=np.float64)
    np.add.at(tot, communities, k)
    return float((internal / m - resolution * (tot / (2 * m)) ** 2).sum())


def louvain_communities(graph, resolution=1.0, seed=0, max_levels=25):
    """
    Louvain modularity communities, returned as a label per node.

    Labels are renumbered so that community 0 is the largest, 1 the next, and
    so on — which matters for coloring: a palette's first and most legible
    entries then land on the clusters a viewer will actually notice.

    `seed` shuffles the node visit order (Louvain is order-dependent), so a
    generated scene must pass a fixed seed to be reproducible.
    """
    n = graph.n
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    if graph.m == 0:
        return np.arange(n, dtype=np.int64)

    rng = np.random.default_rng(seed)
    # `mapping` tracks each ORIGINAL node's community as levels aggregate.
    mapping = np.arange(n, dtype=np.int64)
    edges, weights = graph.edges.copy(), graph.weights.copy()
    size = n

    for _ in range(max_levels):
        comm, changed = _louvain_one_level(size, edges, weights, resolution,
                                           rng)
        if not changed:
            break
        comm = _compact(comm)
        mapping = comm[mapping]
        new_size = comm.max() + 1
        if new_size == size:
            break
        edges, weights = _aggregate(comm, new_size, edges, weights)
        size = new_size
        if size == 1:
            break

    return _order_by_size(mapping)


def _louvain_one_level(n, edges, weights, resolution, rng):
    """
    One pass of local moving: repeatedly move single nodes to the neighboring
    community that most improves modularity, until nothing improves.

    Self-loops (produced by aggregation — they carry a community's internal
    weight) contribute twice to a node's degree but are never a "move to"
    candidate, which is why they are stripped from the neighbor scan and
    added back into `k` separately.
    """
    self_w = np.zeros(n, dtype=np.float64)
    loop = edges[:, 0] == edges[:, 1]
    if loop.any():
        np.add.at(self_w, edges[loop, 0], weights[loop])
    e, w = edges[~loop], weights[~loop]

    k = np.zeros(n, dtype=np.float64)
    if len(e):
        np.add.at(k, e[:, 0], w)
        np.add.at(k, e[:, 1], w)
    k += 2.0 * self_w

    two_m = k.sum()
    if two_m <= 0:
        return np.arange(n, dtype=np.int64), False

    # CSR over non-self edges, both directions.
    rows = np.concatenate([e[:, 0], e[:, 1]])
    cols = np.concatenate([e[:, 1], e[:, 0]])
    vals = np.concatenate([w, w])
    order = np.argsort(rows, kind="stable")
    rows, cols, vals = rows[order], cols[order], vals[order]
    indptr = np.zeros(n + 1, dtype=np.int64)
    np.add.at(indptr, rows + 1, 1)
    indptr = np.cumsum(indptr)

    comm = np.arange(n, dtype=np.int64)
    tot = k.copy()
    # Scratch accumulator reused across nodes; `touched` lists the entries to
    # clear, so resetting costs O(neighbors) rather than O(n) per node.
    w_to = np.zeros(n, dtype=np.float64)
    changed_any = False

    for _ in range(50):
        moved = 0
        for i in rng.permutation(n):
            start, end = indptr[i], indptr[i + 1]
            nbrs, nw = cols[start:end], vals[start:end]
            own = comm[i]
            tot[own] -= k[i]

            touched = []
            for idx in range(len(nbrs)):
                c = comm[nbrs[idx]]
                if w_to[c] == 0.0:
                    touched.append(c)
                w_to[c] += nw[idx]

            best, best_gain = own, w_to[own] - resolution * tot[own] * k[i] / two_m
            for c in touched:
                gain = w_to[c] - resolution * tot[c] * k[i] / two_m
                if gain > best_gain:
                    best, best_gain = c, gain
            for c in touched:
                w_to[c] = 0.0

            tot[best] += k[i]
            if best != own:
                comm[i] = best
                moved += 1
        if moved:
            changed_any = True
        else:
            break

    return comm, changed_any


def _aggregate(comm, ncom, edges, weights):
    """Collapse each community into one node, summing edge weights."""
    a, b = comm[edges[:, 0]], comm[edges[:, 1]]
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    key = lo * ncom + hi
    uniq, inv = np.unique(key, return_inverse=True)
    summed = np.zeros(len(uniq), dtype=np.float64)
    np.add.at(summed, inv, weights)
    return np.stack([uniq // ncom, uniq % ncom], axis=1), summed


def _compact(labels):
    """Renumber arbitrary labels to a dense 0..k-1 range."""
    _, inv = np.unique(labels, return_inverse=True)
    return inv.astype(np.int64)


def _order_by_size(labels):
    """Renumber so community 0 is the largest, 1 the next, and so on."""
    labels = _compact(labels)
    counts = np.bincount(labels)
    rank = np.empty(len(counts), dtype=np.int64)
    rank[np.argsort(-counts, kind="stable")] = np.arange(len(counts))
    return rank[labels]
