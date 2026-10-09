from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path

from harness import runner, schemas
from tests_harness.test_schemas import make_task


def test_codex_wrapper_uses_nonconflicting_automatic_approval_flags() -> None:
    wrapper_path = Path("scripts/run_codex.py").resolve()
    spec = importlib.util.spec_from_file_location("run_codex_wrapper", wrapper_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    command = module.build_codex_command(None, "medium", True)
    assert "--approve-for-me" in command
    assert "--sandbox" not in command


def test_opencode_wrapper_is_noninteractive_isolated_and_maps_model_options() -> None:
    wrapper_path = Path("scripts/run_opencode.py").resolve()
    spec = importlib.util.spec_from_file_location("run_opencode_wrapper", wrapper_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    command = module.build_opencode_command("provider/model", "high", True)
    assert command[0] == "opencode" or Path(command[0]).stem == "opencode"
    assert command[1:4] == ["--pure", "run", "--auto"]
    assert command[command.index("--model") + 1] == "provider/model"
    assert command[command.index("--variant") + 1] == "high"
    assert "skill instructions" not in command[-1]
    assert command == module.build_opencode_command("provider/model", "high", False)

    config = module.build_opencode_config(["hydrology-skill"])
    permissions = config["permission"]
    assert permissions["external_directory"] == "deny"
    assert permissions["question"] == "deny"
    assert permissions["skill"] == {"*": "deny", "hydrology-skill": "allow"}


def test_shared_wrapper_installs_the_same_skill_snapshot_for_all_agents(tmp_path: Path) -> None:
    from harness.agent_wrapper import install_skill_snapshot

    source = tmp_path / "suite"
    (source / "skill-b").mkdir(parents=True)
    (source / "skill-a").mkdir()
    (source / "skill-a" / "SKILL.md").write_text("---\nname: skill-a\ndescription: a\n---\n")
    (source / "skill-b" / "SKILL.md").write_text("---\nname: skill-b\ndescription: b\n---\n")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert install_skill_snapshot(str(source), workspace) == ["skill-a", "skill-b"]
    assert (workspace / ".agents/skills/skill-a/SKILL.md").is_file()
    assert (workspace / ".agents/skills/skill-b/SKILL.md").is_file()


def test_opencode_wrapper_main_passes_an_isolated_noninteractive_environment(tmp_path: Path, monkeypatch) -> None:
    wrapper_path = Path("scripts/run_opencode.py").resolve()
    spec = importlib.util.spec_from_file_location("run_opencode_wrapper_main", wrapper_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    task_path = workspace / "task_public.json"
    task_path.write_text(
        json.dumps(
            {
                "id": "demo-001",
                "prompt": "Create output.txt.",
                "data_files": [],
                "required_outputs": ["output.txt"],
            }
        ),
        encoding="utf-8",
    )
    skill = tmp_path / "skill-a"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: skill-a\ndescription: a\n---\n")
    monkeypatch.setenv("HSQB_WORKSPACE", str(workspace))
    monkeypatch.setenv("HSQB_TASK_JSON", str(task_path))
    monkeypatch.setenv("BENCHMARK_SKILLS_PATH", str(skill))
    monkeypatch.setenv("BENCHMARK_MODEL", "provider/model")
    monkeypatch.setenv("BENCHMARK_EFFORT", "high")
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module.main() == 0
    assert (workspace / "AGENTS.md").is_file()
    assert (workspace / ".agents/skills/skill-a/SKILL.md").is_file()
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["cwd"] == workspace.resolve()
    assert captured["env"]["OPENCODE_DISABLE_CLAUDE_CODE"] == "true"
    assert captured["env"]["OPENCODE_CONFIG_DIR"]
    assert "BENCHMARK_SKILLS_PATH" not in captured["env"]
    config = json.loads(captured["env"]["OPENCODE_CONFIG_CONTENT"])
    assert config["permission"]["skill"]["skill-a"] == "allow"


def test_discovery_filters_domain_and_skill() -> None:
    by_domain = runner.discover_tasks("tests", domain="model-calibration")
    by_timeseries = runner.discover_tasks("tests", skill="data-processing/prepare-discharge-timeseries")
    by_baseflow = runner.discover_tasks("tests", skill="data-processing/separate-baseflow-eckhardt")
    by_events = runner.discover_tasks("tests", skill="data-processing/extract-flood-events")
    by_spatial = runner.discover_tasks("tests", domain="spatial-analysis")
    by_muskingum = runner.discover_tasks("tests", skill="hydrological-modeling/route-muskingum-channel")
    by_xaj = runner.discover_tasks("tests", skill="hydrological-modeling/run-lumped-xaj-model")
    by_dhf = runner.discover_tasks("tests", skill="hydrological-modeling/run-lumped-dhf-model")
    by_hbv = runner.discover_tasks("tests", skill="hydrological-modeling/run-lumped-hbv-model")
    by_tank = runner.discover_tasks("tests", skill="hydrological-modeling/run-lumped-tank-model")
    by_gr4j = runner.discover_tasks("tests", skill="hydrological-modeling/run-lumped-gr4j-model")
    by_sacsma = runner.discover_tasks("tests", skill="hydrological-modeling/run-lumped-sacsma-model")
    by_lohmann = runner.discover_tasks("tests", skill="hydrological-modeling/route-lohmann-channel")
    by_event_metrics = runner.discover_tasks("tests", skill="evaluation-diagnostics/compute-event-flood-metrics")
    by_series_metrics = runner.discover_tasks("tests", skill="evaluation-diagnostics/compute-continuous-series-metrics")
    by_aggregate_metrics = runner.discover_tasks("tests", skill="evaluation-diagnostics/aggregate-event-metrics")
    by_ml_correct = runner.discover_tasks("tests", skill="post-processing/correct-residual-with-ml")
    expected_calibration = [
        f"hydromodel-{algorithm}-{index:03d}"
        for algorithm in ("de", "dhf", "ga", "gr4j", "hbv", "lohmann", "muskingum", "pso", "sacsma", "sce-ua", "swat-sd", "tank", "topmodel", "two-stage", "xaj", "xaj-sd")
        for index in range(1, 4)
    ]
    assert [item["task"]["id"] for item in by_domain] == sorted(expected_calibration)
    assert [item["task"]["id"] for item in by_muskingum] == [
        f"hydromodel-muskingum-{index:03d}" for index in range(1, 4)
    ]
    assert [item["task"]["id"] for item in by_xaj] == [
        f"hydromodel-xaj-{index:03d}" for index in range(1, 4)
    ]
    assert [item["task"]["id"] for item in by_dhf] == [
        f"hydromodel-dhf-{index:03d}" for index in range(1, 4)
    ]
    assert [item["task"]["id"] for item in by_hbv] == [
        f"hydromodel-hbv-{index:03d}" for index in range(1, 4)
    ]
    assert [item["task"]["id"] for item in by_tank] == [
        f"hydromodel-tank-{index:03d}" for index in range(1, 4)
    ]
    assert [item["task"]["id"] for item in by_gr4j] == [
        f"hydromodel-gr4j-{index:03d}" for index in range(1, 4)
    ]
    assert [item["task"]["id"] for item in by_sacsma] == [
        f"hydromodel-sacsma-{index:03d}" for index in range(1, 4)
    ]
    assert [item["task"]["id"] for item in by_lohmann] == [
        f"hydromodel-lohmann-{index:03d}" for index in range(1, 4)
    ]
    assert [item["task"]["id"] for item in by_event_metrics] == [
        f"hydroanalysis-event-metrics-{index:03d}" for index in range(1, 4)
    ]
    assert [item["task"]["id"] for item in by_series_metrics] == [
        f"hydroanalysis-series-metrics-{index:03d}" for index in range(1, 4)
    ]
    assert [item["task"]["id"] for item in by_aggregate_metrics] == [
        f"hydroanalysis-aggregate-metrics-{index:03d}" for index in range(1, 4)
    ]
    assert [item["task"]["id"] for item in by_ml_correct] == [
        f"hydroanalysis-ml-correct-{index:03d}" for index in range(1, 4)
    ]
    assert [item["task"]["id"] for item in by_timeseries] == [
        f"hydrodata-timeseries-{index:03d}" for index in range(1, 13)
    ]
    assert [item["task"]["id"] for item in by_baseflow] == [
        f"hydrodata-baseflow-{index:03d}" for index in range(1, 9)
    ]
    assert [item["task"]["id"] for item in by_events] == [
        f"hydrodata-flood-events-{index:03d}" for index in range(1, 11)
    ]
    assert len(by_spatial) == 41
    assert {item["task"]["primary_skill"] for item in by_spatial} == {
        "spatial-analysis/prepare-dem-analysis-grid",
        "spatial-analysis/extract-dem-stream-network",
        "spatial-analysis/build-hydrological-topology",
        "spatial-analysis/validate-hydrological-topology",
        "spatial-analysis/derive-topmodel-terrain-inputs",
        "spatial-analysis/aggregate-forcing-to-model-units",
    }


def test_environment_metadata_records_conda_environment(monkeypatch) -> None:
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "HydroTune-eval")
    monkeypatch.setenv("CONDA_PREFIX", "C:/conda/envs/HydroTune-eval")
    metadata = runner.environment_metadata()
    assert metadata["conda_environment"] == "HydroTune-eval"
    assert metadata["conda_prefix"].endswith("HydroTune-eval")


def test_workspace_contains_only_public_metadata_and_declared_data(tmp_path: Path) -> None:
    task_path = Path("tests/data-preprocessing/hydrodata-timeseries-001").resolve()
    task = schemas.load_json(task_path / "task.json")
    workspace = runner.stage_workspace(task, task_path, tmp_path / "workspace")
    assert (workspace / "shuffled_flow.csv").is_file()
    assert not (workspace / "expected").exists()
    assert not (workspace / "task.json").exists()
    public_text = (workspace / "task_public.json").read_text(encoding="utf-8")
    assert "grading" not in public_text
    assert "expected/" not in public_text
    assert str(task_path) not in public_text


def test_agent_execution_closes_stdin_and_records_nonzero_artifact(tmp_path: Path) -> None:
    project = tmp_path / "project"
    workspace = tmp_path / "workspace"
    project.mkdir()
    workspace.mkdir()
    public = workspace / "task_public.json"
    public.write_text("{}", encoding="utf-8")
    script = project / "agent.py"
    script.write_text(
        "import os, pathlib, sys\n"
        "pathlib.Path('artifact.txt').write_text('ok')\n"
        "pathlib.Path('stdin.txt').write_text(repr(sys.stdin.read()))\n"
        "pathlib.Path('env.txt').write_text(os.environ['HSQB_TEST_DIR'])\n"
        "raise SystemExit(7)\n",
        encoding="utf-8",
    )
    execution = runner.run_agent(
        f'"{sys.executable}" agent.py',
        workspace,
        public,
        tmp_path / "stdout.log",
        tmp_path / "stderr.log",
        10,
        project,
    )
    assert execution["return_code"] == 7
    assert not execution["timed_out"]
    assert (workspace / "artifact.txt").read_text() == "ok"
    assert (workspace / "stdin.txt").read_text() == "''"
    assert (workspace / "env.txt").read_text() == str(workspace.resolve())


def test_agent_timeout(tmp_path: Path) -> None:
    project = tmp_path / "project"
    workspace = tmp_path / "workspace"
    project.mkdir()
    workspace.mkdir()
    public = workspace / "task_public.json"
    public.write_text("{}", encoding="utf-8")
    (project / "sleep.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    execution = runner.run_agent(
        f'"{sys.executable}" sleep.py',
        workspace,
        public,
        tmp_path / "stdout.log",
        tmp_path / "stderr.log",
        1,
        project,
    )
    assert execution["timed_out"]


def test_run_serialization_and_regrade_after_nonzero_exit(tmp_path: Path) -> None:
    tests_root = tmp_path / "project" / "tests"
    task, _ = make_task(tests_root)
    project = tests_root.parent
    agent = project / "agent.py"
    agent.write_text("from pathlib import Path\nPath('output.txt').write_text('made')\nraise SystemExit(4)\n", encoding="utf-8")
    output = tmp_path / "run"
    result = runner.run_benchmark(
        tests_root=tests_root,
        agent_cmd=f'"{sys.executable}" agent.py',
        output=output,
    )
    assert result["results"][0]["score"] == 1.0
    assert result["results"][0]["execution"]["return_code"] == 4
    assert (output / "tasks" / task["id"] / "workspace" / "output.txt").is_file()
    before_execution = json.loads((output / "tasks" / task["id"] / "execution.json").read_text())
    regraded = runner.regrade_run(output)
    after_execution = json.loads((output / "tasks" / task["id"] / "execution.json").read_text())
    assert regraded["summary"]["score_overall"] == 1.0
    assert before_execution == after_execution
