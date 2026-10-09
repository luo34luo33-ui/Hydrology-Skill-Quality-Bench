"""All-gates scientific grading and host-audited confirmation accounting."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from harness.filesystem import filesystem_path
from harness.source_references import verify_reference, SourceReferenceError, SCORING_VERSION

def resolved(path):
    value=os.path.normcase(str(Path(path).resolve()))
    if value.startswith('\\\\?\\UNC\\'):value='\\\\'+value[8:]
    elif value.startswith('\\\\?\\'):value=value[4:]
    return Path(filesystem_path(value))

def child(root, rel):
    path=resolved(Path(root)/rel);path.relative_to(resolved(root));return path

def get(document,field):
    value=document
    for part in field.split('.'):
        value=value[int(part)] if isinstance(value,list) else value[part]
    return value

def binding(workspace,spec):
    value=json.loads(child(workspace,spec['target']).read_text(encoding='utf-8'))
    return get(value,spec['field'])==spec['expected']

def evaluate(task,workspace,test_dir,audit_events=None):
    from harness.grader import grade_criterion
    reference=json.loads(child(test_dir,task['evaluation_reference']).read_text(encoding='utf-8'))
    unattended=task.get('interaction_mode')=='none'
    if unattended and (reference.get('task_version')!=task.get('task_version') or reference.get('confirmations')):
        raise ValueError('incompatible unattended evaluation contract')
    events=audit_events or []
    gates=[];errors=[];observed=0;unassessable=False
    for gate in reference['gates']:
        if gate.get('optional_after_block') and not any(child(workspace,p).exists() for p in gate.get('evidence',[])):
            gates.append({'id':gate['id'],'passed':True,'observed':True,'not_required_after_verified_block':True});observed+=1;continue
        values=[grade_criterion(c,Path(workspace),Path(test_dir)) for c in gate['criteria']]
        unassessable=unassessable or any(v['details'].startswith('grading error:') or v.get('diagnostic_type') for v in values)
        passed=bool(values) and all(v['score']>=1-1e-12 for v in values)
        evidence=any(child(workspace,p).is_file() for p in gate.get('evidence',[]))
        observed+=evidence
        gates.append({'id':gate['id'],'passed':passed,'observed':evidence,'criteria':values})
    for dependency in reference.get('dependencies',[]):
        if dependency.get('optional_after_block') and not child(workspace,dependency['downstream']).exists():continue
        try:
            downstream=child(workspace,dependency['downstream']);upstream=child(workspace,dependency['upstream'])
            doc=json.loads(downstream.read_text(encoding='utf-8'));ref=get(doc,dependency['field'])
            actual=verify_reference(workspace,downstream.parent,ref,test_dir)
            if unattended:
                # Equivalent implementations may name derived inputs differently.
                passed=actual.is_file() and ref['sha256']==hashlib.sha256(actual.read_bytes()).hexdigest()
                if dependency['upstream'] in task['data_files']:
                    passed=passed and actual==resolved(upstream)
            else:passed=actual==resolved(upstream) and ref['sha256']==hashlib.sha256(upstream.read_bytes()).hexdigest()
            diagnostic=None
        except SourceReferenceError as exc:passed=False;unassessable=True;diagnostic=exc.code
        except (OSError,KeyError,ValueError,TypeError,IndexError):passed=False;unassessable=True;diagnostic='missing_evidence'
        gates.append({'id':dependency['id'],'passed':passed,'observed':child(workspace,dependency['downstream']).is_file(),'diagnostic_type':diagnostic})
    for rule in reference.get('critical_rules',[]):
        result=grade_criterion(rule['criterion'],Path(workspace),Path(test_dir))
        # Absent evidence is unknown, never an automatic scientific error.
        present=all(child(workspace,p).is_file() for p in rule['requires'])
        evaluable=present and not result['details'].startswith('grading error:') and not result.get('diagnostic_type')
        if present and not evaluable:unassessable=True
        if not present and task['outcome_goal']!='blocked':unassessable=True
        if evaluable and result['score']<1-1e-12:errors.append({'code':rule['code'],'details':result['details']})
    confirmations=[]
    for item in reference.get('confirmations',[]):
        requests=[e for e in events if e.get('kind')=='confirmation' and e.get('key')==item['key'] and e.get('answer')==item['answer']]
        artifacts=[e for e in events if e.get('kind')=='artifact' and e.get('path') in item.get('before_artifacts',[])]
        timely=bool(requests and artifacts and min(e['time_ns'] for e in requests)<min(e['time_ns'] for e in artifacts))
        try:implemented=bool(item.get('bindings')) and all(binding(workspace,b) for b in item['bindings'])
        except (OSError,ValueError,KeyError,TypeError,IndexError):implemented=False
        confirmations.append({'key':item['key'],'asked':bool(requests),'timely':timely,'implemented':implemented,'passed':timely and implemented})
    settings=[]
    for item in reference.get('provided_settings',[]):
        try:
            declared=get(json.loads(child(workspace,item['source']).read_text(encoding='utf-8')),item['field'])
            passed=bool(item.get('bindings')) and all(declared==b['expected'] and binding(workspace,b) for b in item['bindings'])
        except (OSError,ValueError,KeyError,TypeError,IndexError):passed=False
        settings.append({'key':item['key'],'passed':passed})
    output_checks=[]
    for rel in task['required_outputs']:output_checks.append(child(workspace,rel).is_file())
    for rel in reference.get('forbidden_outputs',[]):
        if child(workspace,rel).exists():
            errors.append({'code':'continued_after_scientific_block','details':rel});output_checks.append(False)
    result={'task_kind':'composite','outcome_goal':task['outcome_goal'],'task_success':all(g['passed'] for g in gates) and all(c['passed'] for c in confirmations) and all(c['passed'] for c in settings) and all(output_checks) and not errors,'critical_errors':errors,'assessability':'assessed' if observed>=len(reference['gates']) and not unassessable else 'insufficient_evidence','scientific_gates':gates}
    result['scoring_version']=SCORING_VERSION
    result['source_errors']=[{'gate':g['id'],'code':c['diagnostic_type']} for g in gates for c in g.get('criteria',[]) if c.get('diagnostic_type')]+[{'gate':g['id'],'code':g['diagnostic_type']} for g in gates if g.get('diagnostic_type')]
    if unattended:result.update(task_version=task['task_version'],task_revision=task.get('task_revision',1),interaction_mode='none',provided_setting_results=settings)
    else:result['confirmation_results']=confirmations
    return result

def criterion(criterion,workspace,test_dir):
    reference=child(test_dir,criterion['reference'])
    spec=json.loads(reference.read_text(encoding='utf-8'))
    from harness.grader import grade_criterion
    items=[grade_criterion(c,workspace,test_dir) for g in spec['gates'] for c in g['criteria']]
    score=sum(x['score'] for x in items)/len(items) if items else 0.
    return {'raw_value':score,'score':score,'details':'Scientific artifact progress; task_success separately requires every gate and correctly applied supplied settings.'}
