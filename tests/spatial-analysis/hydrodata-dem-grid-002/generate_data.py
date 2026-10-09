from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _spatial_task_factory import build_task
build_task(Path(__file__).resolve().parent.name)
