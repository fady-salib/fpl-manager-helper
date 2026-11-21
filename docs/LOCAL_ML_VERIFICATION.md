# Repaired local ML release — verified 2026-11-18

This supersedes the 2026-11-16 restoration report. The earlier ZIP contained a pipeline,
but no real trained artifact. This release includes a real trained model and measured
results, plus fixes for model discovery, navigation and team onboarding.

## Reproduced causes and changes

- No trained production artifact was included previously. Public 2023/24 and 2024/25
  CSVs were downloaded and a CPU training/evaluation run was completed for this release.
- New Team Builder searched only `models/ensemble.joblib`, while Local ML generated
  `models/local-*.joblib`. A shared registry now handles both formats; the builder has a
  forecast adapter for the new format.
- My Team required an existing squad and gave only a message directing users elsewhere.
  It now provides a public team-ID lookup inline and a route to manual Settings entry.
  Transfers explicitly explain the required squad and financial confirmations.
- The Windows batch launcher reinstalled dependencies and refreshed the API on every
  launch. It now checks installed compatibility and skips setup when ready, with no API
  preflight. scikit-learn is pinned to the bundled artifact's 1.8 series; LightGBM is a
  core dependency. The direct-dependency lock no longer contains Linux-only NVIDIA pins.
- Per-player SQLite reads, repeated fixture filtering and model reloads/prediction on
  reruns were replaced with bulk history queries, shared fixture contexts, resource
  caching and revision-keyed forecast caching. Global ML ranking now remains sorted.
- Stored public snapshots are used during navigation. Refresh is explicit, with visible
  timestamps and stale warnings. Ordinary page changes do not wait for API retries.
- Model Performance reads new reports without requiring live data or an upcoming deadline.
- Historical download, optional current-history refresh and retraining are separate UI
  actions. Missing historical files can be downloaded during an explicitly requested train.

## Training evidence

Downloaded real archive records: 29,725 (2023/24), 27,605 (2024/25). Assistant-manager rows
are excluded from player modeling. Prepared rows: 55,347; training 33,391, validation
10,366, test 11,590. No synthetic records were used for this model.

Training: 2023/24 GW2 through 2024/25 GW8. Validation: 2024/25 GW9–23.
Test: 2024/25 GW24–38. Models were selected on validation and evaluated on test without
refitting. Random Forest, LightGBM and XGBoost regression candidates all ran on CPU.

- Points: selected LightGBM. Test MAE 0.961791, RMSE 1.888784, bias -0.005322.
  Recent-form test MAE 0.988937; historical-average test MAE 1.022806.
- Minutes: selected recent form (the last five matches), which beat the trained candidates
  on validation. Test MAE 12.971419, RMSE 24.603381, bias 0.197246.
- Labeled start, goal, assist and clean-sheet classifiers were trained; reports include
  held-out Brier scores and calibration bins.

These metrics cover all player-fixture rows including non-appearances and zeros; they
are not a claim of starting-XI forecasting accuracy or future FPL performance. See the
versioned report and training log in `reports/` for parameters, features, dataset hashes,
position/season breakdowns and limitations.

## Tests and performance

- Before repair: original 95-test suite passed in the complete dependency environment.
- Final suite: **100 passed**, including new tests for inline My Team loading, new-format
  builder artifacts, bulk point-in-time reads, forecast cache reuse, and offline ML/report
  page access. Full output: `docs/local-ml-test-results.txt`.
- `ruff check .`: passed. `ruff format --check .`: passed.
- `python -m compileall -q src app scripts tests`: passed.
- `scripts/verify_local_install.py`: found the saved model, cached data and available CBC.
- All 11 pages rendered using Streamlit AppTest and real public cached FPL data: 672 players,
  380 fixtures and 6,562 history rows. A populated My Team rendered successfully.
- A real-data squad optimization completed in 0.327 seconds. New Team Builder generated
  three distinct constrained squads with the saved ML artifact in 5.608 seconds.
- On this Linux cloud machine: first Overview 5.822 seconds; subsequent page loads
  0.039–0.926 seconds; populated My Team 0.404 seconds. These are not native Windows
  timings or guarantees. Raw timings: `reports/live-page-smoke.json`,
  `reports/live-builder-smoke.json` and `reports/performance-repair.json`.
- Windows batch execution and GPU execution were not tested. Training used CPU only.
- No private team lookup was performed. Inline lookup integration used deterministic
  test fixtures; live UI checks used public player metadata and a locally generated squad.

## Data and modeling limits

Public snapshot timestamps are visible and must be refreshed before acting on stale
prices/injuries. Full histories update only on request. The bundled SQLite file contains
bootstrap, fixtures and player histories, not user entries, credentials or confirmed
private financial information. Existing user data should be kept in a separate backup;
extract this release into a new folder.

Features use past player outcomes with entire target rounds excluded. Deadline availability
is approximated; retrospective stat corrections prevent a strict point-in-time guarantee.
No trained opponent/home/FDR/price/ownership/injury-recovery effects are claimed. Future
history is frozen; probabilities/minutes are per fixture. Historical blanks are absent;
scoring rules can change between training and live seasons. One immediate transfer set
is held over the horizon; later transfer/chip scheduling and stochastic bench effects are
not implemented by the new adapter. Existing season guards and appearance-aware tools
remain intact.

No original user data was overwritten and no commits or pushes were made.
