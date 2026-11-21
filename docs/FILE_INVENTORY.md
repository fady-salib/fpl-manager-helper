# Source inventory

All source was newly created in this separate repository. Roles below describe actual executable modules; empty `__init__.py` files only establish packages.

- `app/components/pitch.py` — Plotly football-pitch diagram from selected player IDs.
- `app/main.py` — Ten-page Streamlit dashboard and manually confirmed team state.
- `scripts/reproduce.py` — Fail-fast real-data reproduction command sequence.
- `src/fpl_ai/__init__.py` — Package initialization.
- `src/fpl_ai/api/__init__.py` — Package initialization.
- `src/fpl_ai/api/client.py` — Public GET API, strict endpoint allowlist, validation, pacing, cache and bounded retries.
- `src/fpl_ai/backtesting/__init__.py` — Package initialization.
- `src/fpl_ai/backtesting/walkforward.py` — Deadline-snapshot manager benchmark, ML refit option, scoring/state accounting.
- `src/fpl_ai/cli.py` — Collection, rankings, training, tuning, evaluation, optimization and backtesting commands.
- `src/fpl_ai/explainability/__init__.py` — Package initialization.
- `src/fpl_ai/explainability/recommendations.py` — Objective-derived explanations and model sensitivity helper.
- `src/fpl_ai/features/__init__.py` — Package initialization.
- `src/fpl_ai/features/history.py` — Typed histories and lag-only, deadline-filtered feature construction.
- `src/fpl_ai/forecasting/__init__.py` — Package initialization.
- `src/fpl_ai/forecasting/components.py` — Empirical minutes plus conditional event Monte Carlo using reviewed scoring.
- `src/fpl_ai/forecasting/rankings.py` — Live baseline/ML projections, fixture rows, value and differential scores.
- `src/fpl_ai/ingestion/__init__.py` — Package initialization.
- `src/fpl_ai/ingestion/refresh.py` — Resumable full-player ingestion with explicit errors.
- `src/fpl_ai/models/__init__.py` — Package initialization.
- `src/fpl_ai/models/component_evaluation.py` — Same-holdout evaluation of event-model forecasts.
- `src/fpl_ai/models/evaluate.py` — Chronological model selection/calibration/evaluation and training-only Optuna.
- `src/fpl_ai/optimization/__init__.py` — Package initialization.
- `src/fpl_ai/optimization/chip_planning.py` — Four-chip beam search with transfer and chip-state transitions.
- `src/fpl_ai/optimization/chips.py` — Gross BB/TC opportunity screens over eligible windows.
- `src/fpl_ai/optimization/lineup.py` — Finite-scenario XI local search with bench/captain fallback and risk utility.
- `src/fpl_ai/optimization/planning.py` — Stateful fixed-price transfer beam search.
- `src/fpl_ai/optimization/squad.py` — Integer-money MILP, legal squads/lineups, actual sales, hits, captain and chips.
- `src/fpl_ai/rules.py` — Reviewed season profile, free-transfer state and chip eligibility.
- `src/fpl_ai/simulation/__init__.py` — Package initialization.
- `src/fpl_ai/simulation/scoring.py` — Realized formation-respecting substitutions and captain/chip multipliers.
- `src/fpl_ai/storage.py` — Append-only SQLite snapshots and timestamp-cutoff lookup.
- `tests/conftest.py` — Offline deterministic regression tests for conftest.
- `tests/test_backtest.py` — Offline deterministic regression tests for backtest.
- `tests/test_dashboard.py` — Offline deterministic regression tests for dashboard.
- `tests/test_models.py` — Offline deterministic regression tests for models.
- `tests/test_mvp.py` — Offline deterministic regression tests for mvp.
- `tests/test_optimization.py` — Offline deterministic regression tests for optimization.
- `tests/test_simulation.py` — Offline deterministic regression tests for simulation.

Configuration: `pyproject.toml` declares supported dependencies/CLI and lint/test settings; `requirements-lock.txt` records the observed environment; `configs/research.toml` documents defaults (not an implicit configuration override); Dockerfile/CI provide deployment/build checks; `.gitignore` and `.dockerignore` exclude private and generated artifacts.

## New Team Builder additions

- `app/components/new_team_builder.py` — model/horizon/risk form, pitch, alternative comparison, CSV/local drafts and Settings handoff.
- `src/fpl_ai/forecasting/team_builder.py` — adapters for existing baseline, local ML and event simulation; explicit missing-data handling and risk proxies.
- `src/fpl_ai/optimization/team_builder.py` — three style objectives around `solve_squad`; recomputes original expected points, bench/vice and local draft roundtrips.
- `tests/test_team_builder.py` — budget/formation/club/lock/risk/model/export regressions across supported horizons.
- `tests/test_dashboard.py` — new no-ID build/save/reload/official-ID workflow coverage alongside existing pages.

`solve_squad` now accepts optional `locked`, `excluded` and `different_from` constraints, with unchanged defaults. `rank_players` batches frozen-history ML predictions instead of repeating inference per player per future GW. Empty fixture tables retain their schema. No separate squad solver was introduced.
