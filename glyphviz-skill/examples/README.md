# Examples

Curated, verified scenes demonstrating how to *think* about hyperglyph
design — not just the file formats. The first three were generated in the
wild by a skill-equipped Claude instance (2026-07); `RSS_News/`,
`Wind_Rose/`, and `Decay_Chain/` were built in-repo. All passed the repo's
curation gate: loaded through the real `load_node_csv`, channel joins
validated through the real `ChannelEngine`, rendered-scale
checked, and confirmed with a real headless render.

**`Wind_Rose/` and `Decay_Chain/` are the two to read first if you're
designing a hyperglyph** — a composite glyph whose internal structure carries
the variables. Each holds *two* scenes in subfolders: a small, legible one
that teaches the form, and a large one that puts it to work. That pairing is
itself the lesson — a reader who has never seen your glyph can't decode a
thousand of them at once.

**`Rooted_Bars/` and `Glyph_Envelope/` are the two to read first if a scene
you built came out wrong.** They are deliberately small, and each one is about
a single failure mode rather than a subject: the first is what a `scale` number
actually means, the second is what happens when real data meets a design tuned
on one record. Both carry their own measurement — `Rooted_Bars` re-derives its
table through the real engine before writing the CSV, `Glyph_Envelope` commits
`extent_report.txt` beside the scene.

| Example | Demonstrates |
|---|---|
| `Rooted_Bars/` | **A length that carries data belongs in position space, not scale space** — the same 14 values drawn four ways, side by side, so the difference is visible at Global Scale 1 and again at 3. Also the rule underneath it: every geometry fits inside *radius* 1, which is not the same as spanning −1…+1, so a cube reaches 0.577 of its scale and a Pin is a needle 0.1 wide. The generator re-measures its own documentation through the placement engine and refuses to emit if the table and the code disagree. |
| `Glyph_Envelope/` | **The design envelope** — one hyperglyph built at the minimum, median and maximum of every variable, with the variable → channel → domain → clamped-range budget stated and enforced, and a design-specific audit (nothing below the baseline, no part swallowing another) run on all three probes before generating all N. Shows the envelope changing the design: the palm grew a bare stem purely so the worst record's droop clears the ground. Glyph design credited to Dr Dave Warner; data synthetic. |
| `Breathing_Century/` | The **channel-sharing compression pattern**: ~1,700 animated glyphs on 204 channels (nodes sharing birth-year + final-alpha share one `ch_input_id`); step-function `color_a` appear-and-stay timelines; one track feeding `scale_x/y/z` for a breathing glyph; era-fair encoding; carrying values across source-data gaps. |
| `Duel_of_Dynasties/` | **Deep multi-branch design under one clock**: torus → cube-facet → satellite hierarchies; Plot-topology curves; flare-and-settle scale tracks that end on authored state so looping stays consistent; pairing per-node scale channels with shared alpha channels; the choice of clock (career-relative vs calendar) as an analytic decision. |
| `SD_Seismicity/` | **Multi-World-Grid composition + Channels time replay**: a whole-earth grid and a georeferenced region grid joined by a 3D inset-zoom callout; live-API data acquisition with an offline snapshot; depth via grid `scale_z` exaggeration; monthly-cohort channel compression (634 events on 315 channels); flash-decay-relight alpha; a `translate_x` channel as a timeline cursor. |
| `Wind_Rose/` | **Hyperglyph design from an encoding that already exists**: a wind rose's real anatomy (hub → 16 compass arms → speed-bin segments) becomes three levels of hierarchy, every one carrying measured data rather than decoration. Two scenes, learn-then-read: `Rose_Anatomy/` draws twelve archetype stations large and labelled so one glyph can be *read*; `Monsoon_Year/` puts 102 stations on a globe grid and animates all of them through twelve months on one clock. Also: a vector-mean needle as a second encoding inside the same glyph, and picking archetypes so the reader learns the form before facing the swarm. |
| `Decay_Chain/` | **Letting the data set the depth**: a decay chain nests as deeply as the physics does (one step for tritium, fourteen for U-238), so glyph depth *is* the finding — plus real branching (Bi-212 forks and rejoins). `Chain_Forest/` reads as a skyline ordered by chain length; `Secular_Equilibrium/` animates Bateman-equation activities across thirteen decades of logarithmic time with a cursor riding a log axis. Also: invisible `scale 1` hub frames separating structure from appearance, and a Cylinder-topology petal ring for branching ratios. |
| `RSS_News/` | The **live-data regenerate-and-reload pattern**: a `--watch` generator loop with atomic writes (channels first, node CSV last) paired with the app's File > Watch and Reload; an accumulating deduplicated snapshot; cross-language comparability via a multilingual concept dictionary; fixed category slots on globe-surface towers (gaps carry meaning); clickable glyphs via inline `text`/`link` (Alt+click / U opens headlines); per-cube `color_a` pulses over a static-totals base CSV. |

Every scene is complete and loadable: open its `*_gv_node.csv` in GlyphViz
and the name-paired `ch-map`/`ch-tracks` files auto-load; playback off shows
the static scene. `Wind_Rose/` and `Decay_Chain/` hold their two scenes in
subfolders, one `*_gv_node.csv` each. The `build_*.py` generators are
included for reading (they show the authoring patterns in code) — the NHL
examples' source dataset is not bundled, but `SD_Seismicity/`, `RSS_News/`,
`Wind_Rose/`, `Decay_Chain/`, `Rooted_Bars/` and `Glyph_Envelope/` regenerate
fully from their bundled `data/` snapshots (USGS, the 20 RSS feeds, NOAA
station climatology, the IAEA nuclide table, a 14-row extract of that same
table, and a seeded synthetic cohort respectively).

The screenshots that accompany these scenes in the main repo are not bundled
here — the skill zip carries data and prose, not images.

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
