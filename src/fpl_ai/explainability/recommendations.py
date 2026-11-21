"""Numerical model sensitivity and evidence-based transfer descriptions."""

from __future__ import annotations

import numpy as np
import pandas as pd

from fpl_ai.features.history import FEATURES
from fpl_ai.optimization.squad import Plan


def explain_plan(plan: Plan, rolled: Plan, players: pd.DataFrame, column: str) -> dict:
    p = players.set_index("id")

    def describe(i: int) -> dict:
        return {
            "id": i,
            "name": p.at[i, "name"],
            "next_points": float(p.at[i, column]),
            "horizon_points": float(p.at[i, "horizon_points"]),
            "historical_minutes_per_fixture": None
            if pd.isna(p.at[i, "historical_minutes_per_fixture"])
            else float(p.at[i, "historical_minutes_per_fixture"]),
            "status": p.at[i, "status"],
            "news": p.at[i, "news"],
        }

    return {
        "out": [describe(i) for i in plan.transfers_out],
        "in": [describe(i) for i in plan.transfers_in],
        "net_horizon_gain_vs_roll": plan.expected_points - rolled.expected_points,
        "next_gw_gain_vs_roll": plan.weekly_points[column]
        - rolled.weekly_points[column]
        - plan.hit,
        "hit": plan.hit,
        "bank_after": plan.bank / 10,
        "explanation": "Preferred by the constrained expected-lineup-points objective after transfer hits. Fixture scaling and availability are heuristic adjustments; historical minutes are evidence, not guaranteed playing time.",
    }


def feature_sensitivity(artifact: dict, X: pd.DataFrame) -> pd.DataFrame:
    """Mean prediction change on median replacement; correlated features confound attribution."""
    base = np.mean([m.predict(X[FEATURES]) for m in artifact["models"]], axis=0)
    rows = []
    for col in FEATURES:
        changed = X[FEATURES].copy()
        changed[col] = changed[col].median()
        pred = np.mean([m.predict(changed) for m in artifact["models"]], axis=0)
        rows.append(
            {"feature": col, "mean_absolute_prediction_change": float(np.mean(np.abs(base - pred)))}
        )
    return pd.DataFrame(rows).sort_values("mean_absolute_prediction_change", ascending=False)
