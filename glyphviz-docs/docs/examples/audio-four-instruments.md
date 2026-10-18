# Four Instruments in C Major

The audio-Channels pipeline run on a four-instrument piece in C major — watch different instruments light up different regions of the 64-band spectral array.

![Four Instruments in C Major loaded in GlyphViz](../assets/examples/audio-four-instruments.png)

**Try it:** download this example below (or [the full examples set](../getting-started/installation.md#example-scenes)), then open `Audio_Animation_Example/Four_Instruments_C_Major_Example/Four_Instruments_C_Major_Example_gv_node.csv` — or just drag its folder onto the GlyphViz window. Press **Space** to start the animation.

[:material-download: Download this example (2 MB)](https://iluvdata.org/glyphviz/zips/Four_Instruments_C_Major_Example.zip){ .md-button }

## What it is

This is the plainest version of GlyphViz's audio pipeline, and the best place to start with it. A 32-second recording of four instruments playing a major scale is split into **64 frequency bands**, and each band gets its own small hyperglyph. When the music plays, each hyperglyph rises and falls with the loudness of its band. Nothing else moves.

Because the bands are laid out left to right from low pitch to high, you can watch the scale climb across the scene as each instrument takes its turn.

## How to read it

- **Left to right is low to high.** The 64 glyphs sit in a row along the X axis, 3 units apart, from about 20 Hz at the far left to 16 kHz at the far right. The bands are log-spaced, which is how pitch is heard: each octave gets about the same room.
- **Colour is a label, not a signal.** It runs from blue for the lowest band to red for the highest, so you can tell bands apart at a glance. It never changes during playback.
- **Height is loudness.** Everything in a band lifts off its parent's surface in proportion to how much energy that band has in the current frame. At full power a band's root rises eight units, and its smaller children rise less, because their offsets are measured against their parents' smaller sizes.
- **Click a glyph** to see the band's centre frequency, for example *21 Hz*. Every band is labelled.

Each band is a **three-level hyperglyph**: a wire sphere at the root, four shapes spaced around its equator, and two more around each of those, which is 13 nodes per band and **832 in the scene**. The shapes are chosen at random from nine wireframe geometries with a fixed seed, so the scene looks the same every time it is regenerated.

## What to try

**Move between bands.** Press **Space** once to hear and see the whole 32 seconds, then drag the Channels slider to a moment you like and orbit the camera down the row.

**Rewire a glyph.** Every node in a band shares one *Channel In* number. Select one band's root and change its Channel In in the Properties panel to a different band's number: that root now follows the other band while its children keep following their own. It is the shortest demonstration there is of how the Channels join works.

**Read the scale.** Each note of the scale lights one region of the row for a moment before the next takes over. A real instrument's note also puts energy into bands above it, because it is a fundamental plus a stack of overtones, so expect a note to leave more than one glyph lit.

## How it is built

The generator, `generate_audio_example.py`, runs a sliding-window FFT over the WAV file at 30 frames per second and measures each log-spaced band by its loudest frequency bin rather than an average, so a single pure tone reads the same loudness at any pitch. Each band is then normalized to its own peak across the clip, so quiet treble bands stay as legible as loud bass ones, with a floor at a tenth of the loudest band so that leakage from a neighbouring tone is not blown up to full scale.

The result is written as the usual Channels pair: a **map** of 64 channels each bound to `translate_z`, and a **tracks** file of 960 frames. A one-line manifest names the WAV, and GlyphViz plays it in sync with the animation automatically.

Every level uses Sphere topology, and that choice matters. Under Sphere topology a child's X and Y are longitude and latitude, which are just *where* on its parent it sits, and Z is altitude above the parent's surface, which is a separate axis. Channels can therefore push the glyph outward every frame without disturbing where each child sits around its parent. An earlier attempt with no topology made parents and children translate together as one rigid block, with nothing moving relative to anything else.

Point the generator at any mono WAV (`--wav yourfile.wav`) to build the same scene from your own audio.
