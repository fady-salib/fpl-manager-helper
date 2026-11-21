"""Public name-search scope, duplicate safety, caching schema and pagination tests."""

import httpx
import pytest

from fpl_ai.api.client import FPLClient
from fpl_ai.storage import SnapshotStore
from fpl_ai.teams.search import league_id, search_teams, validate_name

LINK = "https://fantasy.premierleague.com/leagues/123/standings/c"


@pytest.mark.parametrize("link", [LINK, LINK + "/?page_standings=4"])
def test_accept_classic_league_url(link):
    assert league_id(link) == 123


@pytest.mark.parametrize(
    "link",
    [
        "123456",
        "https://example.com/leagues/123/standings/c",
        "https://fantasy.premierleague.com.evil/leagues/1/standings/c",
        "http://fantasy.premierleague.com/leagues/1/standings/c",
        "https://fantasy.premierleague.com/leagues/1/standings/h",
    ],
)
def test_reject_non_official_or_non_classic_scopes(link):
    with pytest.raises(ValueError):
        league_id(link)


def test_no_fake_global_search_or_blank_name():
    with pytest.raises(ValueError, match="no global"):
        search_teams(object(), "My XI")
    with pytest.raises(ValueError):
        validate_name("   ")


def test_duplicate_names_and_bounded_pages(tmp_path):
    calls = []

    def respond(request):
        assert request.url.host == "fantasy.premierleague.com"
        assert request.url.path == "/api/leagues-classic/123/standings/"
        page = int(request.url.params["page_standings"])
        calls.append(page)
        rows = [
            {"entry": page, "entry_name": "My XI", "player_name": f"Manager {page}", "rank": page},
            {"entry": 99, "entry_name": "Other XI", "player_name": "Other", "rank": 99},
        ]
        return httpx.Response(
            200,
            json={
                "league": {"name": "Test League"},
                "standings": {"has_next": True, "results": rows},
            },
        )

    with FPLClient(
        SnapshotStore(tmp_path / "fpl.sqlite"),
        interval=0,
        retries=0,
        transport=httpx.MockTransport(respond),
    ) as client:
        result = search_teams(client, " MY   XI ", LINK)
        assert [c["reference"] for c in result["candidates"]] == [1, 2]
        assert {c["manager"] for c in result["candidates"]} == {"Manager 1", "Manager 2"}
        assert result["next_page"] == 3 and result["complete"] is False
        assert calls == [1, 2]
        search_teams(client, "My XI", LINK)
        assert calls == [1, 2]  # Existing HTTP snapshot cache avoids repeated league requests.


def test_saved_reference_is_verified_by_current_name():
    class Client:
        def entry(self, reference):
            return {"name": "My XI", "player_first_name": "Test", "player_last_name": "Manager"}

    result = search_teams(Client(), " my xi ", known_entry_id=123)
    assert result["saved_connection"] and result["candidates"][0]["name"] == "My XI"
    with pytest.raises(ValueError):
        search_teams(Client(), "Another team", known_entry_id=123)


def test_bad_standings_not_treated_as_no_match():
    class Client:
        def league_standings(self, league, page):
            return {"standings": {}}

    with pytest.raises(ValueError, match="valid public"):
        search_teams(Client(), "My XI", LINK)
