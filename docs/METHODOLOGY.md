# Forecasting and evaluation methodology

## MVP baseline

Live official form and season points per match are blended 70/30, scaled per
scheduled fixture with a small documented FDR exponent (0.35). Blank = zero;
doubles sum two fixture projections. Current availability is a heuristic factor on
the next GW only, not a trained medical/rotation forecast. Predictions are not
actual observations. No form-based price/ownership weight is disguised as ML.

## Direct models

Fixture targets; per-player lagged per-fixture means from prior 3,5,10 gameweeks for
points, minutes, xG, xA, goals, assists, bonus, saves, conceded, starts and ICT,
plus prior sample count, point variability and rest days. No target-week results
enter any feature, including the earlier match of a double gameweek. Previous
rounds finishing after a deadline are excluded by the conservative 3h cutoff.
Current ownership, team/position mappings, FDR, prices, injury and set-piece
information are not inserted into historical training features.

Median imputation is trained inside each model's training pipeline. Ridge scales
features; tree models use reproducible seeds and one CPU worker. Selection compares
validation MAE for Ridge/RF/GB/LightGBM/XGBoost; the best two ML estimators are averaged.
This is equal-weight validation selection, not an in-sample fitted stacker.
The model remains trained only on its declared training block; a later production
refit would need a new calibration block and a separately frozen evaluation record.

The last three available feature-bearing GWs are selection, residual calibration
and test; earlier GWs train. At least seven are required. Optuna uses expanding
folds strictly inside the training block; the provided Ridge tuning report does
not retroactively alter the published comparison or access final test labels.

The nominal 80% residual range uses a finite-sample calibration-error order
statistic on the distinct calibration block. On GW8 actual ensemble coverage was
77.4%, not a guarantee of future coverage. Temporal drift and correlated player
observations invalidate simple exchangeability claims. Live FDR/news adjustments
change the prediction distribution further; no calibrated live interval is claimed.

`MAE/RMSE` use points, Spearman uses all fixture rows, top20 overlap is per-GW
intersection of 20 highest predicted/observed **fixture rows**. It is not an FPL
manager score and ties at top-20 boundaries are handled by deterministic row order.
Calibration bins compare predicted mean to actual mean; this is regression
calibration, not classification probability calibration.

## Component simulation

Sample a prior real fixture's minutes, starts and empirical disciplinary/bonus/
defensive events. Conditional Poisson attacking rates use historical xG and xA per
minute; goalkeeper saves and opponent concessions use per-minute rates. The same
simulated conceded variable determines a clean sheet and concession deductions.
Availability is shared within a player's double GW. This preserves part of the
minutes-event and clean-sheet-concession dependence, but not teammate/opponent
covariance or goal-assist exclusivity. Historical bonus is not a full BPS model;
red-card future concessions and detailed assist rules are incomplete.

Compare on the same held-out fixture rows with:

```
fpl-ai evaluate-components
```

The recorded GW8 component baseline MAE was 1.2120, RMSE2.1319, Spearman0.6592,
with p10–p90 empirical coverage88.17%. These are one-week reconstructed-history
results, not proof it is the better season manager. The component method was not
selected using an independent multi-season validation archive. Position-specific
scores use the current-season position mapping; this mapping is not asserted to
be a verified historical roster snapshot. All scoring-event simulation fields must
be present; otherwise the forecast is unavailable.

## Lineups, risk and plans

MILP's main objective uses unconditional point means but excludes expected fallback
and autosubs. A separate Monte Carlo lineup optimizer evaluates official formation
and reserve-GK substitution, ordered outfield substitutes and captain fallback on
aligned scenarios. It evaluates all bench permutations for each candidate and
locally swaps feasible XI players. Finite scenarios and local search mean no global
optimality. Captain pairs maximize captain-bonus utility before full team utility;
this too is an approximation for risk-adjusted whole-team utility.

Risk utilities are explicit: conservative `mean − 0.25*std`; expected `mean`;
aggressive `mean + 0.25*(p90−mean)`. They express preferences, not empirical optimality.
Player marginals are independent except within-player event dependence; team risk
estimates may under/overestimate covariance. 128 UI scenarios keep searches bounded;
use larger counts and stability checks before trusting tiny differences.

Multiweek transfer and chip beams carry squad, bank, selling basis, FT count and
remaining chip instances. Prices are held fixed; action proposals optimize a
held-squad future horizon and score the immediate week at each transition. FH
reverts the squad/bank/sales, WC keeps them, both preserve saved FT. BB/TC are gross
approximate opportunity gains. No terminal value for saving a chip beyond the
horizon is estimated, so short-window chip use is not a whole-season recommendation.

## Historical manager benchmark

Deadline snapshots, source hashes, past-deadline player/fixture metadata and final
actual results are required. Form and historical-average baselines and archived
official expected points are compared without using later prices or injuries.
Points use realized autosubs and captain fallback. The walk-forward benchmark supports one transfer/week and no chips. `--include-ml` retrains at each deadline from archived player histories, selecting and calibrating only on earlier weeks; early weeks with insufficient training history explicitly use form. Complete chip-policy backtesting and multi-season validation remain unfinished. The selected ensemble reports held-out by-position errors using the current roster mapping; per-position squad forecast error is recorded by the manager simulator. A synthetic two-GW unit test verifies state/scoring, but is
not reported as real FPL performance. There is no historical season-total claim.
