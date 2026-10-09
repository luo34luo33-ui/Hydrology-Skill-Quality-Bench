import os
import json
from pathlib import Path
import sys

import pytest

from harness.atomic_contracts import stage_programs, tree_digest
from harness.filesystem import copy_tree, filesystem_path
from harness import runner
from tests_harness.test_atomic_three_arm import fixture_task


@pytest.mark.skipif(os.name != 'nt', reason='Windows MAX_PATH regression')
def test_long_public_program_paths_stage_and_archive(tmp_path):
    source = tmp_path/'bundle';source.mkdir()
    (source/'programs.json').write_text('{}')
    (source/'PROGRAM_INTERFACES.md').write_text('public interfaces')
    rel = Path('programs/visualization-reporting/generate-timeseries-data-processing-report/generate_timeseries_data_processing_report.py')
    file = source/rel;file.parent.mkdir(parents=True)
    file.write_text('print("fixture")\n')
    (source/'__pycache__').mkdir()
    (source/'__pycache__/fixture.pyc').write_bytes(b'ignored')
    (source/'fixture.pyc').write_bytes(b'ignored')
    # Keep the workspace short enough to create normally, but put the nested
    # public entrypoint beyond MAX_PATH just like the reported experiment.
    padding = max(1, 280-len(str(tmp_path/'workspace'/'public'/rel)))
    workspace = tmp_path/('w'*padding)/'workspace';workspace.mkdir(parents=True)
    assert len(str(workspace/'public'/rel)) >= 260
    assert stage_programs(source,workspace) == tree_digest(source)
    assert Path(filesystem_path(workspace/'public'/rel)).read_bytes() == file.read_bytes()
    assert not Path(filesystem_path(workspace/'public/__pycache__')).exists()
    assert not Path(filesystem_path(workspace/'public/fixture.pyc')).exists()
    with pytest.raises(ValueError,match='already exists'):
        stage_programs(source,workspace)
    archive = tmp_path/('a'*padding)/'archive'
    copy_tree(workspace,archive)
    assert Path(filesystem_path(archive/'public'/rel)).read_bytes() == file.read_bytes()


def test_internal_path_conversion_is_absolute_on_windows(tmp_path):
    converted=filesystem_path(tmp_path/'file.py')
    if os.name=='nt':
        assert converted.startswith('\\\\?\\')
        assert filesystem_path(converted)==converted
    else:
        assert converted==str(tmp_path/'file.py')


@pytest.mark.skipif(os.name != 'nt', reason='Windows CLI path regression')
def test_runner_executes_in_short_workspace_and_archives_to_requested_output(tmp_path,monkeypatch):
    folder,task=fixture_task(tmp_path)
    public=tmp_path/'bundle';public.mkdir()
    (public/'programs.json').write_text('{}')
    (public/'PROGRAM_INTERFACES.md').write_text('public interfaces')
    rel=Path('programs/visualization-reporting/generate-timeseries-data-processing-report/generate_timeseries_data_processing_report.py')
    program=public/rel;program.parent.mkdir(parents=True)
    program.write_text('print("executed")\n')
    agent=tmp_path/'agent.py'
    agent.write_text('import subprocess,sys,json,pathlib\n'
        f'r=subprocess.run([sys.executable,{str(Path("public")/rel)!r}],capture_output=True,text=True)\n'
        'assert r.returncode==0,r.stderr\n'
        'pathlib.Path("inspection.json").write_text(json.dumps({"cwd":str(pathlib.Path.cwd()),"program_executed":True}))\n')
    output=tmp_path/('o'*max(1,275-len(str(tmp_path/'tasks'/task['id']/'workspace/public'/rel))))
    monkeypatch.setattr(runner,'environment_metadata',lambda:{'fixture':True})
    result=runner.run_benchmark(tests_root=folder.parent.parent,agent_cmd=f'"{sys.executable}" "{agent}"',
        condition='programs-only',programs_path=public,output=output)
    work=output/'tasks'/task['id']/'workspace'
    inspection=json.loads((work/'inspection.json').read_text())
    assert inspection['program_executed']
    assert Path(inspection['cwd']) != work
    assert len(str(Path(inspection['cwd'])/'public'/rel)) < 260
    assert Path(filesystem_path(work/'public'/rel)).read_bytes()==program.read_bytes()
    assert result['results'][0]['execution']['return_code']==0
