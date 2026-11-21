import pytest

from fpl_ai.optimization.planning import beam_plan
from fpl_ai.optimization.squad import alternatives, selling_price, solve_squad, validate_squad


def test_budget_positions_club_formation_captain(players, rules):
    plan = solve_squad(players, ["gw_9", "gw_10"], rules, budget=750)
    validate_squad(players, plan.squad, rules)
    assert plan.bank == 0
    indexed = players.set_index("id")
    for col, xi in plan.lineups.items():
        assert len(xi) == 11 and plan.captains[col] in xi
        for position in rules.squad:
            assert (
                rules.min_play[position]
                <= sum(indexed.at[i, "element_type"] == position for i in xi)
                <= rules.max_play[position]
            )
    assert plan.expected_points == pytest.approx(sum(plan.weekly_points.values()))


def test_infeasible_never_relaxed(players, rules):
    with pytest.raises(ValueError, match="No proven optimal"):
        solve_squad(players, ["gw_9"], rules, budget=100)


def test_sales_and_roll_and_hits(players, rules):
    owned = solve_squad(players, ["gw_10"], rules).squad
    sales = dict.fromkeys(owned, 40)
    plans = alternatives(
        players,
        ["gw_9"],
        rules,
        owned=owned,
        sale_prices=sales,
        bank=20,
        free_transfers=0,
        max_transfers=2,
    )
    roll = next(p for p in plans if not p.transfers_in)
    assert roll.bank == 20 and roll.hit == 0
    for plan in plans:
        assert plan.hit == 4 * len(plan.transfers_in)
        assert plan.bank == 20 - 10 * len(plan.transfers_in)
        assert plan.expected_points == pytest.approx(plan.weekly_points["gw_9"] - plan.hit)


def test_missing_sales_rejected(players, rules):
    owned = solve_squad(players, ["gw_9"], rules).squad
    with pytest.raises(ValueError, match="selling prices"):
        solve_squad(players, ["gw_9"], rules, owned=owned)


@pytest.mark.parametrize("purchase,current,result", [(50, 55, 52), (50, 51, 50), (50, 48, 48)])
def test_sell_profit_rounding(purchase, current, result):
    assert selling_price(purchase, current) == result


def test_free_transfer_chip_interactions(rules):
    assert rules.next_free_transfers(5, 0) == 5
    assert rules.next_free_transfers(2, 3) == 1
    assert rules.next_free_transfers(2, 8, "wildcard") == 2
    assert not rules.chip_allowed("freehit", 9, {3}, "freehit")
    assert not rules.chip_allowed("bboost", 20, {1})


def test_beam_state(players, rules):
    owned = solve_squad(players, ["gw_9"], rules).squad
    path = beam_plan(
        players,
        ["gw_9", "gw_10"],
        rules,
        owned=owned,
        bank=0,
        sales=dict.fromkeys(owned, 50),
        free=1,
        width=2,
    )
    assert len(path.steps) == 2
    assert path.bank >= 0 and 1 <= path.free <= 5
    assert path.score == pytest.approx(
        sum(
            p.weekly_points[col] - p.hit
            for p, col in zip(path.steps, ["gw_9", "gw_10"], strict=True)
        )
    )


def test_blank_week_objective(players, rules):
    p = players.copy()
    p["blank"] = 0.0
    plan = solve_squad(p, ["blank"], rules)
    assert plan.expected_points == 0


def test_unavailable_player_not_purchased(players, rules):
    p = players.copy()
    p["purchasable"] = True
    p.loc[p.id == 30, "gw_9"] = 1000
    p.loc[p.id == 30, "purchasable"] = False
    assert 30 not in solve_squad(p, ["gw_9"], rules).squad


def test_chip_multipliers_and_free_transfers(players, rules):
    base = solve_squad(players, ["gw_9"], rules)
    common = dict(
        owned=base.squad, bank=0, sale_prices=dict.fromkeys(base.squad, 50), fixed_squad=True
    )
    bb = solve_squad(players, ["gw_9"], rules, chip="bboost", **common)
    p = players.set_index("id")
    assert bb.expected_points == pytest.approx(
        sum(p.at[i, "gw_9"] for i in bb.squad) + p.at[bb.captains["gw_9"], "gw_9"]
    )
    tc = solve_squad(players, ["gw_9"], rules, chip="3xc", **common)
    assert tc.expected_points == pytest.approx(
        base.expected_points + p.at[base.captains["gw_9"], "gw_9"]
    )
    wildcard = solve_squad(
        players,
        ["gw_10"],
        rules,
        owned=base.squad,
        bank=0,
        sale_prices=dict.fromkeys(base.squad, 50),
        free_transfers=0,
        max_transfers=0,
        chip="wildcard",
    )
    assert wildcard.hit == 0


def test_free_hit_reversion_and_chip_consumption(players, rules):
    from dataclasses import replace

    from fpl_ai.optimization.chip_planning import plan_chips

    # Isolate Free Hit as the only permitted action, with a deliberately different next-week optimum.
    r = replace(rules, chips=({"id": 3, "name": "freehit", "start_event": 9, "stop_event": 9},))
    owned = solve_squad(players, ["gw_10"], rules).squad
    result = plan_chips(
        players,
        ["gw_9"],
        r,
        owned=owned,
        sales=dict.fromkeys(owned, 50),
        bank=0,
        free=2,
        available_ids={3},
        max_transfers=0,
        width=2,
    )
    assert result.steps[0].chip == "freehit"
    assert result.squad == owned and result.bank == 0 and result.free == 2
    assert result.available == set()


def test_unproven_incumbent_is_not_reported_as_optimal(players, rules, monkeypatch):
    import pulp

    original = pulp.LpProblem.solve

    def time_limited(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.sol_status = pulp.LpSolutionIntegerFeasible
        return pulp.LpStatusOptimal

    monkeypatch.setattr(pulp.LpProblem, "solve", time_limited)
    with pytest.raises(ValueError, match="No proven optimal"):
        solve_squad(players, ["gw_9"], rules)
