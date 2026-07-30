# Drag and Drop

Dragging files onto the GlyphViz window loads them. It's the fastest route from
a downloaded example to a rendered scene: you can drop the example zip itself,
without extracting it first.

Everything a scene needs is discovered from the node CSV's own path — the
companion tag file, the `ch-map`/`ch-tracks` Channels pair, the audio manifest,
and the `media/` texture folder beside it. So dropping a folder or a zip is
really just "find the node CSV in here"; the rest follows automatically, exactly
as it would through **File → Open**.

The routing lives in `glyphviz_core/drop_router.py`, deliberately separate from
the Qt event handlers in `main_window.py` so it can be tested on its own
(`tests/test_drop_router.py`).

## What you can drop

| Dropped item | What happens |
|---|---|
| **Node CSV** | Opens it as the current scene, same as File → Open |
| **Folder** | Finds the node CSV inside and opens it, with its tag/Channels/media companions |
| **Zip** | Extracts it, then treats the result as a folder |
| **Tag or channel CSV** | Redirects to the node CSV it belongs with — grabbing the wrong file of a pair still works |
| **`.pdb`** | Imports the protein structure (File → Import PDB File) |
| **`.obj` `.stl` `.ply` `.glb` `.gltf`** | Imports as a mesh, onto the selected node or a new one |
| **Image / video file, or a folder of them** | Loads that folder as the texture set |

Anything else is reported in the status bar and ignored.

## Replace or merge

A plain drop **replaces** the scene, matching File → Open.

Hold **Shift** while dropping to **merge** instead — the same operation as
File → Merge Node CSV… (Ctrl+M). The incoming nodes get fresh ids above the
existing ones and keep their own coordinates, so the two scenes overlay in one
world space. As with Ctrl+M, the incoming file's Channels animation is not
merged.

## Dropping several things at once

Multiple items in one drop are applied in a sensible order rather than fighting
each other:

- **Several node CSVs** — the first opens, the rest merge, as if you'd followed
  one Open with several Ctrl+M's.
- **Meshes and textures** are additive, and are applied *after* the scene loads,
  since a mesh attaches to the current selection.
- **A PDB dropped alongside a node CSV** is skipped, with a note. Both are
  whole-scene replacements, and the CSV wins.

Whatever the drop decided is appended to the status bar after the load message,
so "why did it open *that* file?" is always answerable.

## Where a dropped zip extracts

Beside the zip, in a new folder named after it — so a later **Save** lands
somewhere durable, next to the data it came from. An existing folder of that
name is never overwritten; a numeric suffix is added instead.

If that location isn't writable (a read-only share, for instance), GlyphViz
falls back to a temporary folder and says so in the status bar, along with a
reminder to use **Save As** — edits saved into a temp folder are easily lost.

Archives zipped from the parent directory, so that everything sits one level
down inside a single wrapper folder, are handled: GlyphViz steps through the
wrapper to find the scene.

!!! note "Untrusted archives"
    Zip entries whose paths would escape the destination folder — absolute
    paths, or ones containing `..` — are refused outright, as are archives with
    implausible entry counts or uncompressed sizes. A dropped zip may have come
    from anywhere, so it isn't trusted to name its own extraction targets.
