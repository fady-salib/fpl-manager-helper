"""Export the existing trusted fitted artifact to portable, non-executable trees.

Rust inference needs no Python, sklearn, LightGBM DLL, pickle or AI API.
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np

from .registry import model_path
from .training import load


def tree_arrays():
    return {k: [] for k in ("feature", "threshold", "left", "right", "value", "missing_left")}


def lgb_tree(root):
    arrays = tree_arrays()

    def visit(node):
        idx = len(arrays["feature"])
        for key, value in [
            ("feature", -1),
            ("threshold", 0.0),
            ("left", -1),
            ("right", -1),
            ("value", float(node.get("leaf_value", 0.0))),
            ("missing_left", False),
        ]:
            arrays[key].append(value)
        if "split_feature" in node:
            if node["decision_type"] != "<=":
                raise ValueError("Categorical LightGBM splits require a new portable schema")
            arrays["feature"][idx] = node["split_feature"]
            arrays["threshold"][idx] = float(node["threshold"])
            arrays["missing_left"][idx] = bool(node.get("default_left", False))
            arrays["left"][idx] = visit(node["left_child"])
            arrays["right"][idx] = visit(node["right_child"])
        return idx

    visit(root)
    return arrays


def export_predictor(predictor, target, feature_names):
    if isinstance(predictor, str):
        suffix = "5" if predictor == "recent_form" else "avg"
        return {"kind": "baseline", "index": feature_names.index(f"{target}_{suffix}")}
    if isinstance(predictor, float):
        return {"kind": "constant", "value": predictor}
    imputer, estimator = predictor.steps[0][1], predictor.steps[-1][1]
    medians = [float(v) if math.isfinite(v) else 0.0 for v in imputer.statistics_]
    if hasattr(estimator, "booster_"):
        dump = estimator.booster_.dump_model()
        if dump.get("average_output"):
            raise ValueError("Averaged boosting must be handled explicitly")
        trees = [lgb_tree(t["tree_structure"]) for t in dump["tree_info"]]
        return {
            "kind": "trees",
            "imputer": medians,
            "trees": trees,
            "average": False,
            "float32": False,
        }
    if hasattr(estimator, "estimators_") and hasattr(estimator.estimators_[0], "tree_"):
        trees = []
        classification = hasattr(estimator, "predict_proba")
        for item in estimator.estimators_:
            t = item.tree_
            values = t.value[:, 0, :]
            leaf = (
                np.divide(
                    values[:, 1],
                    values.sum(axis=1),
                    out=np.zeros(len(values)),
                    where=values.sum(axis=1) > 0,
                )
                if classification
                else values[:, 0]
            )
            trees.append(
                {
                    "feature": t.feature.tolist(),
                    "threshold": t.threshold.tolist(),
                    "left": t.children_left.tolist(),
                    "right": t.children_right.tolist(),
                    "value": leaf.tolist(),
                    "missing_left": [False] * len(leaf),
                }
            )
        return {
            "kind": "trees",
            "imputer": medians,
            "trees": trees,
            "average": True,
            "float32": True,
        }
    raise ValueError(f"Unsupported native export: {type(estimator).__name__}")


def export(path=None, output="models/native-model.json"):
    path = path or model_path()
    if path is None:
        raise ValueError("Train a model first")
    artifact = load(path)
    features = artifact["features"]
    result = {
        "schema": 1,
        "version": Path(path).name,
        "features": features,
        "metadata": artifact["metadata"],
        "predictors": {},
    }
    for target, predictor in {**artifact["regressors"], **artifact["classifiers"]}.items():
        result["predictors"][target] = export_predictor(predictor, target, features)
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(result, separators=(",", ":"), allow_nan=False), encoding="utf-8"
    )
    temporary.replace(destination)
    print(f"Exported fitted trees for Rust: {destination} ({destination.stat().st_size:,} bytes)")
    return destination


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--model")
    parser.add_argument("--output", default="models/native-model.json")
    args = parser.parse_args()
    export(args.model, args.output)


if __name__ == "__main__":
    main()
