"""Replay candidate parameters with trusted immutable inputs and a trusted physical adapter."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from harness.composite_grader import child

def check(c,workspace,test_dir):
    from runtime.public.physical_calibration import create_evaluator
    base=child(test_dir,c['input_base']);problem=json.loads((base/'problem.json').read_text(encoding='utf-8'))
    doc=json.loads(child(workspace,c['target']).read_text(encoding='utf-8'))
    params={k:float(v['value']) for k,v in doc['parameters'].items()}
    if set(params)!={x['name'] for x in problem['parameters']}:return False,'parameter names'
    if any(not x['lower']<=params[x['name']]<=x['upper'] for x in problem['parameters']):return False,'parameter bounds'
    evaluator=create_evaluator(problem,base)
    for split in ['calibration','validation']:
        expected=evaluator.materialize(params,split)['series'];actual=pd.read_csv(child(workspace,f'calibration/{split}_series.csv'))
        if len(expected)!=len(actual):return False,'series length'
        for col in ['observed','simulated']:
            if not np.allclose(expected[col],actual[col],atol=1e-7,rtol=1e-7):return False,'physical replay '+col
        if not np.array_equal(expected.scored,actual.scored):return False,'scoring mask'
        if not (pd.to_datetime(expected.time,utc=True).to_numpy()==pd.to_datetime(actual.time,utc=True).to_numpy()).all():return False,'time'
        if 'event_id' in expected and expected.event_id.tolist()!=actual.event_id.astype(str).tolist():return False,'event isolation'
    trace=pd.read_csv(child(workspace,'calibration/calibration_trace.csv'))
    if not 0<len(trace)<=128:return False,'objective budget'
    successful=[]
    for row in trace.to_dict('records'):
        if row['status']!='success':continue
        trial={k:float(row['param:'+k]) for k in params}
        physical=evaluator.evaluate(trial,'calibration')['objective']
        if not np.isclose(physical,float(row['objective']),rtol=1e-7,atol=1e-7):return False,'objective trace does not replay'
        successful.append(physical)
    best=evaluator.materialize(params,'calibration')['objective']
    if not successful or not np.isclose(best,min(successful),rtol=1e-7,atol=1e-7):return False,'best parameter lock'
    return True,'physical replay, trace and objective budget'
