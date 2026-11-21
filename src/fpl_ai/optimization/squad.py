"""MILP squad + weekly lineup/captain allocation. Monetary values are tenths of £m."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pulp

from fpl_ai.rules import Rules


@dataclass
class Plan:
    squad: list[int]
    lineups: dict[str, list[int]]
    captains: dict[str, int]
    expected_points: float
    hit: int
    transfers_in: list[int]
    transfers_out: list[int]
    bank: int
    weekly_points: dict[str, float]


def validate_squad(players: pd.DataFrame, ids: list[int], rules: Rules) -> None:
    if len(ids) != 15 or len(set(ids)) != 15:
        raise ValueError("Squad must contain 15 distinct players")
    if not set(ids) <= set(players.id):
        raise ValueError("Squad contains unavailable/unknown player IDs")
    p = players.set_index("id").loc[ids]
    if p.element_type.value_counts().to_dict() != rules.squad:
        raise ValueError("Squad has invalid position counts")
    if p.team.value_counts().max() > rules.club_limit:
        raise ValueError("Squad exceeds club limit")


def selling_price(purchase: int, current: int) -> int:
    if min(purchase, current) < 0:
        raise ValueError("Prices cannot be negative")
    return current if current <= purchase else purchase + (current - purchase) // 2


def solve_squad(
    players: pd.DataFrame,
    points_columns: list[str],
    rules: Rules,
    *,
    budget: int | None = None,
    owned: list[int] | None = None,
    bank: int = 0,
    sale_prices: dict[int, int] | None = None,
    free_transfers: int = 1,
    max_transfers: int = 2,
    exact_transfers: int | None = None,
    fixed_squad: bool = False,
    discount: float = 1.0,
    chip: str | None = None,
    locked: set[int] | None = None,
    excluded: set[int] | None = None,
    different_from: list[list[int]] | None = None,
) -> Plan:
    """Solve the existing squad objective with optional hard player/draft constraints.

    Each `different_from` squad must differ by at least one player. No constraint
    is relaxed if the budget, locks, exclusions or alternatives are infeasible.
    """
    if budget is not None and (
        isinstance(budget, bool) or not isinstance(budget, int) or budget < 0
    ):
        raise ValueError("Budget must be nonnegative integer £0.1m units")
    if chip not in (None, "bboost", "3xc", "wildcard", "freehit"):
        raise ValueError("Unsupported chip")
    transfer_chip = chip in ("wildcard", "freehit")
    required = {"id", "element_type", "team", "cost", *points_columns}
    if not points_columns or not required <= set(players.columns):
        raise ValueError("Need player metadata and at least one forecast column")
    if (
        players.id.duplicated().any()
        or not np.isfinite(players[list(points_columns) + ["cost"]].to_numpy(float)).all()
    ):
        raise ValueError("Forecasts/prices must be finite with unique IDs")
    if not np.equal(players.cost, np.floor(players.cost)).all() or (players.cost < 0).any():
        raise ValueError("Use nonnegative integer price units of £0.1m")
    if isinstance(bank, bool) or not isinstance(bank, int) or bank < 0:
        raise ValueError("Bank must be a nonnegative integer in £0.1m")
    if (
        not 0 <= free_transfers <= rules.free_transfer_cap
        or not 0 <= max_transfers <= rules.transfer_cap
    ):
        raise ValueError("Invalid free-transfer or transfer limit")
    if not 0 < discount <= 1:
        raise ValueError("Discount must be in (0,1]")
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (free_transfers, max_transfers)):
        raise ValueError("Transfer counts must be integers")
    owned = list(owned or [])
    if owned:
        validate_squad(players, owned, rules)
        if sale_prices is None or set(sale_prices) != set(owned):
            raise ValueError("Supply confirmed selling prices for all 15 owned players")
        if any(
            isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in sale_prices.values()
        ):
            raise ValueError("Selling prices must be nonnegative integer £0.1m values")
    elif fixed_squad:
        raise ValueError("Fixed squad requires owned players")
    if owned and any(sale_prices[i] > int(players.set_index("id").at[i, "cost"]) for i in owned):
        raise ValueError("Selling price exceeds current market price; refresh and confirm prices")
    p = players.set_index("id")
    ids = list(map(int, p.index))
    locked, excluded = set(locked or ()), set(excluded or ())
    if any(isinstance(i, bool) or not isinstance(i, (int, np.integer)) for i in locked | excluded):
        raise ValueError("Locked/excluded player IDs must be integers")
    if locked & excluded:
        raise ValueError("A player cannot be both locked and excluded")
    if not (locked | excluded) <= set(ids):
        raise ValueError("Locked/excluded player has no usable forecast")
    if len(locked) > 15:
        raise ValueError("Cannot lock more than 15 players")
    if "purchasable" in p.columns and any(
        not p.at[i, "purchasable"] and i not in owned for i in locked
    ):
        raise ValueError("A locked player is not available for purchase")
    model = pulp.LpProblem("fpl_advisory", pulp.LpMaximize)
    x = pulp.LpVariable.dicts("squad", ids, cat="Binary")
    for i in locked:
        model += x[i] == 1
    for i in excluded:
        model += x[i] == 0
    for previous in different_from or ():
        if len(previous) != 15 or len(set(previous)) != 15 or not set(previous) <= set(ids):
            raise ValueError("Alternative exclusions require 15 distinct known player IDs")
        model += pulp.lpSum(x[i] for i in previous) <= 14
    if "purchasable" in p.columns:
        for i in ids:
            if not p.at[i, "purchasable"] and i not in owned:
                model += x[i] == 0
    model += pulp.lpSum(x.values()) == 15
    for position, count in rules.squad.items():
        model += pulp.lpSum(x[i] for i in ids if p.at[i, "element_type"] == position) == count
    for team in p.team.unique():
        model += pulp.lpSum(x[i] for i in ids if p.at[i, "team"] == team) <= rules.club_limit
    transfers = 15 - pulp.lpSum(x[i] for i in owned) if owned else 0
    hit_units = pulp.LpVariable("paid_transfers", lowBound=0, cat="Integer")
    if owned:
        model += transfers <= (0 if fixed_squad else 15 if transfer_chip else max_transfers)
        if exact_transfers is not None:
            if not 0 <= exact_transfers <= max_transfers:
                raise ValueError("Invalid exact transfer count")
            model += transfers == exact_transfers
        if transfer_chip:
            model += hit_units == 0
        else:
            model += hit_units >= transfers - free_transfers
        model += pulp.lpSum(
            int(p.at[i, "cost"]) * x[i] for i in ids if i not in owned
        ) <= bank + pulp.lpSum(sale_prices[i] * (1 - x[i]) for i in owned)
    else:
        model += hit_units == 0
        model += pulp.lpSum(int(p.at[i, "cost"]) * x[i] for i in ids) <= (
            rules.budget if budget is None else budget
        )
    xi, cap, weekly = {}, {}, {}
    for col in points_columns:
        xi[col] = pulp.LpVariable.dicts(f"xi_{col}", ids, cat="Binary")
        cap[col] = pulp.LpVariable.dicts(f"cap_{col}", ids, cat="Binary")
        model += pulp.lpSum(xi[col].values()) == 11
        model += pulp.lpSum(cap[col].values()) == 1
        for i in ids:
            model += xi[col][i] <= x[i]
            model += cap[col][i] <= xi[col][i]
        for position in rules.squad:
            total = pulp.lpSum(xi[col][i] for i in ids if p.at[i, "element_type"] == position)
            model += total >= rules.min_play[position]
            model += total <= rules.max_play[position]
        first = col == points_columns[0]
        weekly[col] = pulp.lpSum(
            float(p.at[i, col])
            * (
                (x[i] if first and chip == "bboost" else xi[col][i])
                + (2 if first and chip == "3xc" else 1) * cap[col][i]
            )
            for i in ids
        )
    model += (
        pulp.lpSum(discount**k * weekly[c] for k, c in enumerate(points_columns))
        - rules.hit_cost * hit_units
    )
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=30, threads=1, options=["randomSeed 42"])
    if not solver.available():
        raise ValueError(
            "CBC solver is unavailable; reinstall PuLP or configure a supported CBC binary"
        )
    try:
        status = model.solve(solver)
    except pulp.PulpSolverError as exc:
        raise ValueError(f"CBC solver failed: {exc}") from exc
    if status != pulp.LpStatusOptimal or model.sol_status != pulp.LpSolutionOptimal:
        raise ValueError(
            f"No proven optimal feasible solution: {pulp.LpStatus[status]} (solution {model.sol_status})"
        )
    chosen = [i for i in ids if x[i].value() > 0.5]
    ins, outs = sorted(set(chosen) - set(owned)), sorted(set(owned) - set(chosen))
    remaining = (
        bank + sum(sale_prices[i] for i in outs) - sum(int(p.at[i, "cost"]) for i in ins)
        if owned
        else (rules.budget if budget is None else budget)
        - sum(int(p.at[i, "cost"]) for i in chosen)
    )
    weekly_values = {}
    for k, c in enumerate(points_columns):
        selected_xi = (
            chosen if k == 0 and chip == "bboost" else [i for i in ids if xi[c][i].value() > 0.5]
        )
        captain = next(i for i in ids if cap[c][i].value() > 0.5)
        weekly_values[c] = sum(float(p.at[i, c]) for i in selected_xi) + (
            2 if k == 0 and chip == "3xc" else 1
        ) * float(p.at[captain, c])
    hit = int(round(hit_units.value())) * rules.hit_cost
    return Plan(
        chosen,
        {c: [i for i in ids if xi[c][i].value() > 0.5] for c in points_columns},
        {c: next(i for i in ids if cap[c][i].value() > 0.5) for c in points_columns},
        sum(discount**k * weekly_values[c] for k, c in enumerate(points_columns)) - hit,
        hit,
        ins if owned else [],
        outs,
        int(remaining),
        weekly_values,
    )


def alternatives(
    players: pd.DataFrame, columns: list[str], rules: Rules, **kwargs: object
) -> list[Plan]:
    """Always include a roll plan; infeasible purchases are omitted, never relaxed."""
    plans = []
    for count in range(int(kwargs.get("max_transfers", 2)) + 1):
        try:
            plans.append(solve_squad(players, columns, rules, exact_transfers=count, **kwargs))
        except ValueError as exc:
            if "No proven optimal" not in str(exc):
                raise
    return sorted(plans, key=lambda plan: plan.expected_points, reverse=True)
