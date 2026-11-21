"""Local ML workspace; available even when live FPL is offline."""

import json
from pathlib import Path

import streamlit as st


def render(data_dir):
    from components.runtime import load_model, model_key

    from fpl_ai.ml.data import dataset_paths, download, export_current, with_current
    from fpl_ai.ml.training import train

    st.header("Local ML")
    st.caption(
        "Local training and inference. Historical statistics may include later corrections; no accuracy claim is implied."
    )
    seasons = st.text_input("Historical seasons (comma separated)", "2023-24,2024-25").split(",")
    seasons = [s.strip() for s in seasons if s.strip()]
    cpu = st.checkbox("CPU only", True)
    log = st.empty()
    messages = []

    def emit(message):
        messages.append(str(message))
        log.code("\n".join(messages))

    if st.button("Download/update training data"):
        try:
            with st.spinner("Downloading historical training files…"):
                download(seasons, data_dir, refresh=True, log=emit)
                st.cache_data.clear()
            st.success("Data cached locally")
        except Exception as exc:
            st.error(str(exc))
    if st.button("Update current player histories (optional)"):
        try:
            with st.spinner("Downloading current histories; this takes several minutes once…"):
                from fpl_ai.api.client import FPLClient
                from fpl_ai.storage import SnapshotStore

                with FPLClient(SnapshotStore(data_dir / "fpl.sqlite"), ttl=0) as client:
                    bootstrap = client.bootstrap(refresh=True)
                    client.fixtures(refresh=True)
                    progress = st.progress(0.0)
                    for k, p in enumerate(bootstrap["elements"]):
                        client.player(p["id"])
                        progress.progress((k + 1) / len(bootstrap["elements"]))
                    exported = export_current(client.store, bootstrap, data_dir)
                    if exported:
                        emit(f"Saved completed current-season data: {exported}")
                st.cache_data.clear()
            st.success("Current histories updated")
        except Exception as exc:
            st.error(str(exc))
    if st.button("Train local models"):
        try:
            with st.spinner("Training; this can take several minutes…"):
                try:
                    paths_to_train = dataset_paths(seasons, data_dir)
                except ValueError:
                    emit("Downloading missing historical data before training…")
                    paths_to_train = download(seasons, data_dir, log=emit)
                path = train(with_current(paths_to_train, data_dir), use_gpu=not cpu, log=emit)
                st.cache_resource.clear()
                st.cache_data.clear()
            st.success(f"Saved {path}")
        except Exception as exc:
            st.error(str(exc))
    paths = sorted(Path("models").glob("local-*.joblib"), reverse=True)
    if not paths:
        st.info("Download data and train a model to enable predictions.")
        return
    path = st.selectbox("Model version", paths)
    try:
        artifact = load_model(*model_key(path))
    except Exception as exc:
        st.error(f"Cannot load local model: {exc}")
        return
    st.caption(f"Last training: {artifact['metadata']['trained_at']}")
    summary = artifact["metadata"]
    st.success(f"Saved model ready: {path.name}")
    st.dataframe(
        [
            {
                "target": t,
                "selected_model": summary["targets"][t]["winner"],
                **summary["targets"][t]["test"],
            }
            for t in ["total_points", "minutes"]
        ]
    )
    with st.expander("Full evaluation report"):
        st.json(summary)
    horizon = st.slider("Future gameweeks", 1, 8, 3)
    existing = st.text_area(
        "Existing team JSON (optional): owned, bank, sale_prices, free_transfers, max_transfers, chip, available_chip_ids",
        "",
    )
    st.caption(
        "Prices and bank use £0.1m units. Confirm selling prices and chip availability in FPL. Blank input builds a new £100m squad. Predictions freeze history across the horizon; opponent difficulty and injury recovery are not modeled. Minutes and probabilities are per fixture."
    )
    if st.button("Predict and recommend"):
        try:
            from fpl_ai.api.client import FPLClient
            from fpl_ai.features.history import histories_from_store
            from fpl_ai.ml.prediction import live_predictions, recommend
            from fpl_ai.rules import Rules
            from fpl_ai.storage import SnapshotStore

            store = SnapshotStore(data_dir / "fpl.sqlite")
            with FPLClient(store) as client:
                b, f = client.bootstrap(), client.fixtures()
            ranks = live_predictions(artifact, b, f, histories_from_store(store, b), horizon)
            st.dataframe(ranks.sort_values("horizon_points", ascending=False))
            rules = Rules.from_bootstrap(b)
            kwargs = {}
            if existing:
                state = json.loads(existing)
                kwargs = dict(
                    owned=state["owned"],
                    bank=state["bank"],
                    sale_prices={int(k): v for k, v in state["sale_prices"].items()},
                    free_transfers=state["free_transfers"],
                    max_transfers=state.get("max_transfers", 2),
                )
                if state.get("chip"):
                    event = next(e for e in b["events"] if f"gw_{e['id']}" in ranks)
                    if not rules.chip_allowed(
                        state["chip"],
                        event["id"],
                        set(state.get("available_chip_ids", [])),
                        state.get("previous_chip"),
                    ):
                        raise ValueError("Chip unavailable; provide confirmed available_chip_ids")
                    kwargs["chip"] = state["chip"]
            for e in b["events"]:
                if f"gw_{e['id']}" in ranks:
                    rules.validate_event(e)
            result = recommend(ranks, rules, **kwargs)
            st.session_state["local_ml_recommendation"] = result
            st.session_state["local_ml_predictions"] = ranks
        except Exception as exc:
            st.error(str(exc))
    if "local_ml_recommendation" in st.session_state:
        st.caption("Last generated recommendation; regenerate after changing model or team inputs.")
        st.dataframe(st.session_state["local_ml_predictions"])
        st.json(st.session_state["local_ml_recommendation"])
