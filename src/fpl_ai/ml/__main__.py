"""python -m fpl_ai.ml {download_data,train,evaluate,predict}."""

import argparse
import json
from pathlib import Path

from .data import dataset_paths, download, export_current, with_current
from .training import load, train


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("command", choices=["download_data", "train", "evaluate", "predict"])
    parser.add_argument("--seasons", nargs="+", default=["2023-24", "2024-25"])
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--input", nargs="+")
    parser.add_argument("--model")
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--output", default="reports/predictions.csv")
    args = parser.parse_args()
    if args.command == "download_data":
        download(args.seasons, args.data_dir, args.refresh)
        from fpl_ai.api.client import FPLClient
        from fpl_ai.storage import SnapshotStore

        with FPLClient(SnapshotStore(Path(args.data_dir) / "fpl.sqlite")) as client:
            bootstrap = client.bootstrap(refresh=args.refresh)
            client.fixtures(refresh=args.refresh)
            for p in bootstrap["elements"]:
                client.player(p["id"])
            exported = export_current(client.store, bootstrap, args.data_dir)
            if exported:
                print(f"Completed current-season training data: {exported}")
        return
    if args.command == "train":
        paths = args.input or with_current(
            dataset_paths(args.seasons, args.data_dir), args.data_dir
        )
        train(paths, args.models_dir, args.reports_dir, use_gpu=not args.cpu)
        return
    path = (
        Path(args.model)
        if args.model
        else next(iter(sorted(Path(args.models_dir).glob("local-*.joblib"), reverse=True)), None)
    )
    if path is None:
        parser.error("No local model; train first")
    artifact = load(path)
    if args.command == "evaluate":
        print(json.dumps(artifact["metadata"], indent=2))
        return
    from fpl_ai.api.client import FPLClient
    from fpl_ai.features.history import histories_from_store
    from fpl_ai.storage import SnapshotStore

    from .prediction import live_predictions

    store = SnapshotStore(Path(args.data_dir) / "fpl.sqlite")
    with FPLClient(store) as client:
        bootstrap, fixtures = client.bootstrap(), client.fixtures()
    result = live_predictions(
        artifact, bootstrap, fixtures, histories_from_store(store, bootstrap), args.horizon
    )
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves existing user outputs, including concurrent writes.
    with dest.open("x", encoding="utf-8", newline="") as output:
        result.to_csv(output, index=False)
    print(dest)


if __name__ == "__main__":
    main()
