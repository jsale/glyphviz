# Examples

Curated, verified scenes demonstrating how to *think* about hyperglyph
design — not just the file formats. Both were generated in the wild by a
skill-equipped Claude instance (2026-07, NHL history dataset), then passed
the repo's curation gate: loaded through the real `load_node_csv`, channel
joins validated through the real `ChannelEngine`, cumulative render-scale
floor checked, and confirmed with a real headless render.

| Example | Demonstrates |
|---|---|
| `Breathing_Century/` | The **channel-sharing compression pattern**: ~1,700 animated glyphs on 204 channels (nodes sharing birth-year + final-alpha share one `ch_input_id`); step-function `color_a` appear-and-stay timelines; one track feeding `scale_x/y/z` for a breathing glyph; era-fair encoding; carrying values across source-data gaps. |
| `Duel_of_Dynasties/` | **Deep multi-branch design under one clock**: torus → cube-facet → satellite hierarchies; Plot-topology curves; flare-and-settle scale tracks that end on authored state so looping stays consistent; pairing per-node scale channels with shared alpha channels; the choice of clock (career-relative vs calendar) as an analytic decision. |

Each folder is a complete loadable scene: open the `*_gv_node.csv` in
GlyphViz and the name-paired `ch-map`/`ch-tracks` files auto-load; playback
off shows the static scene. The `build_*.py` generators are included for
reading (they show the authoring patterns in code) — regenerating requires
the source dataset, which is not bundled.

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
