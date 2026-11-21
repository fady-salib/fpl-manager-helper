"""Explicit background tasks invoked by the Rust server; never run during navigation."""

import sys

from .data import dataset_paths, download, export_current, with_current
from .export_rust import export
from .training import train


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "train"
    seasons = ["2023-24", "2024-25"]
    if action == "download":
        download(seasons, log=lambda s: print(s, flush=True))
    elif action == "train":
        try:
            paths = dataset_paths(seasons)
        except ValueError:
            paths = download(seasons)
        from fpl_ai.storage import SnapshotStore

        store = SnapshotStore()
        snapshot = store.latest("bootstrap-static/")
        if snapshot:
            exported = export_current(store, snapshot[1])
            if exported:
                print(f"Using completed current-season data: {exported}", flush=True)
        path = train(
            with_current(paths),
            names=("lightgbm",),
            use_gpu=False,
            log=lambda s: print(s, flush=True),
        )
        export(path)
    else:
        raise SystemExit("Unsupported local job")


if __name__ == "__main__":
    main()
