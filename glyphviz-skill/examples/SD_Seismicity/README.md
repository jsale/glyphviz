# San Diego Seismicity Callout

Two World Grids — a Blue Marble whole-earth plate and a georeferenced
San Diego aerial plate hovering 230 units above its own footprint — joined
by an amber inset-zoom callout frustum (4 corner glyphs + 8 Link edges).
634 USGS earthquake hypocenters (1960→now) attach to the region grid by
raw longitude/latitude, depth hanging beneath the plate (×6.5 vertical
exaggeration via the grid's `scale_z`), magnitude driving glyph size and a
cold→hot ramp. Channels replay the catalog at one frame per calendar
month: events flash into existence the month they happened, decay to a dim
memory field, and the whole catalog relights before the loop restarts,
while a cursor sweeps a decade-ticked timeline bar.

**What it teaches:** multi-grid composition — a whole-earth reference grid
and a region grid in one scene, the region plate scaled to dominate while
hovering georeferenced above its own footprint; extents-window
georeferencing of an untextured aerial image; depth as negative
`translate_z` re-spaced by grid `scale_z` (exaggeration without touching
glyph sizes); the channel-sharing compression pattern applied to event
data (634 hypocenters on 315 channels — events born the same month share
one `ch_input_id` and one step-function `color_a` track); a
flash-decay-relight alpha profile; and a `translate_x` channel as a
timeline cursor — channel values are coordinates in the node's own parent
space.

Load `sd_quakes_gv_node.csv` with `media/` beside it; the name-paired
ch-map/ch-tracks auto-load; Space plays (~28 s at 30 FPS). Fully
regenerable, even offline: `python build_sd_quake_scene.py --offline
data/usgs_catalog.csv` (live refetch works too — see the script header).
Textures here are downscaled for the skill zip; full-resolution media
lives in the main repo at `examples/SD_Seismicity_Example/`.
