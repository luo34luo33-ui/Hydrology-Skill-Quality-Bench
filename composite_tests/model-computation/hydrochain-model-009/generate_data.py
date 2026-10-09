from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from composite_tasks import generate
if __name__ == "__main__": generate('model',9,Path(__file__).resolve().parent)
