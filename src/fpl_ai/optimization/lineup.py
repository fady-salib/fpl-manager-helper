"""Appearance-aware lineup refinement with simulated autosubs and captain fallback.

Finite-scenario local search: deterministic, feasible, not globally optimal.
"""

from __future__ import annotations

from itertools import permutations

import numpy as np
import pandas as pd

from fpl_ai.optimization.squad import solve_squad
from fpl_ai.rules import Rules
from fpl_ai.simulation.scoring import score_lineup


def utility(draws: np.ndarray, risk: str) -> float:
    if risk == "Conservative":
        return float(draws.mean() - 0.25 * draws.std())
    if risk == "Aggressive":
        return float(draws.mean() + 0.25 * (np.quantile(draws, 0.9) - draws.mean()))
    if risk != "Expected points":
        raise ValueError("Unknown risk preference")
    return float(draws.mean())


def optimize_lineup(
    players: pd.DataFrame,
    rules: Rules,
    distributions: dict[int, dict],
    *,
    risk: str = "Expected points",
    max_passes: int = 1,
) -> dict:
    """Each distribution has aligned `draws` and `appeared` Monte Carlo scenarios.

    Independent player simulations are only a marginal approximation. Team-level
    dependence and opponent covariance are not modeled by the component generator.
    """
    ids = list(map(int, players.id))
    if len(ids) != 15 or set(distributions) != set(ids):
        raise ValueError("Need distributions for all 15 players")
    sizes = {len(distributions[i]["draws"]) for i in ids}
    if len(sizes) != 1 or next(iter(sizes)) < 1:
        raise ValueError("Monte Carlo scenarios must have identical nonzero lengths")
    n = next(iter(sizes))
    points = {i: np.asarray(distributions[i]["draws"], dtype=float) for i in ids}
    plays = {i: np.asarray(distributions[i]["appeared"], dtype=bool) for i in ids}
    if any(len(plays[i]) != n or not np.isfinite(points[i]).all() for i in ids):
        raise ValueError("Invalid point/appearance scenarios")
    frame = players.copy()
    frame["scenario_mean"] = [points[i].mean() for i in ids]
    initial = solve_squad(
        frame,
        ["scenario_mean"],
        rules,
        owned=ids,
        fixed_squad=True,
        sale_prices=dict.fromkeys(ids, 0),
    )
    positions = frame.set_index("id").element_type.to_dict()
    point_rows = [{i: float(points[i][s]) for i in ids} for s in range(n)]
    play_rows = [{i: bool(plays[i][s]) for i in ids} for s in range(n)]

    def evaluate(xi: list[int]) -> dict:
        captain_options = []
        for cap in xi:
            for vice in xi:
                if vice != cap:
                    extra = np.where(
                        plays[cap], points[cap], np.where(plays[vice], points[vice], 0)
                    )
                    captain_options.append((utility(extra, risk), cap, vice, extra))
        _, cap, vice, extra = max(captain_options, key=lambda t: t[0])
        reserve = set(ids) - set(xi)
        keeper = next(i for i in reserve if positions[i] == 1)
        choices = []
        for order in permutations(sorted(reserve - {keeper})):
            bench = [keeper, *order]
            draws = np.array(
                [
                    score_lineup(
                        xi, bench, cap, vice, positions, point_rows[s], play_rows[s], rules
                    )
                    for s in range(n)
                ]
            )
            choices.append((utility(draws, risk), bench, draws))
        score, bench, draws = max(choices, key=lambda t: t[0])
        return {
            "xi": xi,
            "bench": bench,
            "captain": cap,
            "vice": vice,
            "expected_points": float(draws.mean()),
            "p10": float(np.quantile(draws, 0.1)),
            "p90": float(np.quantile(draws, 0.9)),
            "utility": score,
            "captain_extra": float(extra.mean()),
            "scenario_count": n,
        }

    best = evaluate(initial.lineups["scenario_mean"])
    for _ in range(max_passes):
        previous = best
        xi = previous["xi"]
        for out in xi:
            for incoming in set(ids) - set(xi):
                candidate = [i for i in xi if i != out] + [incoming]
                shape = {pos: sum(positions[i] == pos for i in candidate) for pos in rules.squad}
                if all(
                    rules.min_play[pos] <= count <= rules.max_play[pos]
                    for pos, count in shape.items()
                ):
                    option = evaluate(candidate)
                    if option["utility"] > best["utility"] + 1e-9:
                        best = option
        if best is previous:
            break
    return {
        **best,
        "risk": risk,
        "method": "Finite-scenario local swap search; no global optimality guarantee",
    }
