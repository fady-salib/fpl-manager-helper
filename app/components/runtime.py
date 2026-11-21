"""Shared Streamlit caches: page changes do not reload models or recompute forecasts."""

from pathlib import Path

import streamlit as st


@st.cache_resource(show_spinner=False)
def load_model(path: str, modified_ns: int, size: int):
    from fpl_ai.ml.registry import load_any

    return load_any(path)


def model_key(path):
    if path is None:
        return None
    path = Path(path)
    stat = path.stat()
    return str(path.resolve()), stat.st_mtime_ns, stat.st_size


@st.cache_data(ttl=300, max_entries=12, show_spinner=False)
def cached_rankings(bootstrap, fixtures, horizon, histories, artifact_key=None, clock_bucket=None):
    from fpl_ai.forecasting.rankings import rank_players

    artifact = load_model(*artifact_key) if artifact_key else None
    local = artifact is not None and "regressors" in artifact
    ranks = rank_players(
        bootstrap,
        fixtures,
        horizon=horizon,
        histories=histories,
        artifact=None if local else artifact,
    )
    if local:
        from fpl_ai.ml.prediction import live_predictions

        predictions = live_predictions(artifact, bootstrap, fixtures, histories, horizon).set_index(
            "id"
        )
        columns = [c for c in predictions if c.startswith("gw_")] + ["horizon_points"]
        for col in columns:
            ranks[col] = ranks.id.map(predictions[col])
        ranks["next_points"] = ranks[columns[0]]
        ranks["value"] = ranks.horizon_points / ranks.price
        ranks["differential_score"] = ranks.value * (1 - ranks.ownership / 100)
        for col in [
            "expected_minutes",
            "p_starts",
            "p_goals_scored",
            "p_assists",
            "p_clean_sheets",
            "history_samples",
        ]:
            if col in predictions:
                ranks[col] = ranks.id.map(predictions[col])
        ranks["source"] = "local validation-selected ML"
        ranks = ranks.sort_values("horizon_points", ascending=False).reset_index(drop=True)
    return ranks


@st.cache_data(ttl=300, max_entries=8, show_spinner=False)
def cached_team_plan(players, columns, rules, team_ids):
    from fpl_ai.optimization.squad import solve_squad

    costs = players.set_index("id").cost.to_dict()
    return solve_squad(
        players,
        columns,
        rules,
        owned=team_ids,
        bank=0,
        sale_prices={i: int(costs[i]) for i in team_ids},
        fixed_squad=True,
    )


@st.cache_data(ttl=300, max_entries=12, show_spinner=False)
def cached_snapshot_rankings(db_path, revision, horizon, artifact_key=None, clock_bucket=None):
    """Cheap revision keys avoid hashing the entire API payload on every page switch."""
    from fpl_ai.features.history import histories_from_store
    from fpl_ai.storage import SnapshotStore

    store = SnapshotStore(db_path)
    bootstrap = store.latest("bootstrap-static/")[1]
    fixtures = store.latest("fixtures/")[1]
    histories = histories_from_store(store, bootstrap)
    return cached_rankings(bootstrap, fixtures, horizon, histories, artifact_key, clock_bucket)
