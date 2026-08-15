# Hyperglyph Generator

**Tools → Hyperglyph Generator…** (**Ctrl+H**)

The Hyperglyph Generator invents multi-level glyph designs procedurally. Press
**Regenerate** and you get a whole branching creature — geometry family, color
scheme, branch counts, topologies and proportions all chosen for you — which you
can then drop into the scene or save as a template to edit by hand.

It is the counterpart to the [Glyph Composer](glyph-composer.md): the Composer
is where you *describe* a glyph, this is where you *discover* one.

## What a hyperglyph is

A hyperglyph is a deliberately designed hierarchy of nodes read as a single
visual object rather than as a data plot. It uses exactly the machinery
everything else in GlyphViz uses — each level's [topology](topologies.md)
arranges the next level's children, each level picks a
[geometry](geometries.md) — so a hyperglyph is ordinary scene content, not a
special node type. Nothing downstream treats it differently.

The generator builds on the same `GlyphRecipe` / level model the
[Glyph Composer](glyph-composer.md) edits, which is why every design it produces
can be saved as a Composer template.

## The dialog

The GUI dialog is deliberately **one glyph at a time**. For generating many
designs at once with ratings and mutation, use the
[batch tools](#batch-generation-hyperglyph_lab) below.

### Parameters

| Field | What it does |
| --- | --- |
| **Max Nodes** | An upper bound on the total node count — a **cap, not a target**. Branch counts are chosen to fit under it. |
| **Branch Levels** | How many levels deep, *including* the trunk. 5 means a trunk plus four branching levels. |
| **Randomize** | Checked: every **Regenerate** draws a fresh random seed and shows it in the Seed field. Unchecked: Regenerate reuses the Seed field exactly. |
| **Seed** | Only live when Randomize is off. Seed + Max Nodes + Branch Levels together determine the design completely — the same three values always regenerate the identical glyph. |
| **Idle Motion (rotate_rate)** | A slow counter-rotating spin per branch level, so a fresh hyperglyph reads as alive before any data drives it. |

!!! tip "The one workflow worth knowing"
    Leave Randomize **on** and press Regenerate until something catches your
    eye, then immediately turn Randomize **off**. That locks in the seed of the
    design on screen, and you can now tweak Max Nodes and Branch Levels around
    it without losing it.

Regeneration happens **only** on an explicit Regenerate click — never on opening
the dialog, never on changing a field. Nothing rerolls out from under you.

The readout under the button reports the node count, the geometry family, the
palette scheme, and the seed.

### Idle Motion

Idle Motion sets `rotate_rate_*` on non-root nodes, alternating direction by
depth — each ring of children counter-rotates against its parent ring, like an
orrery. Only rotation is animated: `translate_rate` and `scale_rate` integrate
forever with no wraparound, so they would drift or grow rather than loop.

The static design underneath is already complete without it. To freeze a live
hyperglyph before saving, use **View → Pause Rate Animation** (**P**) in the main
window, which zeroes the rate fields for real rather than just visually.

### Getting the design out

| Button | Result |
| --- | --- |
| **Insert into Scene** | Adds the nodes to the live scene — as a child of the selected node, or at the scene root if nothing is selected. What you previewed is exactly what gets inserted. |
| **Save Recipe…** | Writes the design as a Glyph Template `.json`, the format [Glyph Composer](glyph-composer.md) → Load Template opens. |

Node CSVs still come from **File → Save / Save As** on the main window once a
design is inserted, the same as any other content.

### Capture live orientation

This checkbox changes what **Save Recipe** writes: the pose the preview has
*spun into*, rather than the orientation the design was generated with.

It matters because a recipe holds **one rotation per level**, while Idle Motion
gives every node its own axis and speed — so siblings drift apart and no single
value can describe them all. The capture is therefore:

- **Exact for the trunk**, which is always a single node.
- **Representative for deeper levels**, taking the first node at each level.
  First-node is chosen over an average because it is an orientation that
  genuinely occurred on screen, and it stays stable as the siblings spread out.

With Idle Motion off nothing has moved, so the checkbox has no effect.

!!! note "A recipe is always static"
    Recipes carry no rate fields at all. What Capture live orientation preserves
    is the **pose** the preview had reached, not the motion.

### Large designs

Above roughly 2,000 nodes the dialog says so in the readout, and again when you
save. The recipe file stays tiny and the glyph renders fine in a scene — what
gets heavy is *editing* it in the Composer, which rebuilds the whole tree after
every keystroke. Regenerate is cheap; it's worth knowing before you commit.

## How designs are chosen

The randomness is tuned, not uniform. Three choices do most of the work:

**Geometry family.** One family is picked per design, rather than mixing all
shapes freely — this is what keeps a five-level, thousand-node glyph reading as
one coherent creature instead of visual noise.

| Family | Shapes |
| --- | --- |
| `platonic` | Tetra, Octa, Dodeca, Icosa, Cube (solid + wire) |
| `round` | Sphere, Torus, Cylinder, Cone (solid + wire) |
| `wire_only` | The wireframe of everything |
| `spiky` | Cone, Pin, Tetra, Star |
| `particles` | Point, Circle, Cross, Star |
| `mixed` | A curated cross-section |

**Palette scheme.** Hues are related by color theory rather than rolled per
level: `monochrome`, `analogous`, `complementary`, `triadic`,
`split_complementary`, or `rainbow`. Each level also gets its
`color_index` wired to its depth, so the design is ready for the
[Color Palettes](properties-panel.md) feature the moment it is generated.

**Topology pool.** Only topologies whose angular coordinate suits branching are
drawn from: Sphere, Torus, Cylinder, Pin, Rod, Point, Spiral. Cube, Plane and
None read `translate_x` as something else entirely; the Z-variants place
children through the center rather than on the surface, which reads as a clump
rather than a structure.

Levels are generated with **Topo Scale on Auto** (see
[Glyph Composer](glyph-composer.md#topo-scale-and-auto)), which is what keeps a
Pin level's children inside the parent's extent instead of smeared along 360
units.

## Batch generation (`hyperglyph_lab/`)

For exploring many designs at once, the repository ships a standalone lab with a
CLI and a notebook. This is the tool the dialog is a single-glyph wrapper around.

```bash
python generate_hyperglyphs.py --levels 5 --max-nodes 2000 --count 10
python generate_hyperglyphs.py --levels 4 --max-nodes 500 --count 20 --name storm
```

| Option | Meaning |
| --- | --- |
| `--levels` | Branch levels including the trunk (required) |
| `--max-nodes` | Per-design node cap (required) |
| `--count` | How many designs this batch (default 10) |
| `--name` | Filename prefix |
| `--output-dir` | Where to write (default `hyperglyph_lab/output/`) |
| `--ratings-csv` | The design manifest (default `hyperglyph_lab/ratings.csv`) |
| `--explore-ratio` | Fraction of the batch that is fresh randomness vs. mutation of a past favorite |
| `--seed` | Master seed, for a reproducible batch |
| `--no-idle-motion` | Turn off the idle spin |

Each design writes three files — a `gv_node.csv` / `gv_tag.csv` pair you can
open directly, and a `_recipe.json` you can open in the Composer — plus one row
appended to the ratings manifest.

### The rating loop

`ratings.csv` is a plain manifest of every design ever generated, with blank
`rating`, `categories` and `notes` columns for you to fill in. It is meant to be
edited by hand in a spreadsheet (or from the notebook) between runs.

Once at least three designs are rated 7 or better, later batches stop being pure
noise: part of each batch is spent **mutating** a top-rated recipe instead —
small jitter on the numeric fields, occasional re-rolls of geometry within the
same family and of topology within the safe pool, re-clamped back inside the
node budget.

That is the whole "learning" mechanism. It is a feedback loop with you in it,
not a model.

## Next step

Return to the [Reference overview](index.md), or open a saved recipe in the
[Glyph Composer](glyph-composer.md) to edit it level by level. For designing
branching, tree-like glyphs deliberately rather than at random, see the
[Hyperglyph Tree Designer](tree-designer.md).
