"""ll-issues spike-verdict: deterministic spike verdict from role-tagged JUnit XML (BUG-3592).

``/ll:spike`` used to treat any non-zero Verification exit as a refutation. This
module classifies each run as PROVEN / REFUTED / INCONCLUSIVE from the JUnit XML
of every planned command plus the exception type a generated ``conftest.py``
hook records per failed test, so an import error or environment failure is never
read as "the approach is wrong".
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig

ROLES = ("spike", "regression")
GUARD_PREFIX = "test_guard_"

EXIT_PROVEN = 0
EXIT_REFUTED = 1
EXIT_INCONCLUSIVE = 3

HOOK_BEGIN = "# >>> ll-spike-verdict hook >>>"
HOOK_END = "# <<< ll-spike-verdict hook <<<"

# Runs inside the consuming project's own pytest, so it may import only pytest —
# never little_loops (not importable under a pipx / uv-tool install).
_HOOK_BODY = """import pytest as _ll_pytest


@_ll_pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    yield
    if call.when != "call" or call.excinfo is None:
        return
    exc = call.excinfo.value
    is_assertion = isinstance(exc, AssertionError) or (
        isinstance(exc, _ll_pytest.fail.Exception)
        and str(exc).startswith(("DID NOT RAISE", "DID NOT WARN"))
    )
    item.user_properties.append(("ll_exc_type", call.excinfo.type.__name__))
    item.user_properties.append(("ll_assertion", "true" if is_assertion else "false"))
"""

_HOOK_BLOCK = f"{HOOK_BEGIN}\n{_HOOK_BODY}{HOOK_END}\n"


@dataclass
class SpikeReport:
    """One Verification command's outcome: its role, JUnit XML path and exit code."""

    role: str
    junit_path: Path
    exit_code: int


@dataclass
class SpikeVerdict:
    """Classifier result; ``cause`` is a one-line reason quoted into ``## Spike Findings``."""

    verdict: str
    cause: str


@dataclass
class _Case:
    name: str
    status: str  # pass | failure | error | skipped
    assertion: bool
    exc_type: str
    message: str


def _parse_cases(path: Path) -> list[_Case] | None:
    """Parse a JUnit XML file into cases, or None when missing/malformed."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    cases: list[_Case] = []
    for tc in root.iter("testcase"):
        props = {p.get("name"): p.get("value") for p in tc.iter("property")}
        status = "pass"
        message = ""
        for tag in ("error", "failure", "skipped"):
            node = tc.find(tag)
            if node is not None:
                status = tag
                message = (node.get("message") or "").strip()
                break
        cases.append(
            _Case(
                name=tc.get("name") or "",
                status=status,
                assertion=props.get("ll_assertion") == "true",
                exc_type=props.get("ll_exc_type") or "",
                message=message,
            )
        )
    return cases


def _inconclusive(cause: str) -> SpikeVerdict:
    return SpikeVerdict("INCONCLUSIVE", cause)


def _one_line(text: str, limit: int = 160) -> str:
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


def classify_spike_junit(
    reports: list[SpikeReport], guard_prefix: str = GUARD_PREFIX
) -> SpikeVerdict:
    """Classify a spike run as PROVEN, REFUTED or INCONCLUSIVE.

    Inconclusive triggers are checked first and win. Refuted requires at least
    one AC ``<failure>`` where every AC failure is an assertion, all guard tests
    and regression reports passing, and the spike command exiting 1. Proven
    requires every command exit 0, >=1 guard test passed, and every AC test
    passed (none skipped).
    """
    spike_cases: list[_Case] = []
    spike_exits: list[tuple[int, list[_Case]]] = []
    for report in reports:
        if report.role not in ROLES:
            return _inconclusive(f"unknown report role '{report.role}'")
        cases = _parse_cases(report.junit_path)
        if cases is None:
            return _inconclusive(f"{report.role} report missing or malformed: {report.junit_path}")
        if any(c.status == "error" for c in cases):
            bad = next(c for c in cases if c.status == "error")
            return _inconclusive(f"{report.role} run has a test error ({bad.name}): {bad.message}")
        failed = [c for c in cases if c.status == "failure"]
        if report.role == "regression":
            if report.exit_code != 0 or failed:
                what = failed[0].name if failed else f"exit {report.exit_code}"
                return _inconclusive(f"regression suite did not pass ({what})")
            continue
        if report.exit_code not in (0, 1):
            return _inconclusive(f"spike command exited {report.exit_code} (not a test result)")
        if (report.exit_code == 1) != bool(failed):
            return _inconclusive(
                f"spike exit {report.exit_code} disagrees with its report "
                f"({len(failed)} failure(s))"
            )
        spike_cases.extend(cases)
        spike_exits.append((report.exit_code, cases))

    if not spike_exits:
        return _inconclusive("no spike report supplied")

    guards = [c for c in spike_cases if c.name.startswith(guard_prefix)]
    acs = [c for c in spike_cases if not c.name.startswith(guard_prefix)]
    if not acs:
        return _inconclusive("zero AC tests in the spike report")
    if not guards:
        return _inconclusive(f"zero guard tests ({guard_prefix}*) in the spike report")
    for c in guards:
        if c.status == "skipped":
            return _inconclusive(f"guard test skipped ({c.name})")
        if c.status == "failure":
            return _inconclusive(f"guard test failed ({c.name})")
    skipped = [c for c in acs if c.status == "skipped"]
    if skipped:
        return _inconclusive(f"AC test skipped ({skipped[0].name}); its risk is unproven")
    ac_failures = [c for c in acs if c.status == "failure"]
    for c in ac_failures:
        if not c.assertion:
            kind = c.exc_type or "unrecorded exception type"
            return _inconclusive(f"AC test {c.name} failed with a non-assertion ({kind})")

    if not ac_failures:
        return SpikeVerdict(
            "PROVEN", f"{len(acs)} AC test(s) and {len(guards)} guard test(s) passed"
        )
    first = ac_failures[0]
    return SpikeVerdict(
        "REFUTED",
        f"{len(ac_failures)} AC assertion(s) failed, e.g. {first.name}: {_one_line(first.message)}",
    )


def emit_conftest(out: Path) -> None:
    """Write the sentinel-delimited hook block to *out*, replacing it in place if present.

    Content outside the sentinels (a spike's own fixtures) is preserved, and a
    rerun never duplicates the block.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    existing = out.read_text() if out.exists() else ""
    pattern = re.compile(re.escape(HOOK_BEGIN) + r".*?" + re.escape(HOOK_END) + r"\n?", re.DOTALL)
    if pattern.search(existing):
        new = pattern.sub(lambda _m: _HOOK_BLOCK, existing, count=1)
    elif existing:
        new = existing.rstrip("\n") + "\n\n\n" + _HOOK_BLOCK
    else:
        new = _HOOK_BLOCK
    out.write_text(new)


def _parse_report_arg(raw: str) -> SpikeReport:
    """Split ``role:xml:exit`` — role before the first ``:``, exit after the last."""
    role, sep, rest = raw.partition(":")
    xml, sep2, exit_raw = rest.rpartition(":")
    if not sep or not sep2 or not xml:
        raise ValueError(f"expected <role>:<xml>:<exit>, got '{raw}'")
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}, got '{role}'")
    return SpikeReport(role=role, junit_path=Path(xml), exit_code=int(exit_raw))


def add_spike_verdict_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the spike-verdict subparser on *subs* (BUG-3592)."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "spike-verdict",
        help=(
            "Classify a spike as PROVEN/REFUTED/INCONCLUSIVE from role-tagged JUnit "
            "XML (exit 0/1/3), or write the conftest hook (BUG-3592)"
        ),
    )
    p.set_defaults(command="spike-verdict")
    p.add_argument(
        "--report",
        nargs="+",
        action="extend",
        metavar="ROLE:XML:EXIT",
        help="Verification run: role is 'spike' or 'regression'",
    )
    p.add_argument(
        "--emit-conftest",
        action="store_true",
        help="Write/replace the exception-recording hook block in --out",
    )
    p.add_argument("--out", help="conftest.py path for --emit-conftest")
    add_config_arg(p)
    return p


def cmd_spike_verdict(config: BRConfig, args: argparse.Namespace) -> int:
    """Print ``VERDICT`` plus a one-line cause; exit 0 proven / 1 refuted / 3 inconclusive.

    With ``--emit-conftest --out <path>`` writes the hook block and exits 0.
    Exits 2 on a usage error (2 is also argparse's usage code).
    """
    if getattr(args, "emit_conftest", False):
        if not args.out:
            print("Error: --emit-conftest requires --out <path>", file=sys.stderr)
            return 2
        emit_conftest(Path(args.out))
        print(f"Wrote spike-verdict hook block to {args.out}")
        return 0

    raw_reports = getattr(args, "report", None)
    if not raw_reports:
        print("Error: pass --report <role>:<xml>:<exit> ... or --emit-conftest", file=sys.stderr)
        return 2
    try:
        reports = [_parse_report_arg(r) for r in raw_reports]
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    result = classify_spike_junit(reports)
    print(result.verdict)
    print(result.cause)
    return {
        "PROVEN": EXIT_PROVEN,
        "REFUTED": EXIT_REFUTED,
    }.get(result.verdict, EXIT_INCONCLUSIVE)
