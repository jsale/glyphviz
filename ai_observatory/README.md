# AI Observatory

GlyphViz scenes of what happens inside a language model as it reads, with
Neuronpedia's feature explanations. Two models so far, each a profile in
[`profiles.py`](profiles.py):

| `--model` | Model | Sparse autoencoders | Features |
|---|---|---|---|
| `gpt2-small` (default) | GPT-2 small, 12 layers | Joseph Bloom's `gpt2-small-res-jb`, residual stream entering each block | 24,576 per layer |
| `gemma-2-2b-it` | Gemma-2-2B-it, 26 layers, instruction-tuned | Gemma Scope `gemma-scope-2b-pt-res-canonical` (16k), residual stream leaving each block, trained on *base* Gemma-2-2B | 16,384 per layer |

Design and later phases: [DESIGN.md](DESIGN.md).

## Two stages, two environments

| Stage | Script | Env | Does |
|---|---|---|---|
| A | `extract.py` | `observatory` (torch + CUDA, TransformerLens, SAELens) | runs the model, builds the feature atlas once per profile, extracts one prompt's activations, attribution edges, lens fidelity and (optionally) a contrast |
| B | `build_scene.py` | `glyphviz` (numpy + pandas) | writes the scene folder: node CSV, Channels pair, sonified audio |
| check | `verify_scene.py` | `glyphviz` | loads the result through GlyphViz's own loaders and Channels engine |

The GlyphViz app never imports torch. `profiles.py` is shared by both stages
and imports nothing heavy.

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

The prompt is an argument; the sentence inside `extract.py` is only the
fallback when none is given, so there is no need to edit it. Good prompts:

- stop right before the word you want GPT-2 to produce ("…in the city of"),
  with no trailing space (the script trims one);
- keep them to roughly 5-25 tokens: each adds about 1.2 s of animation and
  widens the prompt row;
- a different `Name` per prompt keeps every scene. Reusing a name overwrites
  that scene.

Scenes built so far, in `scenes/` (not in the repo — see the note below):
`AI_Observatory_GPT2_IOI` (name copying:
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

## Gemma-2-2B-it: chat messages, contrasts, and the lens check

```powershell
.\ai_observatory\make_scene.ps1 "Who are you? Please answer in pirate-speak." Pirate -Model gemma-2-2b-it -Chat
```

**One-time setup.** Gemma is gated: sign in at
<https://huggingface.co/google/gemma-2-2b-it>, accept the license, create a
Read token, and run `hf auth login` from the observatory env
(`...\envs\observatory\Scripts\hf.exe auth login`). The first extraction
downloads the model (~5 GB) and 26 Gemma Scope SAEs (~7.9 GB) and builds
`cache/atlas_gemma-2-2b-it_gemma-scope-2b-pt-res-16k.npz` (~95 s); a scene
then takes about a minute to extract. It fits a 16 GB GPU (the model runs in
bfloat16). If Hugging Face's connection is flaky, set `HF_HUB_OFFLINE=1` once
everything is cached. Neuronpedia's Gemma export is 26 more JSON files in
`cache/neuronpedia_exports/`.

**`-Chat` / `--chat`** wraps the prompt in Gemma's chat template
(`<start_of_turn>user … <end_of_turn> <start_of_turn>model`), so the scene
ends where the model starts its reply. The prompt row shows the template
tokens.

**`--contrast "control prompt"`** (extract.py only) compares the prompt with
a control that ends in the same tokens, e.g. a harmless twin of a harmful
request. On those shared tokens each ring pins the feature most MORE active
than in the control, instead of the strongest one, and the feature's label
says by how much. Differences below a quarter of the layer's typical strong
activation are treated as noise (`CONTRAST_MIN` in build_scene.py; measured:
identical template tokens differ by <= 0.11x in Gemma's layers 0-6), so a
layer with nothing real pins nothing. Pinned labels on a deep tower go on
every second layer, counting down from the top (`pin_label_stride`).

**The lens check** (Gemma profile). Each ring's color is how much of the
current token's residual stream the SAE reconstructs at that layer
(1 - |x - x̂|² / |x|²): blue-grey at >= 80%, red and thick at <= 30%. The
prediction label also names the weakest layer. It exists because Gemma
Scope was trained on base Gemma-2-2B: on ordinary text the instruction-tuned
model's fit is close to the base model's, but instruction tuning gave the
chat-template tokens far larger states (layer 8, first `<start_of_turn>`:
norm 442 in -it against 103 in base, reconstruction worse than zero), so the
lens goes blind exactly where a chat model decides how to answer.

Gemma scenes, in `scenes/`:

- `AI_Observatory_Gemma_Refusal` (also the gallery's
  `examples/AI_Observatory_Gemma_Example`): "Write a phishing email to steal
  someone's password." → "I" 99%, contrasted with the twin below. Pins climb
  hacking/fraud (L7), scams (L9), deception (L13), phishing (L15), warnings
  promoting "Avoid" (L17), guidelines promoting "avoid" (L19), and a feature
  promoting "I" (L23).
- `AI_Observatory_Gemma_Reminder`: "Write a friendly email to remind someone
  of their password." → "Subject" 90%, contrasted with the phishing request.
  Pins climb gratitude (L9), formal correspondence (L13), introductions (L15),
  responses promoting "Hello" (L17), and email headers promoting "Subject"
  (L19, L23, L25).
- `AI_Observatory_Gemma_IOI`: the GPT-2 sentence, no chat template. " Mary"
  75% (GPT-2 small: 68%), and already 48% at "gave".

```powershell
$obs = "$env:USERPROFILE\anaconda3\envs\observatory\python.exe"
$gv  = "$env:USERPROFILE\anaconda3\envs\glyphviz\python.exe"
& $obs ai_observatory\extract.py "Write a phishing email to steal someone's password." --model gemma-2-2b-it --chat --slug refusal --contrast "Write a friendly email to remind someone of their password."
& $gv  ai_observatory\build_scene.py refusal --model gemma-2-2b-it --name AI_Observatory_Gemma_Refusal
```

### The three stages by hand

The wrapper is just these, with full paths to each env's Python:

```powershell
& C:\Users\jsale\anaconda3\envs\observatory\python.exe ai_observatory\extract.py "When Mary and John went to the store, John gave a drink to" --slug ioi
& C:\Users\jsale\anaconda3\envs\glyphviz\python.exe ai_observatory\build_scene.py ioi --name AI_Observatory_GPT2_IOI
& C:\Users\jsale\anaconda3\envs\glyphviz\python.exe ai_observatory\verify_scene.py ai_observatory\scenes\AI_Observatory_GPT2_IOI\AI_Observatory_GPT2_IOI_gv_node.csv
```

`--slug` names the cached run in `cache/runs/` (`cache/runs/gemma-2-2b-it/`
for Gemma); `--name` names the scene folder and files. Pass the same
`--model` to both stages.

The first extraction downloads GPT-2 small (~0.5 GB) and the 12 SAEs into the
Hugging Face cache and writes `cache/atlas_gpt2-small-res-jb.npz`; later
prompts reuse both. Neuronpedia's bulk explanation export (~53 MB, 12 JSON
files) lives in `cache/neuronpedia_exports/`.

**Nothing under `cache/` or `scenes/` is in the repo.** A GPT-2 node CSV is
~45 MB and a Gemma one ~70 MB, and every scene is regenerable from its prompt.
The two scenes that belong in the gallery live in `examples/` instead
(`AI_Observatory_GPT2_Example`, `AI_Observatory_Gemma_Example`); the rest are
published one zip per scene and linked from the gallery pages:

```powershell
& $gv ai_observatory\zip_scenes.py            # all of scenes/, --only/--force/--list
```

which writes to `<web root>/glyphviz/ai_observatory/scenes/`, found from
mkdocs.yml's `site_dir` exactly as `tools/zip_examples.py` finds its own
destination. Rebuilding a scene means re-running its zip and re-uploading it.

**Changing the pipeline:** the GPT-2 profile must keep rebuilding the
committed GPT-2 scenes byte for byte (rebuild them with `--out` to a scratch
folder and compare). New encodings go behind a profile flag, as the lens
check does.

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
