"""Prepare 24 revision-5 tasks without reference computation or model execution."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from harness.filesystem import copy_tree,filesystem_path,normal_path
from harness.reporter import write_json
from harness.source_references import SCORING_VERSION

REVISION=5
PATH_GUIDE='References may be relative to the declaring manifest, or use /work/ for the task workspace. /public/ references must name frozen public files. Unknown absolute paths, parent traversal, cross-task references and incorrect SHA-256 are rejected. decision.json references are relative to the workspace root.'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare_task(source,destination,public):
    if destination.exists():raise ValueError('Revision destination exists; never overwrite old tasks')
    copy_tree(source,destination)
    task=json.loads((destination/'task.json').read_text(encoding='utf-8'))
    spec=json.loads((destination/'expected/evaluation.json').read_text(encoding='utf-8'))
    data=destination/'data'
    task.update(task_revision=REVISION,scoring_version=SCORING_VERSION,validation_status='pending_validation',dataset_split='development')
    task['measured_workflow_capabilities']=task['core_capabilities']
    task['prompt']+=' '+PATH_GUIDE+' 阅读 workflow_requirements.json；按照同一科学约束核查时间轴、组织模式和上下游证据，记录实现选择。'
    derivation=json.loads((data/'derivation.json').read_text(encoding='utf-8'))
    derivation['flow_semantics']='Benchmark flow semantics, units and permissions are supplied upfront in scenario.json; original observations are preserved and no further confirmation is required.'
    write_json(data/'derivation.json',derivation)
    scenario=json.loads((data/'scenario.json').read_text(encoding='utf-8'))
    scenario.update(task_revision=REVISION,scoring_version=SCORING_VERSION)
    write_json(data/'scenario.json',scenario)
    guide=data/'OUTPUT_INTERFACES.md';guide.write_text(guide.read_text(encoding='utf-8')+'\n\n## 来源引用\n\n'+PATH_GUIDE+'\n',encoding='utf-8')
    interfaces=json.loads((data/'output_interfaces.json').read_text(encoding='utf-8'))
    interfaces.update(task_revision=REVISION,scoring_version=SCORING_VERSION,source_reference_policy=PATH_GUIDE)
    for entry in interfaces['outputs'].values():
        if 'metadata_policy' in entry:entry['metadata_policy']=entry['metadata_policy'].replace('References must be relative and SHA-256 valid.',PATH_GUIDE)
    interfaces['result_manifest']=PATH_GUIDE+' Optional implementation-only config and adapter references may be omitted; scientific evidence remains mandatory.'
    write_json(data/'output_interfaces.json',interfaces)
    requirements={'task_revision':REVISION,'measured_capabilities':task['core_capabilities'],
        'state':'Use scenario.json organization mode and initial states; independent events reset state, continuous runs retain state.',
        'warmup':'Preserve model warm-up execution, exclude declared warm-up samples from scoring, and disclose the actual scored sample set.',
        'aggregation':'Use the supplied timestep, units, forcing selection and spatial representativeness; rainfall/evaporation depths sum and discharge follows the declared aggregation.',
        'external_inflow':'Where supplied, distinguish incremental local inflow and external contributions; inject and route each external contribution exactly once.',
        'stability':'Where routing is used, use the supplied routing parameters and actual integration step; do not silently change them.',
        'independence':'Where calibration or comparisons are used, respect the supplied train/validation split and independently recompute scored metrics.',
        'applicability':'Apply each requirement only to capabilities and processes requested in this task; no extra model or scientific decision is required.',
        'axis_checks':[]}
    for rel,entry in interfaces['outputs'].items():
        columns=entry.get('columns',[])
        time=next((c for c in ['time','Time','timestamp'] if c in columns),None)
        if not time:continue
        groups=[c for c in ['event_id','unit_id','reach_id','station_id','source_id','model_id'] if c in columns]
        check={'type':'scientific_invariant','check':'scientific_axis_integrity','target':rel,'time_column':time,'group_columns':groups}
        spec['gates'].append({'id':'axis:'+rel,'criteria':[check],'evidence':[rel]})
        requirements['axis_checks'].append({'path':rel,'time_column':time,'group_columns':groups,'requirements':['explicit timezone','unique time within declared group','chronological order']})
    write_json(data/'workflow_requirements.json',requirements)
    (data/'INPUT_GUIDE.md').write_text((data/'INPUT_GUIDE.md').read_text(encoding='utf-8')+'\n\nworkflow_requirements.json 列明本题工作流能力和跨步骤一致性要求，不包含参考答案。\n',encoding='utf-8')
    inventory=json.loads((data/'input_inventory.json').read_text(encoding='utf-8'))
    known={r['path']:r for r in inventory['files']}
    for path in data.rglob('*'):
        if path.is_file() and path.name!='input_inventory.json':
            rel=path.relative_to(data).as_posix()
            known.setdefault(rel,{'path':rel,'role':'public workflow consistency requirements'})['sha256']=digest(path)
    inventory.update(task_revision=REVISION);inventory['files']=list(known.values())
    write_json(data/'input_inventory.json',inventory)
    task['data_files']=sorted(p.relative_to(data).as_posix() for p in data.rglob('*') if p.is_file())
    protected={rel:digest(data/rel) for rel in task['data_files']}
    write_json(destination/'expected/protected_sources.json',protected)
    write_json(destination/'expected/public_sources.json',public)
    spec.update(task_revision=REVISION,scoring_version=SCORING_VERSION,validation_status='pending_reference_recomputation')
    spec.pop('reference_execution',None)
    write_json(destination/'expected/evaluation.json',spec)
    write_json(destination/'expected/reference_status.json',{'status':'inherited_unverified','source_task':str(normal_path(source)),'notice':'Existing numerical reference files are preserved as development fixtures, not a new acceptance run. Recompute before certification.'})
    write_json(destination/'task.json',task)
    family=task['id'].split('-')[1];index=int(task['id'].split('-')[2])
    (destination/'generate_data.py').write_text(
        '# This frozen revision is immutable; regenerate the complete set into a fresh root.\n'
        'raise SystemExit("Use scripts/composite_revision.py with a fresh output root.")\n',encoding='utf-8')
    return {'task':task['id'],'source':str(normal_path(source)),'development':True,'capabilities':task['core_capabilities'],'added_axis_gates':len(requirements['axis_checks']),'reference_status':'pending_recomputation'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',type=Path,default=ROOT/'composite_tests');p.add_argument('--output-root',type=Path,default=ROOT/'composite_tests_v3');a=p.parse_args()
    source=Path(filesystem_path(a.source_root));target=Path(filesystem_path(a.output_root))
    if target.exists():raise ValueError('Use a fresh revision root; old tasks are preserved')
    paths=sorted(source.glob('*/*/task.json'))
    if len(paths)!=24:raise ValueError('Exactly 24 development tasks required')
    root=ROOT/'runtime/public'
    public={'root':str(root),'files':{x.relative_to(root).as_posix():digest(x) for x in root.rglob('*') if x.is_file() and '__pycache__' not in x.parts and x.suffix not in {'.pyc','.pyo'}}}
    rows=[prepare_task(path.parent,target/path.parent.relative_to(source),public) for path in paths]
    write_json(target/'revision_manifest.json',{'task_version':'composite-unattended-v2','task_revision':REVISION,'scoring_version':SCORING_VERSION,'validation_status':'pending_validation','reference_computation_performed':False,'development_tasks':rows,'blind_test':{'status':'not_prepared','reason':'Existing source pool has been exposed during benchmark development. No independent source interval has been certified as unused.','allow_synthetic_observations_as_blind_truth':False}})
    print('Prepared 24 revision-5 tasks; no scientific calculation or tests performed.')

if __name__=='__main__':main()
