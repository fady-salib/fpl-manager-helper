"""Seeded event simulation using observed histories and season scoring weights.

This is a statistical research baseline, not a calibrated position-specific ML model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from fpl_ai.rules import Rules

REQUIRED = {
    "minutes",
    "starts",
    "expected_goals",
    "expected_assists",
    "expected_goals_conceded",
    "saves",
    "bonus",
    "yellow_cards",
    "red_cards",
    "own_goals",
    "penalties_saved",
    "penalties_missed",
    "clearances_blocks_interceptions",
    "tackles",
    "recoveries",
}


def simulate_player(
    history: pd.DataFrame,
    position: str,
    rules: Rules,
    *,
    fixtures: int = 1,
    availability: float = 1.0,
    samples: int = 5000,
    seed: int = 42,
) -> dict:
    if not REQUIRED <= set(history.columns) or history.empty:
        raise ValueError("Component forecast needs real history with all scoring-event fields")
    if position not in ("GKP", "DEF", "MID", "FWD") or not 0 <= fixtures <= 5:
        raise ValueError("Invalid position/fixture count")
    if not 0 <= availability <= 1 or not 100 <= samples <= 100_000:
        raise ValueError("Invalid availability/sample count")
    h = history.tail(10)[sorted(REQUIRED)].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(h.to_numpy()).all() or (h < 0).any().any():
        raise ValueError("Missing/invalid event rates; no fabricated replacements allowed")
    rng = np.random.default_rng(seed)
    fit_to_play = rng.random(samples) < availability  # Shared availability across double fixtures.
    total = np.zeros(samples)
    minutes_total = np.zeros(samples)
    started = np.zeros(samples, dtype=bool)
    appeared = np.zeros(samples, dtype=bool)
    goals_total = np.zeros(samples)
    assists_total = np.zeros(samples)
    clean = np.zeros(samples, dtype=bool)
    weights = rules.scoring
    duration = max(90, float(h.minutes.sum()))
    rates = {
        k: float(h[k].sum()) / duration
        for k in ("expected_goals", "expected_assists", "expected_goals_conceded", "saves")
    }
    for _ in range(fixtures):
        draw = h.iloc[rng.integers(0, len(h), samples)]
        minutes = draw.minutes.to_numpy() * fit_to_play
        played = (
            (minutes > 0) | (draw.red_cards.to_numpy() > 0) | (draw.yellow_cards.to_numpy() > 0)
        ) & fit_to_play
        long = minutes >= 60
        goals = rng.poisson(rates["expected_goals"] * minutes)
        assists = rng.poisson(rates["expected_assists"] * minutes)
        conceded = rng.poisson(rates["expected_goals_conceded"] * minutes)
        cs = (conceded == 0) & long
        saves = rng.poisson(rates["saves"] * minutes)
        score = np.where(
            long, weights["long_play"], np.where(minutes > 0, weights["short_play"], 0)
        ).astype(float)
        score += goals * weights["goals_scored"][position] + assists * weights["assists"]
        score += cs * weights["clean_sheets"][position]
        score += (conceded // 2) * weights["goals_conceded"][position]
        if position == "GKP":
            score += (saves // 3) * weights["saves"]
        defensive = draw.clearances_blocks_interceptions.to_numpy() + draw.tackles.to_numpy()
        if position in ("MID", "FWD"):
            defensive += draw.recoveries.to_numpy()
        threshold = 10 if position == "DEF" else 12
        score += (defensive >= threshold) * weights["defensive_contribution"][position] * played
        for stat in (
            "bonus",
            "yellow_cards",
            "red_cards",
            "own_goals",
            "penalties_saved",
            "penalties_missed",
        ):
            score += draw[stat].to_numpy() * weights[stat] * played
        total += score
        minutes_total += minutes
        started |= (draw.starts.to_numpy() > 0) & fit_to_play
        appeared |= played
        clean |= cs
        goals_total += goals
        assists_total += assists
    return {
        "mean": float(total.mean()),
        "p10": float(np.quantile(total, 0.1)),
        "p90": float(np.quantile(total, 0.9)),
        "expected_minutes": float(minutes_total.mean()),
        "start_probability": float(started.mean()),
        "appearance_probability": float(appeared.mean()),
        "score_probability": float((goals_total > 0).mean()),
        "assist_probability": float((assists_total > 0).mean()),
        "clean_sheet_probability": float(clean.mean()),
        "draws": total,
        "appeared": appeared,
        "method": "Empirical minutes + conditional Poisson events; uncalibrated",
    }
