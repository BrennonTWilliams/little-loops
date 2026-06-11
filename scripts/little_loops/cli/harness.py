"""ll-harness: One-shot runner evaluation CLI (FEAT-1851)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Any

from little_loops.cli.output import configure_output, print_json, status_block, use_color_enabled
from little_loops.fsm.evaluators import evaluate_llm_structured
from little_loops.host_runner import resolve_host
from little_loops.logger import Logger
from little_loops.mcp_call import call_mcp_tool
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context


@dataclass
class RunnerResult:
    """Captured output from a runner invocation."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    error: str | None = None


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
    parts = [f"/ll:{args.target}"] + runner_args
    prompt = " ".join(parts)

    inv = resolve_host().build_streaming(prompt=prompt)
    runner_label = f"skill {args.target}"

    try:
        proc = subprocess.run(
            [inv.binary, *inv.args],
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        result = RunnerResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)
    except subprocess.TimeoutExpired:
        result = RunnerResult(stdout="", stderr="", exit_code=2, timed_out=True)
    except FileNotFoundError as e:
        result = RunnerResult(stdout="", stderr="", exit_code=2, error=str(e))

    return _evaluate_and_report(runner_label, result, args)


def cmd_cmd(args: argparse.Namespace) -> int:
    """Run a shell command with deadlock-safe stderr draining."""
    runner_label = f"cmd {args.target}"

    process = subprocess.Popen(
        ["bash", "-c", args.target],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    def _drain_stderr() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            stderr_chunks.append(line)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    try:
        assert process.stdout is not None
        for line in process.stdout:
            stdout_chunks.append(line)
        process.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        stderr_thread.join(timeout=5)
        return _evaluate_and_report(
            runner_label,
            RunnerResult(
                stdout="".join(stdout_chunks),
                stderr="".join(stderr_chunks),
                exit_code=2,
                timed_out=True,
            ),
            args,
        )

    stderr_thread.join(timeout=5)
    return _evaluate_and_report(
        runner_label,
        RunnerResult(
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            exit_code=process.returncode,
        ),
        args,
    )


def cmd_mcp(args: argparse.Namespace) -> int:
    """Call an MCP tool and evaluate the result."""
    if ":" not in args.target:
        print(
            f"Error: MCP target must be 'server:tool', got: {args.target!r}",
            file=sys.stderr,
        )
        return 2

    server, tool = args.target.split(":", 1)
    runner_label = f"mcp {args.target}"

    try:
        params: dict[str, Any] = json.loads(args.mcp_args)
    except json.JSONDecodeError as e:
        print(f"Error: --args is not valid JSON: {e}", file=sys.stderr)
        return 2

    response, exit_code = call_mcp_tool(server, tool, params, timeout=args.timeout)
    result = RunnerResult(stdout=json.dumps(response), stderr="", exit_code=exit_code)
    return _evaluate_and_report(runner_label, result, args)


def cmd_prompt(args: argparse.Namespace) -> int:
    """Send a raw prompt to Claude and evaluate the response."""
    label_text = args.target[:40] + ("..." if len(args.target) > 40 else "")
    runner_label = f"prompt {label_text}"
    inv = resolve_host().build_blocking_json(prompt=args.target, model=args.model)

    try:
        proc = subprocess.run(
            [inv.binary, *inv.args],
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        result = RunnerResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)
    except subprocess.TimeoutExpired:
        result = RunnerResult(stdout="", stderr="", exit_code=2, timed_out=True)
    except FileNotFoundError as e:
        result = RunnerResult(stdout="", stderr="", exit_code=2, error=str(e))

    return _evaluate_and_report(runner_label, result, args)


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
        else:
            print(f"Unknown runner: {args.runner}", file=sys.stderr)
            return 2
