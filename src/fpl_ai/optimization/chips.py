"""Chip timing screens, not a jointly optimal whole-season chip policy."""

from __future__ import annotations

import pandas as pd

from fpl_ai.optimization.squad import solve_squad
from fpl_ai.rules import Rules


def chip_opportunities(
    players: pd.DataFrame,
    columns: list[str],
    rules: Rules,
    owned: list[int],
    available_ids: set[int],
    previous_chip: str | None = None,
) -> pd.DataFrame:
    costs = players.set_index("id").cost.to_dict()
    plan = solve_squad(
        players,
        columns,
        rules,
        owned=owned,
        bank=0,
        sale_prices={i: int(costs[i]) for i in owned},
        fixed_squad=True,
    )
    indexed = players.set_index("id")
    rows = []
    for col in columns:
        event = int(col.split("_")[1])
        for name in ("bboost", "3xc"):
            if not rules.chip_allowed(name, event, available_ids, previous_chip):
                continue
            gain = (
                sum(float(indexed.at[i, col]) for i in owned if i not in plan.lineups[col])
                if name == "bboost"
                else float(indexed.at[plan.captains[col], col])
            )
            rows.append({"chip": name, "event": event, "gross_extra_points": gain})
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["versus_best_other_week"] = [
            r.gross_extra_points
            - frame[(frame.chip == r.chip) & (frame.event != r.event)].gross_extra_points.max()
            for r in frame.itertuples()
        ]
    return frame
