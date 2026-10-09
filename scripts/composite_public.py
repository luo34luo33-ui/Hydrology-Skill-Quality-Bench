"""Upfront scientific settings and output interfaces, without reference solutions."""
from pathlib import Path
import json
import pandas as pd
from composite_common import write_json, sha

VERSION = 'composite-unattended-v2'


def scientific_parameters(value):
    """Exclude CLI defaults, filenames and diagnostic counters from equality checks."""
    ignored={'columns','schema_version','event_config_schema_version','alpha_decision',
        'crs_decision','input_format','output_format','per_event_format','overwrite','sheet',
        'max_interpolation_gap_hours','event_filename_by','model','output_detail','output_level',
        'result','stations','max_events','rendered_event_ids','muskingum_coefficients'}
    if isinstance(value,dict):
        return {k:scientific_parameters(v) for k,v in value.items()
                if k not in ignored and not k.endswith('_count') and not (k=='initial_states' and v is None)}
    if isinstance(value,list):
        return [scientific_parameters(v) for v in value]
    return value


def scientific_artifact(rel):
    """Only public scientific interfaces are mandatory, never factory scaffolding."""
    path = Path(rel)
    if path.name in {'result.json', 'best_parameters.json', 'bma_model.json'}:
        return True
    if path.suffix in {'.tif', '.gpkg'}:
        return True
    if path.suffix != '.csv':
        return False
    if path.name.endswith('_source.csv') or path.name in {'boundary.csv', 'daily.csv'}:
        return False
    if rel.startswith(('aligned_members/', 'calibration_inputs/', 'event_forcing/',
                       'routing_inputs/', 'scoring_events/')):
        return False
    if rel.startswith('calibration/') and path.name not in {'calibration_series.csv', 'validation_series.csv'}:
        return False
    return True


def complete_scenario(scenario, data, family, n):
    # Observed event extraction, not arbitrary calendar windows, defines analysis samples.
    scenario.pop('analysis_windows',None)
    multiple = (family, n) in {('data', 6), ('model', 2), ('model', 12)}
    scenario.update({
        'task_version': VERSION, 'task_revision': 4, 'interaction_mode': 'none',
        'timezone': 'Asia/Shanghai', 'vertical_unit': 'm', 'expected_outlets': 1,
        'outlet_semantics': 'basin_outlet',
        'organization_mode': 'event_collection' if multiple else 'continuous',
        'evaporation_mapping': {'source': 'E0', 'target': 'PET', 'factor': 1.0},
        'repair_authorized': False, 'parameter_change_authorized': False,
        'synthetic_supplements_authorized': True,
        'time': {'source_timezone_mode': 'local_naive', 'timezone': 'Asia/Shanghai',
                 'output_timezone_mode': 'offset_aware',
                 'output_rule': 'Localise naive source timestamps to Asia/Shanghai; every output time/start/end/peak timestamp must include an explicit offset. UTC Z and +08:00 denote equivalent instants.',
                 'timestamp_semantics': 'interval_end', 'timestep_seconds': 3600},
        'variables': {
            'GZ_in': {'unit': 'm3/s', 'semantics': 'observed basin outlet discharge'},
            'GB_out': {'unit': 'm3/s', 'semantics': 'upstream reservoir release; used only where external_inflow is specified'},
            'avg_rain': {'unit': 'mm/step', 'semantics': 'supplied basin mean precipitation depth'},
            '*_rain': {'unit': 'mm/step', 'semantics': 'station precipitation depth; source IDs match stations.csv'},
            'E0': {'unit': 'mm/step', 'semantics': 'benchmark-declared evaporation forcing; PET mapping above is explicitly authorised'},
        },
        'spatial_processing': {'analysis_buffer_km': 3, 'vertical_unit': 'm',
            'cell_inclusion': 'center', 'd8_convention': 'Whitebox',
            'depression_treatment': 'fill', 'stream_burning': False,
            'station_aggregation': 'Thiessen polygon area weights clipped to each target unit',
            'min_coverage_fraction': 1.0, 'coordinate_units': 'metres in the analysis grid'},
        'routing_initialization': 'For each independent input series, initial routed flow equals its first inflow value; no state carryover between events.',
        'alignment': {'observed_column': 'GZ_in', 'unit': 'm3/s',
            'outlet_id': 'benchmark_outlet', 'warmup_policy': 'exclude warmup from scoring',
            'time_matching': 'exact timestamps; compare the same scored samples'},
        'evaluation': {'metric_step_hours': 24 if (family, n) == ('model', 6) else 1,
            'volume_unit': 'm3', 'event_summary_columns': ['nse', 'rmse', 'mae',
                'volume_error_relative', 'peak_error_relative', 'peak_time_error_hours'],
            'event_summary_statistics': ['mean', 'median', 'min', 'max', 'count', 'p10', 'p90'],
            'event_segmentation': 'For analysis-001/002, use the supplied event_parameters on observed discharge and basin rainfall, not arbitrary calendar windows.',
            'causality': 'Performance metrics do not establish causal attribution'},
        'implementation_choices': ['tools', 'programming language', 'execution order',
            'equivalent implementation', 'diagnosis and retry within the resource budget'],
        'scientific_constraints': ['specified models and parameters', 'original observations remain unchanged',
            'declared state organization', 'declared scoring samples', 'provenance and units'],
    })
    models={1:'lumped XAJ followed by standalone Muskingum',2:'lumped XAJ followed by standalone Muskingum',
        3:'lumped XAJ followed by standalone Muskingum',4:'lumped XAJ followed by standalone Muskingum',
        5:'lumped DHF',6:'daily GR4J',7:'semi-distributed XAJ',8:'semi-distributed XAJ',
        9:'semi-distributed XAJ',10:'semi-distributed XAJ',
        11:'lumped XAJ followed by standalone Muskingum, DE calibration',
        12:'lumped XAJ followed by standalone Muskingum, DE calibration'}
    scenario['task_science']={
        'active_forward_model':models[n] if family=='model' else 'none; preprocessing or existing-result analysis only',
        'parameter_scope':'Use only the model named here. Other supplied model parameter blocks are contextual and do not select an additional model.',
        'standalone_channel_parameters':{'K':'route_k_hours','X':'route_x','applies_to_model_tasks':[1,2,3,4,11,12]},
        'semi_model_parameters':'semi_parameters; internal channel routing uses xaj.KE, xaj.XE and time.step_seconds inside this block',
        'external_inflow':'Only use external inflow when this task has an external_inflow declaration; other available release columns do not authorize injection.',
        'analysis_members':(['dhf','semi'] if n in [1,3] else ['dhf'] if n==2 else []) if family=='analysis' else [],
    }
    scenario['model_initialization']={
        'lumped_xaj':'Use WUM_init/WLM_init/WDM_init/S1/FR1/Q in lumped_parameters; propagate continuous states, reset to those values for each independent event.',
        'dhf':{'warmup_initial_states':{'sa0':0.0,'ua0':0.0,'ya0':0.5},
            'warmup_steps':12,'semantics':'Run the first 12 forcing rows from these states, then propagate the resulting states over the remaining rows; exclude warmup rows from scoring, with no post-warmup override.',
            'balance_tolerance_fraction':0.01},
        'gr4j':{'production_store':0.0,'routing_store':0.0,'unit_hydrograph_registers':'all zeros',
            'warmup_days':2,'semantics':'Propagate states over all daily forcing rows; exclude the first two days from scoring.',
            'balance_tolerance_fraction':0.05},
        'semi_xaj':'Use semi_parameters.initial, semi_parameters.warmup_steps and semi_parameters.simulation; only that supplied initial-state block selects the semi model states.',
    }
    scenario['baseflow_initialization']={'method':'Eckhardt, one forward pass',
        'initial_baseflow':'first observed discharge in each independent input series',
        'bounds':'clip each filtered baseflow to [0, observed discharge]'}
    if (family,n)==('model',10):
        scenario['routing_stability_audit']={
            'target':'routing_audit.json','scope':'internal semi-distributed XAJ channel routing',
            'K_source':'semi_parameters.xaj.KE','X_source':'semi_parameters.xaj.XE',
            'step_source':'semi_parameters.time.step_seconds','K_unit':'hours',
            'step_conversion':'dt_hours = step_seconds / 3600',
            'coefficient_order':['C0','C1','C2'],
            'definition':'den=K*(1-X)+dt_hours/2; C0=(dt_hours/2-K*X)/den; C1=(dt_hours/2+K*X)/den; C2=(K*(1-X)-dt_hours/2)/den',
            'stable_definition':'all three coefficients are nonnegative',
            'parameter_change_authorized':False,
            'standalone_channel_exclusion':'route_k_hours and route_x belong to a different routing scope and must not be used for this audit',
        }
    if (family,n)==('model',6):
        scenario['daily_aggregation']['grouping']='Group hourly rows by the local calendar date of their supplied timestamps; label each group at that date 00:00:00+08:00. This fixed benchmark grouping is explicit, including the midnight sample.'
    scenario['optimizer'].update({'schema_version': '1.0', 'algorithm': 'de', 'max_failed_evaluations': 2})
    stations=(family=='data' and n in {4,5,7}) or (family=='model' and n in {7,8,9,10})
    pet=(family,n) in {('data',7),('model',5),('model',6)}
    ids=list(pd.read_csv(data/'stations.csv').source_id) if stations else ['basin']
    scenario['forcing_selection']={
        'rainfall_scope':'station' if stations else 'supplied basin mean',
        'rainfall_columns':'SOURCE_ID_rain for each source_id in stations.csv' if stations else 'avg_rain',
        'source_ids':ids,'rainfall_variable':'P',
        'evaporation_source_column':'E0','evaporation_output_variable':'PET' if pet else 'E0',
        'evaporation_rule':'apply the declared E0->PET factor 1.0' if pet else 'retain E0 as E0; the authorised PET mapping is not used by this task',
        'station_evaporation_rule':'The supplied basin E0 depth is attached unchanged to each declared station ID for this benchmark spatial representation.' if stations else 'single basin source_id=basin',
        'standardised_forcing_schema':'time,source_id,variable,depth_mm; emit only the declared source IDs, not other available stations',
        'model_forcing_schema':'time,P,PET' if pet else 'time,P,E0',
    }
    if (family,n)==('model',4):
        scenario['variables']['GZ_in']['semantics']='test-only observed incremental catchment discharge in the explicitly declared external-inflow scenario'
    if multiple:
        sources=sorted((data/'raw_events').glob('*.csv'))
        scenario['event_interfaces']=[{'input':p.relative_to(data).as_posix(),'event_id':p.stem,
            'output_prefix':f'window-{p.stem}/' if family=='data' else f'e{i}/'} for i,p in enumerate(sources)]
    scenario['extracted_event_ids']='Integer IDs 1,2,... in chronological extracted-event order, independently within each observation window.'
    scenario['event_parameters'].update({'min_peak_flow_m3_s': None, 'min_event_volume_m3': None,
        'shape_filter': {'jump_window_steps': 2, 'min_jump_fraction': 0.1,
            'min_plateau_duration_hours': 24.0, 'min_plateau_fraction': 0.5, 'plateau_range_fraction': 0.005}})
    scenario['quality_control']={'flow_missing_policy':'error','flow_duplicate_policy':'error',
        'flow_edge_missing':'error','balance_tolerance_fraction':0.001,'routing_volume_tolerance':0.02}
    scenario['routing']={'layout':'single','reaches':1,'combine':'sum','output_column':'Q_total',
        'local_inflow_column':'Qt','local_route_id':'local','external_route_id':'reservoir'}
    scenario['figure']={'language':'zh','selection':'all','pixel_size':[2400,1200],
        'total_volume_display_unit':'10^8 m3','style':'/public/programs/visualization-reporting/assets/atlas-style-v1.json'}
    if (data/'dem_100m.tif').exists():
        import rasterio
        with rasterio.open(data/'dem_100m.tif') as dataset:
            scenario['spatial_processing']['dem_crs'] = dataset.crs.to_string()
            scenario['spatial_processing']['target_crs'] = dataset.crs.to_string()
        import geopandas as gpd
        scenario['spatial_processing']['basin_crs'] = gpd.read_file(data/'basin.gpkg').crs.to_string()
    if family == 'model' and n == 6:
        scenario['daily_aggregation'].update({'calendar': 'Asia/Shanghai local days',
            'grouping_rule':'group by the local calendar date of each source timestamp, as declared for this benchmark',
            'time_label': 'local day start', 'E0': 'sum', 'avg_rain': 'sum',
            'PET_mapping': scenario['evaporation_mapping'], 'output_file': 'daily.csv'})
    if family == 'model' and n in {11, 12}:
        scenario['calibration'] = {'algorithm': 'de', 'objective': 'rmse', 'direction': 'minimize',
            'adapter_interface': '/public/physical_calibration.py (optional equivalent implementation)',
            'objective_consistency_tolerance': 1e-8, 'validation': 'lock best parameters before validation',
            'state': 'propagate over full continuous record; independently initialize each event',
            'fixed': {'parameters': scenario['lumped_parameters'], 'area_km2': scenario['area_km2'],
                'route_k': scenario['route_k_hours'], 'route_x': scenario['route_x'],
                'step_hours': 1.0, 'warmup_steps': 12}}
    if family == 'analysis' and n == 3:
        scenario['bma'].update({'train_start': '2023-08-01T12:00:00+08:00',
            'predict_end': '2023-08-31T23:00:00+08:00', 'members': ['dhf', 'semi'],
            'distribution': 'censored_gaussian', 'initialization': 'multi-start; convergence and likelihood consistency required',
            'n_starts':5,'quantiles':[0.05,0.5,0.95],
            'prediction_interface_defaults':{'max_iter':500,'tol':1e-8,'random_state':None}})
    if family == 'analysis' and n == 4:
        scenario['review'] = {'scope': 'scored sample independence only',
            'calibration_samples': 'calibration_scored.csv', 'validation_samples': 'validation_scored.csv',
            'excluded_warmup_steps': 12, 'scoring_mask': 'only rows where scored=true',
            'independence_rule': 'nonempty disjoint scored timestamps',
            'limitations': 'Independent scoring does not establish model accuracy or causality'}


def write_input_guide(data, family, n):
    rows=[]
    for path in sorted(data.rglob('*')):
        if not path.is_file():
            continue
        rel=path.relative_to(data).as_posix()
        if rel=='raw.csv' or rel.startswith('raw_events/'):
            role='authorised calculation input, with labelled synthetic supplements'
        elif rel=='original.csv' or rel.startswith('original_events/'):
            role='original observations; preserve all values and missing entries'
        elif 'supplement' in rel:
            role='synthetic supplement provenance; not repaired observations'
        elif rel.startswith('members/'):
            role='supplied physical simulation and provenance for independent analysis'
        else:
            role='upfront scenario, source evidence or spatial/scoring input'
        entry={'path':rel,'role':role,'sha256':sha(path)}
        if path.suffix=='.csv':
            entry['columns']=list(pd.read_csv(path,nrows=0).columns)
        rows.append(entry)
    write_json(data/'input_inventory.json',{'task_version':VERSION,'files':rows})
    (data/'INPUT_GUIDE.md').write_text(
        '# 完整输入资料\n\n本题所有必要事实与授权在启动前提供，运行中没有用户信息补充。\n\n'
        '读取 scenario.json 的变量、时间、空间、模型、初始状态与评价设定；'
        'input_inventory.json 列出各资料的角色、列名和 SHA-256。'
        'raw.csv 或 raw_events/*.csv 是允许使用合成补充的计算资料；'
        'original.csv 或 original_events/*.csv 是只读原始观测，缺测必须保留。'
        '补充值逐项记录在 supplements 文件，不能称为实测。\n\n'
        '已有空间成果与 members 中的物理模型成果属于题目输入，可以读取，'
        '不是本题标准答案。新成果按 OUTPUT_INTERFACES.md 与 output_interfaces.json 输出。\n\n'
        '模型及指定参数、单位、warm-up、组织模式和评分样本不能自行改变；'
        '可自行实现等价计算并排错重试。可用程序及其接口在 /public，'
        '不要求调用某个程序。工具文档中的确认要求由本题启动前的显式设定满足。\n',encoding='utf-8')


def shape(value):
    if isinstance(value,dict):
        return {k:shape(v) for k,v in value.items()}
    if isinstance(value,list):
        return [shape(value[0])] if value else []
    if value is None:
        return 'nullable'
    if isinstance(value,bool):
        return 'boolean'
    if isinstance(value,(int,float)):
        return 'number'
    return 'string'


def write_output_interfaces(data,w,outputs,spec):
    interfaces={}
    for rel in outputs:
        path=w/rel
        entry={'format':path.suffix.lstrip('.')}
        if path.suffix=='.csv':
            entry['columns']=list(pd.read_csv(path,nrows=0).columns)
            entry['ordering']='chronological within each event/unit; match scientific rows and units'
            entry['timestamps']='All temporal fields require explicit timezone offsets; local naive inputs must first be localised to the supplied timezone.'
        elif path.suffix=='.json':
            doc=json.loads(path.read_text(encoding='utf-8'))
            # The public exchange contract must not demand reference-factory
            # adapter/config files from an independent implementation.
            if path.name=='result.json' and isinstance(doc.get('inputs'),dict):
                required_roles={d['field'].split('.',1)[1] for d in spec['dependencies']
                    if d['downstream']==rel and d['field'].startswith('inputs.')}
                entry['optional_input_roles']=[k for k in doc['inputs'] if k not in required_roles]
                doc['inputs']={k:v for k,v in doc['inputs'].items() if k in required_roles}
            entry['structure']=shape(doc)
            entry['metadata_policy']='Field structure is the public interface; generated timestamps, messages, implementation names and input filenames are not reference-answer values. References must be relative and SHA-256 valid.'
            if rel=='routing_audit.json':entry['scientific_definition']='Use scenario.json routing_stability_audit: semi_parameters.xaj.KE/XE and semi_parameters.time.step_seconds; coefficients ordered C0,C1,C2. Do not use standalone route_k_hours/route_x.'
        else:
            entry['semantics']='scientific spatial/figure artifact; preserve declared grid, units and coordinate system'
        interfaces[rel]=entry
    # Required scalar bindings are input facts, not calculated reference values.
    settings=[{'key':x['key'],'source':x['source'],'field':x['field'],
               'output_bindings':[{'target':b['target'],'field':b['field']} for b in x['bindings']]}
              for x in spec['provided_settings']]
    write_json(data/'output_interfaces.json',{'task_version':VERSION,'interaction_mode':'none',
        'outputs':interfaces,'provided_settings':settings,
        'decision':{'status':'deliverable','reason':'scientific_contracts_satisfied',
            'limitations':'nonempty list including synthetic-data limitations and implementation choices',
            'evidence':'nonempty list of {path, sha256}, relative to workspace root'},
        'result_manifest':'Scientific inputs/artifacts: role -> {path, sha256}, relative to manifest parent. Optional config/adapter input roles may be omitted; equivalent implementations may use their own upstream filenames. Every reference that is declared must resolve and have a valid SHA-256.',
        'calibration_evidence':'Trace rows contain status, objective and param:NAME columns; at most 128 evaluations, objective independently replayable, best parameters locked before validation. No prescribed optimizer trajectory.',
        'numerical_tolerance':{'atol':1e-6,'rtol':1e-6}})
    (data/'OUTPUT_INTERFACES.md').write_text(
        '# 公开成果接口\n\noutput_interfaces.json 给出全部必需成果的路径、表列及 JSON 字段结构，'
        '这些是科学交换接口，不限制工具或实现。表格交付须保持时间、事件和空间单元的对应关系。'
        '所有输出时间字段须带时区偏移，原始无时区时间先按 Asia/Shanghai 本地化；UTC Z 与 +08:00 的同一时刻等价。'
        '按 scenario.json 的 forcing_selection 选择实际驱动字段、空间代表性、source_id 和 E0/PET 变量；其它可用列不代表本题要求使用。'
        'JSON 的参数取值来自 scenario.json；计算结果必须来自实际计算。'
        '元数据中的消息、生成时间、工具名称不要求复制任何参考值。\n\n'
        '中间输入可自行命名；result.json 的 inputs 和 artifacts 保持声明的科学角色，'
        'optional_input_roles 所列临时配置／适配器引用可以省略，无需保留参考程序的配置文件；'
        '引用相对文件路径及实际 SHA-256。不要伪造程序运行状态。'
        'decision.json 使用公开的 status/reason，说明科学限制和实现选择，引用实际证据。\n\n'
        '若交付 analysis-001/002/003 的 conclusions.json，causality=not_established，'
        'scoring=same_samples_excluding_warmup，units=m3/s；independent_prediction 仅'
        ' analysis-003 为 true。比较题 ranking_rmse 按实际公平评分后的 RMSE 排序。'
        'report.md 以 JSON 代码块绑定 conclusions.json，并列出 decision.json 的证据路径与哈希。\n',encoding='utf-8')
