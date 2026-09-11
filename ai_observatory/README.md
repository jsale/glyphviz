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

The GlyphViz app never imports torch. `$env:OBSERVATORY_PYTHON` and
`$env:GLYPHVIZ_PYTHON` are set in `.claude/settings.local.json`.

```powershell
# one prompt, end to end
& $env:OBSERVATORY_PYTHON ai_observatory\extract_gpt2.py "When Mary and John went to the store, John gave a drink to" --slug ioi
& $env:GLYPHVIZ_PYTHON   ai_observatory\build_scene.py ioi --name AI_Observatory_GPT2_IOI
& $env:GLYPHVIZ_PYTHON   ai_observatory\verify_scene.py ai_observatory\scenes\AI_Observatory_GPT2_IOI\AI_Observatory_GPT2_IOI_gv_node.csv
```

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
