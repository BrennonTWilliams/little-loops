"""Documentation count verification utilities.

Provides automated verification that documented counts (commands, agents, skills)
match actual file counts in the codebase.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

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
    "skills": ("skills", "SKILL.md"),
}


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

    # Use rglob for recursive search to handle subdirectories
    return len(list(dir_path.rglob(pattern)))


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
        pattern = r"(\d+)\s+\w*\s*skills?"
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
                    pattern = r"(\d+)(\s+\w*\s*skills?)"
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
