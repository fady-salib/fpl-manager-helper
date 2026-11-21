"""Offline UI smoke using deterministic fixtures only; live smoke is recorded separately."""

from pathlib import Path


def test_pages_and_populated_pitch(tmp_path, monkeypatch, bootstrap, players, rules):
    from streamlit.testing.v1 import AppTest

    from fpl_ai.api.client import FPLClient
    from fpl_ai.optimization.squad import solve_squad

    monkeypatch.setenv("FPL_DATA_DIR", str(tmp_path / "data"))
    # Unit-only future dates make the dashboard independent of today's real deadline.
    for event in bootstrap["events"]:
        event["deadline_time"] = f"2030-08-{event['id'] * 3:02d}T10:00:00Z"
    fixtures = [
        {
            "id": event * 10 + team,
            "event": event,
            "team_h": team,
            "team_a": team + 1,
            "team_h_difficulty": 3,
            "team_a_difficulty": 3,
        }
        for event in range(1, 10)
        for team in (1, 3, 5, 7, 9)
    ]
    monkeypatch.setattr(FPLClient, "bootstrap", lambda *a, **k: bootstrap)
    monkeypatch.setattr(FPLClient, "fixtures", lambda *a, **k: fixtures)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app/main.py"), default_timeout=30)
    app.run()
    assert not app.exception
    app.session_state["team_ids"] = solve_squad(players, ["gw_9"], rules).squad
    for page in (
        "New Team Builder",
        "My Team",
        "Player Rankings",
        "Transfers",
        "Captaincy",
        "Fixture Planner",
        "Chip Planner",
        "Model Performance",
        "Settings",
    ):
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, f"Page failed: {page}"


def _builder_app(tmp_path, monkeypatch, bootstrap, initial_locks=()):
    from streamlit.testing.v1 import AppTest

    from fpl_ai.api.client import FPLClient

    monkeypatch.setenv("FPL_DATA_DIR", str(tmp_path / "data"))
    for e in bootstrap["events"]:
        e["deadline_time"] = f"2030-08-{e['id'] * 3:02d}T10:00:00Z"
    fixtures = [
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
    monkeypatch.setattr(FPLClient, "bootstrap", lambda *a, **k: bootstrap)
    monkeypatch.setattr(FPLClient, "fixtures", lambda *a, **k: fixtures)
    app = AppTest.from_file(
        str(Path(__file__).parents[1] / "app/main.py"), default_timeout=45
    ).run()
    app.session_state["builder_locks"] = list(initial_locks)
    app.sidebar.radio[0].set_value("New Team Builder").run()
    assert not app.exception
    return app


def _click(app, label):
    return next(b for b in app.button if b.label == label).click().run(timeout=45)


def test_new_team_no_id_generate_export_save_reload_and_weekly_handoff(
    tmp_path, monkeypatch, bootstrap
):
    from fpl_ai.api.client import FPLClient

    app = _builder_app(tmp_path, monkeypatch, bootstrap)
    app.multiselect(key="builder_locks").set_value([1, 5])
    app.multiselect(key="builder_exclusions").set_value([2, 6])
    _click(app, "Generate three squads")
    assert not app.exception
    squads = app.session_state["builder_results"][2].squads
    assert len(squads) == 3
    assert all({1, 5} <= set(s.plan.squad) and not {2, 6} & set(s.plan.squad) for s in squads)
    assert "team_ids" not in app.session_state
    assert "official_team_id" not in app.session_state
    assert len(app.get("download_button")) == 1
    _click(app, "Save draft locally")
    assert not app.exception
    saved = list((tmp_path / "data/processed/new-teams").glob("squad-*.csv"))
    assert len(saved) == 1
    _click(app, "Load saved draft as player locks")
    assert not app.exception
    assert len(app.session_state["builder_locks"]) == 15
    assert "team_ids" not in app.session_state
    _click(app, "Open weekly management Settings")
    assert not app.exception and app.sidebar.radio[0].value == "Settings"
    ids = squads[0].plan.squad
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
    assert app.session_state["official_team_id"] == 123
    assert app.session_state["confirmed"] is False
    assert app.session_state["sales"] == {}


def test_builder_error_does_not_leave_previous_draft_as_a_new_result(
    tmp_path, monkeypatch, bootstrap
):
    app = _builder_app(tmp_path, monkeypatch, bootstrap)
    _click(app, "Generate three squads")
    assert not app.exception and "builder_results" in app.session_state
    app.multiselect(key="builder_locks").set_value([1])
    app.multiselect(key="builder_exclusions").set_value([1])
    _click(app, "Generate three squads")
    assert not app.exception
    assert "builder_results" not in app.session_state
    assert any("both locked" in e.value for e in app.error)


def test_builder_preserves_obsolete_locks_and_refuses_missing_ml(tmp_path, monkeypatch, bootstrap):
    app = _builder_app(tmp_path, monkeypatch, bootstrap, initial_locks=[999])
    _click(app, "Generate three squads")
    assert not app.exception
    assert app.session_state["builder_locks"] == [999]
    assert any("no supported forecast" in e.value for e in app.error)
    # Isolate local artifact discovery from an actual developer model, if any.
    monkeypatch.chdir(tmp_path)
    app.multiselect(key="builder_locks").set_value([])
    app.selectbox(key="builder_model").set_value("Locally trained ML")
    _click(app, "Generate three squads")
    assert not app.exception
    assert any("No local ML model" in e.value for e in app.error)
    assert "builder_results" not in app.session_state


def test_new_registration_without_published_picks_is_handled(tmp_path, monkeypatch, bootstrap):
    from fpl_ai.api.client import FPLClient

    app = _builder_app(tmp_path, monkeypatch, bootstrap)
    _click(app, "Open weekly management Settings")
    monkeypatch.setattr(
        FPLClient,
        "entry",
        lambda *a, **k: {
            "current_event": 0,
            "name": "Test XI",
            "player_first_name": "Test",
            "player_last_name": "Manager",
        },
    )
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
    assert any("before your first deadline" in e.value for e in app.error)
    assert app.session_state["confirmed"] is False
    assert app.session_state["team_ids"] == []


def test_builder_source_refresh_invalidates_old_exports(tmp_path, monkeypatch, bootstrap):
    app = _builder_app(tmp_path, monkeypatch, bootstrap)
    _click(app, "Generate three squads")
    assert not app.exception and len(app.get("download_button")) == 1
    bootstrap["elements"][0]["now_cost"] += 1
    _click(app, "Refresh live data")
    assert not app.exception
    assert any("source data changed" in i.value for i in app.info)
    assert len(app.get("download_button")) == 0
