import numpy as np

from .node import Node

# Maps attribute names from the ch-map to Node dataclass fields.
# Attributes not listed here are skipped (e.g. translate_rate_* which require
# velocity integration — a future feature).
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
    'color_r': 'color_r',
    'color_g': 'color_g',
    'color_b': 'color_b',
    'color_a': 'color_a',
}

_INT_FIELDS = frozenset({'color_r', 'color_g', 'color_b', 'color_a'})

# Old-style ANTz column name for the channel-input-id field (stored in node.extras).
_CH_INPUT_KEYS = ('ch_input_id', 'np_ch_in_id', 'ch_input_id ')


class ChannelEngine:
    """Applies time-series channel data to node attributes each animation frame."""

    def __init__(self):
        # (node, field_name, col_index, is_int)
        self._bindings: list[tuple[Node, str, int, bool]] = []
        self._tracks: np.ndarray | None = None
        # node.id → {field: original_value}  for reset()
        self._originals: dict[int, dict[str, object]] = {}
        self.frame_count: int = 0

    @property
    def has_bindings(self) -> bool:
        return bool(self._bindings)

    def load(
        self,
        ch_map: dict[int, list[tuple[int, str]]],
        tracks: np.ndarray,
        id_to_col: dict[int, int],
        nodes: list[Node],
    ) -> None:
        self._bindings = []
        self._originals = {}
        self._tracks = tracks
        self.frame_count = len(tracks)

        # Build channel_id → nodes mapping via node.extras ch_input_id
        nodes_by_ch: dict[int, list[Node]] = {}
        for node in nodes:
            ch_id = 0
            for key in _CH_INPUT_KEYS:
                raw = node.extras.get(key)
                if raw is not None:
                    try:
                        ch_id = int(float(raw))
                    except (ValueError, TypeError):
                        pass
                    break
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
                    if node.id not in self._originals:
                        self._originals[node.id] = {}
                    if field not in self._originals[node.id]:
                        self._originals[node.id][field] = getattr(node, field)
                    is_int = field in _INT_FIELDS
                    self._bindings.append((node, field, col, is_int))

    def apply_frame(self, frame: int) -> None:
        if self._tracks is None or not self._bindings:
            return
        frame = max(0, min(frame, self.frame_count - 1))
        row = self._tracks[frame]
        for node, field, col, is_int in self._bindings:
            val = float(row[col])
            if is_int:
                val = max(0, min(255, round(val)))
            setattr(node, field, val)

    def reset(self) -> None:
        """Restore all animated nodes to their original CSV values."""
        for node, field, _col, _is_int in self._bindings:
            orig = self._originals.get(node.id, {}).get(field)
            if orig is not None:
                setattr(node, field, orig)
