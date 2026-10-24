# Fetch Basemap

Any dataset with longitude/latitude can sit on a real map with one click.
Select a World Grid, press **Fetch Basemap…** in the World Grid panel, and
GlyphViz measures your data's lon/lat bounding box, downloads map imagery for
exactly that window from a free map service, and applies it as the grid's
texture — with the grid's extents set to the map's precise coverage, so glyphs
and map features line up.

No account and no API key are needed. Three map styles are built in:

| Style | Source | Good for |
|---|---|---|
| **Streets** (default) | OpenStreetMap | Cities, roads, place names |
| **Satellite** | Esri World Imagery | Terrain, land cover, aerial context |
| **Terrain** | OpenTopoMap | Elevation shading, contours, trails |

The provider's required attribution is stamped into the image corner, so it
stays with the scene wherever the file goes.

## Using it

1. Load or build a scene whose points sit on a World Grid (children of a
   type-6 node, `translate_x` = longitude, `translate_y` = latitude).
2. Select the grid — press **G**, or pick it in the node table.
3. Click **Fetch Basemap…** in the World Grid panel.
4. The lon/lat window is prefilled from your data (with a little padding);
   the dialog previews exactly what a fetch will do — zoom level, tile count,
   output size — as you adjust it. **Fit to Children** restores the data-driven
   window after manual edits.
5. Click **Fetch**. The map appears under your data.

The image is written into the scene's `media/` folder (as
`zz_basemap_grid<id>.png`) beside the node CSV, so the basemap loads with the
scene from then on — including through drag-and-drop and zip sharing. Saving
the scene also persists the extents and texture assignment; other nodes'
`texture_id`s are adjusted automatically if the new image changes the media
numbering. Refetching for the same grid overwrites the same file in place.

## Details worth knowing

- **The map is reprojected.** Tile servers publish Web Mercator; a World Grid
  drapes its texture linearly in latitude (plate carrée). GlyphViz resamples
  the imagery so the two agree — without this, points at US latitudes would sit
  tens of pixels off the map.
- **Tiles are cached on disk** (`%LOCALAPPDATA%\GlyphViz\tile_cache`), so
  refetching a region — or fine-tuning its window — costs little or no network
  traffic. Fetches are capped at 60 tiles, and the zoom level is chosen
  automatically to fit that budget at roughly screen resolution.
- **Flat grids only.** A regional map can't wrap a globe; switch the grid's
  Shape to Flat Rectangle first. (A globe still takes any whole-earth
  equirectangular image the ordinary way, via `texture_id`.)
- **Aspect ratio**: the fetched image has square pixels in degree space. For a
  locally true-to-shape map, set the grid's `scale_x ≈ cos(mean latitude) ×
  scale_y`, as usual: a degree of longitude is the shorter one, by that
  factor (about 0.83 at San Diego's 34°).
- Regions crossing the antimeridian (±180°) aren't supported yet.
- The fetch logic lives in `glyphviz_core/basemap.py`, separate from the Qt
  dialog, and is tested offline with a mocked tile server
  (`tests/test_basemap.py`).
