"""Offline check against the installed CodeBuddy matcher; never starts an Agent."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.atomic_cli_support import codebuddy_permissions, resolve_cli


def verify(workspace: Path) -> dict:
    prefix = resolve_cli("codebuddy")
    if len(prefix) != 2:
        raise ValueError("Offline matcher check requires the installed Node package")
    bundle = Path(prefix[1]).parent.parent / "dist/codebuddy-headless.js"
    if not bundle.is_file():
        raise ValueError("Installed CodeBuddy headless bundle not found")
    # Load the original matcher module in memory, replacing only the CLI entry.
    # The installed program is untouched; login/model/network entry never runs.
    javascript = r'''
const fs=require('fs'), Module=require('module'), path=require('path');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
let source=fs.readFileSync(input.bundle,'utf8');
const start=source.indexOf('class PermissionUtils');
if(start<0)throw Error('Unsupported matcher bundle');
const matches=[...source.slice(0,start).matchAll(/(\d+)\(eA,el,ec\)\{/g)];
const id=matches.at(-1)[1];
const moduleHead=source.slice(matches.at(-1).index,start);
const types=moduleHead.match(/ev=ec\((\d+)\)/);
const entry=/var __webpack_exports__=__webpack_require__\(__webpack_require__\.s=\d+\);return __webpack_exports__/;
if(!types || !entry.test(source))throw Error('Unsupported matcher entry');
source=source.replace(entry,`return {P:__webpack_require__(${id}).N,T:__webpack_require__(${types[1]}).H5}`);
const m=new Module(input.bundle);m.filename=input.bundle;
m.paths=Module._nodeModulePaths(path.dirname(input.bundle));m._compile(source,input.bundle);
const {P,T}=m.exports, checks=[];
function check(name,actual,expected){checks.push({name,actual,expected});if(actual!==expected)throw Error(name);}
process.chdir(input.workspace);
for(const tool of ['Read','Write','Edit']){
 const rules=P.matchPermissionRules(input.permissions.allow,[tool]);
 for(const file of ['task_compute.py','components/result.json','.codebuddy/skills/x/SKILL.md']){
  for(const candidate of [file,'./'+file,input.workspace+'/'+file]){
   check(tool+': '+candidate,P.checkAllowPermissionRules(rules,[{type:T.FilePath,value:candidate}]),true);
  }
 }
 for(const candidate of ['../outside.txt',input.workspace+'-other/result.json']){
  check(tool+': reject '+candidate,P.checkAllowPermissionRules(rules,[{type:T.FilePath,value:candidate}]),false);
 }
}
check('old relative pattern fails',P.matchFileRule(input.workspace+'/task_compute.py','./**'),false);
for(const tool of ['Bash','PowerShell']){
 const rules=P.matchPermissionRules(input.permissions.allow,[tool]);
 const command=tool==='Bash'?input.bash:input.powershell;
 check(tool+': fixed interpreter',P.checkAllowPermissionRules(rules,[{type:T.Command,value:command}]),true);
 for(const bad of ['python ./task_compute.py',command+'; whoami',command+' > ../outside.txt']){
  check(tool+': reject '+bad,P.checkAllowPermissionRules(rules,[{type:T.Command,value:bad}]),false);
 }
}
console.log(JSON.stringify({passed:true,checks,matcher_module:id}));
'''
    from scripts.atomic_cli_support import codebuddy_compute_commands
    bash, powershell = codebuddy_compute_commands()
    payload = {"bundle": str(bundle), "workspace": workspace.resolve().as_posix(),
               "permissions": codebuddy_permissions(workspace, []),
               "bash": bash, "powershell": powershell}
    # Use -e for code, stdin for structured data, without a shell.
    completed = subprocess.run([prefix[0], "-e", javascript], input=json.dumps(payload),
                               capture_output=True, text=True, timeout=30, check=False)
    if completed.returncode:
        raise RuntimeError("Native permission matcher verification failed: " + completed.stderr[-1500:])
    return json.loads(completed.stdout)


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory(prefix="hsqb-codebuddy-permission-probe-") as temporary:
        print(json.dumps(verify(Path(temporary)), ensure_ascii=False, indent=2))
