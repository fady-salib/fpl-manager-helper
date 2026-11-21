"""Portable model conversion must retain fitted predictions, including threshold edges."""

import json
import math
import os
import subprocess
import sys

import joblib
import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline

from fpl_ai.ml.data import FEATURES
from fpl_ai.ml.export_rust import export, export_predictor


def test_export_forest_and_baselines(tmp_path):
    rng = np.random.default_rng(42)
    X = rng.normal(size=(50, len(FEATURES)))
    X[0, 2] = np.nan
    y = np.arange(50) % 5
    reg = make_pipeline(
        SimpleImputer(keep_empty_features=True),
        RandomForestRegressor(n_estimators=4, max_depth=3, random_state=42),
    )
    clf = make_pipeline(
        SimpleImputer(keep_empty_features=True),
        RandomForestClassifier(n_estimators=4, max_depth=3, random_state=42),
    )
    reg.fit(X, y)
    clf.fit(X, y > 1)
    artifact = {
        "features": FEATURES,
        "regressors": {"total_points": reg, "minutes": "recent_form"},
        "classifiers": {"starts": clf, "assists": 0.2},
        "metadata": {},
    }
    source = tmp_path / "local-test.joblib"
    joblib.dump(artifact, source)
    output = export(source, tmp_path / "models/native-model.json")
    encoded = json.loads(output.read_text())
    assert encoded["predictors"]["total_points"]["float32"]
    assert encoded["predictors"]["minutes"]["kind"] == "baseline"
    assert encoded["predictors"]["assists"] == {"kind": "constant", "value": 0.2}
    binary = os.getenv("FPL_RUST_BINARY")
    if not binary:
        from pathlib import Path

        candidate = (
            Path(__file__).parents[1]
            / "rust/target/release"
            / ("fpl-manager.exe" if sys.platform == "win32" else "fpl-manager")
        )
        binary = str(candidate) if candidate.exists() else None
    if not binary:
        return  # Pure export is still tested in a Python-only checkout.
    path = tmp_path / "features.json"
    path.write_text(
        json.dumps([[float(v) if math.isfinite(v) else None for v in row] for row in X])
    )
    env = {**os.environ, "FPL_PROJECT_DIR": str(tmp_path)}
    result = json.loads(
        subprocess.check_output([binary, "--predict-features", str(path)], env=env, text=True)
    )
    assert np.allclose([r["total_points"] for r in result], reg.predict(X), atol=1e-12)
    assert np.allclose([r["starts"] for r in result], clf.predict_proba(X)[:, 1], atol=1e-12)


def test_lightgbm_export_has_all_fitted_trees():
    from lightgbm import LGBMRegressor

    X = np.arange(60 * len(FEATURES), dtype=float).reshape(60, len(FEATURES)) / 7
    y = np.arange(60) % 7
    model = make_pipeline(
        SimpleImputer(keep_empty_features=True),
        LGBMRegressor(n_estimators=5, min_child_samples=2, verbosity=-1, n_jobs=1),
    )
    model.fit(X, y)
    encoded = export_predictor(model, "total_points", FEATURES)
    assert len(encoded["trees"]) == model.steps[-1][1].n_estimators_
    assert encoded["average"] is False and encoded["float32"] is False


def test_unsupported_model_is_explicit():
    from sklearn.linear_model import Ridge

    model = make_pipeline(SimpleImputer(), Ridge()).fit(np.ones((10, len(FEATURES))), np.ones(10))
    with pytest.raises(ValueError, match="Unsupported native export"):
        export_predictor(model, "total_points", FEATURES)
