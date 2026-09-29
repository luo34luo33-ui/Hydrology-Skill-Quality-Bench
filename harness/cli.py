"""Command-line interface for HSQB v0.1."""

from __future__ import annotations

import argparse
import json
import sys

from harness import reporter, runner


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def cmd_validate(args: argparse.Namespace) -> int:
    errors = runner.validate_tests(args.tests_root, args.domain, args.test_id, args.skill)
    if not errors:
        print("Validation passed")
        return 0
    print(f"Validation failed: {len(errors)} issue(s)", file=sys.stderr)
    for item in errors:
        print(f"- {item['path']}: {item['error']}", file=sys.stderr)
    return 1


def cmd_run(args: argparse.Namespace) -> int:
    try:
        result = runner.run_benchmark(
            tests_root=args.tests_root,
            domain=args.domain,
            test_id=args.test_id,
            skill=args.skill,
            agent_cmd=args.agent_cmd,
            model=args.model,
            effort=args.effort,
            skills_path=args.skills_path,
            timeout=args.timeout,
            workspace_root=args.workspace_root,
            output=args.output,
        )
    except Exception as exc:
        print(f"run failed: {exc}", file=sys.stderr)
        return 2
    print(reporter.format_summary(result["summary"]))
    print(f"run_dir: {result['run_dir']}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    try:
        _print_json(reporter.compare_runs(args.run_a, args.run_b))
        return 0
    except Exception as exc:
        print(f"compare failed: {exc}", file=sys.stderr)
        return 2


def cmd_regrade(args: argparse.Namespace) -> int:
    try:
        result = runner.regrade_run(args.run_dir)
    except Exception as exc:
        print(f"regrade failed: {exc}", file=sys.stderr)
        return 2
    print(reporter.format_summary(result["summary"]))
    print(f"changed_tasks: {len(result['changes'])}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hydroSkillBench")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate benchmark tasks")
    validate.add_argument("--tests-root", default="tests")
    validate.add_argument("--domain")
    validate.add_argument("--test-id")
    validate.add_argument("--skill")
    validate.set_defaults(func=cmd_validate)

    run = subparsers.add_parser("run", help="run matching tasks once")
    run.add_argument("--tests-root", default="tests")
    run.add_argument("--domain")
    run.add_argument("--test-id")
    run.add_argument("--skill")
    run.add_argument("--agent-cmd", required=True)
    run.add_argument("--model")
    run.add_argument("--effort")
    run.add_argument("--skills-path")
    run.add_argument("--timeout", type=int)
    run.add_argument("--workspace-root")
    run.add_argument("--output")
    run.set_defaults(func=cmd_run)

    compare = subparsers.add_parser("compare", help="compare two paired runs")
    compare.add_argument("run_a")
    compare.add_argument("run_b")
    compare.set_defaults(func=cmd_compare)

    regrade = subparsers.add_parser("regrade", help="regrade saved task workspaces")
    regrade.add_argument("run_dir")
    regrade.set_defaults(func=cmd_regrade)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

