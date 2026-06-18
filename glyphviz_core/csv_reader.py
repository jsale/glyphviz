import csv
import re as _re
from pathlib import Path

import pandas as pd

from .node import Node

# Columns that GlyphViz reads into explicit Node fields.
# Everything else in the CSV is stashed in Node.extras for round-trip preservation.
_TRACKED_COLS = frozenset({
    'id', 'type', 'parent_id', 'branch_level',
    'translate_x', 'translate_y', 'translate_z',
    'rotate_x', 'rotate_y', 'rotate_z',
    'scale_x', 'scale_y', 'scale_z',
    'color_r', 'color_g', 'color_b', 'color_a',
    'geometry', 'hide', 'topo', 'ratio', 'subspace', 'texture_id',
    'text', 'link',
})

# Extra columns written as plain strings (not int/float formatted).
_STRING_COLS = frozenset({'text', 'link'})

# Canonical 94-column ANTz/GaiaViz np_node column order.
_COL_ORDER = [
    'id', 'type', 'data', 'selected', 'parent_id', 'branch_level',
    'child_id', 'child_index', 'child_count',
    'ch_input_id', 'ch_output_id', 'ch_last_updated', 'average', 'samples',
    'aux_a_x', 'aux_a_y', 'aux_a_z',
    'aux_b_x', 'aux_b_y', 'aux_b_z',
    'color_shift',
    'rotate_vec_x', 'rotate_vec_y', 'rotate_vec_z', 'rotate_vec_s',
    'scale_x', 'scale_y', 'scale_z',
    'translate_x', 'translate_y', 'translate_z',
    'tag_offset_x', 'tag_offset_y', 'tag_offset_z',
    'rotate_rate_x', 'rotate_rate_y', 'rotate_rate_z',
    'rotate_x', 'rotate_y', 'rotate_z',
    'scale_rate_x', 'scale_rate_y', 'scale_rate_z',
    'translate_rate_x', 'translate_rate_y', 'translate_rate_z',
    'translate_vec_x', 'translate_vec_y', 'translate_vec_z',
    'shader', 'geometry', 'line_width', 'point_size', 'ratio',
    'color_index', 'color_r', 'color_g', 'color_b', 'color_a',
    'color_fade', 'texture_id', 'hide', 'freeze', 'topo', 'facet',
    'auto_zoom_x', 'auto_zoom_y', 'auto_zoom_z',
    'trigger_hi_x', 'trigger_hi_y', 'trigger_hi_z',
    'trigger_lo_x', 'trigger_lo_y', 'trigger_lo_z',
    'set_hi_x', 'set_hi_y', 'set_hi_z',
    'set_lo_x', 'set_lo_y', 'set_lo_z',
    'proximity_x', 'proximity_y', 'proximity_z',
    'proximity_mode_x', 'proximity_mode_y', 'proximity_mode_z',
    'segments_x', 'segments_y', 'segments_z',
    'tag_mode', 'format_id', 'table_id', 'record_id', 'size',
]

# Columns written as floats with 6 decimal places; all others are integers.
_FLOAT_COLS = frozenset({
    'aux_a_x', 'aux_a_y', 'aux_a_z',
    'aux_b_x', 'aux_b_y', 'aux_b_z',
    'color_shift',
    'rotate_vec_x', 'rotate_vec_y', 'rotate_vec_z', 'rotate_vec_s',
    'scale_x', 'scale_y', 'scale_z',
    'translate_x', 'translate_y', 'translate_z',
    'tag_offset_x', 'tag_offset_y', 'tag_offset_z',
    'rotate_rate_x', 'rotate_rate_y', 'rotate_rate_z',
    'rotate_x', 'rotate_y', 'rotate_z',
    'scale_rate_x', 'scale_rate_y', 'scale_rate_z',
    'translate_rate_x', 'translate_rate_y', 'translate_rate_z',
    'translate_vec_x', 'translate_vec_y', 'translate_vec_z',
    'line_width', 'point_size', 'ratio',
    'set_hi_x', 'set_hi_y', 'set_hi_z',
    'set_lo_x', 'set_lo_y', 'set_lo_z',
    'proximity_x', 'proximity_y', 'proximity_z',
})

# GaiaViz np_node.csv uses different names for a handful of columns that
# GlyphViz reads by name. Detected via the first header column ('np_node_id')
# and remapped to the ANTz names below so the rest of the loader is unchanged.
# Everything else (translate/rotate/scale/color/hide/ratio/subspace, plus the
# tag and channel files) already shares column names across both formats.
_GAIAVIZ_NODE_COL_ALIASES = {
    'np_node_id': 'id',
    'np_geometry_id': 'geometry',
    'np_topo_id': 'topo',
    'np_texture_id': 'texture_id',
}

# Defaults for untracked columns when a node has no extras (e.g. newly created).
_DEFAULT_EXTRAS: dict = {
    'data': 0,          # overridden to node.id in save_node_csv
    'selected': 0,
    'child_id': 0, 'child_index': 0, 'child_count': 0,
    'ch_input_id': 0, 'ch_output_id': 0, 'ch_last_updated': 0,
    'average': 0, 'samples': 1,
    'aux_a_x': 0.0, 'aux_a_y': 0.0, 'aux_a_z': 0.0,
    'aux_b_x': 0.0, 'aux_b_y': 0.0, 'aux_b_z': 0.0,
    'color_shift': 0.0,
    'rotate_vec_x': 0.0, 'rotate_vec_y': 0.0,
    'rotate_vec_z': 0.0, 'rotate_vec_s': 0.0,
    'tag_offset_x': 0.0, 'tag_offset_y': 0.0, 'tag_offset_z': 0.0,
    'rotate_rate_x': 0.0, 'rotate_rate_y': 0.0, 'rotate_rate_z': 0.0,
    'scale_rate_x': 0.0, 'scale_rate_y': 0.0, 'scale_rate_z': 0.0,
    'translate_rate_x': 0.0, 'translate_rate_y': 0.0, 'translate_rate_z': 0.0,
    'translate_vec_x': 0.0, 'translate_vec_y': 0.0, 'translate_vec_z': 0.0,
    'shader': 0,
    'line_width': 1.0, 'point_size': 0.0,
    'color_index': 0, 'color_fade': 0, 'texture_id': 0,
    'freeze': 0, 'facet': 0,
    'auto_zoom_x': 0, 'auto_zoom_y': 0, 'auto_zoom_z': 0,
    'trigger_hi_x': 0, 'trigger_hi_y': 0, 'trigger_hi_z': 0,
    'trigger_lo_x': 0, 'trigger_lo_y': 0, 'trigger_lo_z': 0,
    'set_hi_x': 0.0, 'set_hi_y': 0.0, 'set_hi_z': 0.0,
    'set_lo_x': 0.0, 'set_lo_y': 0.0, 'set_lo_z': 0.0,
    'proximity_x': 0.0, 'proximity_y': 0.0, 'proximity_z': 0.0,
    'proximity_mode_x': 0, 'proximity_mode_y': 0, 'proximity_mode_z': 0,
    'segments_x': 16, 'segments_y': 16, 'segments_z': 0,
    'tag_mode': 0, 'format_id': 0, 'table_id': 0, 'record_id': 0,
    'size': 420,
}


def _tag_file_path(node_csv_path: str) -> Path | None:
    """Return the companion tag-file path for a node CSV, or None if not applicable.

    Convention (ANTz): anything ending in 'node' → replace with 'tag'.
    E.g. antz0001node.csv → antz0001tag.csv, np_node.csv → np_tag.csv.
    Returns None if the candidate file does not exist.
    """
    p = Path(node_csv_path)
    stem = p.stem
    if stem.endswith('node'):
        candidate = p.parent / (stem[:-4] + 'tag' + p.suffix)
        return candidate if candidate.exists() else None
    return None


def _load_tag_file(tag_path: Path) -> dict[int, tuple[str, str]]:
    """Parse an ANTz np_tag CSV.  Returns {record_id: (text, link)}.

    title field parsing:
      - HTML <a href="url">label</a> → link=url, text=label
      - Plain URL (http/https/www) → link=url, text=url
      - Anything else → link='', text=value
    """
    try:
        df = pd.read_csv(tag_path)
    except Exception:
        return {}
    result: dict[int, tuple[str, str]] = {}
    for _, row in df.iterrows():
        try:
            record_id = int(row['record_id'])
            table_id = int(row.get('table_id', 0))
            if table_id != 0:
                continue
            raw = str(row.get('title', '') or '').strip().strip('"')
            m = _re.search(
                r'<a\s+href=["\']?([^"\'>\s]+)["\']?>([^<]*)</a>',
                raw, _re.IGNORECASE,
            )
            if m:
                link = m.group(1).strip('\'"')
                text = m.group(2).strip() or raw
            elif raw.startswith(('http://', 'https://', 'www.', 'ftp://')):
                link = raw
                text = raw
            else:
                link = ''
                text = raw
            result[record_id] = (text, link)
        except (ValueError, KeyError):
            continue
    return result


def load_node_csv(path: str) -> list[Node]:
    df = pd.read_csv(path)
    if len(df.columns) and df.columns[0] == 'np_node_id':
        df = df.rename(columns=_GAIAVIZ_NODE_COL_ALIASES)
    has_ratio = 'ratio' in df.columns
    has_subspace = 'subspace' in df.columns
    has_texture_id = 'texture_id' in df.columns
    has_text = 'text' in df.columns
    has_link = 'link' in df.columns

    # Fall back to companion tag file only when neither inline column is present.
    tag_data: dict[int, tuple[str, str]] = {}
    if not has_text and not has_link:
        tag_path = _tag_file_path(path)
        if tag_path:
            tag_data = _load_tag_file(tag_path)

    nodes = []
    for _, row in df.iterrows():
        node = Node(
            id=int(row['id']),
            type=int(row['type']),
            parent_id=int(row['parent_id']),
            branch_level=int(row['branch_level']),
            translate_x=float(row['translate_x']),
            translate_y=float(row['translate_y']),
            translate_z=float(row['translate_z']),
            rotate_x=float(row['rotate_x']),
            rotate_y=float(row['rotate_y']),
            rotate_z=float(row['rotate_z']),
            scale_x=float(row['scale_x']),
            scale_y=float(row['scale_y']),
            scale_z=float(row['scale_z']),
            color_r=int(row['color_r']),
            color_g=int(row['color_g']),
            color_b=int(row['color_b']),
            color_a=int(row['color_a']),
            geometry=int(row['geometry']),
            hide=int(row['hide']),
            topo=int(row['topo']),
            ratio=float(row['ratio']) if has_ratio else 0.1,
            subspace=int(row['subspace']) if has_subspace else 0,
            texture_id=int(row['texture_id']) if has_texture_id else 0,
        )
        # Preserve all untracked columns so save_node_csv can round-trip them.
        node.extras = {
            col: row[col]
            for col in df.columns
            if col not in _TRACKED_COLS
        }
        # Populate text / link from inline columns or companion tag file.
        if has_text:
            v = row.get('text')
            node.text = '' if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v)
        if has_link:
            v = row.get('link')
            node.link = '' if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v)
        if tag_data and not has_text and not has_link:
            # Match by record_id (column 92) if available, else fall back to id.
            rid = int(node.extras.get('record_id', node.id))
            entry = tag_data.get(rid) or tag_data.get(node.id)
            if entry:
                node.text, node.link = entry
        nodes.append(node)
    return nodes


def save_node_csv(nodes: list[Node], path: str) -> None:
    """Write nodes to a GaiaViz/ANTz 94-column np_node CSV.

    Tracked fields (position, rotation, scale, color, geo, topo, hide, ratio)
    reflect the current in-memory values.  All other columns are written from
    Node.extras (preserving the original file values) or from _DEFAULT_EXTRAS
    for newly-created nodes.

    If any node has non-empty text or link, those columns are appended after
    the 94-column ANTz standard set (ANTz tools ignore unknown extra columns).
    """
    has_text = any(n.text for n in nodes)
    has_link = any(n.link for n in nodes)
    col_order = list(_COL_ORDER)
    if has_text:
        col_order.append('text')
    if has_link:
        col_order.append('link')

    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(col_order)
        for node in nodes:
            # Build row: defaults → preserved extras → current tracked values.
            row: dict = dict(_DEFAULT_EXTRAS)
            row.update(node.extras)
            row['data'] = node.id       # 'data' mirrors 'id' by convention
            row['id'] = node.id
            row['type'] = node.type
            row['parent_id'] = node.parent_id
            row['branch_level'] = node.branch_level
            row['translate_x'] = node.translate_x
            row['translate_y'] = node.translate_y
            row['translate_z'] = node.translate_z
            row['rotate_x'] = node.rotate_x
            row['rotate_y'] = node.rotate_y
            row['rotate_z'] = node.rotate_z
            row['scale_x'] = node.scale_x
            row['scale_y'] = node.scale_y
            row['scale_z'] = node.scale_z
            row['color_r'] = node.color_r
            row['color_g'] = node.color_g
            row['color_b'] = node.color_b
            row['color_a'] = node.color_a
            row['geometry'] = node.geometry
            row['hide'] = node.hide
            row['topo'] = node.topo
            row['ratio'] = node.ratio
            row['texture_id'] = node.texture_id
            if has_text:
                row['text'] = node.text
            if has_link:
                row['link'] = node.link

            # Format each cell: strings as-is, floats with 6 dp, others as int.
            cells = []
            for col in col_order:
                val = row.get(col, 0)
                if col in _STRING_COLS:
                    cells.append(str(val) if val else '')
                elif col in _FLOAT_COLS:
                    cells.append(f'{float(val):.6f}')
                else:
                    cells.append(int(float(val)))
            writer.writerow(cells)
