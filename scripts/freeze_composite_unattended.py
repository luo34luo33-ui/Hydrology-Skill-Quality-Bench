"""Prepare a v2 runtime lock without borrowing old live certifications."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.runner import _sha256_tree
from harness.reporter import write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',default='runtime/experiment.lock.json')
    parser.add_argument('--output',default='runtime/experiment.unattended-v2.lock.json')
    args=parser.parse_args()
    if Path(args.source).resolve()==Path(args.output).resolve():raise ValueError('Preserve the old lock; use a new output path')
    lock=json.loads(Path(args.source).read_text(encoding='utf-8'))
    lock.update(experiment_version='composite-unattended-v2',interaction_mode='none',
        repetitions=1,status='awaiting_unattended_live_certification',
        runtime_mode='isolated-relay',isolated_network_certified=False,certifications={})
    lock['public_programs_sha256']=_sha256_tree(ROOT/'runtime/public')
    lock['skills_sha256']=_sha256_tree(ROOT/'runtime/skills')
    lock['skills_dir']=str((ROOT/'runtime/skills').resolve())
    lock['host_runtime_sha256']=_sha256_tree(ROOT/'harness')
    for cfg in lock['clis'].values():cfg['budget_audit_certified']=False
    write_json(args.output,lock)
    print('Prepared unattended v2 lock; live certification is still required.')


if __name__=='__main__':main()
