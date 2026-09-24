"""Static BSD/GNU/bash-3.2 portability gate for shipped shell (ENH-3539).

Scans tracked ``*.sh`` under ``hooks/`` and ``scripts/little_loops/hooks/adapters/``
plus ``scripts/little_loops/loops/**/*.yaml`` (line-based; ``#`` comment lines
skipped). Suppress a justified line with ``ll-portability-ok:`` on the same line
or the line immediately above.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SUPPRESS_TOKEN = "ll-portability-ok:"
SCAN_GLOBS = (
    "hooks/**/*.sh",
    "scripts/little_loops/hooks/adapters/**/*.sh",
    "scripts/little_loops/loops/**/*.yaml",
)


@dataclass(frozen=True)
class Rule:
    """One divergent shell form; ``unless`` exempts same-line paired fallbacks."""

    name: str
    pattern: re.Pattern[str]
    unless: re.Pattern[str] | None = None


RULES: tuple[Rule, ...] = (
    Rule("date-%N", re.compile(r"\bdate\b[^|;&]*%[0-9]*N")),
    Rule("grep-P", re.compile(r"\bgrep\b(?:\s+-\w+)*\s+-\w*P")),
    Rule("grep-E-perl-class", re.compile(r"\b(?:grep\s+(?:-\w+\s+)*-\w*E|egrep)\b.*\\[sbwSBW]")),
    Rule("sed-i-no-attached-suffix", re.compile(r"\bsed\s+(?:-\w+\s+)*-i(?!\.\w)")),
    Rule("readlink-f", re.compile(r"\breadlink\s+-f\b")),
    Rule("stat-c", re.compile(r"\bstat\s+(?:-\w+\s+)*-c\b"), re.compile(r"\bstat\s+-f\b")),
    Rule("date-d", re.compile(r"\bdate\s+(?:-\w+\s+)*-d\b"), re.compile(r"\bdate\s+-j\b")),
    Rule("bash4-declare-A", re.compile(r"\bdeclare\s+-A\b")),
    Rule("bash4-mapfile", re.compile(r"\b(?:mapfile|readarray)\b")),
    Rule("bash4-case-mod", re.compile(r"\$\{[A-Za-z_]\w*(?:,,|\^\^)")),
    Rule("bash4-append-redirect", re.compile(r"&>>")),
    Rule("bash4-pipe-stderr", re.compile(r"\|&")),
    Rule("bash4-coproc", re.compile(r"(?:^|[;&|]\s*)coproc\b")),
    Rule("bash4-local-n", re.compile(r"\blocal\s+-n\b")),
)


def scan_portability(text: str, rules: tuple[Rule, ...] = RULES) -> list[tuple[int, str, str]]:
    """Return ``(lineno, rule_name, line)`` for each unsuppressed divergent form."""
    lines = text.splitlines()
    hits: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        if SUPPRESS_TOKEN in line or (i > 0 and SUPPRESS_TOKEN in lines[i - 1]):
            continue
        for rule in rules:
            if rule.pattern.search(line) and not (rule.unless and rule.unless.search(line)):
                hits.append((i + 1, rule.name, line.strip()))
    return hits


def _scan_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", *SCAN_GLOBS],
        capture_output=True,
        cwd=REPO_ROOT,
        check=True,
    ).stdout.decode()
    return sorted(REPO_ROOT / p for p in out.split("\0") if p and "node_modules/" not in p)


@pytest.mark.parametrize(
    "rule,snippet",
    [
        ("date-%N", "MS=$(date +%s%N)"),
        ("grep-P", "grep -P '\\d+' f"),
        ("grep-E-perl-class", "grep -qE '^\\s*x' f"),
        ("sed-i-no-attached-suffix", "sed -i 's/a/b/' f"),
        ("sed-i-no-attached-suffix", "sed -i '' 's/a/b/' f"),
        ("sed-i-no-attached-suffix", 'sed -i "" s/a/b/ f'),
        ("readlink-f", "readlink -f x"),
        ("stat-c", "stat -c %Y f"),
        ("date-d", 'date -d "$x" +%s'),
        ("bash4-declare-A", "declare -A m"),
        ("bash4-mapfile", "mapfile -t a < f"),
        ("bash4-mapfile", "readarray -t a < f"),
        ("bash4-case-mod", 'echo "${x,,}"'),
        ("bash4-case-mod", 'echo "${x^^}"'),
        ("bash4-append-redirect", "cmd &>> log"),
        ("bash4-pipe-stderr", "cmd |& tee log"),
        ("bash4-coproc", "coproc foo { bar; }"),
        ("bash4-local-n", "local -n ref=$1"),
    ],
)
def test_rule_fires(rule: str, snippet: str) -> None:
    assert rule in {name for _, name, _ in scan_portability(snippet)}


@pytest.mark.parametrize(
    "snippet",
    [
        "stat -f %m f || stat -c %Y f",
        "date -j -f %s x +%s || date -d x +%s",
        "  # sed -i '' foo",
        "sed -i.bak 's/a/b/' f && rm f.bak",
        "sort -V list",
        "grep -oE '[[:space:]]+' f",
        "# ll-portability-ok: paired\nstat -c %Y f",
        "date -d x +%s  # ll-portability-ok: paired",
    ],
)
def test_allowed_forms_pass(snippet: str) -> None:
    assert scan_portability(snippet) == []


def test_repo_is_portable() -> None:
    files = _scan_files()
    assert files, "portability gate scan set is empty"
    failures = [
        f"{path.relative_to(REPO_ROOT)}:{n} [{rule}] {line}"
        for path in files
        for n, rule, line in scan_portability(path.read_text(encoding="utf-8", errors="replace"))
    ]
    if failures:
        pytest.fail("Portability violations:\n" + "\n".join(failures))
