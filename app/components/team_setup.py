"""Name-based public squad loading. API references are resolved internally."""

import json
from pathlib import Path

import streamlit as st

from fpl_ai.api.client import DataError, FPLClient
from fpl_ai.teams.search import normalise


def render_public_team_lookup(store, prefix="settings"):
    st.subheader("Load your FPL team")
    st.caption(
        "Find your squad by team name, then choose the matching manager. Public picks are from the last deadline; confirm later transfers yourself."
    )
    name = st.text_input(
        "FPL team name", placeholder="Your team’s name on FPL", key=f"{prefix}_team_name"
    )
    manager = st.text_input(
        "Manager name", placeholder="Full manager name shown on FPL", key=f"{prefix}_team_manager"
    )
    st.caption(
        "First connection: use RUN_FPL_MANAGER.bat and its browser helper to verify your signed-in account. "
        "FPL has no global name-search API. Verified connections can then be loaded here using both names; "
        "no league link or team ID is needed. You can also select your 15 players manually."
    )
    signature = (normalise(name), normalise(manager))
    result_key = f"{prefix}_team_matches"
    stored = st.session_state.get(result_key)
    if stored and stored["signature"] != signature:
        stored = None
    if st.button("Find my team", key=f"{prefix}_find_team"):
        try:
            if not name.strip() or not manager.strip():
                raise ValueError("Enter your team name and full manager name.")
            registry_path = Path(store.path).parent / "account-connections.json"
            saved = (
                json.loads(registry_path.read_text(encoding="utf-8"))
                if registry_path.exists()
                else {}
            )
            known = saved.get("\n".join(signature)) or st.session_state.get("official_team_id")
            if not known:
                raise ValueError(
                    "Verify your account once in the Rust app using its browser helper, then return here. You can also select your squad manually."
                )
            with st.spinner("Verifying your saved team and manager names…"):
                with FPLClient(store, retries=1, timeout=10) as client:
                    entry = client.entry(int(known))
            actual_manager = (
                f"{entry.get('player_first_name', '')} {entry.get('player_last_name', '')}".strip()
            )
            if normalise(entry.get("name", "")) != normalise(name) or normalise(
                actual_manager
            ) != normalise(manager):
                raise ValueError(
                    "The saved account did not match both names. Check the names or reconnect with the Rust browser helper."
                )
            result = {
                "league": "Verified connection",
                "scanned": 1,
                "next_page": None,
                "candidates": [
                    {"reference": int(known), "name": entry["name"], "manager": actual_manager}
                ],
            }
            stored = {"signature": signature, **result}
            st.session_state[result_key] = stored
            st.session_state[f"{prefix}_matched_team"] = 0
        except (DataError, ValueError, OSError, TypeError) as exc:
            st.error(f"Team connection failed: {exc}")
            stored = None
    if not stored:
        return False
    st.caption(
        f"Verified saved connection · {stored['scanned']} entry checked. "
        + ("More league entries have not been searched yet." if stored["next_page"] else "")
    )
    candidates = stored["candidates"]
    if not candidates:
        st.info(
            "No matching name in these entries. Check spelling, search more pages, or use a smaller public mini-league. Your current squad was preserved."
        )
        return False
    selection = st.selectbox(
        "Choose your team and manager",
        list(range(len(candidates))),
        format_func=lambda i: (
            f"{candidates[i]['name']} · {candidates[i]['manager']}"
            + (f" · league rank {candidates[i]['rank']}" if candidates[i].get("rank") else "")
        ),
        key=f"{prefix}_matched_team",
    )
    if st.button("Load public past-deadline picks", key=f"{prefix}_load_team"):
        candidate = candidates[selection]
        st.session_state["confirmed"] = False
        st.session_state["account_confirmation"] = False
        try:
            with st.spinner("Loading your selected public squad…"):
                with FPLClient(store, retries=1, timeout=10) as client:
                    entry = client.entry(candidate["reference"])
                    actual_manager = (
                        f"{entry.get('player_first_name', '')} {entry.get('player_last_name', '')}"
                    )
                    if normalise(entry.get("name", "")) != normalise(
                        candidate["name"]
                    ) or normalise(actual_manager) != normalise(manager):
                        raise ValueError(
                            "The team name changed after searching. Search again before loading; your existing squad was preserved."
                        )
                    current = int(entry.get("current_event") or 0)
                    if current < 1:
                        raise DataError(
                            "Public picks are not available before your first deadline. Keep your draft or select your squad manually in Settings."
                        )
                    picks = client.picks(candidate["reference"], current)
                    history = client.entry_history(candidate["reference"])
            ids = [p["element"] for p in picks["picks"]]
            if len(ids) != 15 or len(set(ids)) != 15:
                raise ValueError("The public API did not return 15 distinct squad players")
            st.session_state["team_ids"] = ids
            st.session_state["official_team_id"] = candidate["reference"]
            st.session_state["official_team_name"] = entry["name"]
            st.session_state["official_team_manager"] = candidate["manager"]
            st.session_state["sales"] = {}
            st.session_state["public_info"] = {
                "team_name": entry["name"],
                "manager": candidate["manager"],
                "gameweek": current,
                "history": history.get("current", []),
                "deadline_value": entry.get("last_deadline_value"),
                "deadline_bank": entry.get("last_deadline_bank"),
            }
            st.success(
                f"Loaded {entry['name']} from GW {current}. Confirm any later transfers in Settings."
            )
            return True
        except (DataError, KeyError, TypeError, ValueError) as exc:
            st.error(f"Public team lookup failed: {exc}")
    return False
