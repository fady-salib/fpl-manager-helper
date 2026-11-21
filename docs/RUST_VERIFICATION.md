# Rust migration verification — 2026-11-18

## Delivered architecture

The new default app is a compiled Rust server (`rust/`, `bin/fpl-manager.exe`) with
embedded, offline HTML/CSS/JavaScript. Axum/Tokio serves loopback-only HTTP. Rust reads
SQLite snapshots, engineers lagged features, evaluates exported fitted trees and solves
squad/transfer MILPs with a pure Rust solver. Page navigation uses already loaded browser
data; it does not rerun Python, query SQLite or restart inference. Normal use requires
no Python, Node, Rust toolchain or paid API.

Python remains the explicit local scientific training/export tool. Training runs in a
background task only on request. The original Streamlit UI/CLI is preserved, with a
separate legacy launcher for research features not moved into the native interface.
This is not a claim that Python ML training was rewritten in Rust.

## Numerical/model evidence

- Real fitted model from 2023/24 and 2024/25, not synthetic training data.
- Exported LightGBM trees, Random Forest probability forests, preprocessing medians and
  the validation-selected recent-form minutes predictor to portable JSON.
- 672-player fitted-model parity and full raw-history-pipeline parity passed: exact
  points/minutes agreement, probability errors at rounding scale, tolerance 1e-8.
- JSON float-round-trip parsing and Random Forest float32 input conversion were necessary
  to preserve threshold decisions. Original evaluation report and limitations are retained.
- Native export schema 1 supports LightGBM, Random Forest, baselines and constant
  probabilities. Native retraining uses supported candidates. Original Python XGBoost
  experiments remain available; XGBoost-to-native export is explicitly unsupported.

Evidence: `reports/rust-prediction-parity.json`, `rust-full-pipeline-parity.json` and
`models/native-model.json`. No new forecasting accuracy or GPU performance is claimed.

## Tests and interface checks

- **103 Python tests passed**, including portable export/inference tests.
- **12 Rust tests passed**: tree traversal, missing baseline values, leakage cutoff,
  completion cutoff, squad/XI/bench constraints, fixed squads without financial input,
  transfer selling prices/hits, season guard, Free Hit reversion and prevention of
  fake selling-price discounts for a new squad.
- Rust formatter and Clippy with all targets / warnings denied passed.
- Python Ruff lint/format and compilation, JavaScript syntax checks passed.
- Headless Chromium exercised all 10 native routes, squad creation, local draft use,
  player search/details, financial confirmation and transfer jobs, with no JS errors.
- Desktop and 390px mobile body-overflow checks passed. Pitch rows support legal
  five-player formations. Screenshots are in `reports/rust-ui/`.
- Inline public team-ID loading was tested with a mocked public response built from a
  local generated squad. It produced 11 starters + 4 bench and reset private financial
  confirmation. No real manager's account was queried for tests.
- The native HTTP client successfully refreshed real official metadata and fixtures,
  honored the configured CA trust, appended snapshots and wrote real SHA256 hashes.
  Network failure handling preserved cached data. TLS was never disabled.
- Cross-origin mutation rejection was checked (403).

## Measured performance

On this Linux cloud machine, a browser run measured cold Overview at 0.809 seconds
(including Playwright's network-idle wait), and route changes roughly 16–44 ms.
Cached state API median was 1.45 ms, p95 2.46 ms. Model/history initialization took about
0.4–1 second across runs. The full real pool was 672 players with 6,562 history records.
Native squad building completed in about 0.1 seconds in the tested pool. Results depend
on hardware and horizon; the native MILP has a 10-second limit. A feasible incumbent
returned at the limit is labeled as such, not advertised as proven optimal.

Raw measurements: `reports/rust-ui/browser-results.json`, `rust-api-performance.json`,
`rust-refresh-smoke.json`, `rust-team-ui-smoke.json`. These are not Windows guarantees.

## Windows build and runtime boundary

`bin/fpl-manager.exe` is a release x86_64-pc-windows-gnu build using static compiler
runtime linking. PE imports were inspected: only Windows system DLLs, no Python,
LightGBM, SQLite, libgcc or winpthread runtime DLL dependencies. SQLite and fitted-model
inference are built into the native app. Assets are embedded in the executable.

The Windows executable and batch/PowerShell launcher were **not executed on native
Windows**. They were cross-compiled on Linux, while the corresponding native Linux build
passed runtime, API and browser checks. This limitation is material and disclosed in
README_RUST.md. No external executable downloads occur on normal launch.

## Preserved constraints and limits

- Legal FPL squad/formation/budget/club constraints and transfer hits are not relaxed.
- Confirmed selling prices apply only to owned players; a new team always uses market
  purchase prices. Chips require a confirmed unused instance and an official window.
- Free Hit lasts one week and reverts; BB/TC are first-week-only. No future transfer
  scheduling, future chip-date optimization or expected autosub modeling is claimed by
  the native optimizer. The legacy research tools remain available separately.
- Current model has no trained opponent/home/FDR/ownership/price/injury-recovery effects.
  Future history is frozen. Probabilities/minutes are per fixture. Corrected historical
  statistics and approximate cutoffs prevent a strict archived point-in-time guarantee.
- Public timestamps remain visible. Explicit refresh is needed before acting on stale
  prices/injuries. Private financial inputs live in browser local storage and are sent
  only to the local Rust optimizer, never to FPL. The bundled database contains public
  bootstrap, fixtures and player histories, not manager entries or private finances.
- Native data lives in data/ and models/ under FPL_PROJECT_DIR. Legacy FPL_DATA_DIR is
  retained for the Python app only. Existing user datasets should be backed up; extract
  the new release into a fresh folder.

No commits, pushes, paid prediction services or cloud deployment were performed.
