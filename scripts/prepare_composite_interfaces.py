"""Create common command-only documentation; no domain skill prose or task recipes."""
import importlib.metadata
import json
import sys
import yaml
from composite_common import ROOT,PUBLIC,native,write_json,sha

def main():
    index=json.loads((PUBLIC/'programs.json').read_text(encoding='utf-8'));rows=[]
    for ref,entry in index.items():
        record=native(ROOT,ref,['--help']);rows.append('## '+ref+'\n\n`python /public/native_bootstrap.py /public/programs/'+ref+'/'+entry['entrypoint']+' [arguments]`\n\n```text\n'+record['stdout'].strip()+'\n```\n')
    (PUBLIC/'PROGRAM_INTERFACES.md').write_text('# Public computational interfaces\n\nSame programs, parameters, file interfaces and units are available in both conditions. These interfaces are not task recipes. Each program writes a manifest binding its inputs and outputs. Basic file, variable, unit and parameter interfaces are also listed in `PROGRAM_DATA_CONTRACTS.json`; this common document omits workflow instructions and task solutions.\n\n'+'\n'.join(rows)+'\n## Unattended scientific settings\n\nAll required facts and permissions are declared in scenario.json before execution. No user confirmation service is available. Generic program warmup confirmed=true refers to the upfront declarations, not an interactive answer.\n',encoding='utf-8')
    contracts={}
    for ref in index:
        path=ROOT/'docs/composite-contracts'/ref/'data-contract.yaml'
        if path.is_file():
            source=yaml.safe_load(path.read_text(encoding='utf-8'))
            contracts[ref]={key:source[key] for key in ['schema_version','inputs','outputs','parameters','warmup_period','simulation_period'] if key in source}
    write_json(PUBLIC/'PROGRAM_DATA_CONTRACTS.json',contracts)
    packages=['jsonschema' ,'numpy','openpyxl','pandas','PyYAML','scipy','xlsxwriter','geopandas','matplotlib','Pillow','pyproj','rasterio','scikit-learn','shapely','whitebox','joblib','xlrd','pytest']
    (ROOT/'runtime/requirements.lock.txt').write_text('\n'.join(p+'=='+importlib.metadata.version(p) for p in packages)+'\n',encoding='utf-8')
    exe=ROOT/'.cache/whitebox/extracted/WhiteboxTools_win_amd64/WBT/whitebox_tools.exe'
    receipt_path=ROOT/'docs/composite-runtime-receipt.json'
    receipt=json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else {'docker_available':False,'linux_binary_verified':False,'formal_ready':False,'formal_runs':0,'real_agents_run':0,'blocking_items':['Container, network, CLI model/settings and live budget certification pending']}
    receipt.update({'python':sys.version.split()[0],'environment':'HydroTune-eval','whitebox_windows_sha256':sha(exe),'whitebox_source':'https://www.whiteboxgeo.com/WBT_Windows/WhiteboxTools_win_amd64.zip','cli_sources':{'codex':'https://github.com/openai/codex','opencode':'https://github.com/anomalyco/opencode','qwen':'https://github.com/QwenLM/qwen-code'}})
    write_json(receipt_path,receipt)
if __name__=='__main__':main()
