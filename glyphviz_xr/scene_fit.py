"""Auto-sizing so any node CSV can be loaded with just --csv, instead of
needing per-file --scale tuning by hand (e.g. the SineWave example's
318-unit width vs. the small golden-master fixture's 3-unit width)."""
import numpy as np

from glyphviz_core.node import NODE_TYPE_LINK, NON_VISUAL_TYPES
from glyphviz_core.scene import Scene, node_world_matrix


def auto_scale_for_scene(scene: Scene, target_size: float) -> float:
    """Pick a --scale that maps the scene's largest bounding-box dimension
    to target_size meters."""
    positions = []
    for node in scene.nodes:
        if node.type in NON_VISUAL_TYPES or node.type == NODE_TYPE_LINK:
            continue
        M = node_world_matrix(node, scene)
        positions.append(M[:3, 3])
    if not positions:
        return 1.0
    positions = np.array(positions)
    extent = positions.max(axis=0) - positions.min(axis=0)
    max_extent = float(extent.max())
    if max_extent <= 0:
        return 1.0
    return target_size / max_extent
