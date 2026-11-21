# Verification — v0.3.0, 2026-11-19

Checks ran on Linux. The x64 Windows GNU binary was cross-compiled, with only Windows
system DLL imports. It has not been run on native Windows. No real signed-in FPL account
was available: account protocol and browser connection tests use explicitly synthetic identities.

- Rust: **23 tests passed**, including valid squads, selling-price constraints, transfer hits,
  chip reversion, season guard, no future/same-round features, both-name identity matching,
  style-dependent captain choice, unchanged reported points, sparse-history behavior and
  zero-minute suppression of upside bonuses. `cargo clippy --all-targets -- -D warnings` passed.
- Python: see `reports/playing-style-python-tests.txt` and the JUnit XML for the final suite.
  Existing API, preparation, leakage, persistence, predictions, squads and UI coverage is retained.
- Ruff lint/format and Node syntax checks passed on changed Python/JavaScript sources.
- `scripts/test_rust_ui.py`: all ten routes, desktop/mobile overflow, native squad build,
  11 starters/four bench, local draft adoption, search/details, finances and transfer job passed.
  No JavaScript errors. Linux headless cold overview: 0.761 s; route changes: 6.7–31.3 ms.
  These are local measurements, not Windows performance guarantees.
- `scripts/test_team_name_ui.py`: exactly two inputs; no league/ID field; mocked one-time
  verification; both-name checking request; automatic verified-squad loading; native XI;
  style persistence and result invalidation; saved-reference reuse; failed-load state preservation;
  legacy reference/finance migration; desktop/mobile layout. Passed with no JavaScript errors.
- `scripts/test_connection_api.py`: eight local endpoint checks passed, including required names,
  hostile origins, invalid tokens/references and replacement invalidation. No live account request.
- `node scripts/test_browser_connector.cjs`: nine offline protocol checks passed, including
  official-host restriction, strict token parsing, entry-only extraction from synthetic `/api/me/`,
  signed-out/error handling and capture of the pairing fragment before site navigation.
- Raw model parity: all **672 real cached players**, exact points/minutes equality with Python;
  probability differences below 2.3e-16. This uses the existing fitted artifact, not new evaluation.

Risk style is a decision preference based on historical spread, not a retrained points forecast.
No improved accuracy, expected points, winning record, calibrated tail probabilities or GPU speedup
is claimed. Mean-model selection and held-out evaluation results are unchanged.

The helper requires manual installation in Chrome/Edge and the user explicitly clicking Verify.
Live sign-in, the current FPL `/api/me/` contract and browser extension permission prompts still
need confirmation on the user's PC. Name-only global lookup remains unavailable upstream; the UI
does not pretend that an arbitrary account can be discovered from two names alone.
