"""Pre-patch check core (ENH-3142) — candidate identification, execution, verdict.

Deterministic only -- no LLM calls, no FSM or CLI-orchestrator knowledge.
Adapters (ENH-2997 FSM executor, ENH-2998 non-FSM adapter) own step timing and
call into this module; this module never calls into either adapter. It also
performs no database access -- ``base_sha``/``base_dirty`` arrive as arguments,
resolved by the host via :func:`little_loops.history_reader.read_base_sha` /
:func:`little_loops.history_reader.read_base_dirty`.

A candidate test is a newly added or modified test function identified from a
verification step's diff. Running it against a worktree forked at the
pre-patch base (built by :func:`little_loops.worktree_utils.setup_prepatch_worktree`)
answers the question the LLM-judged criteria cannot: does this test actually
fail without the change it claims to demonstrate? A test that passes on both
trees is evidence of nothing and is flagged.
"""

from __future__ import annotations

import os
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.config.core import BRConfig
from little_loops.test_file_patterns import filter_test_files
from little_loops.test_tamper_guard import extract_test_functions, read_paths_at_ref
from little_loops.worktree_utils import setup_prepatch_worktree

if TYPE_CHECKING:
    from little_loops.logger import Logger
    from little_loops.parallel.git_lock import GitLock

_MERGE_BASE_TIMEOUT_S = 10
_DIFF_FILE_RE = re.compile(r"^\+\+\+ (?:b/)?(.+)$")
_DIFF_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class PrePatchCandidate:
    """One identified candidate before it is run."""

    nodeid: str
    file: str
    added: bool
    attribution: str  # "function" | "file-fallback"


@dataclass
class PrePatchTestOutcome:
    """One candidate test's result."""

    nodeid: str
    file: str
    added: bool
    category: str  # pass | fail | error | timeout | flaky
    error_kind: str | None
    flag: str  # hard | soft | none
    flag_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "nodeid": self.nodeid,
            "file": self.file,
            "added": self.added,
            "category": self.category,
            "error_kind": self.error_kind,
            "flag": self.flag,
            "flag_reason": self.flag_reason,
        }


@dataclass
class PrePatchEvidence:
    """The per-step bundle: base state used, per-test outcomes, and rollup verdict."""

    base_ref: str
    base_source: str  # "dequeue-stamp" | "merge-base"
    base_dirty: bool | None
    outcomes: list[PrePatchTestOutcome] = field(default_factory=list)
    verdict: str = "clean"  # clean | flagged | skipped
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "base_ref": self.base_ref,
            "base_source": self.base_source,
            "base_dirty": self.base_dirty,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "verdict": self.verdict,
            "skipped_reason": self.skipped_reason,
        }


def _parse_diff(step_diff: str) -> dict[str, list[int]]:
    """Map each touched (added-at-b/) file to its post-patch touched line numbers.

    Only ``+`` lines count as touched -- context and removed lines don't
    identify new-or-modified content. A file that appears via a ``+++``
    header but has no ``+`` lines (pure deletion) maps to an empty list.
    """
    touched: dict[str, list[int]] = {}
    current_path: str | None = None
    current_line = 0
    for line in step_diff.splitlines():
        file_match = _DIFF_FILE_RE.match(line)
        if file_match:
            path = file_match.group(1).strip()
            current_path = None if path == "/dev/null" else path
            if current_path is not None:
                touched.setdefault(current_path, [])
            continue
        hunk_match = _DIFF_HUNK_RE.match(line)
        if hunk_match:
            current_line = int(hunk_match.group(1))
            continue
        if current_path is None:
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            touched[current_path].append(current_line)
            current_line += 1
        elif line.startswith("-"):
            continue
        elif line.startswith(" ") or line == "":
            current_line += 1
    return touched


def _node_range(node: Any) -> tuple[int, int]:
    start = node.lineno
    end = getattr(node, "end_lineno", start) or start
    return start, end


def collect_candidates(
    step_diff: str,
    repo_root: Path,
    base_ref: str,
    config: BRConfig | None = None,
) -> list[PrePatchCandidate]:
    """Identify candidate tests added or modified by *step_diff*.

    Function-level attribution via `extract_test_functions()` +
    `read_paths_at_ref()`'s ``set(after) - set(before)`` split. When a
    touched line falls outside every top-level test function's range (class-
    based tests, conftest changes, module-level edits), attribution is
    ambiguous and the whole file becomes one file-fallback candidate instead
    -- never the full suite.
    """
    touched = _parse_diff(step_diff)
    test_paths = filter_test_files(list(touched.keys()), config=config)
    if not test_paths:
        return []
    before_texts = read_paths_at_ref(repo_root, base_ref, test_paths)
    candidates: list[PrePatchCandidate] = []
    for path in test_paths:
        if Path(path).name == "conftest.py":
            # Fixtures only -- never a runnable pytest target on its own.
            continue
        touched_lines = touched.get(path, [])
        if not touched_lines:
            continue
        abs_path = repo_root / path
        if not abs_path.is_file():
            continue
        after_src = abs_path.read_text()
        before_src = before_texts.get(path)
        after_map = extract_test_functions(after_src)
        before_map = extract_test_functions(before_src) if before_src is not None else {}
        is_new_file = before_src is None
        if after_map is None or before_map is None or not after_map:
            candidates.append(
                PrePatchCandidate(
                    nodeid=path, file=path, added=is_new_file, attribution="file-fallback"
                )
            )
            continue
        after_lines = after_src.splitlines()
        touched_line_set = set(touched_lines)
        # Blank lines (diff noise between top-level defs) don't force ambiguity.
        significant_lines = {
            ln
            for ln in touched_line_set
            if 1 <= ln <= len(after_lines) and after_lines[ln - 1].strip() != ""
        }
        touched_names = {
            name
            for name, node in after_map.items()
            if any(
                start <= ln <= end for ln in touched_line_set for start, end in [_node_range(node)]
            )
        }
        covered_lines = {
            ln
            for name in touched_names
            for start, end in [_node_range(after_map[name])]
            for ln in touched_line_set
            if start <= ln <= end
        }
        if not touched_names or not significant_lines.issubset(covered_lines):
            candidates.append(
                PrePatchCandidate(
                    nodeid=path, file=path, added=is_new_file, attribution="file-fallback"
                )
            )
            continue
        for name in sorted(touched_names):
            candidates.append(
                PrePatchCandidate(
                    nodeid=f"{path}::{name}",
                    file=path,
                    added=name not in before_map,
                    attribution="function",
                )
            )
    return candidates


def _post_patch_test_files(
    step_diff: str, repo_root: Path, config: BRConfig | None
) -> dict[str, str]:
    """Post-patch (working-tree) content for every touched test path, incl. conftest.py."""
    touched = _parse_diff(step_diff)
    test_paths = filter_test_files(list(touched.keys()), config=config)
    files: dict[str, str] = {}
    for path in test_paths:
        abs_path = repo_root / path
        if abs_path.is_file():
            files[path] = abs_path.read_text()
    return files


def _merge_base(repo_root: Path, base_branch: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "merge-base", "HEAD", base_branch],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=_MERGE_BASE_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    sha = proc.stdout.strip()
    return sha or None


def _run_pytest(
    worktree_path: Path,
    targets: list[str],
    junit_path: Path,
    timeout_s: int,
    src_dir: str,
    logger: Logger,
) -> bool:
    """Run pytest against *targets* in the worktree. Returns True if it timed out."""
    env = dict(os.environ)
    prepend = str(worktree_path / src_dir)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{prepend}{os.pathsep}{existing}" if existing else prepend
    cmd = ["python", "-m", "pytest", *targets, f"--junit-xml={junit_path}", "-q"]
    try:
        subprocess.run(
            cmd,
            cwd=str(worktree_path),
            env=env,
            timeout=timeout_s,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"prepatch_check: pytest invocation timed out after {timeout_s}s")
        return True
    except OSError as exc:
        logger.warning(f"prepatch_check: pytest invocation failed to start: {exc}")
    return False


def _classify_error(message: str) -> str:
    if (
        "ModuleNotFoundError" in message
        or "ImportError" in message
        or "collection" in message.lower()
    ):
        return "collection"
    return "infrastructure"


def _reconstruct_nodeid(file_attr: str, classname: str, name: str) -> str:
    dotted_file = (
        file_attr[:-3].replace("/", ".")
        if file_attr.endswith(".py")
        else file_attr.replace("/", ".")
    )
    if classname.startswith(dotted_file + "."):
        remainder = classname[len(dotted_file) + 1 :]
        if remainder:
            return f"{file_attr}::{remainder}::{name}"
    return f"{file_attr}::{name}"


def _parse_junit(junit_path: Path) -> dict[str, tuple[str, str | None]]:
    """Parse a ``--junit-xml`` report into ``{nodeid: (category, error_kind)}``."""
    if not junit_path.is_file():
        return {}
    try:
        tree = ET.parse(junit_path)
    except ET.ParseError:
        return {}
    results: dict[str, tuple[str, str | None]] = {}
    for testcase in tree.getroot().iter("testcase"):
        name = testcase.get("name", "")
        file_attr = testcase.get("file")
        classname = testcase.get("classname", "")
        if file_attr:
            nodeid = _reconstruct_nodeid(file_attr, classname, name)
        else:
            nodeid = f"{classname}::{name}" if classname else name
        failure = testcase.find("failure")
        error = testcase.find("error")
        if failure is not None:
            results[nodeid] = ("fail", None)
        elif error is not None:
            msg = (error.get("message") or "") + " " + (error.text or "")
            results[nodeid] = ("error", _classify_error(msg))
        elif testcase.find("skipped") is not None:
            results[nodeid] = ("fail", None)
        else:
            results[nodeid] = ("pass", None)
    return results


def _apply_retry(
    nodeid: str,
    category: str,
    error_kind: str | None,
    retry_results: dict[str, tuple[str, str | None]],
) -> tuple[str, str | None]:
    if category == "pass" and nodeid in retry_results:
        retry_category, retry_error = retry_results[nodeid]
        if retry_category != "pass":
            return "flaky", retry_error
    return category, error_kind


def _assign_flag(
    added: bool,
    category: str,
    modified_hard: bool,
    base_dirty: bool | None,
) -> tuple[str, str | None]:
    if category not in ("pass", "flaky"):
        return "none", None
    if category == "flaky":
        return "soft", "pre-patch pass was not confirmed on retry (flaky)"
    if added:
        flag, reason = "hard", "newly added test passed pre-patch"
    elif modified_hard:
        flag, reason = "hard", "modified test passed pre-patch (modified_hard enabled)"
    else:
        flag, reason = "soft", "modified test passed pre-patch"
    if flag == "hard" and base_dirty:
        return "soft", f"{reason}; downgraded because base was dirty at dequeue"
    return flag, reason


def run_prepatch_check(
    *,
    step_diff: str,
    repo_root: Path,
    worktree_base: str | Path,
    base_sha: str | None,
    base_dirty: bool | None,
    base_branch: str,
    logger: Logger,
    git_lock: GitLock,
    config: BRConfig | None = None,
) -> PrePatchEvidence:
    """Run candidate tests from *step_diff* against the pre-patch worktree.

    Resolves the base ref itself (dequeue-stamp SHA, falling back to
    merge-base with *base_branch*), performs no database access -- the
    caller supplies ``base_sha``/``base_dirty`` from
    :func:`little_loops.history_reader.read_base_sha` /
    :func:`little_loops.history_reader.read_base_dirty`.
    """
    if config is None:
        config = BRConfig(repo_root)
    ppc = config.prepatch_check

    if base_sha:
        base_ref = base_sha
        base_source = "dequeue-stamp"
    else:
        base_ref = _merge_base(repo_root, base_branch) or base_branch
        base_source = "merge-base"

    if not ppc.enabled:
        return PrePatchEvidence(
            base_ref=base_ref,
            base_source=base_source,
            base_dirty=base_dirty,
            verdict="skipped",
            skipped_reason="pre-patch check skipped by config",
        )

    candidates = collect_candidates(step_diff, repo_root, base_ref, config=config)
    if not candidates:
        return PrePatchEvidence(
            base_ref=base_ref,
            base_source=base_source,
            base_dirty=base_dirty,
            verdict="skipped",
            skipped_reason="no candidate tests identified",
        )

    test_files = _post_patch_test_files(step_diff, repo_root, config)
    worktree_path = setup_prepatch_worktree(
        repo_root,
        worktree_base,
        base_ref,
        test_files,
        logger,
        git_lock,
        src_dir=config.project.src_dir,
    )

    run_dir = worktree_path / ".prepatch-run"
    run_dir.mkdir(parents=True, exist_ok=True)

    targets = sorted({c.nodeid for c in candidates})
    junit_path = run_dir / "prepatch.xml"
    timed_out = _run_pytest(
        worktree_path, targets, junit_path, ppc.timeout_s, config.project.src_dir, logger
    )
    first_results = _parse_junit(junit_path)

    passing = sorted(nid for nid, (cat, _err) in first_results.items() if cat == "pass")
    retry_results: dict[str, tuple[str, str | None]] = {}
    if passing:
        retry_junit = run_dir / "prepatch-retry.xml"
        _run_pytest(
            worktree_path, passing, retry_junit, ppc.timeout_s, config.project.src_dir, logger
        )
        retry_results = _parse_junit(retry_junit)

    default_category = "timeout" if timed_out else "error"
    default_error_kind = None if timed_out else "infrastructure"

    outcomes: list[PrePatchTestOutcome] = []
    for candidate in candidates:
        if candidate.attribution == "file-fallback":
            matches = {
                nid: res
                for nid, res in first_results.items()
                if nid.startswith(candidate.file + "::")
            }
            if not matches:
                matches = {candidate.nodeid: (default_category, default_error_kind)}
        else:
            matches = {
                candidate.nodeid: first_results.get(
                    candidate.nodeid, (default_category, default_error_kind)
                )
            }
        for nid, (category, error_kind) in matches.items():
            final_category, final_error_kind = _apply_retry(
                nid, category, error_kind, retry_results
            )
            flag, flag_reason = _assign_flag(
                candidate.added, final_category, ppc.modified_hard, base_dirty
            )
            outcomes.append(
                PrePatchTestOutcome(
                    nodeid=nid,
                    file=candidate.file,
                    added=candidate.added,
                    category=final_category,
                    error_kind=final_error_kind,
                    flag=flag,
                    flag_reason=flag_reason,
                )
            )

    verdict = "flagged" if any(o.flag == "hard" for o in outcomes) else "clean"
    return PrePatchEvidence(
        base_ref=base_ref,
        base_source=base_source,
        base_dirty=base_dirty,
        outcomes=outcomes,
        verdict=verdict,
        skipped_reason=None,
    )
