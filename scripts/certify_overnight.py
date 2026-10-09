"""Live CLI smoke checks, isolated network probes and budget evidence; no science tasks."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import traceback
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from harness.confirmation import AuditTrail
from harness.isolated_runtime import relay_session,candidate_argv
from harness.composite_runtime import monitor
from harness import reporter

PROMPT='''This is an independent deployment smoke test, not a benchmark task.
Work only in /work. Public interfaces are in /public. Read input.csv and scenario.json;
the timezone is supplied upfront and no user questions or answers are available,
then write summary.json with n, mean_discharge, unit, timezone. Also write
capabilities.json as a JSON list of immediate child directory names under
/home/agent/.agents/skills that contain SKILL.md. If that directory is absent,
write an empty list. This checks installed domain skill descriptions, not the
public scientific programs or bundled general skills. Use the supplied timezone
in the summary. Do not modify provider configuration. Finish after both files.'''

SKILL_PROMPT='''Before writing outputs, use the native skill tool to load both
data-preprocessing and prepare-discharge-timeseries. Do not substitute a directory
listing or direct file read for the native skill tool. Read their returned bodies,
then include skill_receipts in summary.json, with each skill name and one exact
nonempty heading copied from that returned body. These are deployment probes,
not additional scientific task instructions.'''

def native_skill_evidence(cli,stdout,lock,summary):
    if cli!='opencode':
        # Until another adapter has explicit native-load event replay, fail closed.
        return {'passed':False,'reason':'native_skill_adapter_not_certified'}
    required={'data-preprocessing':'workflows-data-preprocessing',
              'prepare-discharge-timeseries':'data-processing-prepare-discharge-timeseries'}
    events=[]
    for line in stdout.read_text(encoding='utf-8').splitlines():
        try:doc=json.loads(line)
        except ValueError:continue
        part=doc.get('part',{});state=part.get('state',{})
        if doc.get('type')=='tool_use' and part.get('tool')=='skill':events.append(state)
    receipts=summary.get('skill_receipts',[])
    checks={}
    for name,directory in required.items():
        expected_directory=Path(lock['skills_dir'])/directory
        calls=[e for e in events if e.get('status')=='completed' and e.get('input',{}).get('name')==name]
        headings=[r.get('heading','') for r in receipts if isinstance(r,dict) and (r.get('name') or r.get('skill'))==name]
        checks[name]=expected_directory.joinpath('SKILL.md').is_file() and any(
            h.startswith('#') and any(f'<skill_content name="{name}">' in str(e.get('output','')) and h in str(e.get('output','')) for e in calls)
            for h in headings)
    return {'passed':all(checks.values()),'checks':checks,'native_calls':len(events),
            'native_errors':sum(e.get('status')=='error' for e in events)}

PROBE='''import json,urllib.request,urllib.error,socket
from pathlib import Path
r={"public_available":Path("/public/programs.json").is_file(),
"confirmation_interface_absent":not Path("/public/confirm_user.py").exists(),
"confirmation_credentials_absent":not any(k.startswith("HSQB_CONFIRMATION_") for k in __import__('os').environ),
"skill_count":len(list(Path("/home/agent/.agents/skills").glob("*/SKILL.md"))),
"hidden_reference_available":Path("/work/expected").exists()}
try:r["relay_health"]=urllib.request.urlopen("http://hsqb-provider:8765/health",timeout=5).status
except Exception:r["relay_health"]=None
try:urllib.request.urlopen("http://hsqb-provider:8765/arbitrary",timeout=5);r["arbitrary_route_blocked"]=False
except urllib.error.HTTPError as e:r["arbitrary_route_blocked"]=e.code==403
for name,url in [("external_blocked","https://example.com"),("host_model_blocked",HOST_MODEL),("host_confirm_blocked","http://hsqb-provider:8765/confirm")]:
 try:urllib.request.urlopen(url,timeout=3);r[name]=False
 except Exception:r[name]=True
print(json.dumps(r))
'''

def certify_cli(cli,lock,base):
    receipts=[]
    for condition in ['no-skills','with-skills']:
        out=base/cli/condition;out.mkdir(parents=True,exist_ok=False);workspace=out/'workspace';workspace.mkdir()
        (workspace/'input.csv').write_text('time,discharge_m3s\n2026-01-01T00:00:00,2\n2026-01-01T01:00:00,4\n')
        reporter.write_json(workspace/'scenario.json',{'timezone':'UTC','unit':'m3/s','interaction_mode':'none'})
        broker=AuditTrail(out/'host_audit.jsonl')
        with relay_session(lock,cli,broker,out,ROOT,rounds=10) as (network,name,gateway):
            prompt=PROMPT+('\n'+SKILL_PROMPT if condition=='with-skills' else '\nDo not load any benchmark domain skills; none are supplied.')
            argv=candidate_argv(lock,cli,condition,workspace,ROOT/'runtime/public',lock['common_config_dir'],network,name,broker.token,prompt)
            code=PROBE.replace('HOST_MODEL',repr(f'http://host.docker.internal:{gateway.server.server_port}/'+('backend-api/codex/models?client_version=0.160.0' if cli=='codex' else 'v1/models')))
            probe=subprocess.run(argv[:-6]+[lock['image_digest'],'-c',code],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=25)
            if probe.returncode:raise RuntimeError('Network probe process failed: '+probe.stderr[-300:])
            network_check=json.loads(probe.stdout);reporter.write_json(out/'network_probe.json',network_check)
            if not all(network_check.get(k) for k in ['public_available','confirmation_interface_absent','confirmation_credentials_absent','relay_health','arbitrary_route_blocked','external_blocked','host_model_blocked','host_confirm_blocked']):
                raise RuntimeError('Network probe failed: '+json.dumps(network_check))
            if network_check['hidden_reference_available'] or network_check['skill_count']!=(44 if condition=='with-skills' else 0):raise RuntimeError('Mount isolation failed')
            def terminate():subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)
            execution=monitor(argv,cli,{'agent_rounds':10,'tool_calls':30},150,out/'stdout.log',out/'stderr.log',broker.record,terminate,
                lambda:sum(e.get('kind')=='confirmation_request' for e in broker.events),lambda:gateway.decision_requests,lambda:gateway.budget_denied)
            reporter.write_json(out/'execution.json',execution)
            summary=json.loads((workspace/'summary.json').read_text(encoding='utf-8')) if (workspace/'summary.json').exists() else {}
            capabilities=json.loads((workspace/'capabilities.json').read_text(encoding='utf-8')) if (workspace/'capabilities.json').exists() else None
            names=capabilities if isinstance(capabilities,list) else capabilities.get('names',capabilities.get('capabilities',[])) if isinstance(capabilities,dict) else None
            passed=execution['return_code']==0 and not execution['termination_reason'] and summary.get('n')==2 and summary.get('mean_discharge')==3 and summary.get('timezone')=='UTC'
            passed=passed and names is not None and bool(names)==(condition=='with-skills')
            passed=passed and not any(e.get('kind','').startswith('confirmation') for e in broker.events) and any(e.get('method')=='POST' and e.get('status')==200 for e in gateway.events)
            native=native_skill_evidence(cli,out/'stdout.log',lock,summary) if condition=='with-skills' else {'passed':network_check['skill_count']==0 and names==[]}
            passed=passed and native['passed']
            receipt={'task_version':'composite-unattended-v2','interaction_mode':'none','certification_version':'native-skill-v3','cli':cli,'condition':condition,'passed':bool(passed),'network':network_check,'execution':execution,'native_capability_names':names,'native_skill_evidence':native}
            reporter.write_json(out/'receipt.json',receipt);receipts.append(receipt)
            print(json.dumps({'cli':cli,'condition':condition,'passed':bool(passed),'rounds':gateway.decision_requests}),flush=True)
            if not passed:break
    return receipts

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',default='results/unattended-v3-certification');p.add_argument('--lock',default='runtime/experiment.unattended-v3.pending.lock.json');p.add_argument('--clis',default='opencode');a=p.parse_args()
    lock=json.loads(Path(a.lock).read_text(encoding='utf-8'));base=Path(a.output);base.mkdir(parents=True,exist_ok=True)
    clis=a.clis.split(',');receipts=[];errors={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={cli:pool.submit(certify_cli,cli,lock,base) for cli in clis}
        for cli,f in futures.items():
            try:receipts+=f.result()
            except Exception as error:errors[cli]={'type':type(error).__name__,'detail':str(error)[:600],'traceback':traceback.format_exc()[-2000:]}
    document={'task_version':'composite-unattended-v2','interaction_mode':'none','certified_clis':clis,'receipts':receipts,'errors':errors,'passed':not errors and len(receipts)==2*len(clis) and all(r['passed'] for r in receipts)}
    reporter.write_json(base/'certification.json',document)
    print(json.dumps({'passed':document['passed'],'errors':errors},ensure_ascii=False),flush=True)
    if not document['passed']:sys.exit(2)

if __name__=='__main__':main()
