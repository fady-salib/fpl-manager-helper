"""Deterministic unit fixtures; no artificial data enter the real dashboard pipeline."""

from dataclasses import replace
from io import StringIO

import numpy as np
import pandas as pd
import pytest

from fpl_ai.forecasting.components import REQUIRED
from fpl_ai.forecasting.team_builder import prepare_forecasts
from fpl_ai.optimization.squad import solve_squad, validate_squad
from fpl_ai.optimization.team_builder import build_squads, load_draft, save_squad, squad_csv


@pytest.fixture
def fixtures():
    return [
        {
            "id": gw * 10 + team,
            "event": gw,
            "team_h": team,
            "team_a": team + 1,
            "team_h_difficulty": 3,
            "team_a_difficulty": 3,
        }
        for gw in range(1, 10)
        for team in (1, 3, 5, 7, 9)
    ]


def forecast(bootstrap, fixtures, horizon=3):
    return prepare_forecasts(
        bootstrap, fixtures, pd.DataFrame(), horizon=horizon, as_of="2026-08-02T00:00:00Z"
    )


@pytest.mark.parametrize("horizon", [1, 3, 5, 8])
@pytest.mark.parametrize("risk", ["Conservative", "Balanced", "Aggressive"])
def test_all_new_squad_constraints_and_real_point_totals(bootstrap, fixtures, rules, horizon, risk):
    f = forecast(bootstrap, fixtures, horizon)
    result = build_squads(f, rules, risk=risk)
    assert len(result.squads) == 3
    assert len({tuple(sorted(s.plan.squad)) for s in result.squads}) == 3
    p = f.players.set_index("id")
    for s in result.squads:
        validate_squad(f.players, s.plan.squad, rules)
        assert p.loc[s.plan.squad].cost.sum() + s.plan.bank == rules.budget
        assert s.plan.bank >= 0 and s.plan.hit == 0
        assert len(s.table) == 15 and s.table.reason.notna().all()
        expected = 0
        for col in f.columns:
            xi, cap, vice = s.plan.lineups[col], s.plan.captains[col], s.vice[col]
            assert len(xi) == len(set(xi)) == 11
            assert cap in xi and vice in xi and cap != vice
            assert set(xi).isdisjoint(s.bench[col]) and set(xi + s.bench[col]) == set(s.plan.squad)
            assert len(s.bench[col]) == 4
            assert p.at[s.bench[col][0], "element_type"] == 1
            assert all(p.at[i, "element_type"] != 1 for i in s.bench[col][1:])
            for pos in rules.squad:
                assert (
                    rules.min_play[pos]
                    <= sum(p.at[i, "element_type"] == pos for i in xi)
                    <= rules.max_play[pos]
                )
            weekly = sum(p.at[i, col] for i in xi) + p.at[cap, col]
            assert s.plan.weekly_points[col] == pytest.approx(weekly)
            expected += weekly
        assert s.plan.expected_points == pytest.approx(expected)
        assert len(s.table.filter(regex=r"^fixtures_\d+$").columns) == horizon


def test_locks_exclusions_and_distinct_variants(bootstrap, fixtures, rules):
    f = forecast(bootstrap, fixtures)
    result = build_squads(f, rules, locked={1, 5}, excluded={2, 6})
    for s in result.squads:
        assert {1, 5} <= set(s.plan.squad)
        assert not {2, 6} & set(s.plan.squad)


@pytest.mark.parametrize(
    "locked,excluded,match",
    [
        ({1}, {1}, "both locked"),
        ({999}, set(), "no usable forecast"),
        (set(range(1, 17)), set(), "more than 15"),
    ],
)
def test_generic_optimizer_invalid_lock_inputs(players, rules, locked, excluded, match):
    with pytest.raises(ValueError, match=match):
        solve_squad(players, ["gw_9"], rules, locked=locked, excluded=excluded)


def test_lock_conflicts_never_relax_rules(bootstrap, fixtures, rules):
    f = forecast(bootstrap, fixtures)
    # Three goalkeepers exceed the official two-player positional allowance.
    with pytest.raises(ValueError, match="No proven optimal"):
        build_squads(f, rules, locked={1, 2, 3})
    with pytest.raises(ValueError, match="No proven optimal"):
        build_squads(f, replace(rules, budget=700))
    with pytest.raises(ValueError, match="No proven optimal"):
        build_squads(f, rules, excluded={1, 2, 3})


def test_fully_locked_squad_reports_alternatives_unavailable(bootstrap, fixtures, rules):
    f = forecast(bootstrap, fixtures)
    owned = solve_squad(f.players, f.columns, rules).squad
    result = build_squads(f, rules, locked=set(owned))
    assert len(result.squads) == 1 and len(result.unavailable_styles) == 2
    assert set(result.squads[0].plan.squad) == set(owned)


def test_risk_changes_selection_but_does_not_inflate_expected_points(bootstrap, fixtures, rules):
    f = forecast(bootstrap, fixtures, 1)
    p = f.players.copy()
    col = f.columns[0]
    p[col] = 2.0
    p[f"risk_{col}"] = 0.0
    p["reliability_proxy"] = 1.0
    base = solve_squad(p, [col], rules).squad
    removed = next(i for i in base if p.set_index("id").at[i, "element_type"] == 4)
    locked = set(base) - {removed}
    candidates = p[(p.element_type == 4) & ~p.id.isin(locked)].id.tolist()
    maximum, volatile, stable, *rest = candidates
    p.loc[p.id == maximum, col] = 20
    p.loc[p.id == volatile, [col, f"risk_{col}"]] = [10, 40]
    p.loc[p.id == stable, col] = 9
    p["horizon_points"] = p[col]
    p["next_points"] = p[col]
    f = replace(f, players=p)
    safe = build_squads(f, rules, risk="Conservative", locked=locked, excluded=set(rest)).squads
    risky = build_squads(f, rules, risk="Aggressive", locked=locked, excluded=set(rest)).squads
    assert maximum in safe[0].plan.squad and maximum in risky[0].plan.squad
    assert stable in safe[1].plan.squad
    assert volatile in risky[1].plan.squad
    assert risky[1].utility != pytest.approx(risky[1].plan.expected_points)


def test_differentials_use_observed_ownership(bootstrap, fixtures, rules):
    f = forecast(bootstrap, fixtures, 1)
    p = f.players.copy()
    col = f.columns[0]
    p[col] = 5.0
    p["horizon_points"] = 5.0
    p["ownership"] = 100.0
    # The differential variant is selected after two exact distinct-squad constraints.
    # Among equally predicted players it prefers the observed low-ownership group.
    p.loc[p.id % 2 == 0, "ownership"] = 0
    result = build_squads(replace(f, players=p), rules)
    rare = result.squads[2].table
    assert (rare.ownership == 0).sum() >= (result.squads[0].table.ownership == 0).sum()
    assert result.squads[2].plan.expected_points == pytest.approx(60)


def test_model_prerequisites_and_missing_event_fields(bootstrap, fixtures, history):
    with pytest.raises(ValueError, match="No local ML"):
        prepare_forecasts(bootstrap, fixtures, pd.DataFrame(), model="Locally trained ML")
    with pytest.raises(ValueError, match="needs real histories"):
        prepare_forecasts(bootstrap, fixtures, pd.DataFrame(), model="Event simulation")
    with pytest.raises(ValueError, match="No players"):
        prepare_forecasts(
            bootstrap,
            fixtures,
            history,
            model="Event simulation",
            horizon=1,
            as_of="2026-08-05T00:00:00Z",
        )


def test_event_forecast_is_deterministic_and_excludes_future_history(
    bootstrap, fixtures, history, rules
):
    h = history.copy()
    for name in REQUIRED - set(h.columns):
        h[name] = 0.0
    a = prepare_forecasts(
        bootstrap,
        fixtures,
        h,
        model="Event simulation",
        horizon=1,
        as_of="2026-08-05T00:00:00Z",
        samples=100,
    )
    changed = h.copy()
    changed.loc[changed["round"] >= 2, ["minutes", "expected_goals"]] = [90, 1000]
    b = prepare_forecasts(
        bootstrap,
        fixtures,
        changed,
        model="Event simulation",
        horizon=1,
        as_of="2026-08-05T00:00:00Z",
        samples=100,
    )
    pd.testing.assert_series_equal(a.players.gw_2, b.players.gw_2)
    assert a.model == "Event simulation"
    assert set(a.players.id) <= set(h.player_id)
    with pytest.raises(ValueError, match="no supported forecast"):
        build_squads(
            a,
            rules,
            locked={30},
        )


def test_local_ml_predictions_are_used(bootstrap, fixtures):
    class KnownPredictor:
        def predict(self, X):
            return np.full(len(X), 7.25)

    f = prepare_forecasts(
        bootstrap,
        fixtures,
        pd.DataFrame(),
        horizon=1,
        model="Locally trained ML",
        artifact={"models": [KnownPredictor()]},
        as_of="2026-08-02T00:00:00Z",
    )
    assert np.allclose(f.players.gw_1, 7.25)
    assert (f.players.source == "Locally trained ML").all()


def test_csv_and_local_save_reload(bootstrap, fixtures, rules, tmp_path):
    f = forecast(bootstrap, fixtures)
    squad = build_squads(f, rules).squads[0]
    exported = pd.read_csv(StringIO(squad_csv(squad)))
    assert set(exported.id) == set(squad.plan.squad)
    assert {
        "price",
        "reason",
        "captain",
        "vice_captain",
        "bench_order",
        "season",
        *f.columns,
    } <= set(exported)
    path = save_squad(squad, tmp_path / "drafts")
    assert set(load_draft(path, f.players, rules)) == set(squad.plan.squad)
    assert save_squad(squad, path.parent) != path
    changed = f.players.copy()
    changed["cost"] = 100
    with pytest.raises(ValueError, match="now exceeds"):
        load_draft(path, changed, rules)
    exported["season"] = "2099_00"
    exported.to_csv(path, index=False)
    with pytest.raises(ValueError, match="different/unknown season"):
        load_draft(path, f.players, rules)


def test_csv_blocks_spreadsheet_formulas(bootstrap, fixtures, rules):
    squad = build_squads(forecast(bootstrap, fixtures), rules).squads[0]
    squad.table.loc[0, "name"] = "=1+1"
    data = pd.read_csv(StringIO(squad_csv(squad)))
    assert data.loc[0, "name"] == "'=1+1"


def test_batched_ml_freezes_features_for_all_future_gameweeks(bootstrap, fixtures):
    class CountingPredictor:
        def __init__(self):
            self.calls = []

        def predict(self, X):
            self.calls.append(X.copy())
            return np.full(len(X), 4.25)

    predictor = CountingPredictor()
    f = prepare_forecasts(
        bootstrap,
        fixtures,
        pd.DataFrame(),
        model="Locally trained ML",
        horizon=8,
        artifact={"models": [predictor]},
        as_of="2026-08-02T00:00:00Z",
    )
    assert len(predictor.calls) == 1
    assert len(predictor.calls[0]) == len(bootstrap["elements"])
    assert np.allclose(f.players[f.columns], 4.25)


def test_no_scheduled_fixtures_produces_zero_not_invented_matches(bootstrap, rules):
    f = forecast(bootstrap, [], 1)
    assert (f.players.next_points == 0).all()
    assert (f.players.fixtures_1 == "BLANK").all()
    result = build_squads(f, rules)
    assert all(s.plan.expected_points == 0 for s in result.squads)


def test_changed_season_constraints_are_taken_from_rules(bootstrap, fixtures, rules):
    changed = replace(rules, budget=750, club_limit=2, min_play={**rules.min_play, 2: 4})
    f = forecast(bootstrap, fixtures, 3)
    result = build_squads(f, changed)
    for s in result.squads:
        p = f.players.set_index("id")
        assert p.loc[s.plan.squad].cost.sum() == 750 and s.plan.bank == 0
        assert p.loc[s.plan.squad].team.value_counts().max() <= 2
        assert all(
            sum(p.at[i, "element_type"] == 2 for i in xi) >= 4 for xi in s.plan.lineups.values()
        )


def test_horizon_shortens_at_season_end_without_inventing_events(bootstrap, fixtures, rules):
    f = prepare_forecasts(
        bootstrap, fixtures, pd.DataFrame(), horizon=8, as_of="2026-08-25T00:00:00Z"
    )
    assert f.columns == ["gw_9"]
    assert any("Only 1 upcoming" in note for note in f.notes)
    assert len(build_squads(f, rules).squads) == 3
