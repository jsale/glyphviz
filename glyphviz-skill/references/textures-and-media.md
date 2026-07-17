# Textures, video, and audio — `texture_id` and the `media/` folder

Verified against `glyphviz_gl/texture_manager.py`, `video_manager.py`, and
`main_window.py` (2026-07-17).

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
