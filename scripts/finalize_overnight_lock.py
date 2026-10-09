"""Certify only from completed live smoke and budget evidence, never unchecked flags."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from harness.cli_events import EventCounter
from harness.runner import _sha256_tree

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--smoke',required=True);p.add_argument('--budget',required=True);p.add_argument('--lock',default='runtime/experiment.unattended-v2.lock.json');a=p.parse_args()
    smoke_path=Path(a.smoke).resolve();budget_path=Path(a.budget).resolve()
    smoke=json.loads(smoke_path.read_text(encoding='utf-8'));budget=json.loads(budget_path.read_text(encoding='utf-8'))
    if not smoke['passed'] or not budget['passed']:raise ValueError('Live certification did not pass')
    if smoke.get('task_version')!='composite-unattended-v2' or smoke.get('interaction_mode')!='none':raise ValueError('Old confirmation certificates cannot certify unattended execution')
    if budget.get('task_version')!='composite-unattended-v2' or budget.get('interaction_mode')!='none':raise ValueError('Old budget certificates cannot certify unattended execution')
    certified_clis=smoke.get('certified_clis',[])
    if not certified_clis or set(certified_clis)!=set(budget.get('certified_clis',[])):
        raise ValueError('Smoke and budget certification must cover the same explicit CLI set')
    if len(smoke['receipts'])!=2*len(certified_clis) or len(budget['receipts'])!=3*len(certified_clis):raise ValueError('Incomplete certification')
    if any(r.get('cli') not in certified_clis for r in smoke['receipts']+budget['receipts']):raise ValueError('Receipt includes a CLI outside the certified set')
    if 'opencode' in certified_clis and any(r.get('condition')=='with-skills' and not r.get('native_skill_evidence',{}).get('passed') for r in smoke['receipts'] if r.get('cli')=='opencode'):
        raise ValueError('OpenCode native workflow and atomic skill calls are not both verified')
    evidence=[]
    for receipt in smoke['receipts']:
        cli=receipt['cli'];condition=receipt['condition'];base=smoke_path.parent/cli/condition
        counter=EventCounter(cli)
        for line in (base/'stdout.log').read_text(encoding='utf-8').splitlines():counter.feed(line)
        events=[json.loads(line) for line in (base/'host_audit.jsonl').read_text(encoding='utf-8').splitlines()]
        asks=sum(e.get('kind')=='confirmation_request' for e in events)
        if asks or any(e.get('kind','').startswith('confirmation') for e in events):raise ValueError('Unattended certification received supplemental user information')
        if counter.tools+asks!=receipt['execution']['tool_calls']:raise ValueError('CLI count replay mismatch')
        network=receipt['network']
        if not all(network[k] for k in ['confirmation_interface_absent','confirmation_credentials_absent','arbitrary_route_blocked','external_blocked','host_model_blocked','host_confirm_blocked']):raise ValueError('Network isolation failed')
        evidence.append({'cli':cli,'condition':condition,'native_tools':counter.tools,'confirmations':asks,
            'normalized_tools':counter.tools+asks,'stdout_sha256':sha(base/'stdout.log'),'receipt_sha256':sha(base/'receipt.json')})
    lock_path=Path(a.lock);lock=json.loads(lock_path.read_text(encoding='utf-8'))
    lock['isolated_network_certified']=True
    lock['certified_clis']=certified_clis
    for cli in lock['clis']:lock['clis'][cli]['budget_audit_certified']=cli in certified_clis
    lock['certifications']={'smoke':{'path':str(smoke_path),'sha256':sha(smoke_path)},
        'budget':{'path':str(budget_path),'sha256':sha(budget_path)}}
    lock['host_runtime_sha256']=_sha256_tree(ROOT/'harness')
    lock['relay_sha256']=sha(ROOT/'runtime/provider_relay.py')
    lock['status']='live_certified_ready'
    lock_path.write_text(json.dumps(lock,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'docs/overnight-live-certification.json').write_text(json.dumps({
        'passed':True,'independent_science_tasks_used':False,'evidence':evidence,
        'smoke':lock['certifications']['smoke'],'budget':lock['certifications']['budget'],
        'image_digest':lock['image_digest'],'cli_models':{cli:{k:c[k] for k in ['version','model','effort']} for cli,c in lock['clis'].items()}},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Live smoke, network and budget certification frozen.')

if __name__=='__main__':main()
