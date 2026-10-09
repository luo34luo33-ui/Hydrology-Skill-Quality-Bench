"""Container-only atomic CLI initialization. Identical instructions for all arms."""
import json
import os
from pathlib import Path
import shutil
import sys

cli, model, effort, prompt = sys.argv[1:]
home = Path.home(); workspace = Path('/work'); source = Path('/provider-config')
mapping = {'codex': ('.codex', ['config.toml']),
           'opencode': ('.config/opencode', ['opencode.json']),
           'qwen': ('.qwen', ['settings.json']), 'codebuddy': ('.codebuddy', ['settings.json'])}
directory, files = mapping[cli]
environment = source / 'provider_environment.json'
if environment.is_file():
    for key, value in json.loads(environment.read_text()).items():
        if not key.endswith(('_API_KEY', '_BASE_URL', '_HOST')):
            raise ValueError('unsupported provider environment field')
        os.environ[key] = str(value)
for name in files:
    origin = source / cli / name
    if origin.is_file():
        dest = home / directory / name; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(origin, dest)
skills = home / '.agents/skills'
if skills.exists():
    for dest in [home / '.qwen/skills', home / '.config/opencode/skills', home / '.codebuddy/skills']:
        dest.parent.mkdir(parents=True, exist_ok=True); dest.symlink_to(skills, target_is_directory=True)
    # Qwen's user/extension/bundled levels are disabled. Expose only this frozen
    # package through project discovery, also visible to all workspace readers.
    for dest in [workspace / '.agents/skills', workspace / '.qwen/skills', workspace / '.codebuddy/skills']:
        dest.parent.mkdir(parents=True, exist_ok=True); dest.symlink_to(skills, target_is_directory=True)
for name in ['QWEN.md', 'CODEBUDDY.md']:
    (workspace / name).write_bytes((workspace / 'AGENTS.md').read_bytes())
shutil.copytree('/opt/whitebox', '/tmp/whitebox', dirs_exist_ok=True)
os.environ.update({'WBT_PATH': '/tmp/whitebox', 'HSQB_WHITEBOX_DIR': '/tmp/whitebox',
                  'DISABLE_TELEMETRY': '1', 'DISABLE_AUTOUPDATER': '1'})
if cli == 'codebuddy':
    cfg_path = home / '.codebuddy/settings.json'
    cfg = json.loads(cfg_path.read_text())
    if effort != 'provider-default':
        cfg['reasoningEffort'] = effort
    else:
        cfg.pop('reasoningEffort', None)
    if effort != 'provider-default':
        cfg['reasoningEffort'] = effort
    else:
        cfg.pop('reasoningEffort', None)
    if any(k in cfg for k in ['hooks', 'mcpServers', 'enabledPlugins']):
        raise ValueError('CodeBuddy provider config must not import customizations')
    cfg['permissions'] = {'defaultMode': 'dontAsk', 'allow': ['Read(/work/**)', 'Write(/work/**)', 'Edit(/work/**)',
        'Bash("/opt/conda/envs/HydroTune-eval/bin/python" ./task_compute.py)'],
        'deny': ['WebFetch', 'WebSearch', 'Agent', 'Task', 'AskUserQuestion'], 'disableBypassPermissionsMode': 'disable'}
    if skills.exists():
        import yaml
        for skill in skills.glob('*/SKILL.md'):
            text = skill.read_text()
            if text.startswith('---'):
                metadata = yaml.safe_load(text.split('---', 2)[1]); name = metadata.get('name')
                if name: cfg['permissions']['allow'].append('Skill(' + name + ')')
    cfg_path.write_text(json.dumps(cfg))
    # The same command interface is present whether public programs/skills exist or not.
    note = '\nWrite task_compute.py for computation and invoke exactly "/opt/conda/envs/HydroTune-eval/bin/python" ./task_compute.py through Bash.\n'
    for name in ['AGENTS.md', 'CODEBUDDY.md']:
        with (workspace / name).open('a') as stream: stream.write(note)
    argv = ['codebuddy', '-p', prompt, '--model', model, '--output-format', 'stream-json', '--verbose',
            '--permission-mode', 'dontAsk', '--settings', str(cfg_path), '--setting-sources', 'user',
            '--strict-mcp-config', '--no-session-persistence', '--tools', 'Read,Write,Edit,Glob,Grep,Bash,Skill']
else:
    from cli_events import command
    if cli == 'qwen':
        p = home / '.qwen/settings.json'; config = json.loads(p.read_text())
        config.setdefault('model', {})['name'] = model
        if effort != 'provider-default': config['model']['reasoningEffort'] = effort
        else: config['model'].pop('reasoningEffort', None)
        p.write_text(json.dumps(config))
    if cli == 'qwen':
        p = home / '.qwen/settings.json'; config = json.loads(p.read_text())
        config.setdefault('model', {})['name'] = model
        if effort != 'provider-default': config['model']['reasoningEffort'] = effort
        else: config['model'].pop('reasoningEffort', None)
        p.write_text(json.dumps(config))
    if cli == 'opencode':
        os.environ.update({'OPENCODE_DISABLE_CLAUDE_CODE': 'true', 'OPENCODE_DISABLE_DEFAULT_PLUGINS': 'true',
                           'OPENCODE_DISABLE_LSP_DOWNLOAD': 'true', 'OPENCODE_AUTO_SHARE': 'false'})
        p = home / '.config/opencode/opencode.json'; config = json.loads(p.read_text())
        config.setdefault('permission', {})['skill'] = 'allow' if skills.exists() else 'deny'
        config['skills'] = {'paths': [str(skills)] if skills.exists() else []}
        p.write_text(json.dumps(config))
    argv = command(cli, model, effort, prompt)
os.execvp(cli, argv)
