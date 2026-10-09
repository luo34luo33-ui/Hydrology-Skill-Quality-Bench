"""Fail-closed formal atomic runtime. Host-only references; three mount conditions."""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading

from harness.atomic_contracts import CONDITIONS, VERSION, tree_digest
from harness import reporter
from harness.filesystem import filesystem_path


def load_lock(path, cli):
    lock = json.loads(Path(filesystem_path(path)).read_text(encoding='utf-8'))
    if lock.get('experiment_version') != VERSION or lock.get('runtime_mode') != 'atomic-isolated-relay':
        raise ValueError('an atomic three-arm lock is required; composite/legacy locks are incompatible')
    if cli not in {'codex', 'opencode', 'qwen', 'codebuddy'}: raise ValueError('invalid CLI')
    image = lock.get('image_digest') or ''
    if not image.startswith('sha256:') and '@sha256:' not in image: raise ValueError('freeze actual image ID/digest')
    cfg = lock.get('clis', {}).get(cli, {})
    if not all(cfg.get(k) for k in ('version', 'model', 'effort', 'config_sha256')):
        raise ValueError('unfrozen CLI settings')
    for name in ('public_programs_dir', 'skills_dir', 'common_config_dir'):
        if not Path(filesystem_path(lock.get(name, ''))).is_dir(): raise ValueError('missing frozen directory: ' + name)
    for name, hash_name in [('public_programs_dir', 'public_programs_sha256'), ('skills_dir', 'skills_sha256'), ('common_config_dir', 'common_config_sha256')]:
        if tree_digest(Path(lock[name])) != lock.get(hash_name): raise ValueError('frozen directory changed: ' + name)
    config_dir = Path(filesystem_path(lock['common_config_dir']))
    allowed = {'provider_environment.json', 'codex/config.toml', 'opencode/opencode.json', 'qwen/settings.json', 'codebuddy/settings.json'}
    if any(p.is_symlink() or p.relative_to(config_dir).as_posix() not in allowed for p in config_dir.rglob('*') if p.is_file()):
        raise ValueError('public provider directory contains credentials or unapproved files')
    if tree_digest(config_dir / cli) != cfg['config_sha256']:
        raise ValueError('CLI provider config changed')
    for file in [*config_dir.rglob('*.json'), *config_dir.rglob('*.toml')]:
        if file.suffix == '.toml':
            import tomllib
            doc = tomllib.loads(file.read_text(encoding='utf-8'))
        else: doc = json.loads(file.read_text(encoding='utf-8'))
        def check(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {'hooks', 'mcp', 'mcpServers', 'plugin', 'plugins', 'extensions', 'enabledPlugins', 'modelFallbacks', 'fallbackModels'} and child:
                        raise ValueError('public provider configuration contains customization/fallbacks')
                    if (key.lower() in {'apikey', 'api_key', 'access_token', 'refresh_token', 'authorization', 'auth_token'} or key.endswith(('_API_KEY', '_AUTH_TOKEN'))) and child and child != 'isolated-placeholder-no-real-key':
                        raise ValueError('real credential must stay in host gateway')
                    if (key.lower() in {'baseurl', 'base_url'} or key.endswith('_BASE_URL')) and child and not str(child).startswith('http://hsqb-provider:8765/'):
                        raise ValueError('candidate provider must use the internal relay')
                    check(child)
            elif isinstance(value, list):
                for child in value: check(child)
        check(doc)
    if tree_digest(Path(__file__).parent) != lock.get('host_runtime_sha256'):
        raise ValueError('host runtime changed after certification')
    from harness.runner import discover_tasks, _sha256_file
    tasks = discover_tasks(Path(lock['tests_root']))
    hashes = {x['task']['id']: _sha256_file(x['task_dir'] / x['task']['public_contract']) for x in tasks}
    if len(hashes) != 183 or hashes != lock.get('public_contract_hashes'):
        raise ValueError('public contracts changed or task inventory incomplete')
    # Receipts are trusted host certification outputs; never candidate supplied.
    for kind in ('contracts', 'isolation', 'provider'):
        record = lock.get('certifications', {}).get(kind, {})
        receipt_path = Path(filesystem_path(record.get('path', '')))
        if not receipt_path.is_file(): raise ValueError('missing certification: ' + kind)
        from harness.atomic_contracts import digest
        if digest(receipt_path) != record.get('sha256'): raise ValueError('certification changed: ' + kind)
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if kind == 'contracts':
            if not receipt.get('contracts_ready'): raise ValueError('public contract audit is incomplete')
            if not receipt.get('negative_controls_ready'): raise ValueError('original graders do not pass the required negative controls')
            if not receipt.get('native_programs_ready'): raise ValueError('public program/atomic task compatibility has not passed all 183 tasks')
            if receipt.get('public_programs_sha256') != lock['public_programs_sha256']:
                raise ValueError('contract audit uses a different public bundle')
        else:
            if receipt.get('image_digest') != image or receipt.get('public_programs_sha256') != lock['public_programs_sha256']:
                raise ValueError('certification not bound to frozen artifacts: ' + kind)
            evidence = receipt.get('clis', {}).get(cli, {})
            if not evidence.get('passed') or evidence.get('version') != cfg['version']:
                raise ValueError('CLI certification failed/pending: ' + kind)
            if kind == 'isolation':
                names = {'hidden_unreadable', 'other_workspace_unreadable', 'external_network_denied',
                         'baseline_programs_absent', 'programs_only_skills_absent', 'with_skills_mounted'}
                checks = evidence.get('checks', {})
                if not names.issubset(checks) or not all(checks[n].get('passed') and checks[n].get('evidence') for n in names):
                    raise ValueError('missing actual isolation probe evidence')
            elif evidence.get('model') != cfg['model'] or evidence.get('effort') != cfg['effort']:
                raise ValueError('provider certification has different model controls')
            elif not evidence.get('native_skill_discovery_verified'):
                raise ValueError('native skill discovery has not been verified for this CLI')
    if cli == 'codebuddy' and cfg.get('relay_protocol') != 'openai-chat':
        raise ValueError('CodeBuddy Tencent login relay is not certified; local login cannot be mounted')
    return lock


def preflight(path, cli):
    try:
        lock = load_lock(path, cli)
        from harness.runner import _cli_version
        p = subprocess.run(['docker', 'image', 'inspect', lock['image_digest']], capture_output=True, timeout=20)
        if p.returncode: raise ValueError('frozen Docker image unavailable')
        p = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--entrypoint', cli,
                            lock['image_digest'], '--version'], capture_output=True, text=True, timeout=30)
        if p.returncode or lock['clis'][cli]['version'] not in p.stdout + p.stderr:
            raise ValueError('installed CLI version does not match lock')
        return {'ready': True, 'issues': []}
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        return {'ready': False, 'issues': [str(exc)]}


class AuditOnlyBroker:
    """No answer table. Confirmation requests are explicitly unavailable for atomic tasks."""
    token = 'atomic-no-confirmation'
    def __init__(self, path): self.path = Path(path); self.events = []
    def record(self, event):
        self.events.append(event)
        with self.path.open('a', encoding='utf-8') as stream: stream.write(json.dumps(event) + '\n')
    def start(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self): self.send_response(403); self.end_headers()
            def do_POST(self): self.send_response(403); self.end_headers()
        self.server = ThreadingHTTPServer(('0.0.0.0', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        return self.server.server_port
    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)


def candidate_argv(lock, cli, condition, workspace, network, name, prompt):
    from harness.filesystem import normal_path
    if condition not in CONDITIONS: raise ValueError('invalid condition')
    argv = ['docker', 'run', '--rm', '--name', name, '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--cpus', '4', '--memory', '8192m', '--pids-limit', '256',
            '--network', network, '--tmpfs', '/tmp:rw,size=512m',
            '--tmpfs', '/home/agent:rw,size=512m,uid=10001,gid=10001,mode=0700',
            '--entrypoint', '/opt/conda/envs/HydroTune-eval/bin/python',
            '--mount', f'type=bind,source={normal_path(workspace)},target=/work',
            '--mount', f'type=bind,source={normal_path(lock["common_config_dir"])},target=/provider-config,readonly',
            '-w', '/work']
    if condition != 'no-skills':
        argv += ['--mount', f'type=bind,source={normal_path(lock["public_programs_dir"])},target=/work/public,readonly']
    if condition == 'with-skills':
        argv += ['--mount', f'type=bind,source={normal_path(lock["skills_dir"])},target=/home/agent/.agents/skills,readonly']
    cfg = lock['clis'][cli]
    return argv + [lock['image_digest'], '/opt/atomic_entrypoint.py', cli, cfg['model'], cfg['effort'], prompt]


def run_isolated_atomic(task, workspace, output, lock, cli, condition, root):
    from harness.agent_wrapper import generate_agents_md
    from harness.isolated_runtime import relay_session
    from harness.composite_runtime import monitor
    from scripts.atomic_cli_support import START_PROMPT
    output, workspace = Path(output), Path(workspace)
    (workspace / 'AGENTS.md').write_text(generate_agents_md(task, False), encoding='utf-8')
    broker = AuditOnlyBroker(output / 'host_audit.jsonl')
    # Atomic tasks retain their existing timeouts; action caps are only those explicitly frozen.
    budget = lock.get('atomic_budget', {'agent_rounds': 60, 'tool_calls': 120})
    with relay_session(lock, cli, broker, output, root, rounds=budget['agent_rounds']) as (network, name, gateway):
        argv = candidate_argv(lock, cli, condition, workspace, network, name, START_PROMPT)
        def terminate(): subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=20)
        execution = monitor(argv, cli, budget, task['timeout_seconds'], output / 'stdout.log', output / 'stderr.log',
                            broker.record, terminate, decision_count=lambda: gateway.decision_requests,
                            decision_exhausted=lambda: gateway.budget_denied)
        execution.update({'condition': condition, 'model': lock['clis'][cli]['model'],
                          'effort': lock['clis'][cli]['effort'], 'runtime': 'isolated'})
        from urllib.parse import urlsplit
        inference_path = '/backend-api/codex/responses' if cli == 'codex' else '/v1/chat/completions'
        execution['model_execution_started'] = any(e.get('method') == 'POST' and e.get('status') == 200
            and urlsplit(e.get('path', '')).path == inference_path for e in gateway.events)
        execution['infrastructure_failure'] = execution.get('termination_reason') == 'unauditable_events' or not execution['model_execution_started']
        return execution
