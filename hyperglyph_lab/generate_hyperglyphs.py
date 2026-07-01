#!/usr/bin/env python3
"""
generate_hyperglyphs.py
========================
CLI for hyperglyph_generator.py — generates a batch of unique, randomized
GlyphViz hyperglyphs (multi-level branching node hierarchies) for music-
synesthesia design exploration.

Usage
-----
  python generate_hyperglyphs.py --levels 5 --max-nodes 2000 --count 10
  python generate_hyperglyphs.py --levels 4 --max-nodes 500 --count 20 --name storm

Each design writes:
  hyperglyph_lab/output/<design_id>_gv_node.csv    (open directly in GlyphViz)
  hyperglyph_lab/output/<design_id>_gv_tag.csv      (paired tag file, usually empty)
  hyperglyph_lab/output/<design_id>_recipe.json     (open in Tools > Glyph Composer)
and one row is appended to hyperglyph_lab/ratings.csv with the design's
parameters and blank rating/categories/notes columns.

The workflow: run a batch, load a few of the node CSVs in GlyphViz, then
fill in the `rating` (e.g. 1-10) and `categories` (free text: "blobby",
"sharp", "menacing", ...) columns in ratings.csv for the ones worth keeping.
The next batch you generate will automatically spend part of its budget
mutating your highest-rated past designs instead of generating pure noise
— see RatingsStore.top_designs()/mutate_recipe() in hyperglyph_generator.py.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from hyperglyph_generator import generate_batch

LAB_DIR = Path(__file__).resolve().parent


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--levels", type=int, required=True,
                    help="Number of branch levels including the trunk (e.g. 5 = trunk + 4 branching levels).")
    p.add_argument("--max-nodes", type=int, required=True,
                    help="Upper bound on total node count per hyperglyph (a cap, not a target).")
    p.add_argument("--count", type=int, default=10,
                    help="Number of unique hyperglyphs to generate this batch (default 10).")
    p.add_argument("--name", default="hyperglyph", help="Filename prefix (default 'hyperglyph').")
    p.add_argument("--output-dir", default=str(LAB_DIR / "output"),
                    help="Where to write CSV/JSON output (default hyperglyph_lab/output/).")
    p.add_argument("--ratings-csv", default=str(LAB_DIR / "ratings.csv"),
                    help="Path to the design manifest/ratings CSV (default hyperglyph_lab/ratings.csv).")
    p.add_argument("--explore-ratio", type=float, default=None,
                    help="Fraction of the batch that is fresh random exploration vs. mutated from a "
                         "top-rated (>=7) past design. Default: auto (100%% until >=3 designs are rated >=7, then 40%%).")
    p.add_argument("--seed", type=int, default=None, help="Master RNG seed, for a reproducible batch.")
    p.add_argument("--no-idle-motion", action="store_true",
                    help="Disable the default slow counter-rotating idle spin on non-root levels.")
    args = p.parse_args()

    rows = generate_batch(
        branch_levels=args.levels,
        max_nodes=args.max_nodes,
        count=args.count,
        output_dir=args.output_dir,
        name_prefix=args.name,
        explore_ratio=args.explore_ratio,
        seed=args.seed,
        idle_motion=not args.no_idle_motion,
        ratings_path=args.ratings_csv,
    )

    print(f"Generated {len(rows)} hyperglyph(s) in {args.output_dir}")
    for row in rows:
        print(f"  {row['design_id']}  nodes={row['actual_node_count']:>5}  "
              f"mode={row['generation_mode']:<8} family={row['geometry_family']:<10} "
              f"palette={row['palette_scheme']}")
    print(f"\nRatings manifest: {args.ratings_csv}")
    print("Open a few node CSVs in GlyphViz, then fill in `rating`/`categories`/`notes` "
          "for the ones worth keeping before generating the next batch.")


if __name__ == "__main__":
    main()
