# Save Selection

**File → Save Selection As…  (Ctrl+Alt+S)** writes the nodes you have selected
to a node CSV of their own, leaving the open scene untouched. Use it to pull a
single hyperglyph out of a crowded scene, to split one dataset into per-region
files, or to lift a shape you like into a reusable building block.

The menu item is greyed out until something is selected.

## Why this is not just "save the highlighted rows"

A selection is rarely a self-contained scene, and the interesting part of the
feature is what happens to the nodes whose **parents stay behind**.

In a node CSV, a child's `translate_x/y/z` is not a position — it is a
coordinate *in its parent's topology*. A child of a Sphere parent at
`(30, 45, 5)` means "longitude 30°, latitude 45°, 5 units above the surface."
A root's translate, on the other hand, is a literal world position. So a node
lifted out of its hierarchy and saved as-is reloads somewhere else entirely —
and a World Grid child, whose translate is longitude and latitude, lands off
the map completely.

GlyphViz handles that for you. The dialog's middle group is the choice:

| Option | What it does |
|---|---|
| **Keep it where it is** *(default)* | Folds the missing parents' placement into the node itself, so the saved fragment reopens exactly where it appeared, at the same size and angle. Its own children ride along untouched. |
| **Save its parent nodes too** | Writes the ancestor chain as well, so the hierarchy stays intact. Perfectly faithful, but the file then contains glyphs you did not select. |
| **Keep its authored values** | Leaves `translate/rotate/scale` exactly as written. The fragment lands near the origin in its old parent's local coordinates — what you want when reusing a glyph as a **template**, not when saving a region of a scene. |

The default is exact, not approximate: reopen the file and every exported node
sits on the same pixel it did in the source scene.

## What travels with the selection

Everything below happens automatically — you only choose the three options in
the dialog.

- **Descendants.** A selected node brings its whole subtree, the way Copy and
  Delete already do. Uncheck *Include each selected node's descendants* to
  write only the highlighted rows.
- **Links.** A link (type 7) whose nodes at *both* ends are in the export is
  written too, even if you never selected the link itself. A link with only
  one end present is dropped rather than left pointing at nothing.
- **Scene settings.** The World row — background color, fog, render mode, tag
  and reference-grid colors — is written at the head of the file, so the
  fragment reopens with the same look.
- **Tags.** The companion tag CSV is written whenever the exported nodes carry
  any labels, under the matching name (`fragment_gv_node.csv` →
  `fragment_gv_tag.csv`).
- **Channel animation.** If the open scene has a Channels pair loaded, the
  export writes `…_ch-map.csv` / `…_ch-tracks.csv` companions holding only the
  channels the exported nodes are bound to. Uncheck the box to skip them.
- **Node ids** keep their original values, so an exported fragment stays easy
  to line up against the scene it came from.

Branch levels are restated to match the new hierarchy, so a node that was
three levels deep becomes a proper root at level 0.

## What the status bar tells you afterwards

The message after a save names anything the export had to decide for you:

- **`N re-rooted`** — nodes whose parent stayed behind, handled per the option
  you chose above.
- **`N link(s) dropped`** — the node at the other end wasn't in the selection.
- **`N approximated`** — a rare case: a node with a *stretched* (non-uniformly
  scaled) parent that is also rotated has a shape no combination of
  `rotate` + `scale` can reproduce on its own. The export writes the closest
  match and tells you which nodes are affected. Choose *Save its parent nodes
  too* if you need those exact.
- **`N with motion rates now moving in world space`** — `translate_rate` on a
  Sphere child orbits it in longitude; the same numbers on a root drift it
  through world XYZ. The values are preserved, but their frame of reference
  changed.

## Things worth knowing

- **Textures don't follow the file.** `texture_id` is an index into the
  `media/` folder sitting beside the CSV, so a fragment saved elsewhere loses
  its textures. Save into a folder that has the same `media/` folder, or copy
  `media/` across whole — copying part of it renumbers everything.
- **Give the fragment its own folder** if it has Channels companions. GlyphViz
  only auto-loads a channel pair when the folder contains exactly one
  `ch-map` file, so exporting next to another animated scene leaves neither
  loadable.
- **Keep the name ending in `node`.** The suggested filename already does. The
  tag companion's name is derived by swapping that `node` for `tag`, so a name
  ending otherwise means no tag file is written (the status bar says so).
- **Global Scale.** The baked placement is exact at the Global Scale in force
  when you save. Reopening the fragment at a different Global Scale keeps it
  where it was rather than where its old parent would now put it.

## Round-tripping it back

A saved selection is an ordinary node CSV: open it (Ctrl+O), drop it on the
window, or merge it back into another scene with **File → Merge Node CSV…**
(Ctrl+M), which rebases its ids onto the host scene. Save Selection plus Merge
is how you move a piece of one scene into another.

## Next step

- [Menus](menus.md) — the rest of the File menu
- [Drag and Drop](drag-and-drop.md) — the other way to load what you saved
- [Channels Animation](channels-animation.md) — what the `ch-map`/`ch-tracks`
  companions hold
