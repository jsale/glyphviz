import numpy as np

from .color_palette import PALETTE_COUNT, resolve_palette_color
from .geometry_data import GEO_COUNT
from .node import Node, RENDER_MODE_COUNT
from .topology import TOPO_COUNT

# Maps attribute names from the ch-map to Node dataclass fields.
# Attributes not listed here are skipped.
#
# The *_rate attributes set a per-cycle velocity that the viewport integrates
# (Viewport._animate_rates, 60 cycles/s) — so a channel driving e.g.
# rotate_rate_z sets how fast the node spins each frame, and the spin itself
# accumulates in rotate_z outside the engine's control. reset() restores the
# rate to its CSV value (normally 0, stopping the motion) but deliberately not
# the integrated position/rotation/scale — those stay wherever the animation
# left them, matching how hand-authored ANTz rate fields behave on load.
#
# render_mode/fog_* are scene-wide settings read only off the World node
# (type=0) — see Scene.world_node(). Binding them means giving that World row
# a ch_input_id like any other node; on any other node type they are inert.
# The World node's own color_r/g/b is the scene background, so it animates
# through the ordinary color binding.
_ATTR_TO_FIELD: dict[str, str] = {
    'translate_x': 'translate_x',
    'translate_y': 'translate_y',
    'translate_z': 'translate_z',
    'rotate_x': 'rotate_x',
    'rotate_y': 'rotate_y',
    'rotate_z': 'rotate_z',
    'scale_x': 'scale_x',
    'scale_y': 'scale_y',
    'scale_z': 'scale_z',
    'translate_rate_x': 'translate_rate_x',
    'translate_rate_y': 'translate_rate_y',
    'translate_rate_z': 'translate_rate_z',
    'rotate_rate_x': 'rotate_rate_x',
    'rotate_rate_y': 'rotate_rate_y',
    'rotate_rate_z': 'rotate_rate_z',
    'scale_rate_x': 'scale_rate_x',
    'scale_rate_y': 'scale_rate_y',
    'scale_rate_z': 'scale_rate_z',
    'color_r': 'color_r',
    'color_g': 'color_g',
    'color_b': 'color_b',
    'color_a': 'color_a',
    'texture_id': 'texture_id',
    # --- shape ---
    'ratio': 'ratio',
    'topo': 'topo',
    'topo_scale': 'topo_scale',
    'geometry': 'geometry',
    'mesh_id': 'mesh_id',
    # --- palette color (resolved to color_r/g/b, see _resolve_palettes) ---
    'palette_id': 'palette_id',
    'color_index': 'color_index',
    # --- visibility ---
    'hide': 'hide',
    'show_text': 'show_text',
    # --- World node (type=0) scene settings ---
    'render_mode': 'render_mode',
    'fog_enabled': 'fog_enabled',
    'fog_start': 'fog_start',
    'fog_end': 'fog_end',
}

# Fields whose animation moves or reshapes geometry, so the viewport's
# playback fast path must refresh the bound node's matrices AND those of its
# whole subtree every frame (see transform_bound_node_ids).
#
#   ratio     — a parent's ratio sets its children's placement radius on
#               Torus/Ztorus (topology.py's pratio term).
#   topo      — a parent's topology is the entire child-placement rule; a
#               node's own topo also picks up Rod's draw-scale factors.
#   topo_scale — a parent's topo_scale scales how far its children's
#               distance-valued translate axes reach. Animating it alongside
#               topo is what lets a scene hold children in frame across a
#               switch between an angular and a linear topology, instead of
#               flinging them ~180x further out on the frame the topology
#               changes.
#   geometry  — normally cosmetic, but on a World Grid (type=6) sphere vs.
#               non-sphere geometry is what switches child placement between
#               globe (KML lon/lat) and flat window (Node.grid_is_globe).
#
# Everything else here (color, texture, mesh, palette, hide, show_text, the
# World scene settings) changes what is drawn but never where anything sits,
# so it does not cascade to descendants.
_TRANSFORM_FIELDS = frozenset({
    'translate_x', 'translate_y', 'translate_z',
    'rotate_x', 'rotate_y', 'rotate_z',
    'scale_x', 'scale_y', 'scale_z',
    'translate_rate_x', 'translate_rate_y', 'translate_rate_z',
    'rotate_rate_x', 'rotate_rate_y', 'rotate_rate_z',
    'scale_rate_x', 'scale_rate_y', 'scale_rate_z',
    'ratio', 'topo', 'topo_scale', 'geometry',
})

# Fields rounded to a whole number before being applied.
_INT_FIELDS = frozenset({
    'color_r', 'color_g', 'color_b', 'color_a',
    'texture_id', 'mesh_id',
    'topo', 'geometry', 'palette_id', 'color_index',
    'hide', 'show_text',
    'render_mode', 'fog_enabled',
})

# Value clamps applied after rounding. Every int field gets one; any int field
# absent from this table clamps to _NONNEGATIVE (an id that only has a floor).
# Float fields are left alone entirely — a track feeding translate_x or
# fog_end means exactly what it says.
_NONNEGATIVE = (0, float('inf'))
_FIELD_RANGE: dict[str, tuple[float, float]] = {
    'color_r': (0, 255),
    'color_g': (0, 255),
    'color_b': (0, 255),
    'color_a': (0, 255),
    'topo': (0, TOPO_COUNT - 1),
    'geometry': (0, GEO_COUNT - 1),
    'palette_id': (0, PALETTE_COUNT - 1),
    'render_mode': (0, RENDER_MODE_COUNT - 1),
    # Flags: any positive track value reads as "on".
    'hide': (0, 1),
    'show_text': (0, 1),
    'fog_enabled': (0, 1),
}

# Binding either of these makes the engine resolve (palette_id, color_index)
# into literal color_r/g/b each frame — the one place palette resolution
# happens automatically rather than on a =/-/Alt+= keypress (see
# color_palette.py's module docstring). A single track can then carry a
# musical quantity (pitch class, key, intensity) straight to a color.
_PALETTE_FIELDS = frozenset({'palette_id', 'color_index'})
_PALETTE_OUTPUT_FIELDS = ('color_r', 'color_g', 'color_b')

# Old-style ANTz column name for the channel-input-id field (stored in node.extras).
_CH_INPUT_KEYS = ('ch_input_id', 'np_ch_in_id', 'ch_input_id ')


def channel_id_of(node: Node) -> int:
    """The ch-map channel this node is bound to, or 0 for none.

    The first of _CH_INPUT_KEYS the node carries wins, whatever its value —
    an explicitly-present column is the node's answer even when unparseable,
    rather than a reason to keep looking under a different spelling.
    """
    for key in _CH_INPUT_KEYS:
        raw = node.extras.get(key)
        if raw is None:
            continue
        try:
            return int(float(raw))
        except (ValueError, TypeError):
            return 0
    return 0


def channel_ids_for_nodes(nodes) -> set[int]:
    """Every channel id referenced by `nodes` — what a partial scene export
    has to carry along to keep its animation (see selection_export)."""
    return {cid for cid in (channel_id_of(n) for n in nodes) if cid}


class ChannelEngine:
    """Applies time-series channel data to node attributes each animation frame."""

    def __init__(self):
        # (node, field_name, col_index, is_int, clamp_or_None)
        self._bindings: list[tuple[Node, str, int, bool, tuple | None]] = []
        self._tracks: np.ndarray | None = None
        # node.id → {field: original_value}  for reset()
        self._originals: dict[int, dict[str, object]] = {}
        # Nodes whose color is driven through the palette (see _PALETTE_FIELDS).
        self._palette_nodes: list[Node] = []
        self.frame_count: int = 0

    @property
    def has_bindings(self) -> bool:
        return bool(self._bindings)

    @property
    def bound_node_ids(self) -> set[int]:
        """Ids of every node with at least one channel binding."""
        return {node.id for node, *_rest in self._bindings}

    @property
    def transform_bound_node_ids(self) -> set[int]:
        """Ids of nodes with a binding that can move/reshape geometry — see
        _TRANSFORM_FIELDS. Color/texture/visibility bindings change draw
        content but never transforms, so they don't cascade to descendants."""
        return {node.id for node, field, *_rest in self._bindings
                if field in _TRANSFORM_FIELDS}

    def load(
        self,
        ch_map: dict[int, list[tuple[int, str]]],
        tracks: np.ndarray,
        id_to_col: dict[int, int],
        nodes: list[Node],
    ) -> None:
        self._bindings = []
        self._originals = {}
        self._palette_nodes = []
        self._tracks = tracks
        self.frame_count = len(tracks)
        palette_ids: set[int] = set()

        # Build channel_id → nodes mapping via node.extras ch_input_id
        nodes_by_ch: dict[int, list[Node]] = {}
        for node in nodes:
            ch_id = channel_id_of(node)
            if ch_id:
                nodes_by_ch.setdefault(ch_id, []).append(node)

        for ch_id, mappings in ch_map.items():
            for node in nodes_by_ch.get(ch_id, []):
                for track_id, attr in mappings:
                    field = _ATTR_TO_FIELD.get(attr)
                    if field is None:
                        continue
                    col = id_to_col.get(track_id)
                    if col is None:
                        continue
                    originals = self._originals.setdefault(node.id, {})
                    originals.setdefault(field, getattr(node, field))
                    is_int = field in _INT_FIELDS
                    clamp = _FIELD_RANGE.get(field, _NONNEGATIVE) if is_int else None
                    self._bindings.append((node, field, col, is_int, clamp))
                    if field in _PALETTE_FIELDS and node.id not in palette_ids:
                        palette_ids.add(node.id)
                        self._palette_nodes.append(node)
                        # Palette resolution overwrites color_r/g/b even
                        # though nothing bound them directly — snapshot them
                        # too so reset() can put the node back.
                        for out in _PALETTE_OUTPUT_FIELDS:
                            originals.setdefault(out, getattr(node, out))

    def apply_frame(self, frame: int) -> None:
        if self._tracks is None or not self._bindings:
            return
        frame = max(0, min(frame, self.frame_count - 1))
        row = self._tracks[frame]
        for node, field, col, is_int, clamp in self._bindings:
            val = float(row[col])
            if is_int:
                val = round(val)
            if clamp is not None:
                val = max(clamp[0], min(clamp[1], val))
            setattr(node, field, val)
        if self._palette_nodes:
            self._resolve_palettes()

    def _resolve_palettes(self) -> None:
        """(palette_id, color_index) → literal color_r/g/b, after every
        binding for this frame has been applied — so a channel driving both
        fields sees a consistent pair. Runs last, which also means a node
        that binds BOTH color_index and color_r/g/b resolves from the
        palette: the direct RGB binding is overwritten. color_a is never
        touched, matching ANTz palette semantics."""
        for node in self._palette_nodes:
            r, g, b = resolve_palette_color(node.palette_id, node.color_index)
            node.color_r, node.color_g, node.color_b = r, g, b

    def reset(self) -> None:
        """Restore all animated nodes to their original CSV values."""
        seen: set[int] = set()
        for node, *_rest in self._bindings:
            if node.id in seen:
                continue
            seen.add(node.id)
            for field, orig in self._originals.get(node.id, {}).items():
                setattr(node, field, orig)
