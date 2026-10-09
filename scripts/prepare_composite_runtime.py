"""Freeze complete source contracts and publish identical scientific programs."""
from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path
import shutil
import sys
from composite_common import ROOT, SKILLS, PUBLIC, sha, write_json

def main():
    p = argparse.ArgumentParser(); p.add_argument('--skills-root', type=Path, default=SKILLS); args = p.parse_args()
    records = []; programs = {}; sources = ROOT / 'docs/composite-contracts'
    for skill in sorted(args.skills_root.glob('*/*/SKILL.md')):
        ref = skill.parent.relative_to(args.skills_root).as_posix()
        files = []
        for src in sorted(skill.parent.rglob('*')):
            if not src.is_file() or '__pycache__' in src.parts: continue
            if src.suffix not in {'.py', '.md', '.json', '.yaml', '.yml'}: continue
            content = src.read_bytes()
            dst = sources / ref / src.relative_to(skill.parent); dst.parent.mkdir(parents=True, exist_ok=True); dst.write_bytes(content)
            files.append({'path': src.relative_to(args.skills_root).as_posix(), 'sha256': sha(src)})
        records.append({'reference': ref, 'kind': 'workflow' if ref.startswith('workflows/') else 'atomic', 'files': files})
        frozen=ROOT/'runtime/skills'/ref.replace('/','-')
        shutil.copytree(sources/ref,frozen,dirs_exist_ok=True)
        examples = skill.parent / 'examples'
        assets=skill.parent/'assets'
        if assets.is_dir():shutil.copytree(assets,PUBLIC/'programs'/skill.parent.parent.name/'assets',dirs_exist_ok=True)
        entries = []
        if examples.is_dir():
            for src in sorted(examples.rglob('*')):
                if not src.is_file() or '__pycache__' in src.parts or src.suffix not in {'.py','.json','.yaml','.yml'}: continue
                dst = PUBLIC / 'programs' / ref / src.relative_to(examples); dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dst)
                if src.suffix == '.py':
                    tree = ast.parse(src.read_text(encoding='utf-8-sig'))
                    if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'ArgumentParser' for n in ast.walk(tree)) and not src.name.startswith('make_'):
                        entries.append(src.relative_to(examples).as_posix())
            if len(entries) == 1: programs[ref] = {'entrypoint': entries[0], 'sha256': sha(examples/entries[0])}
    PUBLIC.mkdir(parents=True, exist_ok=True)
    shared=args.skills_root/'visualization-reporting/assets'
    if shared.is_dir():shutil.copytree(shared,PUBLIC/'programs/visualization-reporting/assets',dirs_exist_ok=True)
    shutil.copyfile(ROOT/'scripts/atomic_native_bootstrap.py', PUBLIC/'native_bootstrap.py')
    write_json(PUBLIC/'programs.json', programs)
    write_json(ROOT/'docs/composite-skill-catalog.json', {'skills': records, 'atomic': sum(r['kind']=='atomic' for r in records), 'workflows':sum(r['kind']=='workflow' for r in records)})
    print(json.dumps({'skills':len(records), 'programs':len(programs)}, ensure_ascii=False))

if __name__ == '__main__': main()
