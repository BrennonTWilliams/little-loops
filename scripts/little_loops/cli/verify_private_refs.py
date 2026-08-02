"""ll-verify-private-refs: lint gate for private-codebase references in published files.

This repo is public. Loop runs, audits, and issue refinement execute against
private codebases, and their prose quotes absolute machine paths, sibling
project directories, and host session artifacts from those projects. ``gitleaks``
(already wired into ``.pre-commit-config.yaml``) does not cover this: the leak is
*paths and project names*, not credentials.

Two rule families, deliberately separated by where they can safely live:

**Structural rules** are built in and name-free. They match the *shape* of a
machine-local path rather than any particular project, so this module can be
tracked in a public repo without itself enumerating what it protects:

1. ``abs_user_path`` — ``/Users/<name>/…``, ``/home/<name>/…``, ``C:\\Users\\<name>\\…``.
   Reveals the author's machine layout and every sibling project directory on
   the path.
2. ``host_session_path`` — ``~/.claude/projects/<slug>/…``, the per-project host
   session store. The slug is a path-mangled absolute path, so it leaks the same
   layout in a form rule 1 misses.

**Name rules** are opt-in and read from ``.ll/private-refs.local.txt``, which is
gitignored. Bare project code names (a private repo mentioned by name with no
path attached) can only be matched by listing them, and a *tracked* list of
"here are my private projects" would publish exactly what the check exists to
withhold. Keeping the list untracked means the names never leave the machine.
The structural rules still apply on a fresh clone with no local file present.

Two modes, each with its own contract:

* **changed-files** (``ll-verify-private-refs FILE...``) — all rules, no
  baseline. This is the forward-only gate used by pre-commit (staged files) and
  the Claude Code PreToolUse hook (candidate content). Any match blocks.
* **full-scan** (``--all``) — structural rules only, compared against the
  tracked baseline at ``.ll/private-refs-baseline.json``. Exits 1 only on
  occurrences *beyond* baseline. Structural rules are deterministic across
  machines, so the baseline is portable; local name rules are not, which is why
  they are excluded from this mode.

The asymmetry is the point: the existing corpus is grandfathered, and anything
new is blocked.

A ``ll-private-ok: <reason>`` marker on the matching line or the line before it
suppresses that one finding (``<!-- ll-private-ok: … -->``, ``# ll-private-ok: …``,
and ``// ll-private-ok: …`` all work).

Exit codes match the ``ll-verify-*`` family: 0 clean, 1 on any unsuppressed
finding (changed-files mode) or any regression beyond baseline (full-scan mode).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.cli_args import add_json_arg
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

BASELINE_PATH = Path(".ll") / "private-refs-baseline.json"
LOCAL_PATTERNS_PATH = Path(".ll") / "private-refs.local.txt"

_SUPPRESS_RE = re.compile(r"ll-private-ok:\s*(.+?)\s*(?:-->|$)")

# Directories never scanned. `.git` and `__pycache__` are noise; `postmortems/`
# and `.loops/` are gitignored run forensics that are *expected* to contain
# these references (quarantining them there is the convention this check
# defends); `thoughts/` and `docs/research/` are likewise gitignored.
_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "postmortems",
        ".loops",
        "thoughts",
        "logs",
    }
)

# This module states the rules; its test file needs literal fixtures. Both would
# otherwise self-report. Excluded by path rather than by suppression marker so
# fixtures stay readable.
#
# ``.ll/ll-continue-prompt.md`` and ``.ll/private-refs.local.txt`` are machine-local
# scratch/handoff content, gitignored by ``ll-init`` (see ``_GITIGNORE_ENTRIES`` in
# ``init/writers.py``) — same category as the ``postmortems``/``.loops`` directory
# exclusions above. Under ``--all`` (which enumerates via ``git ls-files``), this
# exclusion is a no-op for a properly-ignored file; its only effect there is that a
# consumer who has tracked the file anyway gets a leak hidden — acceptable only
# because the gitignore entry makes tracking it the exception, not the norm.
_EXCLUDED_FILES = frozenset(
    {
        "scripts/little_loops/cli/verify_private_refs.py",
        "scripts/tests/test_verify_private_refs.py",
        ".ll/ll-continue-prompt.md",
        ".ll/private-refs.local.txt",
    }
)


# ---------------------------------------------------------------------------
# Rule table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrivateRefRule:
    """One shape of private-codebase reference."""

    name: str
    pattern: re.Pattern[str]
    rationale: str


# Assembled from character classes so this source does not itself contain a
# literal absolute home path (which would make the module self-matching and
# force a blanket exclusion on every consumer of the pattern).
_USER_SEG = "[A-Za-z0-9._-]+"

STRUCTURAL_RULES: tuple[PrivateRefRule, ...] = (
    PrivateRefRule(
        name="abs_user_path",
        pattern=re.compile(
            rf"(?:/(?:U[s]ers|home)/{_USER_SEG}/)"
            rf"|(?:[A-Za-z]:\\\\?U[s]ers\\\\?{_USER_SEG}\\\\?)"
        ),
        rationale=(
            "absolute home-directory path — leaks the machine layout and every "
            "sibling project directory on the path"
        ),
    ),
    PrivateRefRule(
        name="host_session_path",
        pattern=re.compile(r"~/\.claude/projects/[A-Za-z0-9._-]+"),
        rationale=(
            "host session-store path — the project slug is a mangled absolute "
            "path, leaking the same layout abs_user_path catches"
        ),
    ),
)


def load_local_rules(base_dir: Path) -> tuple[PrivateRefRule, ...]:
    """Read opt-in name patterns from the gitignored local patterns file.

    One regex per line; blank lines and ``#`` comments ignored. Returns an empty
    tuple when the file is absent (a fresh clone), so structural rules still
    apply. An unparseable regex is skipped with a note on stderr rather than
    crashing the gate — a broken local file must not block every commit.
    """
    path = base_dir / LOCAL_PATTERNS_PATH
    if not path.is_file():
        return ()

    rules: list[PrivateRefRule] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()

    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            compiled = re.compile(line)
        except re.error as exc:
            print(
                f"[little-loops] {LOCAL_PATTERNS_PATH}:{line_no}: invalid regex, skipped ({exc})",
                file=sys.stderr,
            )
            continue
        rules.append(
            PrivateRefRule(
                name="private_name",
                pattern=compiled,
                rationale=f"matches a private-project pattern from {LOCAL_PATTERNS_PATH}",
            )
        )
    return tuple(rules)


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrivateRefFinding:
    """One unsuppressed private-reference match."""

    path: Path
    line: int
    rule: str
    rationale: str
    excerpt: str


def _is_excluded(rel_path: Path) -> bool:
    if str(rel_path).replace("\\", "/") in _EXCLUDED_FILES:
        return True
    return any(part in _EXCLUDED_DIRS for part in rel_path.parts)


def _read_text(path: Path) -> str | None:
    """Return the file's text, or None when it is binary or unreadable."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:8192]:
        return None
    return raw.decode("utf-8", errors="replace")


# Extra scrub patterns applied to report excerpts only. Deliberately broader
# than the detection rules: the mangled host-session slug carries the same
# layout as an absolute path but is not itself worth failing a build over, so it
# is redacted from output without being a finding in its own right.
_REDACT_EXTRA: tuple[re.Pattern[str], ...] = (
    re.compile(r"\.claude/projects/[A-Za-z0-9._-]+"),
    re.compile(rf"(?:U[s]ers|home)[/\\-]{_USER_SEG}"),
)


def _redact(line: str, match: re.Match[str], rules: tuple[PrivateRefRule, ...]) -> str:
    """Return a short excerpt with the matched text elided.

    The finding must be actionable without the report itself reproducing the
    private path — this output goes to CI logs and hook stderr.

    Scrubbing the matched span alone is not enough: the surrounding context can
    carry a second reference the first redaction does not cover (an absolute
    path followed by the mangled host-session form of the same path). Every rule
    is re-applied to the assembled excerpt so no rule-matching text survives in
    the report.
    """
    start, end = match.span()
    prefix = line[max(0, start - 20) : start].lstrip()
    suffix = line[end : end + 20].rstrip()
    excerpt = f"{prefix}<redacted>{suffix}"
    for rule in rules:
        excerpt = rule.pattern.sub("<redacted>", excerpt)
    for extra in _REDACT_EXTRA:
        excerpt = extra.sub("<redacted>", excerpt)
    return excerpt.strip()


def scan_file(
    path: Path,
    rules: tuple[PrivateRefRule, ...],
    rel_path: Path | None = None,
) -> list[PrivateRefFinding]:
    """Scan one file for *rules*, honouring ``ll-private-ok`` suppression."""
    text = _read_text(path)
    if text is None:
        return []

    findings: list[PrivateRefFinding] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if _SUPPRESS_RE.search(line):
            continue
        if idx > 0 and _SUPPRESS_RE.search(lines[idx - 1]):
            continue
        for rule in rules:
            match = rule.pattern.search(line)
            if match is None:
                continue
            findings.append(
                PrivateRefFinding(
                    path=rel_path or path,
                    line=idx + 1,
                    rule=rule.name,
                    rationale=rule.rationale,
                    excerpt=_redact(line, match, rules),
                )
            )
    return findings


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def staged_added_lines(base_dir: Path, paths: list[Path]) -> dict[str, set[int]] | None:
    """Map each path to the set of line numbers *added* in the staged diff.

    Returns ``None`` when the diff cannot be computed (git missing, not a
    repository, command failure). Callers must treat ``None`` as "scan
    everything" — failing closed, since a gate that silently degrades to
    scanning nothing is worse than one that over-reports.

    A brand-new file has every line in its diff, so it is fully scanned.
    """
    if not paths:
        return {}
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "-U0", "--", *[str(p) for p in paths]],
            cwd=base_dir,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None

    added: dict[str, set[int]] = {}
    current: str | None = None
    lineno = 0
    for raw in result.stdout.decode("utf-8", errors="replace").splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            # "+++ b/path" for a real file, "+++ /dev/null" for a deletion.
            current = target[2:] if target.startswith(("b/", "a/")) else None
            if target == "/dev/null":
                current = None
            continue
        if raw.startswith("@@"):
            match = _HUNK_RE.match(raw)
            lineno = int(match.group(1)) if match else 0
            continue
        if current is None:
            continue
        if raw.startswith("+"):
            added.setdefault(current, set()).add(lineno)
            lineno += 1
        elif raw.startswith("-") or raw.startswith("\\"):
            continue
        else:
            lineno += 1
    return added


def _tracked_files(base_dir: Path) -> list[Path]:
    """List git-tracked files under *base_dir*, or [] when git is unavailable."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=base_dir,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    names = result.stdout.decode("utf-8", errors="replace").split("\0")
    return [Path(n) for n in names if n]


def scan_all(base_dir: Path, rules: tuple[PrivateRefRule, ...]) -> list[PrivateRefFinding]:
    """Scan every git-tracked file under *base_dir*."""
    findings: list[PrivateRefFinding] = []
    for rel in _tracked_files(base_dir):
        if _is_excluded(rel):
            continue
        findings.extend(scan_file(base_dir / rel, rules, rel_path=rel))
    return findings


def scan_paths(
    base_dir: Path,
    paths: list[Path],
    rules: tuple[PrivateRefRule, ...],
    added_only: bool = False,
) -> list[PrivateRefFinding]:
    """Scan an explicit file list (pre-commit / hook mode).

    With *added_only*, report findings only on lines the staged diff adds.
    Without it, a single edit anywhere in one of the ~800 grandfathered files
    would be rejected for pre-existing content the author never touched —
    which punishes unrelated work and trains people to bypass the gate. Only
    lines someone is actually introducing are the gate's business; the
    existing corpus is the baseline's job (``--all``).
    """
    added = staged_added_lines(base_dir, paths) if added_only else None

    findings: list[PrivateRefFinding] = []
    for path in paths:
        abs_path = path if path.is_absolute() else base_dir / path
        if not abs_path.is_file():
            continue
        try:
            rel = abs_path.resolve().relative_to(base_dir.resolve())
        except ValueError:
            rel = path
        if _is_excluded(rel):
            continue
        file_findings = scan_file(abs_path, rules, rel_path=rel)
        # `added is None` means the diff was unavailable — fail closed and keep
        # every finding rather than silently passing the file.
        if added_only and added is not None:
            allowed = added.get(str(rel).replace("\\", "/"), set())
            file_findings = [f for f in file_findings if f.line in allowed]
        findings.extend(file_findings)
    return findings


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def load_baseline(base_dir: Path) -> dict[str, int]:
    """Read the tracked baseline. Missing or malformed file → empty baseline.

    An empty baseline is the strict reading (every finding is a regression),
    which is the safe direction to fail: a corrupted baseline surfaces loudly
    instead of silently grandfathering the whole repo.
    """
    path = base_dir / BASELINE_PATH
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    counts = data.get("counts") if isinstance(data, dict) else None
    if not isinstance(counts, dict):
        return {}
    return {str(k): int(v) for k, v in counts.items() if isinstance(v, int)}


def counts_by_file(findings: list[PrivateRefFinding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        key = str(f.path).replace("\\", "/")
        counts[key] = counts.get(key, 0) + 1
    return counts


def regressions(
    findings: list[PrivateRefFinding], baseline: dict[str, int]
) -> list[PrivateRefFinding]:
    """Return findings in files whose count exceeds the baseline for that file.

    Reports every finding in a regressed file rather than trying to identify
    *which* occurrence is new — line numbers shift under unrelated edits, so a
    positional diff would be unreliable. File-level counts are stable enough to
    gate on and honest about what they mean.
    """
    current = counts_by_file(findings)
    regressed = {path for path, n in current.items() if n > baseline.get(path, 0)}
    return [f for f in findings if str(f.path).replace("\\", "/") in regressed]


def write_baseline(base_dir: Path, findings: list[PrivateRefFinding]) -> Path:
    path = base_dir / BASELINE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_comment": (
            "Grandfathered private-reference counts per file (ll-verify-private-refs "
            "--all). Counts only, never the matched text. Regenerate with "
            "ll-verify-private-refs --all --update-baseline. New or increased "
            "counts fail the gate."
        ),
        "counts": dict(sorted(counts_by_file(findings).items())),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _format_text_report(findings: list[PrivateRefFinding], mode: str) -> str:
    if not findings:
        if mode == "all":
            return "ll-verify-private-refs: PASS — no new private-codebase references"
        return "ll-verify-private-refs: PASS — no private-codebase references"

    header = (
        f"ll-verify-private-refs: {len(findings)} finding(s) beyond baseline"
        if mode == "all"
        else f"ll-verify-private-refs: {len(findings)} finding(s)"
    )
    lines = [header, ""]
    for f in findings:
        lines.append(f"  {f.path}:{f.line}: [{f.rule}] {f.excerpt}")
        lines.append(f"      {f.rationale}")
    lines.append("")
    lines.append("This repo is public. Replace the reference with a repo-relative path or a")
    lines.append("generic placeholder, or suppress a reviewed false positive with a")
    lines.append("'ll-private-ok: <reason>' marker on the line or the line above.")
    return "\n".join(lines)


def _findings_to_json(findings: list[PrivateRefFinding], mode: str) -> dict:
    return {
        "ok": not findings,
        "mode": mode,
        "count": len(findings),
        "findings": [
            {
                "file": str(f.path),
                "line": f.line,
                "rule": f.rule,
                "rationale": f.rationale,
                "excerpt": f.excerpt,
            }
            for f in findings
        ],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main_verify_private_refs(argv: list[str] | None = None) -> int:
    """Entry point for ``ll-verify-private-refs``.

    Returns 0 when clean, 1 on any unsuppressed finding (changed-files mode) or
    any finding beyond baseline (``--all``).
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-private-refs", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-verify-private-refs",
            description=(
                "Scan for private-codebase references (absolute home paths, host "
                "session paths, and opt-in project names) in files published by "
                "this public repo."
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=f"""\
Examples:
  %(prog)s FILE...                     # Gate specific files (all rules, no baseline)
  %(prog)s --added-only FILE...        # Only lines the staged diff adds (pre-commit)
  %(prog)s --all                       # Full scan vs. baseline (structural rules only)
  %(prog)s --all --update-baseline     # Re-record the grandfathered corpus
  %(prog)s --all --json                # Machine-readable output

Opt-in project-name patterns live in {LOCAL_PATTERNS_PATH} (gitignored, one
regex per line) so private names are never tracked in this public repo. They
apply in changed-files mode only.

Suppress a reviewed false positive on the matching line or the one above:
  <!-- ll-private-ok: reason -->   # ll-private-ok: reason   // ll-private-ok: reason

Exit codes:
  0 - Clean (or no findings beyond baseline under --all)
  1 - One or more unsuppressed findings
""",
        )
        parser.add_argument(
            "paths",
            nargs="*",
            type=Path,
            help="Files to scan (changed-files mode). Omit with --all.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Scan every git-tracked file, comparing against the baseline.",
        )
        parser.add_argument(
            "--update-baseline",
            action="store_true",
            help="Rewrite the baseline from the current full scan (requires --all).",
        )
        parser.add_argument(
            "--added-only",
            action="store_true",
            help=(
                "Report only lines added in the staged diff, so an edit to a "
                "grandfathered file isn't rejected for pre-existing content. "
                "Used by the pre-commit gate. Incompatible with --all."
            ),
        )
        parser.add_argument(
            "-C",
            "--directory",
            type=Path,
            default=None,
            help="Project root to scan (default: cwd)",
        )
        add_json_arg(parser)

        args = parser.parse_args(argv)

        if args.update_baseline and not args.all:
            parser.error("--update-baseline requires --all")
        if args.added_only and args.all:
            parser.error("--added-only applies to changed-files mode, not --all")
        if not args.all and not args.paths:
            parser.error("provide one or more paths, or use --all")

        configure_output()
        logger = Logger(use_color=use_color_enabled())
        base_dir = args.directory or Path.cwd()

        if args.all:
            mode = "all"
            findings = scan_all(base_dir, STRUCTURAL_RULES)
            if args.update_baseline:
                write_baseline(base_dir, findings)
                total = len(findings)
                # Report the repo-relative path: an absolute one would print the
                # very thing this command exists to keep out of published text.
                logger.success(f"Baseline updated: {BASELINE_PATH} ({total} occurrence(s))")
                return 0
            reported = regressions(findings, load_baseline(base_dir))
        else:
            mode = "paths"
            rules = STRUCTURAL_RULES + load_local_rules(base_dir)
            reported = scan_paths(base_dir, args.paths, rules, added_only=args.added_only)

        if args.json:
            print_json(_findings_to_json(reported, mode))
            return 1 if reported else 0

        print(_format_text_report(reported, mode))
        if reported:
            logger.error(f"{len(reported)} private-reference finding(s)")
            return 1
        logger.success("No private-codebase references")
        return 0
