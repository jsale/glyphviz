"""AI Observatory model profiles: everything that differs between the models
the Observatory can look inside. Imported by both stages, so it stays free of
torch (stage B runs in the glyphviz env).

A profile pairs a model with ONE family of residual-stream sparse
autoencoders, one per layer, and says where their labels come from. Adding a
model is adding a profile here; the pipeline itself is model-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    key: str                  # --model value
    tl_name: str              # TransformerLens model name
    display: str              # "GPT-2 small"
    short: str                # "GPT-2", used in running prose ("GPT-2 predicts")
    size_text: str            # "124M parameters, 12 layers"
    n_layers: int
    d_sae: int
    sae_release: str          # SAELens release
    sae_id: str               # format string, {layer}
    hook: str                 # format string, {layer}; the hook each SAE reads
    # A resid_pre SAE at layer L is read again at resid_pre L+1, which is where
    # a forward pass stopped at block L+1 ends; a resid_post SAE needs one
    # block more. stop_at_layer for "the next layer's SAE input" = L + 1 + this.
    hook_offset: int
    stage_text: str           # "entering block {layer}" / "leaving block {layer}"
    np_export: str            # Neuronpedia bulk export file, {layer}
    np_api: str               # Neuronpedia per-feature API path, {layer}
    # TransformerLens folds LayerNorm into the unembedding for GPT-2; Gemma
    # loads unprocessed (its SAEs were trained on the raw residual stream), so
    # the final RMSNorm's per-dimension weight has to be applied by hand when
    # reading a direction through W_U.
    processed_weights: bool
    atlas_name: str           # cache/atlas_<this>.npz
    vocab_name: str           # cache/<this>
    runs_subdir: str          # cache/runs/<this>/<slug>; "" = cache/runs/<slug>
    scene_prefix: str         # scene folder name prefix
    promote_from_layer: int   # logit-lens "promotes" labels only from here up
    layer_gap: float          # world units between rings
    frames_per_token: int
    bos_text: str
    # Per-token lens fidelity (how much of the residual stream the SAE
    # reconstructs) drawn on the layer rings. Off for GPT-2 so its committed
    # scenes rebuild byte-identical; on for Gemma, where base-model SAEs read
    # an instruction-tuned model and go blind on chat-template tokens.
    encode_fidelity: bool
    # Attention heads as glyphs of their own: an inner ring per layer. Off for
    # Gemma until grouped-query attention is checked (8 query heads share 4
    # key/value heads there, so "one head" means something different).
    show_heads: bool
    # Each layer's strongest feature pins its label as the pulse passes. Tag
    # labels are fixed-pixel, so a deep tower pins only every Nth layer
    # (counting down from the top, which always pins) to keep them apart.
    pin_label_stride: int = 1
    chat_template: str = ""   # {message}; "" = no chat format


GPT2_SMALL = Profile(
    key="gpt2-small", tl_name="gpt2-small", display="GPT-2 small", short="GPT-2",
    size_text="124M parameters, 12 layers", n_layers=12, d_sae=24576,
    sae_release="gpt2-small-res-jb", sae_id="blocks.{layer}.hook_resid_pre",
    hook="blocks.{layer}.hook_resid_pre", hook_offset=0,
    stage_text="the residual stream entering block {layer}",
    np_export="gpt2-small_{layer}-res-jb.json", np_api="gpt2-small/{layer}-res-jb",
    processed_weights=True, atlas_name="gpt2-small-res-jb", vocab_name="gpt2_vocab.json",
    runs_subdir="", scene_prefix="AI_Observatory_GPT2", promote_from_layer=8,
    layer_gap=14.0, frames_per_token=36, bos_text="<|endoftext|>", encode_fidelity=False,
    show_heads=True)

GEMMA_2_2B_IT = Profile(
    key="gemma-2-2b-it", tl_name="gemma-2-2b-it", display="Gemma-2-2B-it", short="Gemma",
    size_text="2.6B parameters, 26 layers, instruction-tuned", n_layers=26, d_sae=16384,
    sae_release="gemma-scope-2b-pt-res-canonical", sae_id="layer_{layer}/width_16k/canonical",
    hook="blocks.{layer}.hook_resid_post", hook_offset=1,
    stage_text="the residual stream leaving block {layer}",
    np_export="gemma-2-2b_{layer}-gemmascope-res-16k.json",
    np_api="gemma-2-2b/{layer}-gemmascope-res-16k",
    processed_weights=False, atlas_name="gemma-2-2b-it_gemma-scope-2b-pt-res-16k",
    vocab_name="gemma2_vocab.json", runs_subdir="gemma-2-2b-it",
    scene_prefix="AI_Observatory_Gemma", promote_from_layer=17, layer_gap=14.0,
    frames_per_token=48, bos_text="<bos>", encode_fidelity=True, show_heads=False,
    pin_label_stride=2,
    chat_template="<start_of_turn>user\n{message}<end_of_turn>\n<start_of_turn>model\n")

PROFILES = {p.key: p for p in (GPT2_SMALL, GEMMA_2_2B_IT)}

# Published roles for the heads of GPT-2 small's indirect-object circuit, from
# Wang et al. 2022, "Interpretability in the Wild" (arXiv 2211.00593). These
# name what researchers found the head doing on sentences of the Mary-and-John
# kind; a scene states them as a citation beside its OWN measurement of what
# the head did on its prompt, never instead of it. Checked against our
# extraction on the IOI prompt (name movers +2.11/+2.10/+0.82 toward ' Mary',
# negative name movers -2.28/-0.84, L0.H1 attending the first ' John' 0.52
# from the second, L4.H11 the previous token at 1.00, L5.H5 the token after
# the earlier ' John' at 0.92).
HEAD_ROLES = {
    "gpt2-small": {
        (9, 9): "name mover", (9, 6): "name mover", (10, 0): "name mover",
        (10, 7): "negative name mover", (11, 10): "negative name mover",
        (7, 3): "S-inhibition", (7, 9): "S-inhibition",
        (8, 6): "S-inhibition", (8, 10): "S-inhibition",
        (5, 5): "induction", (6, 9): "induction",
        (0, 1): "duplicate token", (0, 10): "duplicate token", (3, 0): "duplicate token",
        (2, 2): "previous token", (4, 11): "previous token",
    },
}
HEAD_ROLE_CITATION = "Wang et al. 2022"


def head_role(profile_key: str, layer: int, head: int) -> str:
    return HEAD_ROLES.get(profile_key, {}).get((layer, head), "")


def get(key: str) -> Profile:
    try:
        return PROFILES[key]
    except KeyError:
        raise SystemExit(f"unknown model '{key}'; choose from {', '.join(PROFILES)}") from None
