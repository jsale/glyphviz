"""
Point Cloud topology (TOPO_POINTCLOUD) — the data half.

A cloud PARENT is an ordinary node whose `topo` is TOPO_POINTCLOUD. Its
children place at plain Cartesian translate_x/y/z (topology._pointcloud_offset
— ANTz's own rule, npgldraw.c:641), and the renderer draws them as ONE batched
GL_POINTS array instead of one glyph apiece (ANTz npgldraw.c:391). That
substitution is the whole feature: a point is still a real node — it has an
id, a color, a tag, a channel binding, and it saves to CSV like anything else
— it just costs one vertex to draw instead of a matrix multiply and a display
list call.

Measured, which is why the topology exists at all: 100k colored GL_POINTS
replay from a compiled display list in 0.10 ms/frame, and 1M in 0.63 ms. The
same 100k drawn as individual glyphs is the thing GlyphViz was already slow
at. The ceiling on a cloud is therefore NOT the renderer. It is the Node: about
2 KB resident each, and about 550 BYTES ON DISK, because save_node_csv writes
the 94-column ANTz-compatible layout whether or not a point uses any of it.
Measured end to end on real imports:

    100,000 points -> 55 MB of node CSV, 3.4 s to save, 1.8 s to reopen
    442,767 points -> 244 MB,           15 s to save,   9 s to reopen

So the practical limit is disk and memory, not frame rate, and it is the
SAVED scene that costs: importing 442k points out of a compressed LAZ takes
4 s and renders at ~400 fps. 100k is the comfortable default; past a few
hundred thousand, decimate on import (glyphviz_core/point_cloud_loader.py).

Everything here is numpy-only: no Qt, no OpenGL. The renderer consumes the
arrays this module builds (glyphviz_gl/viewport.py's _draw_point_clouds), and
a future non-GL presentation layer (OpenXR, three.js) can take exactly the
same arrays and hand them to a VBO — which is the reason the batch is built as
data here rather than as GL commands there.
"""
from dataclasses import dataclass

import numpy as np

from .node import NODE_TYPE_LINK, NON_VISUAL_TYPES, Node
from .topology import TOPO_POINTCLOUD

# Ratio -> rendered point size in pixels. The same conversion Link lines and
# Plot polylines already use for their widths (viewport: `ratio * 20`), so the
# one ratio spin box in the Properties panel means a comparable thickness
# whichever of the three a node is. A cloud parent's default ratio of 0.1
# therefore renders 2 px points.
#
# ANTz drove point size from `node->lineWidth` (npgldraw.c:396). GlyphViz's
# Node has no lineWidth field — ratio is the field that already carries "how
# thick is this thing" for every other batched primitive, so it is the one
# reused here rather than adding a column.
POINT_SIZE_SCALE = 20.0
MIN_POINT_SIZE = 1.0
# Fixed-function GL clamps glPointSize to an implementation maximum (commonly
# 63.0-2048.0) and silently ignores anything past it. Clamping here instead
# keeps behavior identical across drivers, and keeps a runaway ratio — a
# Channels track bound to it, say — from turning a cloud into a screen-filling
# blur that the user then cannot click out of.
MAX_POINT_SIZE = 64.0


@dataclass
class CloudBatch:
    """One cloud parent's children, flattened into draw-ready arrays.

    `ids` is what makes the batch pickable: the color-ID pick pass renders
    the same points with `id_colors(ids)`, so index i in the vertex array and
    index i in `ids` are the same node, and a pixel read back out of the pick
    FBO resolves straight to a node id.
    """
    ids: np.ndarray          # (N,)   int64  — node id per point
    positions: np.ndarray    # (N, 3) float32 — world space
    colors: np.ndarray       # (N, 4) uint8

    def __len__(self) -> int:
        return int(self.ids.shape[0])


def is_cloud_parent(node: Node) -> bool:
    """True for a node whose children render as a batched point cloud.

    A Link (type=7) has no children of its own and its `topo` is meaningless
    — it renders as an edge between two ends — so it is never a cloud parent
    however its topo column reads. Same exclusion `_SceneScan` applies to
    Plot and Surface.
    """
    return node.topo == TOPO_POINTCLOUD and node.type != NODE_TYPE_LINK


def cloud_parent_ids(nodes) -> set[int]:
    """Ids of every cloud parent in *nodes*. Usually empty or tiny, which is
    why the renderer tests child membership as `parent_id in <this set>`
    rather than materializing the (potentially 100k-element) set of points."""
    return {n.id for n in nodes if is_cloud_parent(n)}


def point_size(parent: Node) -> float:
    """Rendered point size in pixels for one cloud, from the parent's ratio."""
    return float(min(MAX_POINT_SIZE,
                     max(MIN_POINT_SIZE, parent.ratio * POINT_SIZE_SCALE)))


def drawable_children(children, show_hidden: bool) -> list[Node]:
    """The children of a cloud parent that render as points.

    Non-visual rows (World/Camera) and Links are excluded for the same
    reasons the ordinary draw loop excludes them; `hide` is honoured unless
    the viewport's show-hidden mode is on. Order is preserved, because the
    batch index -> node mapping in CloudBatch.ids depends on it.
    """
    return [c for c in children
            if c.type not in NON_VISUAL_TYPES
            and c.type != NODE_TYPE_LINK
            and (show_hidden or not c.hide)]


def build_batch(children: list[Node], positions: np.ndarray) -> CloudBatch | None:
    """Flatten *children* and their already-resolved world *positions* into
    draw-ready arrays. Returns None for an empty cloud.

    `positions` is (len(children), 3) in the same order — the caller gathers
    it in one vectorized shot from the Scene's baked transforms
    (Scene.world_pos_rows), because calling world_pos() once per point costs
    ~0.1 s at 100k.

    Colors come off each node's own color_r/g/b/a, so a cloud is colored the
    way every other GlyphViz scene is: per node, from the CSV, and
    Channels-bindable. np.fromiter rather than a list comprehension — at 100k
    points the difference is real and this runs on every scene edit.
    """
    n = len(children)
    if n == 0 or positions.shape[0] != n:
        return None
    ids = np.fromiter((c.id for c in children), dtype=np.int64, count=n)
    rgba = np.fromiter(
        (v for c in children
         for v in (c.color_r, c.color_g, c.color_b, c.color_a)),
        dtype=np.uint8, count=n * 4,
    ).reshape(n, 4)
    return CloudBatch(ids=ids,
                      positions=np.ascontiguousarray(positions, dtype=np.float32),
                      colors=rgba)


def id_colors(ids: np.ndarray) -> np.ndarray:
    """(N, 4) uint8 color-ID array for the pick pass — the vectorized form of
    the renderer's per-node `(id & 0xFF, id >> 8 & 0xFF, id >> 16 & 0xFF)`
    encoding. Must stay bit-identical to it: the pick FBO read decodes both
    with the same arithmetic, so a cloud point and a glyph have to agree on
    what a given pixel color means."""
    ids = np.asarray(ids, dtype=np.int64)
    out = np.empty((ids.shape[0], 4), dtype=np.uint8)
    out[:, 0] = (ids & 0xFF).astype(np.uint8)
    out[:, 1] = ((ids >> 8) & 0xFF).astype(np.uint8)
    out[:, 2] = ((ids >> 16) & 0xFF).astype(np.uint8)
    out[:, 3] = 255
    return out
