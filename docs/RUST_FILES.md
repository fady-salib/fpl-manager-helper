# Exact Rust release changes

Compared with the previously delivered `fpl-ai-manager-fixed-trained.zip`.

## Modified

- `.dockerignore`
- `.github/workflows/ci.yml`
- `.gitignore`
- `README.md`
- `RUN_FPL_MANAGER.bat`
- `data/fpl.sqlite`

## Created

- `BUILD_RUST.bat`
- `README_RUST.md`
- `RUN_LEGACY_STREAMLIT.bat`
- `SETUP_LOCAL_TRAINING.bat`
- `bin/fpl-manager-linux`
- `bin/fpl-manager.exe`
- `docs/RUST_BUNDLED_DATA.json`
- `docs/RUST_FILES.md`
- `docs/RUST_VERIFICATION.md`
- `models/native-model.json`
- `reports/rust-api-performance.json`
- `reports/rust-clippy.txt`
- `reports/rust-full-pipeline-parity.json`
- `reports/rust-prediction-parity.json`
- `reports/rust-python-tests.txt`
- `reports/rust-refresh-smoke.json`
- `reports/rust-release-binaries.json`
- `reports/rust-team-ui-smoke.json`
- `reports/rust-tests.txt`
- `reports/rust-ui/browser-results.json`
- `reports/rust-ui/desktop-overview.png`
- `reports/rust-ui/desktop-pitch.png`
- `reports/rust-ui/mobile-overview.png`
- `reports/rust-ui/mobile-pitch.png`
- `reports/windows-dll-imports.txt`
- `rust/Cargo.lock`
- `rust/Cargo.toml`
- `rust/src/data.rs`
- `rust/src/main.rs`
- `rust/src/model.rs`
- `rust/src/optimize.rs`
- `rust/web/app.css`
- `rust/web/app.js`
- `rust/web/index.html`
- `scripts/test_rust_ui.py`
- `scripts/verify_rust_predictions.py`
- `src/fpl_ai/ml/export_rust.py`
- `src/fpl_ai/ml/native_job.py`
- `tests/test_rust_export.py`

The previous Python app, trained artifact, datasets and interfaces are preserved. Native public refresh appended snapshots; no user records were overwritten. Build directories, virtual environments, compiler toolchains and caches are excluded.
