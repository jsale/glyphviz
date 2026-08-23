# The Wind Rose as a Hyperglyph

A wind rose is not an encoding invented to justify a nested glyph. It is the
standard meteorological representation, and it already *has* an anatomy: a
station hub carrying sixteen compass arms, each arm itself a stack of
speed-bin segments. Three real levels of structure below the World Grid, and
every level carries measured data.

Two scenes, learn-then-read:

**`Rose_Anatomy/`** — twelve archetype stations on a plane, drawn large and
labelled so a single glyph can actually be read. The pale core is how often
the air is still; the sixteen petals are how often the wind blows *from* that
quarter; the colour bands within a petal are wind speed; the slim needle is
the vector-mean (resultant) wind, long where the wind is persistent and stubby
where it is not.

**`Monsoon_Year/`** — 102 stations on the globe, animated through the twelve
months. Every rose reshapes itself on the same clock. Press play and the
Atlantic trades barely stir while the glyphs around the Indian Ocean, West
Africa and northern Australia swing bodily through 180 degrees. A marker
tracks the subsolar latitude, which is the reason it happens.

## What the data says

Nothing here was hand-picked to look good; the physics fell out of the
climatology and then the checks confirmed it.

The stations with the highest **directional constancy** — the vector-mean
wind divided by the mean speed — are Ascension Island (0.98), Cape Verde,
St Helena, Barbados and Fernando de Noronha. That is the trade-wind belt,
recovered without being asked for. The lowest are continental interiors:
Jiuquan in the Gobi (0.12), Sortavala in Karelia, Fort Smith in the Northwest
Territories.

The largest January-to-July reversals of resultant wind direction are Kano
(178°) and Bissau (177°) — the West African monsoon against the harmattan —
followed by Palembang, Darwin (176°), Tokyo and Nikolaevsk-on-Amur. Those are
the Asian, Australian and East Asian monsoons, ranked correctly by a
calculation that knew nothing about monsoons.

## Structure

```text
World Grid (globe, scale 3)
└─ station hub          topo = Cylinder, invisible placement frame
   ├─ calm core         sphere sized by the calm fraction
   ├─ resultant needle  cone aimed along the vector-mean wind
   └─ compass arm ×16   translate_x = 180 - bearing
      └─ speed segment  cube per speed bin, stacked outward
```

The compass mapping is the one non-obvious piece. A station hub is a child of
a Sphere-geometry World Grid, so its local frame is +Z up, +Y east, +X south.
Its `topo` is Cylinder, which places children at
`offset = ((B+tz)·cos tx, (B+tz)·sin tx, ty)` and carries them around by
`Rz(tx)`. Compass bearing therefore maps to

```text
translate_x = 180 - bearing
```

This was measured against the real transform engine before anything was built,
not assumed: `verify_wind.py` re-derives every arm's bearing from its world
position through the local East/North/Up frame and gets the sector back to
2.8e-14 degrees, with every arm lying flat in the horizontal plane to 5e-16.

Each arm sits at radius `B + tz = 0` — exactly at the hub centre. An arm is a
*rotation frame*, not an offset; the segments hang off its local +X.

## Two things worth knowing

**Grid scale buys glyph size for free.** A World Grid's scale re-spaces child
*positions* without touching subtree size. Measured: at scale 3 the hub
separation goes from 9.99 to 29.96 world units while the arm offset stays
4.000 and the segment's world scale stays 0.5000. The globe is therefore drawn
at scale 3, which spreads the stations far enough apart that the roses can be
13 world units across and still not collide. Without that, the speed bands
would not clear the render floor.

**The 0.2 render floor lands on each node's own scale.** It is optional now
(View → Enforce Minimum Glyph Size, **off by default**), and authoring above
it is exactly what makes this scene read the same with the setting either way.
When it is on, `node_world_matrix` floors *this node's* `scale × base_scale` at
0.2 per axis and then multiplies by the parent basis — so a node authored below
0.2 is drawn bigger than it encodes, and the encoding quietly lies. Every hub and arm in these roses is
scale 1, which puts the floor directly on the segment; a cube is inscribed in
the unit sphere, so the shortest speed band that can be drawn honestly is
`0.2 × 2/√3 ≈ 0.231` world units. (Shrinking an ancestor would lower that, but
it would shrink the whole rose with it.) Rather than silently inflate a rare
speed bin to the minimum, sub-floor segments are **merged into a neighbour**,
which keeps the petal's total length — the frequency of wind from that quarter
— exactly right and costs only colour resolution in the tail. A petal shorter than the
floor in total is not drawn at all. Dominant petals keep 4.1 of their 5 bands
on average; length-weighted across all petals it is 3.5.

## Honest caveats

- **Frequencies are conditional on a direction report.** Observations with a
  valid speed but no bearing are excluded from the numerator *and* the
  denominator, so sector frequencies plus calm close to 1.000000. The median
  station-month discards 0.1% of its observations this way; the 95th
  percentile discards 12%.
- **Diurnal sampling is corrected.** Stations differ in how often they report
  and some report only in daylight, which would bias raw frequencies toward
  whatever blows during the reporting hours. Every observation is weighted by
  the inverse of how often that station-month reports in that hour of the
  clock, so every hour carries equal weight.
- **Petal length is clipped at 28% frequency**, a fixed reference across all
  stations so glyphs stay comparable rather than self-normalising. About 2% of
  sectors are more concentrated than that and hit the cap; the verifier skips
  them when decoding and reports how many.
- **Stations above 85° latitude are excluded.** A compass rose is meaningless
  where the local north direction depends on which meridian you pick.
- Five years (2019–2023) is a climatology, not a climate trend. Nothing here
  says anything about change over time.

## Verification

`verify_wind.py` runs the real loader and transform engine over the shipped
CSVs and reads every answer back out of world-space geometry:

- the glyph really nests grid → hub → arm → segment (1632 arms, 4315 segments);
- every visible node's own scale clears the 0.2 render floor (tightest 0.2001,
  i.e. the shortest speed band sits exactly on it);
- the globe's placement formula holds to 3.2e-14 world units;
- **the encoding round-trips**: summing a petal's rendered segment lengths
  recovers the sector frequency that went in, worst error 4.3e-06 across 1509
  petals, against frequencies that run from 0 to 0.86;
- no two roses can intersect (closest hubs 33.7 units apart, rose diameter
  26.4);
- **applying channel frame m reproduces that month's measured rose** — worst
  error 3.6e-06 across 696 petals in January and July.

That last check caught a real modelling bug. The segment *nodes* are fixed by
the annual rose, but each month was originally re-running the merge
independently, so a band that merged differently in July had no node to live
on and the petal silently came up short. Months now allocate across the annual
grouping, and any group falling under the floor is parked inside the calm core
with the rest rescaled to preserve the petal's total length.

## Regenerating

```bash
python fetch_wind.py            # downloads NOAA ISD-Lite, writes data/
python build_wind_scenes.py     # writes both scenes
python verify_wind.py           # checks them
```

`fetch_wind.py` needs the network; everything else works from the vendored
`data/wind_roses.csv` (232 stations × 12 months, 1.9 MB). It shells out to
`curl` rather than using `urllib`, which stalls indefinitely against
ncei.noaa.gov from some networks while ignoring its own timeout.

Data: NOAA NCEI Integrated Surface Database (ISD-Lite), 2019–2023 hourly
observations, public domain.
