# City Climate Rings

A year of climate for 31 cities, as a ring of months around each city on a
globe. Built from a flat spreadsheet by describing it to Claude with the
glyphviz skill, and the scene behind the "Your Data in GlyphViz" lesson video.

Open `climate_rings_gv_node.csv`, or drag this folder onto the window.

## Reading a ring

- **Each ring is one city's year**, lying flat on the globe. January is at the
  top (north) and the months run clockwise, like a clock face.
- **The month beads are coloured by mean temperature**: deep blue for the
  coldest months, through pale, to red for the hottest.
- **The bar standing on each month spans its average low to its average
  high.** Height above the ring is temperature: 0.16 world units per degree,
  with -45 °C at the ring itself. A thin grey stem joins each bead to its bar.
- **The blue column just outside each bead is the month's rainfall**, 1 world
  unit per 60 mm.
- **Click anything to read it.** Every ring, bead, bar and column is labelled
  with its city, month and value.

## What the rings show

Measured from `city_climate.csv`:

- **Yakutsk has the widest year**: its monthly mean goes from -37.4 °C in
  January to 19.8 °C in July, a 57.2 °C swing. **Bogota has the narrowest**:
  1.3 °C, near the equator and high in the Andes. Singapore is next, at
  2.2 °C.
- **Mumbai's monsoon**: 94% of its 2,509 mm a year falls from June to
  September, 834 mm of it in July alone, and January gets none.
- **Lima is the driest city here**, at 24 mm a year, drier than Cairo (60 mm)
  or Dubai (85 mm).
- **The seasons flip across the equator.** Sydney's warmest month is January
  and Moscow's is July, so the warm colours sit at opposite ends of their
  clocks.

## Structure

```text
World Grid (globe, Blue Marble, scale 3)
└─ city ring ×31          Torus glyph and Torus topology, at the city's lon/lat
   └─ month carrier ×12   hidden; on top of the tube (tube angle 90), so its
      │                   +Z points straight up; translate_x = 180 - 30 × month
      ├─ month bead       sphere, colour = mean temperature
      ├─ stem             Link, bead -> the bar's low end
      ├─ temperature bar  Link between two hidden nodes, at the low and high
      └─ rain column      Link between two hidden nodes, base and top
```

3,381 nodes. Every bar is a Link between two hidden nodes, so both of its ends
are coordinates and it keeps its height at any Global Scale.
`build_climate_rings.py` checks the geometry through GlyphViz's own engine
before it writes a file: January due north on all 31 clocks, running
clockwise, every bar upright, every length exact.

A ring on a city far from a pole lies at an angle to the screen. To look
straight down on one, rotate the World Grid (it is an ordinary node): with
rotation mode Euler XYZ, `(0, -(90 - lat), -lon)` brings that city to the top
of the globe, north up when viewed from azimuth 0.

## Files

| File | What it is |
|---|---|
| `city_climate.csv` | the data: 372 rows, one per city per month |
| `prompt.md` | the prompt the scene was made from |
| `build_climate_rings.py` | the generator Claude wrote for that prompt |
| `fetch_climate.py` | rebuilds `city_climate.csv` from NASA POWER |
| `climate_rings_gv_node.csv` | the scene |
| `media/01_bluemarble.png` | NASA Blue Marble, the globe's texture |

## Data

**NASA POWER** daily point data (power.larc.nasa.gov), public domain, no API
key: every day from January 2001 to December 2020, averaged here by calendar
month. High and low are the means of the daily maximum and minimum; rainfall
is each month's total, averaged over the 20 years.

These are values for the MERRA-2 **grid cell** a city sits in, about 50 km
across, not for a weather station. A coastal city's cell often reaches inland:
San Diego's summers come out a few degrees warmer than its airport records.

POWER's climatology endpoint is not used. Its `T2M_MAX` and `T2M_MIN` are the
month's extremes, not its average high and low (it gives San Diego a 27.6 °C
January "high"), so `fetch_climate.py` averages the daily data instead.

Globe texture: NASA Visible Earth Blue Marble.
