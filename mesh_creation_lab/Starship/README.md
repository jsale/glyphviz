# Mesh Starship

A greebled capital ship, two escorts and a fighter screen.

Open `mesh_starship_gv_node.csv`.

## What it demonstrates

**Greebling: detail generated, not modelled.** The dagger hull is a handful of
lofted sections — 1,364 triangles. Everything that makes it read as a
kilometres-long warship is scattered afterwards by code: 1,600 boxes and
blisters planted on the real hull surface, oriented to its local outward
normal, sized by a **power law** so a few large structures anchor the
silhouette and hundreds of small ones fill in.

That distribution is the whole trick. A uniform size range reads as gravel and
conveys no scale at all. Size range also matters more than count: the first
pass allowed greebles up to 5.5% of ship length and they ate the dagger
silhouette entirely — the ship read as a pile of crates.

**A dense mesh, as a capacity check.** The greeble layer is ~19,000 triangles
and compiles into one display list, drawing as one node. Push it with
`--greebles 5000` if you want to find your machine's limit.

**Emissive-looking parts with no emissive support.** GlyphViz lights with one
eye-space headlight and has no emission channel. The engine discs and the
window strips along the flanks are simply a separate mesh drawn in bright
saturated colour. They read as lit because everything around them is not.

**A built-in glyph doing what a mesh should not.** The starfield is a
`GEO_SPHERE_INTERIOR` (geometry 30) at scale 9000 — the inside of a sphere,
mapped to read the right way round from within and drawn unlit, which is
exactly what a backdrop wants. No fog: it would fade the stars into the
background, and there is nothing in vacuum to scatter light anyway.

## Rebuilding it

```
<glyphviz-env>\python.exe mesh_creation_lab/Starship/build_starship.py
<glyphviz-env>\python.exe mesh_creation_lab/Starship/build_starship.py --greebles 400
```
