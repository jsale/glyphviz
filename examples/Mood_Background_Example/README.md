# Mood Background

A scene whose **background** is the animated element. A static double helix of
spheres hangs in space; everything you see changing over the 16-second loop is
the World row (type=0), driven by a single channel.

Load `mood_background_gv_node.csv` — the name-paired ch-map/ch-tracks files
auto-load. Press Space to play.

The arc:

| Phase | Background | Fog | Blend |
|---|---|---|---|
| deep night | near-black indigo | on, mid | Normal |
| pre-dawn | violet-grey | on, close | Normal |
| dawn | warm rose-amber | on, wide | Normal |
| clear day | pale sand | **off** | Normal |
| dusk | deep magenta | on, mid | Normal |
| night falls | indigo | on, close | Normal |
| ember glow | near-black | **off** | **Additive** |

**What it teaches:** the World row holds GlyphViz's scene-wide settings, and
Channels can now drive all of them. Give that row a `ch_input_id` like any
other node and bind:

- `color_r` / `color_g` / `color_b` — the **background color**.
- `fog_enabled` / `fog_start` / `fog_end` — atmospheric depth. Fog fades
  toward the background color, so the two move together for free.
- `render_mode` — the scene-wide blend mode (0 Normal, 1 Additive,
  2 Subtractive, 3 Dark/Multiply, 4 Off, 5 Screen, 6 Premultiplied).

One channel, seven tracks, and every glyph in the scene is affected at once —
no per-glyph animation data at all.

## Two things worth knowing

**Fog cancels Additive.** Fog fades geometry toward the background color, so
thick fog over a near-black sky subtracts exactly what Additive blending is
adding and the glyphs vanish. The ember phase turns fog off for that reason —
Additive only reads well on a dark, unfogged background. It's the single
easiest way to get a "nothing is rendering" result from a scene that is in
fact working perfectly.

**Integer fields are step functions, not ramps.** `fog_enabled` and
`render_mode` are rounded and clamped on the way in, so interpolating them
between keyframes just produces meaningless intermediate modes. The generator
holds each at its keyframe value until the next key; only the colors and the
two fog distances are interpolated. And remember the engine does **no**
interpolation of its own — every smooth fade you see is precomputed per frame
in `build_tracks()`.

## Making it your own

`MOODS` at the top of `generate_mood_background.py` is the whole design: a
list of `(t, name, rgb, fog_enabled, fog_start, fog_end, render_mode)`
keyframes on a normalized 0–1 timeline. Edit it, rerun
`python generate_mood_background.py`, reload. `t = 1.0` repeats `t = 0.0` so
the loop closes seamlessly; drop that and the loop will jump.

Fog distances are in world units of eye-space depth, so they depend on how far
your camera sits from the scene — expect to retune them if you swap the helix
for your own geometry.

To drive this from audio instead of a fixed arc, drop a `*_gv_audio.txt`
manifest in the folder pointing at a WAV; frame advance then follows the
audio's real playback position rather than the FPS timer.
