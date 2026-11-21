"""Evaluation is readable offline and without an upcoming deadline."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st


def render(data_dir):
    st.header("Model Performance")
    reports = sorted(Path("reports").glob("local-*.json"), reverse=True)
    if reports:
        path = st.selectbox("Local evaluation report", reports, format_func=lambda p: p.name)
        report = json.loads(path.read_text(encoding="utf-8"))
        st.caption(f"Trained: {report['trained_at']} · seasons: {', '.join(report['seasons'])}")
        rows = []
        for target in ["total_points", "minutes"]:
            item = report["targets"][target]
            rows.append({"target": target, "selected_model": item["winner"], **item["test"]})
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        st.caption(
            "Untouched chronological test partition. These metrics do not establish future accuracy."
        )
        st.json(report)
    else:
        st.info("No local evaluation report yet. Open Local ML and choose Train local models.")
    legacy = data_dir / "processed/evaluation.json"
    if legacy.exists():
        with st.expander("Legacy model evaluation"):
            st.json(json.loads(legacy.read_text(encoding="utf-8")))
    backtest = data_dir / "processed/backtest.json"
    if backtest.exists():
        with st.expander("Archived backtest"):
            st.json(json.loads(backtest.read_text(encoding="utf-8")))
