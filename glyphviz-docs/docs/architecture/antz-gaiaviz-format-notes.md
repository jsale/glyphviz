# ANTz & GaiaViz Format Notes

GaiaViz and ANTz share the same underlying lineage, and most of their conventions — column structure, hierarchy model, topology behavior — are identical or near-identical. GaiaViz, as the newer commercial successor, has since added its own extensions: updated infrastructure rows and column/header naming in places, plus entirely new capabilities like video textures and copy/paste that don't exist in ANTz at all (some of which GlyphViz also implements, on its own terms).

This page documents the specific, verified places GaiaViz's conventions have moved on from ANTz-native format, so that work explicitly targeting ANTz-native CSV compatibility (per GlyphViz's golden-master invariant — see [Golden-Master Validation](golden-master-validation.md)) uses the right convention for that context, while GaiaViz-derived features stay clearly attributed as such. GlyphViz has no access to GaiaViz's actual source, so nothing here is assumed beyond what GaiaViz's own reference documentation (bundled in `gaiaviz-skill/references/`) describes.

!!! info "Where this applies — and where it doesn't"
    None of this is GlyphViz's own data contract. GlyphViz's native `gv_` format only requires about 20 columns, has no mandatory infrastructure rows, and is documented independently in `glyphviz-skill/references/`. The divergences below matter only when *reading* genuine third-party ANTz or GaiaViz files, or when grounding a topology/behavior decision in one lineage's documented conventions versus the other's — see the project's own "ANTz vs GaiaViz" framing for how that split is made feature by feature.

## Column naming: `facet` vs. `subspace`

The Cube topology's face selector is spelled differently across the two formats. ANTz calls it `facet` and 1-indexes it (1=+X, 2=-X, 3=+Y, 4=-Y, 5=+Z, 6=-Z — confirmed against a real ANTz session). GaiaViz's `np_` dialect calls the same concept `subspace`, 0-indexed. GlyphViz's loader checks for `subspace` first and falls back to `facet - 1` when absent; its saver always writes the canonical ANTz column name, `facet`.

## The `np_` column-name aliases

A handful of GaiaViz-specific column names are recognized on read as aliases for GlyphViz's own field names, purely for interoperability: `np_node_id`, `np_geometry_id`, `np_topo_id`, `np_texture_id`, and `np_ch_in_id`. These exist because genuine GaiaViz export files use them; GlyphViz never *writes* them, and never will — they're a read-side accommodation, not a naming GlyphViz adopts for its own data.

## The `np_` ("neural physics") prefix itself

GaiaViz's `np_` file and column prefix stands for "neural physics," Shane Saxon's architectural concept underpinning ANTz/GaiaViz. GlyphViz has no equivalent architecture and doesn't claim the name — GlyphViz's own data uses a `gv_` prefix (`gv_node.csv`, `gv_tag.csv`, `gv_ch-map.csv`, `gv_ch-tracks.csv`) instead. The `np_` prefix is still recognized when *reading* genuine third-party GaiaViz files, both as a filename pattern and via the column aliases above.

## World Grid parenting convention

GaiaViz's documented convention has scene objects attach implicitly to a main grid via `parent_id = 0` — the same value that means "no parent, this is a root node" everywhere else. GlyphViz deliberately does not use that convention: a World Grid (type=6) is a real, ordinary node, and children attach to it the same explicit way any child attaches to any parent, via `parent_id = grid.id`. There is no default/implicit grid in a GlyphViz scene. (An earlier internal attempt at implicit root-glyph attachment was built and then reverted specifically because of the ambiguity this would have introduced.)

## Rotation convention

Both ANTz and GaiaViz share the same rotation semantics — the *only* one either format has ever used — a Z-X-Z "proper Euler" sequence borrowed from KML's Heading/Tilt/Roll camera-and-model convention (`rotate_y` = heading about z, `rotate_x` = tilt about x, `rotate_z` = roll about z again). GlyphViz implements that convention faithfully (`ROTATION_MODE_HEADING_TILT_ROLL`) and loads every legacy ANTz/GaiaViz file that way by default, so existing files render unchanged. GlyphViz also adds a second, GaiaViz-and-ANTz-absent mode — plain per-axis Euler XYZ — as the default for newly-created nodes in GlyphViz itself, because it's more intuitive for hand-posing a glyph than Heading/Tilt/Roll. This is a GlyphViz-only extension, not a claim about either upstream format. See the [Rotation Convention example](../examples/rotation-convention.md) for a verified side-by-side comparison of the two.

## GaiaViz-only capabilities

Video textures and copy/paste are GaiaViz extensions with no ANTz equivalent at all — GaiaViz's own evolution past the ANTz baseline, not a GlyphViz addition. GlyphViz implements both (video-as-texture via Qt Multimedia; Copy/Paste with full-subtree duplication), on GlyphViz's own terms rather than by reverse-engineering GaiaViz's implementation, since that source isn't available.

## Tags: two different dialects

The full tag row format and its three `title` encodings are documented in `glyphviz-skill/references/tags-and-labels.md` for GlyphViz's own native tag files. `gaiaviz-skill/references/format/Tag-Format.md` covers only the legacy `np_` companion-file dialect used by genuine GaiaViz exports — consult it when reading third-party GaiaViz tag files, not when generating GlyphViz-native ones.
