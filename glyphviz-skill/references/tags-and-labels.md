# Tags and labels — inline `text`/`link` and `gv_tag.csv`

Verified against `glyphviz_core/csv_reader.py` and `glyphviz_gl/viewport.py`
/ `main_window.py` (2026-07-18; pinning and tag color 2026-07-26; font
size 2026-08-18).
Behaviors are machine-checked through the
real loader/saver.

## Two authoring paths (inline wins)

1. **Inline columns** (recommended for generated data; GlyphViz-only):
   add `text` and/or `link` columns to the node CSV itself. `text` is the
   label drawn in the 3D viewport; `link` is what the U key opens. Empty
   cells are fine (they load as ""). On save, GlyphViz appends these as
   extension columns after the canonical 94 — only when some node actually
   has a value.
2. **Companion tag file** (`gv_tag.csv`; ANTz/GaiaViz-compatible): a
   separate CSV holding one row per labeled node.

Precedence is absolute: **if the node CSV has a `text` or `link` column
(even one of them), the companion tag file is never consulted.** Use inline
for new data; produce a tag file only when the scene must round-trip
through ANTz/GaiaViz tooling.

## Companion tag file format

- **Naming**: the node file's stem with its trailing `node` swapped for
  `tag` — `gv_node.csv` ↔ `gv_tag.csv`,
  `myscene_gv_node20260718094500.csv` ↔ `myscene_gv_tag20260718094500.csv`.
  A node filename whose stem doesn't end in `node` has no derivable tag
  name, so no tag file is looked for (or written). Auto-loaded on open from
  the same folder.
- **Columns**: `id, table_id, record_id, title`.
  - `id` — row counter (0-based in GlyphViz-written files).
  - `table_id` — **must be 0**; any other value makes GlyphViz ignore the
    row.
  - `record_id` — matched against the node CSV's `record_id` column
    (falling back to the node's `id`). GlyphViz's saver defaults
    `record_id` to the node's own id, so matching by node id Just Works
    for generated data.
  - `title` — one of three encodings:

| `title` value | Result |
|---|---|
| `<a href="URL">Label</a>` | `link` = URL, `text` = Label |
| bare URL (`http://`, `https://`, `www.`, `ftp://`) | `link` = `text` = the URL |
| anything else | `text` = the value, no link |

GlyphViz writes the anchor form whenever a node has a link, else plain
text; CRLF line endings.

**Encoding gotcha (important)**: the tag file is parsed with pandas — one
malformed byte or stray control character in any title can make the parse
fail and **silently drop every tag in the file** (the scene still loads,
unlabeled). Always write UTF-8 explicitly and strip control characters
from label text. Also avoid literal `"None"`/`"NA"`-style titles — pandas
NA-token parsing can eat them.

## Display behavior in the app

- Tag labels are **off by default**. Toggle: `T` key, View menu, or the
  Display panel's "Show Tag Labels" checkbox.
- "Show Tag Labels of Selected" mode restricts labels to the current
  selection.
- **Pinned labels** (`show_text` = 1 on the node): draw whenever the node
  draws, regardless of both settings above — even with tag display
  entirely off. Set it in the CSV, or select nodes and tick "Always Show
  Text" in the Selected Node panel (works on a multi-node selection; a
  mixed selection shows the box partially-checked). Use it for the few
  labels a scene should always show — a legend, axis ends, the outlier
  worth naming — not as a way to label thousands of nodes.
- **The 500-tag cap** (not a bug, and not a string-length limit): in
  show-all mode, at most **500 tags are drawn per frame** — the first 500
  eligible tagged nodes in file order. It's a frame-rate safety valve for
  pathological cases (thousands of simultaneously labeled nodes);
  ordinary scenes with tens-to-hundreds of tags never hit it. In
  **selected-only mode the cap deliberately does not apply** — every
  selected tag draws, because the user explicitly scoped the set.
  **Pinned labels are exempt** for the same reason. If a generated scene
  labels thousands of nodes, tell users to use selected-only mode to see
  any specific subset in full.
- Eligibility: hidden nodes (unless Show Hidden) and World/Camera rows
  never draw tags — pinning does not override either, nor the `\` draw
  limit. Label text length itself is not limited — see "How long can a
  label be?" below for what that means in practice.
- **Link (type=7) nodes carry labels too**, under exactly the same
  settings — global toggle, selected-only, `show_text` pinning, and both
  color modes (a link's label takes the *link's* own `color_r/g/b` under
  match-node-color). A link's label anchors to the **middle of the edge**
  it draws; a malformed link with no resolvable B-end falls back to its
  own position, which is where it sits for click-picking too. Links are
  not subject to the `\` draw limit, so neither are their labels. Use
  edge labels for weights, relationship types, flow volumes.
- **Color**: labels are pastel yellow (255, 255, 200) over a fixed dark
  drop shadow. The World node's `tag_color_r/g/b` changes that single
  color scene-wide, and `tag_color_mode` = 1 instead draws each label in
  its own node's `color_r/g/b` — useful when glyphs are already colored by
  category. Both are in the Display panel ("Tag Color", "Tag Text Matches
  Node Color"). The drop shadow is deliberately not configurable: it is
  what keeps text legible on both bright glyphs and bright backgrounds.
- **Size**: labels draw at 11 pt unless the World node's `tag_font_size`
  says otherwise (6-36; out-of-range values clamp on render). Like the
  colors this is scene data, so a scene's labels are the size its author
  chose — set it from the Display panel's "Tag Text Size" slider, or write
  the column directly. Generated data rarely needs to: 11 pt is the
  default precisely because it reads at a normal working camera distance.
  Reach for a bigger size when a scene is meant to be read from across a
  room (a demo on a projector) and a smaller one when many labels crowd
  each other. Point size is fixed on screen, so labels do NOT shrink with
  distance — a dense scene gets more legible by labelling fewer nodes
  (`show_text` on the ones that matter), not by shrinking the type.
- Perf note: text layout is cached **per unique string** — 10,000 nodes
  sharing 200 distinct labels paint far cheaper than 10,000 unique
  strings. Prefer short, shared labels where the data allows.

## How long can a label be?

There is **no limit in the format** and **no limit in the loader**. Verified by
round-tripping real strings through the loader and saver: labels of 10 through
**10,000,000** characters load exactly and survive a save-and-reload unchanged,
inline `text` and companion-file `title` alike (a 10M-character label is a 10 MB
file that loads in ~0.12 s). Neither reader has a field-size cap — both use
pandas, not Python's `csv` reader, which is the one with a 131,072-byte default.
Commas, quotes, newlines and non-ASCII inside a label all survive both
directions exactly; CSV quoting handles them.

**The real limit is the screen, and it is measured in pixels, not characters.**
A label is drawn as a **single-line** run at Segoe UI 9pt, starting just right
of the node's screen position. Nothing truncates, elides, or wraps it — a long
label simply runs off the right edge of the window with no indication that more
text is there.

| Window width | Label characters that fit |
|---|---|
| 1280 px | ~237 |
| 1920 px | ~356 |
| 2560 px | ~475 |

(~5.4 px per character of ordinary mixed-case text, 16 px line height.)

Layout cost is linear and cached per unique string, so length is paid once per
distinct label: 10,000 characters costs ~3 ms to lay out and ~0.8 ms/frame to
paint; 100,000 characters costs ~28 ms the first frame it appears — a visible
hitch. That cache clears past 100,000 distinct strings.

**Newlines are silently swallowed.** A CSV field can legally contain a line
break, it round-trips through GlyphViz perfectly, and it renders as one line
with the break simply gone — `"a\nb"` lays out byte-identically to `"ab"`.
**There is no multi-line label.** Don't design one; use several pinned labels on
separate nodes if you need stacked text. (A tab does the opposite of nothing —
one expands to ~87 px of gap.)

**Authoring guidance:** keep labels to roughly **40–80 characters** to stay
readable beside a glyph; a few hundred is where it is running off-screen for
most users. When the text is genuinely long, put it in the **`link`** column
instead and let the U key open it — that is what `link` is for.

## Links: the U key and Alt+click

With exactly **one** node selected, `U` opens its `link`; **Alt+click**
on a node in the viewport does the same in one gesture (it selects the
node, then opens its link). Either way:

- `http://`, `https://`, `ftp://` → default browser; `www.` gets
  `https://` prefixed automatically.
- **Anything else is treated as a local file path** and opened with the
  OS's default application — this is the "app-launch" encoding: a path to
  a document launches its viewer, a path to an executable runs it.
  Relative paths resolve against the app's working directory, so prefer
  absolute paths or URLs in generated data.

## Saving (app behavior, for completeness)

- Save / Save As write a timestamped node CSV; a "save tag file" checkbox
  controls whether the paired tag CSV is written alongside (skipped when
  the chosen filename's stem doesn't end in `node`).
- `K` quick-save always writes both (`gv_node<stamp>.csv` +
  `gv_tag<stamp>.csv`).
- Only nodes with a non-empty `text` or `link` get tag rows.

## Authoring checklist

- Prefer inline `text`/`link`; keep labels short (**~40–80 characters**; a
  label never wraps and never truncates, it just runs off screen) and shared
  between nodes where the data allows, since layout is cached per unique
  string. Long text belongs in `link`, not `text`.
- UTF-8 explicitly; control characters stripped; no literal "None" titles.
- **Numeric labels are safe to write as-is** — hours, years, ranks, station
  ids. GlyphViz reads label text literally, so `007` stays `007` and `1.50`
  keeps its trailing zero. (Before 2026-08-17 the label column was type-inferred
  and a numeric column alongside any unlabelled row rendered as `12.0`; if you
  are targeting an older build, put one non-numeric value in the column.)
- Tag-file route: `table_id` = 0 on every row; `record_id` = the node's
  `id` (or its `record_id` if you set one); name the file by the
  `node`→`tag` stem swap.
- `tag_offset_x/y/z` in the 94-column layout are **round-trip only** —
  GlyphViz does not render a label offset; don't bother computing them.
- Remind users tags are off by default: "press T to see labels." — or pin
  the handful that should always show with `show_text` = 1, so the scene
  reads correctly the moment it opens.
