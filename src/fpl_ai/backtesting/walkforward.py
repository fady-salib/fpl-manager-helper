"""Deadline-snapshot walk-forward benchmark; refuses hindsight reconstruction."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from fpl_ai.forecasting.rankings import rank_players
from fpl_ai.optimization.squad import alternatives, selling_price, solve_squad
from fpl_ai.rules import Rules
from fpl_ai.simulation.scoring import score_lineup
from fpl_ai.storage import SnapshotStore


def deadline_snapshot(
    store: SnapshotStore, endpoint: str, deadline: pd.Timestamp, max_age_hours: int = 24
) -> dict | list:
    found = store.latest(endpoint, before=deadline.to_pydatetime())
    if not found or deadline.to_pydatetime() - found[0] > timedelta(hours=max_age_hours):
        raise ValueError(
            f"Missing pre-deadline {endpoint} snapshot within {max_age_hours}h of {deadline}"
        )
    return found[1]


def run_backtest(
    store: SnapshotStore,
    event_ids: list[int],
    *,
    strategy: str = "form",
    initial_budget: int = 1000,
) -> dict:
    if strategy not in ("form", "historical_average", "official_ep", "ml"):
        raise ValueError("Unknown baseline")
    if not event_ids or event_ids != list(range(event_ids[0], event_ids[-1] + 1)):
        raise ValueError("Backtest needs a consecutive nonempty gameweek range")
    latest = store.latest("bootstrap-static/")
    if latest is None:
        raise ValueError("No bootstrap data")
    events = {e["id"]: e for e in latest[1]["events"]}
    squad, purchase, bank, free = [], {}, initial_budget, 1
    records = []
    for event in event_ids:
        if not events[event].get("data_checked"):
            raise ValueError(f"GW {event} results not finalized")
        deadline = pd.Timestamp(events[event]["deadline_time"])
        b = deadline_snapshot(store, "bootstrap-static/", deadline)
        fixtures = deadline_snapshot(store, "fixtures/", deadline)
        rules = Rules.from_bootstrap(b)
        rules.validate_event(next(e for e in b["events"] if e["id"] == event))
        artifact = None
        history = None
        method = strategy
        if strategy == "ml":
            from fpl_ai.features.history import histories_from_store, training_frame
            from fpl_ai.models.evaluate import train_evaluate

            for p in b["elements"]:
                deadline_snapshot(store, f"element-summary/{p['id']}/", deadline)
            history = histories_from_store(store, b, before=deadline.to_pydatetime())
            if history.empty:
                method = "form (no previous match outcomes at this deadline)"
            else:
                frame = training_frame(history, b)
                if frame.empty or frame.event.nunique() < 7:
                    method = "form (insufficient prior gameweeks for four-block ML selection)"
                else:
                    artifact, _ = train_evaluate(frame)
        ranks = rank_players(
            b,
            fixtures,
            horizon=1,
            as_of=deadline - pd.Timedelta(seconds=1),
            artifact=artifact,
            histories=history,
        )
        col = f"gw_{event}"
        if col not in ranks:
            raise ValueError("Deadline event absent in archived snapshot")
        if strategy == "historical_average":
            ranks[col] = ranks.season_average * ranks.fixture_count
        elif strategy == "official_ep":
            ep = {p["id"]: pd.to_numeric(p.get("ep_next"), errors="coerce") for p in b["elements"]}
            ranks[col] = ranks.id.map(ep)
        ranks = ranks.dropna(subset=[col])
        costs = ranks.set_index("id").cost.to_dict()
        initial_selection = not squad
        if squad:
            sales = {i: selling_price(purchase[i], int(costs[i])) for i in squad}
            plan = alternatives(
                ranks,
                [col],
                rules,
                owned=squad,
                bank=bank,
                sale_prices=sales,
                free_transfers=free,
                max_transfers=1,
            )[0]
        else:
            plan = solve_squad(ranks, [col], rules, budget=initial_budget)
        for i in plan.squad:
            purchase.setdefault(i, int(costs[i]))
        purchase = {i: purchase[i] for i in plan.squad}
        squad, bank = plan.squad, plan.bank
        free = 1 if initial_selection else rules.next_free_transfers(free, len(plan.transfers_in))
        starters, captain = plan.lineups[col], plan.captains[col]
        positions = ranks.set_index("id").element_type.to_dict()
        projections = ranks.set_index("id")[col].to_dict()
        bench = sorted(
            set(squad) - set(starters), key=lambda i: (positions[i] != 1, -projections[i])
        )
        vice = max((i for i in starters if i != captain), key=lambda i: projections[i])
        live = store.latest(f"event/{event}/live/")
        if not live or live[0] <= deadline:
            raise ValueError(f"Missing post-deadline actual results for GW {event}")
        actual = {e["id"]: e["stats"] for e in live[1]["elements"]}
        points = {i: float(actual[i]["total_points"]) for i in squad}
        played = {
            i: bool(actual[i]["minutes"] or actual[i]["red_cards"] or actual[i]["yellow_cards"])
            for i in squad
        }
        realized = score_lineup(starters, bench, captain, vice, positions, points, played, rules)
        active_cap = captain if played[captain] else vice if played[vice] else None
        errors = [abs(projections[i] - points[i]) for i in squad]
        records.append(
            {
                "event": event,
                "forecast_method": method,
                "points": realized - plan.hit,
                "hit": plan.hit,
                "captain_extra": points[active_cap] if active_cap else 0,
                "chip_contribution": 0,
                "squad_mae": sum(errors) / len(errors),
                "mae_by_position": {
                    str(pos): sum(
                        abs(projections[i] - points[i]) for i in squad if positions[i] == pos
                    )
                    / sum(positions[i] == pos for i in squad)
                    for pos in rules.squad
                },
                "squad": squad,
                "bank": bank,
                "next_free_transfers": free,
            }
        )
    return {
        "strategy": strategy,
        "total_points": sum(r["points"] for r in records),
        "average_points": sum(r["points"] for r in records) / len(records),
        "hits": sum(r["hit"] for r in records),
        "weeks": records,
        "limitations": [
            "No chips policy",
            "One-transfer search per week",
            "Deadline snapshots required",
            "Official forecasts only when present in those snapshots",
        ],
    }
