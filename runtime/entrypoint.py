#!/usr/bin/env python
"""Identical initialization for both conditions. No task solution or answer table."""
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
from cli_events import command

cli,model,effort,prompt=sys.argv[1:]
if cli=='opencode':
    rg=shutil.which('rg')
    if not rg or not os.access(rg,os.X_OK):
        raise RuntimeError('deployment_error: pinned ripgrep is unavailable; native skill discovery cannot run offline')
    check=subprocess.run([rg,'--version'],capture_output=True,text=True)
    if check.returncode or not check.stdout.startswith('ripgrep 15.1.0'):
        raise RuntimeError('deployment_error: expected executable ripgrep 15.1.0')
    os.environ.update({'OPENCODE_DISABLE_AUTOUPDATE':'true','OPENCODE_DISABLE_CLAUDE_CODE':'true','OPENCODE_DISABLE_DEFAULT_PLUGINS':'true','OPENCODE_DISABLE_LSP_DOWNLOAD':'true','OPENCODE_AUTO_SHARE':'false'})
home=Path.home();source=Path('/provider-config')
# Approved common configuration contains credentials/provider settings only.
# It must not contain skill directories, memories, instructions, or fallback models.
mapping={'codex':('.codex', ['config.toml','auth.json']), 'opencode':('.config/opencode',['opencode.json']), 'qwen':('.qwen',['settings.json','oauth_creds.json'])}
directory,files=mapping[cli]
for filename in files:
    src=source/cli/filename
    if src.is_file():
        dest=home/directory/filename;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
skills=home/'.agents/skills'
if skills.exists():
    for dest in [home/'.qwen/skills',home/'.config/opencode/skills']:
        dest.parent.mkdir(parents=True,exist_ok=True);dest.symlink_to(skills,target_is_directory=True)
if cli=='opencode':
    settings_path=home/'.config/opencode/opencode.json'
    settings=json.loads(settings_path.read_text())
    settings['permission']['skill']='allow' if skills.exists() else 'deny'
    settings_path.write_text(json.dumps(settings),encoding='utf-8')
shutil.copytree('/opt/whitebox','/tmp/whitebox',dirs_exist_ok=True)
os.environ['WBT_PATH']='/tmp/whitebox';os.environ['HSQB_WHITEBOX_DIR']='/tmp/whitebox'
envpath=source/'provider_environment.json'
if envpath.is_file():
    for key,value in json.loads(envpath.read_text()).items():
        if not key.endswith(('_API_KEY','_BASE_URL','_HOST')):raise ValueError('unsupported provider environment field')
        os.environ[key]=str(value)
os.execvp(cli,command(cli,model,effort,prompt))
