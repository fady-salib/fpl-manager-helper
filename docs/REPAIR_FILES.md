# Exact changes in the 2026-11-18 repair

Compared with the previously delivered `fpl-ai-manager-local-ml.zip`.

## Modified

- `README.md`
- `RUN_FPL_MANAGER.bat`
- `app/components/local_ml.py`
- `app/components/new_team_builder.py`
- `app/main.py`
- `docs/DEPLOYMENT.md`
- `docs/LOCAL_ML_FILES.md`
- `docs/LOCAL_ML_VERIFICATION.md`
- `docs/NEW_TEAM_BUILDER.md`
- `docs/local-ml-test-results.txt`
- `pyproject.toml`
- `requirements-lock.txt`
- `src/fpl_ai/api/client.py`
- `src/fpl_ai/features/history.py`
- `src/fpl_ai/forecasting/rankings.py`
- `src/fpl_ai/forecasting/team_builder.py`
- `src/fpl_ai/ml/__main__.py`
- `src/fpl_ai/ml/data.py`
- `src/fpl_ai/ml/prediction.py`
- `src/fpl_ai/ml/training.py`
- `src/fpl_ai/storage.py`
- `tests/test_local_ml.py`

## Created and bundled

- `app/components/model_performance.py`
- `app/components/runtime.py`
- `app/components/team_setup.py`
- `data/fpl.sqlite`
- `data/history-2023-24.csv`
- `data/history-2024-25.csv`
- `docs/BUNDLED_DATA.json`
- `docs/REPAIR_FILES.md`
- `models/local-20261118T001337021377Z.joblib`
- `reports/live-builder-smoke.json`
- `reports/live-page-smoke.json`
- `reports/local-20261118T001337021377Z.json`
- `reports/local-20261118T001337021377Z.log`
- `reports/performance-repair.json`
- `reports/runtime-versions.json`
- `scripts/verify_local_install.py`
- `src/fpl_ai/ml/registry.py`
- `tests/test_app_repairs.py`

No original source files were removed. Public training CSVs, trained models and public snapshot data are included intentionally. Virtual environments, caches and user account data are excluded.
