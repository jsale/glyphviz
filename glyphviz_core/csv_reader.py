import csv
import re as _re
from datetime import datetime
from pathlib import Path

import pandas as pd

from .node import Node, ROTATION_MODE_HEADING_TILT_ROLL, RENDER_MODE_NORMAL

# Columns that GlyphViz reads into explicit Node fields.
# Everything else in the CSV is stashed in Node.extras for round-trip preservation.
_TRACKED_COLS = frozenset({
    'id', 'type', 'parent_id', 'branch_level',
    'translate_x', 'translate_y', 'translate_z',
    'rotate_x', 'rotate_y', 'rotate_z',
    'scale_x', 'scale_y', 'scale_z',
    'color_r', 'color_g', 'color_b', 'color_a',
    'geometry', 'hide', 'topo', 'ratio', 'subspace', 'facet', 'texture_id',
    'mesh_id', 'text', 'link', 'rotation_mode',
    'render_mode', 'fog_enabled', 'fog_start', 'fog_end',
    'translate_rate_x', 'translate_rate_y', 'translate_rate_z',
    'rotate_rate_x', 'rotate_rate_y', 'rotate_rate_z',
    'scale_rate_x', 'scale_rate_y', 'scale_rate_z',
})

# Extra columns written as plain strings (not int/float formatted).
_STRING_COLS = frozenset({'text', 'link'})

# Canonical 94-column ANTz/GaiaViz node CSV column order.
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
    'fog_start', 'fog_end',
})

# GaiaViz np_node.csv uses different names for a handful of columns that
# GlyphViz reads by name. Detected via the first header column ('np_node_id')
# and remapped to the ANTz names below so the rest of the loader is unchanged.
# Everything else (translate/rotate/scale/color/hide/ratio, plus the tag and
# channel files) already shares column names across both formats. 'subspace'
# is the one tracked field whose *name* still differs: GaiaViz's np_ dialect
# spells it 'subspace' (0-indexed, face id matches Node.subspace directly),
# while legacy ANTz dialect (and the canonical 94-column layout this module
# writes — see _COL_ORDER) spells it 'facet' (1-indexed: facet 1 = +X face =
# subspace 0, ... facet 6 = -Z face = subspace 5). load_node_csv checks for
# 'subspace' first and falls back to 'facet' - 1 so real legacy-ANTz Cube-
# topology files (which only ever have a 'facet' column) aren't silently
# stuck at subspace 0 for every child.
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
    'translate_vec_x': 0.0, 'translate_vec_y': 0.0, 'translate_vec_z': 0.0,
    'shader': 0,
    'line_width': 1.0, 'point_size': 0.0,
    'color_index': 0, 'color_fade': 0, 'texture_id': 0,
    'freeze': 0,
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


_TIMESTAMP_RE = _re.compile(r'\d{14}$')
_TIMESTAMP_FORMAT = '%Y%m%d%H%M%S'   # YYYYMMDDHHMMSS, no delimiters


def _swap_node_tag_stem(stem: str, target: str) -> str | None:
    """Swap the 'node'/'tag' infix in a node-CSV stem, per ANTz/gv_ convention.

    E.g. 'gv_node' -> 'gv_tag', 'topology_example_gv_node' -> '..._gv_tag'.
    Returns None if the stem doesn't end with 'node' (no sensible swap).
    """
    if stem.endswith('node'):
        return stem[:-4] + target
    return None


def _tag_file_path(node_csv_path: str) -> Path | None:
    """Return the companion tag-file path for a node CSV, or None if not applicable.

    Convention (ANTz): anything ending in 'node' → replace with 'tag'.
    E.g. antz0001node.csv → antz0001tag.csv, gv_node.csv → gv_tag.csv,
    np_node.csv → np_tag.csv.
    Returns None if the candidate file does not exist.
    """
    p = Path(node_csv_path)
    tag_stem = _swap_node_tag_stem(p.stem, 'tag')
    if tag_stem is None:
        return None
    candidate = p.parent / (tag_stem + p.suffix)
    return candidate if candidate.exists() else None


def stamp_node_and_tag_paths(node_path: str | Path) -> tuple[Path, Path | None]:
    """Given a desired node-CSV path, return (stamped_node_path, stamped_tag_path)
    sharing one freshly-generated timestamp (YYYYMMDDHHMMSS, no delimiters).

    Any timestamp already trailing the stem (from a prior save this session)
    is stripped first, so repeated calls advance the stamp instead of stacking
    one onto the next. The tag path is None when the (unstamped) stem doesn't
    end in 'node' — there's no sensible 'tag' counterpart name to derive.
    """
    p = Path(node_path)
    base_stem = _TIMESTAMP_RE.sub('', p.stem)
    stamp = datetime.now().strftime(_TIMESTAMP_FORMAT)
    node_out = p.parent / f'{base_stem}{stamp}{p.suffix}'
    tag_stem = _swap_node_tag_stem(base_stem, 'tag')
    tag_out = p.parent / f'{tag_stem}{stamp}{p.suffix}' if tag_stem is not None else None
    return node_out, tag_out


def _load_tag_file(tag_path: Path) -> dict[int, tuple[str, str]]:
    """Parse an ANTz/GaiaViz-style tag CSV (gv_tag.csv or np_tag.csv).

    Returns {record_id: (text, link)}.

    title field parsing:
      - HTML <a href="url">label</a> → link=url, text=label
      - Plain URL (http/https/www) → link=url, text=url
      - Anything else → link='', text=value
    """
    try:
        df = pd.read_csv(tag_path)
    except Exception:
        return {}
    if 'record_id' not in df.columns:
        return {}
    n = len(df)
    record_ids = df['record_id'].tolist()
    table_ids = df['table_id'].tolist() if 'table_id' in df.columns else [0] * n
    titles = df['title'].tolist() if 'title' in df.columns else [''] * n
    result: dict[int, tuple[str, str]] = {}
    for record_id, table_id, title in zip(record_ids, table_ids, titles):
        try:
            record_id = int(record_id)
            table_id = int(table_id)
        except (ValueError, TypeError):
            continue
        if table_id != 0:
            continue
        raw = str(title or '').strip().strip('"')
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
    return result


def _int_col(df: pd.DataFrame, col: str, n: int, default: int) -> list[int]:
    """Column as a list of Python ints (astype truncates toward zero, matching
    int()), or n copies of the default when the column is absent."""
    if col in df.columns:
        return df[col].astype('int64').tolist()
    return [default] * n


def _float_col(df: pd.DataFrame, col: str, n: int, default: float) -> list[float]:
    """Column as a list of Python floats, or n copies of the default when absent."""
    if col in df.columns:
        return df[col].astype('float64').tolist()
    return [default] * n


def load_node_csv(path: str) -> list[Node]:
    # Whole columns are converted up front (astype/tolist run in C) and the
    # per-node loop indexes plain Python lists — iterating pandas rows instead
    # spends ~98% of load time on Series construction/indexing at 100k rows.
    df = pd.read_csv(path)
    if len(df.columns) and df.columns[0] == 'np_node_id':
        df = df.rename(columns=_GAIAVIZ_NODE_COL_ALIASES)
    n = len(df)
    has_text = 'text' in df.columns
    has_link = 'link' in df.columns

    # Fall back to companion tag file only when neither inline column is present.
    tag_data: dict[int, tuple[str, str]] = {}
    if not has_text and not has_link:
        tag_path = _tag_file_path(path)
        if tag_path:
            tag_data = _load_tag_file(tag_path)

    ids          = df['id'].astype('int64').tolist()
    types        = df['type'].astype('int64').tolist()
    parent_ids   = df['parent_id'].astype('int64').tolist()
    branch_levels = df['branch_level'].astype('int64').tolist()
    tx = df['translate_x'].astype('float64').tolist()
    ty = df['translate_y'].astype('float64').tolist()
    tz = df['translate_z'].astype('float64').tolist()
    rx = df['rotate_x'].astype('float64').tolist()
    ry = df['rotate_y'].astype('float64').tolist()
    rz = df['rotate_z'].astype('float64').tolist()
    sx = df['scale_x'].astype('float64').tolist()
    sy = df['scale_y'].astype('float64').tolist()
    sz = df['scale_z'].astype('float64').tolist()
    cr = df['color_r'].astype('int64').tolist()
    cg = df['color_g'].astype('int64').tolist()
    cb = df['color_b'].astype('int64').tolist()
    ca = df['color_a'].astype('int64').tolist()
    geometries = df['geometry'].astype('int64').tolist()
    hides      = df['hide'].astype('int64').tolist()
    topos      = df['topo'].astype('int64').tolist()

    ratios      = _float_col(df, 'ratio', n, 0.1)
    if 'subspace' in df.columns:
        subspaces = df['subspace'].astype('int64').tolist()
    elif 'facet' in df.columns:
        subspaces = (df['facet'].astype('int64') - 1).clip(lower=0).tolist()
    else:
        subspaces = [0] * n
    texture_ids = _int_col(df, 'texture_id', n, 0)
    mesh_ids    = _int_col(df, 'mesh_id', n, 0)
    # Missing rotation_mode column means a pre-existing file authored under
    # ANTz's only-ever convention; default to it so old files keep rendering
    # exactly as before. New Node() calls elsewhere get EULER_XYZ via the
    # dataclass default instead.
    rotation_modes = _int_col(df, 'rotation_mode', n, ROTATION_MODE_HEADING_TILT_ROLL)
    render_modes   = _int_col(df, 'render_mode', n, RENDER_MODE_NORMAL)
    fog_enableds   = _int_col(df, 'fog_enabled', n, 0)
    fog_starts     = _float_col(df, 'fog_start', n, 0.0)
    fog_ends       = _float_col(df, 'fog_end', n, 0.0)
    trx = _float_col(df, 'translate_rate_x', n, 0.0)
    try_ = _float_col(df, 'translate_rate_y', n, 0.0)
    trz = _float_col(df, 'translate_rate_z', n, 0.0)
    rrx = _float_col(df, 'rotate_rate_x', n, 0.0)
    rry = _float_col(df, 'rotate_rate_y', n, 0.0)
    rrz = _float_col(df, 'rotate_rate_z', n, 0.0)
    srx = _float_col(df, 'scale_rate_x', n, 0.0)
    sry = _float_col(df, 'scale_rate_y', n, 0.0)
    srz = _float_col(df, 'scale_rate_z', n, 0.0)

    # Untracked columns, preserved per-node so save_node_csv can round-trip them.
    extras_cols = [c for c in df.columns if c not in _TRACKED_COLS]
    extras_rows = list(zip(*(df[c].tolist() for c in extras_cols))) if extras_cols else None

    text_vals = df['text'].tolist() if has_text else None
    link_vals = df['link'].tolist() if has_link else None

    nodes = []
    for i in range(n):
        node = Node(
            id=ids[i],
            type=types[i],
            parent_id=parent_ids[i],
            branch_level=branch_levels[i],
            translate_x=tx[i], translate_y=ty[i], translate_z=tz[i],
            rotate_x=rx[i], rotate_y=ry[i], rotate_z=rz[i],
            scale_x=sx[i], scale_y=sy[i], scale_z=sz[i],
            color_r=cr[i], color_g=cg[i], color_b=cb[i], color_a=ca[i],
            geometry=geometries[i],
            hide=hides[i],
            topo=topos[i],
            ratio=ratios[i],
            subspace=subspaces[i],
            texture_id=texture_ids[i],
            mesh_id=mesh_ids[i],
            rotation_mode=rotation_modes[i],
            render_mode=render_modes[i],
            fog_enabled=fog_enableds[i],
            fog_start=fog_starts[i],
            fog_end=fog_ends[i],
            translate_rate_x=trx[i], translate_rate_y=try_[i], translate_rate_z=trz[i],
            rotate_rate_x=rrx[i], rotate_rate_y=rry[i], rotate_rate_z=rrz[i],
            scale_rate_x=srx[i], scale_rate_y=sry[i], scale_rate_z=srz[i],
        )
        if extras_rows is not None:
            node.extras = dict(zip(extras_cols, extras_rows[i]))
        # Populate text / link from inline columns or companion tag file.
        if has_text:
            v = text_vals[i]
            node.text = '' if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v)
        if has_link:
            v = link_vals[i]
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
    """Write nodes to a GaiaViz/ANTz-compatible 94-column node CSV.

    Tracked fields (position, rotation, scale, color, geo, topo, hide, ratio)
    reflect the current in-memory values.  All other columns are written from
    Node.extras (preserving the original file values) or from _DEFAULT_EXTRAS
    for newly-created nodes.

    If any node has non-empty text/link, or a non-default rotation_mode,
    those columns are appended after the 94-column ANTz standard set (ANTz
    tools ignore unknown extra columns).
    """
    has_text = any(n.text for n in nodes)
    has_link = any(n.link for n in nodes)
    # Omitting the column means "ROTATION_MODE_HEADING_TILT_ROLL" on reload
    # (see load_node_csv), so the column is needed whenever a node's value
    # would be *misread* by that fallback — not merely when it's non-zero.
    has_rotation_mode = any(n.rotation_mode != ROTATION_MODE_HEADING_TILT_ROLL for n in nodes)
    # mesh_id has no ANTz/GaiaViz equivalent; omitting the column means 0 on
    # reload (no mesh selected), so it only needs writing when some node
    # actually references an imported mesh.
    has_mesh_id = any(n.mesh_id for n in nodes)
    # World-node-only scene settings (see node.py); omitting a column means
    # "default" on reload, so each is only written when some node's value
    # would actually be misread by that fallback.
    has_render_mode = any(n.render_mode != RENDER_MODE_NORMAL for n in nodes)
    has_fog_enabled = any(n.fog_enabled for n in nodes)
    has_fog_start = any(n.fog_start for n in nodes)
    has_fog_end = any(n.fog_end for n in nodes)
    col_order = list(_COL_ORDER)
    if has_text:
        col_order.append('text')
    if has_link:
        col_order.append('link')
    if has_rotation_mode:
        col_order.append('rotation_mode')
    if has_mesh_id:
        col_order.append('mesh_id')
    if has_render_mode:
        col_order.append('render_mode')
    if has_fog_enabled:
        col_order.append('fog_enabled')
    if has_fog_start:
        col_order.append('fog_start')
    if has_fog_end:
        col_order.append('fog_end')

    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(col_order)
        for node in nodes:
            # Build row: defaults → preserved extras → current tracked values.
            row: dict = dict(_DEFAULT_EXTRAS)
            row.update(node.extras)
            row['data'] = node.id       # 'data' mirrors 'id' by convention
            row['id'] = node.id
            # 'record_id' defaults to the node's own id (matching load_node_csv's
            # tag-lookup fallback) rather than _DEFAULT_EXTRAS's bare 0, so a
            # freshly-created node's tag can still be matched by record_id.
            row['record_id'] = node.extras.get('record_id', node.id)
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
            row['facet'] = node.subspace + 1
            row['texture_id'] = node.texture_id
            if has_mesh_id:
                row['mesh_id'] = node.mesh_id
            row['translate_rate_x'] = node.translate_rate_x
            row['translate_rate_y'] = node.translate_rate_y
            row['translate_rate_z'] = node.translate_rate_z
            row['rotate_rate_x'] = node.rotate_rate_x
            row['rotate_rate_y'] = node.rotate_rate_y
            row['rotate_rate_z'] = node.rotate_rate_z
            row['scale_rate_x'] = node.scale_rate_x
            row['scale_rate_y'] = node.scale_rate_y
            row['scale_rate_z'] = node.scale_rate_z
            if has_text:
                row['text'] = node.text
            if has_link:
                row['link'] = node.link
            if has_rotation_mode:
                row['rotation_mode'] = node.rotation_mode
            if has_render_mode:
                row['render_mode'] = node.render_mode
            if has_fog_enabled:
                row['fog_enabled'] = node.fog_enabled
            if has_fog_start:
                row['fog_start'] = node.fog_start
            if has_fog_end:
                row['fog_end'] = node.fog_end

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


def save_tag_csv(nodes: list[Node], path: str) -> None:
    """Write a gv_tag.csv/np_tag.csv companion file: one row per node that has
    a non-empty text or link, in the 'id,table_id,record_id,title' shape this
    project's own example data already uses (see examples/*/*_gv_tag.csv) —
    table_id is always 0 (the GaiaViz tag-table id), record_id matches the
    node CSV's record_id/id (see save_node_csv), and title is the inverse of
    _load_tag_file's decode: an HTML <a href> anchor when a link is set, else
    plain text.
    """
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, lineterminator='\r\n')
        writer.writerow(['id', 'table_id', 'record_id', 'title'])
        tag_id = 0
        for node in nodes:
            if not node.text and not node.link:
                continue
            title = f'<a href="{node.link}">{node.text}</a>' if node.link else node.text
            record_id = node.extras.get('record_id', node.id)
            writer.writerow([tag_id, 0, record_id, title])
            tag_id += 1
