"""Launch: streamlit run app/main.py from the repository root."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from components.runtime import (
    cached_rankings,
    cached_snapshot_rankings,
    cached_team_plan,
    model_key,
)

from fpl_ai.api.client import DataError, FPLClient
from fpl_ai.features.history import histories_from_store
from fpl_ai.forecasting.components import simulate_player
from fpl_ai.forecasting.rankings import fixture_table, upcoming
from fpl_ai.ml.registry import model_path as discover_model
from fpl_ai.optimization.chips import chip_opportunities
from fpl_ai.optimization.squad import alternatives
from fpl_ai.rules import Rules
from fpl_ai.storage import SnapshotStore

st.set_page_config(page_title="FPL AI Manager", page_icon="⚽", layout="wide")
DATA = Path(os.getenv("FPL_DATA_DIR", "data"))
DB = DATA / "fpl.sqlite"
PAGES = [
    "Overview",
    "Local ML",
    "New Team Builder",
    "Player Rankings",
    "My Team",
    "Transfers",
    "Captaincy",
    "Fixture Planner",
    "Chip Planner",
    "Model Performance",
    "Settings",
]


@st.cache_data(ttl=300, show_spinner="Fetching public FPL data…")
def load_data(db_path: str):
    snapshots = SnapshotStore(db_path)
    cached_b, cached_f = snapshots.latest("bootstrap-static/"), snapshots.latest("fixtures/")
    if cached_b and cached_f:
        # Navigation never waits for the network. The snapshot timestamp is visible;
        # the user can explicitly refresh when ready.
        return cached_b[1], cached_f[1]
    with FPLClient(snapshots, retries=0, timeout=8) as client:
        return client.bootstrap(), client.fixtures()


@st.cache_data(ttl=300)
def load_histories(db_path: str):
    s = SnapshotStore(db_path)
    b = s.latest("bootstrap-static/")
    return histories_from_store(s, b[1]) if b else pd.DataFrame()


st.title("⚽ FPL AI Manager")
st.caption("Real public data · advisory forecasts · no account actions")
if st.session_state.get("builder_go_settings"):
    st.session_state["workspace"] = "Settings"
    st.session_state.pop("builder_go_settings")
page = st.sidebar.radio("Workspace", PAGES, key="workspace")
if page == "Local ML":
    from components.local_ml import render

    render(DATA)
    st.stop()
if page == "Model Performance":
    from components.model_performance import render

    render(DATA)
    st.stop()
horizon = st.sidebar.select_slider("Planning horizon", options=[1, 3, 5, 8], value=3)
model_choice = st.sidebar.selectbox("Forecast", ["Locally trained ML", "Transparent form baseline"])
risk = st.sidebar.select_slider(
    "Captain preference",
    options=["Conservative", "Expected points", "Aggressive"],
    value="Expected points",
)
if st.sidebar.button("Refresh live data"):
    try:
        with FPLClient(SnapshotStore(DB), ttl=0, retries=1, timeout=8) as client:
            client.bootstrap(refresh=True)
            client.fixtures(refresh=True)
        st.cache_data.clear()
    except DataError as exc:
        st.sidebar.error(str(exc))
    st.rerun()
use_cache = st.sidebar.checkbox("Allow stored snapshots if API unavailable", value=True)
try:
    bootstrap, fixtures = load_data(str(DB))
except (DataError, ValueError) as exc:
    st.error(f"Live data unavailable: {exc}")
    s = SnapshotStore(DB)
    b, f = s.latest("bootstrap-static/"), s.latest("fixtures/")
    if not use_cache or not b or not f:
        st.info("Retry later, or explicitly allow stored snapshots in the sidebar.")
        st.stop()
    bootstrap, fixtures = b[1], f[1]
    st.warning("Using stored snapshots. These may be stale; verify changes against FPL.")

store = SnapshotStore(DB)
latest = store.latest("bootstrap-static/")
if latest:
    st.caption(f"Player snapshot: {latest[0].strftime('%Y-%m-%d %H:%M UTC')}")
    if (pd.Timestamp.now(tz="UTC") - latest[0]).total_seconds() > 3600:
        st.warning(
            "Player snapshot is over an hour old. Use Refresh live data to update prices, injuries and fixtures."
        )
try:
    rules = Rules.from_bootstrap(bootstrap)
except (ValueError, KeyError) as exc:
    st.error(f"Season rules require review: {exc}")
    st.stop()
events = upcoming(bootstrap, horizon)
if not events and page != "Settings":
    st.info("No upcoming deadline. Settings, Local ML and Model Performance remain available.")
    st.stop()
try:
    for event in events:
        rules.validate_event(event)
except ValueError as exc:
    st.error(str(exc))
    st.stop()
columns = [f"gw_{e['id']}" for e in events]
next_col = columns[0] if columns else None
histories = (
    load_histories(str(DB)) if page not in ("Settings", "Fixture Planner") else pd.DataFrame()
)

selected_path = discover_model() if model_choice == "Locally trained ML" else None
artifact_key = model_key(selected_path) if page not in ("Settings", "Fixture Planner") else None
if model_choice == "Locally trained ML":
    if selected_path:
        st.sidebar.caption(f"Model: {selected_path.name}")
    else:
        st.sidebar.warning(
            "No trained model yet. Open Local ML → Train local models. Showing the form baseline."
        )
try:
    cached_fixtures = store.latest("fixtures/")
    if latest and cached_fixtures and page not in ("Settings", "Fixture Planner"):
        with store.connect() as con:
            history_version = con.execute(
                "SELECT MAX(fetched_at) FROM snapshots WHERE endpoint LIKE 'element-summary/%'"
            ).fetchone()[0]
        revision = (latest[0].isoformat(), cached_fixtures[0].isoformat(), history_version)
        ranks = cached_snapshot_rankings(
            str(DB),
            revision,
            horizon,
            artifact_key,
            int(pd.Timestamp.now(tz="UTC").timestamp() // 300),
        )
    else:
        ranks = cached_rankings(
            bootstrap,
            fixtures,
            horizon,
            histories,
            artifact_key,
            int(pd.Timestamp.now(tz="UTC").timestamp() // 300),
        )
except Exception as exc:
    if artifact_key is None:
        raise
    st.warning(
        f"Local model could not be used: {exc}. Showing the form baseline; retrain in Local ML if library versions changed."
    )
    ranks = cached_rankings(bootstrap, fixtures, horizon, histories)
players = ranks.dropna(subset=columns).copy()
team_ids = st.session_state.get("team_ids", [])


def team_plan():
    if len(team_ids) != 15:
        st.info("Load your public past-deadline squad in Settings, or select 15 player IDs there.")
        return None
    if not set(team_ids) <= set(players.id):
        st.warning(
            "A squad player has no usable forecast or is removed. Confirm your current squad in Settings."
        )
        return None
    try:
        return cached_team_plan(players, columns, rules, team_ids)
    except ValueError as exc:
        st.error(str(exc))
        return None


if page == "Overview":
    c1, c2, c3 = st.columns(3)
    c1.metric("Next gameweek", events[0]["id"])
    c2.metric("Deadline (UTC)", pd.Timestamp(events[0]["deadline_time"]).strftime("%d %b %H:%M"))
    c3.metric("Players with forecasts", len(players))
    st.subheader(f"{rules.season.replace('_', '/')} · Top projected players")
    st.dataframe(
        players[
            ["name", "club", "position", "price", "next_points", "horizon_points", "news"]
        ].head(15),
        hide_index=True,
    )
    st.plotly_chart(
        px.bar(players.head(15), x="name", y="horizon_points", color="position"), width="stretch"
    )
    alerts = ranks[(ranks.status != "a") & (ranks.ownership > 5)]
    st.subheader("Availability alerts · ownership above 5%")
    st.dataframe(alerts[["name", "status", "news", "ownership"]], hide_index=True)
    if model_choice == "Locally trained ML" and selected_path:
        st.info(
            "Showing the saved local model. View its held-out results in Model Performance. History is frozen across the horizon; prices and fixture counts are current snapshots."
        )
    else:
        st.info(
            "Baseline = (70% recent official form + 30% season points per match) × scheduled fixtures × FDR heuristic. Next-GW availability is a separate heuristic; longer-term recovery is not modeled."
        )

elif page == "New Team Builder":
    from components.new_team_builder import render_new_team_builder

    render_new_team_builder(
        bootstrap, fixtures, histories, rules, DATA, latest[0].isoformat() if latest else None
    )

elif page == "Player Rankings":
    selected = st.multiselect(
        "Positions", sorted(players.position.unique()), default=sorted(players.position.unique())
    )
    max_price = st.slider("Maximum price (£m)", 3.0, 20.0, 15.0, 0.5)
    filtered = players[(players.position.isin(selected)) & (players.price <= max_price)]
    st.dataframe(
        filtered[
            [
                "id",
                "name",
                "club",
                "position",
                "price",
                "ownership",
                "next_points",
                "horizon_points",
                "value",
                "differential_score",
                *columns,
            ]
        ],
        hide_index=True,
    )
    st.download_button(
        "Download rankings CSV", filtered.to_csv(index=False), "fpl-rankings.csv", "text/csv"
    )
    st.subheader("Differentials")
    st.caption(
        "Score = horizon points / price × (1 − ownership / 100). A screening heuristic, not a probability of outperforming."
    )
    st.dataframe(
        filtered[filtered.ownership <= 10]
        .sort_values("differential_score", ascending=False)
        .head(15)[["name", "club", "horizon_points", "ownership", "price", "news"]],
        hide_index=True,
    )

elif page == "Settings":
    from components.team_setup import render_public_team_lookup

    render_public_team_lookup(store)
    team_ids = st.session_state.get("team_ids", [])
    info = st.session_state.get("public_info")
    if info:
        st.write({"Public deadline information (not current)": info})
    choices = dict(zip(players.id, players.name + " · " + players.club, strict=True))
    selection = st.multiselect(
        "Confirm current squad (15 players)",
        list(choices),
        default=[i for i in st.session_state.get("team_ids", []) if i in choices],
        format_func=lambda i: f"{choices[i]} [{i}]",
    )
    st.session_state["team_ids"] = selection
    st.session_state["bank"] = st.number_input(
        "Confirmed current bank (£m)", min_value=0.0, value=0.0, step=0.1
    )
    st.session_state["free"] = st.number_input(
        "Confirmed free transfers", 0, rules.free_transfer_cap, value=1
    )
    sale_frame = pd.DataFrame(
        [
            {
                "id": i,
                "name": choices[i],
                "selling_price": st.session_state.get("sales", {}).get(i, float("nan")) / 10,
            }
            for i in selection
        ]
    )
    st.caption(
        "Enter actual selling prices from FPL, in £m. Purchase profit rounding means these may differ from market prices. Kept in this browser session only."
    )
    if len(sale_frame):
        edited = st.data_editor(sale_frame, disabled=["id", "name"], hide_index=True)
        st.session_state["sales"] = {
            int(r.id): int(round(r.selling_price * 10))
            for r in edited.itertuples()
            if pd.notna(r.selling_price)
        }
    st.session_state["confirmed"] = st.checkbox(
        "I confirmed squad, bank, free transfers and selling prices against my current account",
        value=False,
        key="account_confirmation",
    )
    chip_options = {
        c["id"]: f"{c['name']} · GW {c['start_event']}–{c['stop_event']}" for c in rules.chips
    }
    st.session_state["chips"] = st.multiselect(
        "Confirm unused chip instances", list(chip_options), format_func=chip_options.get
    )
    st.session_state["previous_chip"] = st.selectbox(
        "Chip used last gameweek", [None, "freehit", "wildcard", "bboost", "3xc"]
    )
    st.info(
        "No passwords or cookies. Public picks can be outdated; private values are entered manually and never sent to FPL."
    )

elif page == "My Team":
    st.header("My Team")
    if len(team_ids) != 15:
        from components.team_setup import render_public_team_lookup

        st.info(
            "Load your squad below to see your starting XI, bench and captain. No model training is required to open this page."
        )
        if render_public_team_lookup(store, prefix="my_team"):
            st.rerun()
        if st.button("Select my squad manually in Settings"):
            st.session_state["builder_go_settings"] = True
            st.rerun()
        st.stop()
    plan = team_plan()
    if plan:
        from components.pitch import pitch

        indexed = players.set_index("id")
        xi, captain = plan.lineups[next_col], plan.captains[next_col]
        vice = max((i for i in xi if i != captain), key=lambda i: indexed.at[i, next_col])
        st.plotly_chart(pitch(players, xi, captain, vice), width="stretch")
        formation = "–".join(
            str(sum(indexed.at[i, "element_type"] == pos for i in xi)) for pos in (2, 3, 4)
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Projected XI + captain points", f"{plan.weekly_points[next_col]:.2f}")
        c2.metric("Squad market value", f"£{indexed.loc[team_ids, 'price'].sum():.1f}m")
        c3.metric(
            "Confirmed bank",
            f"£{st.session_state.get('bank', 0):.1f}m"
            if st.session_state.get("confirmed")
            else "Not confirmed",
        )
        st.caption(
            f"Formation {formation}. Captain {indexed.at[captain, 'name']}; vice {indexed.at[vice, 'name']}. This objective excludes expected autosubs and captain fallback."
        )
        bench = sorted(
            set(plan.squad) - set(xi),
            key=lambda i: (indexed.at[i, "element_type"] != 1, -indexed.at[i, next_col]),
        )
        st.write(
            "Bench (reserve GK, then outfield priority):", [indexed.at[i, "name"] for i in bench]
        )
        st.caption(
            "Bench order uses projected points; formation-dependent optimal stochastic bench ordering is unfinished."
        )
        st.dataframe(
            indexed.loc[team_ids, ["name", "club", "price", "status", *columns]], hide_index=True
        )

    st.subheader("Appearance-aware statistical lineup")
    st.caption(
        "Uses Monte Carlo events, automatic substitutes and vice-captain fallback. Finite-scenario local search; estimates are uncalibrated and player dependence is simplified."
    )
    if st.button("Optimize simulated lineup and bench"):
        try:
            from fpl_ai.optimization.lineup import optimize_lineup

            if len(team_ids) != 15 or histories.empty:
                raise ValueError("Load a 15-player squad and download real histories first")
            dists = {}
            for pid in team_ids:
                p = players.set_index("id").loc[pid]
                h = histories[(histories.player_id == pid) & (histories["round"] < events[0]["id"])]
                dists[pid] = simulate_player(
                    h,
                    p.position,
                    rules,
                    fixtures=int(p.fixture_count),
                    availability=p.availability_factor,
                    samples=128,
                    seed=42 + int(pid),
                )
            with st.spinner("Searching feasible lineup and bench changes…"):
                result = optimize_lineup(
                    players[players.id.isin(team_ids)], rules, dists, risk=risk
                )
            from components.pitch import pitch

            st.plotly_chart(
                pitch(players, result["xi"], result["captain"], result["vice"]), width="stretch"
            )
            st.json(result)
        except (ValueError, KeyError) as exc:
            st.warning(str(exc))

elif page == "Transfers":
    st.subheader(f"Compare transfer plans over {len(columns)} gameweeks")
    st.caption(
        "MILP maximizes weekly XI + captain forecasts minus hits. Future lineups can change; this comparison holds the purchased squad for the horizon. No account action is possible."
    )
    max_transfers = st.slider("Maximum transfers now", 0, 4, 2)
    if len(team_ids) != 15 or not st.session_state.get("confirmed"):
        st.info(
            "First load your team and confirm selling prices, bank and free transfers in Settings."
        )
        if st.button("Open team Settings"):
            st.session_state["builder_go_settings"] = True
            st.rerun()
    if st.button("Calculate advisory transfers"):
        if (
            not st.session_state.get("confirmed")
            or set(st.session_state.get("sales", {})) != set(team_ids)
            or len(team_ids) != 15
        ):
            st.error(
                "Confirm all 15 current players, selling prices, bank and free transfers in Settings first."
            )
        else:
            try:
                from fpl_ai.explainability.recommendations import explain_plan

                plans = alternatives(
                    players,
                    columns,
                    rules,
                    owned=team_ids,
                    bank=int(round(st.session_state["bank"] * 10)),
                    sale_prices=st.session_state["sales"],
                    free_transfers=int(st.session_state["free"]),
                    max_transfers=max_transfers,
                )
                roll = next(p for p in plans if not p.transfers_in)
                for i, plan in enumerate(plans):
                    st.markdown(
                        f"**Option {i + 1} · {'Roll' if not plan.transfers_in else str(len(plan.transfers_in)) + ' transfer(s)'}**"
                    )
                    st.json(explain_plan(plan, roll, players, next_col))
            except ValueError as exc:
                st.error(str(exc))
    st.caption(
        "Stateful beam planning is available in fpl_ai.optimization.planning; future prices stay fixed, chips are not jointly optimized."
    )

elif page == "Captaincy":
    st.subheader("Captain candidates")
    candidates = players[players.id.isin(team_ids)] if team_ids else players
    st.dataframe(
        candidates.sort_values("next_points", ascending=False)[
            [
                "name",
                "club",
                "next_points",
                "status",
                "historical_minutes_per_fixture",
                "historical_start_rate",
                "ownership",
            ]
        ].head(15),
        hide_index=True,
    )
    pid = st.selectbox(
        "Inspect player uncertainty",
        list(candidates.id),
        format_func=lambda i: players.set_index("id").at[i, "name"],
    )
    if st.button("Run component simulation"):
        p = players.set_index("id").loc[pid]
        try:
            if histories.empty:
                raise ValueError("Download player histories first: fpl-ai refresh --histories")
            history = histories[
                (histories.player_id == pid) & (histories["round"] < events[0]["id"])
            ]
            result = simulate_player(
                history,
                p.position,
                rules,
                fixtures=int(p.fixture_count),
                availability=p.availability_factor,
            )
            st.json({k: v for k, v in result.items() if k not in ("draws", "appeared")})
            st.plotly_chart(
                px.histogram(x=result["draws"], nbins=35, labels={"x": "Simulated points"}),
                width="stretch",
            )
        except ValueError as exc:
            st.warning(str(exc))
    st.caption(
        f"Preference: {risk}. Use My Team’s statistical lineup optimizer to apply this preference to captain, vice and bench. Component ranges are simulated, not calibrated intervals."
    )

elif page == "Fixture Planner":
    teams = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    table = fixture_table(fixtures, teams)
    table = table[table.event.isin([e["id"] for e in events])].copy()
    table["club"] = table.team.map(teams)
    st.dataframe(
        table[["club", "event", "opponent", "home", "difficulty", "kickoff"]], hide_index=True
    )
    pivot = table.pivot_table(
        index="club", columns="event", values="difficulty", aggfunc="mean"
    ).reindex(columns=[e["id"] for e in events])
    st.plotly_chart(
        px.imshow(pivot, text_auto=".1f", color_continuous_scale="RdYlGn_r", zmin=1, zmax=5),
        width="stretch",
    )
    st.caption(
        "Missing cells are blanks or unscheduled fixtures. Double-gameweek cells show mean difficulty; detailed rows retain every fixture."
    )

elif page == "Chip Planner":
    st.subheader("Chip timing opportunities")
    st.dataframe(
        pd.DataFrame(rules.chips)[["id", "name", "start_event", "stop_event"]], hide_index=True
    )
    if len(team_ids) == 15 and st.button("Compare Bench Boost and Triple Captain windows"):
        try:
            opportunities = chip_opportunities(
                players,
                columns,
                rules,
                team_ids,
                set(st.session_state.get("chips", [])),
                st.session_state.get("previous_chip"),
            )
            st.dataframe(opportunities, hide_index=True)
        except ValueError as exc:
            st.error(str(exc))
    st.info(
        "Confirm unused chips in Settings. Values are gross local opportunities with a fixed squad, excluding autosub baseline value. The joint search below includes Wildcard/Free Hit, but whole-season option value remains unmodeled; no automatic use-now recommendation is made."
    )

    st.subheader("Joint transfer and chip search")
    st.caption(
        "Beam search over all four chips with Free Hit reversion, Wildcard persistence, free-transfer retention and chip windows. Fixed future prices, gross BB/TC gains, limited search and no value for saving beyond the horizon; advisory comparison only."
    )
    if st.button("Search transfers and chips across horizon"):
        if not st.session_state.get("confirmed") or len(team_ids) != 15:
            st.warning("Confirm current squad and financial information in Settings first.")
        else:
            try:
                from dataclasses import asdict

                from fpl_ai.optimization.chip_planning import plan_chips

                with st.spinner("Solving a limited beam of future actions…"):
                    path = plan_chips(
                        players,
                        columns,
                        rules,
                        owned=team_ids,
                        sales=st.session_state["sales"],
                        bank=int(round(st.session_state["bank"] * 10)),
                        free=int(st.session_state["free"]),
                        available_ids=set(st.session_state.get("chips", [])),
                        previous_chip=st.session_state.get("previous_chip"),
                        width=2,
                    )
                st.json(
                    {
                        "projected_net_points": path.score,
                        "steps": [asdict(step) for step in path.steps],
                        "unused_chip_ids": sorted(path.available),
                    }
                )
            except (ValueError, KeyError) as exc:
                st.error(str(exc))
