"""Close reports after the existing dispatcher and recovery stop; launch no Agents."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.overnight import atomic_json,keep_awake,latest_records,run_guard,write_reports


def process_alive(pid):
    if os.name=='nt':
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.OpenProcess(0x1000,False,int(pid))
        if not handle:
            if ctypes.get_last_error()==87:return False
            raise OSError(ctypes.get_last_error(),'Cannot inspect dispatcher process')
        try:
            code=ctypes.c_ulong()
            if not kernel.GetExitCodeProcess(handle,ctypes.byref(code)):raise OSError('Cannot inspect dispatcher state')
            return code.value==259
        finally:kernel.CloseHandle(handle)
    try:os.kill(int(pid),0);return True
    except ProcessLookupError:return False


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='results/composite-unattended-v2-r4')
    args=parser.parse_args();root=(ROOT/args.output).resolve();root.relative_to(ROOT)
    receipt=root/'finalization.json'
    with run_guard(root/'finalization'),keep_awake():
        atomic_json(receipt,{'state':'waiting_for_existing_runs','launches_agents':False})
        while True:
            state=json.loads((root/'dispatcher.json').read_text(encoding='utf-8'))
            recoveries=[json.loads(p.read_text(encoding='utf-8')) for p in root.glob('recovery-*.json')]
            if not process_alive(state['pid']) and not any(r['state']=='running' for r in recoveries):break
            time.sleep(15)
        with run_guard(root):
            schedule=json.loads((root/'schedule.json').read_text(encoding='utf-8'))
            if schedule.get('task_revision')!=4 or schedule.get('interaction_mode')!='none':raise ValueError('Wrong frozen task revision')
            for pair in schedule['pairs']:
                rows,_,complete,_=latest_records(root,[pair])
                if complete:
                    state['pairs'][pair['pair_id']].update(status='completed',attempt=max(r['attempt'] for r in rows))
                elif len(rows)==2 and not all(r.get('eligible',False) for r in rows):
                    state['pairs'][pair['pair_id']].update(status='infrastructure_failed',attempt=max(r['attempt'] for r in rows))
            atomic_json(root/'dispatcher.json',state)
            report=write_reports(root,schedule['pairs'])
            for script,extra in [
                ('audit_composite_unattended.py',['--runs-dir',args.output]),
                ('review_unattended_runs.py',['--runs-dir',args.output]),
                ('write_composite_delivery.py',['--pytest-passed','275'])]:
                result=subprocess.run([sys.executable,str(ROOT/'scripts'/script),*extra],cwd=ROOT,
                    capture_output=True,text=True)
                print(script,result.returncode,result.stdout.strip(),flush=True)
                if result.returncode:raise RuntimeError('Final evidence refresh failed: '+script)
            eligible=sum(bool(r.get('eligible',False)) for r in latest_records(root,schedule['pairs'])[0])
            atomic_json(receipt,{'state':'completed' if eligible==144 else 'incomplete_validation',
                'launches_agents':False,'eligible_runs':eligible,'planned_runs':144,
                'completed_pairs':report['completed_pairs'],
                'note':'Reference success is independent evidence; pending or unavailable runs remain incomplete.'})


if __name__=='__main__':main()
