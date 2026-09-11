# AI Observatory

GlyphViz scenes of what happens inside a language model as it reads. Phase 1:
GPT-2 small with Joseph Bloom's residual-stream sparse autoencoders
(`gpt2-small-res-jb`, 24,576 features per layer) and Neuronpedia's feature
explanations. Design and later phases: [DESIGN.md](DESIGN.md).

## Two stages, two environments

| Stage | Script | Env | Does |
|---|---|---|---|
| A | `extract_gpt2.py` | `observatory` (torch + CUDA, TransformerLens, SAELens) | runs the model, builds the feature atlas once, extracts one prompt's activations and attribution edges |
| B | `build_scene.py` | `glyphviz` (numpy + pandas) | writes the scene folder: node CSV, Channels pair, sonified audio |
| check | `verify_scene.py` | `glyphviz` | loads the result through GlyphViz's own loaders and Channels engine |

The GlyphViz app never imports torch.

## Making a scene from your own prompt

One line, from a PowerShell terminal:

```powershell
cd C:\Users\jsale\source\repos\glyphviz
.\ai_observatory\make_scene.ps1 "The Eiffel Tower is in the city of" Eiffel
```

That runs all three stages and writes
`ai_observatory\scenes\AI_Observatory_GPT2_Eiffel\`; drag its `_gv_node.csv`
into GlyphViz. It finds both conda envs' Python on its own and prints GPT-2's
prediction at the end. If Windows refuses to run scripts, use
`powershell -ExecutionPolicy Bypass -File .\ai_observatory\make_scene.ps1 "..." Eiffel`.

The prompt is an argument; the sentence inside `extract_gpt2.py` is only the
fallback when none is given, so there is no need to edit it. Good prompts:

- stop right before the word you want GPT-2 to produce ("…in the city of"),
  with no trailing space (the script trims one);
- keep them to roughly 5-25 tokens: each adds about 1.2 s of animation and
  widens the prompt row;
- a different `Name` per prompt keeps every scene. Reusing a name overwrites
  that scene.

Bundled scenes, all in `scenes/`: `AI_Observatory_GPT2_IOI` (name copying:
"…John gave a drink to" → " Mary"), `AI_Observatory_GPT2_Induction` (pattern
copying: "Mr and Mrs Dursley were proud to say that they were perfectly normal.
Mr and Mrs" → " D" 85% -- GPT-2 spells the name " D" + "urs" + "ley", so its
next token is the name's first piece), `AI_Observatory_GPT2_Eiffel` (fact
recall, and a near miss: "The Eiffel Tower is in the city of" → " London" 8%,
" Paris" 7% -- a 124M-parameter model barely knows this, though its
location features clearly know a city belongs there), and
`AI_Observatory_GPT2_Jordan` (fact recall that works: "Michael Jordan plays
the sport of" → " basketball" 50%). Eiffel and Jordan make a pair: the same
kind of question, answered once by guessing and once by knowing.

### The three stages by hand

The wrapper is just these, with full paths to each env's Python:

```powershell
& C:\Users\jsale\anaconda3\envs\observatory\python.exe ai_observatory\extract_gpt2.py "When Mary and John went to the store, John gave a drink to" --slug ioi
& C:\Users\jsale\anaconda3\envs\glyphviz\python.exe ai_observatory\build_scene.py ioi --name AI_Observatory_GPT2_IOI
& C:\Users\jsale\anaconda3\envs\glyphviz\python.exe ai_observatory\verify_scene.py ai_observatory\scenes\AI_Observatory_GPT2_IOI\AI_Observatory_GPT2_IOI_gv_node.csv
```

`--slug` names the cached run in `cache/runs/`; `--name` names the scene
folder and files.

The first extraction downloads GPT-2 small (~0.5 GB) and the 12 SAEs into the
Hugging Face cache and writes `cache/atlas_gpt2-small-res-jb.npz`; later
prompts reuse both. Neuronpedia's bulk explanation export (~53 MB, 12 JSON
files) lives in `cache/neuronpedia_exports/`. `cache/` and `scenes/` are
gitignored.

## What the scene shows

- **The tower.** A vertical spine is the residual stream. Each of the 12
  layers is a ring; layer 0 at the bottom, the prediction at the top.
- **Every feature, always in the same place.** All 24,576 features of a layer
  are points in that layer's cloud. Position comes from clustering the
  features' decoder directions, ordering the clusters around the ring by
  similarity, and rotating each layer to line up with the one below. So a
  point's place and color mean the same thing in every prompt's scene, and
  roughly the same longitude up the tower.
- **Active features become glyphs.** The strongest features at each token are
  spheres at their home positions; size is activation. Click any point or
  glyph to read its Neuronpedia explanation.
- **Attribution edges.** Cylinder links from a layer's features to the next
  layer's (and from layer 11 to the prediction). Orange pushes the target up,
  blue pushes it down; thickness is the share of the target's attribution.
- **Time is reading.** Press Play: for each token a pulse climbs the tower
  layer by layer, the strongest feature per layer pins its label, and the
  prediction lights up at the top. Stopped, the scene shows the last token.
- **Sound.** Each layer is a note (low layers low), loud when that layer
  is active, brighter with more active features, panned toward where on the
  ring the activity is. A chime marks the prediction, louder the more
  confident it is.

## Honest limits

- GPT-2 small is a base model: there is no refusal or deception to find here.
  It is the model to build the instrument on.
- The SAEs are a lens, not the model itself. Measured on the IOI prompt, they
  reconstruct 99.7% of the residual stream's variance at layer 0, falling
  steadily to 86% at layer 6 and 78% at layers 10-11; what they miss is not
  in the scene. (The model loads with the settings the SAEs were trained
  against: `center_writing_weights=True`, TransformerLens's default.)
- Neuronpedia's explanations are automated and often wrong or vague. They are
  researchers' best guesses, not ground truth.
- Attribution edges are gradient × activation between adjacent layers with
  each SAE's reconstruction error held fixed: a per-prompt linear
  approximation, pruned to the strongest few per target.
- The atlas layout is one reasonable projection of 768 dimensions onto a ring;
  distance on the ring is suggestive, not a metric.
