from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

from fpl_ai.api.client import FPLClient
from fpl_ai.features.history import histories_from_store, training_frame
from fpl_ai.forecasting.rankings import rank_players, upcoming
from fpl_ai.ingestion.refresh import ingest
from fpl_ai.storage import SnapshotStore


def write_json(path: str, data: object) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only FPL forecasts and advisory optimization"
    )
    parser.add_argument("--db", default="data/fpl.sqlite")
    sub = parser.add_subparsers(dest="command", required=True)
    refresh = sub.add_parser("refresh")
    refresh.add_argument("--histories", action="store_true")
    refresh.add_argument("--limit", type=int)
    collect = sub.add_parser("collect")
    collect.add_argument("--event", type=int, required=True)
    ranks = sub.add_parser("rank")
    ranks.add_argument("--horizon", type=int, default=5)
    ranks.add_argument("--out", default="data/processed/rankings.csv")
    train = sub.add_parser("train")
    train.add_argument("--basic-only", action="store_true")
    train.add_argument("--out", default="models/ensemble.joblib")
    train.add_argument("--report", default="data/processed/evaluation.json")
    sub.add_parser("evaluate-components")
    tune = sub.add_parser("tune")
    tune.add_argument("--trials", type=int, default=20)
    optimize = sub.add_parser("optimize")
    optimize.add_argument("--horizon", type=int, default=5)
    optimize.add_argument(
        "--team-json", help="Local confirmed squad, bank, sales and free transfers"
    )
    backtest = sub.add_parser("backtest")
    backtest.add_argument("--include-ml", action="store_true")
    backtest.add_argument("--start", type=int, required=True)
    backtest.add_argument("--end", type=int, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    store = SnapshotStore(args.db)
    if args.command == "collect":
        with FPLClient(store, ttl=0) as client:
            client.bootstrap(refresh=True)
            client.fixtures(refresh=True)
            result = client.live(args.event)
        print(json.dumps({"event": args.event, "players": len(result["elements"])}))
        return
    if args.command == "refresh":
        with FPLClient(store) as client:
            result = ingest(client, histories=args.histories, limit=args.limit)
        print(json.dumps(result, indent=2))
        if result["errors"]:
            raise SystemExit(1)
        return
    cached = store.latest("bootstrap-static/")
    if not cached:
        parser.error("No data: run fpl-ai refresh first")
    b = cached[1]
    if args.command == "evaluate-components":
        from fpl_ai.models.component_evaluation import evaluate_components

        h = histories_from_store(store, b)
        result = evaluate_components(h, training_frame(h, b), b)
        write_json("data/processed/component-evaluation.json", result)
        print(json.dumps(result, indent=2))
    elif args.command in ("train", "tune"):
        from fpl_ai.models.evaluate import train_evaluate, tune_ridge

        frame = training_frame(histories_from_store(store, b), b)
        if args.command == "tune":
            result = tune_ridge(frame, args.trials)
            write_json("data/processed/tuning.json", result)
            print(json.dumps(result, indent=2))
        else:
            import joblib

            artifact, report = train_evaluate(frame, include_ml=not args.basic_only)
            import numpy as np

            from fpl_ai.models.evaluate import chronological_blocks, metrics

            test = chronological_blocks(frame)[-1]
            pred = np.mean(
                [m.predict(test[artifact["features"]]) for m in artifact["models"]], axis=0
            )
            position_by_id = {p["id"]: p["element_type"] for p in b["elements"]}
            position_names = {p["id"]: p["singular_name_short"] for p in b["element_types"]}
            position_ids = test.player_id.map(position_by_id).to_numpy()
            report["models"]["selected_ensemble"]["by_position_current_roster"] = {
                position_names[pos]: metrics(
                    test.target.to_numpy()[position_ids == pos],
                    pred[position_ids == pos],
                    test.event.to_numpy()[position_ids == pos],
                )
                for pos in position_names
                if (position_ids == pos).any()
            }
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(artifact, args.out)
            write_json(args.report, report)
            print(json.dumps(report, indent=2))
    elif args.command in ("rank", "optimize"):
        f = store.latest("fixtures/")
        if not f:
            parser.error("No fixtures; run refresh")
        table = rank_players(
            b, f[1], horizon=args.horizon, histories=histories_from_store(store, b)
        )
        if args.command == "rank":
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            table.to_csv(args.out, index=False)
            print(
                table[["id", "name", "club", "price", "next_points", "horizon_points"]]
                .head(20)
                .to_string(index=False)
            )
        else:
            from fpl_ai.optimization.squad import alternatives, solve_squad
            from fpl_ai.rules import Rules

            columns = [f"gw_{e['id']}" for e in upcoming(b, args.horizon)]
            eligible = table.dropna(subset=columns)
            rules = Rules.from_bootstrap(b)
            if args.team_json:
                private = json.loads(Path(args.team_json).read_text())
                sales = {int(k): int(v) for k, v in private["selling_prices"].items()}
                plans = alternatives(
                    eligible,
                    columns,
                    rules,
                    owned=private["squad"],
                    bank=private["bank"],
                    sale_prices=sales,
                    free_transfers=private["free_transfers"],
                )
            else:
                plans = [solve_squad(eligible, columns, rules)]
            write_json("data/processed/plans.json", [asdict(plan) for plan in plans])
            print(json.dumps([asdict(plan) for plan in plans], indent=2))
    elif args.command == "backtest":
        from fpl_ai.backtesting.walkforward import run_backtest

        results = [
            run_backtest(store, list(range(args.start, args.end + 1)), strategy=s)
            for s in (
                ["form", "historical_average", "official_ep", "ml"]
                if args.include_ml
                else ["form", "historical_average", "official_ep"]
            )
        ]
        write_json("data/processed/backtest.json", results)
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
