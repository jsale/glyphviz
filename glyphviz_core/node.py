from dataclasses import dataclass, field

# Node CSV "type" values (see
# gaiaviz-skill/references/structure/Node-Field-Descriptions.md). World and
# Camera rows are scene-wide settings/views rather than positioned glyphs, so
# they're kept and editable in the table but skipped when drawing/picking in
# the 3D viewport. Grid rows (type=6) are real, renderable, pickable scene
# objects — the World Grid feature — and ordinary glyph rows draw normally.
NODE_TYPE_WORLD  = 0   # one-per-file global scene/world parameters
NODE_TYPE_CAMERA = 1   # camera 'lookat' definitions (switchable with 'C' in ANTz/GaiaViz)
NODE_TYPE_GRID   = 6   # world grid / subgrid definitions
NODE_TYPE_LINK   = 7   # graph edge from parent_id (A-end) to child_id (B-end)

# World/Camera rows hold scene-wide settings, not a position in the glyph
# hierarchy — they're never drawn or picked. Grid rows are NOT in this set:
# a World Grid is a real scene object (movable, rotatable, scalable,
# texturable) whose children attach explicitly via parent_id = grid.id.
NON_VISUAL_TYPES = frozenset({NODE_TYPE_WORLD, NODE_TYPE_CAMERA})

# World Grid (type=6) coordinate window: children's translate_x/y are
# longitude/latitude degrees (or any planar data units), translate_z is
# elevation. The default window is the whole earth in equirectangular
# degrees, so a grid at the origin with scale 1 maps a child 1:1 — a child
# at translate (180, 90) lands at world (180, 90), exactly matching a
# non-grid node with the same coordinates.
GRID_DEFAULT_EXTENTS = (-180.0, 180.0, -90.0, 90.0)   # lon_min, lon_max, lat_min, lat_max
GRID_DEFAULT_SEGMENTS = (36, 18)                      # 10°-cell lines for the default window

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
    mesh_id: int = 0   # selects an imported GEO_MESH shape (see mesh_loader.py); no ANTz/GaiaViz equivalent
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

    # --- World Grid (type=6) accessors ---
    # A grid's coordinate window and line counts live in ANTz 94-column
    # fields kept in `extras` (round-tripped by csv_reader): trigger_lo_x/
    # trigger_hi_x = lon min/max, trigger_lo_y/trigger_hi_y = lat min/max
    # (Native-Tables.md marks the trigger fields "type specific data, used
    # for grid spacing"), and segments_x/segments_y = grid cell counts (the
    # documented ANTz grid meaning). A degenerate axis (hi <= lo, e.g. the
    # all-zero column defaults of files that predate this feature) falls
    # back to the whole-earth GRID_DEFAULT_EXTENTS for that axis.

    def _extras_float(self, key: str, default: float) -> float:
        try:
            return float(self.extras.get(key, default))
        except (TypeError, ValueError):
            return default

    def grid_extents(self) -> tuple[float, float, float, float]:
        """(lon_min, lon_max, lat_min, lat_max) coordinate window of this
        World Grid node. Children's translate_x/y are coordinates within this
        window; the grid's rendered rectangle spans exactly this window
        (times the grid's own scale), centered on the grid's position."""
        lon_lo = self._extras_float('trigger_lo_x', 0.0)
        lon_hi = self._extras_float('trigger_hi_x', 0.0)
        lat_lo = self._extras_float('trigger_lo_y', 0.0)
        lat_hi = self._extras_float('trigger_hi_y', 0.0)
        if lon_hi <= lon_lo:
            lon_lo, lon_hi = GRID_DEFAULT_EXTENTS[0], GRID_DEFAULT_EXTENTS[1]
        if lat_hi <= lat_lo:
            lat_lo, lat_hi = GRID_DEFAULT_EXTENTS[2], GRID_DEFAULT_EXTENTS[3]
        return (lon_lo, lon_hi, lat_lo, lat_hi)

    def set_grid_extents(self, lon_min: float, lon_max: float,
                         lat_min: float, lat_max: float) -> None:
        self.extras['trigger_lo_x'] = float(lon_min)
        self.extras['trigger_hi_x'] = float(lon_max)
        self.extras['trigger_lo_y'] = float(lat_min)
        self.extras['trigger_hi_y'] = float(lat_max)

    def grid_center(self) -> tuple[float, float]:
        """(lon, lat) coordinate that sits at the grid node's own position —
        the midpoint of the extents window. The default whole-earth window
        centers at (0, 0), preserving exact 1:1 child-to-world coordinates."""
        lon_lo, lon_hi, lat_lo, lat_hi = self.grid_extents()
        return ((lon_lo + lon_hi) / 2.0, (lat_lo + lat_hi) / 2.0)

    def grid_half_extents(self) -> tuple[float, float]:
        """Half-spans (lon, lat) of the extents window — the grid's rendered
        rectangle in local units before the node's own scale is applied."""
        lon_lo, lon_hi, lat_lo, lat_hi = self.grid_extents()
        return ((lon_hi - lon_lo) / 2.0, (lat_hi - lat_lo) / 2.0)

    def grid_segments(self) -> tuple[int, int]:
        """(x, y) grid cell counts for rendering (ANTz segments_x/y). 1 = an
        empty rectangle outline, matching the documented ANTz hint."""
        sx = int(self._extras_float('segments_x', 16.0) or 16)
        sy = int(self._extras_float('segments_y', 16.0) or 16)
        return (max(1, sx), max(1, sy))

    def set_grid_segments(self, seg_x: int, seg_y: int) -> None:
        self.extras['segments_x'] = int(max(1, seg_x))
        self.extras['segments_y'] = int(max(1, seg_y))
