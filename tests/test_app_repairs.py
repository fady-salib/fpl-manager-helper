"""Regression coverage for the delivered-model, caching and team setup fixes."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import joblib
import pandas as pd

from fpl_ai.features.history import histories_from_store
from fpl_ai.ml.data import FEATURES
from fpl_ai.ml.registry import load_any, model_path
from fpl_ai.storage import SnapshotStore


def test_bulk_history_lookup_matches_single_and_uses_one_connection(
    tmp_path, bootstrap, monkeypatch
):
    store = SnapshotStore(tmp_path / "snapshots.sqlite")
    now = datetime.now(UTC)
    row = {
        "fixture": 1,
        "round": 1,
        "kickoff_time": "2026-08-01T12:00:00Z",
        "minutes": 90,
        "total_points": 3,
    }
    for pid in (1, 2):
        store.put(f"element-summary/{pid}/", {"history": [row]}, now - timedelta(days=2))
        store.put(f"element-summary/{pid}/", {"history": [{**row, "total_points": 9}]}, now)
    before = now - timedelta(days=1)
    endpoints = [f"element-summary/{i}/" for i in (1, 2)]
    bulk = store.latest_many(endpoints, before)
    assert all(bulk[e] == store.latest(e, before) for e in endpoints)
    calls = []
    original = store.connect

    def connect():
        calls.append(1)
        return original()

    monkeypatch.setattr(store, "connect", connect)
    frame = histories_from_store(store, bootstrap, before)
    assert frame.total_points.tolist() == [3, 3]
    assert len(calls) == 1


def test_registry_and_new_builder_use_same_artifact(tmp_path, bootstrap, history):
    from fpl_ai.forecasting.team_builder import prepare_forecasts

    root = tmp_path / "models"
    root.mkdir()
    artifact = {
        "features": FEATURES,
        "regressors": {"total_points": "recent_form", "minutes": "historical_average"},
        "classifiers": {},
        "metadata": {},
    }
    joblib.dump(artifact, root / "local-20261118.joblib")
    joblib.dump({"models": []}, root / "ensemble.joblib")
    chosen = model_path(root)
    assert chosen.name == "local-20261118.joblib"
    loaded = load_any(chosen)
    fixtures = [
        {
            "id": 1,
            "event": 9,
            "team_h": 1,
            "team_a": 2,
            "team_h_difficulty": 3,
            "team_a_difficulty": 3,
        }
    ]
    forecast = prepare_forecasts(
        bootstrap,
        fixtures,
        history,
        model="Locally trained ML",
        horizon=1,
        artifact=loaded,
        as_of="2026-08-26T00:00:00Z",
    )
    assert not forecast.players.empty
    assert forecast.model == "Locally trained ML"
    assert forecast.players.gw_9.notna().all()


def test_forecast_cache_reuses_result(bootstrap, monkeypatch):
    import sys

    sys.path.insert(0, str(Path(__file__).parents[1] / "app"))
    from components.runtime import cached_rankings

    from fpl_ai.forecasting import rankings

    cached_rankings.clear()
    calls = []
    original = rankings.rank_players

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(rankings, "rank_players", counted)
    for e in bootstrap["events"]:
        e["deadline_time"] = f"2030-08-{e['id'] * 3:02d}T10:00:00Z"
    fixtures = [
        {
            "id": 1,
            "event": 1,
            "team_h": 1,
            "team_a": 2,
            "team_h_difficulty": 3,
            "team_a_difficulty": 3,
        }
    ]
    a = cached_rankings(bootstrap, fixtures, 1, pd.DataFrame(), clock_bucket=1)
    b = cached_rankings(bootstrap, fixtures, 1, pd.DataFrame(), clock_bucket=1)
    pd.testing.assert_frame_equal(a, b)
    assert len(calls) == 1
    cached_rankings.clear()


def test_my_team_loads_public_squad_inline(tmp_path, monkeypatch, bootstrap, players, rules):
    from test_dashboard import _builder_app, _click

    from fpl_ai.api.client import FPLClient
    from fpl_ai.optimization.squad import solve_squad

    app = _builder_app(tmp_path, monkeypatch, bootstrap)
    app.sidebar.radio[0].set_value("My Team").run()
    assert not app.exception
    assert any(n.label == "FPL team name" for n in app.text_input)
    assert not any(n.label == "FPL team ID" for n in app.number_input)
    ids = solve_squad(players, ["gw_9"], rules).squad
    monkeypatch.setattr(
        FPLClient,
        "entry",
        lambda *a, **k: {
            "current_event": 1,
            "name": "Test XI",
            "player_first_name": "Test",
            "player_last_name": "Manager",
        },
    )
    monkeypatch.setattr(
        FPLClient, "picks", lambda *a, **k: {"picks": [{"element": i} for i in ids]}
    )
    monkeypatch.setattr(FPLClient, "entry_history", lambda *a, **k: {"current": []})
    monkeypatch.setattr(
        FPLClient,
        "league_standings",
        lambda *a, **k: {
            "league": {"name": "Test League"},
            "standings": {
                "has_next": False,
                "results": [
                    {
                        "entry": 123,
                        "entry_name": "Test XI",
                        "player_name": "Test Manager",
                        "rank": 1,
                    }
                ],
            },
        },
    )
    next(n for n in app.text_input if n.label == "FPL team name").set_value("Test XI")
    next(n for n in app.text_input if n.label == "Manager name").set_value("Test Manager")
    app.session_state["official_team_id"] = 123
    _click(app, "Find my team")
    _click(app, "Load public past-deadline picks")
    assert not app.exception
    assert set(app.session_state["team_ids"]) == set(ids)
    assert any(m.label == "Projected XI + captain points" for m in app.metric)


def test_ml_and_performance_pages_work_without_fpl_network(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    from fpl_ai.api.client import FPLClient

    def fail(*args, **kwargs):
        raise AssertionError("This page must not request FPL metadata")

    monkeypatch.setenv("FPL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(FPLClient, "bootstrap", fail)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app/main.py"), default_timeout=30)
    for page in ("Local ML", "Model Performance"):
        app.session_state["workspace"] = page
        app.run()
        assert not app.exception


def test_two_names_do_not_trigger_fictitious_global_search(tmp_path, monkeypatch, bootstrap):
    from test_dashboard import _builder_app, _click

    from fpl_ai.api.client import FPLClient

    app = _builder_app(tmp_path, monkeypatch, bootstrap)
    app.sidebar.radio[0].set_value("My Team").run()
    monkeypatch.setattr(
        FPLClient,
        "entry",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("No reference is known")),
    )
    next(n for n in app.text_input if n.label == "FPL team name").set_value("Unknown XI")
    next(n for n in app.text_input if n.label == "Manager name").set_value("Example Manager")
    _click(app, "Find my team")
    assert not app.exception
    assert any("Verify your account once" in e.value for e in app.error)
    assert not any("league" in n.label.lower() for n in app.text_input)


def test_manager_conflict_preserves_existing_squad(
    tmp_path, monkeypatch, bootstrap, players, rules
):
    from test_dashboard import _builder_app, _click

    from fpl_ai.api.client import FPLClient
    from fpl_ai.optimization.squad import solve_squad

    app = _builder_app(tmp_path, monkeypatch, bootstrap)
    app.sidebar.radio[0].set_value("Settings").run()
    app.session_state["official_team_id"] = 123
    app.session_state["team_ids"] = solve_squad(players, ["gw_9"], rules).squad
    before = list(app.session_state["team_ids"])
    monkeypatch.setattr(
        FPLClient,
        "entry",
        lambda *a, **k: {
            "name": "Test XI",
            "player_first_name": "Different",
            "player_last_name": "Manager",
        },
    )
    next(n for n in app.text_input if n.label == "FPL team name").set_value("Test XI")
    next(n for n in app.text_input if n.label == "Manager name").set_value("Example Manager")
    _click(app, "Find my team")
    assert not app.exception
    assert any("did not match both names" in e.value for e in app.error)
    assert app.session_state["team_ids"] == before
