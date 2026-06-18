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


def load_ch_map(path: Path) -> dict[int, list[tuple[int, str]]]:
    """Parse np_ch-map.csv.  Returns {channel_id: [(track_id, attribute), ...]}."""
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


def load_ch_tracks(path: Path) -> tuple[np.ndarray, dict[int, int]]:
    """Parse np_ch-tracks.csv.

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
