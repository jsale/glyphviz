# Duel of Dynasties

Three complete career orreries - Wayne Gretzky, Gordie Howe, Mario
Lemieux - side by side on one plane, each a torus hub carrying season
spheres on a calendar-relative arc (team-colored, points-scaled), with
cube-facet stat satellites (G/A/PIM/+-), prestige-sorted award stacks,
Stanley Cup rings, a Plot-topology points curve, and a Hall of Fame
icosahedron. The shared 34-step clock is *career-relative* ("years since
debut"), so the three rings fill in phase: Gretzky gapless, Howe's
34-year span with his 1971-73 sabbatical, Lemieux's ring bitten by injury,
retirement, and lockout - and the HOF markers appear at real induction
years, mid-career for Howe (1972) and Lemieux (1997), both of whom
unretired after enshrinement.

**What it teaches:** deep multi-branch hyperglyph design (torus -> cube
facets -> satellites) under one animation clock; flare-and-settle scale
tracks (a one-step 1.25x pulse that returns to the authored value, with
every track ending on authored state so looped playback stays consistent);
pairing a per-node scale channel with a shared alpha channel so satellites
are born with their parent without inheriting its scale values; and how the
*choice of clock* (career-relative vs calendar) is itself an analytic
decision - the same nodes tell a different story on a different clock.

Regenerate with `python build_duel.py` (set `HOCKEY_DATA`). Load
`duel_of_dynasties_gv_node.csv`; channel files auto-load by name pairing.
