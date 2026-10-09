"""Hidden development factory for 24 real-data composite tasks. Never stage this file."""
from __future__ import annotations
import argparse
import json
import shutil
from pathlib import Path
import pyexpat  # load the system XML runtime before GDAL on Windows
import numpy as np
import pandas as pd
from composite_common import ROOT, PUBLIC, native, portable_tree, sha, write_json
from composite_inputs import EVENTS, csv
import composite_science as s

TITLES={
 'data':['从连续资料建立洪水事件库','判断洪水事件是否能用于模型计算','从原始 DEM 建立可靠河网与子流域','从地形和站点资料建立半分布式输入','将站点资料转换为已有模型单元驱动','重新整理多个洪水观测窗口','用空间加权雨量建立洪水事件库','建立并验收指定空间结构'],
 'model':['单场新安江模拟至下游断面','多场洪水独立模拟','连续新安江模拟','上游出库与区间来水联合计算','大伙房计算与过程核查','日尺度 GR4J 计算与评价','半分布式新安江出口模拟','半分布式模型加入外部入流','内部过程与出口一致性检查','半分布式河道演算稳定性审查','连续模式受限预算率定与验证','场次集合受限预算率定与验证'],
 'analysis':['连续模拟评价与公平比较','洪水场次评价与误差模式总结','集合预测与独立评价','评分样本与成果审查']}
CAPS={
 'data':[['discharge_standardization','baseflow','event_identification','forcing_standardization'],['discharge_standardization','baseflow','event_identification','forcing_readiness'],['dem_grid','d8_network','hydrobase','independent_topology_qc'],['dem_grid','d8_network','hydrobase','independent_topology_qc','forcing_standardization','spatial_aggregation'],['independent_topology_qc','forcing_standardization','spatial_aggregation'],['discharge_standardization','baseflow','event_identification','forcing_standardization'],['independent_topology_qc','forcing_standardization','spatial_aggregation','discharge_standardization','baseflow','event_identification'],['dem_grid','d8_network','hydrobase','independent_topology_qc']],
 'model':[['forcing_standardization','xaj','muskingum']]*4+[['forcing_standardization','dhf','outlet_alignment','event_metrics'],['daily_forcing','gr4j','outlet_alignment','continuous_metrics']]+[['forcing_standardization','spatial_aggregation','semi_xaj']]*2+[['semi_xaj','outlet_alignment','continuous_metrics'],['forcing_standardization','spatial_aggregation','routing_stability'],['scoring_series','de_calibration','outlet_alignment','continuous_metrics'],['event_collection','de_calibration','event_metrics','event_aggregation']],
 'analysis':[['outlet_alignment','continuous_metrics','event_metrics'],['outlet_alignment','event_metrics','event_aggregation'],['member_alignment','bma','continuous_metrics'],['source_alignment','scored_split_audit','controlled_conclusion_review']]}
BLOCKS={}  # v2: all 24 supplied scenarios support normal delivery.
VERSION='composite-unattended-v2'
SEEDS=ROOT/'composite_assets/reference_seeds'

def ensure_seeds():
    """Rebuild reproducible prerequisites on a fresh checkout; no untracked probe dependence."""
    if not (SEEDS/'spatial/topology-qc/result.json').is_file():
        w=SEEDS/'spatial';w.mkdir(parents=True,exist_ok=True)
        for name in ['dem_100m.tif','basin.gpkg']:asset(w,name)
        s.spatial(w);portable_tree(w)
    if not (SEEDS/'dhf/model/result.json').is_file():
        w=SEEDS/'dhf';w.mkdir(parents=True,exist_ok=True);asset(w,'continuous_supplemented.csv','raw.csv')
        s.direct_model(w,'dhf');portable_tree(w)
    if not (SEEDS/'semi/model/result.json').is_file():
        w=SEEDS/'semi';clone(SEEDS/'spatial',w)
        asset(w,'continuous_supplemented.csv','raw.csv');asset(w,'stations.csv')
        s.semi_model(w,full=True);portable_tree(w)

def clone(source,destination):
    shutil.copytree(source,destination,dirs_exist_ok=True);portable_tree(destination,source)

def asset(data,name,target=None):
    path=data/(target or name);path.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/'composite_assets'/name,path)

def existing_space(data,qc=True):
    seed=SEEDS/'spatial'
    for folder in ['prepared','hydrology','hydrobase']+(['topology-qc'] if qc else []):
        clone(seed/folder,data/folder)
    # Cross-folder references are rebased against the complete original workspace.
    portable_tree(data,seed)

def inputs(data,family,n):
    data.mkdir(parents=True,exist_ok=True)
    asset(data,'source_manifest.json');asset(data,'derivation.json')
    multiple=(family=='data' and n==6) or (family=='model' and n in [2,12])
    if multiple:
        for event in (EVENTS[-3:] if family=='data' else [EVENTS[i] for i in [1,2,4,5]]):
            asset(data,event+'_supplemented.csv',f'raw_events/{event}.csv')
            asset(data,event+'_raw.csv',f'original_events/{event}.csv')
            asset(data,event+'_supplements.csv',f'supplements/{event}.csv')
    else:
        name='20250627' if family=='model' and n in [1,4] else 'continuous'
        asset(data,name+'_supplemented.csv','raw.csv')
        asset(data,name+'_raw.csv','original.csv');asset(data,name+'_supplements.csv','supplements.csv')
        if family=='model' and n in [3,11]:
            for name in ['raw.csv','original.csv']:
                f=pd.read_csv(data/name);csv(data/name,f[(f.time>='2023-08-15')&(f.time<'2023-08-19')])
            f=pd.read_csv(data/'supplements.csv');csv(data/'supplements.csv',f[(f.time>='2023-08-15')&(f.time<'2023-08-19')])
    spatial=(family=='data' and n in [3,4,5,7,8]) or (family=='model' and n in [7,8,9,10])
    if spatial:
        for name in ['dem_100m.tif','basin.gpkg','stations.csv']:asset(data,name)
        if (family=='data' and n in [5,7]) or family=='model':existing_space(data,qc=family=='model')
    if family=='analysis':
        for name in ['dhf','semi']:
            clone(SEEDS/name,data/'members'/name)
            for folder in ['flow','aligned','metrics','model-outlet-only']:
                p=data/'members'/name/folder
                if p.exists():shutil.rmtree(p)
        if n==4:
            f=pd.read_csv(data/'raw.csv');times=pd.to_datetime(f.time).dt.tz_localize('Asia/Shanghai')
            csv(data/'calibration_scored.csv',pd.DataFrame({'time':times.iloc[12:500],'scored':True}))
            csv(data/'validation_scored.csv',pd.DataFrame({'time':times.iloc[500:],'scored':True}))
            write_json(data/'submitted_conclusion.json',{'validation_independent':True,'review_pass':True})
    scenario={'notice':'明确声明的测试场景设定，补充数据不是实测修复。来源清单中的原始空白始终保留；supplements 逐项标注合成值。','flow_column':'GZ_in','flow_unit':'m3/s','station_crs':'EPSG:4326','grid_resolution_m':100,'stream_init_area_km2':100,'bfi_max':.5,'alpha':.95,'event_parameters':{'peak_quantile':.8,'prominence_factor':.15,'min_peak_distance_hours':12,'boundary_fraction':.1,'boundary_persistence_steps':3,'max_search_days':5,'merge_gap_hours':6,'valley_ratio_threshold':.6,'min_event_duration_hours':1,'warmup_steps':12,'rainfall_lookback_hours':24,'min_observed_rainfall_mm':1,'no_rainfall_policy':'exclude','missing_rainfall_policy':'keep'},'lumped_parameters':s.XAJ_PARAMETERS,'dhf_parameters':s.DHF_PARAMETERS,'gr4j_parameters':{'X1':350.,'X2':0.,'X3':90.,'X4':1.7},'area_km2':564.4784427125312,'river_length_km':40,'route_k_hours':1.,'route_x':.2,'warmup_steps':12,'optimizer':{'seed':20261004,'max_evaluations':128,'population_multiplier':3,'mutation_factor':.8,'crossover_probability':.7,'max_generations':3,'tolerance':1e-9,'polish':False},'search_parameters':[{'name':'K','lower':.3,'upper':.9},{'name':'B','lower':.15,'upper':.45}]}
    if family=='model' and n in [7,8,9,10]:
        seed=s.load(SEEDS/'semi/model_config.json');seed['xaj']['KE']=1.5
        scenario['semi_parameters']=seed
    if (family,n)==('model',4):scenario['external_inflow']={'column':'GB_out','relationship':'test-only independent upstream reservoir release plus local incremental GZ_in; both routed once','route_k_hours':1.,'route_x':.2}
    if (family,n)==('model',8):scenario['external_inflow']={'column':'GB_out','reach_id':1,'relationship':'test-only injection at reach 1, exactly once'}
    if family=='analysis':scenario['analysis_windows']='local calendar days 1-7, 8-14, 15-21, 22-28, 29-31; separate windows, warmup excluded'
    if (family,n)==('analysis',3):scenario['bma']={'train_end':'2023-08-20T23:00:00+08:00','predict_start':'2023-08-21T00:00:00+08:00','seed':20261004,'max_iter':2000,'tol':1e-6}
    if family=='model' and n==6:scenario['daily_aggregation']={'P':'sum','PET':'sum','Q':'time-weighted mean','E0_to_PET_factor':1.0,'warmup_days':2}
    if family=='model' and n==5:scenario['dhf_parameter_scale']='original'
    if family=='model' and n in [11,12]:
        scenario['calibration_split']='For continuous data: first half of hourly record for calibration, second half for validation; omit first 12 steps from scoring while maintaining continuous state. For an event collection: first half of chronologically sorted event IDs for calibration, remaining IDs for validation; each event has independent initial states and 12 warmup steps.'
    from composite_public import complete_scenario, write_input_guide
    complete_scenario(scenario,data,family,n)
    write_json(data/'scenario.json',scenario)
    write_input_guide(data,family,n)

def execute(w,family,n):
    records=[]
    if (family,n) in [('data',7),('model',5)]:
        write_json(w/'evaporation_mapping.json',{'mapping':{'source':'E0','target':'PET','factor':1.0}})
    if family=='data':
        if n in [1,2]:records=s.events(w)
        elif n in [3,8]:records=s.spatial(w,expected_outlets=1)
        elif n==4:
            records=s.spatial(w);records+=s.forcing(w,stations=True);records.append(s.aggregate(w))
        elif n==5:
            records=s.spatial(w,existing=True);records+=s.forcing(w,stations=True);records.append(s.aggregate(w))
        elif n==6:
            for i,source in enumerate(sorted((w/'raw_events').glob('*.csv'))):records+=s.events(w,str(source.relative_to(w)),f'window-{source.stem}/')
        elif n==7:
            records=s.spatial(w,existing=True);records+=s.forcing(w,stations=True,evap='PET');records.append(s.aggregate(w,'basin'))
            records.append(s.q_prepare(w));records.append(native(w,s.BF,['--prepare-result','flow/result.json','--bfi-max','.5','--alpha','.95','--output-dir','baseflow']))
            template={'schema_version':'1.2','peak_detection':{'peak_quantile':.8,'prominence_factor':.15,'min_peak_distance_hours':12},'boundaries':{'boundary_fraction':.1,'boundary_persistence_steps':3,'max_search_days':5},'merging':{'merge_gap_hours':6,'valley_ratio_threshold':.6},'filters':{'min_event_duration_hours':1,'min_peak_flow_m3_s':None,'min_event_volume_m3':None},'warmup':{'steps':12},'rainfall_support':{'lookback_hours':24,'min_observed_rainfall_mm':1,'no_rainfall_policy':'exclude','missing_rainfall_policy':'keep'}};write_json(w/'event_config.json',template)
            f=pd.read_csv(w/'aggregate/basin_forcing.csv');csv(w/'basin_rain.csv',f[['time','P']].rename(columns={'P':'P_mm'}))
            write_json(w/'rain_metadata.json',{'spatial_scope':'basin_mean','unit':'mm/step','timestep_seconds':3600,'timezone':'Asia/Shanghai','timestamp_semantics':'interval_end'})
            records.append(native(w,s.FLOOD,['--baseflow-result','baseflow/result.json','--config','event_config.json','--rainfall','basin_rain.csv','--rainfall-metadata','rain_metadata.json','--output-dir','events']))
    elif family=='model':
        if n in [1,2,3,4]:records=s.lumped(w,multiple=n==2,external=n==4)
        elif n in [5,6]:
            if n==6:
                f=pd.read_csv(w/'raw.csv');f.time=pd.to_datetime(f.time);f=f.set_index('time').resample('1D').agg({c:('sum' if c.endswith('rain') or c=='E0' else 'mean') for c in f.columns if c!='time'}).reset_index();csv(w/'daily.csv',f)
            records=s.direct_model(w,'gr4j' if n==6 else 'dhf',source='daily.csv' if n==6 else 'raw.csv')
        elif n in [7,8,9,10]:records=s.semi_model(w,boundary=n==8,full=n==9)
        elif n in [11,12]:records=s.calibration(w,multiple=n==12)
    else:
        if n<4:records=s.analysis(w,n)
        else:
            a=pd.read_csv(w/'calibration_scored.csv');b=pd.read_csv(w/'validation_scored.csv');common=sorted(set(pd.to_datetime(a.time,utc=True))&set(pd.to_datetime(b.time,utc=True)))
            write_json(w/'split_audit.json',{'overlap_count':len(common),'overlap_times':[x.isoformat() for x in common],'review_pass':not common,'validation_independent':not common,'sources':{name:{'path':name,'sha256':sha(w/name)} for name in ['calibration_scored.csv','validation_scored.csv']}})
            write_json(w/'approved_report.json',{'review_pass':not common,'validation_independent':not common,'scope':'scored sample independence only; does not establish model accuracy or causality','evidence':[{'path':'split_audit.json','sha256':sha(w/'split_audit.json')}]})
    if (family,n)==('data',2):
        f=pd.read_csv(w/'raw.csv');missing=f.avg_rain.isna();write_json(w/'readiness.json',{'ready':not bool(missing.any()),'rain_missing_count':int(missing.sum()),'missing_times':f.loc[missing,'time'].tolist(),'repair_authorized':False,'synthetic_supplements_authorized':True})
    if (family,n)==('model',10):
        config=s.load(w/'scenario.json')['semi_parameters'];ke=config['xaj']['KE'];xe=config['xaj']['XE'];dt=config['time']['step_seconds']/3600;den=ke*(1-xe)+.5*dt
        coefficients=[(.5*dt-ke*xe)/den,(.5*dt+ke*xe)/den,(ke*(1-xe)-.5*dt)/den]
        write_json(w/'routing_audit.json',{'stable':min(coefficients)>=0,'coefficients':coefficients,'parameter_change_authorized':False})
    reason=BLOCKS.get((family,n));proofs=sorted(p for p in w.rglob('result.json') if 'members' not in p.parts)
    if (w/'readiness.json').exists():proofs.append(w/'readiness.json')
    if (w/'split_audit.json').exists():proofs.append(w/'split_audit.json')
    if (w/'routing_audit.json').exists():proofs.append(w/'routing_audit.json')
    if (w/'approved_report.json').exists():proofs.append(w/'approved_report.json')
    write_json(w/'decision.json',{'status':'blocked' if reason else 'deliverable','reason':reason or 'scientific_contracts_satisfied','limitations':['Synthetic supplements are test data, not repaired observations.'],'evidence':[{'path':p.relative_to(w).as_posix(),'sha256':sha(p)} for p in proofs]})
    if family=='analysis' and n<4:
        conclusions={'causality':'not_established','scoring':'same_samples_excluding_warmup','units':'m3/s','independent_prediction':n==3}
        if n==1:
            values={name:float(pd.read_csv(w/f'metrics-{name}/series_metrics.csv').set_index('metric').loc['rmse','value']) for name in ['dhf','semi']};conclusions['ranking_rmse']=sorted(values,key=values.get)
        write_json(w/'conclusions.json',conclusions)
        (w/'report.md').write_text('结论与证据\n\n```json\n'+json.dumps(conclusions,ensure_ascii=False,sort_keys=True)+'\n```\n\n本测试使用明确标注的合成补充资料；指标描述拟合误差，不证明成因。\n',encoding='utf-8')
    return records

def sc(check,**kwargs):return {'type':'scientific_invariant','check':check,**kwargs}

def scientific_graph(family,n):
    mappings={
        'data':[['flow/result.json','baseflow/result.json','events/result.json','rain/result.json'],['flow/result.json','baseflow/result.json','events/result.json','readiness.json'],['prepared/result.json','hydrology/result.json','hydrobase/result.json','topology-qc/result.json'],['prepared/result.json','hydrology/result.json','hydrobase/result.json','topology-qc/result.json','rain/result.json','aggregate/result.json'],['topology-qc/result.json','rain/result.json','aggregate/result.json'],[f'window-{EVENTS[-3]}/'+x for x in ['flow/result.json','baseflow/result.json','events/result.json','rain/result.json']],['topology-qc/result.json','rain/result.json','aggregate/result.json','flow/result.json','baseflow/result.json','events/result.json'],['prepared/result.json','hydrology/result.json','hydrobase/result.json','topology-qc/result.json']],
        'model':[['rain/result.json','model/result.json','routed/result.json'],['e0/rain/result.json','model/result.json','routed/20150509/result.json'],['rain/result.json','model/result.json','routed/result.json'],['rain/result.json','model/result.json','routed/result.json'],['rain/result.json','model/result.json','aligned/result.json','metrics/result.json'],['rain/result.json','model/result.json','aligned/result.json','metrics/result.json'],['rain/result.json','aggregate/result.json','model/result.json'],['rain/result.json','aggregate/result.json','model/result.json'],['model/result.json','aligned/result.json','metrics/result.json'],['rain/result.json','aggregate/result.json','routing_audit.json'],['calibration_inputs/continuous.csv','calibration/result.json','validation_aligned.csv','metrics/result.json'],['calibration_inputs/20150509.csv','calibration/result.json','metrics/result.json','summary/result.json']],
        'analysis':[['aligned/result.json','metrics-dhf/result.json','metrics/result.json'],['aligned/result.json','metrics/result.json','summary/result.json'],['aligned-dhf/result.json','fit/result.json','metrics/result.json'],['calibration_scored.csv','split_audit.json','decision.json']]}
    caps=CAPS[family][n-1];artifacts=mappings[family][n-1]
    edges=[(i-1,i) for i in range(1,len(caps))]
    if family=='data' and n in [1,6]:edges=[(0,1),(1,2),(3,2)]
    if family=='data' and n==4:edges=[(0,1),(1,2),(2,3),(3,5),(4,5)]
    if family=='data' and n==5:edges=[(0,2),(1,2)]
    if family=='data' and n==7:edges=[(0,2),(1,2),(3,4),(4,5),(2,5)]
    if family=='analysis' and n==1:edges=[(0,1),(0,2)]
    return {'nodes':[{'id':cap,'capability':cap,'artifact':artifact} for cap,artifact in zip(caps,artifacts)],'edges':[{'from':caps[a],'to':caps[b]} for a,b in edges],'note':'Dependencies below bind actual files and hashes; transform tables are independently checked. Listed graph is developer metadata, never visible to candidates.'}

def reference(task_dir,w,data,family,n,records):
    expected=task_dir/'expected';gates=[];dependencies=[];critical=[];outputs=[];settings=[]
    source_paths={p.relative_to(data).as_posix() for p in data.rglob('*') if p.is_file()}
    protected={rel:sha(data/rel) for rel in sorted(source_paths)}
    write_json(expected/'protected_sources.json',protected)
    gates.append({'id':'protected_sources','criteria':[sc('protected_sources',reference='expected/protected_sources.json')],'evidence':['scenario.json']})
    if (family,n)==('data',2):
        critical.append({'code':'unauthorized_missing_rain_fill','criterion':sc('missing_preservation',target='original.csv',reference='data/original.csv',columns=['avg_rain']),'requires':['original.csv']})
    for path in sorted(w.rglob('*')):
        if not path.is_file():continue
        rel=path.relative_to(w).as_posix()
        if rel in source_paths or '__pycache__' in rel or path.suffix=='.pyc':continue
        from composite_public import scientific_artifact
        if not scientific_artifact(rel):continue
        bma_variable=family=='analysis' and n==3 and (rel.startswith(('forecast/','metrics/')) or rel=='evaluation.csv')
        if bma_variable and path.suffix=='.csv':continue
        criteria=[]
        if path.suffix=='.csv':
            f=pd.read_csv(path)
            if len(f):criteria=[{'type':'table_match','target':rel,'reference':'expected/golden_workspace/'+rel,'columns':list(f.columns),'datetime_columns':[c for c in f if c in ['time','start','end','start_time','end_time','peak_time','warmup_start_time']],'atol':1e-6,'rtol':1e-6}]
            numeric=[c for c in f.select_dtypes(include='number') if c not in ['event_id','sub_id','reach_id','outlet_reach_id','year','month','day','hour','evaluation']]
            if numeric and not (family=='model' and n in [11,12] and rel.startswith(('calibration/','metrics/','summary/','scoring_events/','validation_aligned'))):
                critical.append({'code':'material_scientific_numeric_error','criterion':sc('material_numeric_error',target=rel,reference='expected/golden_workspace/'+rel,columns=numeric,atol=1e-3,rtol=.01),'requires':[rel]})
        elif path.suffix=='.tif':criteria=[{'type':'raster_match','target':rel,'reference':'expected/golden_workspace/'+rel,'atol':1e-5,'rtol':1e-6}]
        elif path.suffix=='.gpkg':criteria=[{'type':'vector_match','target':rel,'reference':'expected/golden_workspace/'+rel,'atol':1e-6,'rtol':1e-6,'geometry_tolerance':1e-6}]
        elif path.name=='result.json':
            doc=s.load(path);subset={k:doc[k] for k in ['parameters','data_shape'] if k in doc}
            from composite_public import scientific_parameters
            if 'parameters' in subset:subset['parameters']=scientific_parameters(subset['parameters'])
            if family=='model' and n in [11,12]:subset.pop('evaluation_count',None);subset.pop('status',None)
            contract='expected/contracts/'+rel;write_json(task_dir/contract,subset)
            criteria=[sc('json_contract',target=rel,reference=contract)]
            def semantic_parameters(value,field):
                if isinstance(value,dict):
                    for key,v in value.items():
                        name=field+'.'+key
                        if key in {'unit','variable','timestep_seconds','timestep_hours','warmup_steps','param_scale','expected_outlets','vertical_unit','target_crs','mode','timestamp_semantics','timestamp_meaning'} and not isinstance(v,(dict,list)):
                            critical.append({'code':'wrong_units_or_scientific_organization','criterion':sc('json_value',target=rel,field=name,expected=v),'requires':[rel]})
                        semantic_parameters(v,name)
            semantic_parameters(doc.get('parameters',{}),'parameters')
            if doc.get('artifacts') or doc.get('inputs'):criteria.append(sc('manifest_integrity',target=rel))
            def refs(value,field):
                if isinstance(value,dict):
                    if isinstance(value.get('path'),str) and 'sha256' in value:
                        upstream=(path.parent/value['path']).resolve()
                        try:up=upstream.relative_to(w.resolve()).as_posix()
                        except ValueError:return
                        # A factory config file is an implementation detail, not a
                        # scientific exchange artifact. Its science is checked
                        # via supplied settings, output parameters and replay.
                        if upstream.suffix=='.json' and not scientific_artifact(up):return
                        dependencies.append({'id':rel+':'+field,'downstream':rel,'upstream':up,'field':field})
                    else:
                        for key,v in value.items():refs(v,field+'.'+key if field else key)
            refs(doc.get('inputs',{}),'inputs')
        if family=='model' and n in [11,12] and (rel.startswith('calibration/') or rel.startswith('validation_aligned') or rel.startswith('scoring_events/') or rel.startswith('metrics/') or rel.startswith('summary/')):continue
        if criteria:gates.append({'id':rel,'criteria':criteria,'evidence':[rel]});outputs.append(rel)
    decision=s.load(w/'decision.json');contract='expected/decision.json';write_json(task_dir/contract,{k:decision[k] for k in ['status','reason']})
    gates.append({'id':'decision','criteria':[sc('json_contract',target='decision.json',reference=contract),sc('decision_evidence',target='decision.json')],'evidence':['decision.json']});outputs.append('decision.json')
    reason=BLOCKS.get((family,n))
    if (family,n)==('data',2):
        write_json(expected/'readiness.json',s.load(w/'readiness.json'));gates.append({'id':'readiness','criteria':[sc('readiness_recompute',target='readiness.json',source='raw.csv',column='avg_rain')],'evidence':['readiness.json']});outputs.append('readiness.json')
    if (family,n)==('analysis',4):
        gates.append({'id':'split_overlap','criteria':[sc('split_audit_recompute',target='split_audit.json',targets=['calibration_scored.csv','validation_scored.csv']),sc('manifest_integrity',target='split_audit.json')],'evidence':['split_audit.json']});outputs.append('split_audit.json')
        gates.append({'id':'review_delivery','criteria':[sc('json_value',target='approved_report.json',field='review_pass',expected=True),sc('json_value',target='approved_report.json',field='validation_independent',expected=True),sc('manifest_integrity',target='approved_report.json')],'evidence':['approved_report.json']});outputs.append('approved_report.json')
        critical.append({'code':'invalid_scored_sample_review','criterion':sc('split_audit_recompute',target='split_audit.json',targets=['calibration_scored.csv','validation_scored.csv']),'requires':['split_audit.json']})
    if family=='model' and n in [11,12]:
        clone(w,expected/'replay_inputs')
        replay=sc('calibration_replay',target='calibration/best_parameters.json',input_base='expected/replay_inputs')
        gates.append({'id':'physical_calibration','criteria':[replay,sc('split_disjoint',targets=['calibration/calibration_series.csv','calibration/validation_series.csv'])],'evidence':['calibration/best_parameters.json']})
        outputs+=['calibration/best_parameters.json','calibration/calibration_series.csv','calibration/validation_series.csv','calibration/calibration_trace.csv','metrics/result.json']
        critical.append({'code':'physical_state_or_split_error','criterion':replay,'requires':['calibration/best_parameters.json','calibration/validation_series.csv']})
        metric=sc('metric_recompute' if n==11 else 'event_metrics_recompute',target='metrics/series_metrics.csv' if n==11 else 'metrics/event_metrics.csv',series='validation_aligned.csv')
        gates.append({'id':'independent_metrics','criteria':[metric,sc('manifest_integrity',target='calibration/result.json')],'evidence':[metric['target']]})
        critical.append({'code':'wrong_independent_metric','criterion':metric,'requires':[metric['target'],'validation_aligned.csv']})
        if n==12:
            summary=sc('event_summary_recompute',target='summary/aggregate_metrics.csv',series='metrics/event_metrics.csv')
            gates.append({'id':'independent_event_aggregation','criteria':[summary],'evidence':['summary/aggregate_metrics.csv']});outputs.append('summary/aggregate_metrics.csv')
    if family=='model' and n==9:
        gates.append({'id':'output_mode_consistency','criteria':[sc('same_series',targets=['model/outlet_flow.csv','model-outlet-only/outlet_flow.csv'],column='Q_m3s')],'evidence':['model/outlet_flow.csv','model-outlet-only/outlet_flow.csv']})
    if family=='analysis' and n==3:
        write_json(expected/'bma.json',{'kind':'bma'});gates.append({'id':'bma_distribution','criteria':[{'type':'report_contract_check','reference':'expected/bma.json'}],'evidence':['fit/bma_model.json','forecast/ensemble_discharge.csv']})
        replay=sc('bma_replay');metric=sc('metric_recompute',target='metrics/series_metrics.csv',series='evaluation.csv')
        gates.append({'id':'bma_source_and_metric_replay','criteria':[replay,metric],'evidence':['forecast/component_predictions.csv','metrics/series_metrics.csv']})
        outputs+=['forecast/ensemble_discharge.csv','forecast/component_predictions.csv','metrics/series_metrics.csv','fit/fit_diagnostics.json','evaluation.csv']
        critical.append({'code':'bma_distribution_or_source_error','criterion':replay,'requires':['fit/bma_model.json','forecast/component_predictions.csv','evaluation.csv']})
    if family=='analysis' and n<4:
        write_json(expected/'conclusions.json',s.load(w/'conclusions.json'))
        gates.append({'id':'controlled_conclusions','criteria':[sc('controlled_claims',target='conclusions.json',reference='expected/conclusions.json'),sc('markdown_json_consistency',target='conclusions.json',markdown='report.md'),sc('markdown_evidence_binding',target='decision.json',markdown='report.md')],'evidence':['conclusions.json']});outputs+=['conclusions.json','report.md']
        critical.append({'code':'unsupported_scientific_conclusion','criterion':sc('controlled_claims',target='conclusions.json',reference='expected/conclusions.json'),'requires':['conclusions.json']})
    if (w/'atlas').is_dir():
        from atomic_oracles import make_grading
        _,rows=make_grading('hydrochain',w,['atlas'],task_dir)
        figure=[c for c in rows if c['type']=='figure_contract_check']
        gates.append({'id':'figure_contract','criteria':figure,'evidence':['atlas/result.json']})
        outputs += [p.relative_to(w).as_posix() for p in (w/'atlas').rglob('*') if p.is_file() and p.suffix in ['.png','.svg','.json']]
    def provided_setting(key,value,target,field):
        settings.append({'key':key,'source':'scenario.json','field':key,'bindings':[{'target':target,'field':field,'expected':value}]})
    if family=='data' and n in [3,4,8]:
        provided_setting('vertical_unit','m','prepared/result.json','parameters.vertical_unit')
        provided_setting('expected_outlets',1,'topology-qc/result.json','parameters.expected_outlets')
    elif family=='model' and n in [11,12]:provided_setting('organization_mode','event_collection' if n==12 else 'continuous','problem.json','data_shape')
    elif family=='analysis':provided_setting('outlet_semantics','basin_outlet','resolved_information.json','outlet_semantics')
    else:
        target='window-'+EVENTS[-3]+'/flow/result.json' if family=='data' and n==6 else ('rain/result.json' if (w/'rain/result.json').is_file() else 'flow/result.json')
        if family=='model' and n==2:target='e0/rain/result.json'
        provided_setting('timezone','Asia/Shanghai',target,'parameters.timezone')
    if (family,n)==('data',2):provided_setting('repair_authorized',False,'readiness.json','repair_authorized')
    if (family,n)==('model',10):provided_setting('parameter_change_authorized',False,'routing_audit.json','parameter_change_authorized')
    if (family,n) in [('data',7),('model',5)]:provided_setting('evaporation_mapping',{'source':'E0','target':'PET','factor':1.0},'evaporation_mapping.json','mapping')
    # Bind extra scientific settings to program parameters rather than claimed logs.
    write_json(w/'resolved_information.json',{'outlet_semantics':'basin_outlet'})
    forbidden=[]
    for gate in gates:
        for c in gate['criteria']:
            if c.get('check') in ['manifest_integrity']:critical.append({'code':'false_or_stale_evidence','criterion':c,'requires':[c['target']]})
    for item in settings:
        for b in item['bindings']:critical.append({'code':'wrong_provided_scientific_setting','criterion':sc('json_value',**b),'requires':[b['target']]})
        outputs += [b['target'] for b in item['bindings']]
    if (family,n)==('model',10):
        gates.append({'id':'routing_stability','criteria':[sc('routing_stability_recompute',source='scenario.json',target='routing_audit.json')],'evidence':['routing_audit.json']});outputs.append('routing_audit.json')
    # Every file consumed by a scientific check must have a visible interface.
    for gate in gates:
        for c in gate['criteria']:
            candidates=[c.get(key) for key in ['target','series','markdown']]+c.get('targets',[])
            outputs += [rel for rel in candidates if isinstance(rel,str) and rel not in source_paths and (w/rel).is_file()]
    spec={'schema_version':'2.0','task_version':VERSION,'interaction_mode':'none','gates':gates,'dependencies':dependencies,'provided_settings':settings,'critical_rules':critical,'forbidden_outputs':forbidden,'core_capabilities':CAPS[family][n-1],'scientific_graph':scientific_graph(family,n),'reference_execution':records,'severity_policy':'Missing evidence is unknown. Artifact tolerances 1e-6; a critical numerical error exceeds 1e-3 + 1% of reference magnitude. Critical categorical failures are explicitly enumerated.'}
    write_json(expected/'evaluation.json',spec)
    return sorted(set(outputs)),spec

def generate(family,n,destination=None):
    ensure_seeds()
    task_id=f'hydrochain-{family}-{n:03d}';domain={'data':'data-preprocessing','model':'model-computation','analysis':'results-analysis'}[family]
    task_dir=Path(destination or ROOT/'composite_tests'/domain/task_id).resolve();task_dir.mkdir(parents=True,exist_ok=True)
    # Rebuild only factory-owned data/expected under this explicitly selected task directory.
    for folder in ['data','expected']:
        p=task_dir/folder
        p.resolve().relative_to(task_dir)
        if p.is_symlink():raise ValueError('Factory-owned directory cannot be a symlink: '+str(p))
        if p.exists():shutil.rmtree(p)
    data=task_dir/'data';inputs(data,family,n);w=task_dir/'expected/golden_workspace';clone(data,w)
    records=execute(w,family,n);portable_tree(w)
    # decision references use workspace-root paths, so refresh after manifest portability.
    decision=s.load(w/'decision.json')
    for ref in decision['evidence']:ref['sha256']=sha(w/ref['path'])
    write_json(w/'decision.json',decision)
    if (w/'report.md').is_file():
        citations='\n'.join('- ['+ref['path']+']('+ref['path']+') SHA-256: '+ref['sha256'] for ref in decision['evidence'])
        with (w/'report.md').open('a',encoding='utf-8') as report:report.write('\n证据绑定\n\n'+citations+'\n')
    outputs,spec=reference(task_dir,w,data,family,n,records);portable_tree(w)
    from composite_public import write_output_interfaces
    write_output_interfaces(data,w,outputs,spec)
    inventory=s.load(data/'input_inventory.json')
    for name in ['INPUT_GUIDE.md','OUTPUT_INTERFACES.md','output_interfaces.json']:
        inventory['files'].append({'path':name,'role':'public input/output interface documentation','sha256':sha(data/name)})
    write_json(data/'input_inventory.json',inventory)
    for name in ['OUTPUT_INTERFACES.md','output_interfaces.json','input_inventory.json']:shutil.copyfile(data/name,w/name)
    write_json(task_dir/'expected/protected_sources.json',{p.relative_to(data).as_posix():sha(p) for p in sorted(data.rglob('*')) if p.is_file()})
    business=TITLES[family][n-1]
    extra='多个观测窗口独立处理，禁止跨窗口拼接或传递状态。' if (family,n) in [('data',6),('model',2),('model',12)] else ''
    if family=='model' and n==11:extra+='按已给定连续组织模式保持状态。'
    if family=='model' and n==12:extra+='按已给定场次组织模式独立处理；率定后锁定参数验证。'
    if family=='analysis':extra+='解释必须绑定证据，不能由拟合优劣推断因果；对比较和独立评价核查实际评分样本。'
    prompt=f'请完成“{business}”。启动前提供的 scenario.json 与 INPUT_GUIDE.md 构成本题完整科学设定；OUTPUT_INTERFACES.md 与 output_interfaces.json 定义公开成果接口。驱动选列、空间代表性、source_id 和 E0/PET 变量按 forcing_selection；输出时间字段必须带显式时区偏移。运行中没有用户答复或信息补充，不调用用户确认接口。自主检查资料、实现计算、排错及重试，可选择工具、代码、执行顺序和等价实现；遵守指定模型、科学参数、状态组织、评价目标和预算，不擅自修改原始观测或科学设定。允许使用已标注的合成补充计算资料，但不得称为实测修复。{extra}交付可复核的中间科学成果、相对文件引用及 SHA-256、最终成果与 decision.json；记录实现选择与限制。decision.json 包含 status、reason、limitations 和 evidence，正常交付使用 status=deliverable、reason=scientific_contracts_satisfied。若发现实际资料或环境异常，记录问题证据；本题预期完成正常计算交付，不以等待用户答复作为完成。'
    if family=='analysis' and n<4:prompt+=' conclusions.json 必须包括 causality、scoring、units、independent_prediction；比较题增加 ranking_rmse。report.md 用 JSON 代码块逐字绑定这些结构化结论，并解释限制。'
    task={'id':task_id,'task_version':VERSION,'task_revision':4,'interaction_mode':'none','title':business,'domain':domain,'difficulty':'advanced','task_kind':'composite','outcome_goal':'deliverable','primary_skill':'workflows/'+{'data':'data-preprocessing','model':'hydrological-modeling','analysis':'simulation-analysis'}[family],'secondary_skills':[],'core_capabilities':CAPS[family][n-1],'prompt':prompt,'data_description':'Readonly originals and explicitly authorised synthetic calculation supplements; complete upfront scientific settings and public output interfaces.','data_files':sorted(p.relative_to(data).as_posix() for p in data.rglob('*') if p.is_file() and '__pycache__' not in p.parts),'required_outputs':outputs,'timeout_seconds':1800 if family=='model' and n in [11,12] else 900,'resource_budget':{'cpus':4,'memory_mb':8192,'agent_rounds':60,'tool_calls':120},'evaluation_reference':'expected/evaluation.json','grading':[{'name':'scientific_artifact_progress','type':'composite_contract_check','reference':'expected/evaluation.json','weight':1.0}]}
    write_json(task_dir/'task.json',task)
    (task_dir/'generate_data.py').write_text('from pathlib import Path\nimport sys\nsys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))\nfrom composite_tasks import generate\nif __name__ == "__main__": generate('+repr(family)+','+str(n)+',Path(__file__).resolve().parent)\n',encoding='utf-8')
    # Retain an empty compatibility fixture, never fabricate user confirmations.
    write_json(task_dir/'expected/audit_fixture.json',{'events':[]})
    write_json(task_dir/'expected/derivation.json',{'family':family,'index':n,'source_manifest_sha256':sha(data/'source_manifest.json'),'data_sha256':{p.relative_to(data).as_posix():sha(p) for p in sorted(data.rglob('*')) if p.is_file()},'supplement_notice':'Synthetic supplemental values; original known values preserved.'})
    print(task_id,len(records),'native calls',flush=True);return task_dir

def main():
    p=argparse.ArgumentParser();p.add_argument('--family',choices=TITLES);p.add_argument('--index',type=int);p.add_argument('--destination');a=p.parse_args()
    for family in ([a.family] if a.family else TITLES):
        for n in ([a.index] if a.index else range(1,len(TITLES[family])+1)):generate(family,n,a.destination)
if __name__=='__main__':main()
