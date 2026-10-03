"""Contract tests for BUG-3708: verify-issues check B8 (format-check citation findings).

B8 is the consumer half of the BUG-3691 split. These tests assert the command's
structure, not its wording, and pin the producer coverage contract B8's two-source
rule depends on. They do not prove the model obeys B8.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from little_loops.issue_parser import _ADVISORY_GAP_CLASSES, check_format_gaps
from little_loops.issues.citations import (
    PROPERTY_LINE,
    PROPERTY_PATH,
    PROPERTY_SYMBOL_DEFINED,
    PROPERTY_SYMBOL_RESOLVES,
    CitationCheck,
)
from little_loops.issues.symbol_claims import build_symbol_index
from little_loops.text_utils import build_ref_index

PROJECT_ROOT = Path(__file__).parent.parent.parent
VERIFY_CMD = PROJECT_ROOT / "commands" / "verify-issues.md"
CLI_DOC = PROJECT_ROOT / "docs" / "reference" / "CLI.md"

BLOCKING_KEYS = (
    "stale_file_ref",
    "ambiguous_file_ref",
    "stale_symbol_ref",
    "mislocated_symbol_ref",
)


def _body() -> str:
    content = VERIFY_CMD.read_text()
    return content[content.index("---", 3) + 3 :]


def _flat(text: str) -> str:
    return " ".join(text.split())


def _b8() -> str:
    """B8 slice: between check 7 and the causal-claims method paragraph / §C."""
    body = _body()
    start = body.index("8. **Citation findings via format-check")
    end = body.index("#### C. Determine Verdict")
    return body[start:end]


class TestB8Placement:
    def test_sits_between_check_7_and_verdict_section(self) -> None:
        body = _body()
        check7 = body.index("7. **Evidence-quote existence check")
        b8 = body.index("8. **Citation findings via format-check")
        verdict = body.index("#### C. Determine Verdict")
        assert check7 < b8 < verdict

    def test_invokes_single_id_format_check_json(self) -> None:
        text = _b8()
        assert 'll-issues format-check "$ID" --format json' in text
        assert "$ISSUE_FILE" in text  # named only to be prohibited
        assert "never `$ISSUE_FILE`" in _flat(text)

    def test_names_cli_as_resolution_owner(self) -> None:
        flat = _flat(_b8())
        assert "owns" in flat and "docs/reference/CLI.md" in flat


class TestB8Contract:
    def test_names_occurrence_identity_fields_and_properties(self) -> None:
        text = _b8()
        for field in ("issue_line", "issue_column", "ref", "property"):
            assert field in text
        for prop in (PROPERTY_PATH, PROPERTY_LINE, PROPERTY_SYMBOL_RESOLVES):
            assert prop in text
        assert PROPERTY_SYMBOL_DEFINED in text

    def test_names_blocking_keys_by_reference_not_restated_list(self) -> None:
        text = _b8()
        assert not all(key in text for key in BLOCKING_KEYS)
        assert "stale_file_ref" in text  # only for the untracked-reporting rule
        assert not any(key in text for key in _ADVISORY_GAP_CLASSES - {"testable"})

    def test_table_rows_cover_all_coverage_outcomes(self) -> None:
        text = _b8()
        rows = [ln for ln in text.splitlines() if ln.strip().startswith("|")]
        flat_rows = _flat("\n".join(rows))
        for needle in ("`ok`", "Blocking gap key", "Advisory gap key", "Absent, unsupported"):
            assert needle in flat_rows
        assert len(rows) == 6  # header + separator + four treatments

    def test_property_exact_demotion_rules(self) -> None:
        flat = _flat(_b8())
        assert "Property-exact demotion" in flat
        assert f"`{PROPERTY_PATH}: ok`" in flat and "exists on disk" in flat
        assert f"`{PROPERTY_LINE}: ok`" in flat and "past end of file" in flat
        assert f"`{PROPERTY_SYMBOL_RESOLVES}: ok`" in flat
        assert f"`{PROPERTY_SYMBOL_DEFINED}: ok`" in flat
        assert "not examined" in flat

    def test_untracked_wording_for_stale_file_ref(self) -> None:
        assert "**untracked**" in _b8()


class TestB8Consumability:
    def test_decided_by_parse_not_exit_code(self) -> None:
        flat = _flat(_b8())
        assert "parses to a JSON object" in flat and "`examined_refs` is a list" in flat
        assert "not the exit code" in flat
        assert "silent fallback" in flat

    def test_single_shared_call_and_freshness(self) -> None:
        flat = _flat(_b8())
        assert "once" in flat and "§E step 3" in flat
        assert "after a §4 edit" in flat
        e3 = _flat(_body()[_body().index("3. **Prose dependency claims**") :][:700])
        assert "check B8" in e3


class TestB8Modes:
    def test_check_and_from_evidence_behavior(self) -> None:
        flat = _flat(_b8())
        assert "Skipped under `--from-evidence`" in flat
        assert "read-only under `--check`" in flat
        assert "never repairs citations" in flat

    def test_report_has_citation_summary_line(self) -> None:
        body = _body()
        report = body[body.index("### 5. Output Report") :]
        assert "Citations (B8)" in report


class TestChecks1And2AndContextRuling:
    @pytest.mark.parametrize("check", ["1. **Check files exist**", "2. **Verify line numbers**"])
    def test_checks_1_and_2_defer_to_b8(self, check: str) -> None:
        body = _body()
        start = body.index(check)
        assert "B8 governs examined" in _flat(body[start : start + 250])

    def test_context_section_is_ruled_outside_correctable_scope(self) -> None:
        body = _body()
        start = body.index("**Correctable scope for `CLAIMS_OUTDATED`")
        scope = _flat(body[start : body.index("#### E. Validate Dependency")])
        assert "`## Context` is in neither list" in scope
        assert "`NON_VALID`" in scope


class TestCliDocNamesConsumer:
    def test_cli_doc_names_verify_issues_b8(self) -> None:
        assert "`/ll:verify-issues` check B8" in CLI_DOC.read_text()


# ---------------------------------------------------------------------------
# Producer coverage contract (probed 2026-10-03): B8's two-source rule
# ---------------------------------------------------------------------------

_TAIL = (
    "\n## Expected Behavior\nIt works.\n\n## Steps to Reproduce\n1. Do it.\n\n"
    "## Acceptance Criteria\n- [ ] ok\n\n## Impact\n- **Priority**: P3\n- **Effort**: S\n"
    "- **Risk**: Low\n- **Breaking Change**: No\n\n## Status\nopen\n"
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "term.py").write_text("def terminal_size():\n    return 1\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def _gaps(repo: Path, summary: str) -> tuple[object, list[CitationCheck]]:
    path = repo / ".issues" / "bugs" / "P3-BUG-9996-t.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nid: BUG-9996\nstatus: open\n---\n\n# BUG-9996: t\n\n## Summary\n"
        f"{summary}\n\n## Current Behavior\nIt breaks.\n" + _TAIL
    )
    collected: list[CitationCheck] = []
    gaps = check_format_gaps(
        path,
        ref_index=build_ref_index(repo),
        symbol_index=build_symbol_index(repo),
        examined_refs=collected,
        project_root=repo,
    )
    return gaps, collected


def test_blocking_plain_path_mention_has_gap_entry_but_no_examined_ref(repo: Path) -> None:
    gaps, collected = _gaps(repo, "The bug is in `pkg/gone_module.py` somewhere.")
    assert gaps.stale_file_ref  # type: ignore[attr-defined]
    assert collected == []


def test_blocking_symbol_claim_appears_in_gap_list_and_examined_refs(repo: Path) -> None:
    gaps, collected = _gaps(repo, "The bug is in `pkg/term.py:gone_symbol()`.")
    assert gaps.stale_symbol_ref  # type: ignore[attr-defined]
    assert [c.result for c in collected if c.property == PROPERTY_SYMBOL_RESOLVES] == [
        "stale_symbol_ref"
    ]
