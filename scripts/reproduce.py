"""Run real-data ingestion, models, metrics and optimization from repository root."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = [
    ["refresh", "--histories"],
    ["train"],
    ["evaluate-components"],
    ["rank", "--horizon", "5"],
    ["optimize", "--horizon", "3"],
]
for command in COMMANDS:
    subprocess.run([sys.executable, "-m", "fpl_ai.cli", *command], cwd=ROOT, check=True)
