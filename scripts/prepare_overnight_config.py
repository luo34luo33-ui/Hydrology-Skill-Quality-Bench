"""Public-only clean CLI configuration, never copies a real credential."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.runner import _sha256_tree
from harness.composite_runtime import COMMON_START

def main():
    p=ROOT/'runtime/experiment.lock.json';lock=json.loads(p.read_text(encoding='utf-8'))
    config=Path.home()/'AppData/Local/HydroTune-bench-runtime/public-config'
    config.mkdir(parents=True,exist_ok=True)
    for cli in ['codex','opencode','qwen']:(config/cli).mkdir(exist_ok=True)
    (config/'codex/config.toml').write_text('''model = "gpt-6.1-sol"
model_reasoning_effort = "medium"
model_provider = "isolated_gateway"
web_search = "disabled"
check_for_update_on_startup = false
[model_providers.isolated_gateway]
name = "Isolated model relay"
base_url = "http://hsqb-provider:8765/backend-api/codex"
wire_api = "responses"
env_key = "HSQB_RELAY_API_KEY"
requires_openai_auth = false
supports_websockets = false
[features]
apps = false
plugins = false
memories = false
multi_agent = false
browser_use = false
computer_use = false
skill_search = false
''',encoding='utf-8')
    settings=json.loads((ROOT/'runtime/opencode-pilot.json').read_text())
    (config/'opencode/opencode.json').write_text(json.dumps(settings,indent=2),encoding='utf-8')
    settings={'model':{'name':'deepseek-v4-pro'},'security':{'auth':{'selectedType':'openai'}},
        'modelProviders':{'openai':[{'id':'deepseek-v4-pro','name':'Frozen DeepSeek V4 Pro',
            'baseUrl':'http://hsqb-provider:8765/v1','envKey':'DEEPSEEK_API_KEY',
            'generationConfig':{'contextWindowSize':1000000}}]},
        'telemetry':{'enabled':False},'mcpServers':{},
        'tools':{'exclude':['web_search','web_fetch','task']}}
    (config/'qwen/settings.json').write_text(json.dumps(settings,indent=2),encoding='utf-8')
    (config/'provider_environment.json').write_text(json.dumps({
        'HSQB_RELAY_API_KEY':'isolated-placeholder-no-real-key',
        'DEEPSEEK_API_KEY':'isolated-placeholder-no-real-key',
        'OPENAI_API_KEY':'isolated-placeholder-no-real-key',
        'OPENAI_BASE_URL':'http://hsqb-provider:8765/v1'}),encoding='utf-8')
    lock['common_config_dir']=str(config);lock['common_config_sha256']=_sha256_tree(config)
    lock['clis']['codex']['auth_source']=str(Path.home()/'.codex/auth.json')
    for cli in ['opencode','qwen']:
        lock['clis'][cli]['credential_store']=str(config.parent/'deepseek.dpapi')
    for cli in lock['clis']:lock['clis'][cli]['config_sha256']=_sha256_tree(config/cli)
    lock['public_programs_sha256']=_sha256_tree(ROOT/'runtime/public')
    lock['skills_sha256']=_sha256_tree(ROOT/'runtime/skills')
    lock['startup_prompt_sha256']=hashlib.sha256(COMMON_START.encode()).hexdigest()
    lock['status']='awaiting_live_certification'
    lock['external_authorization']={'destination':'https://api.deepseek.com','explicit_user_authorization':True,'date':'2026-10-04'}
    p.write_text(json.dumps(lock,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Clean public configuration written; credentials remain host-only.')

if __name__=='__main__':main()
