"""New-team orchestration around solve_squad, plus auditable local draft exports."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from fpl_ai.forecasting.team_builder import RISKS, BuilderForecast
from fpl_ai.optimization.squad import Plan, solve_squad, validate_squad
from fpl_ai.rules import Rules

STYLES = ("Maximum expected points", "Balanced", "Differential-focused")


@dataclass
class BuilderSquad:
    style: str
    risk: str
    plan: Plan  # Expected points always retain original model units, NOT preference utility.
    utility: float
    vice: dict[str, int]
    bench: dict[str, list[int]]  # Reserve GK first; three outfield players in priority order.
    table: pd.DataFrame


@dataclass
class BuilderResult:
    squads: list[BuilderSquad]
    unavailable_styles: dict[str, str]


def _objective(frame: pd.DataFrame, columns: list[str], style: str, risk: str) -> pd.DataFrame:
    result = frame.copy()
    ownership = pd.to_numeric(result.ownership, errors="coerce")
    low_ownership = (1 - ownership.clip(0, 100) / 100).fillna(0)
    for col in columns:
        mean = frame[col]
        if style == STYLES[0]:
            continue  # This alternative must truly maximize expected points regardless of risk.
        spread = frame[f"risk_{col}"]
        adjustment = (
            -0.25 * spread
            if risk == "Conservative"
            else 0.25 * spread
            if risk == "Aggressive"
            else 0
        )
        result[col] = mean + adjustment
        if style == "Balanced":
            result[col] -= 0.10 * mean.clip(lower=0) * (1 - frame.reliability_proxy)
        else:
            result[col] += 0.25 * mean.clip(lower=0) * low_ownership
    return result


def build_squads(
    forecast: BuilderForecast,
    rules: Rules,
    *,
    risk: str = "Balanced",
    locked: set[int] | None = None,
    excluded: set[int] | None = None,
    snapshot_at: str | None = None,
) -> BuilderResult:
    if risk not in RISKS or forecast.season != rules.season:
        raise ValueError("Invalid risk preference or mismatched season rules")
    locked, excluded = set(locked or ()), set(excluded or ())
    if not locked <= set(forecast.players.id):
        bad = sorted(locked - set(forecast.players.id))
        raise ValueError(
            f"Locked players have no supported forecast: {bad}. Unlock them or choose another model."
        )
    # Excluding unsupported players is harmless: they are already absent from the pool.
    if locked & excluded:
        raise ValueError("A player cannot be both locked and excluded")
    frame, columns = forecast.players, forecast.columns
    indexed = frame.set_index("id")
    excluded &= set(frame.id)
    result = BuilderResult([], {})
    for style in STYLES:
        adjusted = _objective(frame, columns, style, risk)
        try:
            plan = solve_squad(
                adjusted,
                columns,
                rules,
                locked=locked,
                excluded=excluded,
                different_from=[s.plan.squad for s in result.squads],
            )
        except ValueError as exc:
            if not result.squads or "No proven optimal" not in str(exc):
                raise
            result.unavailable_styles[style] = str(exc)
            continue
        utility = plan.expected_points
        validate_squad(frame, plan.squad, rules)
        weekly = {
            col: sum(float(indexed.at[i, col]) for i in plan.lineups[col])
            + float(indexed.at[plan.captains[col], col])
            for col in columns
        }
        plan = replace(plan, expected_points=sum(weekly.values()), weekly_points=weekly)
        scores = adjusted.set_index("id")
        vice, benches = {}, {}
        for col in columns:
            vice[col] = max(
                (i for i in plan.lineups[col] if i != plan.captains[col]),
                key=lambda i: (scores.at[i, col], indexed.at[i, col], -i),
            )
            benches[col] = sorted(
                set(plan.squad) - set(plan.lineups[col]),
                key=lambda i: (
                    indexed.at[i, "element_type"] != 1,
                    -scores.at[i, col],
                    -indexed.at[i, col],
                    i,
                ),
            )
        table = indexed.loc[plan.squad].reset_index()
        first = columns[0]
        bench = benches[first]
        table["role"] = [
            "Starting XI"
            if i in plan.lineups[first]
            else "Reserve goalkeeper"
            if i == bench[0]
            else f"Bench {bench.index(i)}"
            for i in table.id
        ]
        table["bench_order"] = [
            0 if i in plan.lineups[first] else bench.index(i) + 1 for i in table.id
        ]
        table["captain"] = table.id == plan.captains[first]
        table["vice_captain"] = table.id == vice[first]
        table["locked"] = table.id.isin(locked)
        table["season"] = rules.season
        table["model"] = forecast.model
        table["risk_preference"] = risk
        table["variant"] = style
        table["snapshot_at"] = snapshot_at or "Not recorded"
        table["generated_at"] = datetime.now(UTC).isoformat()
        table["reason"] = [
            f"{'Locked by you; ' if i in locked else ''}selected in the {style.lower()} feasible squad; "
            f"{indexed.at[i, 'horizon_points']:.2f} projected player points over {len(columns)} GWs "
            f"at £{indexed.at[i, 'price']:.1f}m. "
            + (
                f"Ownership {indexed.at[i, 'ownership']:.1f}%. "
                if pd.notna(indexed.at[i, "ownership"])
                else "Ownership unavailable; no differential bonus. "
            )
            + (
                "Objective uses original expected points. "
                if style == STYLES[0]
                else f"Preference adjustments use {indexed.at[i, 'risk_basis']}; these are heuristics, not extra expected points. "
            )
            + (
                "Reserve GK; covers the starting keeper."
                if i == bench[0]
                else "Outfield bench ranked by next-GW preference score; formation-dependent autosub value is not optimized."
                if i in bench
                else "Chosen for the legal next-GW XI."
            )
            for i in table.id
        ]
        table = table.sort_values(["bench_order", "element_type", "id"]).reset_index(drop=True)
        result.squads.append(BuilderSquad(style, risk, plan, utility, vice, benches, table))
    return result


def squad_csv(squad: BuilderSquad) -> str:
    """CSV contains actual forecast rows and prevents spreadsheet formula evaluation."""
    table = squad.table.copy()
    for col in table.columns:
        table[col] = table[col].map(
            lambda v: (
                "'" + v
                if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
                else v
            )
        )
    return table.to_csv(index=False)


def save_squad(squad: BuilderSquad, directory: Path) -> Path:
    """Immutable local drafts only; never save account credentials or execute actions."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"squad-{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}.csv"
    with path.open("x", encoding="utf-8", newline="") as stream:
        stream.write(squad_csv(squad))
    return path


def load_draft(path: Path, players: pd.DataFrame, rules: Rules) -> list[int]:
    """Reload IDs as locks, not as confirmed account ownership or fresh forecasts."""
    table = pd.read_csv(path)
    if not {"id", "season"} <= set(table.columns) or len(table) != 15:
        raise ValueError("Draft must contain 15 players and season metadata")
    if table.season.isna().any() or not (table.season == rules.season).all():
        raise ValueError("Saved draft belongs to a different/unknown season")
    numeric = pd.to_numeric(table.id, errors="raise")
    if not np.isfinite(numeric).all() or not (numeric == np.floor(numeric)).all():
        raise ValueError("Invalid draft player IDs")
    ids = numeric.astype(int).tolist()
    validate_squad(players, ids, rules)
    current = players.set_index("id").loc[ids]
    if "purchasable" in current and not current.purchasable.all():
        raise ValueError(
            "A saved player is no longer purchasable; regenerate without locking that player"
        )
    if current.cost.sum() > rules.budget:
        raise ValueError("Saved squad now exceeds the official budget; regenerate with fewer locks")
    return ids
