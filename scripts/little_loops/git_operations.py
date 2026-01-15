"""Git operations for little-loops issue management.

Provides git status checking, verification of work done, file filtering
for excluded directories, and .gitignore pattern suggestions.
"""

from __future__ import annotations

import fnmatch
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from little_loops.logger import Logger

# Directories that are excluded when verifying work was done.
# Changes to files in these directories don't count as "real work".
EXCLUDED_DIRECTORIES = (
    ".issues/",
    "issues/",  # Support non-dotted variant (issues.base_dir = "issues")
    ".speckit/",
    "thoughts/",
    ".worktrees/",
    ".auto-manage",
)


# Common .gitignore patterns with metadata.
# Format: (pattern, category, description, priority)
# Lower priority number = higher precedence when matching files.
COMMON_GITIGNORE_PATTERNS: list[tuple[str, str, str, int]] = [
    # Coverage reports (priority 1 - very common)
    ("coverage.json", "coverage", "Coverage report JSON", 1),
    ("*.coverage", "coverage", "Coverage data files", 1),
    (".coverage*", "coverage", "Coverage data files", 1),
    (".nyc_output/", "coverage", "NYC coverage output", 2),
    # Environment files (priority 1 - security sensitive)
    (".env", "environment", "Environment variables", 1),
    (".env.*", "environment", "Environment-specific configs", 1),
    (".env.local", "environment", "Local environment overrides", 1),
    (".env.*.local", "environment", "Local environment overrides", 2),
    # Log files (priority 2 - common clutter)
    ("*.log", "logs", "Application log files", 2),
    ("logs/", "logs", "Log directory", 2),
    # Python (priority 2)
    ("__pycache__/", "python", "Python bytecode cache", 2),
    ("*.pyc", "python", "Python compiled files", 2),
    ("*.pyo", "python", "Python optimized files", 2),
    (".pytest_cache/", "python", "Pytest cache", 2),
    (".mypy_cache/", "python", "MyPy type cache", 2),
    ("*.egg-info/", "python", "Python package metadata", 3),
    # Node.js (priority 2)
    ("node_modules/", "nodejs", "Node.js dependencies", 2),
    ("package-lock.json", "nodejs", "NPM lock file", 3),
    ("yarn.lock", "nodejs", "Yarn lock file", 3),
    ("*.tgz", "nodejs", "NPM package tarballs", 3),
    # Build artifacts (priority 2)
    ("dist/", "build", "Distribution directory", 2),
    ("build/", "build", "Build directory", 2),
    ("*.egg", "python", "Python egg distribution", 3),
    # OS files (priority 3)
    (".DS_Store", "os", "macOS directory metadata", 3),
    (".DS_Store?", "os", "macOS directory metadata (variant)", 3),
    ("._*", "os", "macOS resource forks", 3),
    ("Thumbs.db", "os", "Windows thumbnail cache", 3),
    ("ehthumbs.db", "os", "Windows thumbnail cache (variant)", 3),
    ("Desktop.ini", "os", "Windows desktop settings", 3),
    # Editor/IDE (priority 3)
    (".idea/", "editor", "JetBrains IDE config", 3),
    (".vscode/", "editor", "VS Code config", 3),
    ("*.swp", "editor", "Vim swap files", 3),
    ("*.swo", "editor", "Vim swap files", 3),
    ("*~", "editor", "Backup files", 3),
    (".project", "editor", "Eclipse project", 3),
    (".settings/", "editor", "Eclipse settings", 3),
    # Temporary files (priority 2)
    ("*.tmp", "temp", "Temporary files", 2),
    ("tmp/", "temp", "Temp directory", 2),
    ("temp/", "temp", "Temp directory", 2),
    # State files (priority 2)
    ("*-state.json", "state", "State tracking files", 2),
    (".state.json", "state", "State tracking files", 2),
    # Runtime and cache (priority 2)
    (".cache/", "cache", "Cache directory", 2),
    (".parcel-cache/", "cache", "Parcel bundler cache", 3),
    # Database (priority 3)
    ("*.db", "database", "Database files", 3),
    ("*.sqlite", "database", "SQLite databases", 3),
    ("*.sqlite3", "database", "SQLite databases", 3),
]


@dataclass
class GitignorePattern:
    """Represents a suggested .gitignore pattern with metadata.

    Attributes:
        pattern: The .gitignore pattern string (e.g., "*.log", ".env")
        category: Category of file (e.g., "coverage", "environment", "logs")
        description: Human-readable description of what this pattern matches
        files_matched: List of untracked files that match this pattern
        priority: Priority for suggestion (1=highest, 5=lowest).
    """

    pattern: str
    category: str
    description: str
    files_matched: list[str] = field(default_factory=list)
    priority: int = 3

    def __post_init__(self) -> None:
        """Validate and normalize the pattern."""
        self.pattern = self.pattern.strip()
        if not self.pattern:
            raise ValueError("Pattern cannot be empty")

    @property
    def is_wildcard(self) -> bool:
        """Return True if pattern contains wildcards."""
        return "*" in self.pattern or "?" in self.pattern

    @property
    def is_directory(self) -> bool:
        """Return True if pattern targets a directory."""
        return self.pattern.endswith("/")


@dataclass
class GitignoreSuggestion:
    """Container for gitignore suggestions with user interaction helpers.

    Attributes:
        patterns: List of suggested patterns
        existing_gitignore: Path to .gitignore file
        already_ignored: Files already covered by existing .gitignore
        total_files: Total untracked files examined
    """

    patterns: list[GitignorePattern] = field(default_factory=list)
    existing_gitignore: Path | None = None
    already_ignored: list[str] = field(default_factory=list)
    total_files: int = 0

    @property
    def has_suggestions(self) -> bool:
        """Return True if there are patterns to suggest."""
        return len(self.patterns) > 0

    @property
    def files_to_ignore(self) -> list[str]:
        """Get all files that would be ignored by suggested patterns."""
        files: list[str] = []
        for pattern in self.patterns:
            files.extend(pattern.files_matched)
        return sorted(set(files))

    @property
    def summary(self) -> str:
        """Generate a human-readable summary of suggestions."""
        if not self.has_suggestions:
            return "No .gitignore suggestions needed."

        total_files = len(self.files_to_ignore)
        pattern_count = len(self.patterns)
        return f"Found {total_files} file(s) matching {pattern_count} .gitignore pattern(s)."


def check_git_status(logger: Logger) -> bool:
    """Check for uncommitted changes.

    Args:
        logger: Logger for output

    Returns:
        True if there are uncommitted changes
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--quiet"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("Uncommitted changes detected in working directory")
            return True

        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("Uncommitted staged changes detected")
            return True

        return False
    except Exception as e:
        logger.warning(f"Could not check git status: {e}")
        return True


def filter_excluded_files(files: list[str]) -> list[str]:
    """Filter out files in excluded directories.

    Args:
        files: List of file paths to filter

    Returns:
        List of files not in excluded directories
    """
    return [
        f
        for f in files
        if f and not any(f.startswith(excluded) for excluded in EXCLUDED_DIRECTORIES)
    ]


def verify_work_was_done(logger: Logger, changed_files: list[str] | None = None) -> bool:
    """Verify that actual work was done (not just issue file moves).

    Returns True if there's evidence of implementation work - changes to files
    outside of excluded directories like .issues/, thoughts/, etc.

    This prevents marking issues as "completed" when no actual fix was implemented.

    Args:
        logger: Logger for output
        changed_files: Optional list of changed files. If not provided,
            will detect via git diff commands.

    Returns:
        True if meaningful file changes were detected
    """
    # If changed_files provided, use them directly (ll-parallel case)
    if changed_files is not None:
        meaningful_changes = filter_excluded_files(changed_files)
        if meaningful_changes:
            logger.info(
                f"Found {len(meaningful_changes)} file(s) changed: {meaningful_changes[:5]}"
            )
            return True
        logger.warning("No meaningful changes detected - only excluded files modified")
        return False

    # Otherwise detect via git (ll-auto case)
    try:
        # Check for uncommitted changes
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            files = result.stdout.strip().split("\n")
            meaningful_changes = filter_excluded_files(files)
            if meaningful_changes:
                logger.info(
                    f"Found {len(meaningful_changes)} file(s) changed: {meaningful_changes[:5]}"
                )
                return True

        # Also check staged changes
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            staged = result.stdout.strip().split("\n")
            meaningful_staged = filter_excluded_files(staged)
            if meaningful_staged:
                logger.info(
                    f"Found {len(meaningful_staged)} staged file(s): {meaningful_staged[:5]}"
                )
                return True

        logger.warning("No meaningful changes detected - only excluded files modified")
        return False

    except Exception as e:
        logger.error(f"Could not verify work: {e}")
        # Be conservative - don't assume work was done if we can't verify
        return False


def get_untracked_files(repo_root: Path | str = ".") -> list[str]:
    """Get list of untracked files from git status.

    Args:
        repo_root: Path to repository root. Defaults to current directory.

    Returns:
        List of untracked file paths (relative to repo root).
    """
    repo_root = Path(repo_root).resolve()

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    # Parse porcelain output: ?? for untracked files
    untracked: list[str] = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        # Format: XY filename
        # X = staged status, Y = unstaged status
        # ?? = untracked
        if line.startswith("??"):
            # Extract filename (after status markers)
            filename = line[3:].strip()
            # Handle quoted filenames with spaces
            if filename.startswith('"') and filename.endswith('"'):
                filename = filename[1:-1]
            untracked.append(filename)

    return sorted(untracked)


def _read_existing_gitignore(repo_root: Path) -> list[str]:
    """Read and parse existing .gitignore patterns.

    Args:
        repo_root: Path to repository root.

    Returns:
        List of existing patterns (stripped of comments and whitespace).
        Returns empty list if .gitignore doesn't exist.
    """
    gitignore_path = repo_root / ".gitignore"

    if not gitignore_path.exists():
        return []

    patterns: list[str] = []
    try:
        content = gitignore_path.read_text(encoding="utf-8")
        for line in content.split("\n"):
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith("#"):
                patterns.append(line)
    except (OSError, UnicodeDecodeError):
        # If we can't read it, assume empty
        return []

    return patterns


def _file_matches_pattern(file_path: str, pattern: str) -> bool:
    """Check if a file path matches a gitignore pattern.

    Implements gitignore-style matching semantics:
    - If pattern doesn't contain '/', it matches basename in any directory
    - If pattern contains '/', it matches relative to repo root
    - If pattern ends with '/', it matches a directory
    - Leading '/' anchors to repo root
    - Negation patterns (starting with !) match the same as their base pattern

    Args:
        file_path: File path relative to repo root
        pattern: Gitignore pattern (may start with ! for negation)

    Returns:
        True if file matches the base pattern (regardless of negation)
    """
    # Normalize paths
    file_path = file_path.replace("\\", "/")
    pattern = pattern.replace("\\", "/")

    # Strip negation prefix for matching logic
    # The negation is handled by _is_already_ignored()
    if pattern.startswith("!"):
        pattern = pattern[1:]

    # Handle directory patterns
    if pattern.endswith("/"):
        # Match if file is inside this directory
        dir_pattern = pattern.rstrip("/")
        return file_path == dir_pattern or file_path.startswith(dir_pattern + "/")

    # Handle patterns without path separator (match basename anywhere)
    if "/" not in pattern:
        basename = Path(file_path).name
        # Also check if pattern has wildcards
        if "*" in pattern or "?" in pattern:
            return fnmatch.fnmatch(basename, pattern)
        return basename == pattern

    # Handle patterns with path separator (match from root or subdirectory)
    if pattern.startswith("/"):
        # Anchored to root: must match from start
        return fnmatch.fnmatch(file_path, pattern[1:])
    else:
        # Not anchored: can match at any level
        # Check if it matches the full path
        if fnmatch.fnmatch(file_path, pattern):
            return True
        # Check if it matches any parent path
        parts = file_path.split("/")
        for i in range(len(parts)):
            subpath = "/".join(parts[i:])
            if fnmatch.fnmatch(subpath, pattern):
                return True
        return False


def _is_already_ignored(
    file_path: str,
    existing_patterns: list[str],
) -> bool:
    """Check if a file is already covered by existing .gitignore patterns.

    Processes patterns in order, with negation patterns (starting with !)
    overriding previous matches. This follows gitignore semantics where
    later patterns can negate earlier ones.

    Args:
        file_path: File path to check
        existing_patterns: List of patterns from .gitignore

    Returns:
        True if file is already ignored (final result after all patterns)
    """
    # Process patterns in order - later patterns override earlier ones
    is_ignored = False

    for pattern in existing_patterns:
        if _file_matches_pattern(file_path, pattern):
            # If pattern starts with !, it's a negation
            if pattern.startswith("!"):
                is_ignored = False
            else:
                is_ignored = True

    return is_ignored


def suggest_gitignore_patterns(
    untracked_files: list[str] | None = None,
    repo_root: Path | str = ".",
    logger: Logger | None = None,
) -> GitignoreSuggestion:
    """Analyze untracked files and suggest .gitignore patterns.

    This function examines untracked files and suggests common .gitignore
    patterns that should be added. It respects existing .gitignore patterns
    and won't suggest patterns for already-ignored files.

    Args:
        untracked_files: Optional list of untracked files. If None, will
            detect via git status.
        repo_root: Path to repository root. Defaults to current directory.
        logger: Optional logger for debug output.

    Returns:
        GitignoreSuggestion with suggested patterns and metadata.
    """
    repo_root = Path(repo_root).resolve()

    # Get untracked files if not provided
    if untracked_files is None:
        untracked_files = get_untracked_files(repo_root)

    if not untracked_files:
        return GitignoreSuggestion()

    # Read existing .gitignore
    existing_patterns = _read_existing_gitignore(repo_root)
    gitignore_path = repo_root / ".gitignore"

    # Build pattern objects from common patterns
    pattern_objects: list[GitignorePattern] = []
    for pattern_str, category, description, priority in COMMON_GITIGNORE_PATTERNS:
        pattern_objects.append(
            GitignorePattern(
                pattern=pattern_str,
                category=category,
                description=description,
                priority=priority,
            )
        )

    # Match files to patterns
    already_ignored: list[str] = []
    suggestions: dict[str, GitignorePattern] = {}

    for file_path in untracked_files:
        # Check if already covered by existing .gitignore
        if _is_already_ignored(file_path, existing_patterns):
            already_ignored.append(file_path)
            continue

        # Try to match against common patterns
        matched = False
        for pattern_obj in sorted(pattern_objects, key=lambda p: p.priority):
            if _file_matches_pattern(file_path, pattern_obj.pattern):
                # Add to suggestions (deduplicate by pattern)
                if pattern_obj.pattern not in suggestions:
                    suggestions[pattern_obj.pattern] = pattern_obj
                # Add this file to the pattern's match list
                if file_path not in suggestions[pattern_obj.pattern].files_matched:
                    suggestions[pattern_obj.pattern].files_matched.append(file_path)
                matched = True
                break  # Use first (highest priority) match

        # Log unmatched files for debugging
        if not matched and logger:
            logger.debug(f"No pattern match for: {file_path}")

    # Convert to sorted list (by priority, then category, then pattern)
    suggested_patterns = sorted(
        suggestions.values(),
        key=lambda p: (p.priority, p.category, p.pattern),
    )

    return GitignoreSuggestion(
        patterns=suggested_patterns,
        existing_gitignore=gitignore_path if gitignore_path.exists() else None,
        already_ignored=already_ignored,
        total_files=len(untracked_files),
    )


def add_patterns_to_gitignore(
    patterns: list[str],
    repo_root: Path | str = ".",
    logger: Logger | None = None,
    backup: bool = True,
) -> bool:
    """Add patterns to .gitignore file.

    Args:
        patterns: List of patterns to add (will skip duplicates)
        repo_root: Path to repository root
        logger: Optional logger for output
        backup: If True, create .gitignore.backup before modifying

    Returns:
        True if patterns were added successfully, False otherwise
    """
    repo_root = Path(repo_root).resolve()
    gitignore_path = repo_root / ".gitignore"

    # Read existing patterns
    existing_patterns = _read_existing_gitignore(repo_root)
    existing_set = set(existing_patterns)

    # Filter out patterns that already exist
    new_patterns = [p for p in patterns if p not in existing_set]

    if not new_patterns:
        if logger:
            logger.info("All patterns already exist in .gitignore")
        return True

    try:
        # Create backup if requested
        if backup and gitignore_path.exists():
            backup_path = repo_root / ".gitignore.backup"
            import shutil

            if logger:
                logger.debug(f"Creating backup: {backup_path}")
            shutil.copy2(gitignore_path, backup_path)

        # Build new content
        if gitignore_path.exists():
            content = gitignore_path.read_text(encoding="utf-8")
            # Ensure trailing newline
            if content and not content.endswith("\n"):
                content += "\n"
        else:
            content = ""

        # Add new patterns
        for pattern in new_patterns:
            content += f"{pattern}\n"

        # Write back
        gitignore_path.write_text(content, encoding="utf-8")

        if logger:
            logger.success(f"Added {len(new_patterns)} pattern(s) to .gitignore")
            for pattern in new_patterns:
                logger.info(f"  + {pattern}")

        return True

    except (OSError, UnicodeDecodeError) as e:
        if logger:
            logger.error(f"Failed to update .gitignore: {e}")
        return False
