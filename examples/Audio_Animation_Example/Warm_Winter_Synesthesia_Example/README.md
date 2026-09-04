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
sky — that is the rest state the Stop button restores.

The glyphs grow into each other once the music is running, and that is the
point rather than a defect: the first pass spread them along an arc wide enough
that no two ever touched, and Jeff replaced it with this column — *"there is
some overlap when the animation plays, but that's the way music is. The
instruments are not isolated from each other in the audio, they are all
overlapping."* The column is what he sees in his synesthesia image.

Track 1 also carries a `topo_scale` of 8.91, set on the Properties panel's Topo
Scale slider. Plane topology reads all three translate axes as distances, so it
spreads that glyph's 4×3 blanket about nine times wider — the pad that holds
the whole song becomes the floor the column stands on. No other track scales.

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
that plays back is, at `media/warm_winter_all.wav`.

```
python generate_warm_winter_synesthesia.py --stems <folder with track1..track7>
```

Stems may be `.wav` or `.m4a` (ffmpeg decodes the latter into a temp WAV).
Everything else — placement, colour, the channel data, the labels and the
world's arc — is derived from the audio and the tables at the top of
`generate_warm_winter_synesthesia.py`. Its module docstring is the full design
note.

The committed node CSV is the one Jeff saved out of the app, so it differs from
a fresh run in three harmless ways: it is in the 94-column save format rather
than the generator's compact one; the seven roots sit within half a unit of
`x = y = 0` rather than exactly on it (they were dragged, not typed); and the
branch-2/3 rows carry the `rotate_z` and `translate_x` the rate channels had
accumulated at the moment of the save — the "glyph remembers the song" effect,
which on periodic axes is a uniform phase offset per band and nothing more.
Every design field matches the generator exactly.
