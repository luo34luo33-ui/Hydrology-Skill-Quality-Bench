"""Windows path regressions across arms/CLIs; no model calls or credentials."""
import json
import os
from pathlib import Path
import sys

import pytest

from harness import runner, reporter
from harness.atomic_contracts import tree_digest
from harness.filesystem import filesystem_path, normal_path, execution_workspace, copy_tree
from tests_harness.test_atomic_three_arm import fixture_task

pytestmark=pytest.mark.skipif(os.name!='nt',reason='Windows long path matrix')


def setup_case(tmp_path,monkeypatch):
    folder,task=fixture_task(tmp_path)
    incoming='input/'+('i'*70)+'/'+('j'*55)+'.txt'
    outgoing='output/'+('o'*70)+'/'+('p'*55)+'.txt'
    path=Path(filesystem_path(folder/'data'/incoming));path.parent.mkdir(parents=True)
    path.write_text('original-data')
    task.update(data_files=[incoming],required_outputs=[outgoing],
        grading=[{'name':'delivered','type':'file_check','target':outgoing,'weight':1.0}])
    reporter.write_json(folder/'task.json',task)
    public=tmp_path/'programs';public.mkdir()
    (public/'programs.json').write_text('{}');(public/'PROGRAM_INTERFACES.md').write_text('interfaces')
    skills=tmp_path/'skills';skill=skills/('skill-'+'s'*40);skill.mkdir(parents=True)
    (skill/'SKILL.md').write_text('---\nname: fixture\ndescription: test\n---\n')
    (skill/('helper-'+'h'*40+'.py')).write_text('fixture=1')
    output=tmp_path/('results-'+'r'*100)
    workspace_root=tmp_path/('custom-'+'c'*100)
    agent=tmp_path/'fake_agent.py'
    agent.write_text('import os,sys,json,pathlib\n'
        f'sys.path.insert(0,{str(Path.cwd())!r})\n'
        'from harness.agent_wrapper import install_skill_snapshot\n'
        'from harness.filesystem import copy_tree\n'
        'w=pathlib.Path.cwd();t=json.loads(pathlib.Path(os.environ["HSQB_TASK_JSON"]).read_text())\n'
        'assert (w/t["data_files"][0]).read_text()=="original-data"\n'
        'if os.environ.get("BENCHMARK_SKILLS_PATH"):\n'
        ' install_skill_snapshot(os.environ["BENCHMARK_SKILLS_PATH"],w)\n'
        ' copy_tree(w/".agents/skills",w/".qwen/skills")\n'
        ' copy_tree(w/".agents/skills",w/".codebuddy/skills")\n'
        'p=w/t["required_outputs"][0];p.parent.mkdir(parents=True);p.write_text("computed")\n')
    monkeypatch.setattr(runner,'environment_metadata',lambda:{'test':True})
    return folder,task,public,skills,output,workspace_root,agent


@pytest.mark.parametrize('condition',['no-skills','programs-only','with-skills','legacy-no-skills','legacy-with-skills'])
@pytest.mark.parametrize('custom_root',[False,True])
def test_atomic_local_all_arms_and_custom_roots(tmp_path,monkeypatch,condition,custom_root):
    folder,task,public,skills,output,custom,agent=setup_case(tmp_path,monkeypatch)
    has_skills=condition in ['with-skills','legacy-with-skills']
    legacy=condition.startswith('legacy-')
    result=runner.run_benchmark(tests_root=folder.parent.parent,condition=None if legacy else condition,
        skills_path=skills if has_skills else None,programs_path=public if condition in ['programs-only','with-skills'] else None,
        agent_cmd=f'"{sys.executable}" "{agent}"',workspace_root=custom if custom_root else None,output=output)
    assert result['results'][0]['score']==1
    root=Path(filesystem_path(output/'tasks'/task['id']/'workspace'))
    assert len(str(normal_path(root/task['required_outputs'][0])))>=260
    assert (root/task['required_outputs'][0]).read_text()=='computed'
    assert (root/'.agents/skills').exists()==has_skills
    if has_skills:
        for mirror in ['.qwen/skills','.codebuddy/skills']:
            assert len(list((root/mirror).rglob('SKILL.md')))==1
    execution=json.loads((root.parent/'execution.json').read_text())
    assert len(execution['live_workspace'])+1+len(task['required_outputs'][0])<240
    if custom_root:assert execution['requested_workspace']==str(custom/task['id'])


@pytest.mark.parametrize('cli',['codex','opencode','qwen','codebuddy'])
@pytest.mark.parametrize('condition',['no-skills','programs-only','with-skills'])
def test_atomic_isolated_all_cli_arms(tmp_path,monkeypatch,cli,condition):
    import harness.atomic_runtime as runtime
    folder,task,public,skills,output,custom,_=setup_case(tmp_path,monkeypatch)
    lockfile=tmp_path/'lock.json';lockfile.write_text('{}')
    lock={'image_digest':'sha256:test','common_config_dir':str(tmp_path),'public_programs_dir':str(public),
        'skills_dir':str(skills),'public_programs_sha256':tree_digest(public),'skills_sha256':tree_digest(skills),
        'clis':{cli:{'model':'fixture','effort':'default','version':'test','config_sha256':'test'}}}
    monkeypatch.setattr(runtime,'preflight',lambda *a:{'ready':True})
    monkeypatch.setattr(runtime,'load_lock',lambda *a:lock)
    def execute(task,workspace,output,lock,cli,condition,root):
        argv=runtime.candidate_argv(lock,cli,condition,Path(filesystem_path(workspace)),'internal','candidate','test')
        mounts=[argv[i+1] for i,v in enumerate(argv) if v=='--mount']
        assert all('\\\\?\\' not in m for m in mounts)
        assert any('target=/work/public' in m for m in mounts)==(condition!='no-skills')
        assert any('target=/home/agent/.agents/skills' in m for m in mounts)==(condition=='with-skills')
        assert (workspace/task['data_files'][0]).read_text()=='original-data'
        p=workspace/task['required_outputs'][0];p.parent.mkdir(parents=True);p.write_text('computed')
        return {'return_code':0,'timed_out':False}
    monkeypatch.setattr(runtime,'run_isolated_atomic',execute)
    result=runner.run_benchmark(tests_root=folder.parent.parent,condition=condition,runtime='isolated',
        runtime_lock=lockfile,atomic_cli=cli,programs_path=public if condition!='no-skills' else None,
        skills_path=skills if condition=='with-skills' else None,workspace_root=custom,output=output)
    assert result['results'][0]['score']==1


@pytest.mark.parametrize('cli',['codex','opencode','qwen'])
@pytest.mark.parametrize('skilled',[False,True])
def test_composite_all_cli_arms(tmp_path,monkeypatch,cli,skilled):
    import harness.composite_runtime as runtime
    from harness.isolated_runtime import candidate_argv
    folder,task,public,skills,output,custom,_=setup_case(tmp_path,monkeypatch)
    task.pop('public_contract')
    task.update(task_kind='composite',task_version='composite-unattended-v2',task_revision=4,
        interaction_mode='none',outcome_goal='deliverable',evaluation_reference='expected/evaluation.json')
    reporter.write_json(folder/'expected/evaluation.json',{'task_version':task['task_version'],
        'gates':[],'dependencies':[],'provided_settings':[],'critical_rules':[]})
    monkeypatch.setattr(runner,'validate_tests',lambda *a:[])
    monkeypatch.setattr(runner,'discover_tasks',lambda *a:[{'task':task,'task_dir':folder,'task_path':folder/'task.json'}])
    lockfile=tmp_path/'lock.json';lockfile.write_text('{}')
    lock={'image_digest':'sha256:test','common_config_dir':str(tmp_path),'skills_dir':str(skills),
        'common_config_sha256':'test','public_programs_sha256':'test','skills_sha256':'test',
        'clis':{cli:{'model':'fixture','effort':'default','version':'test','config_sha256':'test'}}}
    monkeypatch.setattr(runtime,'preflight',lambda *a:{'ready':True})
    monkeypatch.setattr(runtime,'load_lock',lambda *a:lock)
    def execute(task,workspace,task_dir,output,lockfile,cli,condition,project):
        argv=candidate_argv(lock,cli,condition,Path(filesystem_path(workspace)),public,tmp_path,'internal','candidate',None,'test')
        mounts=[argv[i+1] for i,v in enumerate(argv) if v=='--mount']
        assert all('\\\\?\\' not in m for m in mounts)
        assert any('target=/home/agent/.agents/skills' in m for m in mounts)==skilled
        assert (workspace/task['data_files'][0]).read_text()=='original-data'
        p=workspace/task['required_outputs'][0];p.parent.mkdir(parents=True);p.write_text('computed')
        return {'return_code':0,'timed_out':False,'eligible':True,'duration_seconds':.01},[]
    monkeypatch.setattr(runtime,'run',execute)
    result=runner.run_benchmark(tests_root=folder.parent.parent,suite='composite',runtime_lock=lockfile,
        composite_cli=cli,skills_path=skills if skilled else None,workspace_root=custom,output=output)
    assert result['results'][0]['task_success']


def test_path_containment_still_rejects_escape_and_long_skill_copy_works(tmp_path):
    from harness.composite_grader import child
    from harness.agent_wrapper import install_skill_snapshot
    workspace=tmp_path/('w'*100);workspace.mkdir()
    with pytest.raises(ValueError):child(workspace,'../outside.txt')
    source=tmp_path/'skills';skill=source/('s'*60);skill.mkdir(parents=True)
    (skill/'SKILL.md').write_text('fixture')
    nested=skill/('n'*50)/('h'*50+'.py')
    extended_nested=Path(filesystem_path(nested))
    extended_nested.parent.mkdir();extended_nested.write_text('fixture')
    install_skill_snapshot(str(source),workspace)
    target=Path(filesystem_path(workspace/'.agents/skills'/nested.relative_to(source)))
    assert len(str(normal_path(target)))>=260
    assert target.read_text()=='fixture'
    copy_tree(workspace/'.agents/skills',workspace/'.qwen/skills')
    assert Path(filesystem_path(workspace/'.qwen/skills'/nested.relative_to(source))).is_file()
