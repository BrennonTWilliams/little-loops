"""Tests for the /ll:advise skill (FEAT-3121).

The real drift risk for an untestable prose artifact is the skill naming a
flag, JSON key, or skip reason that does not exist in the CLI it wraps.
These tests import from the source rather than hardcoding literals.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from little_loops.cli.advise import _SKIP_MESSAGES

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "advise" / "SKILL.md"

_VERDICT_KEYS = ("recommendation", "risks", "confidence", "dissent", "signal", "host", "model")


def _frontmatter_and_body() -> tuple[dict, str]:
    content = SKILL_FILE.read_text()
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    assert match, "SKILL.md must have a YAML frontmatter block"
    frontmatter = yaml.safe_load(match.group(1))
    return frontmatter, match.group(2)


def test_skill_file_exists() -> None:
    assert SKILL_FILE.exists(), f"Skill file not found: {SKILL_FILE}"


def test_all_cli_flags_named_in_skill_exist_in_cli_help() -> None:
    from little_loops.cli.advise import main_advise

    content = SKILL_FILE.read_text()
    flags = set(re.findall(r"--[a-z][a-z-]*", content))

    from contextlib import redirect_stdout
    from io import StringIO
    from unittest.mock import patch

    buf = StringIO()
    with patch("sys.argv", ["ll-advise", "--help"]), redirect_stdout(buf):
        try:
            main_advise(["--help"])
        except SystemExit:
            pass
    help_text = buf.getvalue()

    for flag in flags:
        assert flag in help_text, f"Skill references {flag!r}, not a real ll-advise flag"


def test_verdict_keys_named_in_skill_body() -> None:
    content = SKILL_FILE.read_text()
    for key in _VERDICT_KEYS:
        assert key in content, f"AdvisorVerdict field {key!r} must be named in the skill body"


def test_skip_reasons_named_in_skill_body() -> None:
    content = SKILL_FILE.read_text()
    assert set(_SKIP_MESSAGES) == {
        "disabled",
        "trigger_not_allowed",
        "budget_exhausted",
        "not_configured",
        "floor_violation",
        "failed",
        "timeout",
    }
    for reason in _SKIP_MESSAGES:
        assert reason in content, f"skipped_reason {reason!r} must be named in the skill body"


def test_frontmatter_shape() -> None:
    frontmatter, _ = _frontmatter_and_body()

    assert frontmatter["disable-model-invocation"] is False
    assert "metadata" in frontmatter and frontmatter["metadata"].get("short-description")

    fixtures = frontmatter.get("trigger_fixtures")
    assert fixtures, "trigger_fixtures block required for a model-invocable skill"
    assert fixtures.get("should_fire"), "trigger_fixtures.should_fire must be non-empty"
    assert fixtures.get("should_not_fire"), "trigger_fixtures.should_not_fire must be non-empty"

    allowed_tools = frontmatter.get("allowed-tools", [])
    assert "Bash(ll-advise:*)" in allowed_tools
    assert "Bash" not in allowed_tools, "must not carry a bare Bash entry"


def test_go_no_go_fixture_present() -> None:
    frontmatter, _ = _frontmatter_and_body()
    should_not_fire = frontmatter["trigger_fixtures"]["should_not_fire"]
    assert any(
        "go" in phrase.lower() and "no-go" in phrase.lower() for phrase in should_not_fire
    ), "should_not_fire must include at least one go-no-go-shaped phrasing"


def test_no_plugin_version_marker() -> None:
    content = SKILL_FILE.read_text()
    assert "PLUGIN_VERSION" not in content


def test_go_no_go_disambiguation_present() -> None:
    go_no_go_file = PROJECT_ROOT / "skills" / "go-no-go" / "SKILL.md"
    content = go_no_go_file.read_text()
    assert "/ll:advise" in content, (
        "go-no-go must carry a pointer distinguishing it from /ll:advise"
    )
