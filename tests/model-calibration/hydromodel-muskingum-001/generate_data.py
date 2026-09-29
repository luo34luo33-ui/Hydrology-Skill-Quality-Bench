"""Generate hydromodel-muskingum-001."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _muskingum_task_factory import generate_task


if __name__ == "__main__":
    generate_task("hydromodel-muskingum-001")
