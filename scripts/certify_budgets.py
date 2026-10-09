"""Small live CLI runs demonstrate host round/tool/time termination."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from harness.confirmation import AuditTrail
from harness.isolated_runtime import relay_session,candidate_argv
from harness.composite_runtime import monitor
from harness import reporter

PROMPT='Deployment budget probe. Read /work/input.txt using a tool, then write output.json containing its value plus one. Perform these as separate tool operations. Do not answer until the file is written.'

def lane(cli,lock,base):
    receipts=[]
    for kind,rounds,tools,timeout in [('round',1,30,45),('tool',10,1,45),('timeout',10,30,1)]:
        out=base/cli/kind;out.mkdir(parents=True,exist_ok=False);workspace=out/'workspace';workspace.mkdir()
        (workspace/'input.txt').write_text('41')
        broker=AuditTrail(out/'host_audit.jsonl')
        with relay_session(lock,cli,broker,out,ROOT,rounds=rounds) as (network,name,gateway):
            argv=candidate_argv(lock,cli,'no-skills',workspace,ROOT/'runtime/public',lock['common_config_dir'],network,name,broker.token,PROMPT)
            def terminate():subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)
            result=monitor(argv,cli,{'agent_rounds':rounds,'tool_calls':tools},timeout,out/'stdout.log',out/'stderr.log',broker.record,terminate,
                decision_count=lambda:gateway.decision_requests,decision_exhausted=lambda:gateway.budget_denied)
            gone=subprocess.run(['docker','inspect',name],capture_output=True).returncode!=0
            passed=gone and result['termination_reason']==('timeout' if kind=='timeout' else 'action_budget')
            if kind=='round':passed=passed and result['agent_rounds']==1 and gateway.budget_denied
            if kind=='tool':passed=passed and result['tool_calls']==1
            receipt={'cli':cli,'kind':kind,'passed':bool(passed),'container_gone':gone,'execution':result}
            reporter.write_json(out/'receipt.json',receipt);receipts.append(receipt)
            print(json.dumps({'cli':cli,'kind':kind,'passed':bool(passed)}),flush=True)
    return receipts

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',default='results/unattended-v2-budget-certification');p.add_argument('--lock',default='runtime/experiment.unattended-v2.lock.json');p.add_argument('--clis',default='codex,opencode,qwen');a=p.parse_args()
    lock=json.loads(Path(a.lock).read_text(encoding='utf-8'));base=Path(a.output);base.mkdir(parents=True,exist_ok=True)
    clis=[x for x in a.clis.split(',') if x]
    if not clis or any(x not in lock['clis'] for x in clis):raise ValueError('Invalid CLI certification selection')
    receipts=[];errors={}
    with ThreadPoolExecutor(max_workers=len(clis)) as pool:
        futures={cli:pool.submit(lane,cli,lock,base) for cli in clis}
        for cli,future in futures.items():
            try:receipts+=future.result()
            except Exception as error:errors[cli]={'type':type(error).__name__}
    report={'task_version':'composite-unattended-v2','interaction_mode':'none','certified_clis':clis,'passed':not errors and len(receipts)==3*len(clis) and all(r['passed'] for r in receipts),'receipts':receipts,'errors':errors}
    reporter.write_json(base/'certification.json',report);print(json.dumps({'passed':report['passed'],'errors':errors}),flush=True)
    sys.exit(0 if report['passed'] else 2)
