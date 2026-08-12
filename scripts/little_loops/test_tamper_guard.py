"""Tamper guard core: snapshot/compare/revert over test files (ENH-2933).

Detects whether test files (or the pytest config files that gate which
tests run) were modified/deleted/added across a verification step, and acts
on any finding per a configured policy (``revert`` | ``fail`` | ``allow``).
Deterministic only -- no LLM calls, no FSM or CLI-orchestrator knowledge.
Adapters (ENH-2934, ENH-2935) own step timing and call into this module;
this module never calls into either adapter.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from little_loops.config.core import BRConfig
from little_loops.test_file_patterns import filter_test_files

TamperPolicy = Literal["revert", "fail", "allow"]

DEFAULT_TAMPER_POLICY: TamperPolicy = "fail"

TamperSnapshot = dict[str, str | None]

_GIT_TIMEOUT = 10


@dataclass
class TamperFinding:
    path: str
    kind: Literal["modified", "deleted", "added"]
    is_config: bool = False


@dataclass
class TamperReport:
    policy: TamperPolicy
    findings: list[TamperFinding] = field(default_factory=list)
    reverted: list[str] = field(default_factory=list)
    passed: bool = True


@dataclass
class TestStrength:
    assertions: int
    test_functions: int
    skip_markers: int


@dataclass
class ConfigTarget:
    """A pytest config file plus the sub-document that governs test selection.

    ``section`` is a dotted TOML table path (e.g. ``("tool", "pytest",
    "ini_options")``) for a multi-purpose config file like ``pyproject.toml``,
    or None for a single-purpose file (``pytest.ini``) where the whole file
    is already pytest-scoped and gets whole-file comparison.
    """

    path: str
    section: tuple[str, ...] | None


FindingFilter = Callable[[list[TamperFinding]], list[TamperFinding]]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str | None:
    """Return the sha256 hex digest of *path*'s on-disk bytes, or None if unreadable."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return _sha256_bytes(data)


def snapshot_test_paths(paths: list[str], repo_root: Path) -> TamperSnapshot:
    """Hash the on-disk content of *paths* (relative to *repo_root*).

    A path missing or unreadable at snapshot time maps to None. A path that
    is a section-scoped config target (``ConfigTarget.section`` set, e.g.
    ``pyproject.toml``'s ``[tool.pytest.ini_options]``) is hashed by its
    selected section only, so edits elsewhere in the file are invisible to
    the guard; every other path is hashed whole-file as before.
    """
    section_targets = {
        target.path: target
        for target in resolved_pytest_config_targets(repo_root)
        if target.section is not None
    }
    snapshot: TamperSnapshot = {}
    for path in paths:
        target = section_targets.get(path)
        if target is not None:
            text = _read_text_or_none(repo_root / path)
            snapshot[path] = hash_config_target(text, target) if text is not None else None
        else:
            snapshot[path] = _sha256_file(repo_root / path)
    return snapshot


def read_paths_at_ref(repo_root: Path, ref: str, paths: list[str]) -> dict[str, str | None]:
    """Read *paths* as they existed at git *ref*, returning source text (not hashes).

    The text-returning sibling of ``snapshot_test_paths_at_ref`` -- factors out
    the shared ``git show {ref}:{path}`` call so there is one implementation.
    A path absent at *ref* maps to None, matching ``snapshot_test_paths_at_ref``'s
    missing-file convention.
    """
    return {path: _git(repo_root, "show", f"{ref}:{path}") for path in paths}


def snapshot_test_paths_at_ref(repo_root: Path, ref: str, paths: list[str]) -> TamperSnapshot:
    """Hash *paths* as they existed at git *ref*, for a caller with no live pre-step snapshot.

    Adapters that bracket a single state's action (ENH-2934) capture ``before``
    via ``snapshot_test_paths`` immediately prior to running it. The non-FSM
    orchestrators (ENH-2935) verify once, after the whole run already
    happened, so there is no such live moment to snapshot from -- this
    reconstructs the equivalent "before" from the git object store instead. A
    path absent at *ref* (added since) maps to None, matching
    ``snapshot_test_paths``'s missing-file convention. Section-scoped config
    targets are hashed by their selected section only, matching
    ``snapshot_test_paths``'s section-aware behavior.
    """
    texts = read_paths_at_ref(repo_root, ref, paths)
    section_targets = {
        target.path: target
        for target in resolved_pytest_config_targets(repo_root)
        if target.section is not None
    }
    snapshot: TamperSnapshot = {}
    for path, text in texts.items():
        if text is None:
            snapshot[path] = None
            continue
        target = section_targets.get(path)
        snapshot[path] = (
            hash_config_target(text, target) if target is not None else _sha256_bytes(text.encode())
        )
    return snapshot


def tamper_guard_candidate_paths(repo_root: Path, config: BRConfig | None = None) -> list[str]:
    """Return the test-file + pytest-config paths to snapshot for the tamper guard.

    Enumerates tracked + untracked (non-ignored) repo files via git and
    narrows to test files (``test_file_patterns.filter_test_files``) plus the
    pytest config file(s) this repo actually reads
    (``resolved_pytest_config_paths``). Falls back to just the config paths if
    the git call fails (still lets the config-file half of the guard
    function). Shared by both adapters (ENH-2934's FSM executor and
    ENH-2935's non-FSM ``work_verification`` hook) so there is exactly one
    enumeration implementation.
    """
    config_paths = resolved_pytest_config_paths(repo_root)
    ls_files_out = _git(repo_root, "ls-files", "--cached", "--others", "--exclude-standard")
    if ls_files_out is None:
        return sorted(set(config_paths))
    all_paths = [line for line in ls_files_out.splitlines() if line]
    effective_config = config if config is not None else BRConfig(repo_root)
    return sorted(set(filter_test_files(all_paths, config=effective_config)) | set(config_paths))


def tamper_guard_changed_files(repo_root: Path) -> list[str]:
    """Return repo-relative paths touched since the guard's entry snapshot.

    Unions unstaged+staged modifications against HEAD with untracked
    (non-ignored) files, so a newly-added test file is visible to
    ``run_tamper_guard`` even though it couldn't have been in the entry
    snapshot. Shared by both adapters -- see ``tamper_guard_candidate_paths``.
    """
    diff_out = _git(repo_root, "diff", "--name-only", "HEAD")
    untracked_out = _git(repo_root, "ls-files", "--others", "--exclude-standard")
    changed: set[str] = set()
    if diff_out is not None:
        changed.update(line for line in diff_out.splitlines() if line)
    if untracked_out is not None:
        changed.update(line for line in untracked_out.splitlines() if line)
    return sorted(changed)


def compare_snapshots(before: TamperSnapshot, after: TamperSnapshot) -> list[TamperFinding]:
    """Diff two snapshots, reporting every modified/deleted/added path.

    ``is_config`` defaults to False on every finding; callers that need it
    set (e.g. ``run_tamper_guard``) tag it afterward against the resolved
    pytest config path set.
    """
    findings: list[TamperFinding] = []
    for path in sorted(set(before) | set(after)):
        before_hash = before.get(path)
        after_hash = after.get(path)
        if before_hash == after_hash:
            continue
        if before_hash is None:
            findings.append(TamperFinding(path=path, kind="added"))
        elif after_hash is None:
            findings.append(TamperFinding(path=path, kind="deleted"))
        else:
            findings.append(TamperFinding(path=path, kind="modified"))
    return findings


def _decorator_name(node: ast.expr) -> str:
    """Return the dotted/attribute name of a decorator node, or "" if not resolvable."""
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _call_name(node: ast.expr) -> str:
    """Return the dotted call target's final attribute/name, or "" if not resolvable."""
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


_CONDITIONAL_NODES = (
    ast.If,
    ast.Try,
    ast.While,
    ast.For,
    ast.AsyncFor,
    ast.With,
    ast.AsyncWith,
)


def _is_pytest_skip(func: ast.expr) -> bool:
    """True for ``pytest.skip(...)`` or a bare imported ``skip(...)``.

    Deliberately narrower than ``_call_name(func) == "skip"``: an unrelated
    ``runner.skip(...)`` / ``queue.skip(...)`` is not a pytest skip and must
    not inflate the skip-marker count (BUG-3054).
    """
    if isinstance(func, ast.Attribute):
        return (
            func.attr == "skip" and isinstance(func.value, ast.Name) and func.value.id == "pytest"
        )
    if isinstance(func, ast.Name):
        return func.id == "skip"
    return False


def _count_unconditional_skip_calls(node: ast.AST) -> int:
    """Count ``pytest.skip()`` calls that run unconditionally within *node*.

    BUG-3054: descends only through statements that always execute, so a skip
    nested under ``if``/``try``/loop/``with`` is NOT counted. That shape is a
    runtime environment guard ("the fixture file isn't in this checkout"), not
    a disabled test, and counting it read a strictly-additive test edit as
    tampering — vetoing an otherwise-complete ll-auto run. A bare
    ``pytest.skip()`` at the top of a test body still counts: that genuinely
    neuters the test.
    """
    total = 0
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _CONDITIONAL_NODES):
            continue
        if (
            isinstance(child, ast.Expr)
            and isinstance(child.value, ast.Call)
            and _is_pytest_skip(child.value.func)
        ):
            total += 1
        total += _count_unconditional_skip_calls(child)
    return total


def measure_test_strength(source: str, path: str) -> TestStrength | None:
    """Measure a Python test file's strength: assertion, test-function, and skip-marker counts.

    Counts ``ast.Assert`` nodes plus ``self.assert*``/``pytest.raises`` calls as
    assertions, ``FunctionDef``/``AsyncFunctionDef`` nodes named ``test*`` as test
    functions, and ``skip``/``skipif``/``xfail`` decorators or *unconditional*
    ``pytest.skip(...)`` calls as skip markers.

    BUG-3054: a ``pytest.skip(...)`` nested under ``if``/``try``/loop/``with``
    is a runtime environment guard, not a disabled test, and is not counted.
    Only a skip on an always-executed path counts, alongside the decorators.

    Returns None for a non-Python *path* or an unparseable *source* -- callers
    must treat that conservatively (finding kept, per ``is_weakening``).

    Known limitation: the metric is an aggregate count per file, so it cannot
    see a same-count substitution (gutting real assertions and backfilling
    ``assert True``, ENH-2964 row 5), and it reads a legitimate helper
    extraction that reduces a file's raw assertion count as a weakening
    (ENH-2964 row 1). A moved test function is netted out cross-file by
    ``filter_weakening_findings`` (ENH-2964), so it is no longer a false
    positive at that call site; this function's own per-file measurement is
    unchanged.
    """
    if not path.endswith(".py"):
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    assertions = 0
    test_functions = 0
    skip_markers = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            assertions += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                test_functions += 1
            for decorator in node.decorator_list:
                if _decorator_name(decorator) in ("skip", "skipif", "xfail"):
                    skip_markers += 1
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name.startswith("assert") or name == "raises":
                assertions += 1

    # BUG-3054: skip *calls* are counted separately from the walk above so the
    # count can be restricted to unconditionally-reached ones.
    skip_markers += _count_unconditional_skip_calls(tree)

    return TestStrength(
        assertions=assertions, test_functions=test_functions, skip_markers=skip_markers
    )


def _weakened(before: TestStrength, after: TestStrength) -> bool:
    """Scalar weakening comparison shared by ``is_weakening`` and the
    cross-file netting adjustment in ``filter_weakening_findings``."""
    return (
        after.assertions < before.assertions
        or after.test_functions < before.test_functions
        or after.skip_markers > before.skip_markers
    )


def is_weakening(before_src: str, after_src: str, path: str) -> bool:
    """True when *after_src* weakens *before_src* for the test file at *path*.

    Weakening is: fewer assertions, fewer test functions, more skip/xfail
    markers, or either side being unmeasurable (non-Python or unparseable --
    conservative fallback per ``measure_test_strength``'s contract).
    """
    before = measure_test_strength(before_src, path)
    after = measure_test_strength(after_src, path)
    if before is None or after is None:
        return True
    return _weakened(before, after)


def extract_test_functions(source: str) -> dict[str, ast.AST] | None:
    """Top-level ``test*`` function nodes by name; None when unparseable."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test")
    }


def _subtract(total: TestStrength, parts: list[TestStrength]) -> TestStrength:
    """Field-wise ``total - sum(parts)``, floored at 0."""
    return TestStrength(
        assertions=max(0, total.assertions - sum(p.assertions for p in parts)),
        test_functions=max(0, total.test_functions - sum(p.test_functions for p in parts)),
        skip_markers=max(0, total.skip_markers - sum(p.skip_markers for p in parts)),
    )


def filter_weakening_findings(
    findings: list[TamperFinding], repo_root: Path, ref: str
) -> list[TamperFinding]:
    """Keep only findings that represent an actual weakening of the test suite.

    Keeps every ``deleted`` finding and every ``is_config`` finding
    unconditionally (a deletion or a pytest-config edit is not measurable by
    source strength), keeps each ``modified`` finding whose ``is_weakening``
    is True, and drops ``added`` findings entirely -- a new test file cannot
    weaken the suite.

    A ``modified`` finding that reads as weakening is then re-checked against
    a cross-file-adjusted baseline (ENH-2964): if a test function present in
    its ``before`` text is *newly present* elsewhere in this same finding
    set -- another ``modified`` finding's ``after`` text, or any ``added``
    finding's text -- that relocated function's strength is subtracted from
    the ``before`` baseline before re-comparing. This nets out a test
    function moved to another file without laundering an unrelated deletion
    in the same file (ENH-2964 row 8) or a same-named-but-unrelated function
    already living elsewhere before this run (ENH-2964 row 9), since
    "relocated" only ever contains names newly present in *this run's*
    findings, never a pre-existing name match against an untouched file.
    """
    modified_paths = [f.path for f in findings if f.kind == "modified" and not f.is_config]
    before_texts = read_paths_at_ref(repo_root, ref, modified_paths)
    after_texts = {path: _read_text(repo_root / path) for path in modified_paths}

    added_paths = [f.path for f in findings if f.kind == "added" and not f.is_config]
    added_texts = {path: _read_text(repo_root / path) for path in added_paths}

    relocated: set[str] = set()
    for path in added_paths:
        names = extract_test_functions(added_texts[path])
        if names is not None:
            relocated.update(names)
    for path in modified_paths:
        before_src = before_texts.get(path)
        after_src = after_texts.get(path)
        if before_src is None or after_src is None:
            continue
        before_names = extract_test_functions(before_src)
        after_names = extract_test_functions(after_src)
        if before_names is None or after_names is None:
            continue
        relocated.update(set(after_names) - set(before_names))

    kept: list[TamperFinding] = []
    for finding in findings:
        if finding.is_config or finding.kind == "deleted":
            kept.append(finding)
            continue
        if finding.kind != "modified":
            continue  # "added" findings are dropped.

        before_src = before_texts.get(finding.path)
        after_src = after_texts.get(finding.path)
        if before_src is None or after_src is None:
            kept.append(finding)
            continue
        if not is_weakening(before_src, after_src, finding.path):
            continue

        before_strength = measure_test_strength(before_src, finding.path)
        before_names = extract_test_functions(before_src)
        after_strength = measure_test_strength(after_src, finding.path)
        if (
            before_strength is None
            or before_names is None
            or after_strength is None
            or not relocated
        ):
            kept.append(finding)
            continue

        relocated_parts = [
            part
            for name, node in before_names.items()
            if name in relocated
            for part in [measure_test_strength(ast.unparse(node), finding.path)]
            if part is not None
        ]
        if not relocated_parts:
            kept.append(finding)
            continue

        adjusted_before = _subtract(before_strength, relocated_parts)
        if _weakened(adjusted_before, after_strength):
            kept.append(finding)
    return kept


def _read_toml(path: Path) -> dict | None:
    try:
        return tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def _read_text_or_none(path: Path) -> str | None:
    try:
        return path.read_text()
    except OSError:
        return None


def resolved_pytest_config_targets(repo_root: Path) -> list[ConfigTarget]:
    """Return the pytest config target(s) pytest actually reads for this repo.

    Priority order: ``pytest.ini`` > ``pyproject.toml``
    ``[tool.pytest.ini_options]`` > ``tox.ini`` ``[pytest]`` >
    ``setup.cfg`` ``[tool:pytest]`` -- matching pytest's own discovery order.
    Only ``pyproject.toml`` -- a multi-purpose file -- gets a section
    selector; the rest are already pytest-scoped end to end.
    """
    if (repo_root / "pytest.ini").is_file():
        return [ConfigTarget(path="pytest.ini", section=None)]

    pyproject = repo_root / "pyproject.toml"
    if pyproject.is_file():
        data = _read_toml(pyproject)
        if data is not None and "ini_options" in data.get("tool", {}).get("pytest", {}):
            return [ConfigTarget(path="pyproject.toml", section=("tool", "pytest", "ini_options"))]

    tox_ini = repo_root / "tox.ini"
    if tox_ini.is_file() and "[pytest]" in _read_text(tox_ini):
        return [ConfigTarget(path="tox.ini", section=None)]

    setup_cfg = repo_root / "setup.cfg"
    if setup_cfg.is_file() and "[tool:pytest]" in _read_text(setup_cfg):
        return [ConfigTarget(path="setup.cfg", section=None)]

    return []


def resolved_pytest_config_paths(repo_root: Path) -> list[str]:
    """Thin compatibility wrapper over ``resolved_pytest_config_targets``.

    Returns just the paths, for callers that only need the candidate-path
    set (not the section-scoping metadata) -- e.g. building the union of
    test-file and config paths to snapshot.
    """
    return [target.path for target in resolved_pytest_config_targets(repo_root)]


def hash_config_target(source: str, target: ConfigTarget) -> str:
    """Hash the canonicalized selected section of *source*, or the whole source.

    When ``target.section`` is None, or the section cannot be extracted
    (unparseable TOML, or the section is absent), falls back to whole-source
    hashing -- fail-closed, so an unparseable config still produces a
    finding rather than silently passing.
    """
    if target.section is not None:
        try:
            data = tomllib.loads(source)
        except tomllib.TOMLDecodeError:
            data = None
        if data is not None:
            node: object = data
            for key in target.section:
                if not isinstance(node, dict) or key not in node:
                    node = None
                    break
                node = node[key]
            if node is not None:
                try:
                    blob = json.dumps(node, sort_keys=True, default=str)
                except TypeError:
                    blob = repr(node)
                return _sha256_bytes(blob.encode("utf-8"))
    return _sha256_bytes(source.encode("utf-8"))


def _git(repo_root: Path, *args: str) -> str | None:
    """Return stripped stdout of a git command run in *repo_root*, or None."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def apply_tamper_policy(
    policy: TamperPolicy, findings: list[TamperFinding], repo_root: Path
) -> TamperReport:
    """Act on *findings* per *policy*, always returning the full findings list.

    - ``allow``: no mutation; passes regardless of findings.
    - ``fail``: no mutation; passes only when there are no findings.
    - ``revert``: restores modified/deleted tracked files to their
      pre-existing (git) state via ``git checkout --``. Untracked
      modified/deleted files have no backing git state to restore from and
      are left as unresolved findings. Never touches ``added`` findings --
      that is ENH-2853's pre-patch check's job, not this guard's.
    """
    if not findings:
        return TamperReport(policy=policy, findings=[], reverted=[], passed=True)

    if policy == "allow":
        return TamperReport(policy=policy, findings=findings, reverted=[], passed=True)

    if policy == "fail":
        return TamperReport(policy=policy, findings=findings, reverted=[], passed=False)

    # revert
    revertable = [f for f in findings if f.kind in ("modified", "deleted")]
    reverted: list[str] = []
    if revertable:
        paths = [f.path for f in revertable]
        status_out = _git(repo_root, "status", "--porcelain", "--", *paths) or ""
        untracked: set[str] = set()
        for line in status_out.splitlines():
            if not line or len(line) < 3:
                continue
            code = line[:2]
            file_path = line[3:].split(" -> ")[-1].strip()
            if code.startswith("?"):
                untracked.add(file_path)
        tracked_to_restore = [p for p in paths if p not in untracked]
        if tracked_to_restore:
            checkout_out = _git(repo_root, "checkout", "--", *tracked_to_restore)
            if checkout_out is not None:
                reverted.extend(tracked_to_restore)
    passed = len(reverted) == len(revertable)
    return TamperReport(policy=policy, findings=findings, reverted=reverted, passed=passed)


def run_tamper_guard(
    before: TamperSnapshot,
    changed_files: list[str],
    config: BRConfig,
    policy: TamperPolicy,
    repo_root: Path,
    finding_filter: FindingFilter | None = None,
) -> TamperReport:
    """Compare a pre-step *before* snapshot against current on-disk state and
    act per *policy*.

    The caller (an adapter owning verification-step timing) captures
    *before* itself via ``snapshot_test_paths`` immediately prior to running
    the step, over the union of ``filter_test_files(...)`` and
    ``resolved_pytest_config_paths(repo_root)``. *changed_files* is the set
    of files touched by the step (e.g. from a post-step ``git diff``); it
    covers paths -- like a newly added test file -- that could not have been
    in *before*'s path set.

    *finding_filter*, when given, runs after ``compare_snapshots`` and the
    ``is_config`` tagging but before ``apply_tamper_policy`` -- e.g. narrowing
    byte-level findings down to ones that represent an actual weakening of the
    test suite (BUG-2954). Defaults to None so callers that never pass it
    (the FSM adapter) keep full byte-level strictness, unaffected.
    """
    config_paths = resolved_pytest_config_paths(repo_root)
    after_paths = sorted(
        set(before) | set(filter_test_files(changed_files, config=config)) | set(config_paths)
    )
    after = snapshot_test_paths(after_paths, repo_root)
    findings = compare_snapshots(before, after)
    config_path_set = set(config_paths)
    for finding in findings:
        finding.is_config = finding.path in config_path_set
    if finding_filter is not None:
        findings = finding_filter(findings)
    return apply_tamper_policy(policy, findings, repo_root)
