"""ENH-3261: signature guard against the three legacy automation kwargs
reappearing on the functions ENH-3097/ENH-3261 removed them from.

ENH-3097 originally shimmed ``automation_profile``/``disable_background_tasks``/
``idle_timeout`` alongside ``automation=`` on three concrete functions
(``subprocess_utils.run_claude_command()``, ``issue_manager.run_claude_command()``,
``issue_manager.run_with_continuation()``), with a static AST guard here
preventing any call site from mixing ``automation=`` with a legacy kwarg.
ENH-3261 removed the shim once every in-tree caller had migrated to
``automation=`` — but a written rule alone does not hold: ENH-3130 already
landed a brand-new bare kwarg (``timeout_kill_grace_seconds``) on these same
signatures after ``AutomationContext`` existed, shaped like the pre-collapse
world anyway. This test is repurposed (not deleted) into the mechanical
enforcement of "these three names never reappear on these three signatures" —
an ``inspect.signature`` assertion, since there is no longer a legacy kwarg
for a call site to mix with.
"""

from __future__ import annotations

import inspect

from little_loops import issue_manager, subprocess_utils

_LEGACY_KWARGS = {"automation_profile", "disable_background_tasks", "idle_timeout"}

_TARGET_FUNCTIONS = {
    "subprocess_utils.run_claude_command": subprocess_utils.run_claude_command,
    "issue_manager.run_claude_command": issue_manager.run_claude_command,
    "issue_manager.run_with_continuation": issue_manager.run_with_continuation,
}


class TestNoMixedAutomationKwargs:
    def test_legacy_kwargs_absent_from_target_signatures(self) -> None:
        violations: list[str] = []
        for qualname, func in _TARGET_FUNCTIONS.items():
            params = set(inspect.signature(func).parameters)
            reintroduced = sorted(params & _LEGACY_KWARGS)
            if reintroduced:
                violations.append(f"{qualname}: {reintroduced}")

        assert not violations, (
            "Found removed legacy kwarg(s) reintroduced on a signature ENH-3261 "
            f"stripped them from (Decision Rules item 2): {violations}"
        )

    def test_guard_detects_synthetic_reintroduction(self) -> None:
        """Self-test: the guard actually fires if a legacy kwarg comes back."""

        def fake_run_claude_command(
            command: str, *, automation: object = None, idle_timeout: int = 0
        ) -> None:
            raise NotImplementedError

        params = set(inspect.signature(fake_run_claude_command).parameters)
        assert params & _LEGACY_KWARGS

    def test_automation_kwarg_still_present(self) -> None:
        """The one automation parameter that survives must still be there."""
        for func in _TARGET_FUNCTIONS.values():
            assert "automation" in inspect.signature(func).parameters
