"""Capture the read-only source inventory and contracts used by this completion."""
from pathlib import Path
import hashlib
import json
import sys
import yaml
from atomic_tasks import DEFAULT_SKILLS, GROUPS, REPO
from atomic_fixture_support import write

def main():
    root=Path(sys.argv[1]) if len(sys.argv)>1 else DEFAULT_SKILLS
    categories=yaml.safe_load((root/'resources/categories.yaml').read_text(encoding='utf-8'))['categories']
    tasks=[json.loads(p.read_text(encoding='utf-8')) for p in (REPO/'tests').rglob('task.json')]
    catalog=[]
    for category in categories:
        for skill in sorted((root/category['id']).glob('*/SKILL.md')):
            ref=skill.parent.relative_to(root).as_posix()
            files=[]
            for path in sorted(skill.parent.rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix in ('.md','.yaml','.json','.py'):
                    content=path.read_bytes()
                    files.append(dict(path=path.relative_to(root).as_posix(),sha256=hashlib.sha256(content).hexdigest(),bytes=len(content)))
            entry=dict(skill=ref,files=files,task_ids=sorted(t['id'] for t in tasks if t['primary_skill']==ref))
            if ref in {v[0] for v in GROUPS.values()}:
                contract=skill.parent/'data-contract.yaml'
                entry['data_contract']=yaml.safe_load(contract.read_text(encoding='utf-8'))
                entry['skill_document']=skill.read_text(encoding='utf-8')
                entry['usage_guide']=(skill.parent/'usage-guide.md').read_text(encoding='utf-8')
            catalog.append(entry)
    write(REPO/'docs/atomic-skill-catalog.json',dict(source_root=str(root),snapshot_date='2026-10-04',atomic_skills=catalog,excluded=['workflows'],notes=['Source repository is read-only. File hashes include uncommitted source state.', 'Native scripts determine output/status; report review pass is review.status=pass, not generic success.', 'Windows rasterio/expat import-order compatibility is handled by the deterministic launcher.', 'Spatial upstream fixture reuses committed native Whitebox output; scientific grid equivalence is asserted before rebinding the prepared DEM hash.']))
    print(len(catalog),'atomic skills captured')

if __name__=='__main__': main()
