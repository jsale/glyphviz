"""Label text must survive load, and load→save, exactly as authored.

`load_node_csv` reads the file with pandas, which *infers* each column's type,
and the loader then stringifies whatever it gets. So pandas' idea of the value
— not the characters in the file — becomes the label. Measured behaviour of an
inferred `text` column:

    all numerals, no blank cell   int64    "12"   -> "12"     (survives)
    numerals + ANY blank cell     float64  "12"   -> "12.0"   <- the reported bug
    leading zeros                 int64    "007"  -> "7"
    decimals w/ trailing zeros    float64  "1.50" -> "1.5"
    one non-numeric value present object   "12"   -> "12"     (survives)

The blank cell is what makes this bite in practice rather than in theory: real
scenes always have unlabelled rows (a type=0 World row, hub/frame nodes), so a
scene labelling its glyphs `1`…`12` lands in the float64 row every time.

And it is not merely a rendering nit — `save_node_csv` writes `Node.text` back
out verbatim, so one open-and-save (File > Save, or the K key) persists the
rewritten label into the user's own file and the authored `12` is gone. Hence
the round-trip test, not just a load test.

Fix: `dtype={'text': str, 'link': str}` on the node read, and `{'title': str}`
on the companion tag file read.
"""
import pandas as pd
import pytest

from glyphviz_core.csv_reader import load_node_csv, save_node_csv

COLS = [
    "id", "type", "parent_id", "branch_level",
    "translate_x", "translate_y", "translate_z",
    "rotate_x", "rotate_y", "rotate_z",
    "scale_x", "scale_y", "scale_z",
    "color_r", "color_g", "color_b", "color_a",
    "geometry", "hide", "topo",
]

# Twelve numeric labels plus one unlabelled row — the shape of every real
# scene, and the shape that triggers float64 inference.
HOURS = [str(h) for h in range(1, 13)]
HOURS_WITH_BLANK = HOURS + [""]


def _rows(n, **extra_cols):
    """n minimal glyph rows, plus whatever extra columns are passed as lists."""
    base = {c: [0] * n for c in COLS}
    base["id"] = list(range(1, n + 1))
    base["type"] = [5] * n
    base["color_a"] = [255] * n
    base["geometry"] = [19] * n
    for k, v in extra_cols.items():
        base[k] = v
    return pd.DataFrame(base)


def _write(df, path):
    df.to_csv(path, index=False, lineterminator="\r\n", encoding="utf-8")
    return str(path)


def test_numeric_labels_load_as_authored(tmp_path):
    """The reported bug: numeric labels alongside at least one unlabelled row."""
    path = _write(_rows(13, text=HOURS_WITH_BLANK), tmp_path / "gv_node.csv")
    assert [n.text for n in load_node_csv(path)] == HOURS_WITH_BLANK


def test_numeric_labels_survive_a_save_round_trip(tmp_path):
    """The expensive half — whatever the loader read is written back to disk."""
    src = _write(_rows(13, text=HOURS_WITH_BLANK), tmp_path / "gv_node.csv")
    out = tmp_path / "gv_node_saved.csv"
    save_node_csv(load_node_csv(src), str(out))

    on_disk = pd.read_csv(out, dtype=str)["text"].tolist()
    assert [("" if pd.isna(v) else v) for v in on_disk] == HOURS_WITH_BLANK
    # and a second trip is still stable
    assert [n.text for n in load_node_csv(str(out))] == HOURS_WITH_BLANK


def test_blank_label_cells_still_become_empty_strings(tmp_path):
    """dtype=str must not turn a missing label into the string "nan"."""
    labels = ["12", "", "10", ""]
    path = _write(_rows(4, text=labels), tmp_path / "gv_node.csv")
    assert [n.text for n in load_node_csv(path)] == labels


def test_numeric_links_are_not_reformatted(tmp_path):
    """`link` has the same inference problem (a bare numeric filename)."""
    links = ["2024", "", "2025"]
    path = _write(_rows(3, text=["a", "b", "c"], link=links), tmp_path / "gv_node.csv")
    assert [n.link for n in load_node_csv(path)] == links


def test_file_without_label_columns_still_loads(tmp_path):
    """dtype keys naming absent columns must not break the many unlabelled
    scenes — this is what makes the fix safe as an unconditional argument."""
    path = _write(_rows(3), tmp_path / "gv_node.csv")
    nodes = load_node_csv(path)
    assert len(nodes) == 3
    assert [n.text for n in nodes] == ["", "", ""]


def test_leading_zeros_and_trailing_decimals_are_preserved(tmp_path):
    """Inference rewrites the digits themselves, blanks or no blanks:
    007 -> 7 via int64, 1.50 -> 1.5 via float64."""
    labels = ["007", "1.50", "2.0"]
    path = _write(_rows(3, text=labels), tmp_path / "gv_node.csv")
    assert [n.text for n in load_node_csv(path)] == labels


def test_numeric_titles_in_a_companion_tag_file(tmp_path):
    """Same inference bug on the tag file's `title` column."""
    node_path = tmp_path / "gv_node.csv"
    _write(_rows(3), node_path)
    pd.DataFrame({
        "id": [1, 2, 3],
        "table_id": [0, 0, 0],
        "record_id": [1, 2, 3],
        "title": ["1999", "", "2001"],
    }).to_csv(tmp_path / "gv_tag.csv", index=False, lineterminator="\r\n",
              encoding="utf-8")

    texts = [n.text for n in load_node_csv(str(node_path))]
    assert texts[0] == "1999" and texts[2] == "2001"
    assert "." not in texts[0] and "." not in texts[2]


@pytest.mark.parametrize("labels", [
    HOURS_WITH_BLANK,
    ["1999", "", "2000"],
    ["0", "", "1"],
])
def test_no_label_ever_gains_a_decimal_point(tmp_path, labels):
    path = _write(_rows(len(labels), text=labels), tmp_path / "gv_node.csv")
    assert not any("." in n.text for n in load_node_csv(path))
