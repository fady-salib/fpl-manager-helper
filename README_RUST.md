# FPL Manager — Rust edition

**v0.5.0-beta.3:** Uses the supplied FPL crest for the Windows executable and taskbar.

**v0.5.0-beta.2:** The first-run tutorial opens automatically after the app loads.
Use **Settings > App tutorial** to reopen it.

**v0.3.0:** Aggressive, Balanced and Conservative playing styles. Connection uses only
team name and manager name, with one-time browser-helper verification. See
[PLAYING_STYLE_UPDATE.md](PLAYING_STYLE_UPDATE.md) for this app-only update.

A local Rust application with an FPL-inspired browser interface: purple/green styling,
a football pitch, shirt icons, compact player tables and a mobile layout. This is an
independent tool, not the official FPL website.

## Windows: single-file desktop app

Open **FPL Manager.exe**. On first run, enter your FPL team name and manager name,
click **Connect my team**, then sign in on the official FPL page that opens inside the
app. The desktop runner imports the current squad, selling prices, bank and remaining
free transfers when FPL supplies them. It reuses its browser session on later runs and
syncs on startup. The Chrome connector and batch launcher are for the browser edition.

For a standard transfer recommendation, choose **Review and apply on FPL**. The
official page opens inside the app with the moves staged. Check the players and
points cost, then choose FPL's **Confirm** button. The manager syncs after FPL
reports the updated squad.

The executable includes the local engine, public snapshots, model and WebView2
bootstrapper. First run prepares its files in your local Windows app-data folder.
Optional local model retraining still uses the Python environment described below.

## Windows: browser edition

1. Extract the **whole** ZIP into a new folder. Keep your previous installation as a
   backup; do not replace a personal database with the bundled public database.
2. Double-click **RUN_FPL_MANAGER.bat**. It starts `bin/fpl-manager.exe` and waits for
   the server to be ready before opening `http://127.0.0.1:7878`.
3. Open **My team**, enter your team name and full manager name. Install the included
   Chrome/Edge helper once, click **Connect my team**, sign in on official FPL and click
   the helper's **Continue with FPL**. Future connections reuse the verified reference.
   No league link, team ID or password is entered into this app.
4. On Transfers or Settings, choose **Load squad and selling prices from FPL**.
   In the FPL tab that opens, use the connector's **Continue with FPL** button.
   Then confirm bank and free transfers in Settings and save before comparing transfers.
   If you already installed the connector, reload it once on your browser's Extensions page
   to pick up selling-price import.

**Normal use needs no Python, Streamlit, Rust installation, Node.js, GPU or paid API.**
The full release contains an x64 Windows executable, public snapshot database and a portable
export of the real trained model. This small update contains the app only: retain your existing
`data/` and `models/` folders. Supported target: Windows 10/11 x64. The executable
was cross-compiled and checked for system-DLL dependencies on Linux; it has **not** been
executed on native Windows in this environment. Browser and native runtime tests ran on
Linux. Keep the app's console window open; close it or press Ctrl+C to stop the server.

The app binds only to `127.0.0.1`. Team financial information is saved in this browser's
local storage, not sent to FPL. Settings can export/import a private JSON backup. Public
snapshots in the ZIP do not contain user entries or financial inputs.

## What actually moved into Rust

- HTTP server and embedded HTML/CSS/JavaScript assets (Axum/Tokio).
- Reading official public-data snapshots from the existing SQLite schema.
- Lag-only feature calculations for all current players.
- Native fitted-tree inference: LightGBM points, Random Forest probabilities, and the
  validation-selected recent-form minutes predictor. No Python subprocess per request.
- Native MILP squad/transfer optimization using `good_lp` + `microlp`, including
  positional quotas, legal XIs, club limits, bank/selling prices and transfer hits.
- Exact formation enumeration for a fixed squad, plus captain, vice and bench ranking.
- Official metadata/history downloads, caching, retries and explicit background tasks.

The single-page frontend changes routes locally. Navigation does not restart model
inference, read SQLite again or request the FPL API. The server precomputes forecasts
at startup, after refresh/retraining and when a cached deadline boundary passes. Cached
public timestamps are visible; refresh before using stale prices/injuries.

## Model conversion and retraining

The original trusted `models/local-*.joblib` artifact remains included. Its fitted trees
are exported as **models/native-model.json**. The Rust app reads only this portable JSON;
it does not deserialize pickle/joblib files. The export preserves preprocessing medians,
threshold comparisons and Random Forest float32 input behavior. JSON floating-point
round-trip parsing is enabled to retain threshold decisions.

Both feature-to-prediction and full raw-history-to-prediction comparisons ran on all
**672 real cached players**. Points and minutes matched Python exactly; probability
max errors were at floating-point rounding scale (below 1e-8). This is numerical parity
with the existing model, **not a new accuracy claim**. The original chronological test
report and its limitations remain included.

Training stays in the existing Python scientific stack and runs only when requested.
Use **SETUP_LOCAL_TRAINING.bat** once if you want it, then choose **Local ML → Retrain
local models**. That background job includes completed current-season histories,
trains/evaluates versioned models, exports the fitted trees and reloads Rust predictions.
Other pages remain available. Historical downloads and full current-player-history
updates are separate actions. No GPU acceleration has been verified; the native training
button requests CPU.

The native training action compares LightGBM, Random Forest and historical/recent-form
baselines, which the portable exporter supports. The original Python CLI still supports
XGBoost alternatives; XGBoost artifact export is not supported by portable schema 1.
Unknown model types fail explicitly rather than silently producing different predictions.

PowerShell commands for optional local training and re-export:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "."
.\.venv\Scripts\python.exe -m fpl_ai.ml.native_job train
# Or export an existing trusted fitted artifact:
.\.venv\Scripts\python.exe -m fpl_ai.ml.export_rust
```

Native refresh honors inherited proxy variables and an explicitly configured PEM CA
bundle from `FPL_CA_BUNDLE` or `SSL_CERT_FILE`. TLS verification remains enabled. Standard
public certificate roots are used when no bundle is configured. Network failures preserve
cached data and appear in the task log. No background paid service is introduced.

## Optimization behavior

New squads use 15 players, £100m, 2 GKs / 5 DEFs / 5 MIDs / 3 FWDs, max 3 per club and
legal starting formations. Existing squads need confirmed selling prices and finances
for transfer plans; fixed-squad lineups do not require those private details.

The native MILP has a 10-second solve budget and a feasible warm start where available.
Safe same-club/same-position dominance reduction reduces its candidate pool. Proven
optimal results are labeled **Proven optimal**. A time-limited feasible incumbent is
labeled **Feasible · time limit**, with the actual elapsed time; it is never represented
as an optimal result. Constraints are not relaxed if a plan is infeasible.

Chip instances must be confirmed unused and valid in the current gameweek. Free Hit
reverts to the original squad and bank after its first week; Triple Captain and Bench
Boost apply only to the first week. Transfers are immediate; the squad is held across
the horizon except Free Hit reversion. No future transfer/chip scheduling or expected
autosub optimization is claimed. Unreviewed season rules fail closed for optimization,
while read-only pages remain usable.

The original Streamlit app remains available through **RUN_LEGACY_STREAMLIT.bat**,
including advanced event simulations and season beam planning. It is a separate optional
research interface, not part of the native navigation path. Python model training, old
CLI commands and existing datasets have not been removed.

## Build from source

Install Rust stable. Windows native source builds also need Microsoft C++ Build Tools
for bundled SQLite and cryptographic C code. The included executable avoids that setup.

```powershell
cargo build --manifest-path rust\Cargo.toml --release --locked
cargo test --manifest-path rust\Cargo.toml --locked
cargo clippy --manifest-path rust\Cargo.toml --locked --all-targets -- -D warnings
cargo fmt --manifest-path rust\Cargo.toml --check
```

`BUILD_RUST.bat` builds and copies the executable into `bin/`. On Linux, run from the
project root with `cargo run --release --manifest-path rust/Cargo.toml --locked`.
Use `FPL_PROJECT_DIR` to select another project root, and
`FPL_PORT` for another localhost port. The launcher honors `FPL_PORT` too.

The legacy `FPL_DATA_DIR` override belongs to the Python app; the native edition expects
`data/` and `models/` under its project root. Data/database files are not overwritten by
startup. Refresh appends public snapshots. Model retraining writes new versioned artifacts
and replaces only the generated native export atomically.

## Verification and limits

- 114 Python tests passed, including portable model export/inference checks.
- 19 Rust tests passed, including leakage cutoff, tree traversal, squad/XI constraints,
  transfer prices/hits, season guard and Free Hit reversion.
- Rust formatter and Clippy (warnings denied), Python Ruff and compilation passed.
- Headless Chromium: all 10 native routes, desktop and 390px mobile layouts, no body
  overflow, squad building, 11 starters + 4 bench, draft use, player search/dialog,
  financial confirmation and transfer recommendation flows passed with no JS errors.
- Measured on Linux: cold Overview 0.809s (including the test runner's network-idle wait);
  route switches about 16–44ms; cached `/api/state` median 1.45ms, p95 2.46ms.
  These are not Windows timing guarantees. First model/history load takes roughly
  0.5–1 second here; full history downloads and retraining remain explicit longer tasks.

See `reports/rust-*.json`, `reports/rust-ui/browser-results.json`, screenshots and
`docs/RUST_VERIFICATION.md` for evidence. The existing model's held-out MAE of 0.9618
points and 12.9714 minutes covers all player-fixture rows, including non-appearances.
Current model limitations remain: no trained opponent/home/FDR/injury-recovery effects,
retrospectively corrected historical stats, approximate availability cutoffs and
historical blank-week omissions. Future accuracy and native Windows execution remain
unverified. No commits or pushes were made.
