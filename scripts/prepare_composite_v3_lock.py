"""Create an intentionally unusable v3 lock pending fresh runtime certification."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.filesystem import filesystem_path
from harness.reporter import write_json
from harness.source_references import SCORING_VERSION


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',default='runtime/experiment.unattended-v2.lock.json')
    p.add_argument('--output',default='runtime/experiment.unattended-v3.pending.lock.json')
    p.add_argument('--image-digest',default='');a=p.parse_args()
    source=Path(filesystem_path(a.source)).resolve();output=Path(filesystem_path(a.output)).resolve()
    if source==output or output.exists():raise ValueError('Preserve source lock and create a fresh output path')
    lock=json.loads(source.read_text(encoding='utf-8'))
    lock.update(status='awaiting_v3_live_certification',task_revision=5,
        scoring_version=SCORING_VERSION,isolated_network_certified=False,image_digest='',
        host_runtime_sha256='',relay_sha256='',certifications={})
    lock['image_digest']=a.image_digest
    lock['certified_clis']=[]
    lock['required_skill_certification']='native-skill-v3'
    for config in lock.get('clis',{}).values():config['budget_audit_certified']=False
    write_json(output,lock)
    print(output)


if __name__=='__main__':main()
