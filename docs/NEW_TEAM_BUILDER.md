# New Team Builder — implementation and verification

This feature adds initial squad creation without an account ID. It is implemented
on `feature/new-team-builder`, reusing the existing forecast functions, `solve_squad`
and Plotly pitch. No new solver or FPL write endpoint was introduced.

## Files and behavior

- `app/components/new_team_builder.py`: model/horizon/risk form, player locks and
  exclusions, three squad comparisons, starting pitch, captain/vice, ordered bench,
  all-player evidence table, CSV download, local save/reload, stale-input detection
  and the transition to Settings. Builder controls are independent of weekly-page
  sidebar controls; use Generate to submit form changes.
- `src/fpl_ai/forecasting/team_builder.py`: adapters for the existing baseline,
  trusted local ML artifact and seeded event simulation; frozen current histories,
  explicit unsupported-player details and documented risk/reliability proxies.
- `src/fpl_ai/optimization/team_builder.py`: style-specific inputs to the same
  `solve_squad`, original-mean rescoring, bench and vice selection, CSV protection,
  immutable local saves and validated saved-ID reloads.
- `src/fpl_ai/optimization/squad.py`: optional hard `locked`, `excluded` and
  `different_from` constraints. Defaults preserve weekly optimizer behavior.
- `src/fpl_ai/forecasting/rankings.py`: frozen-history ML inference now runs once
  per batch, rather than once per player per future GW; means remain unchanged.
  Empty fixture tables retain their schema and produce blanks, not invented games.
- `app/main.py`: adds the tenth page and navigation; public-ID loading clears old
  financial confirmation/selling prices, requires an explicitly entered ID, and
  handles unpublished initial picks. Drafts never populate confirmed ownership,
  actual bank, free transfers, prices or chips automatically.
- `tests/test_team_builder.py` / `tests/test_dashboard.py`: algorithm, export,
  source-refresh, error-state and complete new-user workflow coverage.

## Recommendation semantics

The existing MILP enforces the selected season budget, 15 players, position counts,
club maximum and valid weekly XI/captains. It optimizes weekly XI + captain; no
transfer hits apply to a fresh squad. Three distinct squads are produced when
feasible, using whole-squad exclusions after each previous variant. Alternative
optimality is conditional on these distinctness constraints. If locks force only
one squad, other variants are explicitly unavailable, with no relaxed constraints.

Maximum expected points uses raw forecasts, regardless of risk preference. Balanced
and Differential-focused use the explicit heuristic formulas in the README. Their
preference utilities are NOT expected FPL points. Every reported team total is
recomputed using original model means for the chosen weekly XI/captain. Player
horizon totals include their own matches, even when benched, and are labeled
separately. The reserve GK is listed separately from outfield priorities 1–3.

Raw forecast limitations remain: marginal event rates have no opponent conditioning
or teammate covariance; current injuries do not establish future recovery dates;
historical dispersion and availability exposure are uncalibrated risk proxies.
Bench order is deterministic next-GW preference order; builder totals exclude
expected autosubs/captain fallback. Existing My Team statistical lineup search
remains available for that separate approximate calculation.

## Data and model prerequisites

Baseline uses public bootstrap and fixture data. Local ML uses the same registry as
all other pages: newest `models/local-*.joblib`, with `models/ensemble.joblib` as a
legacy fallback. The 2026-11-18 repaired ZIP includes a trained local model. If none
exists, the builder directs you to Local ML to train one rather than silently
substituting baseline. Simulation requires real histories with every
required event field. Unsupported/unpurchasable players are excluded visibly; a
locked player without a forecast stops generation. Preseason missing histories are
not fabricated. No future gameweek is invented at the season end.

CSV and local saves retain real forecast rows, price, model/risk/style/season,
source timestamp, role, captain/vice, fixtures and reasons. Files go under ignored
`data/processed/new-teams/`, with unique filenames. Reloading validates season,
IDs, current purchase eligibility, composition and current budget, and restores
locks only. Current prices/forecasts must be regenerated. Files are local to the
app server; downloads are how to retain a copy on a user's own machine.

## Tests and live smoke

**Final result: 86 tests passed** (34 more than the initial 52), including the pre-existing weekly workflow. Ruff lint and format checks passed across50 Python files; compileall passed. The recorded run emitted953 upstream PuLP/NumPy deprecation warnings, which remain visible in the test log.

Exact automated output is in [new-team-builder-tests.txt](new-team-builder-tests.txt);
lint/format output is in [new-team-builder-lint.txt](new-team-builder-lint.txt).
The suite includes original tests plus supported horizon/risk combinations,
changed season budget/club/formation limits, legal pitch/bench/captain/vice,
point-total accounting, hard locks/exclusions, forced-one-squad behavior,
risk-sensitive selection, ownership preferences, model prerequisites, deterministic
history-cutoff simulation, batched ML inference, blanks, shortened horizons, CSV
roundtrips, formula safety, stale-price reload refusal and account handoff.

AppTest exercises a new user without an ID, generating three teams, downloading,
saving/reloading a draft, opening Settings, explicitly entering an ID and loading
public picks while keeping finances unconfirmed. Error regressions cover conflicting
and obsolete locks, missing local models, pre-first-deadline picks and source
changes invalidating old exports. Fixtures are deterministic only in isolated tests.

Real-data verification used the official snapshot at
**2026-10-29 19:34:53 UTC**, season2026/27, GW9–11. Each of baseline, local ML and
event simulation generated three distinct legal squads from563 supported,
purchasable players (106 others excluded). Nine squads were checked for budget,
composition, lineups, bench and distinctness. Aggregate projections and timings are
in [new-team-builder-smoke.json](new-team-builder-smoke.json).

For the maximum-mean variants, baseline cost£99.7m / bank£0.3m / forecast276.0839;
local ML£97.4m / bank£2.6m / forecast193.9831; simulation£99.6m / bank£0.4m /
forecast209.3820 over three weeks. These are **hypothetical initial-team projections**,
not realized points, accuracy scores, or a reason to prefer the most optimistic model.
Batched inference preserved all previously recorded squad expected totals within1e-6.
Observed end-to-end runs were approximately3.68s/8.55s/5.72s respectively, not SLAs.

A real-data AppTest also generated three squads with player411 locked, player400
excluded and Conservative preference, without loading any official account. The
page exposed the CSV download and no runtime exception occurred. This is functional
verification, not a visual browser/screenshot review or a season-performance claim.

No updated Docker image or remote GitHub Actions run is claimed for this feature;
the existing Dockerfile already copies the new source/app modules and no new
runtime dependency was added. Python3.12 is tested here; Windows and Python3.13 are
not newly executed. No account was registered and no real transfers were executed.
