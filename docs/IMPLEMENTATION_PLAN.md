# Implementation plan and acceptance criteria

The workspace contained no existing FPL application on 2026-10-29. This is a new,
separate repository; no earlier portfolio repository is modified.

1. **MVP:** public read-only HTTP client with bounded retry/backoff, request pacing,
   SQLite append-only timestamped snapshots, schema checks, explicit freshness;
   live fixture-aware baseline rankings and Streamlit pages; offline tests and live smoke.
2. **ML:** player histories; features based on earlier gameweeks and completion before
   target deadlines; chronological train / selection / interval-calibration / untouched
   test blocks. Baseline, Ridge, RF, gradient boosting, optional LightGBM/XGBoost;
   validation-selected ensemble, reproducible metrics, uncertainty and Optuna tooling.
3. **Optimization:** dynamic squad/formation rules; integer money; budget/club/position
   MILP; current-team sales, transfer hits, explicit roll alternative; XI/captain/bench;
   exact realized autosubs scoring; edge-case and infeasibility tests.
4. **Planning:** deterministic seeded player Monte Carlo; documented simplified event
   dependencies; rolling-horizon beam search over transfers and bank/free-transfer
   state; chip opportunity estimates gated by availability/windows; differentials.
5. **Validation/delivery:** walk-forward historical decisions from archived deadline
   snapshots, baselines, no hindsight prices or injuries; explicitly refuse a full-season
   claim without those data. CI, Docker, reproducible commands, source/rules audit,
   limitations and measured results. Validate a real-data local dashboard session.

## Research boundaries

Current endpoints are not a historical point-in-time archive. Recent match histories
can support lag-outcome experiments, not a fully faithful historical manager backtest.
Never join current injuries, ownership, prices, difficulty or team strengths onto past
training deadlines. Save snapshots now for prospective backtesting. Full-season
results require independently licensed, point-in-time inputs and selected-season rules.
Never execute transfers. Never scrape authenticated account pages or store passwords.

## Delivery scope

Implement working pieces in each phase, but label approximate forecasting, limited
planning search and unverified rules explicitly. No fabricated model scores, no
claim of production readiness from unit tests alone. Each phase's evidence is recorded
in `docs/VERIFICATION.md` after execution.
