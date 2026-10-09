"""Deterministic development helpers; never launches a model or CLI agent."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILLS = Path(os.environ.get('HYDROTUNE_SKILLS_ROOT', r'E:\HydroTune-Skills（仿BioSkills版）'))
LUMPED = Path(os.environ.get('HSQB_LUMPED_INPUT', r'E:\Skills-测试\opencode-skill-test-lumped\input'))
SEMI = Path(os.environ.get('HSQB_SEMI_INPUT', r'E:\Skills-测试\opencode-skill-test-semixaj\input'))
PUBLIC = ROOT / 'runtime' / 'public'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()

def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')

def portable_tree(root, old_root=None):
    """Rebase real manifest references and refresh hashes in dependency order."""
    def resolved(path):
        value=os.path.normcase(str(Path(path).resolve()))
        if value.startswith('\\\\?\\UNC\\'):value='\\\\'+value[8:]
        elif value.startswith('\\\\?\\'):value=value[4:]
        return Path(value)
    root=resolved(root);old=resolved(old_root or root);active=set();done=set()
    def visit(path):
        if path in done:return
        # The upfront inventory is immutable input evidence, not an output
        # manifest. In particular, keep public document filename case intact.
        if path.name=='input_inventory.json':done.add(path);return
        if path in active:raise ValueError('manifest reference cycle')
        active.add(path)
        try:doc=json.loads(path.read_text(encoding='utf-8'))
        except (ValueError,UnicodeError):active.remove(path);done.add(path);return
        def walk(value):
            if isinstance(value,dict):
                if isinstance(value.get('path'),str) and 'sha256' in value:
                    original=Path(value['path'])
                    candidate=original if original.is_absolute() else path.parent/original
                    if original.is_absolute():
                        try:candidate=root/original.relative_to(old)
                        except ValueError:return
                    candidate=resolved(candidate)
                    try:candidate.relative_to(root)
                    except ValueError:return
                    if candidate.is_file():
                        if candidate.suffix=='.json':visit(candidate)
                        value['path']=os.path.relpath(candidate,path.parent).replace('\\','/')
                        value['sha256']=sha(candidate)
                for v in value.values():walk(v)
            elif isinstance(value,list):
                for v in value:walk(v)
        walk(doc);write_json(path,doc);active.remove(path);done.add(path)
    for path in sorted(root.rglob('*.json')):visit(path)

def native(workspace, ref, arguments, expected=(0,), timeout=600):
    folder = PUBLIC / 'programs' / ref
    index = json.loads((PUBLIC / 'programs.json').read_text(encoding='utf-8'))
    command = [sys.executable, str(PUBLIC / 'native_bootstrap.py'), str(folder / index[ref]['entrypoint']), *map(str, arguments)]
    p = subprocess.run(command, cwd=workspace, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    if p.returncode not in expected:
        raise RuntimeError(f'{ref}: exit={p.returncode}\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}')
    return {'program': ref, 'arguments': list(map(str, arguments)), 'exit_code': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}

