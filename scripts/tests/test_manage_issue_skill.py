"""Regression tests for manage-issue Phase 4 running configured commands verbatim (ENH-3612)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "manage-issue" / "SKILL.md"


def _phase4_text() -> str:
    content = SKILL.read_text()
    start = content.index("## Phase 4: Verify")
    end = content.index("### Headless-Safe Final Test Run")
    return content[start:end]


class TestManageIssuePhase4Verbatim:
    def test_lint_and_type_placeholders_are_bare(self) -> None:
        checked = 0
        for line in _phase4_text().splitlines():
            for key in ("lint_cmd", "type_cmd"):
                placeholder = "{{config.project." + key + "}}"
                if placeholder in line:
                    checked += 1
                    assert line.strip() == placeholder
        assert checked == 2

    def test_no_test_cmd_line_in_phase4_block(self) -> None:
        text = _phase4_text()
        assert "{{config.project.test_cmd}}" not in text
        assert "Headless-Safe Final Test Run" in text

    def test_phase4_says_run_as_configured(self) -> None:
        assert "exactly as configured" in _phase4_text()


@pytest.mark.parametrize(
    "rel", ["commands/check-code.md", "commands/iterate-plan.md", "skills/create-loop/SKILL.md"]
)
def test_type_cmd_never_appends_src_dir(rel: str) -> None:
    text = (ROOT / rel).read_text()
    assert "{{config.project.type_cmd}} {{config.project.src_dir}}" not in text
