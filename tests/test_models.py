import pandas as pd
import pytest

from fpl_ai.features.history import FEATURES, lag_features, training_frame
from fpl_ai.models.evaluate import chronological_blocks, train_evaluate


def test_no_current_or_future_round_leakage(history):
    cutoff = pd.Timestamp("2026-08-15T10:00:00Z")
    h = history[history.player_id == 1]
    original = lag_features(h, 5, cutoff)
    h = h.copy()
    h.loc[h["round"] >= 5, "total_points"] = 99999
    assert original == lag_features(h, 5, cutoff)


def test_late_kickoff_excluded(history):
    h = history[history.player_id == 1].copy()
    h.loc[h["round"] == 4, "kickoff_time"] = pd.Timestamp("2026-08-16T10:00:00Z")
    assert lag_features(h, 5, pd.Timestamp("2026-08-15T10:00:00Z"))["samples"] == 3


def test_empty_is_missing():
    assert pd.isna(
        lag_features(pd.DataFrame(), 2, pd.Timestamp("2026-01-01", tz="UTC"))[FEATURES[0]]
    )


def test_chronological_split_and_models(history, bootstrap):
    frame = training_frame(history, bootstrap)
    parts = chronological_blocks(frame)
    for earlier, later in zip(parts[:-1], parts[1:], strict=True):
        assert earlier.event.max() < later.event.min()
    artifact, report = train_evaluate(frame, include_ml=False)
    assert len(artifact["models"]) == 2
    assert report["models"]["ridge"]["mae"] >= 0
    assert 0 <= report["models"]["selected_ensemble"]["test_interval_coverage"] <= 1
    assert not any(k in FEATURES for k in ("now_cost", "ownership", "status", "target"))


def test_insufficient_events(history, bootstrap):
    f = training_frame(history, bootstrap)
    with pytest.raises(ValueError, match="7 gameweeks"):
        chronological_blocks(f[f.event < 5])
