# Inside Gemma: Why It Says No

Gemma-2-2B-it, Google's small instruction-tuned chat model, receives the
message "Write a phishing email to steal someone's password." and prepares to
answer **"I"** (99%), the first word of *"I cannot…"*. The second scene of the
AI Observatory; the pipeline that built it, and more scenes, live in the repo's
[`ai_observatory/`](../../ai_observatory/README.md) folder.

Open `AI_Observatory_Gemma_Example_gv_node.csv` (about 10 s to load) and press
**Space** to play.

## How to read this scene

A chat model doesn't see a question; it sees one long run of tokens, including
invisible *template* tokens that mark whose turn it is:
`<start_of_turn>user`, the message, `<end_of_turn>`, then `<start_of_turn>model`
and a newline. The model decides how to answer while it reads those last few
tokens, before it has written anything.

To see *what* it decided, the scene compares it with a **control**: a harmless
twin, "Write a friendly email to remind someone of their password.", which
Gemma answers with "Subject" (90%). Both messages end in the same seven tokens
(" password", ".", and the template). On those tokens, each ring pins the
feature that is most **more active for the phishing request than for the
twin**. Stopped on the last token, they read up the tower:

| Layer | Pinned feature (Neuronpedia's label) | Activation, phishing | Activation, twin |
|---|---|---|---|
| 7 | references to hacking, fraud, and cybersecurity threats | 38 | 7 |
| 9 | terms associated with scams and fraudulent activities | 20 | 0 |
| 13 | instances of deception and pretense | 40 | 0 |
| 15 | topics related to cybersecurity and phishing threats | 37 | 0 |
| 17 | warnings and contraindications (promotes "Avoid") | 58 | 0 |
| 19 | guidelines and recommendations (promotes "avoid") | 60 | 0 |
| 23 | storytelling and narrative structure (promotes "I") | 167 | 0 |

(Activations are on the shared token where the two differ most; each label
in the scene names that token.) The request is recognized as fraud, then as something to warn about and
avoid, and the top of the tower turns toward "I". Below layer 7 the two
messages still look alike on these tokens, so those rings pin nothing there.

**Trace it yourself:** stop on a token, click a large lit sphere and read its
label, click a rod leaving it, follow the rod up to the next layer, and repeat
until you reach the prediction.

**Watch the rings.** Each ring's color is a *lens check*: blue-grey while the
sparse autoencoder can reconstruct that token's state at that layer, turning
red and thicker as it misses more. On the words of the request the rings stay
blue-grey, with at most a faint tint on a few. When the chat template arrives,
15 to 20 of the 26 rings turn red. The autoencoders were trained on the *base*
Gemma model, which never learned the chat format; instruction tuning gave
those template tokens unusually large internal states the dictionaries cannot
represent. So the lens is weakest at the
very moment the refusal forms, and the scene says so instead of hiding it.

| Term | Here |
|---|---|
| token | the unit the model reads, roughly a word; one cube in the prompt row |
| chat template | the invisible turn markers around a message |
| layer | one of 26 processing stages; one ring |
| residual stream | the running state every layer reads and writes; the spine |
| feature | one concept in the learned dictionary; every point on a ring |
| sparse autoencoder | the method that learns that dictionary |
| activation | how strongly a feature is present now; sphere size |
| attribution | an estimate of how much one feature caused another; the rods |
| control prompt | a near-identical input used to isolate what differs |

## What you see

- **The tower.** The spine is the residual stream. Each of the model's 26
  layers is a ring: layer 0 at the bottom, the prediction at the top.
- **Every feature, always in the same place.** Each ring holds all 16,384
  features a Gemma Scope sparse autoencoder finds at that layer, as points,
  placed by meaning, so color is a meaning neighborhood. Click any point to
  read its explanation.
- **Lit features.** The strongest features at each token are spheres at their
  home positions; size is activation.
- **Attribution rods.** Which features drove which, layer to layer, and from
  the last layer to the prediction. Orange pushes the target up, blue pushes
  it down; thickness is the share of the target's attribution.
- **Ring color.** The lens check described above.
- **The prompt** runs along the front, one cube per token, template included.

Stopped, the scene shows the last token, the newline after `model`, where the
answer is decided.

## What you hear

The same mapping as the GPT-2 scene. For every token, as the pulse reaches
each layer, that layer plays a note:

| Sound | Means |
|---|---|
| pitch | which layer; the same twelve pentatonic pitches as GPT-2 (D3 to E5), shared by neighboring layers, so the top of both towers sounds the same note |
| loudness | how strongly that layer's lit features fire at this token |
| brightness (harmonics) | how many of the layer's features are active at all |
| left / right | where on the ring the activity is, as seen from the front |
| chime at the top | the prediction; louder the more confident Gemma is |
| click | the next token begins |

## Honest limits

- The autoencoders are a lens, not the model, and here a borrowed one: Gemma
  Scope was trained on base Gemma-2-2B. On ordinary text they still capture
  most of the instruction-tuned model's state (at least 72% of its squared
  norm, at every layer, on every word of this message); on the template they
  capture as little as 38%
  at the final token, and 0% at layer 8 on the first `<start_of_turn>`. The ring
  colors show where.
- Explanations are Neuronpedia's automated guesses, written from base-model
  text, and some are plainly wrong here: the layer-25 feature pinned at the top
  is labelled "medical and clinical treatment settings".
- The contrast shows what *differs* from one control prompt, not a complete
  cause. A different control would pin somewhat different features.
- Attribution is gradient × activation between adjacent layers with each
  autoencoder's reconstruction error held fixed: a per-prompt linear
  approximation, pruned to the strongest few edges per target.
- The scene ends where the reply begins; it shows the decision to start with
  "I", not the refusal text that follows.

## Sources

- Gemma-2-2B-it, Google, under the
  [Gemma Terms of Use](https://ai.google.dev/gemma/terms), run through
  [TransformerLens](https://github.com/TransformerLensOrg/TransformerLens).
- [Gemma Scope](https://huggingface.co/google/gemma-scope-2b-pt-res)
  residual-stream sparse autoencoders (16k width, canonical), Google DeepMind
  (CC BY 4.0), loaded with [SAELens](https://github.com/jbloomAus/SAELens).
- Feature explanations from [Neuronpedia](https://www.neuronpedia.org/)'s
  public exports; 425,928 of the 425,984 features have one.
