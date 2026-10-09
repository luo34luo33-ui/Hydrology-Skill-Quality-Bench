"""Actual no-model container probes. Missing Docker is a failed receipt, never a pass."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.atomic_contracts import CONDITIONS, tree_digest
from harness.atomic_runtime import candidate_argv
from harness.reporter import write_json


def main():
    p = argparse.ArgumentParser(); p.add_argument('--lock', type=Path, required=True)
    p.add_argument('--output', type=Path, default=ROOT / 'docs/atomic-isolation-certification.json')
    args = p.parse_args(); lock = json.loads(args.lock.read_text(encoding='utf-8'))
    receipt = {'image_digest': lock.get('image_digest'), 'public_programs_sha256': lock.get('public_programs_sha256'),
               'clis': {}, 'real_agent_runs': 0, 'passed': False}
    network = 'hsqb-atomic-probe-' + uuid.uuid4().hex[:10]; created = False
    try:
        subprocess.run(['docker', 'network', 'create', '--internal', network], check=True, capture_output=True, timeout=20); created = True
        with tempfile.TemporaryDirectory(prefix='hsqb-atomic-isolation-') as temporary:
            root = Path(temporary); workspace = root / 'work'; workspace.mkdir()
            # Sentinel stays on the host, outside the only writable mount.
            secret = root / 'hidden_oracle_sentinel.txt'; secret.write_text('must remain hidden')
            other = root / 'other_workspace'; other.mkdir(); (other / 'secret.txt').write_text('unrelated')
            for cli, cfg in lock.get('clis', {}).items():
                evidence = {'version': cfg.get('version'), 'passed': False, 'checks': {}}
                for condition in CONDITIONS:
                    workspace = root / (cli + '-' + condition); workspace.mkdir()
                    (workspace / 'AGENTS.md').write_text('Identical no-model isolation fixture.\n')
                    argv = candidate_argv(lock, cli, condition, workspace, network, network + '-' + cli, 'unused')
                    argv = argv[:-5]  # Keep the frozen image; replace its Python script/arguments.
                    entries = [v['entrypoint'] for v in json.loads((Path(lock['public_programs_dir']) / 'programs.json').read_text()).values()]
                    def aliases(path):
                        s = path.as_posix()
                        return [s, '/host_mnt/' + s[0].lower() + s[2:], '/run/desktop/mnt/host/' + s[0].lower() + s[2:]] if len(s) > 1 and s[1] == ':' else [s]
                    code = '''import json,pathlib,socket,sys,runpy,os,hashlib
p=pathlib.Path
launch=[]
def capture(executable,argv):launch.extend(argv)
os.execvp=capture
sys.argv=['/opt/atomic_entrypoint.py',CLI,'isolation-probe-unused','provider-default','unused']
sys.path.insert(0,'/opt')
runpy.run_path('/opt/atomic_entrypoint.py',run_name='__main__')
network=False
try:
 socket.create_connection(('1.1.1.1',443),timeout=3).close();network=True
except OSError:pass
print(json.dumps({'programs':p('/work/public/programs.json').exists(),'skills':p('/home/agent/.agents/skills').exists(),
 'project_skills':p('/work/.agents/skills').exists(),'qwen_project_skills':p('/work/.qwen/skills').exists(),
 'initialized_launch':launch,'instructions_sha256':hashlib.sha256(p('/work/AGENTS.md').read_bytes()).hexdigest(),
 'baked_programs':[str(x) for root in ['/opt','/home/agent'] for x in p(root).rglob('*.py') if x.name in ENTRIES and '.agents/skills' not in str(x)],
 'host_hidden':any(p(x).exists() for x in HIDDEN),'host_other':any(p(x).exists() for x in OTHER),'external_network':network}))
'''.replace('HIDDEN', repr(aliases(secret))).replace('OTHER', repr(aliases(other / 'secret.txt'))).replace('ENTRIES', repr(entries)).replace('CLI', repr(cli))
                    command = argv + ['-c', code]
                    r = subprocess.run(command, capture_output=True, text=True, timeout=30)
                    if r.returncode: raise RuntimeError(cli + ' isolation probe failed: ' + r.stderr[-800:])
                    observed = json.loads(r.stdout.strip().splitlines()[-1])
                    tests = {'hidden_unreadable': not observed['host_hidden'], 'other_workspace_unreadable': not observed['host_other'],
                             'external_network_denied': not observed['external_network']}
                    if condition == 'no-skills': tests['baseline_programs_absent'] = not observed['programs'] and not observed['skills'] and not observed['baked_programs']
                    if condition == 'programs-only': tests['programs_only_skills_absent'] = observed['programs'] and not observed['skills']
                    if condition == 'with-skills': tests['with_skills_mounted'] = observed['programs'] and observed['skills'] and observed['project_skills'] and observed['qwen_project_skills']
                    tests['entrypoint_initialized'] = bool(observed['initialized_launch'])
                    for name, passed in tests.items():
                        previous = evidence['checks'].get(name, {'passed': True, 'evidence': []})
                        previous['passed'] = previous['passed'] and passed
                        previous['evidence'].append({'condition': condition, 'exit_code': r.returncode, 'observed': observed})
                        evidence['checks'][name] = previous
                evidence['passed'] = all(c['passed'] for c in evidence['checks'].values())
                hashes = {v['observed']['instructions_sha256'] for v in evidence['checks']['entrypoint_initialized']['evidence']}
                evidence['passed'] = evidence['passed'] and len(hashes) == 1
                evidence['instructions_identical'] = len(hashes) == 1
                evidence['native_skill_discovery'] = 'not tested; requires separate native CLI evidence'
                receipt['clis'][cli] = evidence
        receipt['passed'] = bool(receipt['clis']) and all(c['passed'] for c in receipt['clis'].values())
    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as exc:
        receipt['error'] = str(exc)
    finally:
        if created: subprocess.run(['docker', 'network', 'rm', network], capture_output=True, timeout=20)
        write_json(args.output, receipt)
    print(json.dumps({'passed': receipt['passed'], 'error': receipt.get('error')}))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
