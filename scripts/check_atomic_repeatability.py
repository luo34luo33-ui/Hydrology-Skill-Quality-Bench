"""Regenerate each task twice in isolated directories and compare semantics.

Run locations, location-derived evidence IDs, provenance and resulting hashes
are canonicalized. Raster/vector inputs and plotted pixels are still compared.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

import numpy as np
import pandas as pd
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.grader import _contract_stable
from atomic_tasks import build, DEFAULT_SKILLS, GROUPS, REPO
from atomic_fixture_support import read, write

def canonical(value):
    value=_contract_stable(value)
    if isinstance(value,dict): return {k:canonical(v) for k,v in value.items()}
    if isinstance(value,list): return [canonical(v) for v in value]
    if isinstance(value,str):
        value=re.sub(r'[A-Za-z]:[\\/][^\s"\n]+',lambda match:Path(match.group()).name,value)
        return re.sub(r'[0-9a-f]{64}','<content-hash>',value)
    return value

def snapshot(folder):
    result={}
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or path.name=='generate_data.py': continue
        key=path.relative_to(folder).as_posix()
        if path.suffix=='.json': result[key]=canonical(read(path))
        elif path.suffix=='.csv':
            frame=pd.read_csv(path).fillna('<missing>');result[key]=canonical(frame.to_dict('records'))
        elif path.suffix=='.png':
            with Image.open(path) as image:
                result[key]=dict(size=list(image.size),pixels=hashlib.sha256(np.asarray(image.convert('RGB')).tobytes()).hexdigest())
        elif path.suffix=='.svg':
            import xml.etree.ElementTree as ET
            root=ET.parse(path).getroot()
            result[key]=[(element.tag,{k:v for k,v in element.attrib.items() if k in ('d','x','y','width','height','viewBox','transform')}) for element in root.iter()]
        elif path.suffix in ('.md','.txt'):
            text=path.read_text(encoding='utf-8-sig')
            text=text.replace(str(folder.resolve()),'<task-root>')
            result[key]=canonical(text)
        else: result[key]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skills-root',type=Path,default=DEFAULT_SKILLS);parser.add_argument('--task-id');args=parser.parse_args()
    ids=[args.task_id] if args.task_id else [f'{group}-{n:03}' for group,(_,_,count) in GROUPS.items() for n in range(1,count+1)]
    records=[]
    with tempfile.TemporaryDirectory(prefix='hsqb-repeat-') as temp:
        root=Path(temp)
        for task_id in ids:
            a=root/'a'/task_id;b=root/'b'/task_id
            build(task_id,args.skills_root,a);build(task_id,args.skills_root,b)
            left,right=snapshot(a),snapshot(b)
            differences=[key for key in sorted(set(left)|set(right)) if left.get(key)!=right.get(key)]
            if differences: raise AssertionError(f'{task_id}: semantic drift: {differences}')
            records.append(dict(task_id=task_id,files=len(left),status='pass'))
            print(task_id,'repeatability passed',flush=True)
    write(REPO/'docs/atomic-repeatability.json',dict(method='Two independent task-generation directories; canonicalized run-location metadata and content hashes, exact pixel/scientific comparisons.',tasks=records))
    return 0

if __name__=='__main__': raise SystemExit(main())
