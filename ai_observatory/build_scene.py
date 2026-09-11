"""AI Observatory, stage B: turn an extracted GPT-2 run into a GlyphViz scene.

Runs in the ordinary `glyphviz` env (numpy + pandas only; no torch). Reads
cache/atlas_*.npz, cache/runs/<slug>/, and cache/neuronpedia_exports/, and
writes a self-contained scene folder: node CSV, Channels pair, sonified audio
with its manifest, and a README.

Layout (world units, Global Scale 1):
  * a vertical spine = the residual stream; one ring per layer, layer 0 at the
    bottom, prediction at the top
  * every SAE feature of a layer is a point in that layer's cloud, at its
    atlas home position -- the same place in every prompt's scene
  * features active on this prompt are promoted to glyphs at the same spot
  * attribution edges are cylinder links; the prompt runs along the front
  * Channels time = reading the prompt token by token: for each token a pulse
    climbs the tower (layer 0 .. 11), then the prediction lights up
The static scene (Channels stopped) shows the LAST token -- the answer.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import wave
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
RELEASE = "gpt2-small-res-jb"
N_LAYERS = 12

GEO_CUBE, GEO_SPHERE, GEO_TORUS = 1, 3, 7
GEO_TETRA, GEO_ICOSA, GEO_CYLINDER, GEO_POINT = 13, 15, 19, 22
TOPO_NONE, TOPO_PLOT, TOPO_CLOUD = 0, 16, 18
# Reading a feature's decoder direction straight through the unembedding
# ("promotes 'Mary'") only means something near the output; in early layers it
# returns junk tokens ('asty', 'ggles'), so labels carry it from here up only.
PROMOTE_FROM_LAYER = 8

_STOP = set("""
a an the of to in on for and or with that this from into which these those such other
word words token tokens text references reference related relating phrase phrases
instances instance mentions mention terms term context contexts specific various
including particularly often within their about being after before when where there
they them have has sentence sentences letter letters part parts first last end
beginning containing involving indicating discussing used use like following
particular different common typically usually especially possibly potentially
seems appears certain characters character string strings pattern patterns
""".split())


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def hsv_to_rgb(h, s, v):
    h = np.mod(np.asarray(h, dtype=np.float64), 1.0)
    s = np.broadcast_to(np.asarray(s, dtype=np.float64), h.shape)
    v = np.broadcast_to(np.asarray(v, dtype=np.float64), h.shape)
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return (np.stack([r, g, b], -1) * 255).round().astype(int)


_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def clean(text, limit=140):
    text = _CTRL.sub(" ", str(text)).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def show_token(tok):
    t = tok.replace("\n", "⏎")
    return t.strip() if t.strip() else ("␣" if t else "∅")


def load_explanations():
    out = {}
    folder = CACHE / "neuronpedia_exports"
    for layer in range(N_LAYERS):
        path = folder / f"gpt2-small_{layer}-res-jb.json"
        if not path.exists():
            continue
        for rec in json.loads(path.read_text(encoding="utf-8")):
            key = (layer, int(rec["index"]))
            desc = clean(rec.get("description") or "")
            if desc and key not in out:
                out[key] = desc
    return out


def themes(descriptions, n=3):
    counts = Counter()
    for d in descriptions:
        words = set(w for w in re.findall(r"[a-z]{4,}", d.lower()) if w not in _STOP)
        counts.update(words)
    return [w for w, _ in counts.most_common(n)]


class Rows:
    """Accumulates node rows; ids are handed out in creation order."""

    def __init__(self):
        self.rows = []
        self.next_id = 1

    def add(self, **kw):
        row = dict(id=self.next_id, type=5, parent_id=0, branch_level=0,
                   translate_x=0.0, translate_y=0.0, translate_z=0.0,
                   rotate_x=0.0, rotate_y=0.0, rotate_z=0.0,
                   scale_x=1.0, scale_y=1.0, scale_z=1.0,
                   color_r=200, color_g=200, color_b=200, color_a=255,
                   geometry=GEO_SPHERE, hide=0, topo=TOPO_NONE, ratio=0.1,
                   text="", show_text=0, child_id=0, ch_input_id=0)
        scale = kw.pop("scale", None)
        if scale is not None:
            if np.isscalar(scale):
                scale = (scale, scale, scale)
            row["scale_x"], row["scale_y"], row["scale_z"] = scale
        pos = kw.pop("pos", None)
        if pos is not None:
            row["translate_x"], row["translate_y"], row["translate_z"] = pos
        rgba = kw.pop("rgba", None)
        if rgba is not None:
            row["color_r"], row["color_g"], row["color_b"], row["color_a"] = [int(c) for c in rgba]
        row.update(kw)
        self.rows.append(row)
        self.next_id += 1
        return row["id"]


# --------------------------------------------------------------------------
# Channels
# --------------------------------------------------------------------------

class Channels:
    """Dedupes identical tracks and identical (attribute, track) bundles."""

    def __init__(self, frames):
        self.frames = frames
        self.tracks = {}          # bytes -> (track_id, array)
        self.channels = {}        # tuple((attr, track_id)) -> channel_id

    def track(self, values):
        arr = np.round(np.asarray(values, dtype=np.float64), 3)
        assert arr.shape == (self.frames,)
        key = arr.tobytes()
        if key not in self.tracks:
            self.tracks[key] = (len(self.tracks) + 1, arr)
        return self.tracks[key][0]

    def channel(self, bindings):
        key = tuple(sorted((attr, self.track(vals)) for attr, vals in bindings))
        if key not in self.channels:
            self.channels[key] = len(self.channels) + 1
        return self.channels[key]

    def write(self, map_path, tracks_path):
        rows = []
        for key, ch in self.channels.items():
            for attr, tr in key:
                rows.append(dict(id=len(rows) + 1, channel_id=ch, track_id=tr, attribute=attr))
        pd.DataFrame(rows).to_csv(map_path, index=False, lineterminator="\r\n", encoding="utf-8")
        ordered = sorted(self.tracks.values())
        data = {"cyclecount": np.arange(self.frames)}
        for tid, arr in ordered:
            data[f"ch{tid}"] = arr
        pd.DataFrame(data).to_csv(tracks_path, index=False, lineterminator="\r\n",
                                  encoding="utf-8", float_format="%.3g")
        return len(ordered), len(self.channels)


# --------------------------------------------------------------------------
# Sound
# --------------------------------------------------------------------------

def sonify(events, duration, path_wav, sr=44100):
    """events: dicts with time, freq, amp, pan (-1..1), partials, decay."""
    n = int(round(duration * sr))
    out = np.zeros((n, 2), dtype=np.float64)
    for ev in events:
        start = int(ev["time"] * sr)
        length = min(int(ev.get("length", 1.0) * sr), n - start)
        if length <= 0:
            continue
        t = np.arange(length) / sr
        env = np.minimum(t / ev.get("attack", 0.008), 1.0) * np.exp(-t / ev["decay"])
        if ev.get("noise"):
            rng = np.random.default_rng(start)
            sig = rng.standard_normal(length) * np.exp(-t / 0.004)
        else:
            sig = sum(np.sin(2 * math.pi * ev["freq"] * h * t) / h
                      for h in range(1, ev.get("partials", 1) + 1))
        sig = sig * env * ev["amp"]
        pan = ev.get("pan", 0.0)
        out[start:start + length, 0] += sig * math.sqrt((1 - pan) / 2)
        out[start:start + length, 1] += sig * math.sqrt((1 + pan) / 2)
    peak = np.abs(out).max() or 1.0
    pcm = (out / peak * 0.9 * 32767).astype(np.int16)
    with wave.open(str(path_wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# --------------------------------------------------------------------------
# Scene
# --------------------------------------------------------------------------

def build(args):
    run_dir = CACHE / "runs" / args.slug
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    acts = np.load(run_dir / "acts.npz")
    atlas = np.load(CACHE / f"atlas_{RELEASE}.npz")
    vocab = json.loads((CACHE / "gpt2_vocab.json").read_text(encoding="utf-8"))
    expl = load_explanations()
    print(f"explanations loaded for {len(expl)} features")

    k_clusters = int(atlas["k_clusters"])
    R, GAP = args.radius, args.layer_gap
    BAND_H, BAND_R = 2.4, 2.0
    tokens = run["str_tokens"]
    T = len(tokens)
    readable = list(range(1, T))                  # BOS is never shown
    last = readable[-1]
    F = args.frames_per_token
    frames = F * len(readable)
    rise = int(F * 0.62)
    arrive_off = [round(L * rise / (N_LAYERS - 1)) for L in range(N_LAYERS)]
    pred_off = int(F * 0.78)

    def window(t):
        k = t - 1
        return k * F, (k + 1) * F

    shown = [tuple(x) for x in acts["shown"].tolist()]
    act_m = acts["act_matrix"]                   # [F, T]
    layer_l0 = acts["layer_l0"]
    p99 = run["layer_p99"]
    ch = Channels(frames)
    rows = Rows()

    scene_name = args.name
    out_dir = Path(args.out) if args.out else HERE / "scenes" / scene_name
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- World + root -----------------------------------------------------
    rows.add(type=0, geometry=0, rgba=(5, 7, 14, 255), text="World", tag_font_size=12)
    prompt_text = run["prompt"]
    root = rows.add(geometry=GEO_SPHERE, scale=1.6, rgba=(170, 180, 210, 255),
                    text=clean(f"GPT-2 small (124M parameters, 12 layers) reading: \"{prompt_text}\"", 200),
                    show_text=1)
    top_z = GAP * (N_LAYERS + 1)
    rows.add(parent_id=root, branch_level=1, geometry=GEO_CYLINDER,
             pos=(0, 0, top_z / 2), scale=(0.22, 0.22, top_z / 2), rgba=(120, 135, 175, 90),
             text="Residual stream: the running total every layer reads from and writes to")

    # --- Prompt row ---------------------------------------------------------
    # Tag labels are drawn at a fixed pixel size starting just right of their
    # glyph, so evenly spaced tokens let a long word run into the next one
    # ("wereproudto"). Advance each token by the previous label's length.
    token_text = {t: clean(show_token(tokens[t]), 40) for t in readable}
    token_x, x = [], 0.0
    for k, t in enumerate(readable):
        if k:
            x += args.token_gap + args.char_width * len(token_text[readable[k - 1]])
        token_x.append(x)
    x_mid = token_x[-1] / 2
    prompt_node = rows.add(parent_id=root, branch_level=1, geometry=GEO_CUBE, scale=0.6,
                           pos=(0, -(R + 24), 0), topo=TOPO_PLOT, ratio=0.08,
                           rgba=(120, 130, 150, 255),
                           text="The prompt, one glyph per token; the enlarged token is the one being read")
    token_ids = {}
    for k, t in enumerate(readable):
        s0, s1 = window(t)
        vals = np.full(frames, 0.9)
        vals[:s0] = 0.9
        vals[s0:s1] = 2.2
        vals[s1:] = 1.3
        cid = ch.channel([("scale_x", vals), ("scale_y", vals), ("scale_z", vals)])
        token_ids[t] = rows.add(parent_id=prompt_node, branch_level=2, geometry=GEO_CUBE,
                                pos=(round(token_x[k] - x_mid, 3), 0, 0),
                                scale=2.2 if t == last else 1.3, rgba=(235, 235, 245, 255),
                                text=token_text[t], show_text=1,
                                ch_input_id=cid)

    # --- Output: one prediction node per token, shown in its window ----------
    out_hub = rows.add(parent_id=root, branch_level=1, geometry=GEO_SPHERE, scale=1.2,
                       pos=(0, 0, top_z), rgba=(255, 215, 120, 255),
                       text="Output: GPT-2's prediction of the next token")
    pred_ids = {}
    for t in readable:
        s0, s1 = window(t)
        hide = np.ones(frames)
        hide[s0 + pred_off:s1] = 0
        preds = run["predictions"][t]
        so_far = "".join(tokens[1:t + 1])
        guess = " · ".join(f"'{show_token(tok)}' {p:.0%}" for tok, p in preds[:3])
        pred_ids[t] = rows.add(parent_id=out_hub, branch_level=2, geometry=GEO_ICOSA,
                               pos=(0, 0, 5), scale=2.4, rgba=(255, 200, 80, 255),
                               hide=0 if t == last else 1, show_text=1,
                               text=clean(f"After \"…{so_far[-40:]}\" GPT-2 predicts {guess}", 180),
                               ch_input_id=ch.channel([("hide", hide)]))

    # --- Layers ------------------------------------------------------------
    feat_node = {}
    shown_by_layer = defaultdict(list)
    for row_i, (L, j) in enumerate(shown):
        shown_by_layer[L].append((row_i, j))
    cloud_frames = []

    for L in range(N_LAYERS):
        pre = f"L{L}_"
        angle = atlas[pre + "angle"]
        dz, dr = atlas[pre + "dz"], atlas[pre + "dr"]
        cluster = atlas[pre + "cluster"]
        centre = atlas[pre + "cluster_centre"]
        csize = atlas[pre + "cluster_size"]
        ctop = atlas[pre + "cluster_top_tokens"]
        logd = atlas[pre + "log_density"]
        n = angle.shape[0]
        z = GAP * (L + 1)
        shade = 110 + int(100 * L / (N_LAYERS - 1))
        hub = rows.add(parent_id=root, branch_level=1, geometry=GEO_SPHERE, scale=1.1,
                       pos=(0, 0, z), rgba=(shade, shade, 255, 255),
                       text=f"Layer {L}: the residual stream entering block {L}, read through "
                            f"24,576 sparse-autoencoder features in {k_clusters} meaning clusters",
                       show_text=1 if L in (0, N_LAYERS - 1) else 0)
        rows.add(parent_id=hub, branch_level=2, geometry=GEO_TORUS, scale=R, ratio=0.004,
                 rgba=(90, 100, 140, 70), text=f"Layer {L} ring")

        # every feature, as a point at its home position
        cloud = rows.add(parent_id=hub, branch_level=2, geometry=GEO_POINT, topo=TOPO_CLOUD,
                         ratio=args.point_ratio, rgba=(40, 40, 60, 255),
                         text=f"Layer {L} feature cloud: all {n:,} features. Position and color = meaning "
                              f"neighborhood (similar directions sit together, and line up with the layers above and below)")
        r = R + dr * BAND_R
        hue = angle / (2 * math.pi)
        rgb = hsv_to_rgb(hue, 0.55, 0.8)
        if np.any(logd != 0):
            alpha = np.clip(90 + (logd + 5) * 40, 50, 230).round().astype(int)
        else:
            alpha = np.full(n, 150)
        labels = []
        for i in range(n):
            e = expl.get((L, i))
            labels.append(f"L{L} #{i}: {e}" if e else f"L{L} #{i} (no explanation)")
        base = rows.next_id
        cloud_frames.append(pd.DataFrame(dict(
            id=np.arange(base, base + n), type=5, parent_id=cloud, branch_level=3,
            translate_x=np.round(r * np.cos(angle), 3), translate_y=np.round(r * np.sin(angle), 3),
            translate_z=np.round(dz * BAND_H, 3), rotate_x=0, rotate_y=0, rotate_z=0,
            scale_x=1, scale_y=1, scale_z=1, color_r=rgb[:, 0], color_g=rgb[:, 1], color_b=rgb[:, 2],
            color_a=alpha, geometry=GEO_POINT, hide=0, topo=0, ratio=0.1, text=labels,
            show_text=0, child_id=0, ch_input_id=0)))
        rows.next_id += n

        # cluster markers just outside the band
        for c in range(k_clusters):
            members = np.nonzero(cluster == c)[0]
            if members.size == 0:
                continue
            th = [w for w in themes(expl.get((L, int(i)), "") for i in members)]
            promo = ""
            if L >= PROMOTE_FROM_LAYER:
                promo = " · direction promotes " + ", ".join(
                    f"'{show_token(vocab[int(t)])}'" for t in ctop[c][:4])
            crgb = hsv_to_rgb(np.array([centre[c] / (2 * math.pi)]), 0.7, 1.0)[0]
            ro = R + BAND_R + 4
            rows.add(parent_id=hub, branch_level=2, geometry=GEO_TETRA, scale=0.55,
                     pos=(round(ro * math.cos(centre[c]), 3), round(ro * math.sin(centre[c]), 3), 0),
                     rgba=(*crgb, 200),
                     text=clean(f"Layer {L} cluster {c}: {csize[c]:,} features · themes: "
                                f"{', '.join(th) or 'n/a'}{promo}", 200))

        # active features: glyphs animated by the token pulse
        for row_i, j in shown_by_layer[L]:
            a = act_m[row_i]
            norm = np.sqrt(np.clip(a / max(p99[L], 1e-6), 0, 1.6))
            state = np.zeros(T)
            seen = False
            for t in readable:
                if a[t] > 0:
                    state[t] = 0.55 + 1.7 * norm[t]
                    seen = True
                elif seen:
                    state[t] = 0.22
            top1 = {t for t in readable if a[t] > 0 and
                    a[t] >= max(act_m[ri][t] for ri, _ in shown_by_layer[L])}
            scale_track = np.zeros(frames)
            text_track = np.zeros(frames)
            prev = 0.0
            for t in readable:
                s0, s1 = window(t)
                arr = s0 + arrive_off[L]
                scale_track[s0:arr] = prev
                scale_track[arr:s1] = state[t]
                if t in top1:
                    text_track[arr:s1] = 1
                prev = state[t]
            peak_t = int(np.argmax(a[1:]) + 1)
            e = expl.get((L, j), "no explanation")
            promo = ""
            if L >= PROMOTE_FROM_LAYER:
                promo = " · promotes " + ", ".join(
                    f"'{show_token(p)}'" for p in run["promotes"].get(f"{L}_{j}", []))
            rgb1 = hsv_to_rgb(np.array([angle[j] / (2 * math.pi)]), 0.8, 1.0)[0]
            cid = ch.channel([("scale_x", scale_track), ("scale_y", scale_track),
                              ("scale_z", scale_track), ("show_text", text_track)])
            feat_node[(L, j)] = rows.add(
                parent_id=hub, branch_level=2, geometry=GEO_SPHERE,
                pos=(round(float(r[j] * math.cos(angle[j])), 3),
                     round(float(r[j] * math.sin(angle[j])), 3), round(float(dz[j] * BAND_H), 3)),
                scale=float(state[last]), rgba=(*rgb1, 255),
                show_text=1 if last in top1 else 0, ch_input_id=cid,
                text=clean(f"L{L} #{j}: {e}{promo} · peak {a[peak_t]:.1f} on "
                           f"'{show_token(tokens[peak_t])}'", 220))
        print(f"  layer {L}: {n} points, {len(shown_by_layer[L])} active glyphs")

    # --- Attribution edges ---------------------------------------------------
    grouped = defaultdict(list)
    for e in run["edges"]:
        src = feat_node.get((e["src_layer"], e["src_feature"]))
        if e["dst_kind"] == "feat":
            dst = feat_node.get((e["dst_layer"], e["dst_index"]))
        else:
            dst = pred_ids.get(e["token"])
        if src is None or dst is None:
            continue
        grouped[(src, dst)].append(e)
    link_count = 0
    for (src, dst), es in grouped.items():
        hide = np.ones(frames)
        for e in es:
            s0, s1 = window(e["token"])
            start = s0 + (pred_off if e["dst_kind"] == "logit" else arrive_off[e["dst_layer"]])
            hide[start:s1] = 0
        best = max(es, key=lambda e: abs(e["attribution"]))
        at_last = [e for e in es if e["token"] == last]
        sign = best["attribution"] >= 0
        rgba = (255, 175, 70, 210) if sign else (80, 170, 255, 210)
        via = ""
        if best["src_token"] != best["token"]:
            via = f" (reaching back to '{show_token(tokens[best['src_token']])}' through attention)"
        dst_desc = (f"L{best['dst_layer']} #{best['dst_index']}" if best["dst_kind"] == "feat"
                    else f"the prediction '{show_token(vocab[best['dst_index']])}'")
        rows.add(type=7, parent_id=src, child_id=dst, branch_level=3, geometry=GEO_CYLINDER,
                 ratio=round(0.05 + 0.3 * min(1.0, best["share"] * 2), 3), rgba=rgba,
                 hide=0 if at_last else 1, ch_input_id=ch.channel([("hide", hide)]),
                 text=clean(f"L{best['src_layer']} #{best['src_feature']} → {dst_desc}: attribution "
                            f"{best['attribution']:+.2f} ({best['share']:.0%} of the target) at "
                            f"'{show_token(tokens[best['token']])}'{via}; on {len(es)} token(s)", 220))
        link_count += 1
    print(f"  links: {link_count}")

    # --- Write node CSV ------------------------------------------------------
    small = pd.DataFrame(rows.rows)
    frame = pd.concat([small] + cloud_frames, ignore_index=True)
    frame = frame.sort_values("id", kind="stable")
    if "tag_font_size" in frame:
        frame["tag_font_size"] = frame["tag_font_size"].fillna(11).astype(int)
    int_cols = ["id", "type", "parent_id", "branch_level", "color_r", "color_g", "color_b",
                "color_a", "geometry", "hide", "topo", "show_text", "child_id", "ch_input_id"]
    for c in int_cols:
        frame[c] = frame[c].astype(int)
    stem = out_dir / scene_name
    node_path = Path(f"{stem}_gv_node.csv")
    frame.to_csv(node_path, index=False, lineterminator="\r\n", encoding="utf-8", float_format="%.6g")
    n_tracks, n_channels = ch.write(f"{stem}_gv_ch-map.csv", f"{stem}_gv_ch-tracks.csv")
    print(f"nodes: {len(frame):,} -> {node_path.name} ({node_path.stat().st_size / 1e6:.1f} MB)")
    print(f"channels: {n_channels} channels, {n_tracks} tracks, {frames} frames")

    # --- Sound -------------------------------------------------------------
    if not args.no_audio:
        fps = args.fps
        events = []
        energy = {}
        for L in range(N_LAYERS):
            for t in readable:
                tot, sx = 0.0, 0.0
                for row_i, j in shown_by_layer[L]:
                    a = act_m[row_i][t]
                    if a > 0:
                        w = math.sqrt(min(a / max(p99[L], 1e-6), 1.6))
                        tot += w
                        sx += w * math.cos(float(atlas[f"L{L}_angle"][j]))
                energy[(L, t)] = (tot, sx / tot if tot else 0.0)
        emax = max(v[0] for v in energy.values()) or 1.0
        semis = [0, 2, 4, 7, 9]
        for t in readable:
            s0, _s1 = window(t)
            events.append(dict(time=s0 / fps, noise=True, amp=0.35, decay=0.05, length=0.08))
            for L in range(N_LAYERS):
                tot, pan = energy[(L, t)]
                if tot <= 0:
                    continue
                freq = 146.83 * 2 ** ((12 * (L // 5) + semis[L % 5]) / 12)
                l0 = float(layer_l0[L][t])
                events.append(dict(time=(s0 + arrive_off[L]) / fps, freq=freq,
                                   amp=0.25 * math.sqrt(tot / emax),
                                   partials=1 + int(round(4 * min(l0 / 120, 1))),
                                   pan=max(-0.9, min(0.9, pan)), decay=0.3, length=1.1))
            p = run["predictions"][t][0][1]
            for mult, amp in ((1.0, 0.3), (2.76, 0.12)):
                events.append(dict(time=(s0 + pred_off) / fps, freq=880 * mult,
                                   amp=amp * (0.3 + 0.7 * p), decay=0.45, length=1.4))
        wav = Path(f"{stem}.wav")
        sonify(events, frames / fps, wav)
        m4a = Path(f"{stem}.m4a")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "aac",
                        "-b:a", "160k", str(m4a)], check=True)
        wav.unlink()
        Path(f"{stem}_gv_audio.txt").write_text(m4a.name, encoding="utf-8")
        print(f"audio: {m4a.name} ({frames / fps:.1f}s, {m4a.stat().st_size / 1e6:.2f} MB)")

    return out_dir, node_path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("slug")
    ap.add_argument("--name", default="AI_Observatory_GPT2")
    ap.add_argument("--out", default=None)
    ap.add_argument("--radius", type=float, default=60.0)
    ap.add_argument("--layer-gap", type=float, default=14.0)
    ap.add_argument("--token-gap", type=float, default=5.0,
                    help="world units between one token label's end and the next token")
    # Measured off a render: an 11 pt label character is ~8 px, which is
    # distance/109 world units. Labels stay clear out to ~109 x this value,
    # so 6.0 reads from the ~650-unit distance that frames the whole tower.
    ap.add_argument("--char-width", type=float, default=6.0,
                    help="world units per label character; labels stay separate out to ~109x this distance")
    ap.add_argument("--frames-per-token", type=int, default=36)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--point-ratio", type=float, default=0.1)
    ap.add_argument("--no-audio", action="store_true")
    build(ap.parse_args())


if __name__ == "__main__":
    main()
