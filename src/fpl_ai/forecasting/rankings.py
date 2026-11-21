"""Transparent, fixture-aware live baseline; optional validated direct ML model."""

from __future__ import annotations

import numpy as np
import pandas as pd

from fpl_ai.features.history import FEATURES, lag_features


def number(value: object) -> float:
    try:
        f = float(value)
        return f if np.isfinite(f) else np.nan
    except (TypeError, ValueError):
        return np.nan


def upcoming(bootstrap: dict, horizon: int = 5, as_of: object = None) -> list[dict]:
    if not 1 <= horizon <= 8:
        raise ValueError("Horizon must be 1–8 gameweeks")
    from datetime import UTC, datetime

    now = pd.Timestamp(as_of) if as_of is not None else datetime.now(UTC)
    return [e for e in bootstrap["events"] if pd.Timestamp(e["deadline_time"]) > now][:horizon]


def fixture_table(fixtures: list[dict], teams: dict[int, str]) -> pd.DataFrame:
    rows = []
    for f in fixtures:
        if f["event"] is None:
            continue
        for home in (True, False):
            team = f["team_h"] if home else f["team_a"]
            opponent = f["team_a"] if home else f["team_h"]
            rows.append(
                {
                    "team": team,
                    "event": f["event"],
                    "fixture": f["id"],
                    "opponent": teams.get(opponent, str(opponent)),
                    "home": home,
                    "difficulty": f.get("team_h_difficulty" if home else "team_a_difficulty"),
                    "kickoff": f.get("kickoff_time"),
                }
            )
    return pd.DataFrame(
        rows, columns=["team", "event", "fixture", "opponent", "home", "difficulty", "kickoff"]
    )


def rank_players(
    bootstrap: dict,
    fixtures: list[dict],
    *,
    horizon: int = 5,
    histories: pd.DataFrame | None = None,
    artifact: dict | None = None,
    as_of: object = None,
) -> pd.DataFrame:
    events = upcoming(bootstrap, horizon, as_of)
    teams = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    positions = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
    fixture_rows = fixture_table(fixtures, teams)
    # Fixture effects are shared by every player at a club. Compute them once,
    # rather than filtering the same DataFrame for every player/gameweek.
    contexts = {}
    for (team, event), games in fixture_rows.groupby(["team", "event"]):
        factors = [
            float(np.clip((3 / d) ** 0.35, 0.75, 1.25)) if pd.notna(d) and d > 0 else 1.0
            for d in games["difficulty"]
        ]
        contexts[(team, event)] = (
            len(games),
            sum(factors),
            ", ".join(f"{f.opponent} ({'H' if f.home else 'A'})" for f in games.itertuples()),
            float(games["difficulty"].mean()),
        )
    rows = []
    history_by_id = (
        dict(tuple(histories.groupby("player_id")))
        if histories is not None and not histories.empty
        else {}
    )
    ml_predictions = {}
    if artifact is not None and events:
        # All future GWs freeze the same available history: predict this batch once,
        # rather than invoking each model separately for every player and future GW.
        X = pd.DataFrame(
            [
                lag_features(
                    history_by_id.get(p["id"], pd.DataFrame()),
                    events[0]["id"],
                    pd.Timestamp(events[0]["deadline_time"]),
                )
                for p in bootstrap["elements"]
            ],
            columns=FEATURES,
        )
        predictions = np.mean([m.predict(X) for m in artifact["models"]], axis=0)
        ml_predictions = dict(
            zip((p["id"] for p in bootstrap["elements"]), predictions, strict=True)
        )
    for p in bootstrap["elements"]:
        form, average = number(p.get("form")), number(p.get("points_per_game"))
        # Missing statistics remain missing, not an invented football measurement.
        base = 0.7 * form + 0.3 * average if np.isfinite(form + average) else np.nan
        chance = number(p.get("chance_of_playing_next_round"))
        availability = chance / 100 if np.isfinite(chance) else (1.0 if p["status"] == "a" else 0.5)
        if p["status"] in ("u", "s", "i") and chance == 0:
            availability = 0.0
        row = {
            "id": p["id"],
            "name": p["web_name"],
            "position": positions[p["element_type"]],
            "element_type": p["element_type"],
            "team": p["team"],
            "club": teams[p["team"]],
            "cost": p["now_cost"],
            "price": p["now_cost"] / 10,
            "ownership": number(p.get("selected_by_percent")),
            "status": p["status"],
            "news": p.get("news", ""),
            "availability_factor": availability,
            "form": form,
            "season_average": average,
            "source": "form baseline",
            "purchasable": not p.get("removed", False) and p.get("can_select", True),
            "historical_minutes_per_fixture": np.nan,
            "historical_start_rate": np.nan,
        }
        hist = history_by_id.get(p["id"], pd.DataFrame())
        for index, event in enumerate(events):
            count, fixture_factor, description, difficulty = contexts.get(
                (p["team"], event["id"]), (0, 0.0, "BLANK", np.nan)
            )
            prediction = base
            if artifact is not None:
                prediction = float(ml_predictions[p["id"]])
                row["source"] = "held-out selected ML ensemble"
            # FDR modulation is a heuristic, not a trained or calibrated effect.
            factor = (
                availability if index == 0 else 1.0
            )  # Current injury estimate not a recovery forecast.
            if p.get("removed", False):
                factor = 0.0
            row[f"gw_{event['id']}"] = prediction * fixture_factor * factor if count else 0.0
            row[f"fixtures_{event['id']}"] = description
            if index == 0:
                row["next_points"] = row[f"gw_{event['id']}"]
                row["fixture_count"] = count
                row["difficulty"] = difficulty
                if len(hist):
                    last = hist[hist["round"] < event["id"]].tail(10)
                    row["historical_minutes_per_fixture"] = float(last["minutes"].mean())
                    row["historical_start_rate"] = float(
                        last.get("starts", pd.Series(dtype=float)).mean()
                    )
        row["horizon_points"] = sum(row[f"gw_{e['id']}"] for e in events) if events else np.nan
        row["value"] = row["horizon_points"] / row["price"] if row["price"] else np.nan
        row["differential_score"] = row["value"] * (1 - row["ownership"] / 100)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("horizon_points", ascending=False).reset_index(drop=True)
