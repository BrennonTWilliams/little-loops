"""Git operations for little-loops issue management.

Provides git status checking, verification of work done, file filtering
for excluded directories, and .gitignore pattern suggestions.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from little_loops.host_runner import project_child_env
from little_loops.logger import Logger
from little_loops.work_verification import (  # noqa: F401
    EXCLUDED_DIRECTORIES,
    _sample,
    filter_excluded_files,
    verify_work_was_done,
)

# BUG-2963 Option B: `.ll/` is noise for dirty-tree-preservation decisions
# (routinely dirty via `.ll/decisions.d/*.json` fragments, `.ll/
# stray-quarantine-*/` dirs) but is kept OUT of the shared
# `EXCLUDED_DIRECTORIES` above — that constant also gates
# `verify_work_was_done()`'s "was any real work done" question, where a
# `.ll/`-only change (e.g. a decisions-log entry) is legitimate work. See
# the Decision Rationale in BUG-2963 for the full analysis.
LL_NOISE_DIRECTORIES = (".ll/",)


def filter_ll_noise(paths: list[str]) -> list[str]:
    """Filter out ``.ll/``-rooted paths, layered on top of ``filter_excluded_files()``.

    Shared by the completion-commit pre-flight check (``issue_lifecycle.py``)
    and the worktree-teardown preservation backstop (``has_non_noise_dirty_paths``
    below) — the two BUG-2963 call sites that need "is this dirty path noise"
    without widening ``EXCLUDED_DIRECTORIES`` itself (Option B).
    """
    filtered = filter_excluded_files(paths)
    return [p for p in filtered if not any(p.startswith(d) for d in LL_NOISE_DIRECTORIES)]


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
        # ll-no-project: local git plumbing, no host CLI/credentials in play (ENH-3184 AC2)
        result = subprocess.run(
            ["git", "diff", "--quiet"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("Uncommitted changes detected in working directory")
            return True

        # ll-no-project: local git plumbing, no host CLI/credentials in play (ENH-3184 AC2)
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


def get_untracked_files(repo_root: Path | str = ".") -> list[str]:
    """Get list of untracked files from git status.

    Args:
        repo_root: Path to repository root. Defaults to current directory.

    Returns:
        List of untracked file paths (relative to repo root).
    """
    repo_root = Path(repo_root).resolve()

    try:
        # ll-no-project: local git plumbing, no host CLI/credentials in play (ENH-3184 AC2)
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


def file_matches_pattern(file_path: str, pattern: str) -> bool:
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


# Backwards-compat alias for existing in-module and cross-module callers.
_file_matches_pattern = file_matches_pattern


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
        if file_matches_pattern(file_path, pattern):
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
            if file_matches_pattern(file_path, pattern_obj.pattern):
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


# =============================================================================
# Porcelain parsing and dirty-tree preservation (BUG-2963)
# =============================================================================


def porcelain_paths(raw: str) -> list[str]:
    """Extract file paths from ``git status --porcelain -z`` output.

    Promoted from ``codequery/codegraph.py::_porcelain_paths`` (which only had
    two in-module callers and zero unit tests) to a public home shared with
    the completion-commit pre-flight check and the worktree-teardown
    preservation backstop, both of which need issue-file exclusion to be
    resolved-path equality rather than substring containment (BUG-2963).

    Consumes NUL-delimited (``-z``) porcelain records rather than the
    newline-delimited default, which sidesteps two problems with the
    newline format: rename lines use an ``old -> new`` arrow that is
    ambiguous if either path itself contains `` -> ``, and quoted paths are
    only quote-*stripped* (not octal-unescaped), so non-ASCII filenames come
    out as literal ``\\NNN``-style bytes. Under ``-z``, a rename/copy record
    is two consecutive NUL-terminated fields (new path, then old path) with
    no arrow and no quoting.

    Args:
        raw: stdout from ``git status --porcelain -z`` (NUL-terminated records).

    Returns:
        List of file paths (new path for renames/copies), in output order.
    """
    if not raw:
        return []
    records = raw.split("\x00")
    paths: list[str] = []
    i = 0
    n = len(records)
    while i < n:
        record = records[i]
        if not record:
            i += 1
            continue
        # Format: "XY path" — 2-char status code + 1 space + path.
        if len(record) < 4:
            i += 1
            continue
        status_code = record[:2]
        path = record[3:]
        paths.append(path)
        i += 1
        # Renames/copies are followed by a second NUL-terminated field: the
        # original path. Skip it — callers only want the current path.
        if status_code[0] in ("R", "C"):
            i += 1
    return paths


def snapshot_dirty_paths(repo_path: Path) -> frozenset[str]:
    """Capture the set of currently-dirty paths, for BUG-2963's run window.

    The ``pre_run_dirty`` snapshot that ``close_issue()`` /
    ``complete_issue_lifecycle()`` subtract from the close-time porcelain
    output: whatever is dirty *now* is pre-existing WIP, and anything that
    appears later is this run's deliverable.

    Capture this BEFORE the work runs. A snapshot taken afterwards already
    contains the deliverable, which would classify the entire implementation as
    pre-existing WIP and reproduce the incident this guard exists to prevent
    (BUG-2963 Proposed Solution #1, anchor warning).

    Args:
        repo_path: Working tree to snapshot.

    Returns:
        Frozen set of repo-relative paths, unfiltered (the noise filter is
        applied at close time, not here). Empty on any git failure — the
        conservative direction, since an empty snapshot makes the run window
        wider and so preserves more, never less.
    """
    try:
        # ll-no-project: local git plumbing, no host CLI/credentials in play (ENH-3184 AC2)
        result = subprocess.run(
            ["git", "status", "--porcelain", "-z"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return frozenset()
    if result.returncode != 0:
        return frozenset()
    return frozenset(porcelain_paths(result.stdout))


def abandoned_ref_name(identifier: str) -> str:
    """Build a durable ``refs/ll/abandoned/<identifier>-<timestamp>`` ref name.

    Args:
        identifier: Human-readable discriminator (issue ID, or
            ``worktree-<branch-or-dir-name>`` for the teardown backstop).
    """
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "-", identifier)
    return f"refs/ll/abandoned/{safe_id}-{ts}"


def preserve_dirty_tree(
    repo_path: Path,
    ref_name: str,
    logger: Logger | None = None,
) -> str | None:
    """Non-destructively snapshot a dirty working tree to a durable git ref.

    Uses a throwaway index (``GIT_INDEX_FILE``) so the real index and working
    tree are left byte-identical — this must NEVER be implemented with
    ``git stash``, which *removes* changes from the working tree it exists to
    preserve (BUG-2963 Proposed Solution #4 explicitly forbids stash here: in
    the ``ll-auto`` case there is no worktree, so "the tree being preserved"
    is the user's own working tree, and stash would also sweep away
    pre-existing WIP that BUG-2421's guarantee exists to leave untouched)::

        GIT_INDEX_FILE=<tmp> git add -A
        GIT_INDEX_FILE=<tmp> git write-tree          -> <tree>
        git commit-tree <tree> -p HEAD -m "..."      -> <sha>
        git update-ref <ref_name> <sha>

    Objects rooted under ``refs/`` are reachable, so ``git gc`` cannot reap
    them, and a ref written from inside a worktree survives
    ``git worktree remove --force`` because worktrees share the object
    database and ref store with the main repo. Gitignored paths are honored
    (``add -A`` respects ``.gitignore``) — nothing prunes this ref
    automatically; recover via ``git log <ref_name>`` / ``git checkout``.

    Args:
        repo_path: Working tree to snapshot (main repo or a worktree).
        ref_name: Full ref name to write, e.g. from :func:`abandoned_ref_name`.
        logger: Optional logger for error/success reporting.

    Returns:
        The created commit SHA, or ``None`` if there was nothing to preserve
        (clean tree) or an error occurred (logged at ``error`` level).
    """
    try:
        # ll-no-project: local git plumbing, no host CLI/credentials in play (ENH-3184 AC2)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        if logger:
            logger.error("preserve_dirty_tree: git status timed out")
        return None
    if status.returncode != 0 or not status.stdout.strip():
        return None

    try:
        # ll-no-project: local git plumbing, no host CLI/credentials in play (ENH-3184 AC2)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        if logger:
            logger.error("preserve_dirty_tree: git rev-parse HEAD timed out")
        return None
    if head.returncode != 0:
        if logger:
            logger.error(
                f"preserve_dirty_tree: could not resolve HEAD, skipping preservation: "
                f"{head.stderr.strip()}"
            )
        return None
    head_sha = head.stdout.strip()

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_index = str(Path(tmpdir) / "ll-preserve-index")
            env = project_child_env(extra={"GIT_INDEX_FILE": tmp_index})

            add_result = subprocess.run(
                ["git", "add", "-A"],
                cwd=repo_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if add_result.returncode != 0:
                if logger:
                    logger.error(
                        f"preserve_dirty_tree: throwaway-index `git add -A` failed: "
                        f"{add_result.stderr.strip()}"
                    )
                return None

            write_tree = subprocess.run(
                ["git", "write-tree"],
                cwd=repo_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if write_tree.returncode != 0:
                if logger:
                    logger.error(
                        f"preserve_dirty_tree: `git write-tree` failed: {write_tree.stderr.strip()}"
                    )
                return None
            tree_sha = write_tree.stdout.strip()
    except subprocess.TimeoutExpired:
        if logger:
            logger.error("preserve_dirty_tree: throwaway-index snapshot timed out")
        return None

    try:
        # ll-no-project: local git plumbing (commit-tree needs no throwaway-index env) (ENH-3184 AC2)
        commit_tree = subprocess.run(
            [
                "git",
                "commit-tree",
                tree_sha,
                "-p",
                head_sha,
                "-m",
                f"ll: abandoned work ({ref_name})",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        if logger:
            logger.error("preserve_dirty_tree: git commit-tree timed out")
        return None
    if commit_tree.returncode != 0:
        if logger:
            logger.error(
                f"preserve_dirty_tree: `git commit-tree` failed: {commit_tree.stderr.strip()}"
            )
        return None
    commit_sha = commit_tree.stdout.strip()

    try:
        # ll-no-project: local git plumbing (update-ref needs no throwaway-index env) (ENH-3184 AC2)
        update_ref = subprocess.run(
            ["git", "update-ref", ref_name, commit_sha],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        if logger:
            logger.error("preserve_dirty_tree: git update-ref timed out")
        return None
    if update_ref.returncode != 0:
        if logger:
            logger.error(
                f"preserve_dirty_tree: `git update-ref` failed: {update_ref.stderr.strip()}"
            )
        return None

    if logger:
        logger.error(f"Preserved dirty tree to {ref_name} ({commit_sha[:12]})")
    return commit_sha


def has_non_noise_dirty_paths(repo_path: Path) -> tuple[bool, list[str]]:
    """Check whether *repo_path* has dirty paths outside the noise filter.

    Used by the worktree-teardown preservation backstop (BUG-2963 Proposed
    Solution #8) to decide whether an imminent ``git worktree remove --force``
    would destroy something worth preserving to a durable ref. Reuses the same
    noise definition as the completion-commit pre-flight check
    (``filter_ll_noise`` — ``EXCLUDED_DIRECTORIES`` plus the adjacent
    ``.ll/``-only set).

    Returns:
        ``(has_non_noise_dirt, non_noise_paths)``
    """
    try:
        # ll-no-project: local git plumbing, no host CLI/credentials in play (ENH-3184 AC2)
        status = subprocess.run(
            ["git", "status", "--porcelain", "-z"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, []
    if status.returncode != 0 or not status.stdout:
        return False, []
    paths = porcelain_paths(status.stdout)
    non_noise = filter_ll_noise(paths)
    return (len(non_noise) > 0), non_noise


def preserve_before_teardown(
    worktree_path: Path,
    logger: Logger | None = None,
    identifier: str | None = None,
) -> str | None:
    """Preserve non-noise dirt to a durable ref before a worktree is destroyed.

    BUG-2963 Proposed Solution #8 — the backstop that makes the data-loss P1
    unreachable. Call immediately before any ``git worktree remove --force``.

    The per-issue ``pre_run_dirty`` discriminator rescues only the *first*
    orphan: a deliverable that survives one issue's close is present in the
    *next* issue's pre-run snapshot, is therefore classified as pre-existing
    WIP, is left alone by design — and is destroyed at teardown exactly as
    before. This backstop closes that gap at the other end, and is the broader
    guarantee: it holds for orphans from prior runs, from callers that never
    snapshot, and from paths no issue ever claimed.

    Args:
        worktree_path: The worktree about to be removed.
        logger: Optional logger. The preservation is reported at ``error``
            level (via :func:`preserve_dirty_tree`) because reaching this path
            at all means something was about to be lost.
        identifier: Discriminator for the ref name; defaults to
            ``worktree-<dir name>``.

    Returns:
        The preservation commit SHA, or ``None`` if there was nothing worth
        preserving (clean or noise-only tree) or the worktree is already gone.
    """
    if not worktree_path.exists():
        return None
    has_dirt, paths = has_non_noise_dirty_paths(worktree_path)
    if not has_dirt:
        return None
    if logger:
        logger.error(
            f"Worktree {worktree_path.name} holds {len(paths)} uncommitted non-noise "
            f"path(s) at teardown; preserving before removal: {_sample(sorted(paths), 10)}"
        )
    return preserve_dirty_tree(
        worktree_path,
        abandoned_ref_name(identifier or f"worktree-{worktree_path.name}"),
        logger,
    )
