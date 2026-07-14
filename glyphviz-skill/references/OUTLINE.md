# References — status and plan

Every doc here must be verified against `glyphviz_core/` / `glyphviz_gl/`
source (or by running the repo's real loader/renderer) before being marked
done. Nothing is inherited from `gaiaviz-skill/` without re-verification.

| Doc | Status | Scope / primary sources |
|---|---|---|
| `node-csv-format.md` | **Done** (2026-07-14) | Full node CSV spec. Verified against `csv_reader.py`, `node.py`, `geometry_data.py`, `topology.py`. |
| `topologies.md` | Planned | Per-topology child-placement math and worked coordinate examples for all 18 types, incl. Plot/Surface data encoding and Z-variant behavior. Source: `topology.py` offset functions; sanity-check with headless Viewport renders. |
| `world-grid.md` | Planned | Flat plate vs globe, extents windows, region recentering, textures, child coordinate rules, unpickability. Source: `node.py` grid accessors, `scene.py`, `viewport.py`. |
| `tags-and-labels.md` | Planned | Inline `text`/`link` vs `gv_tag.csv`, URL/file/app-launch link encoding, tag offsets, display toggles. Source: `csv_reader.py` tag functions + `glyphviz_gl` tag rendering. |
| `channels-animation.md` | Planned | `gv_ch-map.csv`/`gv_ch-tracks.csv` formats, `ch_input_id` binding, playback transport/FPS. Source: `channel_loader.py`, `channel_engine.py`. |
| `color-palettes.md` | Planned | 26 palette definitions, `color_index` semantics, cycling keys, ramp recipes for generated data. Source: `color_palette.py`. |
| `textures-and-media.md` | Planned | How `texture_id` maps to loaded media, video textures, audio. Source: `glyphviz_gl` texture loading. |
| `code-patterns.md` + `code/` helpers | Planned | Reusable generator snippets (node factory, topology position helpers, color ramps) and a standalone `validate_csv.py` implementing SKILL.md's validation checklist. Must run with no GlyphViz install (skill is used self-contained on claude.ai). |
| `troubleshooting.md` | Planned | Verified gotcha catalog: 0.2 scale floor, UTF-8/control-char tag kill, rotation_mode asymmetry, palette inertness, mesh_id non-inheritance, World-node bulk-edit exclusion. |
| `app-usage.md` | Deliberately out of scope | Keyboard/GUI usage lives in `glyphviz-docs/`, not the skill. The skill only tells users how to open generated files. |
