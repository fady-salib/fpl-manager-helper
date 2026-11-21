"""Fast Windows/CPU installation check; no network requests or training."""

from importlib.metadata import version

from fpl_ai.ml.registry import load_any, model_path
from fpl_ai.storage import SnapshotStore


def main():
    path = model_path()
    if path is None:
        raise SystemExit("No model found. Extract the complete repaired ZIP, including models/.")
    artifact = load_any(path)
    metadata = artifact.get("metadata", {})
    print("Model:", path)
    print("Trained:", metadata.get("trained_at", "legacy model"))
    print("scikit-learn:", version("scikit-learn"))
    store = SnapshotStore()
    for endpoint in ("bootstrap-static/", "fixtures/"):
        snapshot = store.latest(endpoint)
        print(endpoint, "cached at " + snapshot[0].isoformat() if snapshot else "not cached")
    from pulp import PULP_CBC_CMD

    if not PULP_CBC_CMD(msg=False).available():
        raise SystemExit("CBC solver missing. Reinstall PuLP in the project virtual environment.")
    print("CBC solver: available")
    print("Ready. Run: python -m streamlit run app/main.py")


if __name__ == "__main__":
    main()
