# Inside GPT-2: Mary and John

GPT-2 small reading "When Mary and John went to the store, John gave a drink
to" and predicting " Mary" (68%). The first scene of the AI Observatory; the
pipeline that built it, and more scenes, live in the repo's
[`ai_observatory/`](../../ai_observatory/README.md) folder.

Open `AI_Observatory_GPT2_Example_gv_node.csv` (about 12 s to load) and press
**Space** to play.

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

## Sources

- GPT-2 small, OpenAI (MIT), run through
  [TransformerLens](https://github.com/TransformerLensOrg/TransformerLens).
- Residual-stream sparse autoencoders `gpt2-small-res-jb`, Joseph Bloom (MIT),
  loaded with [SAELens](https://github.com/jbloomAus/SAELens).
- Feature explanations from [Neuronpedia](https://www.neuronpedia.org/)'s
  public exports.
