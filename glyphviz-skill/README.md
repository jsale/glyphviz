# GlyphViz Skill

A Claude Agent Skill for generating and validating **GlyphViz** scene data —
`gv_node.csv`, `gv_tag.csv`, and the Channels animation pair
(`gv_ch-map.csv` / `gv_ch-tracks.csv`).

## Status: complete for data authoring (last synced to the app 2026-08-28)

All planned data-format references are done, plus `troubleshooting.md`; the
only remaining item is optional `code/` tooling, not missing coverage. Synced
through app release **20260815** — including link geometries (a Link can be any
glyph, stretched between its ends), the rebuilt Pin, Topology Scale
(`topo_scale`) in both the Properties panel and the Glyph Composer, the
now-optional 0.2 minimum-glyph-size clamp, textured flat markers, and Draw Mode
— then extended on **2026-08-18** with the adjustable tag text size
(`tag_font_size`, a World-row scene setting, also Channels-bindable) and on
**2026-08-23** with **Global Scale** (hard rule 3: author against B = 1.0; what
B does and does not move), **3-D graph layout** (how to position the nodes of a
network, not just draw its edges), and **"Closing the loop"** — how to actually
see a generated scene in one round trip (`tools/export_frame.py --angles
… --report`) instead of a screenshot exchange per question. Extended again on
**2026-08-28** with the two shape families added since — the **interior**
geometries (29–32), for anything meant to be seen from within, and the **Flat
Ring** (33/34), a torus with a rectangular cross-section, which is the geometry
to reach for when a ring must carry legible text or graduations — together with
the ring texture-aspect rule that is the expensive way to learn it.

| Piece | Status |
|---|---|
| `SKILL.md` | **Done** — verified facts only; 11 hard rules, workflow, GaiaViz-myth list |
| `references/node-csv-format.md` | **Done** — verified column-by-column against `glyphviz_core/csv_reader.py` |
| `references/topologies.md` | **Done** — placement math for all 18 topologies plus `topo_scale`, and direction-relative branching (trees); 17 worked examples machine-verified through the real engine |
| `references/links-and-edges.md` | **Done** (2026-08-15, extended 2026-08-23) — the Link row, the three drawing modes, `ratio` as thickness, edge recipes, and laying a graph out in 3-D; endpoint/thickness math verified through `link_geometry`, layout claims against `graph.py`/`graph_layout.py` |
| `references/color-palettes.md` | **Done** — 26 palettes, resolution semantics, ramp recipes; samples machine-verified via `resolve_palette_color` |
| `references/textures-and-media.md` | **Done** (extended 2026-08-13/28) — `texture_id`→`media/` mapping, which geometries render a texture (incl. the interiors and the Flat Ring), generating a texture at a ring's own aspect ratio, GIF/video textures, Solo Audio to Selection |
| `references/channels-animation.md` | **Done** — ch-map/ch-tracks formats, bindable attributes, playback + audio sync; 12 behavior checks through the real ChannelEngine |
| `references/tags-and-labels.md` | **Done** — inline text/link vs tag file, title encodings, U-key rules, 500-per-frame draw cap; 18 checks through the real loader/saver |
| `references/world-grid.md` | **Done** — flat/globe placement, extents windows, the grid scale rule, multi-grid recipes; 18 checks incl. 7 engine-verified examples |
| `references/troubleshooting.md` | **Done** (2026-08-13, extended 2026-08-15/17/23/28) — seventeen silent failure modes (valid CSV, no error, wrong scene) with cause and fix, symptom-indexed; 33 checks against the real source |
| `code/` (generator + validator helpers) | Planned — optional tooling, not a coverage gap; see `references/OUTLINE.md` |
| `examples/` | **Six curated exemplars, eight scenes** (Breathing_Century, Duel_of_Dynasties, SD_Seismicity, RSS_News, Wind_Rose ×2, Decay_Chain ×2) — verified through the real loader/engine/renderer; see `examples/README.md` |

## Relationship to `gaiaviz-skill/`

`gaiaviz-skill/` targets **GaiaViz** (the `np_` "neural physics" dialect) and
remains the authoritative spec for genuine GaiaViz interop. This skill targets
**GlyphViz's own native conventions** (`gv_` prefix, minimal-column authoring,
GlyphViz-only extensions like `rotation_mode`, `palette_id`, `topo_scale`,
inline `text`/`link`, Plot/Surface topologies, World Grid extents, marker
geometries, and links that carry any geometry).

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
