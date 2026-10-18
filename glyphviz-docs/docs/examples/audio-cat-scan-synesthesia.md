# Cat Scan Synesthesia

One master glyph and 64 frequency-band hyperglyphs (4,529 nodes) on a Fibonacci shell — bass at the south pole, treble at the north — with four frequency zones given distinct geometry, palettes, and motion personalities.

![Cat Scan Synesthesia loaded in GlyphViz](../assets/examples/audio-cat-scan-synesthesia.png)

*The commercial source recording is not redistributed; all generated animation files are included.*

**Try it:** download this example below (or [the full examples set](../getting-started/installation.md#example-scenes)), then open `Audio_Animation_Example/Cat_Scan_Synesthesia_Example/Cat_Scan_Synesthesia_Example_gv_node.csv` — or just drag its folder onto the GlyphViz window. Press **Space** to start the animation.

[:material-download: Download this example (24 MB)](https://iluvdata.org/glyphviz/zips/Cat_Scan_Synesthesia_Example.zip){ .md-button }

## What it is

Most audio scenes in this gallery are a *spectral array*: one glyph per frequency band, all the same, all doing one thing. This one is a **synesthesia instrument**. A single master glyph sits at the centre, and its 64 children are the frequency bands of Tangerine Dream's *Cat Scan*, from 20 Hz to 16 kHz. Each band is a three-level hyperglyph with a personality of its own, and that personality changes as the pitch climbs.

Press **Space** and the band glyphs breathe, pop outward, spin and orbit with the music for the whole 4 minutes 4 seconds (7,338 frames at 30 per second), while the recording plays in sync.

## How to read it

The 64 bands sit on a Fibonacci shell around the master glyph, evenly spread, with **bass at the south pole and treble at the north**. Look at the poles first: that is where the lowest and highest sounds live. The bands are grouped into four zones of 16, and each zone has its own shapes, colours and motion:

| Zone | Range | Shapes | Colour | How it moves |
|---|---|---|---|---|
| **Deep** | 20–107 Hz | solid spheres and fat tori | indigo to blue | heavy, slow breathing; lazy spin; slow orbits |
| **Flow** | 107–570 Hz | dodecahedra, cylinders, cubes | teal to emerald | medium envelopes; spin and orbits pick up speed |
| **Shine** | 570–3,000 Hz | octahedra and cones | gold to orange | fast pinwheels; orbits that loop over the poles |
| **Spark** | 3–16 kHz | wire icosahedra, pins, tetrahedra | magenta to near-white | the snappiest envelopes and the fastest orbits |

Four things happen at once for every band, each driven by that band's own loudness:

- **The whole band swells.** Its root's size follows the band's power, with an instant attack and a decay tuned to the zone (half a second in the Deep zone, about a tenth of a second in Spark), so bass booms linger and treble snaps. Because size cascades down a hyperglyph, all of the band's 55 to 91 nodes breathe as one.
- **The middle ring pops outward** from the band's surface, as altitude.
- **The middle ring spins** like a pinwheel around its outward axis.
- **The outer ring orbits** its parent. Longitude and latitude wrap around, so a loud passage makes the children orbit *faster* rather than fly off into space.

Spin speed, orbit speed and altitude all rise with pitch, so the north pole is far busier than the south. The master glyph also breathes by about 5%, following the overall loudness of the track.

Hover or click a band for its label, for example *DEEP 21 Hz*. The master glyph is labelled with the track name.

## Things to try

**Rearrange all 64 bands at once.** The master glyph's topology decides where its children go. Select the master (node 1) and change its topology in the Properties panel to Torus, Cylinder or Spiral: the whole shell reflows into a ring, a column or a helix while the music keeps playing.

**Stop and look.** Rates are integrated by the viewer, so when you press Stop the speeds go to zero but the orbits stay wherever the music left them. The glyph keeps the shape of the song.

**Compare it with a plainer reading.** [Four Instruments in C Major](audio-four-instruments.md) is the spectral-array version of the same idea: one animated attribute per band. [Warm Winter](audio-warm-winter.md) takes the opposite approach and starts from a multitrack session.

## How it is built

| Level | Count | Role |
|---|---|---|
| Master glyph | 1 | a ghostly wire sphere, the stage; its topology places the bands |
| Band roots | 64 | one per log-spaced band, each a wire sphere on the shell |
| Middle ring | 496 | six, seven, eight or ten per band depending on zone, placed with Sphere topology |
| Outer ring | 3,968 | eight per middle node |

That is **4,529 nodes**, all using Sphere topology so that `translate_z` means altitude above the parent's surface and Channels can move it without disturbing where each child sits. The Channels file has **451 mappings over 257 tracks**: size on each band root and on the master, altitude on both rings, pinwheel spin, and orbit speed (around the equator, or over the poles in the Shine zone).

The generator, `generate_cat_scan_synesthesia.py`, ships with the example along with the notebook that explains the design, so the whole mapping can be changed and regenerated for any WAV file.
