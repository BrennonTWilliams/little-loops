"""ENH-3097 AC12: static guard against forwarding automation= alongside a
legacy automation_profile=/disable_background_tasks=/idle_timeout= kwarg.

resolve_automation() treats that combination as a conflict (DeprecationWarning,
explicit automation= wins and the legacy value — critically idle_timeout — is
discarded, not merged). Nothing else in the suite catches every call site
mechanically: AC 9's no-spurious-warning test only exercises the paths it
happens to call. This test walks every ``.py`` file under
``scripts/little_loops/`` and fails on any ``ast.Call`` to
``run_claude_command`` / ``run_with_continuation`` (matched by callee name —
covers both the ``subprocess_utils`` and ``issue_manager`` symbols, and the
``_run_claude_base`` import aliases at ``issue_manager.py:66`` and
``worker_pool.py:39``) that passes ``automation=`` together with any of the
three legacy kwargs.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_TARGET_NAMES = {
    "run_claude_command",
    "run_with_continuation",
    "_run_claude_base",
}
_LEGACY_KWARGS = {"automation_profile", "disable_background_tasks", "idle_timeout"}


def _callee_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _find_violations(source: str, relpath: str) -> list[str]:
    tree = ast.parse(source, filename=relpath)
    violations: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            name = _callee_name(node.func)
            if name in _TARGET_NAMES:
                kwarg_names = {kw.arg for kw in node.keywords if kw.arg is not None}
                if "automation" in kwarg_names and kwarg_names & _LEGACY_KWARGS:
                    mixed = sorted(kwarg_names & _LEGACY_KWARGS)
                    violations.append(f"{relpath}:{node.lineno}: {name}(automation=, {mixed})")
            self.generic_visit(node)

    _Visitor().visit(tree)
    return violations


def _scripts_root() -> Path:
    return Path(__file__).parent.parent / "little_loops"


def _all_py_files() -> list[Path]:
    return sorted(_scripts_root().rglob("*.py"))


class TestNoMixedAutomationKwargs:
    def test_no_call_site_mixes_automation_with_legacy_kwargs(self) -> None:
        all_violations: list[str] = []
        for path in _all_py_files():
            source = path.read_text(encoding="utf-8")
            relpath = str(path.relative_to(_scripts_root().parent))
            all_violations.extend(_find_violations(source, relpath))

        assert not all_violations, (
            "Found call site(s) passing automation= alongside a legacy "
            "automation_profile=/disable_background_tasks=/idle_timeout= kwarg "
            "(ENH-3097 Decision Rules — each layer forwards only automation= "
            f"onward): {all_violations}"
        )

    @pytest.mark.parametrize(
        "snippet",
        [
            'run_claude_command(automation=x, automation_profile="p")',
            "run_claude_command(automation=x, disable_background_tasks=True)",
            "run_claude_command(automation=x, idle_timeout=30)",
            "run_with_continuation(automation=x, idle_timeout=30)",
            "_run_claude_base(automation=x, idle_timeout=30)",
        ],
    )
    def test_guard_detects_synthetic_violation(self, snippet: str) -> None:
        """Self-test: the guard actually fires on the shape it's meant to catch."""
        violations = _find_violations(f"{snippet}\n", "synthetic.py")
        assert violations, f"guard failed to flag: {snippet}"

    def test_guard_allows_automation_alone(self) -> None:
        violations = _find_violations("run_claude_command(automation=x)\n", "synthetic.py")
        assert not violations
