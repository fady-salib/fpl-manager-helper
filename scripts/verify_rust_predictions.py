"""Verify native inference against the fitted Python artifact on real cached histories."""

import argparse
import json
import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from fpl_ai.features.history import histories_from_store
from fpl_ai.ml.data import FEATURES, STATS, features
from fpl_ai.ml.registry import model_path
from fpl_ai.ml.training import load, predict_rows
from fpl_ai.storage import SnapshotStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", default="rust/target/release/fpl-manager")
    args = parser.parse_args()
    store = SnapshotStore()
    bootstrap = store.latest("bootstrap-static/")[1]
    histories = histories_from_store(store, bootstrap)
    now = pd.Timestamp.now(tz="UTC")
    first = next(e["id"] for e in bootstrap["events"] if pd.Timestamp(e["deadline_time"]) > now)
    rows = []
    for _, group in histories.groupby("player_id"):
        past = (
            group[(group["round"] < first) & (group.kickoff_time + pd.Timedelta(hours=3) < now)]
            .sort_values("kickoff_time")
            .copy()
        )
        for stat in STATS:
            if stat not in past:
                past[stat] = np.nan
        rows.append(features(past))
    frame = pd.DataFrame(rows, columns=FEATURES)
    expected = predict_rows(load(model_path()), frame)
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "features.json"
        # Preserve full IEEE precision; pandas.to_json's default precision can move
        # observations to the other side of a fitted tree's threshold.
        source.write_text(
            json.dumps(
                [[float(v) if math.isfinite(v) else None for v in row] for row in frame.to_numpy()]
            ),
            encoding="utf-8",
        )
        actual = json.loads(
            subprocess.check_output([args.binary, "--predict-features", str(source)], text=True)
        )
    columns = {
        "expected_points": "total_points",
        "expected_minutes": "minutes",
        "p_starts": "starts",
        "p_goals_scored": "goals_scored",
        "p_assists": "assists",
        "p_clean_sheets": "clean_sheets",
    }
    errors = {
        key: float(np.max(np.abs(expected[key].to_numpy() - [r[target] for r in actual])))
        for key, target in columns.items()
    }
    assert all(v < 1e-8 for v in errors.values()), errors
    report = {
        "real_players": len(rows),
        "max_absolute_errors": errors,
        "tolerance": 1e-8,
        "model": str(model_path()),
        "note": "Same fitted artifact, not a new evaluation run.",
    }
    Path("reports/rust-prediction-parity.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
