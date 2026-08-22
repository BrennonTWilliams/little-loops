"""BUG-3269 §4: mirror-drift gate for project-command resolution in loop YAMLs.

Delegating to ``ll-config get`` alone does not stop a fourteenth inline copy
from landing — nothing forces a new loop to use it. Two static assertions,
parametrized (registry pattern per `test_wiring_skills_and_commands.py`):

1. No loop YAML contains an inline ``.ll/ll-config.json`` read (the
   ``.get('<key>'`` / ``["<key>"]`` access-pattern shape) for any of the six
   ``ProjectConfig`` command keys, outside the exemption list below.
2. Every ``${context.test_cmd}`` / ``${context.lint_cmd}`` reference in any
   loop YAML resolves against that loop's own declared ``context:`` block —
   the "single highest-risk axis" from BUG-3269 §2: pasting a context-first
   shape into a loop that never declared the key raises `InterpolationError`
   at runtime. Scoped to these two keys rather than every ``${context.*}``
   reference: the FSM executor injects engine-level keys (``run_dir``,
   ``input``, ``input_hash``, ``project_root``, ...) into every run's
   context regardless of the loop's declared ``context:`` block
   (`fsm/executor.py`), so a blanket "every reference must be declared"
   check false-positives on those. ``test_cmd``/``lint_cmd`` carry no such
   engine default — they are exactly the axis BUG-3269 §2 identifies as
   under-covered.

Assertion 1 is scoped to exactly three permanent exemptions (ENH-3288 closed
out the conversion pass — `_PENDING_CONVERSION` no longer exists):
`oracles/code-run-gate.yaml` (BUG-3269 §1d — a different resolution
convention entirely: alias pairs, project-root-relative, never-guess, not
convertible), and `rn-refine.yaml` / `auto-refine-and-implement.yaml`
(ENH-3277 Option A — their absent-key contract means "skip", which
`ll-config get` collapses into the defaulted case and cannot express) — see
the inline comments on `_PERMANENT_EXEMPTIONS` below.

Assertion 2 has no exemptions — it should be green on the tree as it stands
and stay green.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"

# config/core.py:188-195 ProjectConfig fields.
PROJECT_COMMAND_KEYS = ("test_cmd", "lint_cmd", "type_cmd", "format_cmd", "build_cmd", "run_cmd")

# Permanent exemptions (ENH-3288 step 5/6 — the conversion pass is done):
# every one of these has an absent ≡ null ≡ skip, never guess contract that
# `ll-config get` cannot express — it collapses absent and defaulted into one
# output. `oracles/code-run-gate.yaml` (BUG-3269 §1d): a different resolution
# convention entirely (alias pairs, project-root-relative). `rn-refine.yaml`
# / `auto-refine-and-implement.yaml` (ENH-3277 Option A): an absent key today
# means *skip*, and converting either would start running `pytest` / `ruff
# check .` in unconfigured projects instead of skipping. All three keep their
# inline parse and their `.ll/ll.local.md` bypass indefinitely.
_PERMANENT_EXEMPTIONS = {
    "oracles/code-run-gate.yaml",
    "rn-refine.yaml",
    "auto-refine-and-implement.yaml",
}

_EXEMPT = _PERMANENT_EXEMPTIONS

# Matches `cfg.get('project', {}).get('test_cmd', ...)` / `cfg['project']['test_cmd']`
# style chained access into the `project` section of a raw-parsed
# .ll/ll-config.json — the exact shape of every inline read this issue
# eliminates. Scoped to a `project` access immediately before the command
# key (not a bare `.get('test_cmd'` anywhere in the file) so an unrelated
# dict that merely happens to have a same-named key in a different section
# (e.g. a `service.run_cmd` in a deploy-config block) isn't a false positive.
# ENH-3288 step 7: also matches the two-step bind-then-access shape
# (`project = cfg.get('project', {})` ... `project.get('test_cmd')`, the
# exact shape at auto-refine-and-implement.yaml:432-434) via a backreference
# to the bound variable name, so a loop cloning that permanently-exempt file
# as a copyable precedent doesn't land an undetected inline read.
_INLINE_ACCESS_RE = {
    key: re.compile(
        r"""get\(\s*['"]project['"][^)]*\)\s*\.get\(\s*['"]"""
        + re.escape(key)
        + r"""['"]"""
        + r"""|\[\s*['"]project['"]\s*\]\s*\[\s*['"]"""
        + re.escape(key)
        + r"""['"]\s*\]"""
        + r"""|(?P<var>\w+)\s*=\s*[\w.]*\.get\(\s*['"]project['"][^)]*\)[\s\S]*?(?P=var)\.get\(\s*['"]"""
        + re.escape(key)
        + r"""['"]"""
    )
    for key in PROJECT_COMMAND_KEYS
}

# ${context.test_cmd} / ${context.lint_cmd}, or ...:default=..., tolerating
# the escaped $${...} shell form (which is not an interpolation reference).
_CONTEXT_REF_RE = re.compile(r"(?<!\$)\$\{context\.(test_cmd|lint_cmd)(?::default=[^}]*)?\}")


def _all_loop_files() -> list[Path]:
    return [
        path
        for path in sorted(BUILTIN_LOOPS_DIR.glob("**/*.yaml"))
        if not any(part.startswith(".") for part in path.relative_to(BUILTIN_LOOPS_DIR).parts)
    ]


def _relative(path: Path) -> str:
    return str(path.relative_to(BUILTIN_LOOPS_DIR))


ALL_LOOP_FILES = _all_loop_files()


@pytest.mark.parametrize("loop_file", ALL_LOOP_FILES, ids=_relative)
def test_no_inline_project_command_config_read(loop_file: Path) -> None:
    rel = _relative(loop_file)
    if rel in _EXEMPT:
        pytest.skip(f"{rel} is an exempted site — see module docstring")

    text = loop_file.read_text()
    hits = [key for key, pattern in _INLINE_ACCESS_RE.items() if pattern.search(text)]
    assert not hits, (
        f"{rel} reads project command key(s) {hits} via an inline raw-JSON access "
        "pattern instead of `ll-config get project.<key>` (BUG-3269). Inline reads "
        "bypass .ll/ll.local.md and can emit the literal string 'None' for a "
        "present-and-null key."
    )


@pytest.mark.parametrize("loop_file", ALL_LOOP_FILES, ids=_relative)
def test_context_references_are_declared(loop_file: Path) -> None:
    """Every ${context.test_cmd} / ${context.lint_cmd} reference must resolve
    against the loop's own declared context: block — an undeclared key
    raises InterpolationError at runtime (BUG-3269 §2's "single
    highest-risk axis"). No exemptions."""
    data = yaml.safe_load(loop_file.read_text())
    if not isinstance(data, dict):
        return

    # `context:` for ordinary loops; `parameters:` for subloops invoked via
    # `loop:` (e.g. oracles/code-run-gate.yaml), whose declared inputs live
    # there instead and are bound at the call site's `with:` block.
    declared = set((data.get("context") or {}).keys()) | set((data.get("parameters") or {}).keys())
    text = loop_file.read_text()

    undeclared = {
        match.group(1) for match in _CONTEXT_REF_RE.finditer(text) if match.group(1) not in declared
    }

    rel = _relative(loop_file)
    assert not undeclared, (
        f"{rel} references ${{context.<key>}} for undeclared context key(s) "
        f"{sorted(undeclared)} — declare them in the loop's `context:` block "
        "or the reference raises InterpolationError at runtime (BUG-3269 §2)."
    )


def test_permanent_exemptions_still_exist() -> None:
    """Guard against a stale exemption list: every listed file must exist,
    so a file rename or deletion doesn't leave a dangling entry behind. Does
    not force a conversion to land — see
    test_no_inline_project_command_config_read for that."""
    for rel in _PERMANENT_EXEMPTIONS:
        assert (BUILTIN_LOOPS_DIR / rel).exists(), (
            f"_PERMANENT_EXEMPTIONS lists {rel!r}, which no longer exists under "
            f"{BUILTIN_LOOPS_DIR} — remove the dangling entry."
        )


def test_dead_code_cleanup_and_test_coverage_improvement_are_not_exempt() -> None:
    """ENH-3288: both sites this issue converts must never be re-added to
    the exemption list — that would silently disable the regression gate for
    the exact control-flow defect this issue closes."""
    assert "dead-code-cleanup.yaml" not in _EXEMPT
    assert "test-coverage-improvement.yaml" not in _EXEMPT


def test_general_task_and_rl_coding_agent_are_not_exempt() -> None:
    """The three sites this issue actually fixes must never be re-added to
    either exemption list — that would silently disable the regression gate
    for the exact defect this issue closes."""
    assert "general-task.yaml" not in _EXEMPT
    assert "rl-coding-agent.yaml" not in _EXEMPT
