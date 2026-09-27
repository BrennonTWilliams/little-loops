"""ENH-3630: structural pins on the ``prepare-issue-policy`` dispatch-loop fixture.

Precedent: ``test_prepare_issue.py::TestStructure`` (the real ``prepare-issue.yaml``
wrapper's structural pins). This fixture is test-only (``scripts/tests/fixtures/loops/``,
not ``little_loops/loops/``), so it needs its own copy rather than reusing that file's
tests, but the same load-and-validate + no-drift shape applies.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from little_loops.fsm.validation import load_and_validate
from little_loops.preparation_policy import MAX_STEPS

FIXTURE = Path(__file__).parent / "fixtures" / "loops" / "prepare-issue-policy.yaml"


def data() -> dict:
    return yaml.safe_load(FIXTURE.read_text())


class TestStructure:
    def test_validates(self) -> None:
        fsm, errors = load_and_validate(FIXTURE, raise_on_error=False)
        assert errors == []
        assert fsm.initial == "select_step"

    def test_max_steps_matches_the_exported_budget_constant(self) -> None:
        """The fixture's max_steps must never drift from preparation_policy.MAX_STEPS
        (ENH-3630 § Budget arithmetic): 4 * DONE_FACT_CAP + 3."""
        assert data()["max_steps"] == MAX_STEPS

    def test_mark_rate_limited_is_wired_on_every_ladder_slash_state(self) -> None:
        """BUG-3622 is fixed on main: every slash state must route a rate-limit
        exhaustion to mark_rate_limited (not merely "wired for when it lands")."""
        d = data()
        slash_states = [
            name
            for name, state in d["states"].items()
            if state.get("action_type") == "slash_command"
        ]
        assert slash_states  # sanity: the fixture actually has slash states
        for name in slash_states:
            assert d["states"][name].get("on_rate_limit_exhausted") == "mark_rate_limited", name

    def test_terminals_are_done_and_failed(self) -> None:
        d = data()
        assert d["states"]["done"] == {"terminal": True}
        assert d["states"]["failed"] == {"terminal": True, "failure": True}

    def test_scope_declared(self) -> None:
        assert data()["scope"]
