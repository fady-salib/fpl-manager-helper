"""Lag-only outcome features, frozen for all fixtures in the same gameweek."""

from __future__ import annotations

import numpy as np
import pandas as pd

from fpl_ai.storage import SnapshotStore

STATS = (
    "total_points",
    "minutes",
    "expected_goals",
    "expected_assists",
    "goals_scored",
    "assists",
    "bonus",
    "saves",
    "goals_conceded",
    "starts",
    "ict_index",
)
FEATURES = [f"{stat}_{window}" for window in (3, 5, 10) for stat in STATS] + [
    "points_std_5",
    "samples",
    "rest_days",
]


def histories_from_store(
    store: SnapshotStore, bootstrap: dict, before: object = None
) -> pd.DataFrame:
    rows = []
    snapshots = store.latest_many(
        [f"element-summary/{player['id']}/" for player in bootstrap["elements"]], before=before
    )
    for player in bootstrap["elements"]:
        cached = snapshots.get(f"element-summary/{player['id']}/")
        if cached:
            rows.extend({**row, "player_id": player["id"]} for row in cached[1]["history"])
    frame = pd.DataFrame(rows)
    if not frame.empty:
        for col in STATS:
            frame[col] = pd.to_numeric(frame.get(col, np.nan), errors="coerce")
        frame["kickoff_time"] = pd.to_datetime(frame["kickoff_time"], utc=True, errors="coerce")
        frame["round"] = pd.to_numeric(frame["round"], errors="raise").astype(int)
        frame = frame.sort_values(["player_id", "round", "kickoff_time", "fixture"])
        if frame.duplicated(["player_id", "fixture"]).any():
            raise ValueError("Duplicate player/fixture observations")
    return frame


def lag_features(history: pd.DataFrame, event: int, deadline: pd.Timestamp) -> dict[str, float]:
    """Three-hour conservative completion proxy; no current-round outcomes allowed.

    This cannot guarantee availability of later official stat corrections. Archived
    deadline snapshots are required for strict point-in-time evaluation.
    """
    if history.empty:
        return {k: (0.0 if k == "samples" else np.nan) for k in FEATURES}
    past = history[
        (history["round"] < event)
        & (
            history["kickoff_time"].notna()
            & (
                (
                    history["kickoff_time"].astype("datetime64[ns, UTC]").astype("int64")
                    + 10_800_000_000_000
                )
                < deadline.value
            )
        )
    ]
    out = {}
    for window in (3, 5, 10):
        block = past[past["round"] >= event - window]
        for stat in STATS:
            values = pd.to_numeric(block.get(stat, pd.Series(dtype=float)), errors="coerce")
            out[f"{stat}_{window}"] = float(values.mean()) if len(values) else np.nan
    block = past[past["round"] >= event - 5]
    out["points_std_5"] = float(block["total_points"].std(ddof=0)) if len(block) else np.nan
    out["samples"] = float(len(past))
    out["rest_days"] = (
        float((deadline - past["kickoff_time"].max()).total_seconds() / 86400)
        if len(past)
        else np.nan
    )
    return out


def training_frame(histories: pd.DataFrame, bootstrap: dict) -> pd.DataFrame:
    """One row per fixture; no snapshot prices, ownership, injuries, or strengths."""
    deadlines = {e["id"]: pd.Timestamp(e["deadline_time"]) for e in bootstrap["events"]}
    completed = {e["id"] for e in bootstrap["events"] if e.get("data_checked")}
    rows = []
    if histories.empty:
        raise ValueError("No histories; run refresh --histories first")
    for pid, history in histories.groupby("player_id"):
        for event, targets in history.groupby("round"):
            if event not in completed or event not in deadlines:
                continue
            features = lag_features(history, int(event), deadlines[event])
            if features["samples"] == 0:
                continue
            for target in targets.to_dict("records"):
                rows.append(
                    {
                        "player_id": pid,
                        "event": int(event),
                        "fixture": target["fixture"],
                        "target": target["total_points"],
                        **features,
                    }
                )
    return pd.DataFrame(rows)
