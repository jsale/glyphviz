# Cowles Mountain Terrain

A real digital elevation model — Cowles Mountain, San Diego — as a Surface-topology mesh: a grayscale heightmap supplies elevation and the matching aerial photo supplies per-point color.

![Cowles Mountain Terrain loaded in GlyphViz](../assets/examples/surface-cowles.png)

**Try it:** download this example below (or [the full examples set](../getting-started/installation.md#example-scenes)), then open `Surface_Example/Surface_Example_gv_node.csv` — or just drag its folder onto the GlyphViz window.

[:material-download: Download this example (111 KB)](https://iluvdata.org/glyphviz/zips/Surface_Example.zip){ .md-button }

## What it is

A real mountain, drawn as a solid, lit landscape. Cowles Mountain in San Diego is built from two ordinary pictures: a grayscale **elevation map**, where brighter means higher, and a matching **aerial photograph**. GlyphViz reads them, samples every tenth pixel, and lifts a grid of points to the height each pixel says. Between the points it draws a smooth, shaded surface, coloured from the photograph.

It is the simplest demonstration of the **Surface topology**, and the starting point for the other terrain scenes: [Bird Song Spectrogram Surface](bird-song-surface.md) animates the same mechanism, [Multi-Hike Ghost Race](multi-hike-race.md) walks climbers up this mountain, and [SES Achievement Gap Terrain](ses-achievement-gap-terrain.md) uses it for data rather than rock.

## How to read it

The scene is **1,444 nodes**: one root, and 1,443 children in a grid of 39 columns by 37 rows. Under a Surface-topology parent a child sits at its own literal X and Y, and its `translate_z` is the height at that point. GlyphViz works out the grid by itself from the children's distinct X and Y values, so the file needs no row and column numbers, and it draws a quadrilateral mesh between neighbours.

| Property | Where it comes from |
|---|---|
| **Height** | the grayscale elevation image: a pixel's brightness, from 0 to 255, maps to 0 to 12 world units (the scene calls this 12x height), so the relief is strongly exaggerated |
| **Colour** | the aerial photograph, sampled at the same pixel, so the grid carries the real terrain's colours, with each point's colour shared by the mesh around it |
| **Resolution** | every tenth pixel of the 390 × 369 source images; fewer, larger quads read as a crude model, more as a fine one |

Each grid point is also drawn as a tiny fixed-size point sprite in the same colour, so the points stay cheap to draw and the mesh does the visual work. The scene has one label, on the root: *Cowles Mountain DEM (stride=10, 12x height)*.

## Things to try

- **Orbit low.** Seen from near the horizon the peak and the ridges read as a landscape; seen from directly above they flatten into the aerial photograph.
- **Regenerate at higher resolution.** The generator's `--stride` option sets how many pixels are skipped: `python generate_surface_example.py --stride 5 --exaggeration 16` samples four times as many points and doubles the height scale.
- **Check the exaggeration.** Set `--exaggeration 1` for the true proportions. The mountain is much lower and broader than the default makes it look.
- **Use your own terrain.** Any elevation image with a matching colour image works. Replace the two JPEGs, keep them the same pixel size, and rerun the generator. For a lot of points, set the vertices' scale to zero so they do not draw: see *Large terrain* in the [Topologies reference](../reference/topologies.md#large-terrain-give-the-vertices-scale-0).

## How it is built

The generator, `generate_surface_example.py`, reads the two images with Qt's own image loader, so no extra imaging library is needed. It assumes brighter pixels are higher, which is the convention for an elevation rendering, and says where to flip the sign if a different source is inverted. The two images are co-registered and the same size, which is what lets one set of sample positions index both.

Surface is one of GlyphViz's own topologies. ANTz and GaiaViz have no equivalent, so there is no earlier tool to compare it with. The other topology of this kind is Plot, which joins points into a line rather than a surface.
