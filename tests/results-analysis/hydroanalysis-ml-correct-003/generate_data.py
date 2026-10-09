"""Generate hydroanalysis-ml-correct-003."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _mlcorrect_task_factory import generate_task


if __name__ == "__main__":
    generate_task("hydroanalysis-ml-correct-003")
