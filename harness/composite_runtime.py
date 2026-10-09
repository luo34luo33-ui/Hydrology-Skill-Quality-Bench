"""Host-owned Docker execution, evidence observation and budget termination."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid
from harness.cli_events import EventCounter,command
from harness.confirmation import ConfirmationBroker
from harness.runner import _sha256_tree
from harness.filesystem import filesystem_path

COMMON_START='Read task_public.json, scenario.json, INPUT_GUIDE.md and OUTPUT_INTERFACES.md. All scientific facts and permissions are supplied upfront; no user answers or confirmation service are available during this run. Public scientific programs and basic interfaces are in /public. Choose tools, execution order and equivalent implementations autonomously within the declared models, parameters and budget. Preserve intermediate scientific evidence and relative SHA-256 references. Work only in /work and create the requested artifacts. No external retrieval or cross-task memory is available.'

def load_lock(path, clis=None):
    lock=json.loads(Path(filesystem_path(path)).read_text(encoding='utf-8'))
    if lock.get('status')!='live_certified_ready':raise ValueError('Runtime deployment is pending certification; do not run formal tasks')
    if lock.get('experiment_version')!='composite-unattended-v2' or lock.get('interaction_mode')!='none':raise ValueError('An unattended v2 runtime lock is required; old confirmation locks must be recertified')
    if not lock.get('image_digest','').startswith('sha256:'):raise ValueError('freeze a built image digest first')
    selected=set(clis or lock.get('certified_clis',[]))
    if not selected or not selected.issubset(set(lock.get('certified_clis',[]))):
        raise ValueError('Requested CLI has not completed the current runtime certification')
    if not lock.get('isolated_network_certified'):raise ValueError('isolated provider-only network is not certified')
    if lock.get('runtime_mode')!='isolated-relay' and not lock.get('network_name'):raise ValueError('isolated provider-only network is not certified')
    if lock.get('runtime_mode')=='isolated-relay':
        import importlib.util
        if importlib.util.find_spec('harness.isolated_runtime') is None:
            raise ValueError('isolated runtime connector is unavailable; deployment is not ready')
        import hashlib
        for name in ['smoke','budget']:
            certificate=lock.get('certifications',{}).get(name,{})
            receipt=Path(filesystem_path(certificate.get('path','')))
            if not receipt.is_file() or hashlib.sha256(receipt.read_bytes()).hexdigest()!=certificate.get('sha256'):
                raise ValueError('Missing or changed live certification: '+name)
            document=json.loads(receipt.read_text(encoding='utf-8'))
            if document.get('task_version')!='composite-unattended-v2' or document.get('interaction_mode')!='none':
                raise ValueError('Old live certificate cannot certify unattended execution: '+name)
            if not document.get('passed'):
                raise ValueError('Failed live certification: '+name)
            if name=='smoke' and lock.get('required_skill_certification')=='native-skill-v3':
                selected=set(clis or lock['clis'])
                receipts=[r for r in document.get('receipts',[]) if r.get('cli') in selected]
                if len(receipts)!=2*len(selected) or any(r.get('certification_version')!='native-skill-v3' or not r.get('native_skill_evidence',{}).get('passed') for r in receipts):
                    raise ValueError('Native skill load has not been certified for the selected CLI')
    if not lock.get('common_config_sha256'):raise ValueError('freeze the entire reviewed provider configuration directory')
    for cli in selected:
        c=lock.get('clis',{}).get(cli,{})
        if not all(c.get(k) for k in ['model','version','effort','budget_audit_certified','config_sha256']):raise ValueError('unfrozen/uncertified CLI: '+cli)
    return lock

def preflight(lock_path, clis=None):
    issues=[];checks={}
    try:lock=load_lock(lock_path,clis)
    except (ValueError,OSError) as e:return {'ready':False,'issues':[str(e)]}
    try:
        p=subprocess.run(['docker','version','--format','{{.Server.Version}}'],capture_output=True,text=True,timeout=15)
        checks['docker']=p.stdout.strip()
        if p.returncode:issues.append('Docker daemon unavailable')
        p=subprocess.run(['docker','image','inspect',lock['image_digest']],capture_output=True,text=True,timeout=15)
        if p.returncode:issues.append('Frozen image unavailable')
        if lock.get('runtime_mode')!='isolated-relay':
            p=subprocess.run(['docker','network','inspect',lock['network_name']],capture_output=True,text=True,timeout=15)
            if p.returncode or not json.loads(p.stdout)[0].get('Internal'):issues.append('Network must be an internal Docker network')
        auth=Path(filesystem_path(lock.get('common_config_dir','')))
        if lock.get('host_runtime_sha256') and _sha256_tree(Path(__file__).resolve().parent)!=lock['host_runtime_sha256']:issues.append('Host runtime changed after certification')
        allowed={'provider_environment.json','codex/config.toml','codex/auth.json','opencode/opencode.json','qwen/settings.json','qwen/oauth_creds.json'}
        if _sha256_tree(auth)!=lock['common_config_sha256']:issues.append('common provider configuration changed')
        if any(p.relative_to(auth).as_posix() not in allowed or p.is_symlink() for p in auth.rglob('*') if p.is_file()):issues.append('common provider directory contains unapproved files')
        for cli in clis or lock['clis']:
            c=lock['clis'][cli]
            if not (auth/cli).is_dir() or c['config_sha256']!=_sha256_tree(auth/cli):issues.append(cli+' common provider configuration changed')
        for cli in clis or lock['clis']:
            c=lock['clis'][cli]
            p=subprocess.run(['docker','run','--rm','--network','none',lock['image_digest'],cli,'--version'],capture_output=True,text=True,timeout=20)
            if p.returncode or c['version'] not in p.stdout+p.stderr:issues.append(cli+' installed version mismatch')
    except (OSError,subprocess.TimeoutExpired) as e:issues.append(str(e))
    return {'ready':not issues,'issues':issues,'checks':checks}

def monitor(argv,cli,budget,timeout,stdout_path,stderr_path,event_sink,terminate,extra_tools=lambda:0,decision_count=None,decision_exhausted=None):
    """Streaming budget monitor also used with recorded fake processes in tests."""
    counter=EventCounter(cli,budget['agent_rounds'],budget['tool_calls']);lines=queue.Queue()
    p=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,stdin=subprocess.DEVNULL,text=True,encoding='utf-8',errors='replace')
    def read(stream,kind):
        for line in stream:lines.put((kind,line))
        lines.put((kind,None));stream.close()
    threads=[threading.Thread(target=read,args=(p.stdout,'out'),daemon=True),threading.Thread(target=read,args=(p.stderr,'err'),daemon=True)]
    for t in threads:t.start()
    start=time.monotonic();reason=None;closed=set()
    with Path(stdout_path).open('w',encoding='utf-8') as out,Path(stderr_path).open('w',encoding='utf-8') as err:
        while len(closed)<2:
            if reason is None and time.monotonic()-start>=timeout:reason='timeout'
            if reason is None and counter.tools+extra_tools()>=budget['tool_calls']:reason='action_budget'
            if reason is None and decision_count and decision_count()>budget['agent_rounds']:reason='action_budget'
            if reason is None and decision_exhausted and decision_exhausted():reason='action_budget'
            if reason is not None and p.poll() is None:terminate();p.kill()
            try:kind,line=lines.get(timeout=.05)
            except queue.Empty:continue
            if line is None:closed.add(kind);continue
            stream=out if kind=='out' else err
            stream.write(line);stream.flush()
            if kind=='out' and reason is None:
                try:
                    for event in counter.feed(line):event_sink(event)
                    if counter.tools>=budget['tool_calls'] or (not decision_count and counter.exhausted):reason='action_budget'
                except ValueError:reason='unauditable_events'
    return_code=p.wait(timeout=5)
    if reason is None and not counter.recognized:reason='unauditable_events'
    for t in threads:t.join(timeout=1)
    result={'return_code':return_code,'termination_reason':reason,'timed_out':reason=='timeout','duration_seconds':time.monotonic()-start,**counter.summary(),'budget_exhausted':reason=='action_budget','tool_calls':counter.tools+extra_tools(),'confirmation_requests':extra_tools()}
    if decision_count:
        result['native_event_rounds']=result['agent_rounds']
        result['agent_rounds']=decision_count()
        result['round_definition']='upstream inference requests admitted by host gateway; retries count toward budget; compact excluded'
    return result

def run(task,workspace,task_dir,output_dir,lock_path,cli,condition,project_root):
    lock=load_lock(lock_path,[cli])
    if lock.get('runtime_mode')=='isolated-relay':
        from harness.isolated_runtime import run_isolated
        return run_isolated(task,workspace,task_dir,output_dir,lock,cli,condition,project_root)
    raise ValueError('Legacy direct-host runtime is disabled; certify isolated-relay runtime')
