"""Pre-commit gate for ``ll-verify-decisions`` on ``.ll/decisions.yaml`` (ENH-2590).

The ENH-2589 validator CLI is wired into the repo-local pre-commit hook from
``.pre-commit-config.yaml``. This module gates the *plumbing*:

1. The hook entry exists in ``.pre-commit-config.yaml`` with the expected shape
   (``id: ll-verify-decisions``, ``language: system``, ``pass_filenames: false``).
2. ``pre-commit run --files .ll/decisions.yaml`` exits non-zero on OTHE-203
   corruption (load-time ``yaml.YAMLError``).
3. ``pre-commit run --files .ll/decisions.yaml`` exits 0 on a clean file.

The validator's *correctness* (per-corruption exit code mapping,
stderr message format, etc.) is independently gated by
``scripts/tests/test_verify_decisions.py`` and ``scripts/tests/test_decisions.py``.

This test skips (rather than fails) when ``pre-commit`` or
``ll-verify-decisions`` are absent from ``PATH`` — the project's CI is
``python -m pytest scripts/tests/`` and contributors without the toolchain
are not hard-blocked (mirrors the FEAT-2390 ``test_node_conformance_suite_passes``
template at ``scripts/tests/test_policy_builder_node_gate.py:45-71``).

The sibling file name ``test_decisions_yaml_gate.py`` is owned by ENH-2591
(the pytest CI belt); this file name preserves both transport-layer hooks
independently while keeping the established ``test_<feature>_gate.py`` family
convention.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

OTHE_203_PAYLOAD = 'entries:\n  - id: OTHE-203\n    type: decision\n    rationale: "abc "" def"\n'

CLEAN_PAYLOAD = "entries:\n  - id: R-001\n    type: rule\n    rule: Use atomic writes\n"


def _init_git_repo(path: Path) -> None:
    """Initialize a git repo at *path* with a test user identity.

    Mirrors ``scripts/tests/test_hooks_integration.py:2994-3007`` shape.
    """
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    (
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(path),
            check=True,
            capture_output=True,
        ),
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )


def _pre_commit_available() -> str | None:
    """Return the ``pre-commit`` binary path, or ``None`` if missing."""
    return shutil.which("pre-commit")


def _validator_available() -> str | None:
    """Return the ``ll-verify-decisions`` binary path, or ``None`` if missing."""
    return shutil.which("ll-verify-decisions")


def _write_config(repo: Path) -> None:
    """Write a minimal ``.pre-commit-config.yaml`` into *repo*.

    Includes the new ``ll-verify-decisions`` ``repo: local`` block — the actual
    hook shape gated by ``test_pre_commit_config_has_ll_verify_decisions_hook``.
    """
    (repo / ".pre-commit-config.yaml").write_text(
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: ll-verify-decisions\n"
        "        name: Validate .ll/decisions.yaml\n"
        "        language: system\n"
        "        entry: ll-verify-decisions\n"
        "        files: ^\\.ll/decisions\\.yaml$\n"
        "        pass_filenames: false\n",
        encoding="utf-8",
    )


def _write_decisions(repo: Path, body: str) -> Path:
    """Write ``.ll/decisions.yaml`` to *repo* and return its path."""
    ll = repo / ".ll"
    ll.mkdir(parents=True, exist_ok=True)
    decisions_path = ll / "decisions.yaml"
    decisions_path.write_text(body, encoding="utf-8")
    return decisions_path


# ---------------------------------------------------------------------------
# Structural gate: hook shape in repo .pre-commit-config.yaml
# ---------------------------------------------------------------------------


def test_pre_commit_config_has_ll_verify_decisions_hook() -> None:
    """The repo-root ``.pre-commit-config.yaml`` declares the new hook.

    Catches drift if anyone removes the hook block — protects the ENH-2590
    acceptance criterion that the hook is wired at the canonical position.
    Does not depend on ``pre-commit`` or ``ll-verify-decisions`` being
    installed, so it runs unconditionally.
    """
    config_path = Path(__file__).resolve().parents[2] / ".pre-commit-config.yaml"
    assert config_path.exists(), f"missing pre-commit config at {config_path}"
    text = config_path.read_text(encoding="utf-8")
    assert "repo: local" in text, ".pre-commit-config.yaml must contain a repo: local block"
    assert "id: ll-verify-decisions" in text, (
        ".pre-commit-config.yaml must declare the ll-verify-decisions hook id"
    )
    assert "entry: ll-verify-decisions" in text, (
        ".pre-commit-config.yaml hook must invoke ll-verify-decisions"
    )
    assert "language: system" in text, ".pre-commit-config.yaml hook must use language: system"
    assert "pass_filenames: false" in text, (
        ".pre-commit-config.yaml hook must set pass_filenames: false "
        "(main_verify_decisions resolves the path itself via --config-root)"
    )


# ---------------------------------------------------------------------------
# End-to-end subprocess gates: pre-commit run against fixtures
# ---------------------------------------------------------------------------


def test_pre_commit_blocks_othe_203_corruption(tmp_path: Path) -> None:
    """`pre-commit run --files .ll/decisions.yaml` must exit non-zero on YAML corruption.

    OTHE-203 reproduces ``yaml.parser.ParserError`` from the
    unterminated-quote fixture ``rationale: "abc "" def"``. The wired
    validator catches the ``yaml.YAMLError`` and exits 1, which ``pre-commit``
    propagates as a hook failure.
    """
    pre_commit = _pre_commit_available()
    if pre_commit is None:
        pytest.skip("pre-commit not installed; pre-commit gate runs wherever it is available")
    if _validator_available() is None:
        pytest.skip('ll-verify-decisions not installed; run pip install -e "./scripts[dev]"')

    _init_git_repo(tmp_path)
    _write_config(tmp_path)
    decisions_path = _write_decisions(tmp_path, OTHE_203_PAYLOAD)
    subprocess.run(
        ["git", "add", str(decisions_path)],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )

    proc = subprocess.run(
        [pre_commit, "run", "--files", ".ll/decisions.yaml"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0, (
        "pre-commit hook should fail on OTHE-203 YAML corruption, but exit was 0. "
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


def test_pre_commit_passes_clean_file(tmp_path: Path) -> None:
    """`pre-commit run --files .ll/decisions.yaml` must exit 0 on a valid file.

    Control case for the OTHE-203 corruption gate above — proves the hook is
    not unconditionally failing.
    """
    pre_commit = _pre_commit_available()
    if pre_commit is None:
        pytest.skip("pre-commit not installed; pre-commit gate runs wherever it is available")
    if _validator_available() is None:
        pytest.skip('ll-verify-decisions not installed; run pip install -e "./scripts[dev]"')

    _init_git_repo(tmp_path)
    _write_config(tmp_path)
    decisions_path = _write_decisions(tmp_path, CLEAN_PAYLOAD)
    subprocess.run(
        ["git", "add", str(decisions_path)],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )

    proc = subprocess.run(
        [pre_commit, "run", "--files", ".ll/decisions.yaml"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, (
        "pre-commit hook should pass on a clean decisions.yaml, but exit "
        f"was {proc.returncode}. stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
