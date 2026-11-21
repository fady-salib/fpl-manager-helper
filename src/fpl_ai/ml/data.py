"""Cached public datasets and lag-only features; historical blanks are absent."""

from __future__ import annotations

import io
import re
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

STATS = [
    "total_points",
    "minutes",
    "goals_scored",
    "assists",
    "clean_sheets",
    "bonus",
    "expected_goals",
    "expected_assists",
    "starts",
]
FEATURES = [f"{s}_{w}" for w in (3, 5, 10) for s in STATS] + ["total_points_avg", "minutes_avg"]


def validate(frame):
    required = {"season", "element", "round", "fixture", "kickoff_time", "total_points", "minutes"}
    if not required <= set(frame):
        raise ValueError(f"Missing columns: {required - set(frame)}")
    if frame.empty or frame.duplicated(["season", "element", "fixture"]).any():
        raise ValueError("Empty data or duplicate player fixtures")
    frame = frame.copy()
    if (
        frame.season.isna().any()
        or not frame.season.astype(str).str.fullmatch(r"20\d{2}-\d{2}").all()
    ):
        raise ValueError("Invalid season identifiers")
    for col in ["element", "round", "fixture", *STATS]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce") if col in frame else np.nan
    required_numbers = frame[["element", "round", "fixture", "total_points", "minutes"]]
    if not np.isfinite(required_numbers.to_numpy(float)).all():
        raise ValueError("Invalid identities or required targets")
    if not frame.minutes.between(0, 120).all():
        raise ValueError("Invalid minutes")
    for col in ["element", "round", "fixture"]:
        if not ((frame[col] >= 1) & (frame[col] == np.floor(frame[col]))).all():
            raise ValueError(f"Invalid integer {col}")
    frame["kickoff_time"] = pd.to_datetime(frame.kickoff_time, utc=True, errors="raise")
    if frame.kickoff_time.isna().any() or not frame["round"].between(1, 60).all():
        raise ValueError("Invalid kickoff/gameweek")
    for col in STATS:
        if np.isinf(frame[col].to_numpy(float)).any():
            raise ValueError(f"Infinite optional statistic: {col}")
    return frame.sort_values(["season", "element", "round", "kickoff_time", "fixture"])


def features(past):
    values = past[STATS].to_numpy(dtype=float)
    result = {}
    for window in (3, 5, 10):
        block = values[-window:]
        counts = np.isfinite(block).sum(axis=0)
        means = np.divide(
            np.nansum(block, axis=0), counts, out=np.full(len(STATS), np.nan), where=counts > 0
        )
        result.update({f"{stat}_{window}": float(means[j]) for j, stat in enumerate(STATS)})
    for stat in ("total_points", "minutes"):
        column = values[:, STATS.index(stat)]
        result[f"{stat}_avg"] = float(np.nanmean(column)) if np.isfinite(column).any() else np.nan
    return result


def prepare(raw):
    if "position" in raw:
        # The 2024/25 archive also contains assistant managers, not player targets.
        raw = raw[
            raw.position.isna() | raw.position.isin(["GK", "GKP", "DEF", "MID", "FWD", 1, 2, 3, 4])
        ]
    frame = validate(raw)
    rows = []
    # Historical deadlines are not in merged_gw.csv. Use a conservative proxy,
    # exclude the entire target round, and disclose retrospective stat corrections.
    cutoffs = frame.groupby(["season", "round"]).kickoff_time.min() - pd.Timedelta(hours=24)
    for (season, _pid), history in frame.groupby(["season", "element"]):
        history = history.sort_values("kickoff_time")
        for event, group in history.groupby("round"):
            cutoff = cutoffs.loc[(season, event)]
            past = history[
                (history["round"] < event) & (history.kickoff_time + pd.Timedelta(hours=3) < cutoff)
            ]
            if past.empty:
                continue
            for row in group.to_dict("records"):
                rows.append({**row, **features(past), "cutoff": cutoff})
    if not rows:
        raise ValueError("No usable lagged observations")
    return pd.DataFrame(rows)


def download(seasons, root="data", refresh=False, log=print):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    with httpx.Client(timeout=90, follow_redirects=True) as client:
        for season in seasons:
            if not re.fullmatch(r"20\d{2}-\d{2}", season):
                raise ValueError("Season must look like 2024-25")
            path = root / f"history-{season}.csv"
            if path.exists() and not refresh:
                validate(pd.read_csv(path))
                paths.append(path)
                continue
            url = f"https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/{season}/gws/merged_gw.csv"
            for attempt in range(4):
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    frame = pd.read_csv(io.StringIO(response.text))
                    frame["season"] = season
                    validate(frame)
                    if path.exists():
                        path = root / f"history-{season}-{time.time_ns()}.csv"
                    frame.to_csv(path, index=False)
                    log(f"Saved {len(frame)} real observations: {path}")
                    paths.append(path)
                    break
                except httpx.HTTPError:
                    if attempt == 3:
                        raise
                    time.sleep(2**attempt)
    return paths


def dataset_paths(seasons, root="data"):
    paths = []
    for season in seasons:
        if not re.fullmatch(r"20\d{2}-\d{2}", season):
            raise ValueError("Season must look like 2024-25")
        candidates = list(Path(root).glob(f"history-{season}*.csv"))
        if not candidates:
            raise ValueError(f"No downloaded data for {season}")
        paths.append(max(candidates, key=lambda p: p.stat().st_mtime_ns))
    return paths


def export_current(store, bootstrap, root="data"):
    """Version completed current-season fixtures for explicit retraining."""
    from fpl_ai.features.history import histories_from_store

    history = histories_from_store(store, bootstrap)
    completed = {e["id"] for e in bootstrap["events"] if e.get("data_checked")}
    if history.empty or not completed:
        return None
    history = history[history["round"].isin(completed)].copy()
    if history.empty:
        return None
    url = bootstrap["game_config"]["settings"]["static_content_url"]
    match = re.search(r"(20\d{2})_(\d{2})/?$", url)
    if not match:
        raise ValueError("Cannot determine current season")
    history["season"] = f"{match[1]}-{match[2]}"
    history["element"] = history.player_id
    positions = {p["id"]: p["element_type"] for p in bootstrap["elements"]}
    history["position"] = history.element.map(positions).map(
        {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    )
    validate(history)
    path = Path(root) / f"current-{time.time_ns()}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(path, index=False)
    return path


def with_current(paths, root="data"):
    current = list(Path(root).glob("current-*.csv"))
    if not current:
        return paths
    path = max(current, key=lambda p: p.stat().st_mtime_ns)
    seasons = set(pd.read_csv(path, usecols=["season"]).season)
    selected = {s for p in paths for s in pd.read_csv(p, usecols=["season"]).season.unique()}
    return list(paths) + ([path] if not seasons & selected else [])
