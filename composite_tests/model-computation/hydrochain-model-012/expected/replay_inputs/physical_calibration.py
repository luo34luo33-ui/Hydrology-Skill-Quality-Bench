"""General physical XAJ + Muskingum evaluation adapter. No preset split or fit solution."""
from pathlib import Path
import importlib.util
import json
import os
import sys
import numpy as np
import pandas as pd

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m

class Evaluator:
    def __init__(self,problem,base):
        self.problem=problem;self.base=Path(base)
        public=Path(os.environ.get('HSQB_PUBLIC_PROGRAMS',Path(__file__).resolve().parent))
        self.xaj=module('physical_lumped_xaj',public/'programs/hydrological-modeling/run-lumped-xaj-model/_xaj_core.py')
        self.route=module('physical_muskingum',public/'programs/hydrological-modeling/route-muskingum-channel/_muskingum_core.py')
        self.frames={item['id']:pd.read_csv(self.base/item['path']) for item in problem['inputs'] if item['id']!='fixed'}
        fixed=next(x for x in problem['inputs'] if x['id']=='fixed')
        self.fixed=json.loads((self.base/fixed['path']).read_text(encoding='utf-8'))
    def materialize(self,params,split):
        fixed=self.fixed;par={**fixed['parameters'],**params};frames=[]
        # Continuous state is propagated over the full record; scoring masks alone split it.
        ids=self.problem['splits'][split]['events'] if self.problem['data_shape']=='event_collection' else ['continuous']
        for identity in ids:
            f=self.frames[identity];p=self.xaj.build_parameters(par)
            result=self.xaj.run_lumped_xaj(f.P.to_numpy(float),f.E0.to_numpy(float),p,fixed['area_km2'],fixed['step_hours'])
            if any(not np.isfinite(v).all() for v in result.values()):raise ValueError('nonfinite physical state')
            start=fixed['warmup_steps'];soil_start=float(result['W'][start-1]) if start else p.wum_init+p.wlm_init+min(p.wdm_init,p.wdm)
            residual=abs(np.sum(result['P_perv'][start:])-np.sum(result['E'][start:])-np.sum(result['R'][start:])-(result['W'][-1]-soil_start))
            if residual/max(np.sum(result['P_perv'][start:]),1e-9)>1e-3:raise ValueError('native water-balance tolerance failed')
            if any(not np.isfinite(v).all() for v in result.values()):raise ValueError('nonfinite physical state')
            start=fixed['warmup_steps'];soil_start=float(result['W'][start-1]) if start else p.wum_init+p.wlm_init+min(p.wdm_init,p.wdm)
            residual=abs(np.sum(result['P_perv'][start:])-np.sum(result['E'][start:])-np.sum(result['R'][start:])-(result['W'][-1]-soil_start))
            if residual/max(np.sum(result['P_perv'][start:]),1e-9)>1e-3:raise ValueError('native water-balance tolerance failed')
            q,_=self.route.route_single(result['Qt'],fixed['route_k'],fixed['route_x'],fixed['step_hours'],float(result['Qt'][0]))
            times=pd.to_datetime(f.time,utc=True)
            scored=np.arange(len(f))>=fixed['warmup_steps']
            if self.problem['data_shape']=='continuous':
                selector=self.problem['splits'][split]
                scored &= (times>=pd.Timestamp(selector['start'])) & (times<=pd.Timestamp(selector['end']))
            out=pd.DataFrame({'time':times,'observed':f.observed,'simulated':q,'scored':scored,'precipitation':f.P})
            if self.problem['data_shape']=='event_collection':out['event_id']=identity
            frames.append(out)
        series=pd.concat(frames,ignore_index=True);v=series[series.scored]
        o=v.observed.to_numpy();s=v.simulated.to_numpy();rmse=float(np.sqrt(np.mean((s-o)**2)))
        nse=float(1-np.sum((s-o)**2)/np.sum((o-o.mean())**2))
        return {'objective':rmse,'metrics':{'rmse':rmse,'nse':nse},'series':series}
    def evaluate(self,params,split):
        if split!='calibration':raise ValueError('validation only after parameter lock')
        r=self.materialize(params,split);return {'objective':r['objective'],'metrics':r['metrics']}

def create_evaluator(problem,problem_dir):return Evaluator(problem,problem_dir)
