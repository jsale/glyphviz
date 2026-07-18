# References — status and plan

Every doc here must be verified against `glyphviz_core/` / `glyphviz_gl/`
source (or by running the repo's real loader/renderer) before being marked
done. Nothing is inherited from `gaiaviz-skill/` without re-verification.

| Doc | Status | Scope / primary sources |
|---|---|---|
| `node-csv-format.md` | **Done** (2026-07-14) | Full node CSV spec. Verified against `csv_reader.py`, `node.py`, `geometry_data.py`, `topology.py`. |
| `topologies.md` | **Done** (2026-07-14) | Per-topology child-placement math and worked coordinate examples for all 18 types, incl. Plot/Surface overlay rules and Z-variant behavior. Verified against `topology.py` offset functions + `viewport.py` overlays; all 17 worked examples machine-checked through `compute_world_positions`. |
| `world-grid.md` | Planned | Flat plate vs globe, extents windows, region recentering, textures, child coordinate rules, unpickability. Source: `node.py` grid accessors, `scene.py`, `viewport.py`. |
| `tags-and-labels.md` | **Done** (2026-07-18) | Inline `text`/`link` vs `gv_tag.csv`, title encodings, URL/file/app-launch link rules, display behavior incl. the 500-per-frame draw cap (a perf valve, not a string limit). Verified against `csv_reader.py`/`viewport.py`/`main_window.py`; 18 behavior checks through the real loader/saver. |
| `channels-animation.md` | **Done** (2026-07-18) | `gv_ch-map.csv`/`gv_ch-tracks.csv` formats, complete bindable-attribute list, playback transport, audio-sync manifest, recipes. Drafted in the wild by a skill-equipped Desktop instance, then verified/corrected against `channel_loader.py`/`channel_engine.py`/`main_window.py`; behaviors machine-checked through the real ChannelEngine (12 checks incl. an attribute-list drift guard). |
| `color-palettes.md` | **Done** (2026-07-17) | 26 palette definitions (full 20-color table + gradient formulas), `color_index`/`palette_id` resolution semantics, cycling keys, ramp recipes. Verified against `color_palette.py`; sample resolutions machine-checked via `resolve_palette_color`. |
| `textures-and-media.md` | **Done** (2026-07-17) | `texture_id` → `media/` file mapping (1-based, images then videos), animated GIF/video textures, video audio incl. Solo Audio to Selection. Verified against `texture_manager.py`/`video_manager.py`/`main_window.py`. |
| `code-patterns.md` + `code/` helpers | Planned | Reusable generator snippets (node factory, topology position helpers, color ramps) and a standalone `validate_csv.py` implementing SKILL.md's validation checklist. Must run with no GlyphViz install (skill is used self-contained on claude.ai). |
| `troubleshooting.md` | Planned | Verified gotcha catalog: 0.2 scale floor, UTF-8/control-char tag kill, rotation_mode asymmetry, palette inertness, mesh_id non-inheritance, World-node bulk-edit exclusion. |
| `app-usage.md` | Deliberately out of scope | Keyboard/GUI usage lives in `glyphviz-docs/`, not the skill. The skill only tells users how to open generated files. |
