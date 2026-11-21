"""One model discovery path for every app page and command."""

from pathlib import Path


def model_path(root="models"):
    root = Path(root)
    paths = sorted(root.glob("local-*.joblib"), reverse=True)
    if paths:
        return paths[0]
    legacy = root / "ensemble.joblib"
    return legacy if legacy.exists() else None


def load_any(path):
    import joblib

    from .training import load

    if Path(path).name.startswith("local-"):
        return load(path)
    artifact = joblib.load(path)
    if "models" not in artifact:
        raise ValueError("Unsupported model artifact")
    return artifact
