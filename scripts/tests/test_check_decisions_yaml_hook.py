"""Hook-shape tests for the Claude Code PreToolUse belt on ``.ll/decisions.yaml`` (ENH-2592).

The Claude-side host hook (``hooks/scripts/check-decisions-yaml.sh``) is the
innermost belt to the ENH-2589 validator, complementing the pre-commit hook
(ENH-2590) and the pytest CI gate (ENH-2591). It must:

1. Be registered in ``hooks/hooks.json`` under ``PreToolUse`` with
   ``matcher: "Write|Edit"`` and ``timeout: 5``.
2. Block (exit 2 per the Claude Code PreToolUse contract — see
   ``hooks/adapters/claude-code/pre-tool-use.sh:7-13``) when a Write or Edit
   would land a corrupt ``.ll/decisions.yaml`` candidate. The validator's
   ``yaml.YAMLError``/``KeyError``/``ValueError`` classes (per
   ``scripts/little_loops/cli/verify_decisions.py:60-61``) should all flow
   through to a host-level block.
3. Stage ``tool_input.content`` (Write) or reconstruct the post-Edit result
   (Edit) in a temporary config root before invoking ``ll-verify-decisions``,
   so the validator sees the **candidate** content rather than the current
   on-disk file. Otherwise a Write that's about to corrupt the file would
   pass against the still-valid existing file and slip past the hook.
4. Skip cleanly with exit 0 when ``ll-verify-decisions`` is missing — matches
   the sibling ``check-duplicate-issue-id.sh`` graceful-degrade pattern.
5. Exit 0 quickly when the tool is not Write/Edit or the path is not
   ``.ll/decisions.yaml`` (early-allow shape used by the sibling).

Test mirrors the layout of ``test_decisions_yaml_gate.py:48-112`` (positive +
OTHE-203 against ``--config-root``) and
``test_decisions_yaml_pre_commit_gate.py:147-225`` (full hook subprocess), and
of ``test_hooks_integration.py:1457-1647`` for the stdin JSON pattern and
``test_hooks_integration.py:2703-2714`` for the ``hooks.json`` structural
assertion.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_SCRIPT = REPO_ROOT / "hooks/scripts/check-decisions-yaml.sh"
HOOKS_JSON = REPO_ROOT / "hooks/hooks.json"
CLI = "ll-verify-decisions"

# OTHE-203 — unterminated-quote payload (mirrors test_decisions_yaml_gate.py:45).
# Inline per the codebase convention documented at
# test_decisions.py:127-132 and test_verify_decisions.py:49-58.
OTHE_203_PAYLOAD = (
    "entries:\n"
    "  - id: OTHE-203\n"
    "    type: decision\n"
    '    rationale: "abc "" def"\n'
)

CLEAN_PAYLOAD = (
    "entries:\n"
    "  - id: R-001\n"
    "    type: rule\n"
    "    rule: Use atomic writes\n"
)

INVOKE_TIMEOUT = 10


@pytest.fixture(scope="module")
def validator() -> str | None:
    """Return ``ll-verify-decisions`` path, or ``None`` if missing.

    Skips subprocess tests that depend on the validator when absent. Mirrors
    the ``scope="module"`` skip-when-missing shape at
    ``test_decisions_yaml_gate.py:48-61``.
    """
    return shutil.which(CLI)


def _stage_clean_decisions(tmp_path: Path) -> Path:
    """Write a valid ``.ll/decisions.yaml`` under *tmp_path* and return its path.

    Helper used by the Write tests so the on-disk file exists for Edit
    reconstruction baseline; without this, Edit reconstruction has nothing
    to substitute into.
    """
    ll = tmp_path / ".ll"
    ll.mkdir(parents=True, exist_ok=True)
    decisions_path = ll / "decisions.yaml"
    decisions_path.write_text(CLEAN_PAYLOAD, encoding="utf-8")
    return decisions_path


def _invoke_hook(
    payload: dict[str, object],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the hook with a JSON-encoded *payload* on stdin.

    Mirrors the stdin-JSON invocation pattern at
    ``test_hooks_integration.py:1488-1495``. The hook ignores *env*'s
    ``PATH`` when verifying whether ``ll-verify-decisions`` is installed —
    when *env* is provided, callers use it to remove the validator from the
    subprocess's lookup path (graceful-degrade case).
    """
    return subprocess.run(
        [str(HOOK_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=INVOKE_TIMEOUT,
        env=env,
        cwd=str(cwd),
    )


# ---------------------------------------------------------------------------
# Structural gate: hooks.json registration (always runs, no dependency)
# ---------------------------------------------------------------------------


def test_hooks_json_registers_check_decisions_yaml_hook() -> None:
    """``hooks.json`` registers ``check-decisions-yaml.sh`` under PreToolUse ``Write|Edit``.

    Mirrors the unconditional structural gate at
    ``test_hooks_integration.py:2703-2714`` for ``scratch-cleanup.sh``. Catches
    drift if the entry is removed or the timeout is widened beyond the
    5-second host cap.
    """
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    pre_tool_use = data["hooks"].get("PreToolUse", [])
    matches: list[dict[str, object]] = []
    for group in pre_tool_use:
        if group.get("matcher") != "Write|Edit":
            continue
        for hook in group.get("hooks", []):
            command = hook.get("command", "")
            if "check-decisions-yaml.sh" in command:
                matches.append(hook)
    assert matches, (
        "hooks.json is missing a PreToolUse Write|Edit entry for "
        "check-decisions-yaml.sh; see integration map ENH-2592 step 4"
    )
    assert any(hook.get("timeout") == 5 for hook in matches), (
        "check-decisions-yaml hook timeout must be 5 (host-enforced); "
        f"got {[hook.get('timeout') for hook in matches]!r}"
    )


# ---------------------------------------------------------------------------
# Subprocess gates: positive + OTHE-203 (require the validator)
# ---------------------------------------------------------------------------


def test_hook_blocks_othe_203_write(
    tmp_path: Path, validator: str | None
) -> None:
    """Write with OTHE-203 corruption must block (exit 2) and reference decisions.yaml.

    The Claude Code PreToolUse contract (``hooks/adapters/claude-code/pre-tool-use.sh:7-13``)
    reserves ``exit 2`` for host-level block decisions, which the host
    translates into user-facing feedback. We assert on stderr to confirm the
    validator's single-line ``ERROR:`` bubbled through. The on-disk file
    must still be the original clean content — the hook runs **before**
    Claude's Write lands, so the file is unchanged regardless of the verdict.
    """
    if validator is None:
        pytest.skip(f"{CLI} not installed; run `pip install -e ./scripts[dev]`")

    target = _stage_clean_decisions(tmp_path)
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(target),
            "content": OTHE_203_PAYLOAD,
        },
    }
    result = _invoke_hook(payload, cwd=tmp_path)

    assert result.returncode == 2, (
        f"Hook should block OTHE-203 Write with exit 2, got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "decisions.yaml" in result.stderr.lower(), (
        f"Hook stderr should reference decisions.yaml on block; "
        f"got {result.stderr!r}"
    )
    # Sanity-check: PreToolUse runs before mutation — on-disk file unchanged
    assert target.read_text(encoding="utf-8") == CLEAN_PAYLOAD, (
        "Hook must validate candidate content before Claude's Write; "
        "the on-disk file must remain the original CLEAN_PAYLOAD."
    )


def test_hook_allows_valid_write(tmp_path: Path, validator: str | None) -> None:
    """Write with valid content must allow (exit 0).

    Control case for ``test_hook_blocks_othe_203_write`` — proves the hook is
    not unconditionally blocking. The validator's exit 0 against the staged
    candidate must flow through to a host-level allow.
    """
    if validator is None:
        pytest.skip(f"{CLI} not installed; run `pip install -e ./scripts[dev]`")

    target = _stage_clean_decisions(tmp_path)
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(target),
            "content": CLEAN_PAYLOAD,
        },
    }
    result = _invoke_hook(payload, cwd=tmp_path)

    assert result.returncode == 0, (
        f"Hook should allow valid Write with exit 0, got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_hook_blocks_othe_203_edit(
    tmp_path: Path, validator: str | None
) -> None:
    """Edit whose reconstructed result is OTHE-203 corrupt must block (exit 2).

    The hook must reconstruct the post-Edit candidate by applying
    ``old_string`` → ``new_string`` (respecting ``replace_all`` when present)
    on the current on-disk file, then validate the reconstruction. Without
    this, an Edit that replaces valid body content with a corrupted payload
    would slip past the hook (the on-disk file is still valid until Claude
    writes).
    """
    if validator is None:
        pytest.skip(f"{CLI} not installed; run `pip install -e ./scripts[dev]`")

    target = _stage_clean_decisions(tmp_path)
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(target),
            "old_string": CLEAN_PAYLOAD,
            "new_string": OTHE_203_PAYLOAD,
            "replace_all": False,
        },
    }
    result = _invoke_hook(payload, cwd=tmp_path)

    assert result.returncode == 2, (
        f"Hook should block Edit that introduces OTHE-203 corruption with exit 2, "
        f"got {result.returncode}. stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "decisions.yaml" in result.stderr.lower()
    assert target.read_text(encoding="utf-8") == CLEAN_PAYLOAD, (
        "On-disk file must remain unchanged before Claude's Edit lands"
    )


# ---------------------------------------------------------------------------
# Path / tool-shape gates (do NOT need the validator)
# ---------------------------------------------------------------------------


def test_hook_allows_non_target_path(tmp_path: Path) -> None:
    """Non-``.ll/decisions.yaml`` paths exit 0 quickly without invoking the validator.

    Mirrors the early-exit-for-irrelevant-tools shape at
    ``check-duplicate-issue-id.sh:34-56``. Uses a sibling
    ``.ll/learning-tests/example.md`` path that the discovery-gate can
    legitimately target but this hook must skip.
    """
    (tmp_path / ".ll").mkdir(parents=True, exist_ok=True)
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(tmp_path / ".ll/learning-tests/example.md"),
            "content": "anything goes here\n",
        },
    }
    result = _invoke_hook(payload, cwd=tmp_path)

    assert result.returncode == 0, (
        f"Hook should allow non-target paths with exit 0, got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_hook_allows_non_write_edit_tools(tmp_path: Path) -> None:
    """Tools other than Write/Edit exit 0 without invoking the validator."""
    (tmp_path / ".ll").mkdir(parents=True, exist_ok=True)
    target = tmp_path / ".ll/decisions.yaml"
    target.write_text(CLEAN_PAYLOAD, encoding="utf-8")
    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": str(target)},
    }
    result = _invoke_hook(payload, cwd=tmp_path)

    assert result.returncode == 0, (
        f"Hook should allow non-Write/Edit tools with exit 0, got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def _dir_contains_executable(directory: Path, name: str) -> bool:
    """Return True iff *directory* contains an executable named *name*.

    Manual scan of a single directory — used to build a *controlled* PATH
    for the skip-tests. ``shutil.which(name, path=...)`` falls back to
    ``os.defpath`` (``:/bin:/usr/bin``) on POSIX, which leaks executables
    into the lookup even when the controlled PATH omits them. Walking the
    directory ourselves avoids that leakage.
    """
    candidate = directory / name
    try:
        return candidate.is_file() and os.access(candidate, os.X_OK)
    except OSError:
        return False


def _make_isolated_bin(tmp_path: Path, *, with_python: bool) -> Path:
    """Create a temp ``bin/`` dir with symlinks to bash, cat, mktemp, rm, and python3.

    The hook script uses these external commands (``cat`` for stdin read,
    ``python3`` for JSON parsing, ``mktemp`` for the staging dir, and
    ``rm`` for the EXIT trap). No other executables are present, so the
    controlled PATH for the skip-tests is unambiguous. Resolutions use
    ``shutil.which`` which traverses ``os.defpath`` (``/bin:/usr/bin``)
    so this works across Linux and macOS where the four utilities may
    live in different directories.
    """
    needed: dict[str, str] = {}
    for name in ("bash", "cat", "mktemp", "rm"):
        resolved = shutil.which(name)
        if not resolved:
            raise RuntimeError(f"{name} not on test PATH; can't construct isolated env")
        needed[name] = resolved
    if with_python:
        py_src = shutil.which("python3")
        if py_src:
            needed["python3"] = py_src

    bin_dir = tmp_path / "isolated_bin"
    bin_dir.mkdir()
    for name, src in needed.items():
        os.symlink(src, str(bin_dir / name))
    return bin_dir


def test_hook_skips_when_validator_missing(tmp_path: Path) -> None:
    """When ``ll-verify-decisions`` is invisible to the subprocess, hook exits 0.

    Mirrors the graceful-degrade pattern from the sibling
    ``check-duplicate-issue-id.sh`` (the host-side belt to the validator is
    optional when the validator itself is absent). The hook must surface a
    brief skip message on stderr rather than spamming failure or blocking
    the tool call.

    Strategy: invoke the hook with an isolated ``bin`` directory containing
    only ``bash``, ``cat``, and ``python3``. ``ll-verify-decisions`` lives
    only inside Python's ``site-packages/.../bin`` (a directory excluded
    from the controlled PATH), so ``command -v ll-verify-decisions``
    genuinely returns no result and the hook's skip path fires.
    """
    if not shutil.which("python3"):
        pytest.skip("python3 missing in test environment")

    bin_dir = _make_isolated_bin(tmp_path, with_python=True)
    # Sanity: ensure the isolated bin has no validator binary
    assert not (bin_dir / CLI).exists(), (
        f"Isolated bin unexpectedly contains {CLI!r}"
    )

    _stage_clean_decisions(tmp_path)
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(tmp_path / ".ll/decisions.yaml"),
            # OTHE-203 would block if the validator were visible
            "content": OTHE_203_PAYLOAD,
        },
    }
    env = {"PATH": str(bin_dir), "HOME": str(tmp_path)}

    result = _invoke_hook(payload, cwd=tmp_path, env=env)

    assert result.returncode == 0, (
        f"Hook should exit 0 when validator missing, got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    # The validator-missing path emits a "[little-loops] check-decisions-
    # yaml: ... not on PATH; skipping ..." line on stderr.
    assert "skip" in result.stderr.lower(), (
        f"Skip path should print a brief skip message; stderr={result.stderr!r}"
    )


def test_hook_skips_when_python3_missing(tmp_path: Path) -> None:
    """When ``python3`` is unavailable, hook gracefully exits 0.

    Defensive companion to ``test_hook_skips_when_validator_missing`` —
    covers a contributor who lacks the Python interpreter entirely. The
    hook must not block the tool call; the pre-commit and pytest belts
    (ENH-2590/ENH-2591) still enforce integrity.

    Uses an isolated ``bin`` directory with only ``bash`` and ``cat`` (no
    ``python3``) so the hook's ``python3 not on PATH`` graceful-skip path
    fires.
    """
    bin_dir = _make_isolated_bin(tmp_path, with_python=False)
    assert not (bin_dir / "python3").exists()

    _stage_clean_decisions(tmp_path)
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(tmp_path / ".ll/decisions.yaml"),
            "content": CLEAN_PAYLOAD,
        },
    }
    env = {"PATH": str(bin_dir), "HOME": str(tmp_path)}

    result = _invoke_hook(payload, cwd=tmp_path, env=env)

    assert result.returncode == 0, (
        f"Hook should exit 0 when python3 missing, got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
