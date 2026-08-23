"""ll-advise: one-shot, signal-cited second-model consult (FEAT-3120)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from little_loops.advisor import (
    AdvisorNotConfigured,
    CapabilityFloorViolation,
    consult,
)
from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.cli_args import add_json_arg
from little_loops.config import BRConfig
from little_loops.host_runner import BlockingJsonError, HostNotConfigured
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

__all__ = ["main_advise"]


def cmd_invoke(args: argparse.Namespace, logger: Logger) -> int:
    config = BRConfig(Path.cwd())
    if args.host:
        config.advisor.host = args.host
    if args.model:
        config.advisor.model = args.model

    context = ""
    if args.context_file:
        try:
            context = Path(args.context_file).read_text()
        except OSError as exc:
            logger.error(f"could not read --context-file {args.context_file!r}: {exc}")
            return 2

    try:
        verdict = consult(
            question=args.question,
            signal=args.signal,
            context=context,
            config=config,
            main_host=args.main_host,
            main_model=args.main_model,
        )
    except AdvisorNotConfigured as exc:
        logger.error(str(exc))
        return 2
    except CapabilityFloorViolation as exc:
        logger.error(f"capability floor violation: {exc}")
        return 2
    except HostNotConfigured as exc:
        logger.error(str(exc))
        return 2
    except BlockingJsonError as exc:
        logger.error(str(exc))
        return 2

    payload = {
        "recommendation": verdict.recommendation,
        "risks": verdict.risks,
        "confidence": verdict.confidence,
        "dissent": verdict.dissent,
        "signal": verdict.signal,
        "host": verdict.host,
        "model": verdict.model,
    }
    if args.json:
        print_json(payload)
    else:
        logger.info(f"recommendation: {verdict.recommendation}")
        logger.info(f"confidence: {verdict.confidence}")
        if verdict.risks:
            logger.info(f"risks: {', '.join(verdict.risks)}")
        if verdict.dissent:
            logger.info(f"dissent: {verdict.dissent}")
        logger.info(f"signal={verdict.signal} host={verdict.host} model={verdict.model}")

    return 0


def main_advise(argv: list[str] | None = None) -> int:
    """Entry point for ll-advise.

    Returns:
        Exit code: 0 = consult succeeded, 2 = refused or failed (unconfigured
        advisor, capability floor violation, unwired/unauthenticated host,
        or transport failure) — never a traceback for these expected cases.
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-advise", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-advise",
            description="One-shot, signal-cited second-model consult, independent of "
            "orchestration.host_cli",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  %(prog)s --signal user_requested --question "Is this design sound?"
  %(prog)s --signal score_stall --question "..." --context-file notes.md
  %(prog)s --signal user_requested --question "..." --host codex --model gpt-5.1 --json
""",
        )
        parser.add_argument(
            "--signal",
            required=True,
            help="What prompted this consult (e.g. score_stall, user_requested). "
            "Every consult is signal-cited — there is no unsignalled consult path.",
        )
        parser.add_argument("--question", required=True, help="The consult prompt")
        parser.add_argument(
            "--context-file",
            default=None,
            help="Path to a caller-authored context file appended to the prompt",
        )
        parser.add_argument(
            "--main-host",
            default=None,
            help="Host running the primary session, for the capability floor check "
            "(default: the ambient resolved host)",
        )
        parser.add_argument(
            "--main-model",
            default=None,
            help="Model running the primary session, for the capability floor check "
            "(default: fsm.schema.DEFAULT_LLM_MODEL)",
        )
        parser.add_argument(
            "--host",
            default=None,
            help="Advisor host, overriding advisor.host in .ll/ll-config.json",
        )
        parser.add_argument(
            "--model",
            default=None,
            help="Advisor model, overriding advisor.model in .ll/ll-config.json",
        )
        add_json_arg(parser)

        args = parser.parse_args(argv)

        configure_output()
        logger = Logger(use_color=use_color_enabled())

        return cmd_invoke(args, logger)
