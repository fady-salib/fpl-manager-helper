import numpy as np
import pandas as pd
import pytest

from fpl_ai.rules import Rules


@pytest.fixture
def bootstrap():
    types = [
        {
            "id": i,
            "squad_select": n,
            "squad_min_play": lo,
            "squad_max_play": hi,
            "singular_name_short": name,
        }
        for i, n, lo, hi, name in [
            (1, 2, 1, 1, "GKP"),
            (2, 5, 3, 5, "DEF"),
            (3, 5, 2, 5, "MID"),
            (4, 3, 1, 3, "FWD"),
        ]
    ]
    players = []
    pid = 1
    for pos in types:
        for _ in range(pos["squad_select"] * 2):
            players.append(
                {
                    "id": pid,
                    "web_name": f"Test {pid}",
                    "team": (pid % 10) + 1,
                    "element_type": pos["id"],
                    "now_cost": 50,
                    "form": "4",
                    "points_per_game": "3",
                    "status": "a",
                    "selected_by_percent": "10",
                    "can_select": True,
                }
            )
            pid += 1
    scoring = {
        "long_play": 2,
        "short_play": 1,
        "assists": 3,
        "saves": 1,
        "goals_scored": dict(zip(("GKP", "DEF", "MID", "FWD"), (10, 6, 5, 4), strict=True)),
        "clean_sheets": dict(zip(("GKP", "DEF", "MID", "FWD"), (4, 4, 1, 0), strict=True)),
        "goals_conceded": dict(zip(("GKP", "DEF", "MID", "FWD"), (-1, -1, 0, 0), strict=True)),
        "defensive_contribution": dict(
            zip(("GKP", "DEF", "MID", "FWD"), (0, 2, 2, 2), strict=True)
        ),
        "bonus": 1,
        "yellow_cards": -1,
        "red_cards": -3,
        "own_goals": -2,
        "penalties_saved": 5,
        "penalties_missed": -2,
    }
    return {
        "elements": players,
        "teams": [{"id": i, "short_name": f"T{i}"} for i in range(1, 11)],
        "element_types": types,
        "events": [
            {"id": i, "deadline_time": f"2026-08-{i * 3:02d}T10:00:00Z", "data_checked": True}
            for i in range(1, 10)
        ],
        "chips": [
            {"id": 1, "name": "bboost", "start_event": 1, "stop_event": 19},
            {"id": 2, "name": "3xc", "start_event": 1, "stop_event": 19},
            {"id": 3, "name": "freehit", "start_event": 2, "stop_event": 19},
        ],
        "game_config": {
            "settings": {"static_content_url": "https://example.test/2026_27/"},
            "scoring": scoring,
            "rules": {
                "squad_squadsize": 15,
                "squad_squadplay": 11,
                "squad_team_limit": 3,
                "squad_total_spend": 1000,
                "max_extra_free_transfers": 4,
                "transfers_cap": 20,
            },
        },
    }


@pytest.fixture
def rules(bootstrap):
    return Rules.from_bootstrap(bootstrap)


@pytest.fixture
def players(bootstrap):
    return pd.DataFrame(
        [
            {
                **p,
                "cost": p["now_cost"],
                "name": p["web_name"],
                "gw_9": float((p["id"] * 7) % 13),
                "gw_10": float((p["id"] * 3) % 11),
            }
            for p in bootstrap["elements"]
        ]
    )


@pytest.fixture
def history():
    from fpl_ai.features.history import STATS

    rows = []
    rng = np.random.default_rng(3)
    for pid in range(1, 21):
        for gw in range(1, 10):
            rows.append(
                {
                    **dict.fromkeys(STATS, 0.0),
                    "player_id": pid,
                    "round": gw,
                    "fixture": gw,
                    "kickoff_time": pd.Timestamp(f"2026-08-{gw * 3:02d}T12:00:00Z"),
                    "minutes": 90.0,
                    "starts": 1.0,
                    "total_points": float(rng.integers(0, 12)),
                    "expected_goals": 0.2,
                    "expected_assists": 0.1,
                }
            )
    return pd.DataFrame(rows)
