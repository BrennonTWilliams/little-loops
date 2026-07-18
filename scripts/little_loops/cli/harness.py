"""ll-harness: One-shot runner evaluation CLI (FEAT-1851)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from little_loops.cli.output import configure_output, print_json, status_block, use_color_enabled
from little_loops.fsm.evaluators import evaluate_llm_structured
from little_loops.logger import Logger
from little_loops.runner_spec import ActionSpec, RunnerResult, RunnerType, run_action
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

__all__ = [
    "RunnerResult",
    "DslTask",
    "main_harness",
]


@dataclass
class DslTask:
    """A single DSL evaluation task loaded from a task YAML file."""

    prompt: str
    blanks: list[str]
    expected: dict[str, str]
    source_dsl: str
    task_type: str
    source_file: str = ""
    generated_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DslTask:
        return cls(
            prompt=data["prompt"],
            blanks=data.get("blanks") or [],
            expected=data.get("expected") or {},
            source_dsl=data.get("source_dsl", ""),
            task_type=data.get("task_type", ""),
            source_file=data.get("source_file", ""),
            generated_at=data.get("generated_at", ""),
        )


def _build_harness_parser() -> argparse.ArgumentParser:
    """Build the ll-harness argument parser (exposed for testing)."""
    parser = argparse.ArgumentParser(
        prog="ll-harness",
        description="One-shot runner evaluation for little-loops skills and commands",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ll-harness skill check-code
  ll-harness cmd "echo hello" --exit-code 0
  ll-harness mcp my-server:my-tool --args '{"key": "val"}' --semantic "tool returned results"
  ll-harness prompt "What is 2+2?" --semantic "response contains a number"

Exit codes:
  0  PASS
  1  FAIL
  2  Internal error / timeout
""",
    )

    subparsers = parser.add_subparsers(dest="runner", metavar="RUNNER")
    subparsers.required = True

    def _add_evaluator_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--exit-code",
            dest="exit_code",
            type=int,
            default=None,
            metavar="INT",
            help="Expected exit code (default: not checked)",
        )
        p.add_argument(
            "--semantic",
            type=str,
            default=None,
            metavar="TEXT",
            help="Natural-language criterion for output evaluation",
        )
        p.add_argument(
            "--timeout",
            type=int,
            default=120,
            metavar="SECONDS",
            help="Runner timeout in seconds (default: 120)",
        )
        p.add_argument(
            "--output",
            choices=["text", "json"],
            default="text",
            help="Output format (default: text)",
        )
        p.add_argument(
            "--verbose",
            action="store_true",
            help="Show full captured output even on pass",
        )

    skill_p = subparsers.add_parser(
        "skill",
        help="Invoke a little-loops skill",
        description="Invoke a little-loops skill via the active host CLI",
    )
    skill_p.add_argument("target", help="Skill name (e.g. check-code, refine-issue)")
    skill_p.add_argument(
        "runner_args",
        nargs="*",
        help="Additional arguments passed to the skill",
    )
    _add_evaluator_flags(skill_p)

    cmd_p = subparsers.add_parser(
        "cmd",
        help="Run a shell command",
        description="Run a shell command and capture its output",
    )
    cmd_p.add_argument("target", help="Shell command to execute")
    _add_evaluator_flags(cmd_p)

    mcp_p = subparsers.add_parser(
        "mcp",
        help="Call an MCP tool",
        description="Call an MCP tool via JSON-RPC",
    )
    mcp_p.add_argument("target", help="MCP server and tool (format: server:tool)")
    mcp_p.add_argument(
        "--args",
        dest="mcp_args",
        type=str,
        default="{}",
        metavar="JSON",
        help="JSON arguments to pass to the MCP tool (default: {})",
    )
    _add_evaluator_flags(mcp_p)

    prompt_p = subparsers.add_parser(
        "prompt",
        help="Send a raw prompt to Claude",
        description="Send a raw prompt to Claude via the active host CLI",
    )
    prompt_p.add_argument("target", help="Prompt text to send")
    prompt_p.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help="Override Claude model (e.g. claude-haiku-4-5-20251001)",
    )
    _add_evaluator_flags(prompt_p)

    dsl_p = subparsers.add_parser(
        "dsl",
        help="Run a DSL task set and report pass rates by model",
        description="Load and run DSL eval task YAML files, reporting pass rate with Wilson CI",
    )
    dsl_p.add_argument("path", help="DSL task file or directory of .yaml task files")
    dsl_p.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help="Override Claude model (e.g. claude-haiku-4-5-20251001)",
    )
    _add_evaluator_flags(dsl_p)

    return parser


def _parse_harness_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse argv into a Namespace (exposed for testing)."""
    return _build_harness_parser().parse_args(argv)


def _evaluate_and_report(
    runner_label: str,
    result: RunnerResult,
    args: argparse.Namespace,
) -> int:
    """Evaluate result against criteria and print the report. Returns exit code."""
    if result.timed_out:
        _report(runner_label, result, args, error_msg="timeout")
        return 2
    if result.error is not None:
        _report(runner_label, result, args, error_msg=result.error)
        return 2

    passed = True
    exit_code_display = str(result.exit_code)
    semantic_display = "[not checked]"

    if args.exit_code is not None:
        if result.exit_code != args.exit_code:
            passed = False
        exit_code_display = f"{result.exit_code} (expected {args.exit_code})"

    if args.semantic is not None:
        eval_result = evaluate_llm_structured(output=result.stdout, prompt=args.semantic)
        semantic_display = eval_result.verdict
        if eval_result.verdict != "yes":
            passed = False

    overall = "PASS" if passed else "FAIL"
    show_output = not passed or args.verbose

    if args.output == "json":
        print_json(
            {
                "runner": runner_label,
                "exit_code": result.exit_code,
                "exit_code_check": exit_code_display,
                "semantic": semantic_display,
                "result": overall,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
    else:
        print(
            status_block(
                {
                    "Runner": runner_label,
                    "Exit": exit_code_display,
                    "Semantic": semantic_display,
                    "Result": overall,
                }
            )
        )
        if show_output and result.stdout:
            print("---")
            sys.stdout.write(result.stdout)
            if not result.stdout.endswith("\n"):
                print()

    return 0 if passed else 1


def _report(
    runner_label: str,
    result: RunnerResult,
    args: argparse.Namespace,
    error_msg: str,
) -> None:
    """Print an error/timeout report."""
    if args.output == "json":
        print_json(
            {
                "runner": runner_label,
                "result": "ERROR",
                "error": error_msg,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
    else:
        print(status_block({"Runner": runner_label, "Result": f"ERROR ({error_msg})"}))


def cmd_skill(args: argparse.Namespace) -> int:
    """Invoke a little-loops skill via the active host CLI."""
    runner_args: list[str] = getattr(args, "runner_args", None) or []
    runner_label = f"skill {args.target}"
    spec = ActionSpec(
        name=args.target,
        runner=RunnerType.SKILL,
        target=args.target,
        args={"runner_args": runner_args},
        timeout=args.timeout,
    )
    result = run_action(spec)
    return _evaluate_and_report(runner_label, result, args)


def cmd_cmd(args: argparse.Namespace) -> int:
    """Run a shell command with deadlock-safe stderr draining."""
    runner_label = f"cmd {args.target}"
    spec = ActionSpec(
        name=args.target,
        runner=RunnerType.CMD,
        target=args.target,
        timeout=args.timeout,
    )
    result = run_action(spec)
    return _evaluate_and_report(runner_label, result, args)


def cmd_mcp(args: argparse.Namespace) -> int:
    """Call an MCP tool and evaluate the result."""
    if ":" not in args.target:
        print(
            f"Error: MCP target must be 'server:tool', got: {args.target!r}",
            file=sys.stderr,
        )
        return 2

    runner_label = f"mcp {args.target}"

    try:
        params: dict[str, Any] = json.loads(args.mcp_args)
    except json.JSONDecodeError as e:
        print(f"Error: --args is not valid JSON: {e}", file=sys.stderr)
        return 2

    spec = ActionSpec(
        name=args.target,
        runner=RunnerType.MCP,
        target=args.target,
        args={"mcp_params": params},
        timeout=args.timeout,
    )
    result = run_action(spec)
    return _evaluate_and_report(runner_label, result, args)


def cmd_prompt(args: argparse.Namespace) -> int:
    """Send a raw prompt to Claude and evaluate the response."""
    label_text = args.target[:40] + ("..." if len(args.target) > 40 else "")
    runner_label = f"prompt {label_text}"
    spec = ActionSpec(
        name=label_text,
        runner=RunnerType.PROMPT,
        target=args.target,
        args={"model": args.model},
        timeout=args.timeout,
    )
    result = run_action(spec)
    return _evaluate_and_report(runner_label, result, args)


def cmd_dsl(args: argparse.Namespace) -> int:
    """Run a DSL task set and report pass rates with Wilson CI."""
    from little_loops.stats import wilson_ci

    path = Path(args.path)
    if path.is_dir():
        task_files = sorted(path.glob("*.yaml"))
    elif path.is_file():
        task_files = [path]
    else:
        print(f"Error: DSL path not found: {path}", file=sys.stderr)
        return 2

    if not task_files:
        print(f"Error: no .yaml task files found in {path}", file=sys.stderr)
        return 2

    pass_count = 0
    total = 0

    for task_file in task_files:
        with open(task_file) as f:
            data = yaml.safe_load(f)
        task = DslTask.from_dict(data)

        prompt_text = task.prompt
        if task.blanks:
            prompt_text += f"\n\nBlanks to fill: {task.blanks}"

        task_args = argparse.Namespace(
            target=prompt_text,
            exit_code=args.exit_code,
            semantic=args.semantic,
            timeout=args.timeout,
            output=args.output,
            verbose=args.verbose,
            model=args.model,
        )
        rc = cmd_prompt(task_args)
        total += 1
        if rc == 0:
            pass_count += 1

    lo, hi = wilson_ci(pass_count, total)
    print(f"\nDSL pass-rate: {pass_count}/{total}  [{lo:.2f}, {hi:.2f}] (95% CI)")
    return 0 if pass_count == total else 1


def main_harness(argv: list[str] | None = None) -> int:
    """Entry point for ll-harness CLI."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-harness", sys.argv[1:]):
        args = _parse_harness_args(argv)
        configure_output()
        Logger(use_color=use_color_enabled())

        if args.runner == "skill":
            return cmd_skill(args)
        elif args.runner == "cmd":
            return cmd_cmd(args)
        elif args.runner == "mcp":
            return cmd_mcp(args)
        elif args.runner == "prompt":
            return cmd_prompt(args)
        elif args.runner == "dsl":
            return cmd_dsl(args)
        else:
            print(f"Unknown runner: {args.runner}", file=sys.stderr)
            return 2
