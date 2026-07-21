# RSS News — Live International News Globe

Twenty news outlets across 12 countries and 8 languages, each a pad on a
Blue Marble globe World Grid at its home city. Above every outlet rises a
concept tower: one cube per tracked concept (war, election, economy,
climate, …) at a fixed altitude slot, sized by how many of the outlet's
articles mention it, colored by concept identity (legend column west of
the globe). An amber octahedron at each tower's top carries the outlet's
latest headline as its `text` and the article URL as its `link` —
Alt+click (or select + U) opens the story. Channels replay the last 72
hours in 3-hour buckets: cubes dim to a baseline and flash in the buckets
where matching articles were published while a cursor sweeps a UTC
timeline bar.

**What it teaches:** the **live-data regenerate-and-reload pattern** — a
generator that fetches external feeds on a loop (`--watch N`), rewrites
the scene CSVs **atomically** (temp file + `os.replace`, companion
channel files first, node CSV **last**), pairing with the app's File >
Watch and Reload (Ctrl+R) for a self-updating scene; an accumulating
snapshot (dedup by URL, age-pruned) so short feeds grow into a long
replay window across cycles; **cross-language comparability** via a
concept dictionary (per-language term lists collapse onto shared concept
slots, so encodings compare across languages); fixed category slots with
deliberate gaps (same concept = same altitude on every tower, absence
visible); inline `text`/`link` making glyphs clickable data points; and
per-cube `color_a` pulse channels against a static-totals base CSV
(playback off = totals, playback on = time structure).

Load `rss_news_gv_node.csv` with `media/` beside it; the name-paired
ch-map/ch-tracks auto-load; Space plays. Fully regenerable offline from
the bundled snapshot (`python build_rss_news_scene.py --offline`) or live
(no arguments; stdlib-only RSS/Atom/RDF parsing, per-feed failures
tolerated, ~15 s for a full 20-feed cycle). The feed list
(`data/feeds.csv`) and concept dictionary (`data/terms.csv`) are plain
CSVs — "customized for any topic" means editing those two files.
