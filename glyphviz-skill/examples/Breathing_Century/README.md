# The Breathing Century

Every franchise in a century of hockey (1909-10 to 2011-12) stands as a
vertical tower of season discs on a founding-order ring - disc width is
points percentage, color runs deep blue (outscored) through silver to gold
(dominant), ghosted alpha marks missed playoffs, and gold dodecahedra hang
at Stanley Cup heights. Channels turn the reef into a growth animation: one
cyclecount step per season, and every glyph is born transparent, snapping
solid the year it happened, while a translucent "tide" torus at the center
breathes with league-wide goals per game (holding its breath through the
2004-05 lockout).

**What it teaches:** the channel-sharing compression pattern - ~1,700
animated glyphs driven by only 204 channels because every node with the same
birth year and final alpha shares one `ch_input_id`; step-function `color_a`
tracks for appear-and-stay timelines; one track feeding `scale_x/y/z` on a
single channel for a breathing glyph; precomputed `color_r/g/b` gradient
tracks; era-fair encoding (rate stats, not raw totals) so a 1919 season and
a 2010 season read identically; and carrying values forward across gaps in
the source time series so the shared clock never desynchronizes.

Regenerate with `python build_breathing_century.py` (set `HOCKEY_DATA` to
the folder holding the hockey history CSVs). Load
`century_reef_gv_node.csv`; the name-paired ch-map/ch-tracks files auto-load.
Playback off shows the complete static reef.
