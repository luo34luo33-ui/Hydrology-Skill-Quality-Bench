param(
    [string]$Python = 'C:\Users\DELL\miniconda3\envs\HydroTune-eval\python.exe',
    [string]$Lock = 'runtime/experiment.lock.json',
    [string]$Output = 'results/overnight-20261004',
    [string]$Deadline = '2026-10-05T10:00:00+08:00'
)
$ErrorActionPreference = 'Stop'
$taskProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskProjectRoot
$env:PATH = 'C:\Users\DELL\AppData\Local\Programs\DockerDesktop\resources\bin;' + $env:PATH
$env:PYTHONIOENCODING = 'utf-8'
# Preflight refuses an incomplete or uncertified configuration; no Agent starts.
$env:HSQB_LOCK_PATH = (Resolve-Path -LiteralPath $Lock).Path
& $Python -c "import os,json,sys; from harness.composite_runtime import preflight; r=preflight(os.environ['HSQB_LOCK_PATH']); print(json.dumps(r,ensure_ascii=False,indent=2)); sys.exit(0 if r['ready'] else 2)"
if ($LASTEXITCODE -ne 0) { throw 'Preflight failed. Background process was not started.' }
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$taskOutputPath = (Resolve-Path -LiteralPath $Output).Path
$taskArguments = @('-m','harness.experiment','--lock',('"' + $env:HSQB_LOCK_PATH + '"'),
    '--clis','codex,opencode,qwen','--workers','3','--output',('"' + $taskOutputPath + '"'),
    '--deadline',$Deadline,'--resume','--execute')
$taskProcess = Start-Process -FilePath $Python -ArgumentList $taskArguments `
    -WorkingDirectory $taskProjectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $taskOutputPath 'dispatcher.stdout.log') `
    -RedirectStandardError (Join-Path $taskOutputPath 'dispatcher.stderr.log')
Set-Content -LiteralPath (Join-Path $taskOutputPath 'dispatcher.pid') -Value $taskProcess.Id -Encoding ascii
Start-Sleep -Seconds 3
$taskProcess.Refresh()
if ($taskProcess.HasExited) { throw 'Dispatcher exited during startup. Inspect dispatcher.stderr.log.' }
Write-Output ('Dispatcher started. PID=' + $taskProcess.Id + '; output=' + $taskOutputPath)
