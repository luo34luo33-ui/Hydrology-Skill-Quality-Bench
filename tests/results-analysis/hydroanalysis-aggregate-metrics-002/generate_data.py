"""Generate hydroanalysis-aggregate-metrics-002."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _diagnostics_task_factory import generate_task


if __name__ == "__main__":
    generate_task("hydroanalysis-aggregate-metrics-002")
