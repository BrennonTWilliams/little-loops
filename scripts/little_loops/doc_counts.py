"""Documentation count verification utilities.

Provides automated verification that documented counts (commands, agents, skills)
match actual file counts in the codebase.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from little_loops.fsm.validation import is_runnable_loop

_DEFAULT_BUDGET_TOKENS = 2000
_DEFAULT_PER_SKILL_WARN_TOKENS = 200

# Documentation files to check
DOC_FILES = [
    "README.md",
    "CONTRIBUTING.md",
    "docs/ARCHITECTURE.md",
]

# Directories to count
COUNT_TARGETS = {
    "commands": ("commands", "*.md"),
    "agents": ("agents", "*.md"),
    "skills": ("skills", "*/SKILL.md"),
    "loops": ("scripts/little_loops/loops", "*.yaml"),
}

# Bridge skills are auto-generated from commands/ and should be excluded from the skill count
BRIDGE_MARKER = "Bridged from `commands/"

# Step 0 decision (ENH-3195): the canonical "skill count" documented in README.md,
# CONTRIBUTING.md, and docs/ARCHITECTURE.md is the *authored, non-bridge* count —
# i.e. False here means bridge skills (BRIDGE_MARKER) are subtracted, matching
# BRIDGE_MARKER's existing intent. Flipping this to True would mean the documented
# count includes the 29 command-bridge skills (69 total); every doc callout and the
# extractor/fix_counts pairing above assume False. Change only alongside a matching
# rewording pass across all four documented callouts.
SKILL_COUNT_INCLUDES_BRIDGES = False

# Opt-out marker for count lines that are deliberately approximate/non-derivable
# prose (e.g. "about 70 skills"). Two forms, checked in this order by
# is_count_opted_out(): (a) trailing, same line as the count — works inside a
# ``` ``` ``` tree-fence "#" comment and a ```mermaid``` "%%" comment; (b) a
# preceding-line HTML comment, for plain markdown only (breaks both fence types).
_COUNT_IGNORE_MARKER = "ll-doc-count: ignore"
_COUNT_IGNORE_MARKER_HTML = f"<!-- {_COUNT_IGNORE_MARKER} -->"


@dataclass
class CountResult:
    """Result of counting files in a directory.

    ``action_severity`` mirrors ``doctor.py``'s ``CheckResult.severity`` shape:
    a closed vocabulary interpreted by one function (``fix_counts``) rather than
    scattered conditionals. ``auto`` means the mismatch is safe to rewrite
    silently; ``mention`` means a human should confirm before any rewrite;
    ``route`` means another command owns the repair (named in ``route_owner``).
    All count mismatches from ``verify_documentation`` are ``auto`` today —
    ``mention``/``route`` exist for callers that construct ``CountResult``
    directly with a different provenance.
    """

    category: str
    actual: int
    documented: int | None = None
    file: str | None = None
    line: int | None = None
    matches: bool = True
    action_severity: Literal["auto", "mention", "route"] = "auto"
    route_owner: str | None = None
    missing: list[str] = field(default_factory=list)
    """Coverage-gap mismatches (category "cli_entry_points"/"hooks") name the
    specific entries a doc omits here instead of comparing a single number.
    Empty for ordinary numeric-callout mismatches."""


@dataclass
class VerificationResult:
    """Overall verification result."""

    total_checked: int = 0
    mismatches: list[CountResult] = field(default_factory=list)
    all_match: bool = True

    def add_result(self, result: CountResult) -> None:
        """Add a result and track mismatches."""
        if not result.matches:
            self.mismatches.append(result)
            self.all_match = False


@dataclass
class FixResult:
    """Result of fixing counts."""

    fixed_count: int
    files_modified: list[str]


def count_files(directory: str, pattern: str, base_dir: Path | None = None) -> int:
    """Count files matching pattern in directory.

    Args:
        directory: Directory name relative to base_dir
        pattern: Glob pattern (e.g., "*.md" or "SKILL.md")
        base_dir: Base directory path (defaults to current working directory)

    Returns:
        Number of matching files
    """
    if base_dir is None:
        base_dir = Path.cwd()
    dir_path = base_dir / directory
    if not dir_path.exists():
        return 0

    return len(list(dir_path.glob(pattern)))


def extract_count_from_line(line: str, category: str) -> int | None:
    """Extract count from a documentation line.

    Handles multiple formats:
    - "34 commands" or "34 slash commands"
    - "8 agents" or "8 specialized agents"
    - "6 skills" or "6 skill definitions"

    Args:
        line: Line text to search
        category: Category name (commands, agents, skills)

    Returns:
        Extracted count or None if not found
    """
    # For skills/commands, also match the singular form (e.g., "skill
    # definitions", "command templates"). Pattern matches: number followed by
    # optional words and category name. Examples: "34 commands", "29 slash
    # command templates", "8 specialized agents", "6 skill definitions".
    if category == "skills":
        # Match both "skills" and "skill" (singular)
        pattern = r"(\d+)\s+\w*\s*skills?(?!\s+description)"
    elif category == "commands":
        # Match both "commands" and "command" (singular)
        pattern = r"(\d+)\s+\w*\s*commands?"
    else:
        pattern = rf"(\d+)\s+\w*\s*{category}"

    match = re.search(pattern, line, re.IGNORECASE)
    return int(match.group(1)) if match else None


def is_count_opted_out(lines: list[str], index: int) -> bool:
    """Return True if the count line at ``index`` is marked as opt-out.

    Checked in this order: (a) a trailing same-line marker anywhere after the
    count — usable inside a tree-fence ``#`` comment or a mermaid ``%%``
    comment; (b) a preceding-line ``<!-- ll-doc-count: ignore -->`` HTML
    comment, for plain markdown only. Shared by ``verify_documentation`` and
    ``fix_counts`` so the verifier and the rewriter can never disagree.

    Args:
        lines: All lines of the document (0-indexed).
        index: 0-indexed position of the line to check.

    Returns:
        True if the line should be skipped by count verification/fixing.
    """
    if _COUNT_IGNORE_MARKER in lines[index]:
        return True
    if index > 0 and lines[index - 1].strip() == _COUNT_IGNORE_MARKER_HTML:
        return True
    return False


def verify_documentation(
    base_dir: Path | None = None,
) -> VerificationResult:
    """Verify all documented counts against actual file counts.

    Args:
        base_dir: Base directory path (defaults to current working directory)

    Returns:
        VerificationResult with all results
    """
    if base_dir is None:
        base_dir = Path.cwd()
    result = VerificationResult(total_checked=0)

    # Get actual counts
    actual_counts: dict[str, int] = {}
    for category, (directory, pattern) in COUNT_TARGETS.items():
        actual_counts[category] = count_files(directory, pattern, base_dir)

    # Loops live in nested subdirs (e.g. loops/oracles/) and share a directory
    # with non-runnable library fragments (loops/lib/). Recursively enumerate
    # and filter to runnable FSM definitions so the verifier stays in sync
    # with `ll-loop validate`'s notion of "runnable".
    loops_dir = base_dir / COUNT_TARGETS["loops"][0]
    if loops_dir.exists():
        actual_counts["loops"] = sum(1 for p in loops_dir.rglob("*.yaml") if is_runnable_loop(p))

    # Adjust skill count to exclude bridge skills (auto-generated from commands/)
    # per the SKILL_COUNT_INCLUDES_BRIDGES decision.
    skills_dir = base_dir / "skills"
    if "skills" in actual_counts and skills_dir.exists() and not SKILL_COUNT_INCLUDES_BRIDGES:
        actual_counts["skills"] -= sum(
            1 for p in skills_dir.glob("*/SKILL.md") if BRIDGE_MARKER in p.read_text()
        )

    # Check each documentation file
    for doc_file in DOC_FILES:
        doc_path = base_dir / doc_file
        if not doc_path.exists():
            continue

        content = doc_path.read_text()
        lines = content.splitlines()

        for line_num, line in enumerate(lines, start=1):
            if is_count_opted_out(lines, line_num - 1):
                continue
            for category in COUNT_TARGETS:
                documented = extract_count_from_line(line, category)
                if documented is not None:
                    actual = actual_counts[category]
                    matches = documented == actual

                    count_result = CountResult(
                        category=category,
                        actual=actual,
                        documented=documented,
                        file=str(doc_file),
                        line=line_num,
                        matches=matches,
                    )
                    result.add_result(count_result)
                    result.total_checked += 1

    return result


# -- Enumeration-coverage checks (ENH-3195 checks 3-4) ---------------------
#
# Unlike the numeric callouts above, these compare *sets* derived from the
# filesystem/pyproject.toml against sets of names documented in a reference
# file, and report the specific missing entries rather than a count mismatch.
# `verify_coverage()` is the single entry point the pytest gate, `ll-verify-docs`,
# and `ll-doctor` all share — never re-derive these sets in a test file.

_PYPROJECT_PATH = "scripts/pyproject.toml"
_CLI_DOC_PATH = "docs/reference/CLI.md"
_HOOKS_JSON_PATH = "hooks/hooks.json"
_HOOKS_GUIDE_PATH = "docs/guides/BUILTIN_HOOKS_GUIDE.md"

_CLI_SECTION_RE = re.compile(r"^###\s+`?([A-Za-z0-9][\w.-]*)`?\s*$", re.MULTILINE)
_SH_BASENAME_RE = re.compile(r"\b([\w.-]+\.sh)\b")


def declared_entry_points(pyproject: Path) -> set[str]:
    """Return every ``[project.scripts]`` entry-point name declared in *pyproject*.

    Parsed with stdlib ``tomllib`` rather than ``importlib.metadata.entry_points()``,
    which reflects a possibly-stale editable install (ENH-3195 check 3).
    """
    import tomllib

    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return set(data.get("project", {}).get("scripts", {}))


def documented_cli_sections(cli_md: Path) -> set[str]:
    """Return every ``### `` heading name in *cli_md*, tolerating backticks."""
    text = cli_md.read_text(encoding="utf-8")
    return set(_CLI_SECTION_RE.findall(text))


def registered_hook_scripts(hooks_json: Path) -> set[str]:
    """Return the deduped set of ``*.sh`` basenames registered in *hooks_json*.

    Walks the nested ``hooks`` / matcher-entry / ``hooks`` structure and reduces
    each ``command`` string to its script basename (e.g. ``record-hook-event.sh``
    appears once even though it is registered under several events).
    """
    data = json.loads(hooks_json.read_text(encoding="utf-8"))
    scripts: set[str] = set()
    for matcher_entries in data.get("hooks", {}).values():
        for matcher_entry in matcher_entries:
            for hook in matcher_entry.get("hooks", []):
                command = hook.get("command", "")
                match = _SH_BASENAME_RE.search(command)
                if match:
                    scripts.add(match.group(1))
    return scripts


def documented_hook_names(guide: Path) -> set[str]:
    """Return every ``*.sh`` basename named anywhere in *guide*."""
    text = guide.read_text(encoding="utf-8")
    return set(_SH_BASENAME_RE.findall(text))


def verify_coverage(base_dir: Path | None = None) -> VerificationResult:
    """Verify enumeration coverage: every CLI entry point and registered hook
    is named in its reference doc.

    Unlike ``verify_documentation``'s numeric callouts, a failure here reports
    the specific missing entry-point/hook names via ``CountResult.missing``
    rather than a single documented/actual pair.

    Args:
        base_dir: Base directory path (defaults to current working directory)

    Returns:
        VerificationResult with coverage-gap mismatches, if any
    """
    if base_dir is None:
        base_dir = Path.cwd()
    result = VerificationResult(total_checked=0)

    pyproject = base_dir / _PYPROJECT_PATH
    cli_doc = base_dir / _CLI_DOC_PATH
    if pyproject.exists() and cli_doc.exists():
        entry_points = declared_entry_points(pyproject)
        cli_sections = documented_cli_sections(cli_doc)
        missing_cli = sorted(entry_points - cli_sections)
        result.add_result(
            CountResult(
                category="cli_entry_points",
                actual=len(entry_points),
                documented=len(cli_sections & entry_points),
                file=_CLI_DOC_PATH,
                matches=not missing_cli,
                missing=missing_cli,
            )
        )
        result.total_checked += 1

    hooks_json = base_dir / _HOOKS_JSON_PATH
    hooks_guide = base_dir / _HOOKS_GUIDE_PATH
    if hooks_json.exists() and hooks_guide.exists():
        registered = registered_hook_scripts(hooks_json)
        documented = documented_hook_names(hooks_guide)
        missing_hooks = sorted(registered - documented)
        result.add_result(
            CountResult(
                category="hooks",
                actual=len(registered),
                documented=len(documented & registered),
                file=_HOOKS_GUIDE_PATH,
                matches=not missing_hooks,
                missing=missing_hooks,
            )
        )
        result.total_checked += 1

    return result


def format_result_text(result: VerificationResult) -> str:
    """Format verification result as text.

    Args:
        result: Verification result

    Returns:
        Formatted text output
    """
    lines = ["Documentation Count Verification", "=" * 40]

    if result.all_match:
        lines.append(f"✓ All {result.total_checked} count(s) match!")
    else:
        lines.append(f"✗ Found {len(result.mismatches)} mismatch(es):")
        lines.append("")

        for mismatch in result.mismatches:
            if mismatch.missing:
                lines.append(f"  {mismatch.category}: missing {', '.join(mismatch.missing)}")
            else:
                lines.append(
                    f"  {mismatch.category}: documented={mismatch.documented}, actual={mismatch.actual}"
                )
            if mismatch.line is not None:
                lines.append(f"    at {mismatch.file}:{mismatch.line}")
            elif mismatch.file is not None:
                lines.append(f"    at {mismatch.file}")

    return "\n".join(lines)


def format_result_json(result: VerificationResult) -> str:
    """Format verification result as JSON.

    Args:
        result: Verification result

    Returns:
        JSON string
    """
    data = {
        "all_match": result.all_match,
        "total_checked": result.total_checked,
        "mismatches": [
            {
                "category": m.category,
                "documented": m.documented,
                "actual": m.actual,
                "file": m.file,
                "line": m.line,
                "action_severity": m.action_severity,
                "route_owner": m.route_owner,
                "missing": m.missing,
            }
            for m in result.mismatches
        ],
    }

    return json.dumps(data, indent=2)


def format_result_markdown(result: VerificationResult) -> str:
    """Format verification result as Markdown.

    Args:
        result: Verification result

    Returns:
        Markdown formatted string
    """
    lines = ["# Documentation Count Verification", ""]

    if result.all_match:
        lines.append("## ✅ All Counts Match")
        lines.append(f"\nAll {result.total_checked} documented count(s) are accurate.")
    else:
        lines.append("## ❌ Mismatches Found")
        lines.append("")
        lines.append("| Category | Documented | Actual | Location |")
        lines.append("|----------|-----------|--------|----------|")

        for mismatch in result.mismatches:
            location = (
                f"`{mismatch.file}:{mismatch.line}`"
                if mismatch.line is not None
                else f"`{mismatch.file}`"
            )
            if mismatch.missing:
                lines.append(
                    f"| {mismatch.category} | missing: {', '.join(mismatch.missing)} | | {location} |"
                )
            else:
                lines.append(
                    f"| {mismatch.category} | {mismatch.documented} | "
                    f"{mismatch.actual} | {location} |"
                )

    return "\n".join(lines)


@dataclass
class SkillBudgetResult:
    """Result of checking skill description token budget."""

    total_tokens: int
    threshold_tokens: int
    under_budget: bool
    skill_breakdown: list[tuple[Path, str, int]]
    violations: list[tuple[Path, str, int]]


def _parse_skill_frontmatter(text: str) -> dict[str, str]:
    """Extract flat key/value pairs from SKILL.md frontmatter.

    Uses yaml.safe_load so YAML block scalars (e.g. ``description: |``)
    are resolved to their string content instead of the indicator literal.
    Non-string scalar values are stringified; nested structures are dropped.

    If the frontmatter is not valid YAML (e.g. unquoted colons in values),
    falls back to a permissive line-based scan that mirrors the historical
    behaviour — top-level ``key: value`` pairs, block scalars not supported.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    fm_text = text[3:end]
    try:
        loaded = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        loaded = None
    if isinstance(loaded, dict):
        fm: dict[str, str] = {}
        for key, value in loaded.items():
            if value is None:
                fm[str(key)] = ""
            elif isinstance(value, str):
                fm[str(key)] = value
            elif isinstance(value, bool | int | float):
                fm[str(key)] = str(value).lower() if isinstance(value, bool) else str(value)
        return fm
    fm = {}
    for line in fm_text.splitlines():
        if line and not line.startswith(" ") and not line.startswith("\t") and ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm


def check_skill_budget(
    base_dir: Path | None = None,
    threshold_tokens: int = _DEFAULT_BUDGET_TOKENS,
    per_skill_warn_tokens: int = _DEFAULT_PER_SKILL_WARN_TOKENS,
) -> SkillBudgetResult:
    """Scan skills/*/SKILL.md description fields, estimate tokens, check budget.

    Skips skills with ``disable-model-invocation: true``.  Token estimate uses
    the character-count approximation ``len(description) // 4``.

    Args:
        base_dir: Base directory (defaults to cwd)
        threshold_tokens: Total token budget (default: 2000 = ~1% of 200k context)
        per_skill_warn_tokens: Per-skill threshold for listing as a violation

    Returns:
        SkillBudgetResult with total, sorted breakdown, and per-skill violations
    """
    if base_dir is None:
        base_dir = Path.cwd()

    skills_dir = base_dir / "skills"
    skill_breakdown: list[tuple[Path, str, int]] = []

    if skills_dir.exists():
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            try:
                text = skill_md.read_text()
            except OSError:
                continue
            fm = _parse_skill_frontmatter(text)
            if fm.get("disable-model-invocation", "").lower() in ("true", "yes", "1"):
                continue
            description = fm.get("description", "")
            tokens = len(description) // 4
            skill_breakdown.append((skill_md, description, tokens))

    skill_breakdown.sort(key=lambda x: x[2], reverse=True)
    total_tokens = sum(t for _, _, t in skill_breakdown)
    violations = [(p, d, t) for p, d, t in skill_breakdown if t >= per_skill_warn_tokens]

    return SkillBudgetResult(
        total_tokens=total_tokens,
        threshold_tokens=threshold_tokens,
        under_budget=total_tokens <= threshold_tokens,
        skill_breakdown=skill_breakdown,
        violations=violations,
    )


def check_skill_sizes(
    base_dir: Path | None = None,
    limit: int = 500,
) -> list[tuple[Path, int]]:
    """Scan skills/*/SKILL.md files and return those exceeding the line limit.

    Skips skills with ``disable-model-invocation: true``.

    Args:
        base_dir: Base directory (defaults to cwd)
        limit: Maximum allowed lines per SKILL.md (default: 500)

    Returns:
        List of (path, line_count) pairs where line_count > limit
    """
    if base_dir is None:
        base_dir = Path.cwd()

    skills_dir = base_dir / "skills"
    violations: list[tuple[Path, int]] = []

    if not skills_dir.exists():
        return violations

    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            text = skill_md.read_text()
        except OSError:
            continue
        fm = _parse_skill_frontmatter(text)
        if fm.get("disable-model-invocation", "").lower() in ("true", "yes", "1"):
            continue
        line_count = len(text.splitlines())
        if line_count > limit:
            violations.append((skill_md, line_count))

    return violations


def fix_counts(base_dir: Path, result: VerificationResult) -> FixResult:
    """Fix count mismatches in documentation files.

    Only ``auto``-severity mismatches are rewritten. ``mention`` mismatches
    need a human to confirm; ``route`` mismatches are owned by another
    command's repair flow (see ``CountResult.action_severity``).

    Args:
        base_dir: Base directory path
        result: Verification result with mismatches

    Returns:
        FixResult with counts of fixes made
    """
    files_modified: set[str] = set()
    fixed_count = 0

    # Group mismatches by file (auto-severity only)
    mismatches_by_file: dict[str, list[CountResult]] = {}
    for mismatch in result.mismatches:
        if mismatch.action_severity != "auto":
            continue
        if mismatch.file:
            mismatches_by_file.setdefault(mismatch.file, []).append(mismatch)

    # Fix each file
    for file_path, mismatches in mismatches_by_file.items():
        doc_path = base_dir / file_path
        content = doc_path.read_text()
        lines = content.splitlines()

        for mismatch in mismatches:
            # CoverageGap-shaped mismatches (category "cli_entry_points"/"hooks")
            # carry no file:line — they name missing entries, not a number to
            # rewrite, and are already excluded from mismatches_by_file above
            # since mismatch.file is None for them.
            if mismatch.line is not None and 1 <= mismatch.line <= len(lines):
                if is_count_opted_out(lines, mismatch.line - 1):
                    continue
                line = lines[mismatch.line - 1]

                # Build regex pattern based on category
                # For skills/commands, also match the singular form
                if mismatch.category == "skills":
                    pattern = r"(\d+)(\s+\w*\s*skills?(?!\s+description))"
                elif mismatch.category == "commands":
                    pattern = r"(\d+)(\s+\w*\s*commands?)"
                else:
                    pattern = rf"(\d+)(\s+\w*\s*{re.escape(mismatch.category)})"

                # Replace the count while preserving the rest of the line
                new_line = re.sub(
                    pattern,
                    str(mismatch.actual) + r"\2",
                    line,
                    count=1,  # Only replace first occurrence
                    flags=re.IGNORECASE,
                )

                if new_line != line:
                    lines[mismatch.line - 1] = new_line
                    fixed_count += 1
                    files_modified.add(file_path)

        # Write back if changes were made
        if file_path in files_modified:
            doc_path.write_text("\n".join(lines))

    return FixResult(
        fixed_count=fixed_count,
        files_modified=list(files_modified),
    )
