"""Honest component vs direct comparison on the same held-out fixture rows."""

from __future__ import annotations

import numpy as np
import pandas as pd

from fpl_ai.forecasting.components import simulate_player
from fpl_ai.models.evaluate import chronological_blocks, metrics
from fpl_ai.rules import Rules


def evaluate_components(
    histories: pd.DataFrame,
    frame: pd.DataFrame,
    bootstrap: dict,
    samples: int = 1000,
    seed: int = 42,
) -> dict:
    test = chronological_blocks(frame)[-1]
    deadlines = {e["id"]: pd.Timestamp(e["deadline_time"]) for e in bootstrap["events"]}
    positions = {p["id"]: p["element_type"] for p in bootstrap["elements"]}
    names = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
    rules = Rules.from_bootstrap(bootstrap)
    predictions, low, high = [], [], []
    for row in test.itertuples():
        h = histories[
            (histories.player_id == row.player_id)
            & (histories["round"] < row.event)
            & (histories.kickoff_time < deadlines[row.event] - pd.Timedelta(hours=3))
        ]
        result = simulate_player(
            h,
            names[positions[row.player_id]],
            rules,
            samples=samples,
            seed=seed + int(row.player_id),
        )
        predictions.append(result["mean"])
        low.append(result["p10"])
        high.append(result["p90"])
    pred = np.array(predictions)
    actual = test.target.to_numpy()
    report = {
        "events": sorted(map(int, test.event.unique())),
        "rows": len(test),
        "samples_per_player_fixture": samples,
        "seed": seed,
        "metrics": metrics(actual, pred, test.event.to_numpy()),
        "p10_p90_coverage": float(((actual >= low) & (actual <= high)).mean()),
        "limitations": [
            "Uncalibrated empirical-event model",
            "Position uses current-season roster mapping",
            "No deadline snapshot archive",
            "Independent player/opponent event approximation",
        ],
    }
    by_position = {}
    for position in names:
        mask = test.player_id.map(positions).to_numpy() == position
        if mask.any():
            by_position[names[position]] = metrics(
                actual[mask], pred[mask], test.event.to_numpy()[mask]
            )
    report["by_position"] = by_position
    return report
