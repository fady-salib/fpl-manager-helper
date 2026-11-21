"""Synthetic fixtures verify behavior only, never forecasting accuracy.

Run independently of pytest: python -m unittest discover -s tests -p test_local_ml.py
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from fpl_ai.ml.data import FEATURES, dataset_paths, prepare, validate, with_current
from fpl_ai.ml.prediction import live_predictions
from fpl_ai.ml.training import load, predict_rows, split, train


def history():
    return pd.DataFrame(
        [
            dict(
                season="2023-24",
                element=p,
                round=gw,
                fixture=gw,
                kickoff_time=(
                    pd.Timestamp("2023-08-01", tz="UTC") + pd.Timedelta(days=gw * 7)
                ).isoformat(),
                total_points=gw % 5 + p,
                minutes=90,
                position="MID",
            )
            for p in (1, 2)
            for gw in range(1, 21)
        ]
    )


class LocalMLTests(unittest.TestCase):
    def test_validation(self):
        h = history()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate(pd.concat([h, h]))
        h.loc[0, "minutes"] = 999
        with self.assertRaises(ValueError):
            validate(h)
        h = history()
        h["element"] = h.element.astype(float)
        h.loc[0, "element"] = 1.5
        with self.assertRaises(ValueError):
            validate(h)

    def test_no_future_or_same_week_leakage(self):
        h = history()
        before = prepare(h)
        mutated = h.copy()
        mutated.loc[mutated["round"] >= 10, "total_points"] = 999
        after = prepare(mutated)
        pd.testing.assert_frame_equal(
            before.loc[before["round"] <= 10, FEATURES].reset_index(drop=True),
            after.loc[after["round"] <= 10, FEATURES].reset_index(drop=True),
        )
        double = h[h["round"] == 10].copy()
        double["fixture"] = 999
        double["total_points"] = 999
        result = prepare(pd.concat([h, double]))
        self.assertEqual(
            result[(result.element == 1) & (result["round"] == 10)].total_points_3.nunique(), 1
        )

    def test_split_chronological(self):
        a, b, c = split(prepare(history()))
        self.assertLess(a["round"].max(), b["round"].min())
        self.assertLess(b["round"].max(), c["round"].min())

    def test_training_loading_prediction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "test-only.csv"
            h = history()
            h.to_csv(source, index=False)
            path = train(
                [source],
                root / "models",
                root / "reports",
                names=(),
                use_gpu=False,
                log=lambda _: None,
            )
            artifact = load(path)
            prediction = predict_rows(artifact, prepare(h))
            self.assertTrue(np.isfinite(prediction.to_numpy()).all())
            self.assertTrue(prediction.expected_minutes.between(0, 90).all())
            self.assertTrue(list((root / "reports").glob("*.json")))
            self.assertTrue(list((root / "reports").glob("*.log")))
            joblib.dump({}, root / "bad.joblib")
            with self.assertRaises(ValueError):
                load(root / "bad.joblib")

    def test_double_blank_live_predictions(self):
        artifact = {
            "features": FEATURES,
            "regressors": {"total_points": "recent_form", "minutes": "historical_average"},
            "classifiers": {},
        }
        b = {
            "elements": [
                {"id": 1, "web_name": "Fixture", "team": 1, "element_type": 3, "now_cost": 50}
            ],
            "events": [
                {"id": 2, "deadline_time": "2027-01-01T12:00:00Z"},
                {"id": 3, "deadline_time": "2027-01-08T12:00:00Z"},
            ],
        }
        h = pd.DataFrame(
            [
                {
                    "player_id": 1,
                    "round": 1,
                    "kickoff_time": "2026-12-20T12:00:00Z",
                    "total_points": 4,
                    "minutes": 90,
                }
            ]
        )
        f = [{"event": 2, "team_h": 1, "team_a": 2}, {"event": 2, "team_h": 3, "team_a": 1}]
        r = live_predictions(artifact, b, f, h, horizon=2, as_of="2026-12-25T12:00:00Z")
        self.assertEqual(r.iloc[0].gw_2, 8)
        self.assertEqual(r.iloc[0].gw_3, 0)
        self.assertEqual(r.iloc[0].expected_minutes, 90)

    def test_missing_optional_statistics(self):
        frame = prepare(history())
        self.assertTrue(frame.expected_goals_3.isna().all())
        self.assertTrue(frame.starts.isna().all())
        self.assertTrue(set(FEATURES) <= set(frame))

    def test_probability_bounds_and_calibration(self):
        h = pd.concat([history().assign(element=p) for p in range(1, 81)], ignore_index=True)
        # Explicit synthetic labels exercise the classifier/report code only.
        for j, stat in enumerate(["starts", "goals_scored", "assists", "clean_sheets"]):
            h[stat] = ((h.element + h["round"] + j) % 3 == 0).astype(int)
        # Drop repeated fixtures created by the two source players.
        h = h.drop_duplicates(["season", "element", "fixture"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            h.to_csv(root / "fixture.csv", index=False)
            path = train(
                [root / "fixture.csv"],
                root / "models",
                root / "reports",
                names=(),
                use_gpu=False,
                log=lambda _: None,
            )
            artifact = load(path)
            result = predict_rows(artifact, prepare(h))
            for stat in ["starts", "goals_scored", "assists", "clean_sheets"]:
                self.assertTrue(result[f"p_{stat}"].between(0, 1).all())
                self.assertTrue(artifact["metadata"]["targets"][stat]["calibration"])

    def test_dataset_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            h = history()
            h.to_csv(root / "history-2023-24.csv", index=False)
            self.assertEqual(len(dataset_paths(["2023-24"], root)), 1)
            h.assign(season="2024-25").to_csv(root / "current-1.csv", index=False)
            self.assertEqual(len(with_current(dataset_paths(["2023-24"], root), root)), 2)

    @unittest.skipUnless(importlib.util.find_spec("pulp"), "PuLP is not installed")
    def test_squad_and_transfer_constraints(self):
        from fpl_ai.ml.prediction import recommend
        from fpl_ai.optimization.squad import validate_squad
        from fpl_ai.rules import Rules

        rules = Rules(
            "2026_27",
            {1: 2, 2: 5, 3: 5, 4: 3},
            {1: 1, 2: 3, 3: 2, 4: 1},
            {1: 1, 2: 5, 3: 5, 4: 3},
            3,
            1000,
            5,
            20,
            (),
            {},
        )
        rows = []
        for pos, count in rules.squad.items():
            for _ in range(count * 2):
                i = len(rows) + 1
                rows.append(
                    dict(id=i, element_type=pos, team=i % 10 + 1, cost=50, gw_1=i / 10, gw_2=i / 10)
                )
        players = pd.DataFrame(rows)
        result = recommend(players, rules)
        squad = result["plan"]["squad"]
        validate_squad(players, squad, rules)
        self.assertLessEqual(players.set_index("id").loc[squad, "cost"].sum(), 1000)
        for week in result["weeks"].values():
            self.assertEqual(len(week["xi"]), 11)
            self.assertEqual(len(week["bench"]), 4)
            self.assertNotEqual(week["captain"], week["vice_captain"])
            self.assertFalse(set(week["xi"]) & set(week["bench"]))
        sales = dict.fromkeys(squad, 50)
        updated = recommend(
            players,
            rules,
            owned=squad,
            sale_prices=sales,
            bank=0,
            free_transfers=1,
            max_transfers=1,
        )
        self.assertLessEqual(len(updated["plan"]["transfers_in"]), 1)
        self.assertGreaterEqual(updated["plan"]["bank"], 0)
        self.assertEqual(updated["plan"]["hit"], 0)


if __name__ == "__main__":
    unittest.main()
