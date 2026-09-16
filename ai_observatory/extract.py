"""AI Observatory, stage A: run a language model on a prompt and extract what
the scene needs. Runs in the `observatory` conda env (torch + TransformerLens +
SAELens); the GlyphViz app never imports this. `--model` picks a profile from
profiles.py (GPT-2 small by default, or Gemma-2-2B-it).

Outputs, under ai_observatory/cache/ :

  atlas_<profile>.npz           prompt-independent home position of every SAE
                                feature (computed once, reused by every prompt)
  runs/[<model>/]<slug>/run.json  tokens, predictions, active features, edges
  runs/[<model>/]<slug>/acts.npz  activation of every displayed feature per token

The atlas is what makes this an observatory rather than a one-off picture: a
feature sits in the same place in every prompt's scene.

Attribution edges are gradient x activation between ADJACENT layers' SAE
features, with each SAE's reconstruction error held fixed, so the path runs
through features. It is a linear, per-prompt approximation; the scene says so.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from pathlib import Path

import numpy as np
import torch

import profiles

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"


# --------------------------------------------------------------------------
# Model + SAEs
# --------------------------------------------------------------------------

def load_model(profile, device):
    from transformer_lens import HookedTransformer
    if profile.processed_weights:
        model = HookedTransformer.from_pretrained(profile.tl_name, device=device)
    else:
        # The SAEs were trained on the raw residual stream; TransformerLens's
        # default weight processing (centering, LayerNorm folding) changes
        # that basis and would make every SAE read garbage without an error.
        model = HookedTransformer.from_pretrained_no_processing(
            profile.tl_name, device=device,
            dtype=torch.bfloat16 if device == "cuda" else torch.float32)
    model.eval()
    for p in model.parameters():
        p.requires_grad_(False)       # attribution differentiates activations only
    return model


def sae_dtype(model):
    return str(model.cfg.dtype).replace("torch.", "")


def str_tokens(model, prompt):
    try:
        return model.to_str_tokens(prompt)
    except TypeError:
        # TransformerLens 3.8.1's to_str_tokens breaks on Gemma's tokenizer.
        return [model.tokenizer.decode([int(t)]) for t in model.to_tokens(prompt)[0]]


def unembed(model, profile):
    """[d_model, vocab]: what a residual direction does to the logits."""
    w_u = model.W_U.detach().float()
    if not profile.processed_weights:
        w_u = model.ln_final.w.detach().float()[:, None] * w_u
    return w_u


def load_saes(profile, device, dtype="float32"):
    from sae_lens import SAE
    saes, densities = [], []
    for layer in range(profile.n_layers):
        sae_id = profile.sae_id.format(layer=layer)
        density = None
        loader = getattr(SAE, "from_pretrained_with_cfg_and_sparsity", None)
        if loader is not None:
            sae, _cfg, sparsity = loader(release=profile.sae_release, sae_id=sae_id,
                                         device=device, dtype=dtype)
            density = sparsity
        else:
            out = SAE.from_pretrained(release=profile.sae_release, sae_id=sae_id, device=device)
            if isinstance(out, tuple):
                sae = out[0]
                density = out[2] if len(out) > 2 else None
            else:
                sae = out
        sae.eval()
        saes.append(sae)
        densities.append(None if density is None
                         else density.detach().float().cpu().numpy())
    return saes, densities


# --------------------------------------------------------------------------
# Atlas: a fixed home position for every feature
# --------------------------------------------------------------------------

def spherical_kmeans(x, k, iters=40, seed=0):
    """x: unit rows [n, d] on the GPU. Returns (labels [n], centroids [k, d])."""
    g = torch.Generator(device="cpu").manual_seed(seed)
    idx = torch.randperm(x.shape[0], generator=g)[:k].to(x.device)
    cent = x[idx].clone()
    labels = None
    for _ in range(iters):
        sim = x @ cent.T
        new = sim.argmax(dim=1)
        if labels is not None and torch.equal(new, labels):
            break
        labels = new
        sums = torch.zeros_like(cent).index_add_(0, labels, x)
        counts = torch.bincount(labels, minlength=k)
        empty = counts == 0
        if empty.any():                       # reseed empty clusters on the worst-fit points
            worst = sim.max(dim=1).values.argsort()[: int(empty.sum())]
            sums[empty] = x[worst]
        cent = torch.nn.functional.normalize(sums, dim=1)
    return labels, cent


def circular_order(cent):
    """Angle (radians) per centroid from a spectral circular embedding, so
    neighbouring clusters around the ring mean similar things."""
    sim = (cent @ cent.T).clamp(min=0).cpu().double()
    k = sim.shape[0]
    nn = min(8, k - 1)
    w = torch.zeros_like(sim)
    top = sim.topk(nn + 1, dim=1).indices
    for i in range(k):
        w[i, top[i]] = sim[i, top[i]]
    w = torch.maximum(w, w.T)
    w.fill_diagonal_(0)
    d = w.sum(1)
    dinv = torch.where(d > 0, d.rsqrt(), torch.zeros_like(d))
    lap = torch.eye(k, dtype=w.dtype) - dinv[:, None] * w * dinv[None, :]
    _vals, vecs = torch.linalg.eigh(lap)
    return torch.atan2(vecs[:, 2], vecs[:, 1]).numpy()


def build_atlas(profile, saes, densities, model, k_clusters, out_path, device):
    t0 = time.time()
    layers = {}
    prev = None           # (centroids, centre angles, sizes) of the layer below
    w_u = unembed(model, profile)             # [d_model, vocab]
    chunk = max(64, 2048 * 50257 // w_u.shape[1])   # ~400 MB of logits per chunk
    for layer, sae in enumerate(saes):
        w = torch.nn.functional.normalize(sae.W_dec.detach().float(), dim=1)  # [n, d]
        n = w.shape[0]
        labels, cent = spherical_kmeans(w, k_clusters, seed=layer)
        sizes = torch.bincount(labels, minlength=k_clusters).cpu().numpy()
        ang = circular_order(cent)
        order = np.argsort(ang)                               # ring order

        # Arc per cluster proportional to membership; start angle chosen to
        # line up with the layer below (rotation + optional reflection).
        span = sizes[order] / n * 2 * math.pi
        centre_rel = np.cumsum(span) - span / 2               # relative centres
        best = (None, -np.inf)
        if prev is not None:
            cross = (cent @ prev[0].T).clamp(min=0).cpu().numpy()   # [k, k_prev]
            weight = cross * sizes[:, None] * prev[2][None, :]
            for flip in (1, -1):
                rel = np.empty(k_clusters)
                rel[order] = flip * centre_rel
                for deg in range(360):
                    phi = math.radians(deg)
                    score = float((weight * np.cos(rel[:, None] + phi - prev[1][None, :])).sum())
                    if score > best[1]:
                        best = ((flip, phi), score)
            flip, phi = best[0]
        else:
            flip, phi = 1, 0.0
        centre = np.empty(k_clusters)
        centre[order] = flip * centre_rel + phi
        half = np.empty(k_clusters)
        half[order] = span / 2

        # Within a cluster: rank along PC1 spreads members across the arc,
        # PC2 -> height in the band, PC3 -> radial depth of the band.
        angle = np.zeros(n, dtype=np.float32)
        dz = np.zeros(n, dtype=np.float32)
        dr = np.zeros(n, dtype=np.float32)
        lab = labels.cpu().numpy()
        for c in range(k_clusters):
            members = np.nonzero(lab == c)[0]
            if members.size == 0:
                continue
            m = w[torch.as_tensor(members, device=w.device)]
            m = m - m.mean(0, keepdim=True)
            if members.size >= 4:
                _u, _s, v = torch.linalg.svd(m, full_matrices=False)
                pcs = (m @ v[:3].T).cpu().numpy()
            else:
                pcs = np.zeros((members.size, 3), dtype=np.float32)
            rank = pcs[:, 0].argsort().argsort()
            u = (rank + 0.5) / members.size * 2 - 1           # -1..1 uniform
            angle[members] = centre[c] + flip * u * half[c] * 0.9
            for col, dest in ((1, dz), (2, dr)):
                p = pcs[:, col]
                s = np.percentile(np.abs(p), 98) if members.size >= 4 else 1.0
                dest[members] = np.clip(p / (s or 1.0), -1, 1)

        # What each cluster centroid and each feature pushes the output towards
        # (decoder direction through the unembedding) -- a local, model-derived
        # label that needs no network.
        cent_logits = cent @ w_u
        cent_top = cent_logits.topk(6, dim=1).indices.cpu().numpy().astype(np.int32)
        feat_top = np.zeros((n, 3), dtype=np.int32)
        for s in range(0, n, chunk):
            feat_top[s:s + chunk] = (w[s:s + chunk] @ w_u).topk(3, dim=1).indices.cpu().numpy()

        layers[layer] = dict(
            cluster=lab.astype(np.int16), angle=angle.astype(np.float32),
            dz=dz, dr=dr, cluster_centre=centre.astype(np.float32),
            cluster_half=half.astype(np.float32), cluster_size=sizes.astype(np.int32),
            cluster_top_tokens=cent_top, feature_top_tokens=feat_top,
            log_density=(np.zeros(n, np.float32) if densities[layer] is None
                         else densities[layer].astype(np.float32)))
        prev = (cent, centre, sizes)
        print(f"  atlas layer {layer}: {n} features, {k_clusters} clusters, "
              f"align score {best[1]:.3g}")

    flat = {f"L{l}_{key}": val for l, d in layers.items() for key, val in d.items()}
    flat["k_clusters"] = np.array(k_clusters)
    np.savez_compressed(out_path, **flat)
    print(f"atlas written: {out_path} ({time.time() - t0:.1f}s)")


# --------------------------------------------------------------------------
# One prompt
# --------------------------------------------------------------------------

def slugify(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "prompt"


def feature_acts(profile, model, saes, tokens):
    """Per layer: SAE feature activations [T, n], and per token the fraction of
    the residual stream's squared norm the SAE reconstructs (1 - |x - x^|^2 /
    |x|^2, clipped to 0..1) -- how much of that token's state the lens sees."""
    hooks = {profile.hook.format(layer=l) for l in range(profile.n_layers)}
    acts, fidelity = [], []
    with torch.no_grad():
        _logits, cache = model.run_with_cache(tokens, names_filter=lambda name: name in hooks)
        for layer, sae in enumerate(saes):
            x = cache[profile.hook.format(layer=layer)][0]
            f = sae.encode(x)                                # [T, n]
            acts.append(f)
            xf = x.float()
            err = ((xf - sae.decode(f).float()) ** 2).sum(-1) / (xf ** 2).sum(-1).clamp(min=1e-9)
            fidelity.append((1 - err).clamp(0, 1).cpu().numpy())
    return acts, _logits[0], np.stack(fidelity)              # fidelity [L, T]


def attribution_edges(profile, model, saes, tokens, acts, targets_per_token, sources_per_target,
                      min_frac):
    """Gradient x activation from layer L features to layer L+1 features (and
    from layer 11 features to the predicted logit). Returns a list of dicts."""
    edges = []
    t_len = tokens.shape[1]

    def spliced_hook(layer, holder):
        sae = saes[layer]

        def hook(x, hook):
            f = sae.encode(x[0]).detach()
            err = (x[0] - sae.decode(f)).detach()
            pos = torch.nonzero(f[1:] > 0) + torch.tensor([1, 0], device=f.device)  # skip BOS
            vals = f[pos[:, 0], pos[:, 1]].clone().requires_grad_(True)
            dense = torch.zeros_like(f).index_put((pos[:, 0], pos[:, 1]), vals)
            dense[0] = f[0]
            holder["pos"], holder["vals"] = pos, vals
            return (sae.decode(dense) + err)[None]
        return hook

    n_layers = profile.n_layers
    for layer in range(n_layers):
        holder = {}
        hook_name = profile.hook.format(layer=layer)
        if layer + 1 < n_layers:
            out = model.run_with_hooks(tokens, fwd_hooks=[(hook_name, spliced_hook(layer, holder))],
                                       stop_at_layer=layer + 1 + profile.hook_offset)
            tgt_acts = saes[layer + 1].encode(out[0])        # [T, n]
            with torch.no_grad():
                ref = acts[layer + 1]
            target_list = []
            for t in range(1, t_len):
                top = ref[t].topk(targets_per_token)
                for val, j in zip(top.values.tolist(), top.indices.tolist()):
                    if val > 0:
                        target_list.append((t, j, tgt_acts[t, j], ("feat", layer + 1, j)))
        else:
            logits = model.run_with_hooks(tokens, fwd_hooks=[(hook_name, spliced_hook(layer, holder))])[0]
            target_list = []
            for t in range(1, t_len):
                tok = int(logits[t].argmax())
                target_list.append((t, tok, logits[t, tok] - logits[t].mean(), ("logit", n_layers, tok)))

        pos, vals = holder["pos"], holder["vals"]
        for i, (t, _j, scalar, target) in enumerate(target_list):
            grad, = torch.autograd.grad(scalar, vals, retain_graph=i < len(target_list) - 1)
            attr = (grad * vals).detach()
            keep = pos[:, 0] <= t                            # causal: only tokens up to t
            attr = torch.where(keep, attr, torch.zeros_like(attr))
            total = attr.abs().sum()
            if total <= 0:
                continue
            top = attr.abs().topk(min(sources_per_target, attr.numel()))
            for a, k in zip(top.values.tolist(), top.indices.tolist()):
                if a < min_frac * float(total):
                    continue
                edges.append(dict(
                    token=t, src_layer=layer, src_feature=int(pos[k, 1]),
                    src_token=int(pos[k, 0]), dst_kind=target[0], dst_layer=target[1],
                    dst_index=int(target[2]), attribution=float(attr[k]),
                    share=float(a / float(total))))
        del holder
        print(f"  edges from layer {layer}: {sum(1 for e in edges if e['src_layer'] == layer)}")
    return edges


def head_effects(profile, model, tokens, top_tokens, heads_per_token, min_attn, sources_per_head):
    """What every attention head did, per token.

    A head is the only way information moves between positions: it attends to
    earlier tokens (weights summing to 1) and writes a vector into the residual
    stream. So each one gets two measurements:

      dla [heads, T]  direct logit attribution -- the head's own output at this
                      token, read through the final LayerNorm and the
                      unembedding, toward the token the model actually predicts
                      (centred on the mean logit, the convention the
                      feature->logit edges already use). Positive pushes the
                      prediction up, negative pushes it down.
      bos [heads, T]  the share parked on the start token. Attention has to sum
                      to 1, so a head with nothing to fetch dumps it there
                      (measured on the IOI prompt: 64 of 144 heads put over half
                      their attention there). Those are not "looking" and the
                      scene drops them.

    Plus, for the heads that matter most at each token, where they looked.
    """
    n_layers, n_heads = model.cfg.n_layers, model.cfg.n_heads
    model.set_use_attn_result(True)
    want = ("hook_result", "hook_pattern")
    with torch.no_grad():
        # ln_final.hook_scale too: apply_ln_to_stack reads it to put a head's
        # output on the same scale the unembedding sees.
        _logits, cache = model.run_with_cache(
            tokens, names_filter=lambda name: (name.endswith(want)
                                               or name == "ln_final.hook_scale"))
        t_len = tokens.shape[1]
        stack = torch.stack([cache[f"blocks.{l}.attn.hook_result"][0, :, h]
                             for l in range(n_layers) for h in range(n_heads)])   # [heads, T, d]
        w_u = unembed(model, profile)
        dla = np.zeros((stack.shape[0], t_len), dtype=np.float32)
        for t in range(1, t_len):
            # scaled by the same LayerNorm the model applies before unembedding
            scaled = cache.apply_ln_to_stack(stack[:, t][:, None], layer=-1, pos_slice=t)[:, 0]
            direction = w_u[:, top_tokens[t]].float() - w_u.float().mean(-1)
            dla[:, t] = (scaled.float() @ direction).cpu().numpy()
        pattern = torch.stack([cache[f"blocks.{l}.attn.hook_pattern"][0, h]
                               for l in range(n_layers) for h in range(n_heads)])  # [heads, T, T]
        bos = pattern[:, :, 0].float().cpu().numpy()
    model.set_use_attn_result(False)

    def sources(index, t, k):
        w = pattern[index, t].clone()
        w[0] = 0                       # the start-token sink is not looking
        top = w.topk(min(k, w.shape[0]))
        return [(int(j), float(v)) for v, j in zip(top.values.tolist(), top.indices.tolist())
                if v >= min_attn and j < t]

    attends, peaks = [], []
    for t in range(1, t_len):
        order = np.argsort(-np.abs(dla[:, t]))[:heads_per_token]
        for index in order:
            for src, weight in sources(int(index), t, sources_per_head):
                attends.append(dict(token=t, layer=int(index) // n_heads,
                                    head=int(index) % n_heads, src=src,
                                    weight=round(weight, 3), dla=float(dla[index, t])))
    for index in range(dla.shape[0]):
        t = int(np.argmax(np.abs(dla[index, 1:])) + 1)
        src = sources(index, t, 1)
        peaks.append(dict(layer=index // n_heads, head=index % n_heads, token=t,
                          dla=float(dla[index, t]), bos=float(bos[index, t]),
                          src=src[0][0] if src else None,
                          weight=src[0][1] if src else 0.0))
    print(f"heads: {dla.shape[0]} heads, {len(attends)} attention links, "
          f"strongest |effect| {np.abs(dla).max():.2f}")
    return dict(n_heads=n_heads, attends=attends, peaks=peaks), dla, bos


def contrast_features(profile, model, saes, tokens, acts, message, chat, per_token):
    """Run a control prompt and compare feature activations on the tokens both
    prompts END with (for chat prompts, at least the template that hands the
    turn to the model). Whatever differs there is what the model concluded
    about the part that differs. Returns the control's summary and, per shared
    token and layer, the features most MORE active in this prompt."""
    prompt = profile.chat_template.format(message=message) if chat else message
    other = model.to_tokens(prompt)
    k = 0
    while (k < min(tokens.shape[1], other.shape[1]) - 1
           and int(tokens[0, -1 - k]) == int(other[0, -1 - k])):
        k += 1
    if k == 0:
        raise SystemExit("--contrast prompt shares no final tokens with the prompt")
    other_acts, other_logits, _fid = feature_acts(profile, model, saes, other)
    probs = other_logits[-1].float().softmax(-1).topk(5)
    t_len, o_len = tokens.shape[1], other.shape[1]
    found = []
    with torch.no_grad():
        for back in range(1, k + 1):
            t = t_len - back
            for layer in range(profile.n_layers):
                diff = acts[layer][t].float() - other_acts[layer][o_len - back].float()
                top = diff.topk(per_token)
                for d, j in zip(top.values.tolist(), top.indices.tolist()):
                    if d > 0:
                        found.append(dict(token=t, layer=layer, feature=int(j), diff=float(d),
                                          act=float(acts[layer][t, j]),
                                          act_other=float(other_acts[layer][o_len - back, j])))
    print(f"contrast: {k} shared final tokens, {len(found)} contrast features; control predicts "
          + ", ".join(f"{model.to_string(int(i))!r} {float(p):.0%}"
                      for p, i in zip(probs.values, probs.indices)))
    return dict(message=message, prompt=prompt, shared_tokens=k,
                predictions=[(model.to_string(int(i)), float(p))
                             for p, i in zip(probs.values.tolist(), probs.indices.tolist())],
                features=found)


def fetch_explanations(profile, keys, cache_dir, workers=6):
    """Neuronpedia auto-interp explanations for (layer, index) pairs, cached
    on disk. Missing/unreachable -> no entry (the scene falls back to the
    model-derived 'promotes' label)."""
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor
    cache_dir.mkdir(parents=True, exist_ok=True)

    def one(key):
        layer, index = key
        path = cache_dir / f"{layer}_{index}.json"
        if path.exists():
            return key, json.loads(path.read_text(encoding="utf-8"))
        url = f"https://www.neuronpedia.org/api/feature/{profile.np_api.format(layer=layer)}/{index}"
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    data = json.loads(r.read().decode("utf-8"))
                keep = dict(
                    explanations=[e.get("description", "") for e in data.get("explanations", [])],
                    frac_nonzero=data.get("frac_nonzero"),
                    max_act=data.get("maxActApprox"),
                    pos_str=data.get("pos_str", [])[:5])
                path.write_text(json.dumps(keep), encoding="utf-8")
                return key, keep
            except Exception:
                time.sleep(1.5 * (attempt + 1))
        return key, None

    out = {}
    with ThreadPoolExecutor(workers) as pool:
        for key, val in pool.map(one, sorted(keys)):
            if val is not None:
                out[key] = val
    return out


def run_dir(profile, slug):
    return CACHE / "runs" / profile.runs_subdir / slug if profile.runs_subdir else CACHE / "runs" / slug


def run_prompt(profile, model, saes, message, args, device):
    slug = args.slug or slugify(message)
    out_dir = run_dir(profile, slug)
    out_dir.mkdir(parents=True, exist_ok=True)
    chat = bool(args.chat)
    if chat and not profile.chat_template:
        raise SystemExit(f"{profile.display} has no chat format; drop --chat")
    prompt = profile.chat_template.format(message=message) if chat else message
    tokens = model.to_tokens(prompt)                         # BOS prepended
    str_toks = str_tokens(model, prompt)
    t_len = tokens.shape[1]
    print(f"prompt: {prompt!r} -> {t_len} tokens (incl. BOS)")

    acts, logits, fidelity = feature_acts(profile, model, saes, tokens)
    probs = logits.float().softmax(-1)
    preds = []
    for t in range(t_len):
        top = probs[t].topk(5)
        preds.append([(model.to_string(int(i)), float(p))
                      for p, i in zip(top.values.tolist(), top.indices.tolist())])

    t0 = time.time()
    edges = attribution_edges(profile, model, saes, tokens, acts, args.targets_per_token,
                              args.sources_per_target, args.min_share)
    print(f"attribution: {len(edges)} edges ({time.time() - t0:.1f}s)")
    n_layers = profile.n_layers

    # Displayed features: top-k per (layer, token) plus every edge endpoint.
    shown = set()
    for layer in range(n_layers):
        for t in range(1, t_len):
            top = acts[layer][t].topk(args.display_per_token)
            shown.update((layer, j) for v, j in zip(top.values.tolist(), top.indices.tolist()) if v > 0)
    for e in edges:
        shown.add((e["src_layer"], e["src_feature"]))
        if e["dst_kind"] == "feat":
            shown.add((e["dst_layer"], e["dst_index"]))
    heads = head_dla = head_bos = None
    if profile.show_heads and not args.no_heads:
        heads, head_dla, head_bos = head_effects(
            profile, model, tokens, [int(probs[t].argmax()) for t in range(t_len)],
            args.heads_per_token, args.head_min_attn, args.sources_per_head)

    contrast = None
    if args.contrast:
        contrast = contrast_features(profile, model, saes, tokens, acts, args.contrast, chat,
                                     args.contrast_per_token)
        shown.update((c["layer"], c["feature"]) for c in contrast["features"])
    shown = sorted(shown)
    act_matrix = np.stack([acts[l][:, j].float().cpu().numpy() for l, j in shown])  # [F, T]
    layer_totals = np.stack([acts[l].float().sum(1).cpu().numpy() for l in range(n_layers)])
    layer_l0 = np.stack([(acts[l] > 0).sum(1).cpu().numpy() for l in range(n_layers)])
    # per-layer activation scale over the prompt (BOS excluded), for normalizing
    layer_p99 = [float(np.percentile(acts[l][1:].float().cpu().numpy()[acts[l][1:].float().cpu().numpy() > 0], 99))
                 if (acts[l][1:] > 0).any() else 1.0 for l in range(n_layers)]

    # Labels normally come from Neuronpedia's bulk export (build_scene.py reads
    # cache/neuronpedia_exports/ for every feature); the per-feature API adds
    # activation density and top tokens for the displayed ones, on request.
    explanations = {}
    if args.neuronpedia_api:
        t0 = time.time()
        cache_dir = CACHE / "neuronpedia" / profile.runs_subdir if profile.runs_subdir else CACHE / "neuronpedia"
        ex = fetch_explanations(profile, set(shown), cache_dir)
        explanations = {f"{l}_{j}": v for (l, j), v in ex.items()}
        print(f"neuronpedia: {len(explanations)}/{len(shown)} explanations ({time.time() - t0:.1f}s)")

    w_u = unembed(model, profile)
    promotes = {}
    for l, j in shown:
        d = torch.nn.functional.normalize(saes[l].W_dec[j].detach().float(), dim=0)
        promotes[f"{l}_{j}"] = [model.to_string(int(i)) for i in (d @ w_u).topk(3).indices.tolist()]

    extra = {} if head_dla is None else dict(head_dla=head_dla, head_bos=head_bos)
    np.savez_compressed(out_dir / "acts.npz", act_matrix=act_matrix,
                        shown=np.array(shown, dtype=np.int32),
                        layer_totals=layer_totals, layer_l0=layer_l0, fidelity=fidelity,
                        **extra)
    fid = fidelity[:, 1:]
    print("lens fidelity by layer (mean over tokens, BOS excluded): "
          + " ".join(f"{v:.2f}" for v in fid.mean(1)))
    run = dict(prompt=prompt, slug=slug, model=profile.key, sae_release=profile.sae_release,
               chat=chat, message=message, contrast=contrast, heads=heads,
               str_tokens=str_toks, predictions=preds, edges=edges,
               layer_p99=layer_p99, explanations=explanations, promotes=promotes,
               settings=dict(display_per_token=args.display_per_token,
                             targets_per_token=args.targets_per_token,
                             sources_per_target=args.sources_per_target,
                             min_share=args.min_share))
    (out_dir / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"run written: {out_dir} ({len(shown)} displayed features)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("prompt", nargs="?", default="When Mary and John went to the store, John gave a drink to")
    ap.add_argument("--model", default="gpt2-small", choices=sorted(profiles.PROFILES))
    ap.add_argument("--chat", action="store_true",
                    help="wrap the prompt as a user chat turn, so the scene ends where the model "
                         "starts its answer (instruction-tuned models only)")
    ap.add_argument("--contrast", default=None, metavar="PROMPT",
                    help="a control prompt ending in the same tokens (e.g. a harmless twin of a "
                         "harmful request); on those shared tokens the scene pins the features "
                         "that differ most from it")
    ap.add_argument("--contrast-per-token", type=int, default=3)
    ap.add_argument("--no-heads", action="store_true",
                    help="skip attention heads even when the profile draws them")
    ap.add_argument("--heads-per-token", type=int, default=6,
                    help="heads per token that get attention links (by |effect on the prediction|)")
    ap.add_argument("--sources-per-head", type=int, default=2)
    ap.add_argument("--head-min-attn", type=float, default=0.08,
                    help="drop an attention link below this weight")
    ap.add_argument("--slug", default=None)
    ap.add_argument("--clusters", type=int, default=64)
    ap.add_argument("--rebuild-atlas", action="store_true")
    ap.add_argument("--display-per-token", type=int, default=8)
    ap.add_argument("--targets-per-token", type=int, default=6)
    ap.add_argument("--sources-per-target", type=int, default=3)
    ap.add_argument("--min-share", type=float, default=0.05,
                    help="drop an edge carrying less than this share of its target's attribution")
    ap.add_argument("--neuronpedia-api", action="store_true",
                    help="also query the per-feature API for the displayed features (cached)")
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args()

    device = "cpu" if args.cpu or not torch.cuda.is_available() else "cuda"
    torch.set_grad_enabled(True)
    CACHE.mkdir(exist_ok=True)
    profile = profiles.get(args.model)
    print(f"device: {device}, model: {profile.display}")
    model = load_model(profile, device)
    saes, densities = load_saes(profile, device, sae_dtype(model))

    atlas_path = CACHE / f"atlas_{profile.atlas_name}.npz"
    if args.rebuild_atlas or not atlas_path.exists():
        with torch.no_grad():
            build_atlas(profile, saes, densities, model, args.clusters, atlas_path, device)
        vocab = [model.to_string(i) for i in range(model.cfg.d_vocab)]
        (CACHE / profile.vocab_name).write_text(json.dumps(vocab, ensure_ascii=False), encoding="utf-8")

    run_prompt(profile, model, saes, args.prompt, args, device)


if __name__ == "__main__":
    main()
