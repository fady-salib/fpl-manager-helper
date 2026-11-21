"""Forecast adapters for new squads; use real source rows and existing predictors."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from fpl_ai.forecasting.components import simulate_player
from fpl_ai.forecasting.rankings import fixture_table, rank_players, upcoming
from fpl_ai.rules import Rules

MODELS = ("Baseline", "Locally trained ML", "Event simulation")
RISKS = ("Conservative", "Balanced", "Aggressive")


@dataclass
class BuilderForecast:
    players: pd.DataFrame
    columns: list[str]
    season: str
    model: str
    unavailable: dict[int, str]
    notes: list[str]


def prepare_forecasts(
    bootstrap: dict,
    fixtures: list[dict],
    histories: pd.DataFrame,
    *,
    model: str = "Baseline",
    horizon: int = 5,
    artifact: dict | None = None,
    as_of: object = None,
    samples: int = 1000,
) -> BuilderForecast:
    """Never switch requested models silently or invent missing event distributions.

    Baseline/ML dispersion is a historical points-dispersion proxy. If unavailable,
    only the explicit availability-exposure heuristic is used. It is not an interval.
    Component simulations freeze current history and do not predict injury recovery.
    """
    if model not in MODELS or horizon not in (1, 3, 5, 8):
        raise ValueError("Select a supported forecast and a 1, 3, 5 or 8 GW horizon")
    if model == "Locally trained ML" and artifact is None:
        raise ValueError("No local ML model. Run fpl-ai refresh --histories then fpl-ai train")
    if model == "Event simulation" and histories.empty:
        raise ValueError("Event simulation needs real histories: fpl-ai refresh --histories")
    rules = Rules.from_bootstrap(bootstrap)
    events = upcoming(bootstrap, horizon, as_of)
    if not events:
        raise ValueError("No upcoming gameweek deadlines")
    for event in events:
        rules.validate_event(event)
    columns = [f"gw_{e['id']}" for e in events]
    rows = rank_players(
        bootstrap,
        fixtures,
        horizon=horizon,
        histories=histories,
        artifact=artifact if model == "Locally trained ML" and "models" in artifact else None,
        as_of=as_of,
    )
    if model == "Locally trained ML" and "regressors" in artifact:
        from fpl_ai.ml.prediction import live_predictions

        predictions = live_predictions(
            artifact, bootstrap, fixtures, histories, horizon, as_of
        ).set_index("id")
        for col in columns + ["horizon_points"]:
            rows[col] = rows.id.map(predictions[col])
        rows["next_points"] = rows[columns[0]]
        rows["value"] = rows.horizon_points / rows.price
        rows["differential_score"] = rows.value * (1 - rows.ownership / 100)
    teams = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    games = fixture_table(fixtures, teams)
    deadline = pd.Timestamp(events[0]["deadline_time"])
    grouped = dict(tuple(histories.groupby("player_id"))) if not histories.empty else {}
    unavailable = {}
    output = []
    notes = [
        "Projections hold current history and prices fixed; future injuries/rotation are not forecast.",
        "Totals include each week's XI and captain, excluding expected autosubs and captain fallback.",
    ]
    if len(events) < horizon:
        notes.append(
            f"Only {len(events)} upcoming deadlines exist; the requested {horizon} GW horizon is shortened."
        )
    notes.append(
        "Risk uses uncalibrated simulated dispersion."
        if model == "Event simulation"
        else "Risk uses historical points dispersion; without history it uses availability exposure only. Neither is a calibrated forecast interval."
    )
    if model == "Event simulation":
        notes.append(
            "The event model uses marginal history rates per fixture, not opponent/FDR-conditioned rates or teammate correlations."
        )
    for row in rows.to_dict("records"):
        pid = int(row["id"])
        if not row["purchasable"]:
            unavailable[pid] = "Not available for purchase"
            continue
        history = grouped.get(pid, pd.DataFrame())
        if not history.empty:
            history = history[
                (history["round"] < events[0]["id"])
                & history.kickoff_time.notna()
                & (
                    (
                        history.kickoff_time.astype("datetime64[ns, UTC]").astype("int64")
                        + 10_800_000_000_000
                    )
                    < deadline.value
                )
            ]
        recent = history.tail(10)
        totals = pd.to_numeric(
            recent.get("total_points", pd.Series(dtype=float)), errors="coerce"
        ).dropna()
        dispersion = float(totals.std(ddof=0)) if len(totals) >= 2 else np.nan
        minutes = pd.to_numeric(
            recent.get("minutes", pd.Series(dtype=float)), errors="coerce"
        ).dropna()
        reliability = (
            float(np.clip(minutes.mean() / 90, 0, 1))
            if len(minutes)
            else float(row["availability_factor"])
        )
        row["reliability_proxy"] = reliability
        row["risk_basis"] = (
            "simulated event dispersion"
            if model == "Event simulation"
            else (
                "historical point dispersion"
                if np.isfinite(dispersion)
                else "availability exposure only (history unavailable)"
            )
        )
        simulations = {}
        try:
            for k, event in enumerate(events):
                col = columns[k]
                fixtures_now = games[(games.team == row["team"]) & (games.event == event["id"])]
                count = len(fixtures_now)
                availability = float(row["availability_factor"]) if k == 0 else 1.0
                if model == "Event simulation":
                    key = (count, availability)
                    if key not in simulations:
                        simulations[key] = simulate_player(
                            history,
                            row["position"],
                            rules,
                            fixtures=count,
                            availability=availability,
                            samples=samples,
                            seed=42 + pid,
                        )
                    sim = simulations[key]
                    row[col] = sim["mean"]
                    row[f"risk_{col}"] = float(np.std(sim["draws"]))
                    row[f"minutes_{col}"] = sim["expected_minutes"]
                else:
                    exposure = max(0, row[col]) * (1 - availability)
                    row[f"risk_{col}"] = (
                        max(exposure, dispersion * np.sqrt(count) * availability)
                        if np.isfinite(dispersion)
                        else exposure
                    )
                row[f"count_{col}"] = count
        except (ValueError, TypeError) as exc:
            unavailable[pid] = f"Event forecast unavailable: {exc}"
            continue
        if not all(np.isfinite(row[col]) for col in columns):
            unavailable[pid] = "Missing/nonfinite model forecast"
            continue
        row["source"] = model
        row["horizon_points"] = sum(row[col] for col in columns)
        row["next_points"] = row[columns[0]]
        output.append(row)
    if not output:
        raise ValueError(
            "No players have supported forecasts; refresh data/histories or choose another model"
        )
    return BuilderForecast(pd.DataFrame(output), columns, rules.season, model, unavailable, notes)
