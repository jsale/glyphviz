# Golden-Master Validation

GlyphViz's core claim — that it renders ANTz/GaiaViz-lineage scenes correctly, not just plausibly — has to be checked by something more rigorous than "it looks right." The golden-master harness in `tests/golden/` is that check: it isolates the one function that decides where every glyph ends up, `node_world_matrix()` in `glyphviz_core/scene.py`, and holds it to a stored reference answer for a battery of hand-built scenes.

!!! note "Today this is a regression baseline, not an ANTz cross-check"
    The stored answers were computed by GlyphViz's own Python, not extracted
    from the ANTz C renderer. The harness therefore catches any change that
    moves a glyph, but it does not yet prove the math matches ANTz. That
    needs Phase A, which runs the same scenes through an instrumented ANTz
    build, and that hasn't been done yet. [Details below](#what-golden-master-means-here-today).

## How it works

Each scene lives as a small, deliberately-targeted CSV in `tests/golden/scenes/` — a deep parent→child chain, sibling branching, a rotation cascade, one scene per topology under test (Cartesian, Sphere, Rod, …). For every node in every scene, `generate_expected.py` computes the 4×4 world transform with `node_world_matrix()` and writes it to a matching JSON file in `tests/golden/expected/`. `pytest` (`tests/golden/test_matrices.py`) then reloads each scene fresh and asserts the freshly-computed matrix for every node matches the stored one to float32-appropriate tolerance (`atol=1e-5`) — plus two structural sanity checks that hold regardless of any oracle: the bottom row of every world matrix is `[0, 0, 0, 1]` (it's a valid affine transform), and the de-scaled rotation block is orthonormal wherever a node's parent has uniform scale (a non-uniform parent scale is expected to introduce real shear, matching ANTz's own behavior, so those nodes are skipped rather than flagged).

## What "golden master" means here today

Be precise about what's actually being checked right now, because the honest answer is more useful than the inspiring one: the stored expected matrices are currently a **Python-computed baseline** — `node_world_matrix()`'s own output, captured and pinned — not matrices extracted from a running instance of the original ANTz C renderer. That makes today's harness a **regression guard**: it catches any future change that silently shifts where a node lands, because the math was worked out and hand-verified against ANTz/GaiaViz's documented topology and scene-graph conventions (see [ANTz & GaiaViz Format Notes](antz-gaiaviz-format-notes.md)) once, and it can't drift after that without a test failing.

What it does **not** yet do is independently prove that hand-verified math actually matches ANTz's real behavior on a scene nobody thought to check by hand — that requires a second, independent implementation to compare against, and that's specifically what the "oracle" phase (labeled **Phase A** in the harness's own code comments) is for: instrumenting a real ANTz build to dump its `GL_MODELVIEW_MATRIX` per node for the same scene CSVs, then swapping those matrices in as the new `expected/*.json` through an `--oracle <dir>` option on `generate_expected.py` (planned, not yet written). The harness's plumbing — one scene in, one matrix out, per node, compared with a tolerance — was built so that swap needs only a small loader, not a rewrite, whenever a working ANTz build to instrument is available. Until then, "golden master" describes the harness's design and intent more than its current evidentiary weight, and that's worth saying plainly rather than letting the name imply more than the current baseline delivers.

## Why bother

Rendering-math bugs in a hierarchical scene graph are exactly the kind that hide in plain sight: a node three levels deep with a rotated, non-uniformly-scaled parent can be subtly wrong in a way that's nearly impossible to eyeball but immediately obvious to a matrix comparison. GlyphViz's history has real examples of exactly that class of bug — multi-level non-uniform-scale distortion, topology-specific child orientation on circular paths, Z-topology clustering — the kind that a fresh `pytest` run catches deterministically the moment `node_world_matrix()` changes, rather than relying on someone noticing a glyph looks subtly off in a hundred-node scene. That's the actual argument for the harness, independent of whether its current baseline is Python-derived or ANTz-derived: it turns "does this still render correctly" from a manual visual check into a fast, automated, sub-second `pytest` run, for exactly the class of change most likely to break silently.
