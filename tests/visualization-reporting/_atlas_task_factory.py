"""Shared fixed-atlas task factory."""
from pathlib import Path
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from atomic_tasks import build, DEFAULT_SKILLS

def generate(task_id):
    if not task_id.startswith('hydrovisual-'): raise ValueError(task_id)
    return build(task_id,Path(os.environ.get('HYDROTUNE_SKILLS_ROOT',str(DEFAULT_SKILLS)).strip().strip('"')))
