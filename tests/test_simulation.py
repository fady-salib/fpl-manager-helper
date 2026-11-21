import numpy as np
import pytest

from fpl_ai.forecasting.components import REQUIRED, simulate_player
from fpl_ai.simulation.scoring import score_lineup


def setup_lineup():
    positions = dict(zip(range(1, 16), [1, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 1, 3, 2, 2], strict=True))
    return (
        list(range(1, 12)),
        [12, 13, 14, 15],
        positions,
        dict.fromkeys(range(1, 16), 2),
        dict.fromkeys(range(1, 16), True),
    )


def test_all_appear_captain_and_bench_boost(rules):
    xi, bench, positions, pts, plays = setup_lineup()
    assert score_lineup(xi, bench, 9, 5, positions, pts, plays, rules) == 24
    assert score_lineup(xi, bench, 9, 5, positions, pts, plays, rules, chip="bboost") == 32
    assert score_lineup(xi, bench, 9, 5, positions, pts, plays, rules, chip="3xc") == 26


def test_missing_defender_skips_midfielder_and_captain_fallback(rules):
    xi, bench, positions, pts, plays = setup_lineup()
    plays[2] = plays[9] = False
    pts[2] = pts[9] = 0
    pts[13] = 8
    pts[14] = 7
    # One DEF and one FWD missing: MID + DEF both allowed, preserves >=3 DEF and >=1 FWD.
    assert score_lineup(xi, bench, 9, 5, positions, pts, plays, rules) == 35
    plays[9] = True
    pts[9] = 2
    assert score_lineup(xi, bench, 9, 5, positions, pts, plays, rules) == 29


def test_keeper_negative_and_no_captains(rules):
    xi, bench, positions, pts, plays = setup_lineup()
    plays[1] = plays[9] = plays[5] = False
    pts[1] = pts[9] = pts[5] = 0
    pts[12] = -2
    assert score_lineup(xi, bench, 9, 5, positions, pts, plays, rules) == 18


def test_zero_points_is_appearance(rules):
    xi, bench, positions, pts, plays = setup_lineup()
    pts[9] = 0
    assert score_lineup(xi, bench, 9, 5, positions, pts, plays, rules) == 20


def test_component_determinism_and_blank(history, rules):
    h = history[history.player_id == 1].copy()
    for col in REQUIRED - set(h.columns):
        h[col] = 0
    a = simulate_player(h, "MID", rules, samples=1000)
    b = simulate_player(h, "MID", rules, samples=1000)
    np.testing.assert_array_equal(a["draws"], b["draws"])
    assert a["p10"] <= a["mean"] <= a["p90"]
    blank = simulate_player(h, "MID", rules, fixtures=0, samples=1000)
    assert blank["mean"] == 0 and blank["appearance_probability"] == 0
    with pytest.raises(ValueError, match="all scoring"):
        simulate_player(h.drop(columns="saves"), "MID", rules)


def test_stochastic_lineup_fallback_and_risk(players, rules):
    from fpl_ai.optimization.lineup import optimize_lineup, utility
    from fpl_ai.optimization.squad import solve_squad

    ids = solve_squad(players, ["gw_9"], rules).squad
    p = players[players.id.isin(ids)].copy()
    distributions = {
        i: {"draws": np.full(8, float(i % 7)), "appeared": np.ones(8, dtype=bool)} for i in ids
    }
    result = optimize_lineup(p, rules, distributions, max_passes=0)
    assert len(result["xi"]) == 11 and len(result["bench"]) == 4
    assert result["captain"] != result["vice"]
    assert result["expected_points"] == pytest.approx(
        sum(i % 7 for i in result["xi"]) + result["captain"] % 7
    )
    assert utility(np.array([0, 10]), "Conservative") < utility(np.array([0, 10]), "Aggressive")
