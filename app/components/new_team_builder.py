"""New-team page; draft state is separate from confirmed weekly account state."""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path

import pandas as pd
import streamlit as st
from components.pitch import pitch
from components.runtime import cached_rankings

from fpl_ai.forecasting.team_builder import MODELS, RISKS, prepare_forecasts
from fpl_ai.optimization.team_builder import build_squads, load_draft, save_squad, squad_csv
from fpl_ai.rules import Rules


def _signature(
    bootstrap: dict,
    fixtures: list[dict],
    histories: pd.DataFrame,
    snapshot_at: str | None,
    controls: tuple,
) -> str:
    digest = hashlib.sha256(
        json.dumps(
            [bootstrap, fixtures, snapshot_at, controls], sort_keys=True, default=str
        ).encode()
    )
    digest.update(pd.util.hash_pandas_object(histories, index=True).values.tobytes())
    from fpl_ai.ml.registry import model_path

    model = model_path()
    if model is not None:
        digest.update(f"{model.stat().st_mtime_ns}:{model.stat().st_size}".encode())
    return digest.hexdigest()


def render_new_team_builder(
    bootstrap: dict,
    fixtures: list[dict],
    histories: pd.DataFrame,
    rules: Rules,
    data_dir: Path,
    snapshot_at: str | None,
) -> None:
    st.header("New Team Builder")
    st.write("Build your first 15-player squad from scratch. No FPL team ID is needed.")
    st.caption(
        f"{rules.season.replace('_', '/')} initial budget £{rules.budget / 10:.1f}m · "
        f"max {rules.club_limit} per club · positional rules from the official season configuration."
    )
    # This metadata pool is for selectors and validating saved IDs, not the chosen model's predictions.
    available = cached_rankings(
        bootstrap,
        fixtures,
        1,
        pd.DataFrame(),
        clock_bucket=int(pd.Timestamp.now(tz="UTC").timestamp() // 60),
    )
    selectable = available.sort_values(["name", "id"])
    names = {
        int(r.id): f"{r['name']} · {r.club} · £{r.price:.1f}m [{r.id}]"
        for _, r in selectable.iterrows()
    }
    # Preserve obsolete locks visibly: never drop a hard constraint during refresh.
    for key in ("builder_locks", "builder_exclusions"):
        for player_id in st.session_state.get(key, []):
            names.setdefault(player_id, f"Unavailable player [{player_id}] — unlock to regenerate")
    drafts_dir = data_dir / "processed" / "new-teams"
    saved = sorted(drafts_dir.glob("squad-*.csv"), reverse=True) if drafts_dir.exists() else []
    with st.expander("Saved local drafts"):
        st.caption(
            "Drafts live on this app's machine, not your FPL account. Reloading restores player locks; generate again to use current prices and forecasts."
        )
        if saved:
            chosen = st.selectbox(
                "Saved draft", saved, format_func=lambda p: p.name, key="builder_saved_file"
            )
            if st.button("Load saved draft as player locks", key="builder_load"):
                try:
                    ids = load_draft(chosen, available, rules)
                    st.session_state["builder_locks"] = ids
                    st.session_state["builder_exclusions"] = []
                    st.session_state.pop("builder_results", None)
                    st.success(
                        "Restored all 15 as locks. You can unlock players before generating."
                    )
                except (ValueError, OSError) as exc:
                    st.error(f"Cannot load draft: {exc}")
        else:
            st.caption("No saved draft yet. Generate a team and choose Save draft locally.")
    with st.form("new_team_builder_form"):
        c1, c2, c3 = st.columns(3)
        model = c1.selectbox("Builder prediction model", MODELS, key="builder_model")
        horizon = c2.selectbox(
            "Builder planning horizon (GWs)", [1, 3, 5, 8], index=1, key="builder_horizon"
        )
        risk = c3.selectbox("Builder risk preference", RISKS, index=1, key="builder_risk")
        locked = st.multiselect(
            "Lock players", list(names), format_func=names.get, key="builder_locks"
        )
        excluded = st.multiselect(
            "Exclude players", list(names), format_func=names.get, key="builder_exclusions"
        )
        generate = st.form_submit_button("Generate three squads", type="primary")
    st.caption(
        "Risk applies to Balanced and Differential-focused. Maximum expected points remains a risk-neutral reference. Baseline/ML risk uses historical dispersion or an availability-only proxy; simulated risk is uncalibrated."
    )
    controls = (model, horizon, risk, sorted(locked), sorted(excluded))
    signature = _signature(bootstrap, fixtures, histories, snapshot_at, controls)
    if generate:
        st.session_state.pop("builder_results", None)
        try:
            artifact = None
            if model == "Locally trained ML":
                from components.runtime import load_model, model_key

                from fpl_ai.ml.registry import model_path

                path = model_path()
                if path is None:
                    raise ValueError(
                        "No local ML model. Open Local ML and choose Train local models."
                    )
                artifact = load_model(*model_key(path))
            with st.spinner("Forecasting players and solving three constrained squads…"):
                forecast = prepare_forecasts(
                    bootstrap, fixtures, histories, model=model, horizon=horizon, artifact=artifact
                )
                result = build_squads(
                    forecast,
                    rules,
                    risk=risk,
                    locked=set(locked),
                    excluded=set(excluded),
                    snapshot_at=snapshot_at,
                )
            st.session_state["builder_results"] = (signature, forecast, result)
            styles = [s.style for s in result.squads]
            st.session_state["builder_variant"] = "Balanced" if "Balanced" in styles else styles[0]
        except (
            ValueError,
            KeyError,
            TypeError,
            OSError,
            ImportError,
            pickle.UnpicklingError,
            EOFError,
        ) as exc:
            st.error(f"Cannot build squads: {exc}")
            st.info(
                "Check conflicting locks/exclusions and available budget. Missing histories or a local ML artifact must be supplied; the builder will not silently switch models or relax rules."
            )
    stored = st.session_state.get("builder_results")
    if stored is not None:
        old_signature, forecast, result = stored
        if old_signature != signature:
            st.info(
                "Inputs or source data changed. Generate again before exporting or saving a recommendation."
            )
        else:
            for note in forecast.notes:
                st.caption(note)
            if forecast.unavailable:
                st.warning(
                    f"{len(forecast.unavailable)} players excluded from this model's pool because they are unpurchasable or lack supported forecasts."
                )
                with st.expander("Unavailable forecast details"):
                    st.dataframe(
                        pd.DataFrame(
                            [{"id": i, "reason": why} for i, why in forecast.unavailable.items()]
                        ),
                        hide_index=True,
                    )
            for style, why in result.unavailable_styles.items():
                st.warning(
                    f"{style} could not produce a distinct proven-optimal squad: {why}. Locks and season rules were preserved."
                )
            st.caption(
                f"Generated draft: {forecast.model} · {result.squads[0].risk} preference · {len(forecast.columns)} GWs. Submit form changes with Generate three squads before using a new configuration."
            )
            comparison = pd.DataFrame(
                [
                    {
                        "Squad": s.style,
                        "Expected horizon points (XI + captain)": s.plan.expected_points,
                        "Cost (£m)": (rules.budget - s.plan.bank) / 10,
                        "Remaining (£m)": s.plan.bank / 10,
                    }
                    for s in result.squads
                ]
            )
            st.dataframe(comparison, hide_index=True)
            style = st.radio(
                "Recommended squad variant",
                [s.style for s in result.squads],
                key="builder_variant",
                horizontal=True,
            )
            squad = next(s for s in result.squads if s.style == style)
            first = forecast.columns[0]
            frame = forecast.players.set_index("id")
            captain, vice = squad.plan.captains[first], squad.vice[first]
            c1, c2, c3 = st.columns(3)
            c1.metric("Total squad cost", f"£{(rules.budget - squad.plan.bank) / 10:.1f}m")
            c2.metric("Remaining budget", f"£{squad.plan.bank / 10:.1f}m")
            c3.metric(
                "Predicted horizon points · XI + captain", f"{squad.plan.expected_points:.2f}"
            )
            st.caption(
                f"GW {first.split('_')[1]} captain: {frame.at[captain, 'name']}; vice-captain: {frame.at[vice, 'name']}. Fixed squad over {len(forecast.columns)} GWs, with weekly lineups; no transfer hits for initial selection."
            )
            st.plotly_chart(
                pitch(forecast.players, squad.plan.lineups[first], captain, vice), width="stretch"
            )
            st.subheader("Bench order")
            st.caption(
                "Reserve goalkeeper is separate from outfield priorities 1–3. Outfield order uses next-GW preference scores, without stochastic autosub optimization."
            )
            bench = squad.table.set_index("id").loc[squad.bench[first]]
            st.dataframe(
                bench[["role", "name", "position", "price", "next_points", "horizon_points"]],
                hide_index=True,
            )
            st.subheader("All 15 players and selection evidence")
            fixture_cols = [f"fixtures_{col.split('_')[1]}" for col in forecast.columns]
            display = [
                "id",
                "role",
                "name",
                "club",
                "position",
                "price",
                "captain",
                "vice_captain",
                "next_points",
                "horizon_points",
                *forecast.columns,
                *fixture_cols,
                "reason",
            ]
            st.dataframe(squad.table[display], hide_index=True)
            st.caption(
                "Player horizon points sum their own fixtures. The team total above counts each week's starting XI plus captain, not all fifteen. Preference utility and differential bonuses are never displayed as extra expected points."
            )
            weekly = pd.DataFrame(
                [
                    {
                        "Gameweek": col.split("_")[1],
                        "Expected XI + captain points": squad.plan.weekly_points[col],
                        "Captain": frame.at[squad.plan.captains[col], "name"],
                        "Vice": frame.at[squad.vice[col], "name"],
                    }
                    for col in forecast.columns
                ]
            )
            st.dataframe(weekly, hide_index=True)
            st.download_button(
                "Download squad CSV",
                squad_csv(squad),
                file_name="fpl-new-team.csv",
                mime="text/csv",
                key="builder_download",
            )
            if st.button("Save draft locally", key="builder_save"):
                try:
                    path = save_squad(squad, drafts_dir)
                    st.session_state["builder_saved_notice"] = path.name
                    st.rerun()
                except OSError as exc:
                    st.error(f"Could not save draft: {exc}")
    if st.session_state.get("builder_saved_notice"):
        st.success(f"Saved draft: {st.session_state['builder_saved_notice']}")
    st.subheader("After registering your official FPL team")
    st.write(
        "Register and select players on the official FPL website yourself. Then open Settings, enter your FPL team name and public classic mini-league link, choose the matching manager, and load public past-deadline picks. Confirm later transfers, actual selling prices, bank, free transfers and unused chips there before using My Team or Transfers. Picks may be unavailable until your first deadline."
    )
    if st.button("Open weekly management Settings", key="builder_to_settings"):
        st.session_state["builder_go_settings"] = True
        st.rerun()
