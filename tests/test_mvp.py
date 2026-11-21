from datetime import UTC, datetime, timedelta

import httpx
import pytest

from fpl_ai.api.client import DataError, FPLClient
from fpl_ai.forecasting.rankings import rank_players
from fpl_ai.storage import SnapshotStore


def test_cache_roundtrip_and_cutoff(tmp_path):
    store = SnapshotStore(tmp_path / "cache.sqlite")
    now = datetime.now(UTC)
    store.put("x/", {"a": 1}, now - timedelta(hours=2))
    store.put("x/", {"a": 2}, now)
    assert store.latest("x/")[1] == {"a": 2}
    assert store.latest("x/", now - timedelta(hours=1))[1] == {"a": 1}
    assert store.latest("x/", now - timedelta(hours=3)) is None


def test_client_cache_and_schema(tmp_path, bootstrap):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=bootstrap)

    with FPLClient(
        SnapshotStore(tmp_path / "db"), interval=0, transport=httpx.MockTransport(respond)
    ) as c:
        assert c.bootstrap() == c.bootstrap()
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert "cookie" not in calls[0].headers


@pytest.mark.parametrize("status", [401, 403, 404])
def test_http_errors(tmp_path, status):
    with FPLClient(
        SnapshotStore(tmp_path / "db"),
        interval=0,
        transport=httpx.MockTransport(lambda r: httpx.Response(status)),
    ) as c:
        with pytest.raises(DataError, match=str(status)):
            c.bootstrap()


def test_retry_429_then_success(tmp_path, monkeypatch):
    monkeypatch.setattr("fpl_ai.api.client.time.sleep", lambda _: None)
    responses = iter(
        [httpx.Response(429, headers={"Retry-After": "1"}), httpx.Response(200, json=[])]
    )
    with FPLClient(
        SnapshotStore(tmp_path / "db"),
        interval=0,
        transport=httpx.MockTransport(lambda r: next(responses)),
    ) as c:
        assert c.fixtures() == []


def test_invalid_schema(tmp_path):
    with FPLClient(
        SnapshotStore(tmp_path / "db"),
        interval=0,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"elements": []})),
    ) as c:
        with pytest.raises(DataError, match="schema"):
            c.bootstrap()


@pytest.mark.parametrize("bad", [0, -1, "1", True])
def test_invalid_id(bad):
    with pytest.raises(ValueError):
        FPLClient._id(bad)


def test_blank_and_double_gameweek(bootstrap):
    fixture = {
        "id": 1,
        "event": 2,
        "team_h": 1,
        "team_a": 2,
        "team_h_difficulty": 3,
        "team_a_difficulty": 3,
    }
    table = rank_players(
        bootstrap, [fixture, {**fixture, "id": 2}], horizon=1, as_of="2026-08-05T00:00:00Z"
    )
    assert table[table.team == 1].iloc[0].fixture_count == 2
    assert table[table.team == 1].iloc[0].next_points == pytest.approx(7.4)
    assert (table[~table.team.isin([1, 2])].next_points == 0).all()


@pytest.mark.parametrize(
    "endpoint",
    ["//attacker.test/", "https://attacker.test/", "../entry/1/", "fixtures/?x=1", "my-team/1/"],
)
def test_only_public_endpoints(tmp_path, endpoint):
    with FPLClient(SnapshotStore(tmp_path / "db")) as client:
        with pytest.raises(ValueError, match="Unsupported public"):
            client.get(endpoint)


def test_429_long_cooldown_not_ignored(tmp_path):
    with FPLClient(
        SnapshotStore(tmp_path / "db"),
        interval=0,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(429, headers={"Retry-After": "3600"})
        ),
    ) as client:
        with pytest.raises(DataError, match="cooldown"):
            client.fixtures()


def test_unavailable_api_never_silently_returns_old_data(tmp_path, monkeypatch):
    monkeypatch.setattr("fpl_ai.api.client.time.sleep", lambda _: None)
    store = SnapshotStore(tmp_path / "db")
    store.put("fixtures/", [], datetime.now(UTC) - timedelta(days=1))

    def unavailable(request):
        raise httpx.ConnectError("offline", request=request)

    with FPLClient(
        store, retries=1, interval=0, transport=httpx.MockTransport(unavailable)
    ) as client:
        with pytest.raises(DataError, match="after retries"):
            client.fixtures()


def test_unknown_season_rejected(bootstrap):
    from fpl_ai.rules import Rules

    bootstrap["game_config"]["settings"]["static_content_url"] = "https://example.test/2027_28/"
    with pytest.raises(ValueError, match="need review"):
        Rules.from_bootstrap(bootstrap)


def test_event_rule_changes_rejected(rules):
    with pytest.raises(ValueError, match="overrides"):
        rules.validate_event({"id": 10, "overrides": {"rules": {"transfers_cost": 0}}})


def test_retry_after_http_date(tmp_path, monkeypatch):
    from email.utils import format_datetime

    monkeypatch.setattr("fpl_ai.api.client.time.sleep", lambda _: None)
    header = format_datetime(datetime.now(UTC) + timedelta(hours=1))
    with FPLClient(
        SnapshotStore(tmp_path / "db"),
        interval=0,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(429, headers={"Retry-After": header})
        ),
    ) as client:
        with pytest.raises(DataError, match="cooldown"):
            client.fixtures()
