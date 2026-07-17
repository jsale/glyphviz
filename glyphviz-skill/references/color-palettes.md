# Color palettes — `color_index` and `palette_id`

Verified against `glyphviz_core/color_palette.py` and
`glyphviz_gl/main_window.py` (2026-07-17). The sample resolutions below are
engine output from `resolve_palette_color()`, not hand math.

## The model (read this first — it's not what you'd guess)

A node's rendered color is always the **literal** `color_r/g/b` value.
`palette_id` + `color_index` are dormant metadata: GlyphViz resolves them
into `color_r/g/b` **only when the user presses the cycle keys** —
`=` / `-` steps `color_index` (wrapping within the palette's index range),
`Alt+=` / `Alt+-` steps `palette_id` (re-clamping the index) — each keypress
overwriting `color_r/g/b` with the resolved color. Loading a file never
resolves them; rendering never resolves them. `color_a` is never touched by
palette resolution.

Consequences for generated data:

- **If the scene must look right on load, write literal `color_r/g/b`** —
  compute the ramp yourself (formulas below reproduce the built-ins
  exactly).
- **Also setting `color_index`/`palette_id` is cheap and useful**: it
  pre-wires the scene for in-app recoloring. E.g. `color_index` = branch
  level (or category ordinal) with matching literal colors means one
  `Alt+=` press later repaints the whole selection coherently in the next
  palette.
- **Every index resolves to a real color.** There is no "no color" /
  "unset" sentinel: palette 0's index 0 is Caribbean current
  `(50, 101, 101)` — ANTz's documented default node color — not "none".
- Picking a color via the RGB color-picker leaves `color_index`/`palette_id`
  untouched (they simply go stale until the next cycle keypress overwrites
  `color_r/g/b` again — matches documented ANTz behavior).

CSV notes (see `node-csv-format.md`): `color_index` is canonical 94-column
slot 55; `palette_id` has **no** 94-column slot — GlyphViz appends it as an
extension column only when some node's value is nonzero. Both default to 0.

## The 26 palettes

Odd id = the even id below it with every channel inverted (255 − c).

| id | Name | Index range |
|---|---|---|
| 0 / 1 | 20 Distinct Colors / (Inverted) | 0–19 |
| 2 / 3 | Rainbow Heatmap / (Inverted) | 0–127 |
| 4 / 5 | Blue → Green / (Inverted) | 0–127 |
| 6 / 7 | Green → Red / (Inverted) | 0–127 |
| 8 / 9 | Blue → Red / (Inverted) | 0–127 |
| 10 / 11 | Purple → Yellow / (Inverted) | 0–127 |
| 12 / 13 | Black → Red / (Inverted) | 0–127 |
| 14 / 15 | Black → Green / (Inverted) | 0–127 |
| 16 / 17 | Black → Blue / (Inverted) | 0–127 |
| 18 / 19 | White → Red / (Inverted) | 0–127 |
| 20 / 21 | White → Green / (Inverted) | 0–127 |
| 22 / 23 | White → Blue / (Inverted) | 0–127 |
| 24 / 25 | Greyscale / (Inverted) | 0–127 |

`color_index` outside the range wraps (modulo), it doesn't clamp.

## Palette 0 — the 20 distinct colors

| idx | RGB | Name | idx | RGB | Name |
|---|---|---|---|---|---|
| 0 | 50, 101, 101 | Caribbean current (default) | 10 | 185, 153, 102 | Lion (gold) |
| 1 | 0, 255, 0 | Green | 11 | 255, 180, 255 | Mauve |
| 2 | 255, 0, 0 | Red | 12 | 0, 152, 255 | Dodgers blue |
| 3 | 0, 0, 255 | Blue | 13 | 185, 255, 0 | Lime |
| 4 | 255, 255, 0 | Yellow | 14 | 152, 0, 0 | Penn red |
| 5 | 152, 0, 255 | Electric violet | 15 | 127, 127, 127 | Gray |
| 6 | 255, 168, 0 | Orange | 16 | 127, 127, 255 | Tropical indigo |
| 7 | 0, 255, 255 | Cyan | 17 | 197, 82, 0 | Tawny |
| 8 | 255, 0, 255 | Fuchsia | 18 | 0, 0, 0 | Black |
| 9 | 0, 153, 0 | Forest green | 19 | 255, 255, 255 | White |

For categorical data, indices 1–17 give the most-distinct sequence (0 is the
muted default; 18/19 are black/white and vanish against dark/light
backgrounds).

## Gradient formulas (reproduce them in generated data)

For gradient palettes (ids 2–25), with `t = (color_index % 128) / 127`:

- **Two-color gradients** (ids 4–25, even): per-channel linear
  interpolation, `round(start + (end − start) · t)`. Endpoints: Blue→Green
  `(0,0,255)→(0,255,0)`; Green→Red `(0,255,0)→(255,0,0)`; Blue→Red
  `(0,0,255)→(255,0,0)`; Purple→Yellow `(152,0,255)→(255,255,0)`;
  Black→X from `(0,0,0)`; White→X from `(255,255,255)`; Greyscale
  `(0,0,0)→(255,255,255)`.
- **Rainbow Heatmap (2)**: HSV sweep, `hue = t`, full saturation/value —
  note it wraps back to red at index 127, so for a heatmap that shouldn't
  wrap, cap your indices below ~106 (hue ≈ 300°, magenta) or use a
  two-color gradient instead.
- **Odd ids**: compute the even id's color, then invert each channel
  (255 − c).

Engine-verified sample resolutions:

- palette 0 index 0 → (50, 101, 101)
- palette 0 index 4 → (255, 255, 0)
- palette 2 index 0 → (255, 0, 0)
- palette 2 index 64 → (0, 249, 255)
- palette 4 index 127 → (0, 255, 0)
- palette 9 index 0 → (255, 255, 0)
- palette 24 index 64 → (129, 129, 129)

## Recipe: category coloring that survives both worlds

For n categories: give category i `color_index = i + 1` (skipping the muted
default at 0) and set `color_r/g/b` to the palette-0 table's entry for that
index. The scene loads correctly colored AND the user can re-theme it live
with Alt+= / Alt+-. For continuous values: map value → index 0–127 on a
gradient palette, write both the index and the lerped literal color.
