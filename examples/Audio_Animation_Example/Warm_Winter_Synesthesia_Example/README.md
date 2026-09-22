# Warm Winter Synesthesia — one hyperglyph per track

Jeff Sale's *Warm Winter* (3:47, Garage Band, seven keyboard tracks), read from
the **multitrack session** rather than the finished mix. Where
`../Cat_Scan_Synesthesia_Example/` had to split one stereo file into 64
frequency bands, this scene gives each track a hyperglyph of its own — so a
glyph's shape, colour and motion belong to *that instrument*.

5,006 nodes (1 world row + 7 glyphs of 715), 260 channels, 348 tracks ×
6,807 frames at 30 fps. Every node carries a label in the companion tag CSV;
nothing is pinned, so press **T** to read the ones you select.

Load: **File > Open Node CSV** → `Warm_Winter_Synesthesia_Example_gv_node.csv`,
then press Play in the Channels panel. The mixdown plays in sync automatically.

## The song's form is the composition

Every track runs the full file, but each enters a few measures after the
previous and leaves a few measures before it. Measured from the stems
themselves at a -34 dB gate:

| track | plays | window (its own 5–95% rolloff, ±1 octave) | centroid | branch 0 → 1 | colour |
|---|---|---|---|---|---|
| 1 | 0:00 – 3:45 | 242 – 3876 Hz | 826 Hz | Plane → Plane | pale ice blue |
| 2 | 0:17 – 3:30 | 38 – 603 Hz | 328 Hz | Plane → Sphere | pale periwinkle |
| 3 | 0:34 – 3:12 | 82 – 1314 Hz | 630 Hz | Sphere → Sphere | pale violet |
| 4 | 0:52 – 2:54 | 65 – 4188 Hz | 1375 Hz | Spiral → Spiral | amber gold |
| 5 | 1:09 – 2:38 | 67 – 1572 Hz | 879 Hz | Plane → **Rod** | warm orange |
| 6 | 1:27 – 2:19 | 129 – 2067 Hz | 934 Hz | **Rod** → Zrod | scarlet |
| 7 | 1:44 – 2:02 | 75 – 1443 Hz | 510 Hz | **Pin** → Pin | magenta |

A perfectly nested set — ~17.4 s of stagger on each side, the climax centred at
1:53. The scene says that three times over:

* the seven glyphs **stack straight up +Z** in playing order, all seven roots
  on `x = y = 0`, 8 world units apart;
* each glyph's whole size is bound to **its own track's loudness**, so it waits
  as a 38% dormant seed, blooms open when its instrument enters, and folds back
  down when it drops out;
* the **world row is on a channel** — background colour and fog run from a
  near-black, close winter night `(4,6,14)` through a warming dusk `(48,47,73)`
  at the climax and settle at `(19,23,41)` for the fade-out. The ending is
  deliberately *not* as dark as the opening: the ramp that lifts the floor only
  starts climbing after the measured peak, so the world keeps some of the
  warmth the climax gave it. Fog takes the background's colour, so the mist
  always matches the sky.

Open the file without playing and every glyph is at full size under the night
sky — that is the rest state the Stop button restores. "Full size" here means
each root at its own **peak** presence, all seven at once, which is a state the
playback never reaches: the tracks peak at different times, and a dormant glyph
sits at 38% of it. So the file opens about 1.4× larger than a typical playing
frame, and that is deliberate — the scene is sized so that a glyph reads
correctly **while its instrument is playing** (measured: a glyph holds 0.70 of
its written peak while playing), rather than so that the rest state does. Press
Play and the column settles to the size it was tuned at; the climax comes back
up to roughly the opened size.

The glyphs grow into each other once the music is running, and that is the
point rather than a defect: the first pass spread them along an arc wide enough
that no two ever touched, and Jeff replaced it with this column — *"there is
some overlap when the animation plays, but that's the way music is. The
instruments are not isolated from each other in the audio, they are all
overlapping."* The column is what he sees in his synesthesia image.

Tracks 1 and 2 carry a `topo_scale`, set on the Properties panel's Topo Scale
slider — 8.91 and 3.0 respectively. Plane topology reads all three translate
axes as distances, so track 1's spreads that glyph's 4×3 blanket about nine
times wider — the pad that holds the whole song becomes the floor the column
stands on — and track 2's opens its grid of orbs out to three times, which is
what keeps them from crowding once every sphere has grown. No other track
scales.

## Global Scale is baked into the file

Nothing in a node CSV records which Global Scale a scene was authored against,
and this one is tuned at **3.0** rather than the app's 1.0 default. Rather than
ship a file that only looks right after a slider is moved by hand, the
generator bakes that setting into the numbers, so the example opens correct at
GlyphViz's own default.

Global Scale does two things, and it is the second that makes this more than a
size multiplier: every glyph renders that many times larger, *and* it is the
parent-radius term in every topology's placement formula — a Sphere parent puts
a child at `Global Scale + translate_z`, a Pin at `Global Scale + translate_x`
up the spike. A purely Cartesian parent (Plane, None) has no such term, so its
children do not move at all. Global Scale 3.0 is therefore *not* a uniform 3×
zoom: the seven root positions stay where they are, a Plane blanket keeps its
spacing while its glyphs triple, and a Sphere shell spreads by rather less than
it grows.

The exact equivalent, written at Global Scale 1.0, is to multiply each glyph
root's `scale` by 3 — every scale below it is a ratio to its parent's, so one
multiplication at the root carries the whole glyph — and to divide every node's
`topo_scale` by 3, which scales down precisely the translate axes a topology
reads as a distance and leaves every angle alone. Verified node-for-node
against the engine: the baked file at 1.0 reproduces the unbaked one at 3.0 to
1e-9 in both world position and draw matrix, for all 5,006 nodes, static and
mid-playback.

One consequence worth knowing before tuning this scene again: the Topo Scale
the Properties panel shows for a root is a third of the number set on the
slider — track 1 reads `2.9708`, not `8.9125`. Put Global Scale back to 1.0
first, or the bake compounds.

## Why the frequency windows differ per track

A single 20 Hz – 16 kHz window would leave track 2 (the bass) lighting three
bands and the rest dead. Each stem is measured for its own spectral rolloff and
given a window an octave wider each way, so all 12 of a glyph's bands are in
play and the fan shows where *that* instrument lives. The trade is that the
DEEP/FLOW/SHINE/SPARK zones read as each instrument's own low-to-high register
rather than as absolute frequency.

## Rod appears at exactly one level per glyph

A node whose `topo` is Rod is not merely a *placement* rule:
`glyphviz_core/scene.py` draws it 0.25× wide, 5× tall and bottom-capped,
ANTz-style, so the node literally becomes the rod its children are threaded
along. Nesting Rod inside Rod multiplies that 5× at every level and the glyph
collapses into a smear of needles. Track 5 puts Rod at branch 1 — each cell of
the grid blanket grows a rod with its band's children strung up it. Track 6
puts it at branch 0 — one dominating trunk carrying all twelve bands — and
gives the bands **Zrod**, the rod family's centred variant, which rings children
around a node without restyling it.

## Regenerating

The seven stems are **not shipped** (52 MB of source audio); only the mixdown
that plays back is, at `media/warm_winter_all.m4a` — Jeff's own Garage Band
export, remuxed to drop its cover art but with the AAC stream copied
untouched, so there is no second generation of loss. Playback goes through
`QMediaPlayer`, and PySide6 bundles Qt's FFmpeg media backend
(`plugins/multimedia/ffmpegmediaplugin`), so the decoder travels with the app
rather than depending on system codecs. The analysis path never touches this
file: it reads the stems, and `to_wav()` shells out to ffmpeg for anything
that is not already a WAV.

```
python generate_warm_winter_synesthesia.py --stems <folder with track1..track7>
```

Stems may be `.wav` or `.m4a` (ffmpeg decodes the latter into a temp WAV).
Everything else — placement, colour, the channel data, the labels and the
world's arc — is derived from the audio and the tables at the top of
`generate_warm_winter_synesthesia.py`. Its module docstring is the full design
note.

The committed files are a straight run of the script — no hand edits, so
re-running it reproduces them. (Until 2026-09-20 the committed node CSV was one
Jeff had saved out of the app instead; that copy carried the `rotate_z` and
`translate_x` its rate channels had accumulated at the moment of the save — the
"glyph remembers the song" effect — plus sub-unit drift on the seven roots, and
cost 809 KB against this file's 585 KB. Worth knowing if you save an animated
scene mid-playback: the app bakes the accumulated rates into the file.)
