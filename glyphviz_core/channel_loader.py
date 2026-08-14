from pathlib import Path

import numpy as np
import pandas as pd


def find_channel_files(node_csv_path: str) -> tuple[Path | None, Path | None]:
    """Return (ch_map_path, ch_tracks_path) companions for a node CSV, or (None, None)."""
    d = Path(node_csv_path).parent
    map_files = [p for p in d.iterdir() if 'ch-map' in p.name and p.suffix == '.csv']
    track_files = [p for p in d.iterdir() if 'ch-track' in p.name and p.suffix == '.csv']
    map_path = map_files[0] if len(map_files) == 1 else None
    track_path = track_files[0] if len(track_files) == 1 else None
    return map_path, track_path


def find_audio_file(node_csv_path: str) -> Path | None:
    """Return the WAV/audio file a node CSV's Channels were derived from, if any.

    Convention: a one-line manifest named "*_gv_audio.txt" sits next to the
    node CSV, containing a path (relative to the node CSV's folder) to the
    source audio file — see examples/Audio_Animation_Example/
    generate_audio_example.py. This lets Channels playback play that file in
    sync, without guessing among unrelated WAVs that might also be sitting in
    the same media/ folder (e.g. alternate takes used to build other examples).
    """
    d = Path(node_csv_path).parent
    manifests = [p for p in d.iterdir() if p.name.endswith('_gv_audio.txt')]
    if len(manifests) != 1:
        return None
    rel = manifests[0].read_text(encoding='utf-8').strip()
    if not rel:
        return None
    # resolve() before the existence check: a rel path with many ".."
    # segments can push the unresolved string past Windows' MAX_PATH limit,
    # making is_file() report False for a file that exists.
    audio_path = (d / rel).resolve()
    return audio_path if audio_path.is_file() else None


def load_ch_map(path: Path) -> dict[int, list[tuple[int, str]]]:
    """Parse a ch-map.csv (gv_ch-map.csv or np_ch-map.csv).

    Returns {channel_id: [(track_id, attribute), ...]}.
    """
    df = pd.read_csv(path)
    ch_map: dict[int, list[tuple[int, str]]] = {}
    for _, row in df.iterrows():
        try:
            cid = int(row['channel_id'])
            tid = int(row['track_id'])
            attr = str(row['attribute'])
            ch_map.setdefault(cid, []).append((tid, attr))
        except (KeyError, ValueError):
            continue
    return ch_map


def export_channel_subset(map_path: Path, tracks_path: Path,
                          channel_ids: set[int],
                          out_map: Path, out_tracks: Path) -> tuple[int, int]:
    """Write the ch-map/ch-tracks pair covering `channel_ids` only.

    For Save Selection As… (see selection_export): a fragment of an animated
    scene keeps its animation only if the channel files travel with it, and
    copying them whole would drag along tracks for thousands of nodes that
    didn't come.

    Filtering happens at the FILE level rather than through load_ch_map/
    load_ch_tracks, so any column those parsers ignore still round-trips.
    Channel and track ids keep their original values, matching the node
    export's preserved node ids — nothing is renumbered, so a `chN` column
    still means track N.

    Returns (channels_written, tracks_written); (0, 0) writes nothing at all,
    since a ch-map with no rows would still be found by find_channel_files
    and would shadow the real one if both sat in a folder together.
    """
    ch_map = pd.read_csv(map_path)
    kept_map = ch_map[ch_map['channel_id'].isin(channel_ids)]
    track_ids = {int(t) for t in kept_map['track_id']}
    if kept_map.empty or not track_ids:
        return (0, 0)

    tracks = pd.read_csv(tracks_path)
    # Everything that isn't a chN track column (cyclecount, timestamps, …)
    # is scene-level and stays.
    keep_cols = [
        col for col in tracks.columns
        if not (col.startswith('ch') and col[2:].isdigit())
        or int(col[2:]) in track_ids
    ]
    kept_map.to_csv(out_map, index=False)
    tracks[keep_cols].to_csv(out_tracks, index=False)
    return (int(kept_map['channel_id'].nunique()), len(track_ids))


def load_ch_tracks(path: Path) -> tuple[np.ndarray, dict[int, int]]:
    """Parse a ch-tracks.csv (gv_ch-tracks.csv or np_ch-tracks.csv).

    Returns:
        tracks  — float64 array of shape (num_frames, num_tracks)
        id_to_col — dict mapping track_id (int) to column index in tracks
    """
    df = pd.read_csv(path)
    track_cols: list[tuple[int, str]] = []
    for col in df.columns:
        if col.startswith('ch') and col[2:].isdigit():
            track_cols.append((int(col[2:]), col))
    track_cols.sort(key=lambda x: x[0])
    track_ids = [t for t, _ in track_cols]
    col_names = [c for _, c in track_cols]
    tracks = df[col_names].values.astype(np.float64)
    id_to_col = {tid: i for i, tid in enumerate(track_ids)}
    return tracks, id_to_col
