"""Task discovery, isolated staging, agent execution, and regrading."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import platform
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from harness import __version__, grader, reporter, schemas


def discover_tasks(
    tests_root: str | Path = "tests",
    domain: str | None = None,
    test_id: str | None = None,
    skill: str | None = None,
) -> list[dict[str, Any]]:
    root = Path(tests_root)
    if not root.is_dir():
        return []
    tasks: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/*/task.json")):
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
) -> list[dict[str, str]]:
    found = discover_tasks(tests_root, domain, test_id, skill)
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
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_tree(path: Path) -> str:
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
    task_root = Path(task_dir).resolve()
    workspace_path = Path(workspace).resolve()
    _clean_directory(workspace_path)
    for rel in task["data_files"]:
        source = (task_root / "data" / rel).resolve()
        source.relative_to((task_root / "data").resolve())
        destination = workspace_path / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    reporter.write_json(workspace_path / "task_public.json", schemas.public_task(task))
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
) -> dict[str, Any]:
    if not agent_cmd:
        raise ValueError("--agent-cmd is required")
    validation_errors = validate_tests(tests_root, domain, test_id, skill)
    if validation_errors:
        raise ValueError("task validation failed: " + "; ".join(item["error"] for item in validation_errors))
    tasks = discover_tasks(tests_root, domain, test_id, skill)
    tests_root_path = Path(tests_root).resolve()
    project_root = tests_root_path.parent
    output_dir = Path(output) if output else _default_output()
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    task_hashes: dict[str, str] = {}
    timeouts: dict[str, int] = {}
    for item in tasks:
        task = item["task"]
        task_id_value = task["id"]
        task_output = output_dir / "tasks" / task_id_value
        task_output.mkdir(parents=True, exist_ok=False)
        if workspace_root:
            live_workspace = Path(workspace_root).resolve() / task_id_value
        else:
            live_workspace = task_output / "workspace"
        stage_workspace(task, item["task_dir"], live_workspace)
        task_timeout = int(timeout if timeout is not None else task["timeout_seconds"])
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
        if workspace_root:
            audit_workspace = task_output / "workspace"
            shutil.copytree(live_workspace, audit_workspace)
        else:
            audit_workspace = live_workspace
        result = grader.grade_task(task, audit_workspace, item["task_dir"])
        result["execution"] = {
            "return_code": execution["return_code"],
            "timed_out": execution["timed_out"],
        }
        reporter.write_json(task_output / "execution.json", execution)
        reporter.write_json(task_output / "result.json", result)
        results.append(result)
        task_hashes[task_id_value] = _sha256_tree(item["task_dir"])
        timeouts[task_id_value] = task_timeout

    skill_path_value = Path(skills_path).resolve() if skills_path else None
    metadata = {
        "schema_version": 1,
        "created_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "tests_root": str(tests_root_path),
        "selected_domain": domain,
        "selected_test_id": test_id,
        "selected_skill": skill,
        "model": model,
        "effort": effort,
        "agent_cmd": agent_cmd,
        "timeouts": timeouts,
        "task_hashes": task_hashes,
        "skill_condition": "with-skills" if skill_path_value else "no-skills",
        "skill_suite": skill_path_value.name if skill_path_value else None,
        "skills_path": str(skill_path_value) if skill_path_value else None,
        "skills_hash": _sha256_tree(skill_path_value) if skill_path_value else None,
        "environment": environment_metadata(),
    }
    summary = reporter.aggregate_results(results)
    reporter.write_json(output_dir / "run_metadata.json", metadata)
    reporter.write_json(output_dir / "summary.json", summary)
    return {"run_dir": str(output_dir), "metadata": metadata, "summary": summary, "results": results}


def regrade_run(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir).resolve()
    metadata = json.loads((root / "run_metadata.json").read_text(encoding="utf-8"))
    tests_root = Path(metadata["tests_root"])
    results: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for result_path in sorted((root / "tasks").glob("*/result.json")):
        previous = json.loads(result_path.read_text(encoding="utf-8"))
        task_id = previous["test_id"]
        task_path = next(tests_root.glob(f"*/{task_id}/task.json"), None)
        if task_path is None:
            raise FileNotFoundError(f"canonical task not found for {task_id}")
        task = schemas.load_json(task_path)
        current = grader.grade_task(task, result_path.parent / "workspace", task_path.parent)
        current["execution"] = previous.get("execution", {})
        if abs(float(previous.get("score", 0.0)) - current["score"]) > 1e-12:
            changes.append({"test_id": task_id, "old_score": previous.get("score", 0.0), "new_score": current["score"]})
        reporter.write_json(result_path, current)
        results.append(current)
    summary = reporter.aggregate_results(results)
    reporter.write_json(root / "summary.json", summary)
    return {"run_dir": str(root), "changes": changes, "summary": summary}
