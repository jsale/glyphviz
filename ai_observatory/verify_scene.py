"""AI Observatory: check a generated scene through GlyphViz's own loaders.

Runs in the `glyphviz` env. Loads the node CSV with load_node_csv, resolves
every parent and link end, runs the Channels three-way join through the real
ChannelEngine, steps a few frames, and confirms the audio manifest resolves.
Exit code 1 on any failure.
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from glyphviz_core.csv_reader import load_node_csv                      # noqa: E402
from glyphviz_core.channel_loader import (                             # noqa: E402
    find_audio_file, find_channel_files, load_ch_map, load_ch_tracks)
from glyphviz_core.channel_engine import ChannelEngine, channel_id_of  # noqa: E402


def main(node_csv):
    failures = []
    t0 = time.time()
    nodes = load_node_csv(node_csv)
    print(f"loaded {len(nodes):,} nodes in {time.time() - t0:.1f}s")
    by_id = {n.id: n for n in nodes}
    print("types:", dict(Counter(n.type for n in nodes)))

    orphans = [n.id for n in nodes if n.parent_id and n.parent_id not in by_id]
    if orphans:
        failures.append(f"{len(orphans)} nodes with unresolved parent_id (first {orphans[:5]})")
    links = [n for n in nodes if n.type == 7]
    dangling = [n.id for n in links
                if int(float(n.extras.get("child_id", 0) or 0)) not in by_id or n.parent_id not in by_id]
    if dangling:
        failures.append(f"{len(dangling)} one-ended links (first {dangling[:5]})")
    unlabeled = [n.id for n in nodes if n.type != 0 and not n.text]
    if unlabeled:
        failures.append(f"{len(unlabeled)} nodes without text (first {unlabeled[:5]})")
    pinned = sum(1 for n in nodes if n.show_text)
    print(f"links: {len(links):,}   pinned labels in the static view: {pinned}")

    map_path, tracks_path = find_channel_files(node_csv)
    if not (map_path and tracks_path):
        failures.append("channel pair not discovered")
    else:
        ch_map = load_ch_map(map_path)
        tracks, id_to_col = load_ch_tracks(tracks_path)
        engine = ChannelEngine()
        engine.load(ch_map, tracks, id_to_col, nodes)
        bound = [n for n in nodes if channel_id_of(n)]
        missing = sorted({channel_id_of(n) for n in bound} - set(ch_map))
        if missing:
            failures.append(f"{len(missing)} ch_input_ids with no ch-map channel")
        bad_tracks = sorted({tr for rows in ch_map.values() for tr, _a in rows} - set(id_to_col))
        if bad_tracks:
            failures.append(f"{len(bad_tracks)} ch-map track ids with no ch<id> column")
        print(f"channels: {len(ch_map)} channels, {tracks.shape[1]} tracks, "
              f"{engine.frame_count} frames, {len(bound):,} bound nodes, "
              f"has_bindings={engine.has_bindings}")
        t1 = time.time()
        for f in (0, engine.frame_count // 2, engine.frame_count - 1):
            engine.apply_frame(f)
        print(f"applied 3 frames in {(time.time() - t1) * 1000:.0f} ms")
        engine.reset()

    audio = find_audio_file(node_csv)
    print(f"audio: {audio}")
    if audio is None or not Path(audio).exists():
        failures.append("audio manifest missing or unresolved")

    if failures:
        print("FAIL:\n  " + "\n  ".join(failures))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
