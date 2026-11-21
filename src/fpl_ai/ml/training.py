"""Validation-selected local models and an untouched chronological test partition."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import brier_score_loss, mean_absolute_error, mean_squared_error
from sklearn.pipeline import make_pipeline

from .data import FEATURES, prepare


def gpu_available():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def metrics(y, pred):
    return {
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(np.sqrt(mean_squared_error(y, pred))),
        "bias": float(np.mean(pred - np.asarray(y))),
    }


def split(frame):
    keys = sorted(set(zip(frame.season, frame["round"], strict=True)))
    if len(keys) < 10:
        raise ValueError("Need at least ten chronological season/gameweek groups")
    a, b = int(len(keys) * 0.6), int(len(keys) * 0.8)
    sets = [set(keys[:a]), set(keys[a:b]), set(keys[b:])]
    return [
        frame[[key in group for key in zip(frame.season, frame["round"], strict=True)]].copy()
        for group in sets
    ]


def candidates(names, gpu):
    yield (
        "random_forest",
        RandomForestRegressor(n_estimators=100, min_samples_leaf=10, n_jobs=2, random_state=42),
    )
    if "lightgbm" in names:
        try:
            from lightgbm import LGBMRegressor

            yield (
                "lightgbm",
                LGBMRegressor(
                    n_estimators=150,
                    max_depth=6,
                    verbosity=-1,
                    random_state=42,
                    device_type="cuda" if gpu else "cpu",
                    n_jobs=2,
                ),
            )
        except ImportError:
            pass
    if "xgboost" in names:
        try:
            from xgboost import XGBRegressor

            yield (
                "xgboost",
                XGBRegressor(
                    n_estimators=150,
                    max_depth=5,
                    random_state=42,
                    tree_method="hist",
                    device="cuda" if gpu else "cpu",
                    n_jobs=2,
                ),
            )
        except ImportError:
            pass


def baseline(frame, target, recent):
    return frame[f"{target}_5" if recent else f"{target}_avg"].fillna(0).to_numpy()


def train(
    paths,
    models_dir="models",
    reports_dir="reports",
    names=("lightgbm", "xgboost"),
    use_gpu=True,
    log=print,
):
    original_log = log
    training_log = []

    def log(message):
        training_log.append(str(message))
        original_log(message)

    log("Reading training files and preparing lag-only features…")
    raw = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    frame = prepare(raw)
    train_set, valid, test = split(frame)
    log(f"Chronological rows: train={len(train_set)}, validation={len(valid)}, test={len(test)}")
    gpu = use_gpu and gpu_available()
    report = {
        "trained_at": datetime.now(UTC).isoformat(),
        "seasons": sorted(raw.season.unique().tolist()),
        "features": FEATURES,
        "gpu_detected": gpu,
        "requested_models": list(names),
        "targets": {},
        "skipped": {},
        "split_groups": [
            sorted(set(zip(f.season, f["round"], strict=True))) for f in (train_set, valid, test)
        ],
        "data_sha256": {str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths},
        "limitations": "Retrospective corrected statistics; cutoff is earliest GW kickoff minus 24h. No archived injury, ownership, price or strength inputs. Per-fixture models; historical blanks are absent.",
    }
    artifact = {"features": FEATURES, "regressors": {}, "classifiers": {}}
    report["rows"] = {
        "raw": len(raw),
        "prepared": len(frame),
        "train": len(train_set),
        "validation": len(valid),
        "test": len(test),
    }
    for target in ("total_points", "minutes"):
        choices, results = {}, {}
        for recent, name in ((False, "historical_average"), (True, "recent_form")):
            choices[name] = name
            results[name] = metrics(valid[target], baseline(valid, target, recent))
        for name, estimator in candidates(names, gpu):
            log(f"Training {target}: {name}")
            model = make_pipeline(
                SimpleImputer(strategy="median", keep_empty_features=True), estimator
            )
            device = "cuda" if gpu and name != "random_forest" else "cpu"
            try:
                model.fit(train_set[FEATURES], train_set[target])
            except Exception as exc:
                if device != "cuda":
                    raise
                log(f"{name} CUDA unavailable ({type(exc).__name__}); retrying CPU")
                estimator.set_params(
                    **({"device_type": "cpu"} if name == "lightgbm" else {"device": "cpu"})
                )
                model.fit(train_set[FEATURES], train_set[target])
                device = "cpu"
            if name == "xgboost":
                device = json.loads(estimator.get_booster().save_config())["learner"][
                    "generic_param"
                ]["device"]
            choices[name] = model
            results[name] = {
                **metrics(valid[target], model.predict(valid[FEATURES])),
                "device": device,
            }
        report["skipped"][target + "_candidates"] = sorted(set(names) - set(choices))
        winner = min(results, key=lambda n: results[n]["mae"])
        selected = choices[winner]
        artifact["regressors"][target] = selected
        pred = (
            baseline(test, target, winner == "recent_form")
            if isinstance(selected, str)
            else selected.predict(test[FEATURES])
        )
        groups = {}
        for col in ("season", "position"):
            if col in test:
                groups[col] = {
                    str(k): metrics(g[target], pd.Series(pred, index=test.index).loc[g.index])
                    for k, g in test.groupby(col)
                }
        detail = {
            "winner": winner,
            "validation": results,
            "test": metrics(test[target], pred),
            "test_groups": groups,
            "test_baselines": {
                n: metrics(test[target], baseline(test, target, r))
                for r, n in ((False, "historical_average"), (True, "recent_form"))
            },
        }
        if not isinstance(selected, str):
            est = selected.steps[-1][1]
            detail["parameters"] = est.get_params()
            detail["importance"] = dict(
                zip(FEATURES, map(float, est.feature_importances_), strict=True)
            )
        report["targets"][target] = detail
        log(
            f"{target}: selected {winner}, validation MAE={results[winner]['mae']:.4f}, test MAE={detail['test']['mae']:.4f}"
        )
    for target in ("starts", "goals_scored", "assists", "clean_sheets"):
        groups = [f[f[target].notna()] for f in (train_set, valid, test)]
        if any(
            len(g) < 200
            or (g[target] > 0).nunique() < 2
            or (g[target] > 0).value_counts().min() < 20
            for g in groups
        ):
            report["skipped"][target] = (
                "Need 200 labels and 20 examples of each class in every split"
            )
            continue
        tr, va, te = groups
        log(f"Training probability model: {target}")
        model = make_pipeline(
            SimpleImputer(keep_empty_features=True),
            RandomForestClassifier(
                n_estimators=100, min_samples_leaf=20, random_state=42, n_jobs=2
            ),
        )
        model.fit(tr[FEATURES], (tr[target] > 0).astype(int))
        prevalence = float((tr[target] > 0).mean())
        vp = model.predict_proba(va[FEATURES])[:, 1]
        trained_brier = brier_score_loss(va[target] > 0, vp)
        base_brier = brier_score_loss(va[target] > 0, np.full(len(va), prevalence))
        selected = model if trained_brier < base_brier else prevalence
        artifact["classifiers"][target] = selected
        prob = (
            model.predict_proba(te[FEATURES])[:, 1]
            if selected is model
            else np.full(len(te), prevalence)
        )
        bins = pd.DataFrame({"probability": prob, "observed": (te[target] > 0).to_numpy()})
        bins["bin"] = pd.cut(bins.probability, np.linspace(0, 1, 11), include_lowest=True)
        report["targets"][target] = {
            "validation_brier": float(trained_brier),
            "baseline_validation_brier": float(base_brier),
            "winner": "random_forest" if selected is model else "prevalence",
            "parameters": model.steps[-1][1].get_params()
            if selected is model
            else {"prevalence": prevalence},
            "test_brier": float(brier_score_loss(te[target] > 0, prob)),
            "calibration": bins.groupby("bin", observed=True)
            .agg(
                predicted=("probability", "mean"),
                observed=("observed", "mean"),
                count=("observed", "size"),
            )
            .reset_index()
            .astype({"bin": str})
            .to_dict("records"),
        }
    version = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    artifact["metadata"] = report
    import platform

    import sklearn

    report["runtime"] = {
        "python": platform.python_version(),
        "scikit_learn": sklearn.__version__,
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }
    mdir, rdir = Path(models_dir), Path(reports_dir)
    mdir.mkdir(parents=True, exist_ok=True)
    rdir.mkdir(parents=True, exist_ok=True)
    path = mdir / f"local-{version}.joblib"
    joblib.dump(artifact, path)
    (rdir / f"local-{version}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"Saved {path}; validation-selected models, test reported without refitting")
    (rdir / f"local-{version}.log").write_text("\n".join(training_log), encoding="utf-8")
    return path


def load(path):
    # Only load trusted local artifacts: joblib deserialization executes code.
    artifact = joblib.load(path)
    if (
        artifact.get("features") != FEATURES
        or not {"total_points", "minutes"} <= artifact.get("regressors", {}).keys()
    ):
        raise ValueError("Incompatible local model")
    return artifact


def predict_rows(artifact, frame):
    result = pd.DataFrame(index=frame.index)
    for target, model in artifact["regressors"].items():
        pred = (
            baseline(frame, target, model == "recent_form")
            if isinstance(model, str)
            else model.predict(frame[FEATURES])
        )
        result["expected_points" if target == "total_points" else "expected_minutes"] = (
            np.clip(pred, 0, 90) if target == "minutes" else pred
        )
    for target, model in artifact["classifiers"].items():
        result[f"p_{target}"] = (
            np.full(len(frame), model)
            if isinstance(model, float)
            else model.predict_proba(frame[FEATURES])[:, 1]
        )
    return result
