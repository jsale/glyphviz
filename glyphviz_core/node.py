from dataclasses import dataclass, field

# Node CSV "type" values (see
# gaiaviz-skill/references/structure/Node-Field-Descriptions.md). World and
# Camera rows are scene-wide settings/views rather than positioned glyphs, so
# they're kept and editable in the table but skipped when drawing/picking in
# the 3D viewport. Grid and ordinary glyph rows ARE drawn/picked normally.
NODE_TYPE_WORLD  = 0   # one-per-file global scene/world parameters
NODE_TYPE_CAMERA = 1   # camera 'lookat' definitions (switchable with 'C' in ANTz/GaiaViz)
NODE_TYPE_GRID   = 6   # world grid / subgrid definitions
NODE_TYPE_LINK   = 7   # graph edge from parent_id (A-end) to child_id (B-end)

# World/Camera rows hold scene-wide settings, not a position in the glyph
# hierarchy -- they're never drawn, picked, or counted as scene content.
# Grid rows are NOT in this set: a Grid is a real, renderable, pickable
# scene object (see Scene.grid_node() / node_world_matrix) that root glyphs
# implicitly attach to, not infrastructure to hide.
NON_VISUAL_TYPES = frozenset({NODE_TYPE_WORLD, NODE_TYPE_CAMERA})

# rotate_x/y/z interpretation. ANTz/GaiaViz always used HEADING_TILT_ROLL (a
# Z-X-Z "proper Euler" sequence borrowed from KML's Heading/Tilt/Roll camera
# and model convention: rotate_y and rotate_z both rotate about the z-axis).
# EULER_XYZ is GlyphViz-only: rotate_x/y/z each rotate about their own named
# axis, intuitive for hand-posing glyphs but unable to isolate "spin around
# wherever I'm currently aimed" into a single channel the way Roll can.
ROTATION_MODE_EULER_XYZ = 0
ROTATION_MODE_HEADING_TILT_ROLL = 1

# Scene-wide blend mode, read from the World node (type=0) only — see
# Scene.world_node(). Mirrors ANTz's global "transparency mode" hotkey (8),
# documented as a scene-wide toggle, not a per-glyph one (User-Commands.md's
# "Global Color Settings" section), plus two GlyphViz-original additions
# (SCREEN, PREMULTIPLIED) that fit the same fixed-function blend pipeline.
RENDER_MODE_NORMAL = 0         # GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA (current default)
RENDER_MODE_ADDITIVE = 1       # GL_SRC_ALPHA, GL_ONE — glow / light-stacking
RENDER_MODE_SUBTRACTIVE = 2    # GL_FUNC_REVERSE_SUBTRACT
RENDER_MODE_DARK = 3           # GL_ZERO, GL_SRC_COLOR — multiply
RENDER_MODE_OFF = 4            # blending disabled, alpha ignored
RENDER_MODE_SCREEN = 5         # GL_ONE_MINUS_DST_COLOR, GL_ONE
RENDER_MODE_PREMULTIPLIED = 6  # GL_ONE, GL_ONE_MINUS_SRC_ALPHA

# Fallback background color (0-255) used when a scene has no World node —
# matches the viewport's original hardcoded glClearColor(0.08, 0.08, 0.12, 1).
WORLD_DEFAULT_BG_RGB = (20, 20, 31)

RENDER_MODE_COUNT = 7
RENDER_MODE_NAMES = {
    RENDER_MODE_NORMAL: "Normal",
    RENDER_MODE_ADDITIVE: "Additive",
    RENDER_MODE_SUBTRACTIVE: "Subtractive",
    RENDER_MODE_DARK: "Dark (Multiply)",
    RENDER_MODE_OFF: "Off",
    RENDER_MODE_SCREEN: "Screen",
    RENDER_MODE_PREMULTIPLIED: "Premultiplied Alpha",
}


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
    rotation_mode: int = ROTATION_MODE_EULER_XYZ
    # Per-cycle velocities (ANTz convention: added to translate/rotate/scale
    # every cycle, nominally 60 cycles/second — see Node-Field-Descriptions.md's
    # Translate/Rotate/Scale sections). Applied by the viewport's animation
    # tick; a script-authored node CSV can set these directly with no GUI
    # interaction needed. freeze (Node.extras) suspends this when nonzero.
    translate_rate_x: float = 0.0
    translate_rate_y: float = 0.0
    translate_rate_z: float = 0.0
    rotate_rate_x: float = 0.0
    rotate_rate_y: float = 0.0
    rotate_rate_z: float = 0.0
    scale_rate_x: float = 0.0
    scale_rate_y: float = 0.0
    scale_rate_z: float = 0.0
    text: str = ""   # display label shown in 3D viewport
    link: str = ""   # URL or file path opened by U key
    # World-node-only scene settings (see Scene.world_node()): background
    # color reuses color_r/g/b/a above; fog fades to that same color.
    render_mode: int = RENDER_MODE_NORMAL
    fog_enabled: int = 0
    fog_start: float = 0.0
    fog_end: float = 0.0
    # Preserves untracked CSV columns (e.g. channel IDs, quaternion, segments)
    # so that save_node_csv can round-trip files without data loss.
    extras: dict = field(default_factory=dict)
