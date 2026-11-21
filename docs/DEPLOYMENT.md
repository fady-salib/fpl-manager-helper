# Deployment and reproducibility

Run from the repository root with Python 3.12+. The repaired ZIP includes a CPU-trained
model, its chronological evaluation, historical CSVs and public current-season snapshots.
`RUN_FPL_MANAGER.bat` performs dependency setup only when needed, then launches the app
without a blocking API preflight. Navigation uses saved snapshots; refresh explicitly
when prices, injuries or fixtures need updating. Public timestamps and stale warnings
remain visible.

`requirements-lock.txt` pins the tested direct dependencies for Python 3.12; pip resolves
transitive dependencies. It contains no Linux-only NVIDIA package. Install with
`pip install -r requirements-lock.txt`, then `pip install -e . --no-deps`, or use the
project's compatible ranges with `pip install -e .`. The bundled artifact uses
scikit-learn 1.8.x and LightGBM 4.7.0. The project pins the scikit-learn series for model
compatibility. Native Windows execution has not been tested here.

The core install includes LightGBM. Optional `.[ml]` adds XGBoost and Optuna comparison
tools. The new pipeline uses seed 42 and two CPU workers. For retraining run
`python -m fpl_ai.ml train --cpu`; `evaluate` prints the saved held-out report.
Legacy `fpl-ai train` remains available for the older experiment.

Docker requires persistent data/models/reports directories if training artifacts should
survive replacement. The application does not read `.env` automatically: export
`FPL_DATA_DIR` in your shell or use Docker `--env`. The Streamlit app expects to run from
the project root, where `models/` and `reports/` are located.

A corporate TLS proxy may require a CA bundle. The Dockerfile supports optional
BuildKit `--secret id=proxy_ca,src=/path/to/combined-ca-bundle.pem`; certificates are
mounted only during networked steps, not baked into layers. Keep certificate
verification enabled. Runtime deployments behind a proxy must also supply an
appropriate read-only CA bundle and `SSL_CERT_FILE` if required.

Suggested local automation:

- Hourly: `fpl-ai refresh`.
- Daily and before a deadline: `fpl-ai refresh --histories`.
- Before each deadline: collect immutable bootstrap, fixture and history snapshots;
  check timestamps before ranking. Run `fpl-ai collect --event GW` after results are
  finalized to retain outcome data for later testing.
- Retrain only when new finalized events exist; archive metric reports and seed.
- Back up SQLite with SQLite's backup API or while stopped; copying a live DB without
  its WAL may lose snapshots. Store personal team JSON outside the repository.

No public hosting, GitHub publication or account transfer has been performed.
Runtime service must be protected by authentication for multiuser deployment;
Streamlit session state is not a complete production account or authorization system.
