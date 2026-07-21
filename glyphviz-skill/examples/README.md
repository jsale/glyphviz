# Examples

Curated, verified scenes demonstrating how to *think* about hyperglyph
design — not just the file formats. Most were generated in the wild by a
skill-equipped Claude instance (2026-07); `RSS_News/` was built in-repo
alongside the app's Watch and Reload feature. All passed the repo's
curation gate: loaded through the real `load_node_csv`, channel joins
validated through the real `ChannelEngine`, cumulative render-scale floor
checked, and confirmed with a real headless render.

| Example | Demonstrates |
|---|---|
| `Breathing_Century/` | The **channel-sharing compression pattern**: ~1,700 animated glyphs on 204 channels (nodes sharing birth-year + final-alpha share one `ch_input_id`); step-function `color_a` appear-and-stay timelines; one track feeding `scale_x/y/z` for a breathing glyph; era-fair encoding; carrying values across source-data gaps. |
| `Duel_of_Dynasties/` | **Deep multi-branch design under one clock**: torus → cube-facet → satellite hierarchies; Plot-topology curves; flare-and-settle scale tracks that end on authored state so looping stays consistent; pairing per-node scale channels with shared alpha channels; the choice of clock (career-relative vs calendar) as an analytic decision. |
| `SD_Seismicity/` | **Multi-World-Grid composition + Channels time replay**: a whole-earth grid and a georeferenced region grid joined by a 3D inset-zoom callout; live-API data acquisition with an offline snapshot; depth via grid `scale_z` exaggeration; monthly-cohort channel compression (634 events on 315 channels); flash-decay-relight alpha; a `translate_x` channel as a timeline cursor. |
| `RSS_News/` | The **live-data regenerate-and-reload pattern**: a `--watch` generator loop with atomic writes (channels first, node CSV last) paired with the app's File > Watch and Reload; an accumulating deduplicated snapshot; cross-language comparability via a multilingual concept dictionary; fixed category slots on globe-surface towers (gaps carry meaning); clickable glyphs via inline `text`/`link` (Alt+click / U opens headlines); per-cube `color_a` pulses over a static-totals base CSV. |

Each folder is a complete loadable scene: open the `*_gv_node.csv` in
GlyphViz and the name-paired `ch-map`/`ch-tracks` files auto-load; playback
off shows the static scene. The `build_*.py` generators are included for
reading (they show the authoring patterns in code) — the NHL examples'
source dataset is not bundled, but `SD_Seismicity/` and `RSS_News/`
regenerate fully from their bundled `data/` snapshots (or a live
refetch — USGS and the 20 RSS feeds respectively).

A third exemplar from the same series, **Century_Swarm** (29,140
player-seasons, ~140k nodes — spatial position as the primary encoding, and
the scale/labeling strategies that make a six-figure node count workable),
lives in the main repo at `examples/Century_Swarm_Example/`; its node CSV
is too large to bundle in the skill zip.

## Rules for adding an example

- Must pass the curation gate above (real loader, real engine, real render)
  before landing.
- Trim to the minimum that demonstrates the concept — the skill zip stays
  small; no large media.
- Each example's README states the concept and **what it teaches**, not
  just what it is.
- Never hand-edit the CSVs; regenerate from the script.
