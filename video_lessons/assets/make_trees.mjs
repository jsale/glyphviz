// Writes Glyph Composer template .json files for the lesson videos by running
// the Tree Designer's OWN buildRecipe() (hyperglyph_lab/hyperglyph_tree_designer.html)
// under Node with a stub `document`, so the templates are exactly what the
// page's "Download .json" button would give. Seeds are fixed, so the output is
// reproducible.
//
//   node video_lessons/assets/make_trees.mjs
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(
  path.join(here, "..", "..", "hyperglyph_lab", "hyperglyph_tree_designer.html"), "utf8");
const lines = html.split("\n");

// xmur3 .. end of buildRecipe is pure (no DOM beyond two input values).
const start = lines.findIndex(l => l.startsWith("function xmur3"));
const end = lines.findIndex(l => l.startsWith("function buildRecipe"));
let stop = end;
while (!lines[stop].startsWith("}")) stop++;      // closing brace of buildRecipe
const preset0 = lines.findIndex(l => l.startsWith("const DEFAULTS"));
const body = lines.slice(start, stop + 1).join("\n");
const consts = lines.slice(lines.findIndex(l => l.startsWith("const GEO_NAMES")),
                           start).join("\n");

const fields = { seed: { value: "" }, tplName: { value: "" } };
const ctx = { document: { getElementById: id => fields[id] }, Math, JSON, Object, Set };
vm.createContext(ctx);
vm.runInContext("'use strict';\n" + consts + "\n" + body +
  "\nthis.api = {PRESETS, DEFAULTS, buildRecipe, setP: p => { P = p; }};", ctx);
const { PRESETS, DEFAULTS, buildRecipe, setP } = ctx.api;

// preset, seed, overrides, file stem. One level shallower than the presets
// (the node count is the product of the branch counts, so a stamped forest
// stays a few hundred nodes per tree), 0.6 size so a forest of them fits a
// small meadow, and blossoms fully opaque.
const WANT = [
  // File names are what the designer's Download button would write.
  ["Mighty Oak", "oak-lesson", { levels: 4, treeSize: 0.6 }, "Mighty_Oak"],
  ["Cherry Blossom", "cherry-lesson", { levels: 4, blossomAlpha: 255, treeSize: 0.6 }, "Cherry_Blossom"],
];
const outDir = path.join(here, "trees");
fs.mkdirSync(outDir, { recursive: true });
for (const [name, seed, over, stem] of WANT) {
  setP(Object.assign({}, DEFAULTS, PRESETS[name], over));
  fields.seed.value = seed;
  fields.tplName.value = name;
  const recipe = buildRecipe();
  fs.writeFileSync(path.join(outDir, stem + ".json"), JSON.stringify(recipe, null, 2));
  const counts = recipe.levels.map(l => l.count);
  console.log(stem, "levels", recipe.levels.length, "counts", counts.join("x"));
}
