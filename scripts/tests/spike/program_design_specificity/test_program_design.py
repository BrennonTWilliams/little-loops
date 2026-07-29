"""AC tests for the ENH-2852 Program Design specificity spike."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from .program_design import (
    extract_call_path_anchors,
    git_grep_resolver,
    grade_program_design,
    parse_signature_lines,
)

VALID_SECTION = """
### Types

- `ProgramDesignGap: str`
- `entries: list[CodeRef]`

### Signatures

- `def grade_program_design(body: str, resolver: Resolver) -> DesignVerdict`
- `FormatGaps.to_dict(self) -> dict[str, list[str]]`

### Call Path

`cmd_format_check` -> `check_format_gaps` -> `grade_program_design`
"""

PROSE_SECTION = """
### Types

We will introduce a new type to hold the result (probably a dataclass).

### Signatures

The function will take the issue body and return whether it is specific enough.

### Call Path

The CLI calls the parser which calls the new checker.
"""


def _fake_resolver(known: set[str]):
    return lambda symbol: symbol.rsplit(".", 1)[-1] in known


class TestSignatureShape:
    def test_accepts_varied_real_signature_shapes(self):
        body = "\n".join(
            [
                '- `def foo(a: int, b: str = "x") -> Bar`',
                "- `async def fetch(self, url: str) -> dict[str, list[int]]`",
                "- `Class.method(self, *args, **kwargs)`",
                "- `render() -> None`",
                "- `sha: str`",
                "- `refs: list[CodeRef] | None`",
            ]
        )
        assert len(parse_signature_lines(body)) == 6

    def test_rejects_prose_that_merely_contains_parentheses(self):
        body = "\n".join(
            [
                "This changes the way the parser handles input (mostly).",
                "We call check_format_gaps(the issue path) and then decide what to do.",
                "Note: this is important and should be considered carefully.",
                "The gate fails when the section is missing, empty, or vague.",
            ]
        )
        assert parse_signature_lines(body) == []


class TestGrading:
    def test_prose_only_section_is_not_specific(self):
        verdict = grade_program_design(PROSE_SECTION, _fake_resolver({"check_format_gaps"}))
        assert verdict.is_specific is False
        assert any("signature-shaped" in r for r in verdict.reasons)

    @pytest.mark.parametrize("body", ["", "   \n\n  \t "])
    def test_missing_or_empty_section_is_not_specific(self, body):
        verdict = grade_program_design(body, _fake_resolver({"check_format_gaps"}))
        assert verdict.is_specific is False
        assert verdict.reasons == ["section is empty"]

    def test_new_identifiers_need_only_be_shape_valid(self):
        """A fake resolver that doesn't know `grade_program_design` still passes the section."""
        verdict = grade_program_design(
            VALID_SECTION, _fake_resolver({"cmd_format_check", "check_format_gaps"})
        )
        assert verdict.is_specific is True
        assert verdict.reasons == []
        assert "grade_program_design" in verdict.unresolved
        assert any("grade_program_design" in s for s in verdict.signatures)

    def test_unresolvable_call_path_anchors_fail(self):
        verdict = grade_program_design(VALID_SECTION, _fake_resolver(set()))
        assert verdict.is_specific is False
        assert any("no call-path anchor resolves" in r for r in verdict.reasons)

    def test_anchors_extracted_only_from_call_path_subsection(self):
        anchors = extract_call_path_anchors(VALID_SECTION)
        assert anchors == ["cmd_format_check", "check_format_gaps", "grade_program_design"]


class TestRealRepoResolution:
    def test_real_repo_anchors_resolve_via_git_grep(self):
        root = Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
        verdict = grade_program_design(
            VALID_SECTION, lambda symbol: git_grep_resolver(symbol, root=root)
        )
        assert verdict.is_specific is True
        assert "check_format_gaps" in verdict.resolved
        assert "cmd_format_check" in verdict.resolved
        # The new identifier's resolution status is irrelevant to the verdict:
        # resolution is only ever *required* of call-path anchors that exist today.
        # A new identifier that happens to resolve (e.g. once its defining code is
        # committed — as this spike itself demonstrates) must never flip the grade.
        assert "grade_program_design" in verdict.resolved + verdict.unresolved

    def test_git_grep_resolver_rejects_undefined_symbol(self):
        assert git_grep_resolver("definitely_not_a_real_symbol_xyz") is False


class TestIsolation:
    def test_spike_does_not_import_production_core(self):
        source = (Path(__file__).parent / "program_design.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert not [name for name in imported if name.split(".")[0] == "little_loops"]
