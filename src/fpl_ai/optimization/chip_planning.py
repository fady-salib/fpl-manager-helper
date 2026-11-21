"""Beam policy over transfers and all four chip types; fixed-price approximation."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from fpl_ai.optimization.squad import Plan, alternatives, solve_squad, validate_squad
from fpl_ai.rules import Rules


@dataclass
class ChipStep:
    event: int
    chip_id: int | None
    chip: str | None
    plan: Plan


@dataclass
class ChipPath:
    squad: list[int]
    sales: dict[int, int]
    bank: int
    free: int
    available: set[int]
    previous_chip: str | None
    score: float
    steps: list[ChipStep]


def plan_chips(
    players: pd.DataFrame,
    columns: list[str],
    rules: Rules,
    *,
    owned: list[int],
    sales: dict[int, int],
    bank: int,
    free: int,
    available_ids: set[int],
    previous_chip: str | None = None,
    width: int = 2,
    max_transfers: int = 1,
) -> ChipPath:
    """BB/TC add gross points; WC persists, FH reverts. One chip per gameweek.

    Action proposals optimize a held-squad remaining horizon. Beam pruning and
    proposals mean this is NOT a globally optimal sequence. Saving beyond the
    horizon has no terminal option value: do not treat a chosen chip as a use-now
    recommendation without a longer horizon and expiry review.
    """
    if not 1 <= len(columns) <= 8 or not 1 <= width <= 5:
        raise ValueError("Use 1–8 weeks and width 1–5")
    event_ids = [int(c.split("_")[1]) for c in columns]
    if event_ids != list(range(event_ids[0], event_ids[-1] + 1)):
        raise ValueError("Chip planning requires consecutive gameweeks")
    if not available_ids <= {c["id"] for c in rules.chips}:
        raise ValueError("Unknown chip instance")
    validate_squad(players, owned, rules)
    costs = players.set_index("id").cost.to_dict()
    beam = [ChipPath(owned, sales, bank, free, available_ids, previous_chip, 0, [])]
    for k, event in enumerate(event_ids):
        col = columns[k]
        candidates = []
        for state in beam:
            common = dict(
                owned=state.squad,
                bank=state.bank,
                sale_prices=state.sales,
                free_transfers=state.free,
                max_transfers=max_transfers,
            )
            actions = [(None, None, p) for p in alternatives(players, columns[k:], rules, **common)]
            for chip in rules.chips:
                name = chip["name"]
                if (
                    not rules.chip_allowed(name, event, state.available, state.previous_chip)
                    or chip["id"] not in state.available
                ):
                    continue
                # Free Hit's replacement team exists only this week.
                target_cols = [col] if name == "freehit" else columns[k:]
                try:
                    plan = solve_squad(players, target_cols, rules, chip=name, **common)
                    actions.append((chip["id"], name, plan))
                except ValueError as exc:
                    if "No proven optimal" not in str(exc):
                        raise
            for chip_id, name, plan in actions:
                free_next = rules.next_free_transfers(state.free, len(plan.transfers_in), name)
                squad_next = state.squad if name == "freehit" else plan.squad
                sales_next = (
                    state.sales
                    if name == "freehit"
                    else {i: state.sales.get(i, int(costs[i])) for i in squad_next}
                )
                bank_next = state.bank if name == "freehit" else plan.bank
                candidates.append(
                    ChipPath(
                        squad_next,
                        sales_next,
                        bank_next,
                        free_next,
                        state.available - ({chip_id} if chip_id else set()),
                        name,
                        state.score + plan.weekly_points[col] - plan.hit,
                        state.steps + [ChipStep(event, chip_id, name, plan)],
                    )
                )
        unique = {}
        for path in sorted(candidates, key=lambda c: c.score, reverse=True):
            key = (
                tuple(sorted(path.squad)),
                path.bank,
                path.free,
                tuple(sorted(path.available)),
                path.previous_chip,
            )
            unique.setdefault(key, path)
        beam = list(unique.values())[:width]
        if not beam:
            raise ValueError("No feasible chip path")
    return max(beam, key=lambda c: c.score)
