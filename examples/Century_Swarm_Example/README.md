# The Century Swarm

All 29,140 player-seasons of 25+ games from 1921-22 to 2011-12 as
hyperglyphs placed at their coordinates in scoring phase space: X = goals
per game, Y = assists per game, Z = year. Each season is a sphere sized by
points per game and colored by position (red centers, orange/gold wingers,
blue defensemen, green goalies) carrying facet satellites for goals,
assists, PIM, and signed +/- - about 140,000 nodes total. The shape itself
is the finding: a dense mass of ordinary seasons hugging the low corner,
the whole cloud inhaling through the 1980s and exhaling into the dead-puck
era, defensemen forming a blue wall along the low-goals plane (with Bobby
Orr's seasons escaped deep into forward territory), and the transcendent
seasons physically detached from the swarm - remoteness is the ranking.

**What it teaches:** scale - authoring and loading a six-figure node count
from a single flat two-level hierarchy (one root, 29k parents, 111k
satellites); using *spatial position as the primary encoding* (phase-space
scatter) rather than topology scaffolds; respecting the 0.2 rendered-scale
floor in mass hierarchies (parent >= 0.6 x satellite >= 0.34 keeps every
cumulative product >= 0.204); confining a large scene to a bounded volume
(~+-26 units) so nothing clips; wayfinding guide nodes for unlabeled
space; and inline selection labels as the only viable labeling strategy at
this density.

Regenerate with `python build_swarm.py` (set `HOCKEY_DATA`). Load
`century_swarm_gv_node.csv` with tag labels off; select any glyph for its
full season line.
