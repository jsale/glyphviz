# GlyphViz Skill

A Claude Agent Skill for generating and validating **GlyphViz** scene data —
`gv_node.csv`, `gv_tag.csv`, and the Channels animation pair
(`gv_ch-map.csv` / `gv_ch-tracks.csv`).

## Status: scaffold (in progress)

| Piece | Status |
|---|---|
| `SKILL.md` | First draft — verified facts only |
| `references/node-csv-format.md` | **Done** — verified column-by-column against `glyphviz_core/csv_reader.py` |
| `references/topologies.md` | **Done** — placement math for all 18 topologies; 17 worked examples machine-verified through the real engine |
| `references/color-palettes.md` | **Done** — 26 palettes, resolution semantics, ramp recipes; samples machine-verified via `resolve_palette_color` |
| `references/textures-and-media.md` | **Done** — `texture_id`→`media/` mapping, GIF/video textures, Solo Audio to Selection |
| `references/channels-animation.md` | **Done** — ch-map/ch-tracks formats, bindable attributes, playback + audio sync; 12 behavior checks through the real ChannelEngine |
| `references/tags-and-labels.md` | **Done** — inline text/link vs tag file, title encodings, U-key rules, 500-per-frame draw cap; 18 checks through the real loader/saver |
| Remaining references | Planned — see `references/OUTLINE.md` |
| `examples/` | Curation plan only — see `examples/README.md` |
| `code/` (generator + validator helpers) | Planned |

## Relationship to `gaiaviz-skill/`

`gaiaviz-skill/` targets **GaiaViz** (the `np_` "neural physics" dialect) and
remains the authoritative spec for genuine GaiaViz interop. This skill targets
**GlyphViz's own native conventions** (`gv_` prefix, minimal-column authoring,
GlyphViz-only extensions like `rotation_mode`, `palette_id`, inline `text`/`link`,
Plot/Surface topologies, World Grid extents, marker geometries, Link prisms).

The two deliberately do not share prose — several gaiaviz-skill rules are
**wrong for GlyphViz** (e.g. "exactly 94 columns", "infrastructure rows are
mandatory", "line_width > 0 or nodes won't display"). Everything in this skill
is verified against the GlyphViz source, not inherited from GaiaViz docs.
Long-term intent: this skill replaces gaiaviz-skill once its coverage is
complete; the `np_` read-side interop aliases in `glyphviz_core` are unaffected.

## Installing / testing the skill

- **Claude Code**: copy (or symlink) this directory into `.claude/skills/glyphviz/`
  in any project, or reference it from the repo directly.
- **Claude Desktop / claude.ai**: zip this directory and upload it under
  Settings → Capabilities → Skills. The skill must work self-contained there
  (no repo access) — that is the acceptance bar for each reference doc.

## Verification policy

Every factual claim in `SKILL.md` and `references/` must be traceable to the
GlyphViz source (`glyphviz_core/`, `glyphviz_gl/`) or verified by running code
against the real loader (the repo's temp-CSV-through-real-app-objects pattern).
No claims imported from GaiaViz reference docs without re-verification.
