"""Build hidden contracts from native artifacts, with independent science checks."""
from pathlib import Path
import xml.etree.ElementTree as ET
import json
import shutil
import re

from PIL import Image
import pandas as pd

from atomic_fixture_support import read, write

def stable(value):
    if isinstance(value, dict):
        return {k:stable(v) for k,v in value.items() if k not in {'provenance','sha256','package_fingerprint','author','reviewer','rationale','text','message'} and not k.endswith('_path') and k not in {'path','result_path','result','source_results','sources'}}
    if isinstance(value,list): return [stable(v) for v in value]
    if isinstance(value,str):
        if Path(value).is_absolute(): return Path(value).name
        return re.sub(r'ev-[0-9a-f]{20}', 'ev-location-id', value)
    return value

def make_grading(group,ws,outputs,task_dir):
    golden=task_dir/'expected/golden_workspace'
    required=[p.relative_to(golden).as_posix() for p in sorted(golden.rglob('*')) if p.is_file()]
    grading=[dict(name='required_native_outputs',type='file_check',targets=required,weight=0)]
    refs={};figure_refs=[]
    for folder in outputs:
        result=ws/folder/'result.json'
        if result.exists():
            doc=read(result)
            refs[f'{folder}/result.json']={k:stable(doc[k]) for k in ('status','skill','warnings') if k in doc}
            if doc.get('status')=='error' and doc.get('message'):
                refs[f'{folder}/result.json']['error_reason_contains']=re.split(r'[A-Z]:[\\/]',doc['message'])[0].strip()
            grading.append(dict(name=folder+'_artifact_integrity',type='artifact_reference_check',target=f'{folder}/result.json',required_keys=sorted(doc.get('artifacts',{})),weight=0))
        for path in sorted((ws/folder).glob('*.json')):
            doc=read(path)
            if path.name in ('report.json','review.json','analysis-tables.json','alignment_qc.json','model_card.json','fit_diagnostics.json','bma_model.json'):
                if path.name=='report.json':
                    selected={k:stable(doc[k]) for k in ('schema_version','report_type','evidence','analysis','gaps','warnings') if k in doc}
                    # Compare machine sections excluding Agent-authored paragraph prose.
                    selected['sections']=[{k:stable(v) for k,v in s.items() if k!='paragraphs'} for s in doc.get('sections',[])]
                    selected['narrative_required']=group=='hydroreport-study' and (ws/folder/'report.md').exists()
                    refs[path.relative_to(ws).as_posix()]=selected
                elif path.name=='review.json':
                    refs[path.relative_to(ws).as_posix()]={k:stable(doc[k]) for k in ('status','summary','findings') if k in doc}
                elif path.name in ('bma_model.json','fit_diagnostics.json'):
                    # Fit identity and nonconvergence are checked without requiring
                    # one unique optimizer solution for duplicate members.
                    refs[path.relative_to(ws).as_posix()]={k:stable(doc[k]) for k in ('schema_version','distribution','estimator','series_mode','outlet_id','model_ids','timestep_hours','timezone','unit','training_start','training_end','training_events','random_state','converged') if k in doc}
                elif group=='hydroanalysis-bma' and path.name=='model_card.json':
                    refs[path.relative_to(ws).as_posix()]={k:stable(v) for k,v in doc.items() if k not in ('model','inputs')}
                else: refs[path.relative_to(ws).as_posix()]=stable(doc)
            png=path.with_suffix('.png')
            if path.name.endswith('.figure.json'): png=path.with_name(path.name.replace('.figure.json','.png'))
            if png.exists() and path.with_name(png.stem+'.svg').exists():
                with Image.open(png) as img: size=list(img.size)
                figure_refs.append(dict(metadata=path.relative_to(ws).as_posix(),png=png.relative_to(ws).as_posix(),svg=path.with_name(png.stem+'.svg').relative_to(ws).as_posix(),size=size,metadata_contract=stable(doc)))
                svg_path=path.with_name(png.stem+'.svg')
                root=ET.parse(svg_path).getroot()
                elements=[e for e in root.iter() if e.tag.rsplit('}',1)[-1] in {'path','image','polyline','polygon','circle','rect'}]
                figure_refs[-1]['minimum_graphics']=max(10,int(len(elements)*.8))
                # Scientific line and collection geometry is independent of SVG
                # IDs and font encodings; blank/replaced layers cannot pass.
                geometry=[]
                for element in root.iter():
                    if element.tag.endswith('g') and element.get('id','').startswith(('line2d_','LineCollection_','PathCollection_','patch_')):
                        paths=[e.get('d') for e in element.iter() if e.tag.endswith('path') and e.get('d')]
                        if paths: geometry.extend(paths)
                figure_refs[-1]['geometry']=geometry
        for path in sorted((ws/folder).glob('*.csv')):
            frame=pd.read_csv(path)
            if frame.empty: continue
            # Reviewer free-form recommendation/rationale text isn't an oracle.
            columns=[c for c in frame if c not in ('rationale','recommendation','message','details','report_location','evidence_location','source_result','artifact','sha256','id','referenced_by') and not c.endswith('_path')]
            if group=='hydroanalysis-bma' and path.name=='component_predictions.csv': continue
            if columns:
                grading.append(dict(name=folder+'_'+path.stem,type='table_match',target=path.relative_to(ws).as_posix(),reference='expected/golden_workspace/'+path.relative_to(ws).as_posix(),columns=columns,atol=1e-5,rtol=1e-5,weight=0))
    contract=dict(kind='bma' if group=='hydroanalysis-bma' else 'report',files=refs)
    if group=='hydroreport-study' and (ws/'conclusions.json').exists() and (ws/'report/report.md').exists():
        contract['files']['conclusions.json']=read(ws/'conclusions.json')
    markdown={}
    for folder in outputs:
        path=ws/folder/'report.md'
        if path.exists(): markdown[path.relative_to(ws).as_posix()]=[line for line in path.read_text(encoding='utf-8').splitlines() if line.startswith(('#','|','!['))]
    contract['markdown']=markdown
    if (ws/'semantic.json').exists():
        contract['semantic_verdicts']={p['id']:p['verdict'] for p in read(ws/'semantic.json')['paragraphs']}
    if group.startswith('hydroreport') or group=='hydroanalysis-bma':
        write(task_dir/'expected/report-contract.json',contract)
        grading.append(dict(name='evidence_and_scientific_contract',type='report_contract_check',target=outputs[-1]+'/result.json',reference='expected/report-contract.json',weight=0))
    if figure_refs:
        write(task_dir/'expected/figure-contract.json',dict(figures=figure_refs))
        grading.append(dict(name='rendered_figure_contract',type='figure_contract_check',target=outputs[-1]+'/result.json',reference='expected/figure-contract.json',weight=0))
    # Always grade status, including failures with no figures/report content.
    write(task_dir/'expected/status-contract.json',dict(kind='status',files={k:v for k,v in refs.items() if k.endswith('/result.json')}))
    grading.append(dict(name='native_status_contract',type='report_contract_check',target=outputs[-1]+'/result.json',reference='expected/status-contract.json',weight=0))
    forbidden=[]
    for folder in outputs:
        doc=read(ws/folder/'result.json')
        if doc.get('status')=='error':
            candidates= ['bma_model.json','ensemble_discharge.csv','component_predictions.csv'] if group=='hydroanalysis-bma' else (['report.md','report.json','summary.csv'] if group.startswith('hydroreport') else [])
            forbidden += [f'{folder}/{name}' for name in candidates if not (ws/folder/name).exists()]
            if group.startswith('hydrovisual'):
                # Discover forbidden PNG/SVGs from normal native fixtures after
                # errors; dashboard-only scientific failures handled separately.
                normal=task_dir.parent/(group+'-001')/'expected/golden_workspace/atlas'
                if normal.exists(): forbidden += ['atlas/'+p.name for p in normal.iterdir() if p.suffix in ('.png','.svg') and not (ws/'atlas'/p.name).exists()]
    if forbidden: grading.append(dict(name='prohibited_deliverables_absent',type='file_absence_check',targets=forbidden,weight=0))
    for item in grading: item['weight']=1/len(grading)
    grading[-1]['weight']=1-sum(item['weight'] for item in grading[:-1])
    return required,grading
