"""Frozen-history per-fixture forecasts, summed over actual double/blank weeks."""

import pandas as pd

from fpl_ai.forecasting.rankings import upcoming

from .data import STATS, features
from .training import predict_rows


def live_predictions(artifact, bootstrap, fixtures, histories, horizon=5, as_of=None):
    events = upcoming(bootstrap, horizon, as_of)
    if not events:
        raise ValueError("No upcoming gameweeks")
    cutoff = pd.Timestamp(as_of) if as_of else pd.Timestamp.now(tz="UTC")
    by_id = dict(tuple(histories.groupby("player_id"))) if not histories.empty else {}
    rows, metadata = [], []
    for p in bootstrap["elements"]:
        past = by_id.get(p["id"], pd.DataFrame(columns=[*STATS, "round", "kickoff_time"]))
        past = past.copy()
        for stat in STATS:
            past[stat] = (
                pd.to_numeric(past[stat], errors="coerce") if stat in past else float("nan")
            )
        past["kickoff_time"] = pd.to_datetime(past.kickoff_time, utc=True)
        past = past[
            (past["round"] < events[0]["id"]) & (past.kickoff_time + pd.Timedelta(hours=3) < cutoff)
        ].sort_values("kickoff_time")
        rows.append(features(past))
        metadata.append(
            {
                "id": p["id"],
                "name": p["web_name"],
                "team": p["team"],
                "element_type": p["element_type"],
                "cost": p["now_cost"],
                "purchasable": not p.get("removed", False) and p.get("can_select", True),
                "history_samples": len(past),
            }
        )
    predicted = predict_rows(artifact, pd.DataFrame(rows))
    result = pd.concat([pd.DataFrame(metadata), predicted.reset_index(drop=True)], axis=1)
    for event in events:
        counts = {}
        for f in fixtures:
            if f.get("event") == event["id"]:
                for team in (f["team_h"], f["team_a"]):
                    counts[team] = counts.get(team, 0) + 1
        result[f"gw_{event['id']}"] = result.expected_points * result.team.map(counts).fillna(0)
    result["horizon_points"] = result[[f"gw_{e['id']}" for e in events]].sum(axis=1)
    return result


def recommend(players, rules, **kwargs):
    from fpl_ai.optimization.squad import solve_squad

    columns = [c for c in players if c.startswith("gw_")]
    plan = solve_squad(players, columns, rules, **kwargs)
    weeks = {}
    indexed = players.set_index("id")
    for col, xi in plan.lineups.items():
        cap = plan.captains[col]
        vice = max((i for i in xi if i != cap), key=lambda i: indexed.at[i, col])
        bench = sorted(
            set(plan.squad) - set(xi),
            key=lambda i: (indexed.at[i, "element_type"] != 1, -indexed.at[i, col]),
        )
        weeks[col] = {"xi": xi, "bench": bench, "captain": cap, "vice_captain": vice}
    return {
        "plan": vars(plan),
        "weeks": weeks,
        "method": "Optimal expected-points squad and XI; bench/vice ordered by expected points. One immediate transfer set held across the horizon; no future transfer scheduling or autosub expectation.",
    }
