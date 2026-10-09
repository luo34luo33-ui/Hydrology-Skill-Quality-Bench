"""Trusted development recipes connecting unchanged scientific programs."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import pandas as pd
from composite_common import ROOT, PUBLIC, native, write_json
from composite_common import sha
from composite_inputs import csv

XAJ_PARAMETERS={'K':.5,'B':.3,'C':.12,'WM':120.,'WUM':20.,'WLM':60.,'IM':.02,'SM':4.,'EX':1.2,'KG':.35,'KI':.3,'CG':.95,'CI':.6,'CS':.2,'L':2,'WUM_init':15.,'WLM_init':45.,'WDM_init':30.,'S1':5.,'FR1':.4,'Q':15.}
DHF_PARAMETERS={'S0':50.,'U0':90.,'D0':100.,'KC':.8,'KW':.5,'K2':.4,'KA':.7,'G':.1,'A':.5,'B':1.5,'B0':1.,'K0':.3,'N':3,'DD':1.2,'CC':2.,'COE':.4,'DDL':1.,'CCL':2.}

Q='data-processing/prepare-discharge-timeseries'; P='data-processing/prepare-model-forcing-timeseries'
BF='data-processing/separate-baseflow-eckhardt'; FLOOD='data-processing/extract-flood-events'
DEM='spatial-analysis/prepare-dem-analysis-grid'; NET='spatial-analysis/extract-dem-stream-network'
BUILD='spatial-analysis/build-hydrological-topology'; QC='spatial-analysis/validate-hydrological-topology'
AGG='spatial-analysis/aggregate-forcing-to-model-units'; XAJ='hydrological-modeling/run-lumped-xaj-model'
ROUTE='hydrological-modeling/route-muskingum-channel'; SD='hydrological-modeling/run-semi-distributed-xaj-model'
ALIGN='post-processing/align-observed-simulated-discharge'; SERIES='evaluation-diagnostics/compute-continuous-series-metrics'
EVENT='evaluation-diagnostics/compute-event-flood-metrics'; SUMMARY='evaluation-diagnostics/aggregate-event-metrics'

def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def q_prepare(w,source='raw.csv',out='flow',column='GZ_in'):
    return native(w,Q,['--input',source,'--time-column','time','--flow-column',column,'--flow-unit','m3/s','--timezone','Asia/Shanghai','--output-dir',out])

def forcing(w,source='raw.csv',stations=False,evap='E0',prefix='',step=3600):
    frame=pd.read_csv(w/source);frames=[]
    if stations:
        for station in pd.read_csv(w/'stations.csv').source_id:
            frames.append(pd.DataFrame({'time':frame.time,'source_id':station,'value':frame[f'{station}_rain']}))
    else:frames=[pd.DataFrame({'time':frame.time,'source_id':'basin','value':frame.avg_rain})]
    csv(w/f'{prefix}rain_source.csv',pd.concat(frames,ignore_index=True))
    ids=list(pd.read_csv(w/'stations.csv').source_id) if stations else ['basin']
    csv(w/f'{prefix}evap_source.csv',pd.concat([pd.DataFrame({'time':frame.time,'source_id':station,'value':frame.E0}) for station in ids],ignore_index=True))
    records=[]
    for name,var in [('rain','P'),('evap',evap)]:
        config={'schema_version':'1.0','variable':var,'columns':{'time':'time','source_id':'source_id','value':'value'},'unit':'mm/step','value_semantics':'step_depth','timezone':'Asia/Shanghai','source_timezone_mode':'local_naive','timestamp_semantics':'interval_end','timestep_seconds':step}
        write_json(w/f'{prefix}{name}_config.json',config)
        records.append(native(w,P,['--source',f'{prefix}{name}_source.csv','--config',f'{prefix}{name}_config.json','--output-dir',f'{prefix}{name}']))
    return records

def events(w,source='raw.csv',prefix='',raw_rain=False,valley_ratio=.6):
    records=[q_prepare(w,source,prefix+'flow')]
    records.append(native(w,BF,['--prepare-result',prefix+'flow/result.json','--bfi-max','0.5','--alpha','0.95','--output-dir',prefix+'baseflow']))
    frame=pd.read_csv(w/source)
    if not raw_rain:
        records.extend(forcing(w,source,prefix=prefix))
        rain=pd.read_csv(w/f'{prefix}rain/prepared_forcing.csv').rename(columns={'depth_mm':'P_mm'})[['time','P_mm']]
    else:
        rain=pd.DataFrame({'time':pd.to_datetime(frame.time).dt.tz_localize('Asia/Shanghai').astype(str),'P_mm':frame.avg_rain})
    csv(w/f'{prefix}basin_rain.csv',rain)
    write_json(w/f'{prefix}rain_metadata.json',{'spatial_scope':'basin_mean','unit':'mm/step','timestamp_semantics':'interval_end','timezone':'Asia/Shanghai','timestep_seconds':3600})
    config={'schema_version':'1.2','peak_detection':{'peak_quantile':.8,'prominence_factor':.15,'min_peak_distance_hours':12},'boundaries':{'boundary_fraction':.1,'boundary_persistence_steps':3,'max_search_days':5},'merging':{'merge_gap_hours':6,'valley_ratio_threshold':.6},'filters':{'min_event_duration_hours':1,'min_peak_flow_m3_s':None,'min_event_volume_m3':None},'warmup':{'steps':12},'rainfall_support':{'lookback_hours':24,'min_observed_rainfall_mm':1,'no_rainfall_policy':'exclude','missing_rainfall_policy':'keep'}}
    config['merging']['valley_ratio_threshold']=valley_ratio
    write_json(w/f'{prefix}event_config.json',config)
    records.append(native(w,FLOOD,['--baseflow-result',prefix+'baseflow/result.json','--config',prefix+'event_config.json','--rainfall',prefix+'basin_rain.csv','--rainfall-metadata',prefix+'rain_metadata.json','--output-dir',prefix+'events']))
    return records

def spatial(w,expected_outlets=1,existing=False,threshold=100):
    records=[]
    if not existing:
        records.append(native(w,DEM,['--dem','dem_100m.tif','--basin','basin.gpkg','--analysis-buffer-km','3','--vertical-unit','m','--output-dir','prepared']))
        whitebox=os.environ.get('HSQB_WHITEBOX_DIR',str(ROOT/'.cache/whitebox/extracted/WhiteboxTools_win_amd64/WBT'))
        os.environ['WBT_PATH']=whitebox
        records.append(native(w,NET,['--analysis-dem','prepared/dem_analysis_buffer.tif','--stream-init-area-km2',threshold,'--whitebox-dir',whitebox,'--output-dir','hydrology']))
        args=['--basin','prepared/basin_normalized.gpkg']
        for flag,name in [('dem-filled','dem_filled'),('d8-pointer','d8_pointer'),('flow-accumulation','flow_accumulation_cells'),('stream-links','stream_links'),('stream-order','strahler_order'),('subbasins','subbasins')]:args.extend(['--'+flag,'hydrology/'+name+'.tif'])
        args+=['--upstream-result','prepared/result.json','--cell-inclusion','center','--output-dir','hydrobase']
        records.append(native(w,BUILD,args))
    records.append(native(w,QC,['--build-result','hydrobase/result.json','--expected-outlets',str(expected_outlets),'--output-dir','topology-qc'],expected=(0,) if expected_outlets==1 else (2,)))
    return records

def aggregate(w,target='subbasin',out='aggregate'):
    evap='E0' if target=='subbasin' else 'PET'
    config={'min_coverage_fraction':1.0,'layers':{'P':{'kind':'station','variable':'P','result':'rain/result.json','stations':'stations.csv','station_crs':'EPSG:4326'},'evap':{'kind':'station','variable':evap,'result':'evap/result.json','stations':'stations.csv','station_crs':'EPSG:4326'}}}
    write_json(w/'source_config.json',config)
    return native(w,AGG,['--topology-result','hydrobase/result.json','--topology-qc-result','topology-qc/result.json','--source-config','source_config.json','--target',target,'--output-dir',out])

def forcing_table(w,prefix=''):
    p=pd.read_csv(w/f'{prefix}rain/prepared_forcing.csv');e=pd.read_csv(w/f'{prefix}evap/prepared_forcing.csv')
    joined=p.merge(e,on=['time','source_id'],validate='one_to_one',suffixes=('_p','_e'))
    out=pd.DataFrame({'time':joined.time,'P':joined.depth_mm_p,'E0':joined.depth_mm_e})
    csv(w/f'{prefix}forcing.csv',out);return out

def lumped(w,multiple=False,external=False):
    records=[];sources=sorted((w/'raw_events').glob('*.csv')) if multiple else [w/'raw.csv']
    for i,source in enumerate(sources):
        prefix=f'e{i}/' if multiple else ''
        records.extend(forcing(w,str(source.relative_to(w)),prefix=prefix))
        f=forcing_table(w,prefix)
        raw=pd.read_csv(source)
        if external:f['GB_out']=raw.GB_out;csv(w/f'{prefix}forcing.csv',f)
    write_json(w/'params.json',XAJ_PARAMETERS)
    area=float(pd.read_csv(w/'hydrobase/subbasins.csv').area_km2.sum()) if (w/'hydrobase/subbasins.csv').exists() else 564.4784427125312
    args=['--params','params.json','--area-km2',area,'--timestep-hours',1,'--warmup-steps',12,'--mode','event' if multiple else 'continuous','--output-dir','model']
    if multiple:
        (w/'event_forcing').mkdir(exist_ok=True)
        for i,source in enumerate(sources):shutil.copyfile(w/f'e{i}/forcing.csv',w/'event_forcing'/source.name)
        args+=['--events-dir','event_forcing']
    else:args+=['--forcing','forcing.csv']
    if external:args+=['--carry-columns','GB_out']
    records.append(native(w,XAJ,args))
    spec={'schema_version':'1.0','routes':[{'id':'local','column':'Qt','layout':'single','k':1.,'x':.2}]}
    if external:spec['routes'].append({'id':'reservoir','column':'GB_out','layout':'single','k':1.,'x':.2})
    write_json(w/'routes.json',spec)
    model=pd.read_csv(w/'model/lumped_xaj_runoff.csv')
    if multiple:
        for event,frame in model.groupby('event_id',sort=True):
            csv(w/f'routing_inputs/{event}.csv',frame)
            records.append(native(w,ROUTE,['--inflow',f'routing_inputs/{event}.csv','--route-spec','routes.json','--timestep-hours',1,'--output-dir',f'routed/{event}']))
    else:records.append(native(w,ROUTE,['--inflow','model/lumped_xaj_runoff.csv','--route-spec','routes.json','--timestep-hours',1,'--output-dir','routed']))
    return records

def direct_model(w,capability='dhf',source='raw.csv'):
    records=forcing(w,source=source,evap='PET',step=86400 if capability=='gr4j' else 3600);f=forcing_table(w);f.rename(columns={'E0':'PET'},inplace=True);csv(w/'forcing.csv',f)
    params=DHF_PARAMETERS if capability=='dhf' else {'X1':350.,'X2':0.,'X3':90.,'X4':1.7}
    write_json(w/'params.json',params)
    args=['--forcing','forcing.csv','--params','params.json','--area-km2',564.4784427125312,'--timestep-hours',24 if capability=='gr4j' else 1,'--mode','continuous','--warmup-steps',2 if capability=='gr4j' else 12,'--output-dir','model']
    if capability=='dhf':args+=['--river-length-km',40,'--param-scale','original']
    records.append(native(w,'hydrological-modeling/run-lumped-'+capability+'-model',args))
    records.extend(evaluate_outlet(w,step=24 if capability=='gr4j' else 1,events_mode=capability=='dhf',source=source))
    return records

def semi_model(w,boundary=False,full=False,unstable=False):
    records=forcing(w,stations=True);records.append(aggregate(w))
    frame=pd.read_csv(w/'aggregate/subbasin_forcing.csv');subs=pd.read_csv(w/'hydrobase/subbasins.csv');reaches=pd.read_csv(w/'hydrobase/reaches.csv')
    times=sorted(frame.time.unique());config={'schema_version':'1.0','time':{'step_seconds':3600,'timezone':'Asia/Shanghai','timestamp_meaning':'interval_end'},'xaj':{'KC':.8,'B':.3,'C':.12,'IMP':.02,'WM':120.,'WUM':20.,'WLM':60.,'SM':25.,'EX':1.2,'KG':.35,'KI':.3,'CG':.95,'CI':.6,'CS':.2,'KE':.01 if unstable else 1.5,'XE':.2},'routing':{'dp_by_reach':{str(int(r)):1 for r in reaches.reach_id},'lag_steps':0},'initial':{'soil_fraction':.3,'s_mm':5.,'fr':.4,'qi_m3s':.05,'qg_m3s':.1,'qs_cs_m3s':0.,'qi_cs_m3s':.05,'qg_cs_m3s':.1},'warmup_steps':12,'simulation':{'start':times[12],'end':times[-1]}}
    write_json(w/'model_config.json',config)
    args=['--topology-result','hydrobase/result.json','--topology-qc-result','topology-qc/result.json','--forcing','aggregate/subbasin_forcing.csv','--params','model_config.json','--output-detail','full' if full else 'outlet-only','--output-dir','model']
    if boundary:
        # A declared test scenario, not inferred reservoir reach geography.
        reach=int(reaches.reach_id.min());raw=pd.read_csv(w/'raw.csv')
        csv(w/'boundary.csv',pd.DataFrame({'time':times,'reach_id':reach,'Q_m3s':raw.GB_out.to_numpy()}));args+=['--boundary-inflow','boundary.csv']
    records.append(native(w,SD,args,expected=(1,) if unstable else (0,)))
    if full and not unstable:
        args2=[x for x in args];args2[args2.index('full')]='outlet-only';args2[-1]='model-outlet-only';records.append(native(w,SD,args2))
        records.extend(evaluate_outlet(w))
    return records

def evaluate_outlet(w,step=1,events_mode=False,model_result='model/result.json',routed=False,source='raw.csv'):
    records=[q_prepare(w,source=source)]
    args=['--observed-result','flow/result.json','--simulation-result',model_result,'--output-dir','aligned']
    if routed:
        route=load(w/model_result)
        write_json(w/'outlet_declaration.json',{'unit':'m3/s','input_unit':'m3/s','outlet_id':'benchmark_outlet','location':'basin_outlet','column':'Q_total','inflow_sha256':route['inputs']['inflow']['sha256'],'upstream_xaj_result':'model/result.json'})
        args+=['--outlet-declaration','outlet_declaration.json']
    records.append(native(w,ALIGN,args))
    if events_mode:
        frame=pd.read_csv(w/'aligned/evaluation_discharge.csv');frame['event_id']='window';csv(w/'evaluation_events.csv',frame)
        records.append(native(w,EVENT,['--events','evaluation_events.csv','--observed-column','observed_m3_s','--simulated-column','simulated_m3_s','--timestep-hours',step,'--volume-unit','m3','--output-dir','metrics']))
    else:records.append(native(w,SERIES,['--series','aligned/evaluation_discharge.csv','--observed-column','observed_m3_s','--simulated-column','simulated_m3_s','--timestep-hours',step,'--output-dir','metrics']))
    return records

def calibration(w,multiple=False):
    records=[];inputs=[]
    sources=sorted((w/'raw_events').glob('*.csv')) if multiple else [w/'raw.csv']
    for i,source in enumerate(sources):
        prefix=f'e{i}/' if multiple else ''
        records.extend(forcing(w,str(source.relative_to(w)),prefix=prefix));f=forcing_table(w,prefix)
        raw=pd.read_csv(source);f['observed']=raw.GZ_in.to_numpy()
        identity=source.stem if multiple else 'continuous';path=f'calibration_inputs/{identity}.csv';csv(w/path,f)
        inputs.append({'id':identity,'path':path,'sha256':sha(w/path)})
    write_json(w/'fixed.json',{'parameters':XAJ_PARAMETERS,'area_km2':564.4784427125312,'route_k':1.,'route_x':.2,'step_hours':1.,'warmup_steps':12})
    inputs.append({'id':'fixed','path':'fixed.json','sha256':sha(w/'fixed.json')})
    shutil.copyfile(PUBLIC/'physical_calibration.py',w/'physical_calibration.py')
    if multiple:
        ids=[x['id'] for x in inputs if x['id']!='fixed'];cut=len(ids)//2;splits={'calibration':{'events':ids[:cut]},'validation':{'events':ids[cut:]}}
    else:
        times=list(f.time);cut=len(times)//2;splits={'calibration':{'start':times[12],'end':times[cut-1]},'validation':{'start':times[cut],'end':times[-1]}}
    problem={'schema_version':'1.0','adapter':{'path':'physical_calibration.py','sha256':sha(w/'physical_calibration.py')},'inputs':inputs,'parameters':[{'name':'K','lower':.3,'upper':.9},{'name':'B','lower':.15,'upper':.45}], 'objective':{'metric':'rmse','direction':'minimize'},'splits':splits,'data_shape':'event_collection' if multiple else 'continuous','warmup':{'confirmed':True,'semantics':'12 steps per independent event; continuous state propagated across scoring split'},'variables':{'observed':{'semantics':'outlet_discharge','unit':'m3/s'},'simulated':{'semantics':'outlet_discharge','unit':'m3/s'}},'objective_consistency_tolerance':1e-8}
    write_json(w/'problem.json',problem)
    write_json(w/'optimizer.json',{'schema_version':'1.0','algorithm':'de','seed':20261004,'max_evaluations':128,'max_failed_evaluations':2,'population_multiplier':3,'mutation_factor':.8,'crossover_probability':.7,'max_generations':3,'tolerance':1e-9,'polish':False})
    os.environ['HSQB_PUBLIC_PROGRAMS']=str(PUBLIC)
    records.append(native(w,'model-calibration/calibrate-model-de',['--problem','problem.json','--optimizer-config','optimizer.json','--output-dir','calibration']))
    series=pd.read_csv(w/'calibration/validation_series.csv');series=series[series.scored].rename(columns={'observed':'observed_m3_s','simulated':'simulated_m3_s'})
    csv(w/'validation_aligned.csv',series)
    if multiple:
        for identity,frame in series.groupby('event_id'):csv(w/f'scoring_events/{identity}.csv',frame)
        records.append(native(w,EVENT,['--events-dir','scoring_events','--observed-column','observed_m3_s','--simulated-column','simulated_m3_s','--timestep-hours','1','--volume-unit','m3','--output-dir','metrics']))
        records.append(event_summary(w))
    else:records.append(native(w,SERIES,['--series','validation_aligned.csv','--observed-column','observed_m3_s','--simulated-column','simulated_m3_s','--timestep-hours','1','--output-dir','metrics']))
    return records

def event_summary(w):
    return native(w,SUMMARY,['--metrics-table','metrics/event_metrics.csv','--value-columns','nse,rmse,mae,volume_error_relative,peak_error_relative,peak_time_error_hours','--output-dir','summary'])

def analysis(w,n):
    records=[q_prepare(w)]
    if n==3:
        members=[]
        for name in ['dhf','semi']:
            output='aligned-'+name
            records.append(native(w,ALIGN,['--observed-result','flow/result.json','--simulation-result',f'members/{name}/model/result.json','--output-dir',output]))
            aligned=pd.read_csv(w/output/'evaluation_discharge.csv');model=load(w/f'members/{name}/model/result.json')
            if name=='dhf':
                adapted=pd.DataFrame({'time':aligned.time,'Q':aligned.simulated_m3_s,'is_warmup':False});key='simulation_table'
            else:
                original=pd.read_csv(w/'members/semi/model/outlet_flow.csv');adapted=pd.DataFrame({'time':aligned.time,'Q_m3s':aligned.simulated_m3_s,'outlet_reach_id':int(original.outlet_reach_id.iloc[0]),'is_warmup':False});key='outlet_flow'
            csv(w/f'aligned_members/{name}.csv',adapted)
            model['artifacts']={key:{'path':name+'.csv','sha256':sha(w/f'aligned_members/{name}.csv')}}
            model['inputs']={'alignment':{'path':'../'+output+'/result.json','sha256':sha(w/output/'result.json')},'physical_source':{'path':f'../members/{name}/model/result.json','sha256':sha(w/f'members/{name}/model/result.json')}}
            model['message']='Aligned outlet adapter preserving physical-source provenance; not a new forward run'
            write_json(w/f'aligned_members/{name}-result.json',model)
            members.append({'model_id':name,'outlet_id':'benchmark_outlet','simulation_result':f'aligned_members/{name}-result.json'})
        write_json(w/'members.json',{'schema_version':'1.0','outlet_id':'benchmark_outlet','timestep_hours':1,'timezone':'Asia/Shanghai','unit':'m3/s','members':members})
        records.append(native(w,'post-processing/ensemble-discharge-with-bma',['--mode','train','--members','members.json','--observed-result','flow/result.json','--start','2023-08-01T12:00:00+08:00','--end','2023-08-20T23:00:00+08:00','--random-state','20261004','--max-iter','2000','--tol','1e-6','--output-dir','fit']))
        records.append(native(w,'post-processing/ensemble-discharge-with-bma',['--mode','predict','--members','members.json','--model-result','fit/result.json','--start','2023-08-21T00:00:00+08:00','--end','2023-08-31T23:00:00+08:00','--output-dir','forecast']))
        f=pd.read_csv(w/'forecast/ensemble_discharge.csv');q=pd.read_csv(w/'flow/discharge_timeseries.csv');f.time=pd.to_datetime(f.time,utc=True);q.time=pd.to_datetime(q.time,utc=True)
        f=f.merge(q,on='time',validate='one_to_one').rename(columns={'discharge_m3_s':'observed_m3_s','ensemble_mean_m3_s':'simulated_m3_s'});csv(w/'evaluation.csv',f)
        records.append(native(w,SERIES,['--series','evaluation.csv','--observed-column','observed_m3_s','--simulated-column','simulated_m3_s','--timestep-hours','1','--output-dir','metrics']))
        return records
    for name in (['dhf','semi'] if n==1 else ['dhf']):
        output='aligned' if name=='dhf' else 'aligned-semi'
        records.append(native(w,ALIGN,['--observed-result','flow/result.json','--simulation-result',f'members/{name}/model/result.json','--output-dir',output]))
        if n==1:
            records.append(native(w,SERIES,['--series',output+'/evaluation_discharge.csv','--observed-column','observed_m3_s','--simulated-column','simulated_m3_s','--timestep-hours','1','--output-dir','metrics-'+name]))
    f=pd.read_csv(w/'aligned/evaluation_discharge.csv')
    records+=events(w,prefix='observation/')
    bounds=pd.read_csv(w/'observation/events/event_summary.csv');pieces=[]
    axis=pd.to_datetime(f.time,utc=True)
    for row in bounds.itertuples():
        piece=f[(axis>=pd.Timestamp(row.start_time))&(axis<=pd.Timestamp(row.end_time))].copy();piece['event_id']=str(row.event_id);pieces.append(piece)
    f=pd.concat(pieces,ignore_index=True)
    csv(w/'evaluation_events.csv',f)
    for identity,frame in f.groupby('event_id'):csv(w/f'scoring_events/{identity}.csv',frame)
    records.append(native(w,EVENT,['--events-dir','scoring_events','--observed-column','observed_m3_s','--simulated-column','simulated_m3_s','--timestep-hours','1','--volume-unit','m3','--output-dir','metrics']))
    if n==2:
        records.append(event_summary(w))
        records.append(native(w,'visualization-reporting/visualize-flood-event-atlas',['--extract-result','observation/events/result.json','--rainfall','observation/basin_rain.csv','--rainfall-metadata','observation/rain_metadata.json','--language','zh','--output-dir','atlas']))
    return records

