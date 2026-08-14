"""Merge a second node CSV's contents into an already-loaded scene.

Loading file B "into" file A is not a concatenation: both files number their
nodes from their own id space, both carry their own per-file infrastructure
rows (the World row's scene settings, ANTz/GaiaViz camera rows), and both may
reference ids in fields the loader keeps in Node.extras (a link's B-end
``child_id``, the tag file's ``record_id``, a channel binding's
``ch_input_id``).  merge_nodes() rebases the incoming list onto a fresh id
block above everything already in the scene and rewrites every one of those
references to match, so the result is a single self-consistent scene that
round-trips through save_node_csv/save_tag_csv unchanged.

Node coordinates are deliberately left alone: two scenes merged together
overlay in the same world space, which is what makes merging useful for
datasets that share a frame (two GPS tracks, two layers over one World Grid).
Reposition afterwards with an ordinary multi-select drag if you want them
side by side.
"""

import copy
from dataclasses import dataclass, field

from .node import Node, NODE_TYPE_LINK, NODE_TYPE_WORLD, NON_VISUAL_TYPES

# extras keys holding a channel-input id (see channel_engine._CH_INPUT_KEYS)
# plus the output side. Cleared on merged nodes because channel ids live in
# the incoming file's OWN ch-map id space — leaving them set would silently
# bind merged nodes to whatever unrelated channel happens to share the number
# in the host scene's ch-map on the next load.
_CH_KEYS = ('ch_input_id', 'np_ch_in_id', 'ch_input_id ',
            'ch_output_id', 'np_ch_out_id')


@dataclass
class MergeResult:
    """What merge_nodes() produced, for the caller's status reporting."""

    nodes: list[Node] = field(default_factory=list)
    # old incoming id -> new id in the merged scene
    id_map: dict[int, int] = field(default_factory=dict)
    # incoming World/Camera infrastructure rows dropped as duplicates
    skipped_global: int = 0
    # type=7 links whose B-end wasn't part of the merged set
    dropped_links: int = 0
    # nodes whose parent row was dropped (or was already dangling), re-rooted
    rerooted: int = 0
    # nodes whose channel binding was cleared (see _CH_KEYS)
    cleared_channels: int = 0

    @property
    def count(self) -> int:
        return len(self.nodes)


def _clear_channel_binding(node: Node) -> bool:
    """Zero any channel-input/output id in extras. True if anything changed."""
    changed = False
    for key in _CH_KEYS:
        if key in node.extras:
            try:
                already_zero = int(float(node.extras[key])) == 0
            except (TypeError, ValueError):
                already_zero = False
            node.extras[key] = 0
            changed = changed or not already_zero
    return changed


def recompute_branch_levels(nodes: list[Node], own_ids: set[int]) -> None:
    """Set branch_level to true depth for the merged nodes.

    Only ids inside `own_ids` count as parents — a node parented onto
    something outside the set is treated as a root here.  Re-rooting (below)
    already makes that impossible for the GUI's plain merge, but recomputing
    keeps branch_level honest if a caller reparents the result afterwards.

    Public because selection_export needs exactly this: branch_level is a
    stored column, not a derived one, so any operation that lifts nodes out
    of one hierarchy into another has to restate it.
    """
    children: dict[int, list[Node]] = {}
    roots: list[Node] = []
    for n in nodes:
        if n.parent_id in own_ids:
            children.setdefault(n.parent_id, []).append(n)
        else:
            roots.append(n)
    frontier = roots
    level = 0
    while frontier:
        for n in frontier:
            n.branch_level = level
        level += 1
        frontier = [c for n in frontier for c in children.get(n.id, ())]


def merge_nodes(existing: list[Node], incoming: list[Node]) -> MergeResult:
    """Rebase `incoming` so it can be appended to `existing` as one scene.

    Returns a MergeResult holding fresh deep copies — `incoming` is never
    mutated, so a caller can merge the same loaded list into several scenes.

    Rules:
      - New ids are one contiguous block starting at max(existing ids) + 1,
        assigned in file order; parent_id, a link's extras['child_id'] and
        extras['record_id'] (the tag file's join key) are all rewritten to
        match.
      - Incoming World (type=0) and Camera (type=1) rows are per-file
        globals, so they're dropped rather than duplicated — except that the
        incoming World row is kept when the host scene has none, so merging
        into an empty scene still brings its background/tag/fog settings.
      - A link whose B-end isn't in the merged set is dropped rather than
        left pointing at an arbitrary host node (same rule as Copy/Paste).
      - A node whose parent didn't survive (or was already dangling in the
        source file) becomes a root instead of a dangling child.
      - Channel bindings are cleared; see _CH_KEYS.
    """
    result = MergeResult()
    if not incoming:
        return result

    existing_ids = {n.id for n in existing}
    next_id = max(existing_ids, default=0) + 1
    host_has_world = any(n.type == NODE_TYPE_WORLD for n in existing)

    # --- pick which incoming rows survive ---
    kept: list[Node] = []
    world_slot_open = not host_has_world
    for n in incoming:
        if n.type in NON_VISUAL_TYPES:
            if n.type == NODE_TYPE_WORLD and world_slot_open:
                world_slot_open = False   # first World row only
                kept.append(n)
                continue
            result.skipped_global += 1
            continue
        kept.append(n)

    # --- allocate the new id block ---
    id_map = {n.id: next_id + i for i, n in enumerate(kept)}
    result.id_map = id_map

    # --- rebase ---
    merged: list[Node] = []
    for n in kept:
        node = copy.deepcopy(n)
        node.id = id_map[n.id]
        if n.parent_id == 0:
            node.parent_id = 0
        elif n.parent_id in id_map:
            node.parent_id = id_map[n.parent_id]
        else:
            # Parent was a dropped Camera/World row, or never existed.
            node.parent_id = 0
            result.rerooted += 1
        if node.type == NODE_TYPE_LINK:
            try:
                b_id = int(float(n.extras.get('child_id', 0)))
            except (TypeError, ValueError):
                b_id = 0
            if b_id not in id_map:
                result.dropped_links += 1
                continue
            node.extras['child_id'] = id_map[b_id]
        # record_id is the node<->tag join key on save; the incoming file's
        # value belongs to its own id space and would collide with a host
        # node's. Re-point it at the new id, matching what save_node_csv
        # writes for a freshly-created node.
        if 'record_id' in node.extras:
            node.extras['record_id'] = node.id
        if _clear_channel_binding(node):
            result.cleared_channels += 1
        merged.append(node)

    recompute_branch_levels(merged, {n.id for n in merged})
    result.nodes = merged
    return result
