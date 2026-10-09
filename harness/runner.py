"""Task discovery, isolated staging, agent execution, and regrading."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import platform
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from harness import __version__, grader, reporter, schemas
from harness.filesystem import filesystem_path, copy_file, execution_workspace, normal_path


def discover_tasks(
    tests_root: str | Path = "tests",
    domain: str | None = None,
    test_id: str | None = None,
    skill: str | None = None,
    suite: str = 'atomic',
) -> list[dict[str, Any]]:
    root = Path(filesystem_path(tests_root))
    if not root.is_dir():
        return []
    tasks: list[dict[str, Any]] = []
    if suite not in {'atomic','composite','all'}: raise ValueError('invalid suite')
    composite_root=root if root.name.startswith('composite_tests') else root.parent/'composite_tests'
    roots=[root] if suite=='atomic' else ([composite_root] if suite=='composite' else [root,composite_root])
    for path in sorted(p for r in roots for p in r.glob("*/*/task.json")):
        task = schemas.load_json(path)
        if domain and task.get("domain") != domain:
            continue
        if test_id and task.get("id") != test_id:
            continue
        if skill and task.get("primary_skill") != skill and skill not in task.get("secondary_skills", []):
            continue
        tasks.append({"task": task, "task_path": path.resolve(), "task_dir": path.parent.resolve()})
    return tasks


def validate_tests(
    tests_root: str | Path = "tests",
    domain: str | None = None,
    test_id: str | None = None,
    skill: str | None = None,
    suite: str = 'atomic',
) -> list[dict[str, str]]:
    found = discover_tasks(tests_root, domain, test_id, skill, suite)
    errors: list[dict[str, str]] = []
    if not found:
        errors.append({"path": str(Path(tests_root)), "error": "no matching tasks found"})
        return errors
    ids: dict[str, Path] = {}
    for item in found:
        task_id = item["task"].get("id")
        if task_id in ids:
            errors.append(
                {
                    "path": str(item["task_path"]),
                    "error": f"duplicate task id also used by {ids[task_id]}",
                }
            )
        else:
            ids[task_id] = item["task_path"]
        for error in schemas.validate_task(item["task"], item["task_dir"]):
            errors.append({"path": str(item["task_path"]), "error": error})
    return errors


def _sha256_file(path: Path) -> str:
    path=Path(filesystem_path(path))
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_tree(path: Path) -> str:
    path=Path(filesystem_path(path))
    digest = hashlib.sha256()
    files = (
        item
        for item in path.rglob("*")
        if item.is_file()
        and "__pycache__" not in item.parts
        and ".git" not in item.parts
        and item.suffix.lower() not in {".pyc", ".pyo"}
    )
    for file_path in sorted(files):
        digest.update(file_path.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(_sha256_file(file_path).encode())
    return digest.hexdigest()


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _cli_version(executable: str) -> str | None:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return completed.stdout.strip() or completed.stderr.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def environment_metadata() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "conda_environment": os.environ.get("CONDA_DEFAULT_ENV"),
        "conda_prefix": os.environ.get("CONDA_PREFIX"),
        "codex": _cli_version("codex"),
        "opencode": _cli_version("opencode"),
        "packages": {
            name: _package_version(name)
            for name in (
                "numpy", "pandas", "scipy", "rasterio", "geopandas",
                "shapely", "pyproj", "matplotlib", "Pillow", "whitebox",
            )
        },
        "hsqb": __version__,
    }


def _clean_directory(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"workspace is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def stage_workspace(task: dict[str, Any], task_dir: str | Path, workspace: str | Path) -> Path:
    task_root = Path(filesystem_path(task_dir)).resolve()
    workspace_path = Path(filesystem_path(workspace)).resolve()
    _clean_directory(workspace_path)
    for rel in task["data_files"]:
        source = (task_root / "data" / rel).resolve()
        source.relative_to((task_root / "data").resolve())
        destination = workspace_path / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        copy_file(source, destination)
    reporter.write_json(workspace_path / "task_public.json", schemas.public_task(task))
    from harness.atomic_contracts import stage_contract
    stage_contract(task, task_root, workspace_path)
    return workspace_path


def _command_argv(agent_cmd: str, project_root: Path) -> list[str]:
    argv = shlex.split(agent_cmd, posix=os.name != "nt")
    argv = [item[1:-1] if len(item) >= 2 and item[0] == item[-1] == '"' else item for item in argv]
    if not argv:
        raise ValueError("agent command is empty")
    for index in range(1, len(argv)):
        candidate = Path(argv[index])
        rooted = project_root / candidate
        if not candidate.is_absolute() and rooted.is_file():
            argv[index] = str(rooted.resolve())
            break
    return argv


def _terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def run_agent(
    agent_cmd: str,
    workspace: str | Path,
    public_task_path: str | Path,
    stdout_path: str | Path,
    stderr_path: str | Path,
    timeout_seconds: int,
    project_root: str | Path,
    model: str | None = None,
    effort: str | None = None,
    skills_path: str | Path | None = None,
) -> dict[str, Any]:
    workspace_path = Path(workspace).resolve()
    argv = _command_argv(agent_cmd, Path(project_root).resolve())
    env = os.environ.copy()
    for key in ('BENCHMARK_MODEL', 'BENCHMARK_EFFORT', 'BENCHMARK_SKILLS_PATH'):
        env.pop(key, None)
    env.update(
        {
            "HSQB_TASK_JSON": str(Path(public_task_path).resolve()),
            "HSQB_TEST_DIR": str(workspace_path),
            "HSQB_WORKSPACE": str(workspace_path),
        }
    )
    if model:
        env["BENCHMARK_MODEL"] = model
    if effort:
        env["BENCHMARK_EFFORT"] = effort
    if skills_path:
        env["BENCHMARK_SKILLS_PATH"] = str(Path(skills_path).resolve())
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    start = time.monotonic()
    timed_out = False
    with Path(stdout_path).open("w", encoding="utf-8", errors="replace") as stdout, Path(stderr_path).open(
        "w", encoding="utf-8", errors="replace"
    ) as stderr:
        process = subprocess.Popen(
            argv,
            cwd=workspace_path,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            text=True,
            start_new_session=os.name != "nt",
            creationflags=creationflags,
        )
        try:
            return_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_tree(process)
            try:
                return_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                return_code = process.wait()
    return {
        "argv": argv,
        "return_code": int(return_code),
        "timed_out": timed_out,
        "timeout_seconds": int(timeout_seconds),
        "duration_seconds": time.monotonic() - start,
    }


def _default_output() -> Path:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    return Path("results") / f"run-{timestamp}"


def run_benchmark(
    tests_root: str | Path = "tests",
    domain: str | None = None,
    test_id: str | None = None,
    skill: str | None = None,
    agent_cmd: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    skills_path: str | Path | None = None,
    timeout: int | None = None,
    workspace_root: str | Path | None = None,
    output: str | Path | None = None,
    suite: str = 'atomic',
    runtime_lock: str | Path | None = None,
    composite_cli: str | None = None,
    condition: str | None = None,
    programs_path: str | Path | None = None,
    runtime: str = 'local',
    atomic_cli: str | None = None,
) -> dict[str, Any]:
    from harness.atomic_contracts import resolve_condition, VERSION, tree_digest, stage_programs
    condition = resolve_condition(condition, skills_path, programs_path)
    if condition is not None and suite != 'atomic':
        raise ValueError('three-arm conditions apply to the atomic suite only')
    if runtime == 'isolated' and (suite != 'atomic' or not condition or not runtime_lock or not atomic_cli):
        raise ValueError('isolated atomic runs require --condition, --runtime-lock and --cli')
    if runtime not in {'local', 'isolated'}: raise ValueError('invalid runtime')
    if not agent_cmd and suite!='composite' and runtime != 'isolated':
        raise ValueError("--agent-cmd is required")
    validation_errors = validate_tests(tests_root, domain, test_id, skill,suite)
    if validation_errors:
        raise ValueError("task validation failed: " + "; ".join(item["error"] for item in validation_errors))
    tasks = discover_tasks(tests_root, domain, test_id, skill,suite)
    if condition is not None and any(not x['task'].get('public_contract') for x in tasks):
        raise ValueError('all selected three-arm tasks must have public contracts')
    public_programs = None
    if condition in {'programs-only', 'with-skills'}:
        public_programs = Path(filesystem_path(programs_path or Path(tests_root).resolve().parent / 'runtime/atomic-public')).resolve()
        if not (public_programs / 'programs.json').is_file(): raise ValueError('missing atomic public program bundle')
    if runtime == 'isolated':
        from harness.atomic_runtime import preflight, load_lock
        ready = preflight(runtime_lock, atomic_cli)
        if not ready['ready']: raise ValueError('formal atomic preflight failed: ' + str(ready['issues']))
        atomic_lock = load_lock(runtime_lock, atomic_cli)
        if public_programs and tree_digest(public_programs) != atomic_lock['public_programs_sha256']:
            raise ValueError('selected public program bundle differs from certified lock')
        if condition == 'with-skills' and tree_digest(Path(skills_path).resolve()) != atomic_lock['skills_sha256']:
            raise ValueError('selected skill snapshot differs from certified lock')
        model, effort = atomic_lock['clis'][atomic_cli]['model'], atomic_lock['clis'][atomic_cli]['effort']
        agent_cmd = atomic_cli
        if timeout is not None: raise ValueError('isolated atomic timeout is frozen per task')
    frozen_runtime = None
    if any(x['task'].get('task_kind')=='composite' for x in tasks):
        from harness.composite_runtime import preflight
        if not runtime_lock or not composite_cli:raise ValueError('composite runs require --runtime-lock and --composite-cli')
        ready=preflight(runtime_lock,[composite_cli])
        if not ready['ready']:raise ValueError('formal composite preflight failed: '+str(ready['issues']))
        if timeout is not None:raise ValueError('composite timeout is frozen per task')
        from harness.composite_runtime import load_lock, COMMON_START
        frozen_runtime = load_lock(runtime_lock,[composite_cli])
        model = frozen_runtime['clis'][composite_cli]['model']
        effort = frozen_runtime['clis'][composite_cli]['effort']
        agent_cmd = composite_cli
    tests_root_path = Path(tests_root).resolve()
    project_root = tests_root_path.parent
    output_dir = Path(output) if output else _default_output()
    output_dir = Path(filesystem_path(output_dir)).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    task_hashes: dict[str, str] = {}
    timeouts: dict[str, int] = {}
    longest_program_path = max((len(p.relative_to(public_programs).as_posix())
        for p in public_programs.rglob('*') if p.is_file()), default=0) if public_programs else 0
    skills_root=Path(filesystem_path(skills_path)) if skills_path else None
    longest_skill_path=max((len(p.relative_to(skills_root).as_posix()) for p in skills_root.rglob('*') if p.is_file()),default=0) if skills_root else 0
    for item in tasks:
        task_started = time.monotonic()
        task = item["task"]
        task_id_value = task["id"]
        task_output = output_dir / "tasks" / task_id_value
        task_output.mkdir(parents=True, exist_ok=False)
        if workspace_root:
            live_workspace = Path(workspace_root).resolve() / task_id_value
        else:
            live_workspace = task_output / "workspace"
        requested_workspace=normal_path(live_workspace)
        relative_budget=max([128]+[len(p) for p in task['data_files']+task['required_outputs']]
            +([len('public/')+longest_program_path] if public_programs and runtime=='local' else [])
            +([len('.codebuddy/skills/')+longest_skill_path+len(skills_root.name)+1] if skills_root and runtime=='local' else []))
        live_workspace=execution_workspace(requested_workspace,project_root,relative_budget)
        stage_workspace(task, item["task_dir"], live_workspace)
        if public_programs and runtime == 'local': stage_programs(public_programs, live_workspace)
        task_timeout = int(timeout if timeout is not None else task["timeout_seconds"])
        audit_events=None
        if task.get('task_kind')=='composite':
            from harness.composite_runtime import run as run_composite
            execution,audit_events=run_composite(task,live_workspace,item['task_dir'],task_output,runtime_lock,composite_cli,'with-skills' if skills_path else 'no-skills',project_root)
        elif runtime == 'isolated':
            from harness.atomic_runtime import run_isolated_atomic
            execution = run_isolated_atomic(task, live_workspace, task_output, atomic_lock, atomic_cli, condition, project_root)
        else:
            execution = run_agent(
            agent_cmd,
            live_workspace,
            live_workspace / "task_public.json",
            task_output / "stdout.log",
            task_output / "stderr.log",
            task_timeout,
            project_root,
            model,
            effort,
            skills_path,
        )
        if normal_path(live_workspace) != normal_path(task_output / 'workspace'):
            audit_workspace = task_output / "workspace"
            from harness.filesystem import copy_tree
            copy_tree(live_workspace, audit_workspace)
        else:
            audit_workspace = live_workspace
        if normal_path(live_workspace) != normal_path(audit_workspace):
            execution['live_workspace'] = str(live_workspace)
            execution['requested_workspace'] = str(requested_workspace)
        result = grader.grade_task(task, audit_workspace, item["task_dir"],audit_events=audit_events)
        if task.get('task_kind')=='composite':
            result['eligible']=execution.get('eligible',True)
            if execution['return_code']!=0 or execution.get('termination_reason'):result['task_success']=False
        result["execution"] = {
            "return_code": execution["return_code"],
            "timed_out": execution["timed_out"],
        }
        if task.get('task_kind')=='composite':
            from harness.resource_usage import usage_from_logs
            result['resource_usage']={'wall_seconds':round(time.monotonic()-task_started,6),
                'agent_seconds':execution.get('duration_seconds'),
                'tokens':execution.get('token_usage') or usage_from_logs(task_output)}
        reporter.write_json(task_output / "execution.json", execution)
        reporter.write_json(task_output / "result.json", result)
        results.append(result)
        task_hashes[task_id_value] = _sha256_tree(item["task_dir"])
        timeouts[task_id_value] = task_timeout

    skill_path_value = Path(skills_path).resolve() if skills_path else None
    metadata = {
        "schema_version": 1,
        "experiment_version": 'composite-unattended-v2' if frozen_runtime else (VERSION if condition else 'legacy'),
        "condition": condition,
        "runtime": runtime,
        "programs_available": bool(public_programs),
        "public_programs_sha256": tree_digest(public_programs) if public_programs else None,
        "public_contract_hashes": {x['task']['id']: _sha256_file(x['task_dir'] / x['task']['public_contract']) for x in tasks if x['task'].get('public_contract')},
        "created_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "tests_root": str(tests_root_path),
        "selected_domain": domain,
        "selected_test_id": test_id,
        "selected_skill": skill,
        "suite":suite,
        "runtime_lock":str(Path(runtime_lock).resolve()) if runtime_lock else None,
        "runtime_lock_sha256":hashlib.sha256(Path(runtime_lock).read_bytes()).hexdigest() if frozen_runtime or runtime == 'isolated' else None,
        "atomic_runtime_controls": ({'image_digest': atomic_lock['image_digest'], 'cli': atomic_cli,
                                     'version': atomic_lock['clis'][atomic_cli]['version'],
                                     'config_sha256': atomic_lock['clis'][atomic_cli]['config_sha256']} if runtime == 'isolated' else None),
        "runtime_controls":({"image_digest":frozen_runtime["image_digest"],"cli":composite_cli,"cli_version":frozen_runtime["clis"][composite_cli]["version"],"config_sha256":frozen_runtime["clis"][composite_cli]["config_sha256"],"common_config_sha256":frozen_runtime["common_config_sha256"],"public_programs_sha256":frozen_runtime["public_programs_sha256"],"skills_sha256":frozen_runtime["skills_sha256"],"startup_prompt_sha256":hashlib.sha256(COMMON_START.encode()).hexdigest()} if frozen_runtime else None),
        "model": model,
        "effort": effort,
        "agent_cmd": agent_cmd,
        "timeouts": timeouts,
        "task_hashes": task_hashes,
        "skill_condition": condition or ("with-skills" if skill_path_value else "no-skills"),
        "skill_suite": skill_path_value.name if skill_path_value else None,
        "skills_path": str(skill_path_value) if skill_path_value else None,
        "skills_hash": _sha256_tree(skill_path_value) if skill_path_value else None,
        "environment": environment_metadata(),
    }
    summary = reporter.aggregate_results(results)
    reporter.write_json(output_dir / "run_metadata.json", metadata)
    reporter.write_json(output_dir / "summary.json", summary)
    return {"run_dir": str(normal_path(output_dir)), "metadata": metadata, "summary": summary, "results": results}


def regrade_run(run_dir: str | Path) -> dict[str, Any]:
    root = Path(filesystem_path(run_dir)).resolve()
    metadata = json.loads((root / "run_metadata.json").read_text(encoding="utf-8"))
    tests_root = Path(metadata["tests_root"])
    results: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for result_path in sorted((root / "tasks").glob("*/result.json")):
        previous = json.loads(result_path.read_text(encoding="utf-8"))
        task_id = previous["test_id"]
        candidates=discover_tasks(tests_root,test_id=task_id,suite=metadata.get('suite','atomic'))
        task_path=candidates[0]['task_path'] if candidates else None
        if task_path is None:
            raise FileNotFoundError(f"canonical task not found for {task_id}")
        task = schemas.load_json(task_path)
        if task.get('task_kind')=='composite' and previous.get('task_version')!=task.get('task_version'):
            raise ValueError('Cannot regrade an old composite result against a different task version')
        if task.get('task_kind')=='composite' and previous.get('task_revision',1)!=task.get('task_revision',1):
            raise ValueError('Cannot regrade a composite result against a different task revision')
        audit_path=result_path.parent/'host_audit.jsonl'
        events=[json.loads(line) for line in audit_path.read_text(encoding='utf-8').splitlines()] if audit_path.exists() else None
        current = grader.grade_task(task, result_path.parent / "workspace", task_path.parent,audit_events=events)
        current["execution"] = previous.get("execution", {})
        if 'resource_usage' in previous:current['resource_usage']=previous['resource_usage']
        if task.get('task_kind')=='composite':
            execution=json.loads((result_path.parent/'execution.json').read_text(encoding='utf-8'))
            current['eligible']=execution.get('eligible',True)
            if execution.get('return_code',1)!=0 or execution.get('termination_reason'):current['task_success']=False
        if abs(float(previous.get("score", 0.0)) - current["score"]) > 1e-12:
            changes.append({"test_id": task_id, "old_score": previous.get("score", 0.0), "new_score": current["score"]})
        reporter.write_json(result_path, current)
        results.append(current)
    summary = reporter.aggregate_results(results)
    reporter.write_json(root / "summary.json", summary)
    return {"run_dir": str(root), "changes": changes, "summary": summary}
