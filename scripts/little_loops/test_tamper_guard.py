"""Tamper guard core: snapshot/compare/revert over test files (ENH-2933).

Detects whether test files (or the pytest config files that gate which
tests run) were modified/deleted/added across a verification step, and acts
on any finding per a configured policy (``revert`` | ``fail`` | ``allow``).
Deterministic only -- no LLM calls, no FSM or CLI-orchestrator knowledge.
Adapters (ENH-2934, ENH-2935) own step timing and call into this module;
this module never calls into either adapter.
"""

from __future__ import annotations

import hashlib
import subprocess
import tomllib
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


def _sha256_file(path: Path) -> str | None:
    """Return the sha256 hex digest of *path*'s on-disk bytes, or None if unreadable."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def snapshot_test_paths(paths: list[str], repo_root: Path) -> TamperSnapshot:
    """Hash the on-disk content of *paths* (relative to *repo_root*).

    A path missing or unreadable at snapshot time maps to None.
    """
    return {path: _sha256_file(repo_root / path) for path in paths}


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


def resolved_pytest_config_paths(repo_root: Path) -> list[str]:
    """Return the pytest config file(s) pytest actually reads for this repo.

    Priority order: ``pytest.ini`` > ``pyproject.toml``
    ``[tool.pytest.ini_options]`` > ``tox.ini`` ``[pytest]`` >
    ``setup.cfg`` ``[tool:pytest]`` -- matching pytest's own discovery order.
    """
    if (repo_root / "pytest.ini").is_file():
        return ["pytest.ini"]

    pyproject = repo_root / "pyproject.toml"
    if pyproject.is_file():
        data = _read_toml(pyproject)
        if data is not None and "ini_options" in data.get("tool", {}).get("pytest", {}):
            return ["pyproject.toml"]

    tox_ini = repo_root / "tox.ini"
    if tox_ini.is_file() and "[pytest]" in _read_text(tox_ini):
        return ["tox.ini"]

    setup_cfg = repo_root / "setup.cfg"
    if setup_cfg.is_file() and "[tool:pytest]" in _read_text(setup_cfg):
        return ["setup.cfg"]

    return []


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
    return apply_tamper_policy(policy, findings, repo_root)
