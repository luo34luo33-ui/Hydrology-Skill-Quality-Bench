"""One isolated Codex pilot; deliberately excluded from formal experiment runs.

The host owns model forwarding, confirmation answers, budgets and grading.
Only public task data/programs are mounted. No personal config or skills are loaded.
"""
from __future__ import annotations

import argparse
import datetime as dt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from urllib.parse import urlsplit
import urllib.error
import urllib.request

from harness import grader, reporter, runner
from harness.composite_runtime import COMMON_START, monitor
from harness.confirmation import AuditTrail
from runtime.provider_relay import allowed_model_route


class ModelGateway:
    """Fixed HTTPS upstream and model routes; no CONNECT/arbitrary URL forwarding."""
    def __init__(self, audit, auth_headers=None, model=None, round_limit=None, event_sink=None):
        self.audit = Path(audit)
        self.auth_headers = auth_headers or {}
        self.model = model
        self.round_limit = round_limit
        self.event_sink = event_sink
        self.decision_requests = 0
        self.budget_denied = False
        self.lock = threading.Lock()
        self.events = []

    def record(self, method, path, status):
        with self.lock, self.audit.open('a', encoding='utf-8') as f:
            event = {'method': method, 'path': urlsplit(path).path,
                     'status': status, 'time_ns': time.monotonic_ns()}
            self.events.append(event)
            f.write(json.dumps(event) + '\n')

    def start(self):
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def do_CONNECT(self):
                self.send_error(403)

            def forward(self):
                if not allowed_model_route(self.command, self.path):
                    gateway.record(self.command, self.path, 403)
                    self.send_error(403)
                    return
                if self.headers.get('Upgrade'):
                    gateway.record(self.command, self.path, 426)
                    self.send_error(426, 'Use the HTTP streaming interface')
                    return
                n = int(self.headers.get('Content-Length', '0'))
                if n > 32 * 1024 * 1024:
                    self.send_error(413)
                    return
                headers = {k: v for k, v in self.headers.items() if k.lower() not in {
                    'host', 'connection', 'transfer-encoding', 'accept-encoding',
                    'upgrade', 'content-length'
                }}
                headers['Accept-Encoding'] = 'identity'
                headers.update(gateway.auth_headers)
                body = self.rfile.read(n) if n else None
                if body and gateway.model:
                    try:
                        payload = json.loads(body)
                    except ValueError:
                        self.send_error(400)
                        return
                    if payload.get('model') != gateway.model:
                        gateway.record(self.command, self.path, 403)
                        self.send_error(403, 'Frozen model required')
                        return
                if self.command == 'POST' and urlsplit(self.path).path == '/backend-api/codex/responses':
                    with gateway.lock:
                        if gateway.round_limit is not None and gateway.decision_requests >= gateway.round_limit:
                            gateway.budget_denied = True
                            self.send_error(429, 'Decision budget exhausted')
                            return
                        gateway.decision_requests += 1
                        decision_id = gateway.decision_requests
                    if gateway.event_sink:
                        gateway.event_sink({'kind':'model_decision_request','id':str(decision_id)})
                class NoRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, *args, **kwargs):
                        return None
                request = urllib.request.Request('https://chatgpt.com' + self.path,
                    headers=headers, data=body, method=self.command)
                try:
                    try:
                        r = urllib.request.build_opener(NoRedirect()).open(request, timeout=300)
                    except urllib.error.HTTPError as error:
                        r = error
                    with r:
                        gateway.record(self.command, self.path, r.status)
                        self.send_response(r.status)
                        for k, v in r.headers.items():
                            if k.lower() not in {'connection', 'transfer-encoding',
                                                 'content-encoding', 'content-length'}:
                                self.send_header(k, v)
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        # read1 returns currently available bytes without waiting to fill a chunk.
                        while data := r.read1(65536):
                            self.wfile.write(data)
                            self.wfile.flush()
                except (urllib.error.URLError, OSError):
                    gateway.record(self.command, self.path, 502)
                    self.close_connection = True
                    return
                self.close_connection = True

            do_GET = forward
            do_POST = forward

        self.server = ThreadingHTTPServer(('0.0.0.0', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.server.server_port

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def run_pilot(image, output, test_id='hydrochain-data-001', model='gpt-6.1-sol', effort='medium'):
    root = Path(__file__).resolve().parent.parent
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Pilot output must be a fresh directory')
    items = runner.discover_tasks(root / 'tests', test_id=test_id, suite='composite')
    if len(items) != 1:
        raise ValueError('Pilot requires exactly one composite task')
    item = items[0]
    task = item['task']
    issues = runner.validate_tests(root / 'tests', test_id=test_id, suite='composite')
    if issues:
        raise ValueError(issues)
    image_info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))[0]
    image_id = image_info['Id']
    version = subprocess.check_output(['docker', 'run', '--rm', '--network', 'none', image_id,
                                       'codex', '--version'], text=True).strip()
    output.mkdir(parents=True, exist_ok=True)
    task_out = output / 'tasks' / test_id
    task_out.mkdir(parents=True)
    workspace = task_out / 'workspace'
    runner.stage_workspace(task, item['task_dir'], workspace)
    if task.get('interaction_mode')!='none':raise ValueError('Pilot requires unattended v2 tasks')
    reference = {}
    broker = AuditTrail(task_out / 'host_audit.jsonl')
    gateway = ModelGateway(output / 'model_gateway_audit.jsonl')
    network = 'hsqb-pilot-' + uuid.uuid4().hex[:12]
    name = network + '-codex'
    relay_name = network + '-relay'
    subprocess.run(['docker', 'network', 'create', '--internal', network], check=True, capture_output=True)
    stop = threading.Event()
    known = set()
    observed = {p for c in reference.get('confirmations', []) for p in c['before_artifacts']}
    observe_lock = threading.Lock()

    def observe():
        with observe_lock:
            for p in observed:
                if p not in known and (workspace / p).is_file():
                    broker.record({'kind': 'artifact', 'path': p})
                    known.add(p)

    broker.before_answer = lambda _: observe()
    broker.budget_exhausted = lambda: sum(e.get('kind') in {'tool', 'confirmation_request'} for e in broker.events) >= task['resource_budget']['tool_calls']

    def watcher():
        while not stop.wait(.01):
            observe()

    thread = threading.Thread(target=watcher, daemon=True)

    def terminate():
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=15)

    try:
        model_port = gateway.start()
        # Only the relay has an egress interface. The candidate has no host-gateway mapping.
        subprocess.run(['docker', 'run', '-d', '--rm', '--name', relay_name,
                        '--network', network, '--network-alias', 'hsqb-provider',
                        '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                        '--memory', '128m', '--cpus', '.5', '--pids-limit', '64',
                        '--entrypoint', '/opt/conda/envs/HydroTune-eval/bin/python',
                        '--mount', f'type=bind,source={root / "runtime/provider_relay.py"},target=/relay.py,readonly',
                        '-e', f'MODEL_UPSTREAM=http://host.docker.internal:{model_port}',
                        image_id, '/relay.py'], check=True, capture_output=True)
        subprocess.run(['docker', 'network', 'connect', 'bridge', relay_name], check=True, capture_output=True)
        # Infrastructure probe only, no login or model generation. Fail before starting Codex.
        for attempt in range(10):
            probe = subprocess.run(['docker', 'run', '--rm', '--network', network,
                '--entrypoint', '/opt/conda/envs/HydroTune-eval/bin/python', image_id, '-c',
                'import urllib.request;print(urllib.request.urlopen("http://hsqb-provider:8765/health",timeout=5).read().decode())'],
                capture_output=True, text=True, timeout=15)
            if probe.returncode == 0:
                break
        else:
            raise RuntimeError('Internal provider relay preflight failed: ' + probe.stderr)
        thread.start()
        # Only the login file is copied. Personal config, plugins, MCP, memory and skills are absent.
        with tempfile.TemporaryDirectory(prefix='hsqb-pilot-provider-') as auth_temp:
            auth = Path(auth_temp)
            (auth / 'codex').mkdir()
            shutil.copyfile(Path.home() / '.codex/auth.json', auth / 'codex/auth.json')
            config = f'''model = {json.dumps(model)}
model_reasoning_effort = {json.dumps(effort)}
chatgpt_base_url = "http://hsqb-provider:8765/backend-api/"
model_provider = "pilot_gateway"
cli_auth_credentials_store = "file"
web_search = "disabled"
check_for_update_on_startup = false
[model_providers.pilot_gateway]
name = "OpenAI isolated model relay"
base_url = "http://hsqb-provider:8765/backend-api/codex"
wire_api = "responses"
requires_openai_auth = true
supports_websockets = false
[features]
apps = false
plugins = false
memories = false
multi_agent = false
browser_use = false
computer_use = false
skill_search = false
'''
            (auth / 'codex/config.toml').write_text(config, encoding='utf-8')
            probe_code = '''import json,urllib.request
from pathlib import Path
d=json.loads(Path("/provider-config/codex/auth.json").read_text())
r=urllib.request.Request("http://hsqb-provider:8765/backend-api/codex/models?client_version=0.160.0",headers={"Authorization":"Bearer "+d["tokens"]["access_token"],"ChatGPT-Account-Id":d["tokens"]["account_id"]})
with urllib.request.urlopen(r,timeout=20) as response:
 data=json.load(response)
 print(json.dumps({"status":response.status,"target_model_listed":any(m.get("slug")=="gpt-6.1-sol" for m in data.get("models",[]))}))
'''
            probe = subprocess.run(['docker', 'run', '--rm', '--network', network,
                '--entrypoint', '/opt/conda/envs/HydroTune-eval/bin/python',
                '--mount', f'type=bind,source={auth},target=/provider-config,readonly',
                image_id, '-c', probe_code], capture_output=True, text=True, timeout=30)
            reporter.write_json(output / 'connection_preflight.json',
                                {'return_code': probe.returncode, 'stdout': probe.stdout, 'stderr': probe.stderr})
            if probe.returncode:
                raise RuntimeError('Authenticated model connection preflight failed; Agent not started')
            controls = {'image_digest': image_id, 'cli_version': version, 'model': model,
                        'effort': effort, 'condition': 'no-skills', 'public_programs_sha256': runner._sha256_tree(root / 'runtime/public'),
                        'startup_prompt_sha256': hashlib.sha256(COMMON_START.encode()).hexdigest(),
                        'provider_config_sha256': runner._sha256_tree(auth), 'network_internal': True,
                        'network_formally_certified': False, 'skills_mounted': False,
                        'hidden_reference_mounted': False, 'budget': task['resource_budget'],
                        'timeout_seconds': task['timeout_seconds']}
            metadata = {'schema_version': 1, 'purpose': 'single-task integration pilot',
                        'formal_eligible': False, 'created_at_utc': dt.datetime.now(dt.UTC).isoformat(),
                        'suite': 'composite', 'tests_root': str(root / 'tests'), 'selected_test_id': test_id,
                        'skill_condition': 'no-skills', 'runtime_controls': controls,
                        'task_hashes': {test_id: runner._sha256_tree(item['task_dir'])}}
            reporter.write_json(output / 'run_metadata.json', metadata)
            argv = ['docker', 'run', '--rm', '--name', name, '--read-only', '--cap-drop', 'ALL',
                    '--security-opt', 'no-new-privileges', '--cpus', str(task['resource_budget']['cpus']),
                    '--memory', str(task['resource_budget']['memory_mb']) + 'm', '--pids-limit', '256',
                    '--network', network,
                    '--tmpfs', '/tmp:rw,size=512m', '--tmpfs', '/home/agent:rw,size=512m,uid=10001,gid=10001,mode=0700',
                    '--entrypoint', '/opt/conda/envs/HydroTune-eval/bin/python',
                    '--mount', f'type=bind,source={workspace},target=/work',
                    '--mount', f'type=bind,source={root / "runtime/public"},target=/public,readonly',
                    '--mount', f'type=bind,source={auth},target=/provider-config,readonly',
                    '-w', '/work', '-e', 'HSQB_PUBLIC_PROGRAMS=/public',
                    image_id, '/opt/entrypoint.py', 'codex', model, effort, COMMON_START]
            execution = monitor(argv, 'codex', task['resource_budget'], task['timeout_seconds'],
                                task_out / 'stdout.log', task_out / 'stderr.log', broker.record,
                                terminate, lambda: sum(e.get('kind') == 'confirmation_request' for e in broker.events))
    finally:
        terminate()
        subprocess.run(['docker', 'rm', '-f', relay_name], capture_output=True, timeout=15)
        stop.set()
        if thread.is_alive():
            thread.join(timeout=2)
        observe()
        if hasattr(broker, 'server'):
            broker.close()
        if hasattr(gateway, 'server'):
            gateway.close()
        subprocess.run(['docker', 'network', 'rm', network], capture_output=True, timeout=15)
    execution['cli_session_started'] = execution['agent_started']
    execution['model_execution_started'] = any(e.get('method') == 'POST' and e.get('path') == '/backend-api/codex/responses' and e.get('status') == 200 for e in gateway.events)
    execution['agent_started'] = bool(execution['model_execution_started'] or execution['agent_rounds'] or execution['tool_calls'])
    execution.update({'model': model, 'effort': effort, 'cli_version': version,
                      'eligible': execution['agent_started'], 'formal_eligible': False})
    result = grader.grade_task(task, workspace, item['task_dir'], audit_events=broker.events)
    result['eligible'] = execution['eligible']
    result['formal_eligible'] = False
    if execution['return_code'] or execution.get('termination_reason'):
        result['task_success'] = False
    result['execution'] = {'return_code': execution['return_code'], 'timed_out': execution['timed_out']}
    reporter.write_json(task_out / 'execution.json', execution)
    reporter.write_json(task_out / 'result.json', result)
    summary = reporter.aggregate_results([result])
    reporter.write_json(output / 'summary.json', summary)
    print(reporter.format_summary(summary))
    print('run_dir: ' + str(output))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--test-id', default='hydrochain-data-001')
    parser.add_argument('--model', default='gpt-6.1-sol')
    parser.add_argument('--effort', default='medium')
    args = parser.parse_args()
    run_pilot(**vars(args))
