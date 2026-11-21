"""Chronological model selection with a separate residual interval calibration block."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from fpl_ai.features.history import FEATURES

LOG = logging.getLogger(__name__)


def metrics(y: np.ndarray, pred: np.ndarray, events: np.ndarray) -> dict:
    errors = y - pred
    ranking = []
    # Fixture-level top ranking: double-GW players may have more than one row.
    for event in np.unique(events):
        take = np.where(events == event)[0]
        k = min(20, len(take))
        actual = set(take[np.argsort(y[take])[-k:]])
        forecast = set(take[np.argsort(pred[take])[-k:]])
        ranking.append(len(actual & forecast) / k)
    bins = []
    for idx in np.array_split(np.argsort(pred), min(5, len(y))):
        bins.append(
            {
                "count": len(idx),
                "predicted": float(pred[idx].mean()),
                "observed": float(y[idx].mean()),
            }
        )
    corr = float(spearmanr(y, pred).statistic) if np.std(pred) > 0 and np.std(y) > 0 else None
    return {
        "mae": float(np.abs(errors).mean()),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "spearman": corr,
        "top20_overlap": float(np.mean(ranking)),
        "mean_bias": float((pred - y).mean()),
        "calibration_bins": bins,
    }


def candidates(seed: int = 42, include_ml: bool = True) -> dict:
    raw = {
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=10)),
        "random_forest": RandomForestRegressor(
            n_estimators=120, min_samples_leaf=15, random_state=seed, n_jobs=1
        ),
        "gradient_boosting": GradientBoostingRegressor(
            n_estimators=100, max_depth=2, random_state=seed
        ),
    }
    if include_ml:
        from lightgbm import LGBMRegressor
        from xgboost import XGBRegressor

        raw.update(
            lightgbm=LGBMRegressor(
                n_estimators=100,
                num_leaves=15,
                min_child_samples=30,
                verbosity=-1,
                n_jobs=1,
                random_state=seed,
            ),
            xgboost=XGBRegressor(
                n_estimators=100, max_depth=3, learning_rate=0.05, n_jobs=1, random_state=seed
            ),
        )
    return {
        name: make_pipeline(
            SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), model
        )
        for name, model in raw.items()
    }


def chronological_blocks(frame: pd.DataFrame) -> list[pd.DataFrame]:
    events = sorted(frame["event"].unique())
    if len(events) < 7:
        raise ValueError(
            "Need at least 7 gameweeks with lag features for four chronological blocks"
        )
    # Keep all players and all fixtures of an event in the same block.
    split = [events[:-3], [events[-3]], [events[-2]], [events[-1]]]
    return [frame[frame["event"].isin(part)].copy() for part in split]


def train_evaluate(
    frame: pd.DataFrame, *, seed: int = 42, include_ml: bool = True
) -> tuple[dict, dict]:
    train, select, calibration, test = chronological_blocks(frame)
    ytest = test["target"].to_numpy(float)
    report = {
        "seed": seed,
        "unit": "player-fixture",
        "blocks": {
            name: {"events": sorted(map(int, part["event"].unique())), "rows": len(part)}
            for name, part in zip(
                ("train", "selection", "calibration", "test"),
                (train, select, calibration, test),
                strict=True,
            )
        },
        "limitations": [
            "Reconstructed recent histories, not archived deadline snapshots",
            "Later corrections to historical outcomes cannot be removed",
            "No historical current-price/injury/ownership inputs",
            "Small single-season test; repeated-player observations correlated",
        ],
        "models": {},
    }
    trained, selection = {}, {}
    for name, model in candidates(seed, include_ml).items():
        model.fit(train[FEATURES], train["target"])
        selection[name] = float(np.mean(np.abs(model.predict(select[FEATURES]) - select["target"])))
        trained[name] = model
        report["models"][name] = {
            "selection_mae": selection[name],
            **metrics(ytest, model.predict(test[FEATURES]), test["event"].to_numpy()),
        }
    chosen = sorted(selection, key=selection.get)[:2]
    selected = [trained[name] for name in chosen]
    calpred = np.mean([m.predict(calibration[FEATURES]) for m in selected], axis=0)
    abs_errors = np.abs(calpred - calibration["target"].to_numpy())
    # Finite-sample conformal order statistic; temporal drift prevents coverage guarantee.
    q = min(1, np.ceil((len(abs_errors) + 1) * 0.8) / len(abs_errors))
    width = float(np.quantile(abs_errors, q, method="higher"))
    pred = np.mean([m.predict(test[FEATURES]) for m in selected], axis=0)
    report["models"]["selected_ensemble"] = {
        "members": chosen,
        **metrics(ytest, pred, test["event"].to_numpy()),
        "nominal_interval": 0.8,
        "residual_half_width": width,
        "test_interval_coverage": float(np.mean(np.abs(pred - ytest) <= width)),
    }
    for name, col in (("form_3", "total_points_3"), ("average_10", "total_points_10")):
        base = test[col].fillna(train["target"].mean()).to_numpy()
        report["models"][name] = metrics(ytest, base, test["event"].to_numpy())
    return {
        "models": selected,
        "features": FEATURES,
        "interval_half_width": width,
        "trained_through_event": int(train["event"].max()),
        "report": report,
    }, report


def tune_ridge(frame: pd.DataFrame, trials: int = 20, seed: int = 42) -> dict:
    """Optuna sees expanding folds inside training only; final blocks stay untouched."""
    import optuna

    train = chronological_blocks(frame)[0]
    events = sorted(train["event"].unique())
    if len(events) < 3:
        raise ValueError("Need three training events for expanding tuning folds")

    def objective(trial: optuna.Trial) -> float:
        alpha = trial.suggest_float("alpha", 0.01, 1000, log=True)
        losses = []
        for event in events[1:]:
            fit, valid = train[train.event < event], train[train.event == event]
            model = make_pipeline(
                SimpleImputer(keep_empty_features=True), StandardScaler(), Ridge(alpha=alpha)
            )
            model.fit(fit[FEATURES], fit.target)
            losses.append(np.mean(np.abs(model.predict(valid[FEATURES]) - valid.target)))
        return float(np.mean(losses))

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=trials)
    return {
        "best_params": study.best_params,
        "training_cv_mae": study.best_value,
        "trials": trials,
        "note": "Research tuning report only; not silently applied to benchmark",
    }
