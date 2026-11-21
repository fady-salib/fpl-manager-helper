# Delivery verification — 2026-10-29

The following records the initial release. For the latest New Team Builder changes
and expanded test results, see [New Team Builder verification](NEW_TEAM_BUILDER.md).

## Initial inspection

No local FPL repository existed; a GitHub search for `user:fady-salib fpl` also
returned no repositories. Created a separate local repository on `develop`.
The four earlier portfolio repositories were not changed. No FPL GitHub repository
has been published, no account action or transfer has been executed, and no
personal team state has been inferred from example entry ID 1.

## Phase 1: working live-data MVP

Implemented `api/client.py`, `storage.py`, `ingestion/refresh.py`,
`forecasting/rankings.py`, `cli.py`, `app/main.py` and pitch component.
Public source verification: all six requested endpoint families returned HTTP200;
entry history was also exercised in public lookup. The guessed game-settings
endpoint returned404 and was discarded. Rules came from bootstrap and the actual
client-rendered official rules text, not the empty HTML shell.

Live ingestion completed: **669 players, 380 fixtures, 669 histories, zero errors**.
Data are real and remain local, ignored by Git. Live baseline rankings were exported;
blank and double gameweeks are covered by deterministic unit tests. All nine
Streamlit pages opened under AppTest with real cached official data and no exceptions.
The offline suite also checks a populated, legal 15-player pitch and all nine pages.
A functional AppTest pass is not a screenshot or visual browser review.

## Phase 2: real-data ML and forecasting

Implemented `features/history.py`, `models/evaluate.py`,
`models/component_evaluation.py`, `forecasting/components.py` and training commands.
Downloaded complete current-season histories, rather than a selected-player subset.
The same data and fixed seed were used in repeated training; the reported ensemble
MAE was unchanged. Exact environment: Python3.12.14, versions in requirements-lock.

| Partition | Events | Player-fixture rows |
|---|---|---:|
| Train | 2–5 | 2,549 |
| Selection | 6 | 667 |
| Residual calibration | 7 | 667 |
| Test | 8 | 668 |

| Method | Test MAE | Test RMSE | Spearman | Top-20 overlap |
|---|---:|---:|---:|---:|
| Ridge | 1.2453 | 2.2018 | 0.6313 | 0.05 |
| Random Forest | 1.2537 | 2.1613 | 0.6695 | 0.05 |
| Gradient Boosting | 1.2538 | 2.1538 | 0.6671 | 0.10 |
| LightGBM | 1.3267 | 2.2636 | 0.6476 | 0.15 |
| XGBoost | 1.2723 | 2.1492 | 0.6804 | 0.10 |
| Selected RF/XGBoost ensemble | 1.2581 | 2.1490 | 0.6701 | 0.10 |
| Lag-3 form | 1.3468 | 2.4405 | 0.6469 | 0.00 |
| Lag-10 average | 1.2878 | 2.2919 | 0.6514 | 0.10 |
| Empirical event simulation | 1.2120 | 2.1319 | 0.6592 | 0.15 |

Ensemble nominal80% residual interval achieved77.395% test coverage. Component
p10–p90 achieved88.174% coverage; it is uncalibrated. Its simulation used1,000 draws
per player-fixture, seed42 plus player ID. Full calibration bins, bias and selected
ensemble/component by-position errors are in evaluation.json and component-evaluation.json.
Positions for these diagnostic slices use the current-season roster mapping.

Optuna research smoke: **3 completed trials** over expanding training-only Ridge
folds; best alpha0.7459343285726545, training-CV MAE1.2041938478509089. This is not
an independent test metric and did not modify the benchmark. `fpl-ai tune` defaults
to20 trials for the user's later experiment.

Limitations: only one finalized test GW; mostly zero/low scores, correlated player
rows and no archived collection-time histories. These results do not establish
season gains. Historical current-price, ownership, injury and team-strength
features are intentionally excluded. Event correlations, cold starts and future
minutes/rotation remain research work.

## Phase 3: optimization

Implemented `optimization/squad.py`, `optimization/lineup.py`,
`simulation/scoring.py`, `explainability/recommendations.py` and dashboard controls.
Real baseline input produced a proven-optimal new £100m squad for GW9–11 with15
players, £0.3m remaining and projected objective276.0839 points. This is a model
projection for a hypothetical freshly selected team, not realized points or a
recommendation for the user's unknown squad.

Regression tests verify budget, integer costs,15/11 player counts, positions,
club limits, captain eligibility, selling-profit rounding, hit costs, roll inclusion,
missing sales, unavailable purchases, infeasibility and zero-point blank weeks.
CBC time-limited incumbents are explicitly rejected unless optimality is proved;
a dedicated test covers PuLP's misleading top-level optimal status when solution
status only indicates an integer-feasible incumbent.

Statistical lineup tests cover participation despite zero points, negative returns,
reserve keeper, formation-constrained substitutions, captain fallback, Bench Boost,
Triple Captain, risk utility and deterministic finite-scenario selection.

No user team ID or actual private financial/chip state was supplied. Current-team
transfers therefore require manual confirmation in Settings before calculation.

## Phase 4: planning and chips

Implemented `optimization/planning.py`, `optimization/chips.py` and
`optimization/chip_planning.py`. Tests cover beam budget/FT transitions, saved FT
cap and retention, chip windows, consecutive-Free-Hit rejection, Wildcard hit
exemption, chip scoring multipliers, Free Hit squad/bank/FT reversion and instance
consumption. Component Monte Carlo determinism and blank-gameweek zero distributions
are tested; missing scoring statistics refuse simulation.

These are bounded fixed-price searches, not full-season global optimization.
Stateful transfers and all four chip actions are executable; the planner does not
model future price moves or the terminal value of saving chips beyond the horizon.
Gross BB value also omits expected autosubs already earned without the chip.

## Phase 5: testing, historical validation and deployment

**Final offline suite: 52 passed** (4.72s in the recorded final run;171 upstream PuLP
deprecation warnings). Ruff check and format check passed across44 Python files.
Python compileall passed. Offline tests use deterministic artificial records only;
real-data smoke and reported experiment metrics are separate.

Added `backtesting/walkforward.py` with pre-deadline snapshot cutoffs, fresh metadata,
optional deadline-local ML training, initial-entry FT correction, actual points,
autosubs, captain fallback, transfer-state updates and three clearly defined baselines.
A two-GW deterministic test checks scoring/state. Historical snapshot selection
rejects future or stale records, including player-history snapshots.

Real `fpl-ai backtest --start 2 --end 8` **refused as intended**: missing pre-deadline
bootstrap snapshot before2026-08-28 17:30UTC. No synthetic historical season score
was substituted. Full-season/chip-policy validation remains unavailable without
legitimate pre-deadline archives. Optional ML backtesting must also have archived
histories for all players; early-season insufficient histories use an explicit form
fallback. It is not claimed as an executed real-season ML backtest.

Docker image built successfully from Python3.12-slim. The non-root image's local
Streamlit health check returned `ok`; `fpl-ai refresh` inside the container fetched
669 players and380 fixtures with zero errors. The final source image was rebuilt before packaging; its non-root UID was checked as10001 and its health/live-ingestion smoke was repeated. BuildKit mounted the managed CA for build steps; it was not copied
into the image. An initial local Buildx cache path was read-only; setting a writable
BUILDX_CONFIG resolved that environment issue without changing registry credentials.

GitHub Actions test/lint matrix (3.12/3.13) and container-build jobs are supplied,
**not executed on GitHub**. Python3.13 is not locally tested. The Windows BAT was
created and inspected but cannot be executed in the Linux environment. Docker
image default excludes optional ML training dependencies; the ML extra build is
configured but the default image is the one built and smoke-tested.

## Delivery and remaining work

See implementation plan, source/rules evidence, methodology, deployment instructions,
file inventory and README. Source ZIP excludes raw football data, databases, learned
pickles, credentials and private account inputs. Source is MIT; football data are not.

Not yet validated: full historical seasons, joint teammate/opponent uncertainty,
full official assist/BPS/red-card event simulation, verified historical position
mapping, complete historical chip policies, PostgreSQL, hosted multiuser security,
load tests and long-term monitoring. The project is a working research release,
not a declaration that every requested production requirement is complete.
