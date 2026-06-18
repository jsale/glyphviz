from dataclasses import dataclass, field

# np_node "type" values that describe scene infrastructure rather than visual
# data glyphs (see gaiaviz-skill/references/structure/Node-Field-Descriptions.md).
# GlyphViz doesn't yet have its own camera/grid/world handling, so these rows
# are kept (and remain editable in the table) but skipped when drawing/picking
# in the 3D viewport — otherwise they show up as stray wireframe-cube glyphs.
NODE_TYPE_WORLD  = 0   # one-per-file global scene/world parameters
NODE_TYPE_CAMERA = 1   # camera 'lookat' definitions (switchable with 'C' in ANTz/GaiaViz)
NODE_TYPE_GRID   = 6   # world grid / subgrid definitions
NODE_TYPE_LINK   = 7   # graph edge from parent_id (A-end) to child_id (B-end)

NON_VISUAL_TYPES = frozenset({NODE_TYPE_WORLD, NODE_TYPE_CAMERA, NODE_TYPE_GRID})


@dataclass
class Node:
    id: int
    type: int
    parent_id: int
    branch_level: int
    translate_x: float
    translate_y: float
    translate_z: float
    rotate_x: float
    rotate_y: float
    rotate_z: float
    scale_x: float
    scale_y: float
    scale_z: float
    color_r: int
    color_g: int
    color_b: int
    color_a: int
    geometry: int
    hide: int
    topo: int
    ratio: float = 0.1
    subspace: int = 0
    texture_id: int = 0
    text: str = ""   # display label shown in 3D viewport
    link: str = ""   # URL or file path opened by U key
    # Preserves untracked CSV columns (e.g. channel IDs, quaternion, segments)
    # so that save_node_csv can round-trip files without data loss.
    extras: dict = field(default_factory=dict)
