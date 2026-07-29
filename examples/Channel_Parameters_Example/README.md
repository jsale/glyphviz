# Channel Parameters

A test bench: seven labeled stations in a row, one per newly-bindable Channels
attribute, each driven by its own channel and a single track. The ch-map reads
as a legend.

Load `channel_parameters_gv_node.csv` — the name-paired ch-map/ch-tracks files
auto-load. Press Space to play. The 8-second loop runs every station at once.

| Station | Attribute | What to watch |
|---|---|---|
| 1 | `ratio` | a torus tube swells; its 8 children ride the swell apart and inward |
| 2 | `topo` | a parent's 12 children re-lay-out as the topology steps Sphere → Torus → Cylinder → Cube → Spiral |
| 3 | `geometry` | one glyph cycles through eight solid shapes |
| 4 | `color_index` | one track sweeps the 128-entry Rainbow Heatmap palette |
| 5 | `palette_id` | one glyph steps through all 26 built-in palettes at a fixed index |
| 6 | `hide` | a glyph strobes 4 frames on / 4 off |
| 7 | `show_text` | a tag label pops on for 12 frames once a second |

**What it teaches:** stations 1 and 2 are the important ones. `ratio`, `topo`
and `geometry` re-place a node's **children**, not just its own appearance, so
those stations show a whole subtree rearranging from a single track. The other
five change only what is drawn.

Station 4 is the one that changes how you author data: a single track carrying
a palette index replaces the three-track `color_r`/`color_g`/`color_b` pattern
whenever a built-in ramp is close enough, cutting the tracks file to a third
of its width. Set `palette_id` once in the node CSV and animate `color_index`.

## The torus subtlety

Station 1's children sit at tube angles 90° and 270° (`translate_y`), not 0°.
That is deliberate: a torus's major and minor radii always sum to its overall
radius, so a child on the tube's **outer equator** (tube angle 0) sits at the
same place for every value of `ratio` and looks completely static. Put
children on the top or bottom of the tube to see the swell.

## Not covered here

`mesh_id` is bindable too, but it selects among meshes imported at runtime via
*File → Import Mesh*, so it can't be demonstrated from a CSV alone. Bind it
exactly like `geometry` once you have meshes loaded.

Scene-wide settings — background color, fog, blend mode — live on the World
row and get their own example: see `../Mood_Background_Example/`.

## Regenerating

`python generate_channel_parameters.py` rewrites all three CSVs in place.
`build_tracks()` holds each station's track in a few lines; `TOPO_CYCLE` and
`GEO_CYCLE` at the top control what stations 2 and 3 step through.

Integer flip-books (`topo`, `geometry`) hold each value for a beat rather than
stepping every frame — step them per-frame and the scene reads as noise.
