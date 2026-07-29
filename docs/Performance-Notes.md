# GlyphViz Rendering Performance Notes

Record of the 2026-06/07 rendering-performance work, the measured results,
and how to benchmark — including against ANTz on the same files.

## How to benchmark

```
python tools/benchmark_frames.py --csv path/to/scene_node.csv
```

Options: `--frames N`, `--no-tags`, `--no-grid`, `--no-axes`, `--stereo`,
`--width/--height`. Renders headlessly through the real `Viewport` (the same
code path as the desktop app) and reports ms/frame + fps.

**Caveat for absolute numbers:** each headless frame includes a synchronous
`grabFramebuffer()` GPU→CPU readback (~3.7 MB at 1280×720) that interactive
vsync'd rendering never does, so headless fps understates on-screen fps.
Use this tool for *relative* comparisons between GlyphViz builds.

**Comparing against ANTz:** use each app's own on-screen FPS counter, same
file, same machine, same window size. GlyphViz shows fps in the status bar
(`Viewport.fpsUpdated`). Load an ANTz-format `np_node.csv` in both. Note
that GlyphViz's first 1–2 frames after load/edit are slower (see "retained
scene display list" below) — compare steady-state orbiting, not the first
seconds.

## Reference numbers

Benchmark file: `examples/CalStateTesting_Example/CalStateTesting_Example_gv_node.csv`
(8,320 nodes: 4,255 icosa, 3,048 cylinder-wire, 508 sphere, 508 torus, 8,319
text tags). Machine: Jeff's Windows 11 dev box. 1280×720, tags on, headless.

| Stage | ms/frame | cumulative speedup |
|---|---|---|
| Session start (2026-06-30) | 1,597 | — |
| Round 1: display-list caching for textured/torus geometry, frustum culling, 500-tag cap (commit 6e00c30) | 503 → re-measured 830* | 3.2x |
| Tier 1: PyOpenGL error checking off | 253 | 6.3x |
| Tier 2: per-node draw-data cache in Scene | 122 | 13x |
| Tier 3: retained scene display list | **38** (22 with tags off) | **42x** |

\* Run-to-run variance between sessions; the Tier 1–3 A/Bs were measured
back-to-back in one session against the 830 ms control.

## What each fix was (newest first)

### Tier 3 — Retained scene display list (`viewport.py`)

The whole per-node draw loop (matrix loads, colors, texture binds, geometry
list calls) is baked into **one** OpenGL display list and replayed with a
single `glCallList` while scene *content* is unchanged. Camera motion never
triggers a rebake (the camera lives on the modelview stack outside the
baked commands). This removes per-node Python entirely for static scenes —
the same reason ANTz is fast: ANTz's per-node loop is compiled C; ours is
now compiled GL commands.

- Rebake key: `(Scene._revision, Viewport._assets_rev, show_hidden,
  _draw_limit)`. `Scene.invalidate()` bumps `_revision` (all node edits,
  gizmo drags, base-scale changes, rate animation); `_assets_rev` covers
  texture/video folder loads and mesh registration.
- Bake happens on the *second* stable frame; the first frame after any
  change renders immediate-mode (with CPU frustum culling). Rate-animated
  scenes change every frame, so they stay on the immediate path.
- Selection outlines draw in their own pass (`_draw_selected_outlines`) so
  selecting/deselecting never rebakes.
- Videos/GIFs keep playing inside the baked list (binds are by texture
  name; content updates under the same name). Baked video texture_ids are
  re-marked "visible" each frame so `VideoManager.finalize_frame()` doesn't
  pause them.
- Torus per-ratio lists are pre-warmed before baking — `glNewList` cannot
  nest, so `GeoRenderer.ensure_torus_list()` exists to compile them outside
  the bake. Nothing evicts those lists (a compiled one may be referenced by
  the retained scene list), so the ratio key is quantized to 1% steps: a
  Channels animation sweeping `ratio` continuously costs ~100 lists per
  geo/textured pair instead of one per distinct float.

### Tier 2 — Per-node draw-data cache (`scene.py`)

`Scene.node_draw_data(node)` caches `(world matrix, float32 column-major
GL form, bounding radius)` per node until `invalidate()`. Previously all
three were recomputed per node per frame even for static scenes. Used by
the draw loop, the frustum cull, and the pick pass.

### Tier 1 — PyOpenGL error checking off (`glyphviz_gl/__init__.py`)

PyOpenGL wraps **every** GL call with `glGetError()` by default — 66k+
per frame on this file, 51% of profiled CPU time, and worse under GPU load
because `glGetError` can force a pipeline sync. Disabled at import time.
**Set `GLYPHVIZ_GL_DEBUG=1` to re-enable per-call GL error checking** when
debugging rendering issues.

### Round 1 (commit 6e00c30)

- Textured geometry + torus compiled into display lists (torus was
  regenerated vertex-by-vertex in Python per node per frame — 37x).
- View-frustum culling (Gribb/Hartmann plane extraction, bounding-sphere
  test) — now only used on the immediate path.
- Tag projection MVP hoist + `_MAX_TAGS_PER_FRAME = 500` cap (QPainter text
  is CPU-rasterized and unbatched).

## Remaining known costs / future work

- **Tag overlay** (~16 ms/frame at the 500-tag cap): QPainter per-frame
  text. A GPU text path (cached label textures / bitmap-font atlas) would
  cut this and could raise/remove the cap.
- **First-frame latency** after load/edit: one immediate-mode frame + one
  bake frame. Could pre-bake at load if it ever feels sluggish.
- **Rate-animated scenes** never use the baked list; their ceiling is the
  immediate path (Tier 1+2 improvements still apply). Vectorizing
  `compute_world_bases`/`compute_world_positions` with numpy would be the
  next lever for those.
- **GPU instancing / modern GL** remains the long-term modernization path
  (and the likely architecture for the XR renderer), but is no longer
  needed for ANTz parity on static scenes.
