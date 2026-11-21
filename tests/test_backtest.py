import pandas as pd
import pytest

from fpl_ai.backtesting.walkforward import deadline_snapshot
from fpl_ai.storage import SnapshotStore


def test_backtest_refuses_future_snapshot(tmp_path):
    store = SnapshotStore(tmp_path / "db")
    store.put("bootstrap-static/", {}, pd.Timestamp("2026-10-02", tz="UTC").to_pydatetime())
    with pytest.raises(ValueError, match="Missing pre-deadline"):
        deadline_snapshot(store, "bootstrap-static/", pd.Timestamp("2026-10-01", tz="UTC"))


def test_backtest_refuses_stale_snapshot(tmp_path):
    store = SnapshotStore(tmp_path / "db")
    store.put("fixtures/", [], pd.Timestamp("2026-09-01", tz="UTC").to_pydatetime())
    with pytest.raises(ValueError, match="Missing pre-deadline"):
        deadline_snapshot(store, "fixtures/", pd.Timestamp("2026-10-01", tz="UTC"))


def test_walkforward_uses_predeadline_team_and_realized_rules(tmp_path, bootstrap):
    from datetime import timedelta

    from fpl_ai.backtesting.walkforward import run_backtest

    store = SnapshotStore(tmp_path / "db")
    fixtures = [
        {
            "id": event * 10 + team,
            "event": event,
            "team_h": team,
            "team_a": team + 1,
            "team_h_difficulty": 3,
            "team_a_difficulty": 3,
        }
        for event in (2, 3)
        for team in (1, 3, 5, 7, 9)
    ]
    for event in (2, 3):
        deadline = pd.Timestamp(bootstrap["events"][event - 1]["deadline_time"]).to_pydatetime()
        store.put("bootstrap-static/", bootstrap, deadline - timedelta(hours=1))
        store.put("fixtures/", fixtures, deadline - timedelta(hours=1))
        live = {
            "elements": [
                {
                    "id": p["id"],
                    "stats": {"total_points": 2, "minutes": 90, "red_cards": 0, "yellow_cards": 0},
                }
                for p in bootstrap["elements"]
            ]
        }
        store.put(f"event/{event}/live/", live, deadline + timedelta(days=1))
    result = run_backtest(store, [2, 3])
    assert result["total_points"] == 48
    assert result["average_points"] == 24
    assert result["weeks"][0]["next_free_transfers"] == 1
    assert all(len(w["squad"]) == 15 for w in result["weeks"])


def test_history_reads_respect_snapshot_cutoff(tmp_path, bootstrap):
    from fpl_ai.features.history import histories_from_store

    store = SnapshotStore(tmp_path / "db")
    store.put(
        "element-summary/1/", {"history": []}, pd.Timestamp("2026-10-02", tz="UTC").to_pydatetime()
    )
    # A future snapshot must not masquerade as a historical pre-deadline observation.
    assert histories_from_store(
        store, bootstrap, before=pd.Timestamp("2026-10-01", tz="UTC").to_pydatetime()
    ).empty
