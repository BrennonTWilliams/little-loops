"""Tests for occurrence-aware citation checks and coverage metadata (BUG-3691)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from little_loops.issue_parser import FormatGaps, check_format_gaps
from little_loops.issues.citations import (
    CitationCheck,
    CitationReport,
    check_citations,
)
from little_loops.issues.symbol_claims import (
    SymbolIndex,
    build_symbol_index,
    classify_symbol_definition,
    extract_symbol_claims,
    iter_symbol_claim_occurrences,
)
from little_loops.text_utils import RefIndex, build_ref_index

_TERM = "def terminal_size():\n    return 1\n"
_FEED = "from pkg.term import terminal_size\n\n\ndef real_func():\n    return terminal_size()\n"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A small tracked repo: feed.py imports (not defines) terminal_size."""
    _write(tmp_path, "pkg/term.py", _TERM)
    _write(tmp_path, "pkg/feed.py", _FEED)
    _write(tmp_path, "pkg/empty.py", "")
    _write(tmp_path, "pkg/dup/same.py", "x = 1\n")
    _write(tmp_path, "pkg/other/same.py", "x = 2\n")
    _write(tmp_path, ".codex/a/only.md", "one\ntwo\nthree\n")
    _write(tmp_path, ".gemini/a/only.md", "one\ntwo\nthree\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def ref_index(repo: Path) -> RefIndex:
    return build_ref_index(repo)


@pytest.fixture
def symbol_index(repo: Path) -> SymbolIndex:
    return build_symbol_index(repo)


def _issue(*, current: str = "", integration: str = "", tests: str = "") -> str:
    """Issue text with frontmatter so positions are checked against the full file."""
    parts = [
        "---",
        "id: BUG-9999",
        "status: open",
        "---",
        "",
        "# BUG-9999: t",
        "",
        "## Summary",
        current or "Nothing cited here.",
        "",
        "## Integration Map",
        integration or "None.",
        "",
        "### Tests",
        tests or "None.",
        "",
        "## Status",
        "open",
    ]
    return "\n".join(parts)


def _run(
    content: str,
    ref_index: RefIndex,
    symbol_index: SymbolIndex | None,
    repo: Path | None,
    **kwargs: object,
) -> CitationReport:
    return check_citations(
        content,
        ref_index=ref_index,
        symbol_index=symbol_index,
        project_root=repo,
        **kwargs,  # type: ignore[arg-type]
    )


def _by_prop(report: CitationReport, prop: str) -> list[CitationCheck]:
    return [c for c in report.checks if c.property == prop]


# ---------------------------------------------------------------------------
# Definition vs import
# ---------------------------------------------------------------------------


def test_imported_only_definition_claim_is_advisory_mislocated(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(
        _issue(tests="- `pkg/feed.py:terminal_size()` — wiring target"),
        ref_index,
        symbol_index,
        repo,
    )
    assert report.advisory_mislocated_symbol_ref == [
        "terminal_size (claimed in pkg/feed.py; imported there, defined in pkg/term.py)"
    ]
    resolves = _by_prop(report, "symbol_resolves_in")
    defined = _by_prop(report, "symbol_defined_in")
    assert [c.result for c in resolves] == ["ok"]  # import-inclusive presence only
    assert [c.result for c in defined] == ["advisory_mislocated_symbol_ref"]
    assert not any(c.property == "symbol_defined_in" and c.result == "ok" for c in report.checks)


def test_definition_in_cited_file_is_defined_ok(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(
        _issue(tests="- `pkg/term.py:terminal_size()` — defined here"),
        ref_index,
        symbol_index,
        repo,
    )
    assert report.advisory_mislocated_symbol_ref == []
    assert [c.result for c in _by_prop(report, "symbol_defined_in")] == ["ok"]


def test_usage_site_mention_gets_no_definition_entry(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(
        _issue(tests="- The loop calls `terminal_size()` from `pkg/feed.py` on resize."),
        ref_index,
        symbol_index,
        repo,
    )
    assert [c.result for c in _by_prop(report, "symbol_resolves_in")] == ["ok"]
    assert _by_prop(report, "symbol_defined_in") == []
    assert report.advisory_mislocated_symbol_ref == []


def test_defined_in_phrase_makes_same_sentence_claim_definition_shaped(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(
        _issue(tests="- `terminal_size()` is defined in `pkg/feed.py`."),
        ref_index,
        symbol_index,
        repo,
    )
    assert [c.result for c in _by_prop(report, "symbol_defined_in")] == [
        "advisory_mislocated_symbol_ref"
    ]
    (entry,) = _by_prop(report, "symbol_resolves_in")
    # the complete attribution span, backticks removed — not the bare name
    assert entry.ref == "terminal_size()` is defined in `pkg/feed.py".replace("`", "")


def test_multiple_alternative_definitions_publish_no_guess(repo: Path) -> None:
    _write(repo, "pkg/term2.py", _TERM)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    refs, symbols = build_ref_index(repo), build_symbol_index(repo)
    report = _run(_issue(tests="- `pkg/feed.py:terminal_size()` — target"), refs, symbols, repo)
    assert _by_prop(report, "symbol_defined_in") == []
    assert report.advisory_mislocated_symbol_ref == []


def test_empty_reverse_index_never_authorizes_definition(repo: Path) -> None:
    refs = build_ref_index(repo)
    symbols = SymbolIndex(root=repo)  # no reverse index
    report = _run(_issue(tests="- `pkg/term.py:terminal_size()`"), refs, symbols, repo)
    assert [c.result for c in _by_prop(report, "symbol_resolves_in")] == ["ok"]
    assert _by_prop(report, "symbol_defined_in") == []


def test_classify_symbol_definition_contract(symbol_index: SymbolIndex) -> None:
    (claim,) = extract_symbol_claims("`pkg/feed.py:terminal_size()`", _stub_refs(symbol_index))
    assert classify_symbol_definition(symbol_index, claim) == ("mislocated", "pkg/term.py")


def _stub_refs(symbol_index: SymbolIndex) -> RefIndex:
    return build_ref_index(symbol_index.root)


def test_suppressed_claim_has_no_coverage(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    tests = "<!-- ll-prose-ok: intentional -->\n- `pkg/feed.py:terminal_size()`"
    report = _run(_issue(tests=tests), ref_index, symbol_index, repo)
    assert report.checks == []
    assert report.advisory_mislocated_symbol_ref == []


def test_unsupported_language_file_has_no_symbol_entry(repo: Path) -> None:
    _write(repo, "pkg/notes.md", "# notes\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    refs, symbols = build_ref_index(repo), build_symbol_index(repo)
    report = _run(_issue(tests="- `pkg/notes.md:something()`"), refs, symbols, repo)
    assert _by_prop(report, "symbol_resolves_in") == []
    assert _by_prop(report, "symbol_defined_in") == []


# ---------------------------------------------------------------------------
# Line bounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cite", "expected"),
    [
        ("pkg/term.py:1", "ok"),
        ("pkg/term.py:2", "ok"),
        ("pkg/term.py:1-2", "ok"),
        ("pkg/term.py:3", "stale_line_ref"),
        ("pkg/term.py:0", "stale_line_ref"),
        ("pkg/term.py:2-1", "stale_line_ref"),
        ("pkg/term.py:1-99", "stale_line_ref"),
        ("pkg/empty.py:1", "stale_line_ref"),
    ],
)
def test_line_range_validity(
    cite: str, expected: str, repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(_issue(tests=f"- see `{cite}` for details"), ref_index, symbol_index, repo)
    (entry,) = _by_prop(report, "line_in_range")
    assert entry.result == expected
    assert entry.ref == cite
    assert bool(report.stale_line_ref) is (expected != "ok")


def test_line_check_is_rooted_at_project_not_cwd(
    repo: Path,
    ref_index: RefIndex,
    symbol_index: SymbolIndex,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    _write(elsewhere, "pkg/term.py", "\n".join(["x"] * 50))  # would pass line 40 if cwd-rooted
    monkeypatch.chdir(elsewhere)
    report = _run(_issue(tests="- `pkg/term.py:40`"), ref_index, symbol_index, repo)
    assert [c.result for c in _by_prop(report, "line_in_range")] == ["stale_line_ref"]


def test_no_root_leaves_line_bounds_unexamined(ref_index: RefIndex) -> None:
    report = _run(_issue(tests="- `pkg/term.py:1`"), ref_index, None, None)
    assert [c.result for c in _by_prop(report, "path_resolves")] == ["ok"]
    assert _by_prop(report, "line_in_range") == []


def test_tracked_but_deleted_file_gets_path_ok_but_no_line_entry(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    (repo / "pkg" / "term.py").unlink()
    report = _run(_issue(tests="- `pkg/term.py:1`"), ref_index, symbol_index, repo)
    assert [c.result for c in _by_prop(report, "path_resolves")] == ["ok"]
    assert _by_prop(report, "line_in_range") == []
    assert report.stale_line_ref == []


def test_stale_path_gets_failing_path_entry_but_no_line_pass(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(_issue(tests="- `pkg/missing.py:3`"), ref_index, symbol_index, repo)
    assert [c.result for c in _by_prop(report, "path_resolves")] == ["advisory_stale_file_ref"]
    assert _by_prop(report, "line_in_range") == []
    assert report.advisory_stale_file_ref == ["pkg/missing.py:3"]


def test_unsupported_line_forms_are_not_examined(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(
        _issue(tests="- `pkg/term.py:L2` and `pkg/term.py:1:5` and https://x.example.com:80"),
        ref_index,
        symbol_index,
        repo,
    )
    assert report.checks == []


# ---------------------------------------------------------------------------
# Bare filename citations
# ---------------------------------------------------------------------------


def test_bare_filename_single_match_resolves(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(_issue(tests="- `feed.py:3`"), ref_index, symbol_index, repo)
    assert [c.result for c in _by_prop(report, "path_resolves")] == ["ok"]
    assert [c.result for c in _by_prop(report, "line_in_range")] == ["ok"]


def test_bare_filename_zero_matches_is_advisory_stale(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(_issue(tests="- `nowhere.py:3`"), ref_index, symbol_index, repo)
    assert [c.result for c in _by_prop(report, "path_resolves")] == ["advisory_stale_file_ref"]
    assert report.advisory_stale_file_ref == ["nowhere.py:3"]


def test_bare_filename_multiple_matches_lists_sorted_candidates(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(_issue(tests="- `same.py:1`"), ref_index, symbol_index, repo)
    assert [c.result for c in _by_prop(report, "path_resolves")] == ["advisory_ambiguous_file_ref"]
    assert report.advisory_ambiguous_file_ref == [
        "same.py:1 (2: pkg/dup/same.py, pkg/other/same.py)"
    ]
    assert _by_prop(report, "line_in_range") == []


def test_mirror_only_multiple_matches_are_ambiguous_not_stale(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(_issue(tests="- `only.md:1`"), ref_index, symbol_index, repo)
    assert [c.result for c in _by_prop(report, "path_resolves")] == ["advisory_ambiguous_file_ref"]
    assert report.advisory_stale_file_ref == []


def test_planned_new_bare_filename_is_unexamined(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(_issue(tests="- `brand_new.py:10` (new)"), ref_index, symbol_index, repo)
    assert report.checks == []
    assert report.advisory_stale_file_ref == []


def test_untracked_by_design_slash_path_is_unexamined(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(_issue(tests="- `thoughts/shared/plan.md:4`"), ref_index, symbol_index, repo)
    assert report.checks == []


def test_unsuffixed_bare_filename_is_not_newly_checked(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(_issue(tests="- `nowhere.py` and `feed.py`"), ref_index, symbol_index, repo)
    assert report.checks == []
    assert not report.advisory_stale_file_ref


def test_bare_filename_symbol_form_requires_call_parens(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    with_parens = _run(_issue(tests="- `term.py:terminal_size()`"), ref_index, symbol_index, repo)
    assert [c.result for c in _by_prop(with_parens, "path_resolves")] == ["ok"]
    without = _run(_issue(tests="- `term.py:terminal_size`"), ref_index, symbol_index, repo)
    assert _by_prop(without, "path_resolves") == []  # no new path coverage...
    assert [c.result for c in _by_prop(without, "symbol_resolves_in")] == [
        "ok"
    ]  # ...existing form kept


def test_empty_index_authorizes_no_path_verdict(repo: Path, symbol_index: SymbolIndex) -> None:
    empty = RefIndex(by_basename={})
    report = _run(_issue(tests="- `pkg/term.py:1`"), empty, symbol_index, repo)
    assert report.checks == []
    assert report.advisory_stale_file_ref == []


# ---------------------------------------------------------------------------
# Occurrence identity, scope, positions
# ---------------------------------------------------------------------------


def test_positions_are_one_based_in_the_full_file_including_frontmatter(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    content = _issue(tests="- see `pkg/term.py:1` now")
    report = _run(content, ref_index, symbol_index, repo)
    (entry,) = _by_prop(report, "line_in_range")
    line_text = content.split("\n")[entry.issue_line - 1]
    assert line_text[entry.issue_column - 1 :].startswith("pkg/term.py:1")


def test_fenced_citations_are_skipped(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    tests = "```\n`pkg/feed.py:terminal_size()` pkg/term.py:99\n```\n- real `pkg/term.py:1`"
    report = _run(_issue(tests=tests), ref_index, symbol_index, repo)
    assert {c.ref for c in report.checks} == {"pkg/term.py:1"}


def test_same_file_different_ranges_keep_distinct_identities(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(
        _issue(tests="- `pkg/term.py:1-2` and `pkg/term.py:5-9`"), ref_index, symbol_index, repo
    )
    results = {c.ref: c.result for c in _by_prop(report, "line_in_range")}
    assert results == {"pkg/term.py:1-2": "ok", "pkg/term.py:5-9": "stale_line_ref"}


def test_repeated_symbol_attributed_to_different_files(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(
        _issue(tests="- `pkg/feed.py:terminal_size()`\n- `pkg/term.py:terminal_size()`"),
        ref_index,
        symbol_index,
        repo,
    )
    defined = {c.ref: c.result for c in _by_prop(report, "symbol_defined_in")}
    assert defined == {
        "pkg/feed.py:terminal_size()": "advisory_mislocated_symbol_ref",
        "pkg/term.py:terminal_size()": "ok",
    }


def test_current_state_occurrence_uses_legacy_blocking_key_and_new_scope_is_advisory(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    cite = "`pkg/term.py:gone_symbol()`"
    content = _issue(current=f"The bug lives in {cite}.", tests=f"- {cite}")
    (claim,) = extract_symbol_claims(f"The bug lives in {cite}.", ref_index)
    report = _run(content, ref_index, symbol_index, repo, legacy_symbol_outcomes={claim: "stale"})
    by_line = sorted(_by_prop(report, "symbol_resolves_in"), key=lambda c: c.issue_line)
    assert [c.result for c in by_line] == ["stale_symbol_ref", "advisory_stale_symbol_ref"]
    # only the new-scope occurrence becomes an advisory finding
    assert report.advisory_stale_symbol_ref == ["gone_symbol (claimed in pkg/term.py)"]


def test_current_state_occurrence_without_legacy_outcome_gets_no_entry(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(
        _issue(current="Lives in `pkg/term.py:terminal_size()`."), ref_index, symbol_index, repo
    )
    assert _by_prop(report, "symbol_resolves_in") == []


def test_nested_tests_inside_integration_map_is_not_double_counted(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    report = _run(_issue(tests="- `pkg/term.py:1`"), ref_index, symbol_index, repo)
    assert len(_by_prop(report, "line_in_range")) == 1


def test_wiring_phase_heading_with_suffix_is_in_scope(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    content = _issue() + "\n\n### Wiring Phase (added by `/ll:wire-issue`)\n- `pkg/term.py:50`\n"
    report = _run(content, ref_index, symbol_index, repo)
    assert [c.result for c in _by_prop(report, "line_in_range")] == ["stale_line_ref"]


def test_checks_sorted_deduplicated_and_byte_identical(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    content = _issue(
        integration="- `pkg/term.py:2` and `pkg/feed.py:terminal_size()`",
        tests="- `pkg/term.py:9` `same.py:1`",
    )
    first = _run(content, ref_index, symbol_index, repo)
    second = _run(content, ref_index, symbol_index, repo)
    assert [c.to_dict() for c in first.checks] == [c.to_dict() for c in second.checks]
    keys = [c.sort_key() for c in first.checks]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)
    triples = [(c.issue_line, c.issue_column, c.ref, c.property) for c in first.checks]
    assert len(set(triples)) == len(triples)  # never both ok and failure for one occurrence


def test_citation_check_serializes_exact_schema() -> None:
    check = CitationCheck("a.py:1", 3, 4, "line_in_range", "ok")
    assert list(check.to_dict()) == ["ref", "issue_line", "issue_column", "property", "result"]


def test_symbol_occurrence_iterator_matches_set_extractor(ref_index: RefIndex, repo: Path) -> None:
    body = (
        "Calls `pkg/feed.py:terminal_size()` and `term.terminal_size()`;\n"
        "`terminal_size()` is defined in `pkg/term.py`.\n"
    )
    claims = extract_symbol_claims(body, ref_index)
    occurrences = iter_symbol_claim_occurrences(body, ref_index)
    assert {o.claim for o in occurrences} == claims
    for occ in occurrences:
        assert occ.ref  # complete attribution span retained
        assert body[occ.start : occ.end].replace("`", "") == occ.ref


# ---------------------------------------------------------------------------
# check_format_gaps integration: collector, advisory-only, metadata is not a gap
# ---------------------------------------------------------------------------

_BUG_TEMPLATE_TAIL = (
    "\n## Expected Behavior\nIt works.\n\n## Steps to Reproduce\n1. Do it.\n\n"
    "## Acceptance Criteria\n- [ ] ok\n\n## Impact\n- **Priority**: P3\n- **Effort**: S\n"
    "- **Risk**: Low\n- **Breaking Change**: No\n"
)


def _bug_file(repo: Path, tests_line: str) -> Path:
    body = (
        "---\nid: BUG-9998\nstatus: open\n---\n\n# BUG-9998: t\n\n## Summary\nA real problem.\n\n"
        "## Current Behavior\nIt breaks.\n"
        + _BUG_TEMPLATE_TAIL
        + f"\n## Integration Map\n\n### Tests\n- {tests_line}\n\n## Status\nopen\n"
    )
    path = repo / ".issues" / "bugs" / "P3-BUG-9998-t.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def test_metadata_only_issue_has_no_gaps(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    path = _bug_file(repo, "`pkg/term.py:1`")
    collected: list[CitationCheck] = []
    gaps = check_format_gaps(
        path,
        ref_index=ref_index,
        symbol_index=symbol_index,
        examined_refs=collected,
        project_root=repo,
    )
    assert collected  # coverage was gathered...
    assert not gaps.has_gaps  # ...and is never a gap
    assert not gaps.has_blocking_gaps
    assert "examined_refs" not in gaps.to_dict()
    assert "examined_refs" not in set(FormatGaps.__dataclass_fields__)


def test_advisory_findings_set_has_gaps_but_not_blocking(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    path = _bug_file(repo, "`pkg/term.py:99`")
    gaps = check_format_gaps(
        path, ref_index=ref_index, symbol_index=symbol_index, project_root=repo
    )
    assert gaps.stale_line_ref
    assert gaps.has_gaps
    assert not gaps.has_blocking_gaps


def test_check_format_gaps_without_collector_still_reports_advisories(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    path = _bug_file(repo, "`pkg/feed.py:terminal_size()`")
    gaps = check_format_gaps(
        path, ref_index=ref_index, symbol_index=symbol_index, project_root=repo
    )
    assert gaps.advisory_mislocated_symbol_ref
    assert not gaps.has_blocking_gaps


def test_project_root_falls_back_to_symbol_index_root(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    path = _bug_file(repo, "`pkg/term.py:99`")
    gaps = check_format_gaps(path, ref_index=ref_index, symbol_index=symbol_index)
    assert gaps.stale_line_ref
    gaps_no_root = check_format_gaps(path, ref_index=ref_index)
    assert gaps_no_root.stale_line_ref == []


def test_existing_blocking_stale_symbol_rule_unchanged(
    repo: Path, ref_index: RefIndex, symbol_index: SymbolIndex
) -> None:
    path = repo / ".issues" / "bugs" / "P3-BUG-9997-t.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nid: BUG-9997\nstatus: open\n---\n\n# BUG-9997: t\n\n## Summary\n"
        "The bug is in `pkg/term.py:gone_symbol()`.\n" + _BUG_TEMPLATE_TAIL
    )
    collected: list[CitationCheck] = []
    gaps = check_format_gaps(
        path,
        ref_index=ref_index,
        symbol_index=symbol_index,
        examined_refs=collected,
        project_root=repo,
    )
    assert gaps.stale_symbol_ref == ["gone_symbol (claimed in pkg/term.py)"]
    assert gaps.advisory_stale_symbol_ref == []  # not duplicated as an advisory
    assert [c.result for c in collected if c.property == "symbol_resolves_in"] == [
        "stale_symbol_ref"
    ]
