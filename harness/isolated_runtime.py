"""Per-run relay isolation; host secrets and reference answers are never mounted."""
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import uuid

from harness.confirmation import AuditTrail
from harness.composite_runtime import COMMON_START, monitor
from harness import reporter
from harness.provider_gateway import create_gateway


def candidate_argv(lock,cli,condition,workspace,public,config,network,name,token,prompt):
    from harness.filesystem import normal_path
    cfg=lock['clis'][cli]
    argv=['docker','run','--rm','--name',name,'--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--cpus','4','--memory','8192m','--pids-limit','256',
        '--network',network,'--tmpfs','/tmp:rw,size=512m',
        '--tmpfs','/home/agent:rw,size=512m,uid=10001,gid=10001,mode=0700',
        '--entrypoint','/opt/conda/envs/HydroTune-eval/bin/python',
        '--mount',f'type=bind,source={normal_path(workspace)},target=/work',
        '--mount',f'type=bind,source={normal_path(public)},target=/public,readonly',
        '--mount',f'type=bind,source={normal_path(config)},target=/provider-config,readonly',
        '-w','/work','-e','HSQB_PUBLIC_PROGRAMS=/public']
    if token is not None:
        argv+=['-e','HSQB_CONFIRMATION_URL=http://hsqb-provider:8765/confirm','-e','HSQB_CONFIRMATION_TOKEN='+token]
    if condition=='with-skills':
        argv+=['--mount',f'type=bind,source={normal_path(lock["skills_dir"])},target=/home/agent/.agents/skills,readonly']
    return argv+[lock['image_digest'],'/opt/entrypoint.py',cli,cfg['model'],cfg['effort'],prompt]


@contextmanager
def relay_session(lock,cli,broker,output,root,gateway_builder=create_gateway,rounds=60):
    output=Path(output);root=Path(root)
    network='hsqb-'+uuid.uuid4().hex[:12];name=network+'-candidate';relay=network+'-relay'
    gateway=None;network_created=False
    try:
        gateway=gateway_builder(cli,lock['clis'][cli],output/'model_gateway_audit.jsonl',broker.record,rounds)
        port=None if isinstance(broker,AuditTrail) else broker.start()
        model_port=gateway.start()
        subprocess.run(['docker','network','create','--internal',network],check=True,capture_output=True)
        network_created=True
        subprocess.run(['docker','run','-d','--rm','--name',relay,'--network',network,
            '--network-alias','hsqb-provider','--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges','--memory','128m','--cpus','.5','--pids-limit','64',
            '--entrypoint','/opt/conda/envs/HydroTune-eval/bin/python',
            '--mount',f'type=bind,source={root / "runtime/provider_relay.py"},target=/relay.py,readonly',
            '-e',f'MODEL_PROFILE={"codex" if cli=="codex" else "deepseek"}',
            '-e',f'MODEL_UPSTREAM=http://host.docker.internal:{model_port}',
            *(['-e',f'CONFIRMATION_UPSTREAM=http://host.docker.internal:{port}'] if port is not None else []),
            lock['image_digest'],'/relay.py'],check=True,capture_output=True)
        subprocess.run(['docker','network','connect','bridge',relay],check=True,capture_output=True)
        reporter.write_json(output/'relay_audit.json',{
            'candidate_network':network,'candidate_host_gateway':False,
            'network':json.loads(subprocess.check_output(['docker','network','inspect',network])),
            'relay':json.loads(subprocess.check_output(['docker','inspect',relay]))})
        for attempt in range(10):
            probe=subprocess.run(['docker','run','--rm','--network',network,
                '--entrypoint','/opt/conda/envs/HydroTune-eval/bin/python',lock['image_digest'],'-c',
                'import urllib.request;print(urllib.request.urlopen("http://hsqb-provider:8765/health",timeout=5).status)'],
                capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
            if probe.returncode==0:break
        else:raise RuntimeError('Relay health preflight failed')
        yield network,name,gateway
    finally:
        for container in [name,relay]:subprocess.run(['docker','rm','-f',container],capture_output=True,timeout=20)
        if hasattr(broker,'server'):broker.close()
        if gateway and hasattr(gateway,'server'):gateway.close()
        if network_created:subprocess.run(['docker','network','rm',network],capture_output=True,timeout=20)
        reporter.write_json(output/'cleanup.json',{'cleanup_attempted':True,'containers':[name,relay],'network':network})


def run_isolated(task,workspace,task_dir,output,lock,cli,condition,root):
    from harness.runner import _sha256_tree
    root=Path(root);workspace=Path(workspace);output=Path(output)
    if condition not in {'no-skills','with-skills'}:raise ValueError('Invalid condition')
    if lock['public_programs_sha256']!=_sha256_tree(root/'runtime/public'):raise ValueError('Public programs changed')
    if lock['skills_sha256']!=_sha256_tree(root/'runtime/skills'):raise ValueError('Skills changed')
    if task.get('interaction_mode')!='none' or task.get('task_version')!='composite-unattended-v2':
        raise ValueError('Only unattended v2 composite tasks may use this runtime')
    if (root/'runtime/public/confirm_user.py').exists():raise ValueError('Public bundle exposes a retired confirmation interface')
    # Runtime never loads hidden user answers or scientific settings.
    broker=AuditTrail(output/'host_audit.jsonl')
    with relay_session(lock,cli,broker,output,root,rounds=task['resource_budget']['agent_rounds']) as (network,name,gateway):
        argv=candidate_argv(lock,cli,condition,workspace,root/'runtime/public',lock['common_config_dir'],network,name,None,COMMON_START)
        def terminate():subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=20)
        execution=monitor(argv,cli,task['resource_budget'],task['timeout_seconds'],output/'stdout.log',output/'stderr.log',broker.record,terminate,
            decision_count=lambda:gateway.decision_requests,decision_exhausted=lambda:gateway.budget_denied)
        path='/backend-api/codex/responses' if cli=='codex' else '/v1/chat/completions'
        execution['model_execution_started']=any(e.get('method')=='POST' and e.get('path')==path and e.get('status')==200 for e in gateway.events)
        execution['eligible']=bool(execution['model_execution_started'])
        execution.update({'model':lock['clis'][cli]['model'],'effort':lock['clis'][cli]['effort'],'cli_version':lock['clis'][cli]['version']})
        execution.update(task_version=task['task_version'],interaction_mode='none',confirmation_service_started=False)
        execution['diagnostic_category']=('environment_unavailable' if not execution['eligible'] else
            'agent_execution_failure' if execution['return_code'] or execution.get('termination_reason') else 'execution_completed')
    from harness.resource_usage import usage_from_logs
    execution['token_usage']=usage_from_logs(output)
    return execution,broker.events
