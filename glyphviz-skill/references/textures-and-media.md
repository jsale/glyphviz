# Textures, video, and audio — `texture_id` and the `media/` folder

Verified against `glyphviz_gl/texture_manager.py`, `video_manager.py`,
`main_window.py` (2026-07-17), and `glyphviz_gl/geometry.py` (2026-08-13).

## How `texture_id` maps to files

There is no per-node file path: `texture_id` is a **1-based index into the
alphanumerically sorted contents of a `media/` folder**.

- At startup GlyphViz loads `media/` next to the app itself; when a CSV is
  opened, a `media/` folder next to the CSV **takes precedence** (replaces
  the loaded set). Ship scene textures in `media/` beside `gv_node.csv`.
- **Images load first**: files with extensions `.png .jpg .jpeg .jfif .bmp
  .tga .gif .tif .tiff .webp`, sorted alphanumerically → `texture_id` 1..N.
- **Videos continue the numbering**: `.mp4 .avi .mov .mkv .webm .m4v .wmv
  .flv`, sorted alphanumerically → `texture_id` N+1... So with
  `alpha.png, beta.jpg, clip.mp4` the ids are 1, 2, 3 — and adding a new
  image renumbers every video after it.
- `texture_id = 0` (the default) means untextured.

**Authoring rule**: name media files so their sort order is deliberate
(e.g. `01_earth.jpg`, `02_moon.jpg`), derive each node's `texture_id` from
that sorted order in the generator, and never mix "extra" files into
`media/` — every image/video file in the folder consumes an id.

## Which geometries actually show a texture

`texture_id` is never gated by `geometry` anywhere in the format — any node may
carry any id — but only some shapes *render* one. Setting a texture on the
others is silently ignored (no error, no warning), so check this table before
you spend media slots on it:

**Textured**

- Every solid primitive: Cube 1, Sphere 3, Cone 5, Torus 7, Dodecahedron 9,
  Octahedron 11, Tetrahedron 13, Icosahedron 15, Pin 16, Cylinder 19, Grid 21.
- **Circle 24, Cross 25, Star 26** — the flat markers (added 2026-08-06; they
  rendered untextured before that).
- Prism 28 on a Link node — the scrollable directed-flow tube.

**Untextured — the id is read and then ignored**

- Every **wireframe** variant: 0, 2, 4, 6, 8, 10, 12, 14, 17, 18, 20.
- Point 22 — a fixed-pixel `GL_POINTS` sprite drawn outside the display-list
  system, so it has no surface to map onto.
- Mesh 23 — imported meshes render in their node color only.
- Line 27 — the plain Link connector (use Prism 28 if you need a texture).

The three flat markers reuse the Grid's own `[-1,1]²  →  [0,1]²` mapping, so an
image gets **cropped to the marker's silhouette** rather than stretched to fit
it — a texture keeps identical framing and orientation whether it lands on a
Grid, a Circle, or a Star. Being flat, all three show the texture face-on and
vanish to an edge side-on: they work as billboards in a fixed-camera or
top-down scene, not in one the user will orbit freely.

## Animated textures

- **Multi-frame GIFs** are detected automatically and play with their own
  embedded per-frame delays — the cheapest way to get an animated surface;
  no Channels setup needed.
- **Videos** render as live animated textures (decoded via Qt Multimedia,
  bundled with standard PySide6 on Windows; if unavailable, videos are
  skipped with a console notice).
- A World Grid's solid form maps its texture equirectangularly across the
  extents window (flat) or the globe — a lon/lat map image lines up with
  KML-placed children automatically.

## Video audio and "Solo Audio to Selection"

Every loaded video's audio track plays through its own output:

- **Default**: all loaded videos are audible at once (OS-mixed, like
  multiple browser tabs).
- **Audio-track dropdown** (Display panel): pick "Only: <file>" to solo one
  track, or "All Audio Tracks" to unmute everything.
- **"Solo Audio to Selection" checkbox** (Display panel, **off by
  default**): while checked, selection drives the mix — only videos
  textured on currently *selected* nodes play; selecting several
  video-textured nodes plays them together; selecting none mutes all. It
  overrides the dropdown while checked.

Authoring implications for multi-video scenes: the scene is a wall of sound
until the user intervenes, so (a) tell users about the checkbox in your
handoff notes, and (b) make each video-textured node comfortably clickable
(adequate scale, not buried inside other glyphs) since selecting it is how
its audio gets isolated.

## What this is NOT

- Audio playback is **not synchronized** to Channels animation frames —
  video textures and channel playback run on independent clocks. Do not
  design scenes that depend on audio/animation sync.
- There is no per-node volume, pan, or audio-only (non-video) media field.
