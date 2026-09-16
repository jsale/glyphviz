# AI Observatory — design note (draft 1, 2026-09-11)

An interactive, multi-sensory view of what happens inside a language model,
built as GlyphViz scenes. Starts with GPT-2 small on one laptop, scales to
supercomputer-sized models without changing the viewer.

## Verdict

Feasible, and mostly with what already ships. The viewer needs nothing new
for Phase 1: hyperglyph hierarchy, Channels animation, audio-synced playback,
link geometries, Point Cloud topology, the 3D graph layout engine, Web and VR
all exist. The new work is a **pipeline** that turns interpretability data
into `gv_` scenes. That pipeline lives in its own environment and the GlyphViz
app never imports torch (same split as `hyperglyph_lab/`).

## Two halves

```
ai_observatory/            (torch, transformer_lens, sae_lens, circuit-tracer)
   model + prompt  ->  activations, features, attribution edges
                   ->  gv_node.csv / gv_tag.csv / gv_ch-map + gv_ch-tracks
                   ->  sonification .wav -> .m4a + *_gv_audio.txt manifest
GlyphViz / GlyphViz Web    renders the folder like any other scene
```

Everything expensive is precomputed. The viewer's budget is per-node render
cost, so the pipeline decides what becomes a glyph and what stays a point.

## Data sources (all open)

| Source | What it gives | Scale |
|---|---|---|
| GPT-2 small (TransformerLens) | 12 layers, d=768, 12 heads/layer, activations for any prompt | 124M params, runs on CPU |
| res-jb residual SAEs (SAELens / Neuronpedia) | 24,576 features per layer, decoder directions | 294,912 features |
| Neuronpedia API | auto-interp explanation per feature, activation density, top tokens | one string per feature -> `text` column |
| GPT-2 small transcoders (Dunefsky et al.) | per-prompt attribution edges feature -> feature | verify in Phase 1 before relying on it |
| Weight-only wiring (fallback) | cos(W_dec[l], W_enc[l+1]) | static, no prompt needed, cheap |
| circuit-tracer (Anthropic, open source) | attribution graphs; official support Gemma-2-2B, Llama-3.2-1B | Phase 2 |
| Gemma Scope | SAEs at every layer of Gemma-2 2B/9B, widths 16k to 1M | Phase 2/3 |
| Pythia checkpoints | 154 snapshots across training | Phase 3: training as time |

## The scene

**Level 0** World row (background, fog, tag style).

**Level 1: the Tower.** The residual stream is a vertical spine
(`TOPO_ROD`/`TOPO_CYLINDER`); each layer is a ring at its own height.
Height = depth in the model.

**Level 2: clusters.** Features on a layer ring are placed by *meaning*, not
by index. Unit-normalize each feature's decoder direction, k-means into
~128 clusters per layer, then order clusters around the ring (1-D spectral
ordering of centroids) so neighbouring clusters mean similar things. Align
angles between adjacent layers by centroid similarity, so a concept keeps
roughly the same longitude as it climbs the tower. This gives every feature a
**home position that is the same in every prompt's scene** — that is what
makes it an observatory rather than a one-off picture.

**Level 3: features.** Children of their cluster. Inactive features are a
Point Cloud (295k points is well inside the 4.1M already loaded). Features
active on the current prompt are promoted to real glyphs (union of the
top-k per token, capped around 5k).

**Tokens.** The prompt is a `TOPO_PLOT` row at the base, one node per token,
labelled with the token text. Channels time = token position; the current
token is highlighted and its text pinned. A viewer reads the sentence left to
right and watches the tower light up.

**Links.** Attribution edges as type-7 links with cylinder geometry:
`ratio` = edge weight, colour = sign. Pruned to a few thousand (6,400 proven
in the GTDB example).

**Encodings.** Activation -> scale + palette colour; how often a feature fires
across a corpus -> base size; label confidence -> alpha/ring; attention heads
(144) as an inner ring per layer, with per-token attention patterns as links
to source tokens (Phase 1b).

**Labels.** Every node gets `text` (feature explanation, cluster's most common
words, token string) so the encoding teaches itself; only the current token
and the top few features are pinned (`show_text`), because the tag pass is
the expensive one.

**Sound.** Layer -> octave, cluster angle -> stereo pan and timbre,
activation -> amplitude, one token per beat (about 2 tokens/s). Rendered with
numpy to WAV, compressed to m4a, attached via `<name>_gv_audio.txt`, so frame
advance follows the audio position (the supported sync path). You hear a
layer come alive before you find it on screen.

## Budgets (numbers measured in this repo)

- Points: 4.1M loaded. All 295k GPT-2 features as points: fine.
- Glyphs: render cost is per node (the splatting measurement). Keep active
  glyphs <= ~5k per scene.
- Links: 6,400 rendered in Org_Event_Network; prune attribution graphs to <= 3k.
- Channels: 50 tokens x 5k nodes x 3 attributes = 750k cells, tens of MB;
  the dense-scene fast path covers it.
- Tags: label everything, pin <= 20.

## Phases

**Phase 1: GPT-2 small on this laptop (RTX 3080 Ti 16 GB, 32 GB RAM).**
One prompt end to end: activations -> scene -> Channels -> audio. Three
demo prompts with known circuits: induction ("Mr and Mrs Dursley ... Mr and
Mrs"), indirect-object identification ("When Mary and John went to the
store, John gave a drink to"), factual recall ("The Eiffel Tower is in").
Deliverable: `examples/AI_Observatory_GPT2/`, a per-example zip, a docs page.

**Phase 2: a GPU box.** Gemma-2-2B-it + Gemma Scope + circuit-tracer. Real
attribution graphs, and an instruction-tuned model where refusal and
sycophancy-like features actually exist. Batch thousands of prompts; build a
corpus-level feature atlas (co-activation graph laid out with
`forceatlas2_3d`); one atlas shared by every prompt's scene.

*Status 2026-09-15, step 2a done:* Gemma-2-2B-it with Gemma Scope residual
SAEs, on the laptop after all (bf16 model, 16 GB GPU is enough). Same tower
as GPT-2 via a model profile (`profiles.py`), plus two things GPT-2 didn't
need: a per-token **lens check** on the rings, because base-model SAEs go
blind on instruction-tuned chat-template tokens, and **contrast pinning**
against a control prompt, because raw activation and even
gradient-to-logit pinning both surfaced only generic template features on
a refusal. Scenes: Refusal (gallery), Reminder (its twin), IOI.
*Next, step 2b:* circuit-tracer attribution graphs. Needs its own env
(`transformers<=4.57.3`, `huggingface_hub<1.0`, which conflicts with this
one). Its transcoders are a different dictionary from the residual SAEs, have
no Neuronpedia bulk labels (per-feature API only), and attribute one target
at a time, so a per-token animation is one graph per token.

**Phase 3: a supercomputer.** Pythia checkpoints with an SAE trained per
checkpoint: watch a concept be born over training. Two towers side by side
to compare models. 9B/27B models with million-width SAEs. The heavy job is
SAE training itself (GPU-days per model), which is exactly what an
allocation buys.

**Phase 4: a public instrument.** GlyphViz Web + VR bundle; a glyphviz-skill
extension so "show me how the model reads this sentence" produces a scene;
share with Neuronpedia, ARENA and MATS.

## Honest limits

1. GPT-2 small is a base model: no deception, no refusal. It is the right
   model to build the pipeline on and the wrong one for the safety story;
   that story starts at Gemma-2-2B-it in Phase 2.
2. Auto-interp labels are often wrong. The scene shows the researchers'
   claims and must encode confidence; it does not verify them.
3. Attribution graphs are per-prompt, pruned, and linear approximations.
   Say so in the scene.
4. A 300k-feature scene can be as opaque as a 300k-row list. The test for
   every design choice: can a non-expert answer one question from it ("why
   did it say Paris?").
5. Render cost is per node; level of detail is a requirement, not a polish.

## Environment

A separate conda env `observatory` (torch + CUDA, transformer_lens,
sae_lens, circuit-tracer, ffmpeg for m4a). Nothing added to the `glyphviz`
env, so the packaged app is unaffected. Downloads for Phase 1: GPT-2 small
(~0.5 GB) + 12 res-jb SAEs (~1.8 GB). Gemma requires a Hugging Face token.
