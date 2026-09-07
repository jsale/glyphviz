import csv
import re as _re
from datetime import datetime
from pathlib import Path

import pandas as pd

from .node import (
    Node, DEFAULT_TOPO_SCALE, ROTATION_MODE_HEADING_TILT_ROLL,
    RENDER_MODE_NORMAL,
    TAG_COLOR_MODE_UNIFORM, TAG_DEFAULT_TEXT_RGB, TAG_DEFAULT_FONT_SIZE,
    REF_GRID_DEFAULT_RGB,
)

# Columns that GlyphViz reads into explicit Node fields.
# Everything else in the CSV is stashed in Node.extras for round-trip preservation.
_TRACKED_COLS = frozenset({
    'id', 'type', 'parent_id', 'branch_level',
    'translate_x', 'translate_y', 'translate_z',
    'rotate_x', 'rotate_y', 'rotate_z',
    'scale_x', 'scale_y', 'scale_z',
    'color_r', 'color_g', 'color_b', 'color_a', 'color_index', 'palette_id',
    'geometry', 'hide', 'topo', 'ratio', 'topo_scale', 'subspace', 'facet',
    'texture_id',
    'mesh_id', 'text', 'link', 'rotation_mode', 'show_text',
    'render_mode', 'fog_enabled', 'fog_start', 'fog_end',
    'tag_color_mode', 'tag_color_r', 'tag_color_g', 'tag_color_b',
    'tag_font_size',
    'ref_grid_color_r', 'ref_grid_color_g', 'ref_grid_color_b',
    'translate_rate_x', 'translate_rate_y', 'translate_rate_z',
    'rotate_rate_x', 'rotate_rate_y', 'rotate_rate_z',
    'scale_rate_x', 'scale_rate_y', 'scale_rate_z',
})

# Extra columns written as plain strings (not int/float formatted).
_STRING_COLS = frozenset({'text', 'link'})

# Columns written with significant-figure rather than fixed-decimal
# precision. topo_scale is a MULTIPLIER whose useful range spans several
# orders of magnitude (1.0 down to TOPO_SCALE_ANTZ = 1/180 and below), where
# a fixed 6 decimal places would quietly round 0.00555555… to four
# significant figures. Every other float column holds a coordinate or a 0..1
# proportion, for which 6 dp is ample.
_PRECISE_FLOAT_COLS = frozenset({'topo_scale'})

# Columns written as ints when the value is integral, 6-dp floats otherwise.
# The trigger fields are historically integer-formatted (and every legacy
# file holds 0 there, which must keep round-tripping byte-identically), but
# GlyphViz's World Grid stores its lon/lat extents window in them (see
# Node.grid_extents) and fractional extents like -117.5 must not truncate.
_INT_OR_FLOAT_COLS = frozenset({
    'trigger_hi_x', 'trigger_hi_y', 'trigger_hi_z',
    'trigger_lo_x', 'trigger_lo_y', 'trigger_lo_z',
})

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


def unstamped_stem(path: str | Path) -> str:
    """A file's stem with any trailing YYYYMMDDHHMMSS save stamp removed, so
    a name derived from an already-saved file doesn't carry the old stamp
    into the middle of the new one."""
    return _TIMESTAMP_RE.sub('', Path(path).stem)


def companion_tag_path(node_csv_path: str | Path) -> Path | None:
    """The tag-file path a node CSV pairs with, whether or not it exists yet.

    Convention (ANTz): a stem ending in 'node' → 'tag'. None when the stem
    doesn't end in 'node', i.e. there is no sensible companion name to
    derive. For WRITING a companion (Save Selection As…); readers want
    _tag_file_path below, which additionally requires the file to be there.
    """
    p = Path(node_csv_path)
    tag_stem = _swap_node_tag_stem(p.stem, 'tag')
    return None if tag_stem is None else p.parent / (tag_stem + p.suffix)


def _tag_file_path(node_csv_path: str) -> Path | None:
    """Return the companion tag-file path for a node CSV, or None if not applicable.

    Convention (ANTz): anything ending in 'node' → replace with 'tag'.
    E.g. antz0001node.csv → antz0001tag.csv, gv_node.csv → gv_tag.csv,
    np_node.csv → np_tag.csv.
    Returns None if the candidate file does not exist.
    """
    candidate = companion_tag_path(node_csv_path)
    if candidate is None:
        return None
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
    base_stem = unstamped_stem(p)
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
        # dtype=str on the title, for the same reason load_node_csv reads
        # text/link as str: inference rewrites numeric titles (years, ids,
        # ranks) — "2024" comes back as "2024.0" once any title cell is blank.
        # Harmless when the column is absent; pandas ignores dtype keys it
        # doesn't find.
        df = pd.read_csv(tag_path, dtype={'title': str})
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
    #
    # text/link are read as str explicitly, so the label is the characters in
    # the file rather than pandas' idea of them. Left to inference, a numeric
    # label column (hours, years, ranks, station ids) is rewritten: with any
    # blank cell it becomes float64 and "12" loads as "12.0"; without one it
    # becomes int64 and "007" loads as "7"; decimals lose trailing zeros. The
    # blank is what makes it bite in practice — every real scene has unlabelled
    # rows (a World row, hub frames), so a scene labelled 1..12 hits the
    # float64 case every time. And since save_node_csv writes Node.text back
    # out verbatim, one open+save persists the rewrite into the user's file.
    # dtype keys for columns the file lacks are ignored, so this is safe for
    # the many scenes with no labels at all. Blank cells still arrive as NaN
    # and are still emptied by the isna() guard below.
    df = pd.read_csv(path, dtype={'text': str, 'link': str})
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
    color_indices = _int_col(df, 'color_index', n, 0)
    # palette_id has no slot in the ANTz 94-column layout (see node.py); missing
    # column means 0 (the default 20-distinct-colors palette) on reload, same
    # value a fresh Node() gets -- symmetric, unlike rotation_mode's fallback.
    palette_ids   = _int_col(df, 'palette_id', n, 0)
    geometries = df['geometry'].astype('int64').tolist()
    hides      = df['hide'].astype('int64').tolist()
    topos      = df['topo'].astype('int64').tolist()

    ratios      = _float_col(df, 'ratio', n, 0.1)
    # A missing topo_scale column is every file written before the field
    # existed; 1.0 means "a translate unit is a world unit", which is how such
    # a file has always rendered. Symmetric with the Node() default, so no
    # asymmetric-fallback subtlety here (unlike rotation_mode above).
    topo_scales = _float_col(df, 'topo_scale', n, DEFAULT_TOPO_SCALE)
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
    # show_text / tag_color_* have no ANTz/GaiaViz column slot (see node.py).
    # A missing column means the same value a fresh Node() gets, so the
    # fallbacks here are symmetric with the dataclass defaults (unlike
    # rotation_mode, whose fallback deliberately differs).
    show_texts     = _int_col(df, 'show_text', n, 0)
    render_modes   = _int_col(df, 'render_mode', n, RENDER_MODE_NORMAL)
    fog_enableds   = _int_col(df, 'fog_enabled', n, 0)
    fog_starts     = _float_col(df, 'fog_start', n, 0.0)
    fog_ends       = _float_col(df, 'fog_end', n, 0.0)
    tag_color_modes = _int_col(df, 'tag_color_mode', n, TAG_COLOR_MODE_UNIFORM)
    tag_color_rs    = _int_col(df, 'tag_color_r', n, TAG_DEFAULT_TEXT_RGB[0])
    tag_color_gs    = _int_col(df, 'tag_color_g', n, TAG_DEFAULT_TEXT_RGB[1])
    tag_color_bs    = _int_col(df, 'tag_color_b', n, TAG_DEFAULT_TEXT_RGB[2])
    # A file with no tag_font_size column predates the setting, so it loads at
    # the current default rather than the 9 pt labels were hardcoded to — the
    # point of raising the default is that old scenes get the bigger type too.
    tag_font_sizes  = _int_col(df, 'tag_font_size', n, TAG_DEFAULT_FONT_SIZE)
    grid_color_rs   = _int_col(df, 'ref_grid_color_r', n, REF_GRID_DEFAULT_RGB[0])
    grid_color_gs   = _int_col(df, 'ref_grid_color_g', n, REF_GRID_DEFAULT_RGB[1])
    grid_color_bs   = _int_col(df, 'ref_grid_color_b', n, REF_GRID_DEFAULT_RGB[2])
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
            color_index=color_indices[i], palette_id=palette_ids[i],
            geometry=geometries[i],
            hide=hides[i],
            topo=topos[i],
            ratio=ratios[i],
            topo_scale=topo_scales[i],
            subspace=subspaces[i],
            texture_id=texture_ids[i],
            mesh_id=mesh_ids[i],
            rotation_mode=rotation_modes[i],
            show_text=show_texts[i],
            render_mode=render_modes[i],
            fog_enabled=fog_enableds[i],
            fog_start=fog_starts[i],
            fog_end=fog_ends[i],
            tag_color_mode=tag_color_modes[i],
            tag_color_r=tag_color_rs[i],
            tag_color_g=tag_color_gs[i],
            tag_color_b=tag_color_bs[i],
            tag_font_size=tag_font_sizes[i],
            ref_grid_color_r=grid_color_rs[i],
            ref_grid_color_g=grid_color_gs[i],
            ref_grid_color_b=grid_color_bs[i],
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


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
#
# GlyphViz writes the MINIMAL native dialect by default: the columns a scene
# actually uses, and no others. The canonical 94-column ANTz/GaiaViz layout is
# still available (save_node_csv(..., compact=False)) for a file that has to
# round-trip through ANTz tooling, but it is no longer what the app saves --
# a node row in it is ~550 bytes whether or not a node uses twenty of its
# fields, which turned a 442k-point LIDAR scan into a 244 MB scene file.
#
# The rule for what gets written is unchanged from the old writer's handling of
# its extension columns, just applied to every column now: a column is written
# only when omitting it would make some node reload as a DIFFERENT value. A
# column whose values are all covered by load_node_csv's documented default is
# information-free and is left out. That is what keeps a scene column-stable
# across a load/save round trip instead of accreting columns.
#
# This matches GlyphViz Web's writer (glyphviz-web/src/gv/writeNodeCsv.ts), so
# the two apps produce the same file for the same scene.

def _num(v) -> str:
    """A float column's cell: 6 decimal places, trailing zeros trimmed.

    6 dp is the precision every GlyphViz writer has always used; what the trim
    saves is the padding, which is most of the file. A scene's numbers are
    overwhelmingly whole (a translate of 0, a scale of 1, a color-driven
    layout on integer coordinates), and '0.000000' is eight bytes to say '0'.
    Reload is unaffected -- pandas parses either spelling to the same float --
    and it roughly halves a large scene on disk.

    Written as string surgery rather than a value test so a NaN or an inf that
    somehow reached a node field still writes as 'nan'/'inf' the way the
    94-column writer did, instead of raising mid-save.
    """
    s = f'{v:.6f}'
    if s[-1] == '0' and '.' in s:
        s = s.rstrip('0')
        if s[-1] == '.':
            s = s[:-1]
        # A value that rounds to zero at 6 dp has no meaningful sign, and the
        # generators that produce them (an epicycle's cos at 90 degrees lands
        # on -1.2e-17) sprinkle them through a scene. Writing '-0' also made
        # the writer non-idempotent, since pandas reads that cell back as a
        # positive zero.
        if s == '-0':
            s = '0'
    return s


# Always written: the 20 columns load_node_csv requires, plus `ratio` and
# `facet` -- the 22-column shape this repo's own hand-authored example scenes
# use, and what GlyphViz Web emits.
_COMPACT_BASE: tuple[tuple[str, object], ...] = (
    ('id',            lambda n: n.id),
    ('type',          lambda n: n.type),
    ('parent_id',     lambda n: n.parent_id),
    ('branch_level',  lambda n: n.branch_level),
    ('translate_x',   lambda n: _num(n.translate_x)),
    ('translate_y',   lambda n: _num(n.translate_y)),
    ('translate_z',   lambda n: _num(n.translate_z)),
    ('rotate_x',      lambda n: _num(n.rotate_x)),
    ('rotate_y',      lambda n: _num(n.rotate_y)),
    ('rotate_z',      lambda n: _num(n.rotate_z)),
    ('scale_x',       lambda n: _num(n.scale_x)),
    ('scale_y',       lambda n: _num(n.scale_y)),
    ('scale_z',       lambda n: _num(n.scale_z)),
    ('color_r',       lambda n: n.color_r),
    ('color_g',       lambda n: n.color_g),
    ('color_b',       lambda n: n.color_b),
    ('color_a',       lambda n: n.color_a),
    ('geometry',      lambda n: n.geometry),
    ('hide',          lambda n: n.hide),
    ('topo',          lambda n: n.topo),
    ('ratio',         lambda n: _num(n.ratio)),
    # `facet` is the on-disk (1-indexed) spelling of Node.subspace.
    ('facet',         lambda n: n.subspace + 1),
)

# Optional tracked columns, each keyed by the name _needed_columns() uses to
# report that the scene needs it. Several are groups written all-or-nothing:
# a rate triple, the fog settings and the two color triples are each ONE
# setting, and writing only the component that happens to differ would reload
# as a mix of authored and default values.
_COMPACT_OPTIONAL: tuple[tuple[str, tuple[tuple[str, object], ...]], ...] = (
    ('topo_scale',     (('topo_scale', lambda n: f'{float(n.topo_scale):.10g}'),)),
    ('texture_id',     (('texture_id', lambda n: n.texture_id),)),
    ('mesh_id',        (('mesh_id', lambda n: n.mesh_id),)),
    ('rotation_mode',  (('rotation_mode', lambda n: n.rotation_mode),)),
    ('color_index',    (('color_index', lambda n: n.color_index),)),
    ('palette_id',     (('palette_id', lambda n: n.palette_id),)),
    ('translate_rate', (('translate_rate_x', lambda n: _num(n.translate_rate_x)),
                        ('translate_rate_y', lambda n: _num(n.translate_rate_y)),
                        ('translate_rate_z', lambda n: _num(n.translate_rate_z)))),
    ('rotate_rate',    (('rotate_rate_x', lambda n: _num(n.rotate_rate_x)),
                        ('rotate_rate_y', lambda n: _num(n.rotate_rate_y)),
                        ('rotate_rate_z', lambda n: _num(n.rotate_rate_z)))),
    ('scale_rate',     (('scale_rate_x', lambda n: _num(n.scale_rate_x)),
                        ('scale_rate_y', lambda n: _num(n.scale_rate_y)),
                        ('scale_rate_z', lambda n: _num(n.scale_rate_z)))),
    ('text',           (('text', lambda n: str(n.text) if n.text else ''),)),
    ('link',           (('link', lambda n: str(n.link) if n.link else ''),)),
    ('show_text',      (('show_text', lambda n: n.show_text),)),
    ('render_mode',    (('render_mode', lambda n: n.render_mode),)),
    ('fog',            (('fog_enabled', lambda n: n.fog_enabled),
                        ('fog_start', lambda n: _num(n.fog_start)),
                        ('fog_end', lambda n: _num(n.fog_end)))),
    ('tag_color_mode', (('tag_color_mode', lambda n: n.tag_color_mode),)),
    ('tag_color',      (('tag_color_r', lambda n: n.tag_color_r),
                        ('tag_color_g', lambda n: n.tag_color_g),
                        ('tag_color_b', lambda n: n.tag_color_b))),
    ('tag_font_size',  (('tag_font_size', lambda n: n.tag_font_size),)),
    ('ref_grid_color', (('ref_grid_color_r', lambda n: n.ref_grid_color_r),
                        ('ref_grid_color_g', lambda n: n.ref_grid_color_g),
                        ('ref_grid_color_b', lambda n: n.ref_grid_color_b))),
)

_OPTIONAL_COUNT = len(_COMPACT_OPTIONAL)

def _same_value(a, b) -> bool:
    """True when an extras cell holds the value a MISSING column would give.

    Compared numerically where both sides parse as numbers -- a legacy file's
    '0' and a default of 0 are the same absent column -- and by text
    otherwise, so an unparseable cell is never mistaken for a default.
    """
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


def _needed_columns(nodes: list[Node]) -> set[str]:
    """Which of _COMPACT_OPTIONAL's groups this scene actually needs.

    One fused pass rather than an `any()` sweep per group: an all-default
    scene answers "no" to every question, so every sweep would run to the end,
    and a point-cloud scene is 400k+ nodes.
    """
    need: set[str] = set()
    add = need.add
    for n in nodes:
        # Omitting the column means ROTATION_MODE_HEADING_TILT_ROLL on reload
        # (see load_node_csv), so the column is needed whenever a node's value
        # would be *misread* by that fallback -- not merely when it's nonzero.
        # This one asymmetric default is why old files stay column-stable.
        if n.rotation_mode != ROTATION_MODE_HEADING_TILT_ROLL:
            add('rotation_mode')
        if n.topo_scale != DEFAULT_TOPO_SCALE:
            add('topo_scale')
        if n.texture_id:
            add('texture_id')
        if n.mesh_id:
            add('mesh_id')
        if n.color_index:
            add('color_index')
        if n.palette_id:
            add('palette_id')
        if n.translate_rate_x or n.translate_rate_y or n.translate_rate_z:
            add('translate_rate')
        if n.rotate_rate_x or n.rotate_rate_y or n.rotate_rate_z:
            add('rotate_rate')
        if n.scale_rate_x or n.scale_rate_y or n.scale_rate_z:
            add('scale_rate')
        if n.text:
            add('text')
        if n.link:
            add('link')
        if n.show_text:
            add('show_text')
        # World-row-only scene settings from here down.
        if n.render_mode != RENDER_MODE_NORMAL:
            add('render_mode')
        if n.fog_enabled or n.fog_start or n.fog_end:
            add('fog')
        if n.tag_color_mode != TAG_COLOR_MODE_UNIFORM:
            add('tag_color_mode')
        if (n.tag_color_r, n.tag_color_g, n.tag_color_b) != TAG_DEFAULT_TEXT_RGB:
            add('tag_color')
        if n.tag_font_size != TAG_DEFAULT_FONT_SIZE:
            add('tag_font_size')
        if (n.ref_grid_color_r, n.ref_grid_color_g,
                n.ref_grid_color_b) != REF_GRID_DEFAULT_RGB:
            add('ref_grid_color')
        if len(need) == _OPTIONAL_COUNT:
            break
    return need


def _fmt_extra(val) -> str:
    """Format an extras cell for writing: verbatim, minus pandas' float cast.

    An extras value is whatever the source file held, so it goes back out as
    text rather than being coerced to int the way a known column is -- a
    third-party column may hold anything. The one adjustment is that pandas
    reads every numeric column as float64, so an integral value writes as
    '10', not '10.0', and a blank cell (NaN) writes back blank.
    """
    if val is None:
        return ''
    if isinstance(val, float):
        if val != val:          # NaN: the blank cell it was read from
            return ''
        if val.is_integer():
            return str(int(val))
    return str(val)


def _extras_columns(nodes: list[Node]) -> list[str]:
    """Untracked columns worth carrying, in first-seen order.

    Same rule as the tracked columns: a column every node fills with the value
    load_node_csv would supply for a MISSING column carries nothing, so it is
    dropped -- this is what shrinks a scene that was previously saved in the
    94-column dialect, where 60-odd such columns were written as zeros.
    Anything with no documented default (a genuinely foreign column) is kept
    verbatim, because there is no way to know what its absence would mean.
    """
    names: list[str] = []
    seen: set[str] = set()
    for n in nodes:
        for key in n.extras:
            if key not in seen and key not in _TRACKED_COLS:
                seen.add(key)
                names.append(key)

    # Two extras columns mirror the node's own id, which is exactly what
    # load_node_csv assumes when they are absent: 'record_id' is the tag
    # file's join key and falls back to the node's id (see load_node_csv and
    # save_tag_csv), and 'data' is ANTz's id mirror, which nothing in
    # GlyphViz reads at all.
    keep: list[str] = []
    for name in names:
        if name == 'record_id':
            informative = any(
                not _same_value(n.extras.get('record_id', n.id), n.id) for n in nodes)
        elif name == 'data':
            informative = any(
                not (_same_value(n.extras.get('data', n.id), n.id)
                     or _same_value(n.extras.get('data', 0), 0))
                for n in nodes)
        elif name in _DEFAULT_EXTRAS:
            default = _DEFAULT_EXTRAS[name]
            informative = any(
                not _same_value(n.extras.get(name, default), default) for n in nodes)
        else:
            informative = True
        if informative:
            keep.append(name)
    return keep


def save_node_csv(nodes: list[Node], path: str, compact: bool = True) -> None:
    """Write nodes to a GlyphViz node CSV.

    By default this is the MINIMAL native dialect: the 22 base columns, plus
    each optional column the scene actually uses, plus any untracked column
    from Node.extras that still carries information. A column whose values are
    all covered by load_node_csv's documented default is omitted rather than
    written out as a row of zeros, so re-saving a scene never grows its column
    set and a scene of 400k simple nodes costs ~150 bytes a row instead of
    ~550. Columns are written by name and the loader reads by name, so the
    file round-trips exactly.

    Pass compact=False for the canonical 94-column ANTz/GaiaViz layout (with
    GlyphViz extension columns appended after it), for a file that has to be
    read by ANTz/GaiaViz tooling.
    """
    if not compact:
        _save_node_csv_antz(nodes, path)
        return

    columns: list[tuple[str, object]] = list(_COMPACT_BASE)
    needed = _needed_columns(nodes)
    for name, cols in _COMPACT_OPTIONAL:
        if name in needed:
            columns.extend(cols)
    for name in _extras_columns(nodes):
        if name == 'record_id':
            columns.append((name, lambda n: _fmt_extra(n.extras.get('record_id', n.id))))
        else:
            fill = _DEFAULT_EXTRAS.get(name, '')
            columns.append(
                (name, lambda n, _n=name, _f=fill: _fmt_extra(n.extras.get(_n, _f))))

    getters = [get for _, get in columns]
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([name for name, _ in columns])
        writer.writerows([get(n) for get in getters] for n in nodes)


def _save_node_csv_antz(nodes: list[Node], path: str) -> None:
    """Write nodes in the canonical 94-column ANTz/GaiaViz layout.

    Tracked fields (position, rotation, scale, color, geo, topo, hide, ratio)
    reflect the current in-memory values.  All other columns are written from
    Node.extras (preserving the original file values) or from _DEFAULT_EXTRAS
    for newly-created nodes.

    Columns with no slot in the 94-column ANTz standard set (text/link,
    rotation_mode, show_text, the World node's tag_color_* styling, ...) are
    appended after it, and only when some node's value would otherwise be
    misread by load_node_csv's fallback for a missing column -- so untouched
    legacy files stay byte-for-byte stable. ANTz tools ignore unknown extra
    columns. Note that a foreign column from Node.extras with no slot in the
    94 is NOT written by this path (the compact writer does carry those).
    """
    has_text = any(n.text for n in nodes)
    has_link = any(n.link for n in nodes)
    has_rotation_mode = any(n.rotation_mode != ROTATION_MODE_HEADING_TILT_ROLL for n in nodes)
    has_mesh_id = any(n.mesh_id for n in nodes)
    has_palette_id = any(n.palette_id for n in nodes)
    has_render_mode = any(n.render_mode != RENDER_MODE_NORMAL for n in nodes)
    has_fog_enabled = any(n.fog_enabled for n in nodes)
    has_fog_start = any(n.fog_start for n in nodes)
    has_fog_end = any(n.fog_end for n in nodes)
    has_tag_color_mode = any(n.tag_color_mode != TAG_COLOR_MODE_UNIFORM for n in nodes)
    has_tag_color = any(
        (n.tag_color_r, n.tag_color_g, n.tag_color_b) != TAG_DEFAULT_TEXT_RGB
        for n in nodes
    )
    has_tag_font_size = any(n.tag_font_size != TAG_DEFAULT_FONT_SIZE for n in nodes)
    has_ref_grid_color = any(
        (n.ref_grid_color_r, n.ref_grid_color_g, n.ref_grid_color_b) != REF_GRID_DEFAULT_RGB
        for n in nodes
    )
    has_show_text = any(n.show_text for n in nodes)
    has_topo_scale = any(n.topo_scale != DEFAULT_TOPO_SCALE for n in nodes)
    col_order = list(_COL_ORDER)
    if has_text:
        col_order.append('text')
    if has_link:
        col_order.append('link')
    if has_rotation_mode:
        col_order.append('rotation_mode')
    if has_mesh_id:
        col_order.append('mesh_id')
    if has_palette_id:
        col_order.append('palette_id')
    if has_render_mode:
        col_order.append('render_mode')
    if has_fog_enabled:
        col_order.append('fog_enabled')
    if has_fog_start:
        col_order.append('fog_start')
    if has_fog_end:
        col_order.append('fog_end')
    if has_show_text:
        col_order.append('show_text')
    if has_topo_scale:
        col_order.append('topo_scale')
    if has_tag_color_mode:
        col_order.append('tag_color_mode')
    if has_tag_color:
        col_order.extend(('tag_color_r', 'tag_color_g', 'tag_color_b'))
    if has_tag_font_size:
        col_order.append('tag_font_size')
    if has_ref_grid_color:
        col_order.extend(('ref_grid_color_r', 'ref_grid_color_g', 'ref_grid_color_b'))

    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(col_order)
        for node in nodes:
            # Build row: defaults -> preserved extras -> current tracked values.
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
            row['color_index'] = node.color_index
            row['geometry'] = node.geometry
            row['hide'] = node.hide
            row['topo'] = node.topo
            row['ratio'] = node.ratio
            row['facet'] = node.subspace + 1
            row['texture_id'] = node.texture_id
            if has_mesh_id:
                row['mesh_id'] = node.mesh_id
            if has_palette_id:
                row['palette_id'] = node.palette_id
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
            if has_show_text:
                row['show_text'] = node.show_text
            if has_topo_scale:
                row['topo_scale'] = node.topo_scale
            if has_tag_color_mode:
                row['tag_color_mode'] = node.tag_color_mode
            if has_tag_color:
                row['tag_color_r'] = node.tag_color_r
                row['tag_color_g'] = node.tag_color_g
                row['tag_color_b'] = node.tag_color_b
            if has_tag_font_size:
                row['tag_font_size'] = node.tag_font_size
            if has_ref_grid_color:
                row['ref_grid_color_r'] = node.ref_grid_color_r
                row['ref_grid_color_g'] = node.ref_grid_color_g
                row['ref_grid_color_b'] = node.ref_grid_color_b

            # Format each cell: strings as-is, floats with 6 dp, others as int.
            cells = []
            for col in col_order:
                val = row.get(col, 0)
                if col in _STRING_COLS:
                    cells.append(str(val) if val else '')
                elif col in _FLOAT_COLS:
                    cells.append(f'{float(val):.6f}')
                elif col in _PRECISE_FLOAT_COLS:
                    cells.append(f'{float(val):.10g}')
                elif col in _INT_OR_FLOAT_COLS:
                    v = float(val)
                    cells.append(int(v) if v.is_integer() else f'{v:.6f}')
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
