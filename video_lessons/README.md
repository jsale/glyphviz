# Lesson videos

Short narrated feature lessons rendered straight from the GlyphViz engine:
no screen recording, no editing timeline. Each lesson is a Python file; one
command turns it into an MP4 with narration, burned-in captions, a separate
`.srt`, and the lesson's own scene CSV.

```powershell
& $env:GLYPHVIZ_PYTHON video_lessons/render_lesson.py tags camera_mode torus
& $env:GLYPHVIZ_PYTHON video_lessons/render_lesson.py torus --stills-only   # look first
& $env:GLYPHVIZ_PYTHON video_lessons/render_lesson.py torus --draft         # 640x360@15
```

Output goes to `video_lessons/out/<lesson>/` (gitignored): `<lesson>.mp4`,
`<lesson>.srt`, `<lesson>.narration.wav`, `scene/<lesson>_gv_node.csv`.
A ~40 s lesson renders in about 30 s.

The MP4s are **assets for the docs site**. Only this folder's source is
committed; any video can be rebuilt from it with one command, which also
means every video can be re-rendered after a UI or rendering change.

## The lessons

| lesson | kind | length |
| --- | --- | --- |
| `parent_children` | feature: N, Shift+N, New Object Defaults, topology | ~74 s |
| `tags` | feature: tag labels | ~35 s |
| `camera_mode` | feature: Camera Mode flight | ~32 s |
| `torus` | feature: Torus topology | ~37 s |
| `building_glyphviz` | **example explainer**: the Building GlyphViz gallery scene | ~138 s |
| `channels_sine` | Channels 1/3: tracks, map, Channel In, on a lesson copy of Sine Wave | ~102 s |
| `channels_hike_race` | Channels 2/3: GPS data, the Multi-Hike Ghost Race | ~97 s |
| `channels_river_pulse` | Channels 3/3: at scale, The Pulse (70,809 nodes) | ~103 s |
| `climate_rings` | **workflow**: a spreadsheet, a prompt, a drop: City Climate Rings | ~106 s |

All nine are narrated in `af_heart`, Jeff's pick of the Kokoro voices.

## Example explainers

An example video films a shipped gallery scene instead of a generated one,
and takes its screenplay from that example's gallery page.

- `Lesson(scene_csv=...)` films an existing node CSV exactly as the app opens it.
- `Shot(scene=...)` cuts to another CSV at the start of a shot.
  `building_glyphviz` uses this to teach reading a column on the small
  Five Archetypes scene, then cuts back to the full scene.
- Anchor callouts on the scene's own pinned nameplates and legend; look up
  their node ids by label.
- A dense scene can't take a close-up. Find a clean companion scene or
  column for the detail shots.
- To fit a clicked label in frame, offset the camera target along the view's
  right vector (at azimuth `a`, that's `(-sin a, cos a, 0)`).
- Numbers spoken in narration are dated to the gallery page. Re-check them
  whenever the example is regenerated.

`building_glyphviz` unpacks its gitignored 6 MB scene from
`Building_GlyphViz_Scene.zip` on first use.

## How it works

1. `narrate.py` speaks each shot's `say` line with Windows' built-in SAPI
   voice (no install, offline) and caches the WAVs by text hash.
2. Each clip's length sets its shot's length, so voice and picture can't drift.
3. `lessonkit.render` drives the **real** `Viewport` (via
   `tools/export_frame._build_viewport`) frame by frame: it animates node
   fields, eases the camera between keyframes, grabs the framebuffer, draws
   overlays with PIL, and pipes raw frames into ffmpeg.
4. The narration track is laid under the video, and captions come from the
   same lines.

Everything in the 3D view is the app's own renderer, so a lesson can't show a
feature behaving differently from the app. Only the overlays (title, captions,
key caps, callouts, mouse-drag glyph, value readout, recap card) are drawn
outside the engine.

## Writing a lesson

Add `lessons/<name>.py` with a `build() -> Lesson`. A `Shot` holds:

| field | what it does |
| --- | --- |
| `say` | the narration line (and the caption) |
| `keys` | camera `Key`s at shot fractions `u` 0..1: orbit (`az/el/dist/target`, where `target` may be a node id that is tracked) or flight (`eye` + `az/el`) |
| `select`, `state`, `events` | the selection and Viewport attributes (`show_tags`, ...) at the start of the shot or at a time `u` |
| `animate(lesson, u)` | mutates node fields per frame (`lesson.node(id)`) |
| `callouts` | a ring plus a leader-line label anchored to a node's projected screen position |
| `keycap` / `keycap_note` | the key-cap badge; also takes `f(u) -> (key, note)` |
| `gesture(u)` | the mouse glyph: `{button, offset, label}` |
| `readout(lesson, u)` | a live monospace value box |
| `title`, `summary` | the opening title card and the recap card |

Check every UI fact in the narration against the code before rendering. For
example, additive selection is **Ctrl**+click, not Shift.

## Voices

The default is **Kokoro** (natural neural TTS, offline). Each lesson picks
its voice with `Lesson(voice=...)`; `--voice` overrides it and `--rate` sets
the speed (1.0 = normal). Voices in use: `af_heart` (US female, Kokoro's
best-rated), `am_michael` (US male), `bf_emma` (British female). Others to
try include `af_bella`, `am_fenrir` and `bm_george`.

Kokoro lives in its **own** venv, never the glyphviz env, because
kokoro-onnx pins onnxruntime/numpy versions the app must not inherit.
`narrate.py` runs `kokoro_worker.py` inside it as a subprocess. One-time
setup (about 350 MB):

```powershell
$k="$env:LOCALAPPDATA\GlyphViz\kokoro"; mkdir $k
& $env:GLYPHVIZ_PYTHON -m venv "$k\venv"
& "$k\venv\Scripts\python.exe" -m pip install kokoro-onnx soundfile
$r="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
curl.exe -L -o "$k\kokoro-v1.0.onnx" "$r/kokoro-v1.0.onnx"
curl.exe -L -o "$k\voices-v1.0.bin" "$r/voices-v1.0.bin"
```

`--engine sapi` falls back to Windows' built-in voices (robotic, but needs no
setup).

## Channels lessons

A `use_window` lesson with `scene_csv` opens the scene through File > Open's
own path (`MainWindow._load_csv_path`), so its ch-map/ch-tracks, tags, media/
and meshes/ all load as they do for a user. The animation then runs on a
clock driven by **video time**, not the app's QTimer, through the same
`_ch_apply_and_show_frame` the play timer calls:

| Shot field | what it does |
| --- | --- |
| `ch_rate` | frames per second of video from this shot on (0 pauses) |
| `ch_frame` | jump the animation to this frame at the shot's start |
| `ch_span` | play frame A -> B across the shot, or `((u, frame), ...)` to arrive and hold; chain shots A->B, B->C so playback never skips |
| `card` | `f(overlay, draw, u)`: a custom full-frame card (tables, prompts) |

`Lesson(prepare=...)` runs before rendering, e.g. to write a lesson's own copy
of a scene into `out/` (`channels_sine` adds pulse, colour and ripple channels
to a copy of Sine Wave; the shipped example is never touched). A lesson that
films a `scene_csv` never saves back over it.

Channel In changes go through the Properties panel's own spin box
(`MainWindow._insp_ch_in`); the readout prints that spin box and its hint.

## The workflow lesson's data

`examples/City_Climate_Rings_Example/` (a gallery example) holds everything
`climate_rings` shows: `city_climate.csv` (NASA POWER daily data 2001-2020,
averaged by month; `fetch_climate.py` rebuilds it), `prompt.md` (the prompt),
and `build_climate_rings.py` (the generator for that prompt, which verifies
its own geometry through GlyphViz's engine before writing). The lesson writes the
scene into `out/` and drops the folder on a real MainWindow through
`MainWindow.apply_drop`. To film a ring with its bars upright, the lesson
turns the globe (an ordinary rotatable node) to bring each city to the top.

## Lessons that act like a user

`Lesson(use_window=True)` renders through a real, never-shown `MainWindow`.
Events can then call the app's own handlers (`_create_root_node` for N,
`_create_child_node` for Shift+N, the New Object Defaults widgets, table
selection, the Properties Topology list), so the video shows exactly what
those actions do. See `lessons/parent_children.py`.
