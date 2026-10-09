"""Generate hydrodata-eto-faopm-002."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _eto_task_factory import generate_task


if __name__ == "__main__":
    generate_task("hydrodata-eto-faopm-002")
