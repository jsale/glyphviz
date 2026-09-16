# Inside GPT-2: Mary and John

GPT-2 small reading "When Mary and John went to the store, John gave a drink
to" and predicting " Mary" (68%). The first scene of the AI Observatory; the
pipeline that built it, and more scenes, live in the repo's
[`ai_observatory/`](../../ai_observatory/README.md) folder.

Open `AI_Observatory_GPT2_Example_gv_node.csv` (about 12 s to load) and press
**Space** to play.

## How to read this scene

GPT-2 doesn't store words. It stores *concepts*, thousands of them
overlapping in the same numbers, and it revises which ones are active as it
reads each word. This scene breaks that hidden state into named concepts and
shows which ones light up, in what order, and which ones caused which, one
word at a time.

Picture a twelve-station assembly line. The sentence enters at the bottom;
each station (a layer, one ring) reads everything written so far on a shared
workpiece (the spine, the *residual stream*) and adds its own notes. The lit
spheres are those notes made readable: *providing solutions or relief* at
layer 3, *the action of giving something to someone* by layer 6, *phrases
that start with a person's name* at layer 11. The rods are the handoffs. The
cycle repeats once per word, and the glyph at the top says what GPT-2 would
say next and how sure it is.

**Trace a circuit yourself:** stop on a token, click a large lit sphere and
read its label, click a rod leaving it, follow the rod up to the next layer,
and repeat until you reach the prediction.

| Term | Here |
|---|---|
| token | the unit the model reads, roughly a word; one cube in the prompt row |
| layer | one of 12 processing stages; one ring |
| residual stream | the running state every layer reads and writes; the spine |
| superposition | many concepts in the same numbers, so no single neuron means one thing |
| feature | one concept in the learned dictionary; every point on a ring |
| sparse autoencoder | the method that learns that dictionary |
| activation | how strongly a feature is present now; sphere size |
| attribution | an estimate of how much one feature caused another; the rods |
| attention head | one of 12 per layer that fetch from earlier words; the cones |
| attention weight | how much of a head's attention one earlier word gets; the violet links |

The dictionary is a lens, not the model, and the labels are machine-written
guesses: see the limits below.

## What you see

- **The tower.** The thin spine is the residual stream. Each of the model's
  12 layers is a ring: layer 0 at the bottom, the prediction at the top.
- **Every feature, always in the same place.** Each ring holds all 24,576
  features a sparse autoencoder finds at that layer, as points. They are
  placed by meaning (features whose directions are similar sit together, and
  each ring is turned to line up with the one below), so color is a meaning
  neighborhood and it holds all the way up. Click any point to read its
  explanation.
- **Lit features.** The strongest features at each token are spheres at their
  home positions; size is activation.
- **Attribution rods.** Which features drove which, layer to layer, and from
  the last layer to the prediction. Orange pushes the target up, blue pushes
  it down; thickness is the share of the target's attribution.
- **Attention heads.** Twelve cones on a smaller ring just below each layer's
  ring: the heads, which are how information moves between words at all. Size
  is how strongly that head pushes the word the model is about to say, orange
  toward it and blue against, and a violet link shows the word it is looking
  at. On the last token, L9.H9 and L9.H6 read " Mary" and push it (+3.03,
  +2.75) while L10.H7 reads the same word and pushes back (−3.16). A head with
  nothing to fetch parks its attention on the invisible start token (64 of 144
  do here), and those links are dropped.
- **The prompt** runs along the front, one cube per token.

Stopped, the scene shows the last token, "to", where the answer is decided.

## What you hear

The audio is generated from the same numbers as the animation. For every
token, as the pulse reaches each layer, that layer plays a note:

| Sound | Means |
|---|---|
| pitch | which layer (a pentatonic scale from D3 at layer 0 to E5 at layer 11) |
| loudness | how strongly that layer's lit features fire at this token |
| brightness (harmonics) | how many of the layer's 24,576 features are active at all |
| left / right | where on the ring the activity is, as seen from the front |
| chime at the top | the prediction; louder the more confident GPT-2 is |
| click | the next token begins |

A layer with nothing lit is silent. Pitch is a fixed design choice so you can
tell layers apart; everything else is data.

## Honest limits

- The autoencoders are a lens, not the model: they reconstruct 99.7% of the
  residual stream's variance at layer 0, falling to 78% at layers 10-11.
- Explanations are Neuronpedia's automated guesses and are sometimes wrong.
- Attribution is gradient × activation between adjacent layers with each
  autoencoder's reconstruction error held fixed: a per-prompt linear
  approximation, pruned to the strongest few edges per target.
- The ring layout is one projection of 768 dimensions; distance around a ring
  is suggestive, not a measurement.
- A head's size is its *direct* effect on the prediction only: what its own
  output does read straight through to the output. It misses what a head does
  by feeding other heads downstream, which is most of what the S-inhibition
  heads (L7.H3, L7.H9, L8.H6, L8.H10) do here.
- Head role names ("name mover" and the rest) are citations to Wang et al.
  2022, stated beside this scene's own measurement, not derived from it.

## Sources

- GPT-2 small, OpenAI (MIT), run through
  [TransformerLens](https://github.com/TransformerLensOrg/TransformerLens).
- Residual-stream sparse autoencoders `gpt2-small-res-jb`, Joseph Bloom (MIT),
  loaded with [SAELens](https://github.com/jbloomAus/SAELens).
- Feature explanations from [Neuronpedia](https://www.neuronpedia.org/)'s
  public exports.
