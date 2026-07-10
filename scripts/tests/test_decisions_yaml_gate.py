"""Pytest CI belt for ``ll-verify-decisions`` on ``.ll/decisions.yaml`` (ENH-2591).

The ENH-2589 validator CLI is enforced on commits by the pre-commit hook
(ENH-2590). This module is the complementary **pytest belt**: it wraps the same
validator as a subprocess-asserting gate so ``python -m pytest scripts/tests/``
(our project CI per ``.claude/CLAUDE.md``) catches ``.ll/decisions.yaml``
corruption on every test run — closing the ``git commit --no-verify`` and
non-hook edit paths.

The gate mirrors the canonical shape established by
``scripts/tests/test_policy_builder_node_gate.py`` (FEAT-2390) and the sibling
pre-commit gate at ``scripts/tests/test_decisions_yaml_pre_commit_gate.py``
(ENH-2590). It runs two cases:

1. **Positive**: ``ll-verify-decisions`` exits 0 against the live
   ``.ll/decisions.yaml`` (no corruption present).
2. **Negative** (OTHE-203): ``ll-verify-decisions`` exits non-zero with a
   ``decisions.yaml`` reference in stderr when the unterminated-quote payload
   ``rationale: "abc "" def"`` is substituted in via ``tmp_path``.

The gate skips (rather than fails) when ``ll-verify-decisions`` is absent from
``PATH`` — contributors without the editable install are not hard-blocked; the
gate is fully enforced wherever the CLI is available. The validator's own
correctness (exit-code contract, error-message format) is independently gated
by ``scripts/tests/test_verify_decisions.py`` and ``scripts/tests/test_decisions.py``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CLI = "ll-verify-decisions"
REPO_ROOT = Path(__file__).resolve().parents[2]

# OTHE-203 payload — reproduces ``yaml.parser.ParserError`` from the
# unterminated-quote fixture ``rationale: "abc "" def"``. Defined locally rather
# than imported from ``test_decisions_yaml_pre_commit_gate.py`` per the
# codebase convention (see ``test_decisions.py:127-132`` and
# ``test_verify_decisions.py:49-58``): inline the payload, don't share fixtures
# across test files.
OTHE_203_PAYLOAD = 'entries:\n  - id: OTHE-203\n    type: decision\n    rationale: "abc "" def"\n'


@pytest.fixture(scope="module")
def validator() -> str:
    """Return the ``ll-verify-decisions`` binary path, skipping when missing.

    Mirrors the canonical skip-when-missing idiom from
    ``test_policy_builder_node_gate.py:52-57`` and
    ``test_decisions_yaml_pre_commit_gate.py:155-163``. Marked
    ``scope="module"`` so the ``shutil.which`` lookup runs once per file
    rather than per test.
    """
    path = shutil.which(CLI)
    if path is None:
        pytest.skip(f"{CLI} not installed; install via `pip install -e ./scripts[dev]`")
    return path


def test_decisions_yaml_loads(validator: str) -> None:
    """``ll-verify-decisions`` exits 0 against the live ``.ll/decisions.yaml``.

    Runs the validator with no ``--config-root`` so it resolves the log path
    from ``cwd`` (defaults to ``Path.cwd() / .ll/decisions.yaml``); the test
    invokes it with ``cwd=REPO_ROOT`` so the live log path is targeted.
    ``timeout=60`` mirrors the sibling pre-commit gate at
    ``test_decisions_yaml_pre_commit_gate.py:180``.
    """
    result = subprocess.run(
        [validator],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"{CLI} failed against live .ll/decisions.yaml (exit {result.returncode}): "
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_decisions_yaml_rejects_othe_203(validator: str, tmp_path: Path) -> None:
    """``ll-verify-decisions`` exits non-zero with a ``decisions.yaml`` reference on OTHE-203.

    Writes the unterminated-quote payload under ``tmp_path/.ll/decisions.yaml``
    and runs the validator with ``--config-root tmp_path``. The validator's
    exit-code contract (per ``scripts/little_loops/cli/verify_decisions.py:65-108``)
    is ``1`` on any caught ``yaml.YAMLError``/``KeyError``/``ValueError``, with
    a single-line ``ERROR: {log_path}: {ExcClass}: {exc}`` written to **stderr**.
    """
    decisions_dir = tmp_path / ".ll"
    decisions_dir.mkdir()
    (decisions_dir / "decisions.yaml").write_text(OTHE_203_PAYLOAD, encoding="utf-8")

    result = subprocess.run(
        [validator, "--config-root", str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0, (
        f"{CLI} should fail on OTHE-203 YAML corruption, but exit was 0. "
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "decisions.yaml" in result.stderr.lower(), (
        f"{CLI} stderr should reference the decisions.yaml path on failure; got:\n{result.stderr}"
    )
