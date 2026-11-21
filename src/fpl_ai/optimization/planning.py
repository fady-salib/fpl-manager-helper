"""Bounded beam search: stateful transfers across a fixed-price forecast horizon."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from fpl_ai.optimization.squad import Plan, alternatives
from fpl_ai.rules import Rules


@dataclass
class Path:
    squad: list[int]
    bank: int
    free: int
    sales: dict[int, int]
    score: float
    steps: list[Plan]


def beam_plan(
    players: pd.DataFrame,
    columns: list[str],
    rules: Rules,
    *,
    owned: list[int],
    bank: int,
    sales: dict[int, int],
    free: int,
    width: int = 3,
    max_transfers: int = 1,
) -> Path:
    if not 1 <= len(columns) <= 8 or not 1 <= width <= 10:
        raise ValueError("Use 1–8 weeks and beam width 1–10")
    beam = [Path(owned, bank, free, sales, 0.0, [])]
    costs = players.set_index("id").cost.to_dict()
    for k, col in enumerate(columns):
        candidates = []
        for state in beam:
            for plan in alternatives(
                players,
                columns[k:],
                rules,
                owned=state.squad,
                bank=state.bank,
                sale_prices=state.sales,
                free_transfers=state.free,
                max_transfers=max_transfers,
            ):
                sales_next = {i: state.sales.get(i, int(costs[i])) for i in plan.squad}
                # Only realized first-week utility accumulates; later projections propose actions.
                candidates.append(
                    Path(
                        plan.squad,
                        plan.bank,
                        rules.next_free_transfers(state.free, len(plan.transfers_in)),
                        sales_next,
                        state.score + plan.weekly_points[col] - plan.hit,
                        state.steps + [plan],
                    )
                )
        if not candidates:
            raise ValueError("No feasible planning path")
        unique = {}
        for path in sorted(candidates, key=lambda s: s.score, reverse=True):
            key = (tuple(sorted(path.squad)), path.bank, path.free)
            unique.setdefault(key, path)
        beam = list(unique.values())[:width]
    return max(beam, key=lambda state: state.score)
