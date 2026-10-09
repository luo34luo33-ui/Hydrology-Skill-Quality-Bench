"""Trusted closed scientific checks; never import candidate code or pickle."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from harness.composite_grader import child, get,resolved
from harness.source_references import verify_reference

def grade(c,workspace,test_dir):
    kind=c['check'];ok=False;details=kind
    if kind=='json_value':
        doc=json.loads(child(workspace,c['target']).read_text(encoding='utf-8'));ok=get(doc,c['field'])==c['expected']
    elif kind=='json_contract':
        from harness.grader import _contract_equal
        doc=json.loads(child(workspace,c['target']).read_text(encoding='utf-8'))
        expected=json.loads(child(test_dir,c['reference']).read_text(encoding='utf-8'))
        task_path=test_dir/'task.json'
        unattended=task_path.is_file() and json.loads(task_path.read_text(encoding='utf-8')).get('interaction_mode')=='none'
        if unattended:
            import re
            def semantic_equal(actual,reference):
                if isinstance(reference,dict):
                    return isinstance(actual,dict) and all(k in actual and semantic_equal(actual[k],v) for k,v in reference.items())
                if isinstance(reference,list):
                    return isinstance(actual,list) and len(actual)==len(reference) and all(semantic_equal(a,b) for a,b in zip(actual,reference))
                if isinstance(actual,str) and isinstance(reference,str) and re.match(r'^\d{4}-\d{2}-\d{2}T',reference):
                    try:
                        left,right=pd.Timestamp(actual),pd.Timestamp(reference)
                        if left.tzinfo is not None and right.tzinfo is not None:return left==right
                    except (ValueError,TypeError):pass
                return _contract_equal(actual,reference)
            ok=semantic_equal(doc,expected)
        else:ok=_contract_equal(doc,expected)
    elif kind=='manifest_integrity':
        import hashlib
        path=child(workspace,c['target']);doc=json.loads(path.read_text(encoding='utf-8'));checks=[]
        reference_base=doc.get('reference_base','manifest_parent')
        if reference_base not in {'workspace_root','manifest_parent'}:
            raise ValueError('unrecognized manifest reference base')
        base=resolved(workspace) if reference_base=='workspace_root' else path.parent
        def walk(value):
            if isinstance(value,dict):
                if isinstance(value.get('path'),str) and 'sha256' in value:
                    verify_reference(workspace,base,value,test_dir)
                    checks.append(True)
                for v in value.values():walk(v)
            elif isinstance(value,list):
                for v in value:walk(v)
        from pathlib import Path
        walk(doc)
        if not checks:raise ValueError('no hash-bound manifest evidence')
        ok=all(checks)
    elif kind=='nonnegative_finite':
        frame=pd.read_csv(child(workspace,c['target']));values=frame[c['columns']].to_numpy(float)
        ok=bool(len(frame) and np.isfinite(values).all() and (values>=-c.get('atol',1e-10)).all())
    elif kind=='scientific_axis_integrity':
        frame=pd.read_csv(child(workspace,c['target']))
        temporal=c['time_column'];raw=frame[temporal].astype(str)
        times=pd.to_datetime(raw,utc=True,errors='coerce')
        groups=[x for x in c.get('group_columns',[]) if x in frame]
        keyed=frame[groups].copy();keyed['_time']=times
        ordered=all(pd.to_datetime(part[temporal],utc=True).is_monotonic_increasing for _,part in frame.groupby(groups,dropna=False)) if groups else times.is_monotonic_increasing
        ok=bool(len(frame) and times.notna().all() and raw.str.contains(r'(?:Z|[+-]\d{2}:\d{2})$',regex=True).all() and not keyed.duplicated().any() and ordered)
    elif kind=='material_numeric_error':
        a=pd.read_csv(child(workspace,c['target']));b=pd.read_csv(child(test_dir,c['reference']))
        # Missing/incomplete tables do not alone prove a critical scientific error.
        if len(a)!=len(b):ok=True
        else:
            cols=c['columns'];av=a[cols].to_numpy(float);bv=b[cols].to_numpy(float)
            both=np.isfinite(bv);magnitude=c.get('atol',1e-3)+c.get('rtol',.01)*np.abs(bv)
            ok=not bool(np.any(both & (~np.isfinite(av) | (np.abs(av-bv)>magnitude))))
    elif kind=='component_balance':
        frame=pd.read_csv(child(workspace,c['target']))
        ok=bool(len(frame) and np.allclose(frame[c['total']],frame[c['parts']].sum(axis=1),rtol=c.get('rtol',1e-8),atol=c.get('atol',1e-8)))
    elif kind=='split_disjoint':
        frames=[pd.read_csv(child(workspace,p)) for p in c['targets']]
        sets=[]
        for f in frames:
            if 'scored' in f:f=f[f.scored.astype(str).str.lower().isin(['true','1'])]
            if 'is_warmup' in f:f=f[~f.is_warmup.astype(str).str.lower().isin(['true','1'])]
            sets.append(set(pd.to_datetime(f.time,utc=True)))
        ok=bool(all(sets) and not (sets[0]&sets[1]))
        if all('event_id' in f for f in frames):ok=ok and not (set(frames[0].event_id.astype(str))&set(frames[1].event_id.astype(str)))
        if c.get('expect_overlap'):ok=bool(sets[0]&sets[1])
    elif kind=='protected_sources':
        import hashlib
        reference=json.loads(child(test_dir,c['reference']).read_text(encoding='utf-8'))
        ok=all(child(workspace,rel).is_file() and hashlib.sha256(child(workspace,rel).read_bytes()).hexdigest()==digest for rel,digest in reference.items())
    elif kind=='missing_preservation':
        a=pd.read_csv(child(workspace,c['target']));b=pd.read_csv(child(test_dir,c['reference']))
        ok=len(a)==len(b) and all(np.array_equal(a[col].isna(),b[col].isna()) for col in c['columns'])
    elif kind=='same_series':
        left,right=[pd.read_csv(child(workspace,p)) for p in c['targets']]
        ok=len(left)==len(right) and np.allclose(left[c['column']],right[c['column']],rtol=1e-8,atol=1e-8)
    elif kind=='coverage':
        frame=pd.read_csv(child(workspace,c['target']));ok=bool(len(frame) and np.allclose(frame.coverage_fraction,1,rtol=0,atol=1e-7))
    elif kind=='decision_evidence':
        import hashlib
        doc=json.loads(child(workspace,c['target']).read_text(encoding='utf-8'));refs=doc.get('evidence',[])
        checks=[]
        for ref in refs:
            verify_reference(workspace,workspace,ref,test_dir);checks.append(True)
        ok=bool(checks) and all(checks) and bool(doc.get('limitations'))
    elif kind=='markdown_json_consistency':
        import re
        doc=json.loads(child(workspace,c['target']).read_text(encoding='utf-8'))
        blocks=re.findall(r'```json\s*(.*?)\s*```',child(workspace,c['markdown']).read_text(encoding='utf-8'),re.S)
        ok=bool(blocks) and all(json.loads(block)==doc for block in blocks)
    elif kind=='markdown_evidence_binding':
        import hashlib
        doc=json.loads(child(workspace,c['target']).read_text(encoding='utf-8'));text=child(workspace,c['markdown']).read_text(encoding='utf-8')
        ok=bool(doc.get('evidence')) and all(ref['path'] in text and hashlib.sha256(child(workspace,ref['path']).read_bytes()).hexdigest() in text for ref in doc['evidence'])
    elif kind=='routing_stability_recompute':
        scenario=json.loads(child(workspace,c['source']).read_text(encoding='utf-8'));config=scenario['semi_parameters'];ke=config['xaj']['KE'];xe=config['xaj']['XE'];dt=config['time']['step_seconds']/3600;den=ke*(1-xe)+.5*dt
        expected=[(.5*dt-ke*xe)/den,(.5*dt+ke*xe)/den,(ke*(1-xe)-.5*dt)/den]
        doc=json.loads(child(workspace,c['target']).read_text(encoding='utf-8'));ok=bool(np.allclose(doc['coefficients'],expected,atol=1e-12,rtol=1e-12) and doc['stable'] is (min(expected)>=0) and doc['parameter_change_authorized'] is False)
    elif kind=='readiness_recompute':
        raw=pd.read_csv(child(workspace,c['source']));doc=json.loads(child(workspace,c['target']).read_text(encoding='utf-8'))
        missing=raw[c['column']].isna();ok=bool(doc['rain_missing_count']==int(missing.sum()) and doc['missing_times']==raw.loc[missing,'time'].tolist() and doc['ready'] is (not bool(missing.any())) and doc['repair_authorized'] is False)
    elif kind=='split_audit_recompute':
        a,b=[pd.read_csv(child(workspace,p)) for p in c['targets']];overlap=sorted(set(pd.to_datetime(a.loc[a.scored,'time'],utc=True))&set(pd.to_datetime(b.loc[b.scored,'time'],utc=True)))
        independent=bool(a.scored.any() and b.scored.any() and not overlap)
        doc=json.loads(child(workspace,c['target']).read_text(encoding='utf-8'));ok=bool(doc['overlap_count']==len(overlap) and doc['overlap_times']==[t.isoformat() for t in overlap] and doc['review_pass'] is independent and doc['validation_independent'] is independent)
    elif kind=='metric_recompute':
        f=pd.read_csv(child(workspace,c['series']));m=pd.read_csv(child(workspace,c['target'])).set_index('metric').value
        o=f[c.get('observed','observed_m3_s')].to_numpy(float);s=f[c.get('simulated','simulated_m3_s')].to_numpy(float)
        expected={'rmse':float(np.sqrt(np.mean((s-o)**2))),'mae':float(np.mean(np.abs(s-o))),'volume_bias':float(np.sum(s-o)*c.get('step_seconds',3600)),'nse':float(1-np.sum((s-o)**2)/np.sum((o-o.mean())**2))}
        ok=bool(len(o) and all(np.isclose(m[k],v,atol=1e-6,rtol=1e-7) for k,v in expected.items()))
    elif kind=='event_metrics_recompute':
        f=pd.read_csv(child(workspace,c['series']));m=pd.read_csv(child(workspace,c['target'])).set_index('event_id');checks=[]
        for identity,frame in f.groupby('event_id'):
            row=m.loc[str(identity)] if str(identity) in m.index else m.loc[identity]
            o=frame.observed_m3_s.to_numpy();s=frame.simulated_m3_s.to_numpy()
            values={'rmse':np.sqrt(np.mean((s-o)**2)),'mae':np.mean(np.abs(s-o)),'nse':1-np.sum((s-o)**2)/np.sum((o-o.mean())**2),'observed_volume':o.sum()*3600,'simulated_volume':s.sum()*3600,'observed_peak':o.max(),'simulated_peak':s.max()}
            checks.extend(np.isclose(row[k],v,atol=1e-6,rtol=1e-7) for k,v in values.items())
        ok=bool(checks) and all(checks) and len(m)==f.event_id.nunique()
    elif kind=='event_summary_recompute':
        f=pd.read_csv(child(workspace,c['series']));summary=pd.read_csv(child(workspace,c['target']));checks=[len(summary)==1]
        if len(summary)==1:
            row=summary.iloc[0]
            for col in summary.columns:
                if col in ['group','events']:continue
                metric,stat=col.rsplit('_',1);values=pd.to_numeric(f[metric],errors='coerce').dropna()
                val={'mean':values.mean(),'median':values.median(),'min':values.min(),'max':values.max(),'count':len(values),'p10':values.quantile(.1),'p90':values.quantile(.9)}[stat]
                checks.append(np.isclose(row[col],val,atol=1e-6,rtol=1e-7))
            checks.append(row.events==len(f))
        ok=all(checks)
    elif kind=='bma_replay':
        from scipy.stats import norm
        from scipy.special import logsumexp
        model=json.loads(child(workspace,'fit/bma_model.json').read_text(encoding='utf-8'));ids=model['model_ids'];theta=np.asarray(model['theta'],float);weights=np.asarray(model['weights'],float);scale=float(model['scale_m3_s'])
        checks=[set(ids)=={'dhf','semi'},theta.shape==(2,3),np.isclose(weights.sum(),1),bool((weights>=0).all())]
        train=[];full={}
        for name in ids:
            f=pd.read_csv(child(workspace,'aligned-'+name+'/evaluation_discharge.csv'));f.time=pd.to_datetime(f.time,utc=True);full[name]=f
            a=f[(f.time>=pd.Timestamp('2023-08-01T04:00:00Z'))&(f.time<=pd.Timestamp('2023-08-20T15:00:00Z'))];train.append(a)
        checks.extend([pd.Timestamp(model['training_start'])==pd.Timestamp('2023-08-01T04:00:00Z'),pd.Timestamp(model['training_end'])==pd.Timestamp('2023-08-20T15:00:00Z'),len(train[0])==468])
        y=train[0].observed_m3_s.to_numpy()/scale
        logs=np.column_stack([np.where(y==0,norm.logcdf(-(theta[j,0]+theta[j,1]*train[j].simulated_m3_s.to_numpy()/scale)/theta[j,2]),norm.logpdf(y,theta[j,0]+theta[j,1]*train[j].simulated_m3_s.to_numpy()/scale,theta[j,2])) for j in range(2)])
        likelihood=float(logsumexp(logs+np.log(np.maximum(weights,np.finfo(float).tiny)),axis=1).mean())
        checks.append(np.isclose(likelihood,model['score'],atol=1e-6,rtol=1e-6))
        components=pd.read_csv(child(workspace,'forecast/component_predictions.csv'));components.time=pd.to_datetime(components.time,utc=True)
        for j,name in enumerate(ids):
            part=components[components.model_id==name];joined=part.merge(full[name][['time','simulated_m3_s']],on='time',suffixes=('','_source'),validate='one_to_one')
            checks.extend([len(joined)==264,np.allclose(joined.simulated_m3_s,joined.simulated_m3_s_source,atol=1e-6,rtol=1e-6),np.allclose(joined.corrected_center_m3_s,theta[j,0]*scale+theta[j,1]*joined.simulated_m3_s,atol=1e-6,rtol=1e-6),np.allclose(joined.sigma_m3_s,theta[j,2]*scale,atol=1e-6,rtol=1e-6),np.allclose(joined.weight,weights[j],atol=1e-8)])
        evaluation=pd.read_csv(child(workspace,'evaluation.csv'));forecast=pd.read_csv(child(workspace,'forecast/ensemble_discharge.csv'));evaluation.time=pd.to_datetime(evaluation.time,utc=True);forecast.time=pd.to_datetime(forecast.time,utc=True)
        joined=evaluation.merge(forecast[['time','ensemble_mean_m3_s']],on='time',validate='one_to_one').merge(full[ids[0]][['time','observed_m3_s']],on='time',suffixes=('','_source'),validate='one_to_one')
        checks.extend([len(joined)==264,np.allclose(joined.simulated_m3_s,joined.ensemble_mean_m3_s,atol=1e-6),np.allclose(joined.observed_m3_s,joined.observed_m3_s_source,atol=1e-6)])
        diagnostics=json.loads(child(workspace,'fit/fit_diagnostics.json').read_text(encoding='utf-8'))
        checks.append(any(x['converged'] and np.isclose(x['mean_loglik_normalized'],likelihood,atol=1e-6) and x['iterations']<=2000 for x in diagnostics['starts']))
        ok=all(checks)
    elif kind=='calibration_replay':
        from harness.calibration_replay import check
        ok,details=check(c,workspace,test_dir)
    elif kind=='controlled_claims':
        actual=json.loads(child(workspace,c['target']).read_text(encoding='utf-8'))
        expected=json.loads(child(test_dir,c['reference']).read_text(encoding='utf-8'))
        ok=all(actual.get(k)==v for k,v in expected.items())
    else:raise ValueError('unknown scientific check '+kind)
    return {'score':float(ok),'raw_value':bool(ok),'details':details}
