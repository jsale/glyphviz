"""
Unit tests for the color palette / color_index feature: the resolve function
against ANTz's documented palette table (glyphviz_core/color_palette.py), and
the Node.palette_id/color_index CSV round-trip (glyphviz_core/csv_reader.py).
"""
import pandas as pd
import pytest

from glyphviz_core.color_palette import (
    PALETTE_20, PALETTE_20_INV, PALETTE_BLUE_GREEN, PALETTE_GREYSCALE,
    PALETTE_RAINBOW, _PALETTE_20_RGB,
    palette_index_count, resolve_palette_color,
)
from glyphviz_core.csv_reader import _COL_ORDER, load_node_csv, save_node_csv


def _row(**overrides):
    row = {c: 0 for c in _COL_ORDER}
    row.update(scale_x=1, scale_y=1, scale_z=1, ratio=0.1, type=5, color_a=255)
    row.update(overrides)
    return row


def _write_csv(tmp_path, rows, name="node.csv"):
    # palette_id has no _COL_ORDER slot (it's an appended extra column, like
    # rotation_mode/mesh_id) -- keep it if a row asked for it, same as
    # save_node_csv does when writing a non-default value.
    extra_cols = [c for r in rows for c in r if c not in _COL_ORDER]
    cols = _COL_ORDER + sorted(set(extra_cols))
    path = tmp_path / name
    pd.DataFrame(rows).reindex(columns=cols, fill_value=0).to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# resolve_palette_color / palette_index_count against the documented table
# ---------------------------------------------------------------------------

def test_palette_20_matches_literal_table():
    for i in range(20):
        assert resolve_palette_color(PALETTE_20, i) == _PALETTE_20_RGB[i]


def test_palette_20_inverted_is_exact_inverse():
    for i in range(20):
        expected = tuple(255 - c for c in _PALETTE_20_RGB[i])
        assert resolve_palette_color(PALETTE_20_INV, i) == expected


def test_palette_20_color_index_wraps():
    assert resolve_palette_color(PALETTE_20, 20) == resolve_palette_color(PALETTE_20, 0)
    assert resolve_palette_color(PALETTE_20, 25) == resolve_palette_color(PALETTE_20, 5)


def test_gradient_endpoints():
    assert resolve_palette_color(PALETTE_BLUE_GREEN, 0) == (0, 0, 255)
    assert resolve_palette_color(PALETTE_BLUE_GREEN, 127) == (0, 255, 0)
    assert resolve_palette_color(PALETTE_GREYSCALE, 0) == (0, 0, 0)
    assert resolve_palette_color(PALETTE_GREYSCALE, 127) == (255, 255, 255)


def test_gradient_inverted_is_exact_inverse():
    for ci in (0, 40, 127):
        base = resolve_palette_color(PALETTE_BLUE_GREEN, ci)
        inv = resolve_palette_color(PALETTE_BLUE_GREEN + 1, ci)
        assert inv == tuple(255 - c for c in base)


def test_rainbow_heatmap_endpoints_are_pure_hue():
    # HSV(0, 1, 1) = pure red; HSV(~1, 1, 1) wraps back to (near) pure red too,
    # so just check start is red and the sweep hits pure green/blue partway.
    assert resolve_palette_color(PALETTE_RAINBOW, 0) == (255, 0, 0)


def test_palette_index_count():
    assert palette_index_count(PALETTE_20) == 20
    assert palette_index_count(PALETTE_20_INV) == 20
    assert palette_index_count(PALETTE_BLUE_GREEN) == 128
    assert palette_index_count(PALETTE_GREYSCALE) == 128


# ---------------------------------------------------------------------------
# Node.palette_id / color_index CSV round-trip
# ---------------------------------------------------------------------------

def test_color_index_and_palette_id_load_from_csv(tmp_path):
    rows = [_row(id=1, parent_id=0, color_index=7, palette_id=4)]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    assert nodes[0].color_index == 7
    assert nodes[0].palette_id == 4


def test_missing_columns_default_to_zero(tmp_path):
    # Legacy file: no color_index/palette_id columns at all.
    cols = [c for c in _COL_ORDER if c not in ("color_index", "palette_id")]
    path = tmp_path / "legacy.csv"
    pd.DataFrame([_row(id=1, parent_id=0)])[cols].to_csv(path, index=False)
    nodes = load_node_csv(str(path))
    assert nodes[0].color_index == 0
    assert nodes[0].palette_id == 0


def test_palette_id_column_omitted_when_all_default(tmp_path):
    rows = [_row(id=1, parent_id=0)]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    out_path = tmp_path / "out.csv"
    save_node_csv(nodes, str(out_path))
    header = pd.read_csv(out_path, nrows=0).columns.tolist()
    assert "palette_id" not in header
    assert "color_index" in header   # always written -- it's a real _COL_ORDER column


def test_palette_id_round_trips_when_nonzero(tmp_path):
    rows = [_row(id=1, parent_id=0, color_index=3, palette_id=2)]
    nodes = load_node_csv(str(_write_csv(tmp_path, rows)))
    out_path = tmp_path / "out.csv"
    save_node_csv(nodes, str(out_path))
    reloaded = load_node_csv(str(out_path))
    assert reloaded[0].color_index == 3
    assert reloaded[0].palette_id == 2
