"""Documentation count verification utilities.

Provides automated verification that documented counts (commands, agents, skills)
match actual file counts in the codebase.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

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


@dataclass
class CountResult:
    """Result of counting files in a directory."""

    category: str
    actual: int
    documented: int | None = None
    file: str | None = None
    line: int | None = None
    matches: bool = True


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
    # For skills, also match singular "skill" (e.g., "skill definitions")
    # Pattern matches: number followed by optional words and category name
    # Examples: "34 commands", "8 specialized agents", "6 skill definitions"
    if category == "skills":
        # Match both "skills" and "skill" (singular)
        pattern = r"(\d+)\s+\w*\s*skills?(?!\s+description)"
    else:
        pattern = rf"(\d+)\s+\w*\s*{category}"

    match = re.search(pattern, line, re.IGNORECASE)
    return int(match.group(1)) if match else None


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

    # Adjust skill count to exclude bridge skills (auto-generated from commands/)
    skills_dir = base_dir / "skills"
    if "skills" in actual_counts and skills_dir.exists():
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
            lines.append(
                f"  {mismatch.category}: documented={mismatch.documented}, actual={mismatch.actual}"
            )
            lines.append(f"    at {mismatch.file}:{mismatch.line}")

    return "\n".join(lines)


def format_result_json(result: VerificationResult) -> str:
    """Format verification result as JSON.

    Args:
        result: Verification result

    Returns:
        JSON string
    """
    import json

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
            lines.append(
                f"| {mismatch.category} | {mismatch.documented} | "
                f"{mismatch.actual} | `{mismatch.file}:{mismatch.line}` |"
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


def fix_counts(base_dir: Path, result: VerificationResult) -> FixResult:
    """Fix count mismatches in documentation files.

    Args:
        base_dir: Base directory path
        result: Verification result with mismatches

    Returns:
        FixResult with counts of fixes made
    """
    files_modified: set[str] = set()
    fixed_count = 0

    # Group mismatches by file
    mismatches_by_file: dict[str, list[CountResult]] = {}
    for mismatch in result.mismatches:
        if mismatch.file:
            mismatches_by_file.setdefault(mismatch.file, []).append(mismatch)

    # Fix each file
    for file_path, mismatches in mismatches_by_file.items():
        doc_path = base_dir / file_path
        content = doc_path.read_text()
        lines = content.splitlines()

        for mismatch in mismatches:
            if mismatch.line is not None and 1 <= mismatch.line <= len(lines):
                line = lines[mismatch.line - 1]

                # Build regex pattern based on category
                # For skills, also match singular "skill"
                if mismatch.category == "skills":
                    pattern = r"(\d+)(\s+\w*\s*skills?(?!\s+description))"
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
