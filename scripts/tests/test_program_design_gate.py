"""Program Design specificity gate (ENH-2852).

Promotes the proving assertions from ``scripts/tests/spike/program_design_specificity/``
onto the production module (``little_loops.issues.program_design``) and covers the
wiring into ``check_format_gaps()`` / ``ll-issues format-check``.

The gate is opt-in per project: absent ``.ll/program-design-cutover.json`` it is off
entirely (fail open), and issues whose timestamp is strictly earlier than the stamped
date are grandfathered.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- helpers

_VALID_SECTION = """
### Types

- `sha: str`
- `cutover_date: datetime.date`

### Signatures

- `grade_program_design(body: str, resolver: Resolver) -> DesignVerdict`
- `def read_cutover_stamp(root: Path) -> date | None`

### Call Path

`check_format_gaps` -> `grade_program_design` -> `git_grep_resolver`
"""

_PROSE_SECTION = """
### Types

We will introduce a new type to hold the result of the check.

### Signatures

There will be a function that grades the section and returns whether it passed.

### Call Path

The linter calls the grader, which calls the resolver (all inside the parser).
"""


def _clean_bug_body(*, program_design: str | None = _VALID_SECTION) -> str:
    """A structurally complete BUG issue body, optionally with a Program Design section."""
    from little_loops.issue_parser import check_format_gaps  # noqa: F401  (import guard)

    sections = [
        "---",
        "id: BUG-9500",
        "status: open",
        "discovered_date: 2026-07-20",
        "---",
        "",
        "# BUG-9500: Something broke",
        "",
        "## Summary",
        "The widget explodes when the input is empty.",
        "",
        "## Steps to Reproduce",
        "1. Open the widget\n2. Submit an empty form",
        "",
        "## Current Behavior",
        "It explodes.",
        "",
        "## Expected Behavior",
        "It should not break.",
        "",
        "## Actual Behavior",
        "It breaks loudly.",
        "",
        "## Impact",
        "- **Priority**: P3 - Minor annoyance for a rare input.",
        "",
        "## Status",
        "**Open** | Created: 2026-07-20 | Priority: P3",
    ]
    if program_design is not None:
        sections.insert(-3, "## Program Design")
        sections.insert(-3, program_design.strip())
        sections.insert(-3, "")
    return "\n".join(sections) + "\n"


def _init_repo(root: Path) -> None:
    """Initialize a real git repo so ``git grep`` anchor resolution can run."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)


def _commit_all(root: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=root, check=True)


def _make_project(
    tmp_path: Path,
    *,
    stamp_date: str | None = None,
    body: str | None = None,
    filename: str = "P3-BUG-9500-something-broke.md",
) -> Path:
    """Create a project tree with `.issues/bugs/<issue>` and optionally a cutover stamp.

    Returns the issue file path.
    """
    issues_dir = tmp_path / ".issues" / "bugs"
    issues_dir.mkdir(parents=True)
    issue_file = issues_dir / filename
    issue_file.write_text(body if body is not None else _clean_bug_body(), encoding="utf-8")
    if stamp_date is not None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (ll_dir / "program-design-cutover.json").write_text(
            json.dumps({"sha": "0" * 40, "date": stamp_date}), encoding="utf-8"
        )
    return issue_file


# ------------------------------------------------------------------ signature shape


class TestSignatureShape:
    """A signature-shaped line must be distinguishable from English prose."""

    def test_accepts_varied_real_signature_shapes(self) -> None:
        from little_loops.issues.program_design import parse_signature_lines

        body = "\n".join(
            [
                "- `def check_format_gaps(issue_path: Path) -> FormatGaps`",
                "`grade(body: str, resolver: Resolver) -> DesignVerdict`",
                "- `FallbackProvider.defines(symbol)`",
                "- `sha: str`",
                "- `entries: list[CodeRef]`",
                "async def sweep(root: Path) -> None",
                "- `resolve(x) -> dict[str, list[int]]`",
            ]
        )

        found = parse_signature_lines(body)

        assert len(found) == 7, found

    def test_accepts_nested_generic_return_types(self) -> None:
        """A flat `\\[[^\\]]*\\]` subscript stops at the inner bracket (spike finding)."""
        from little_loops.issues.program_design import parse_signature_lines

        assert parse_signature_lines("- `load() -> dict[str, list[int]]`")

    def test_rejects_prose_that_merely_contains_parentheses(self) -> None:
        from little_loops.issues.program_design import parse_signature_lines

        body = "\n".join(
            [
                "We will add a helper (probably in the parser) that grades the section.",
                "The call path: the linter reaches the grader through the CLI.",
                "It returns a verdict (specific or not) to the caller.",
            ]
        )

        assert parse_signature_lines(body) == []

    def test_split_top_level_respects_bracket_depth(self) -> None:
        from little_loops.issues.program_design import _split_top_level

        assert _split_top_level('a: Literal["x", "y"], b: dict[str, int]') == [
            'a: Literal["x", "y"]',
            "b: dict[str, int]",
        ]

    def test_split_top_level_empty_and_single(self) -> None:
        from little_loops.issues.program_design import _split_top_level

        assert _split_top_level("") == []
        assert _split_top_level("a: int") == ["a: int"]

    def test_accepts_keyword_only_and_positional_only_markers(self) -> None:
        from little_loops.issues.program_design import parse_signature_lines

        assert parse_signature_lines("- `foo(a: int, *, b: str) -> Bar`")
        assert parse_signature_lines("- `foo(a: int, /, b: str) -> Bar`")

    def test_accepts_trailing_description_after_signature(self) -> None:
        from little_loops.issues.program_design import parse_signature_lines

        assert parse_signature_lines("- `foo(a: int) -> Bar` — does a thing")
        assert parse_signature_lines("- `foo(a: int) -> Bar` -- does a thing")
        assert parse_signature_lines("- `foo(a: int) -> Bar`: does a thing")

    def test_accepts_comma_bearing_annotation_in_params(self) -> None:
        from little_loops.issues.program_design import parse_signature_lines

        assert parse_signature_lines('- `foo(a: Literal["x", "y"]) -> Bar`')
        assert parse_signature_lines("- `foo(a: dict[str, int]) -> Bar`")

    def test_reproduction_lines_from_bug_2960(self) -> None:
        from little_loops.issues.program_design import parse_signature_lines

        for line in (
            "- `foo(a: int) -> Bar`",
            "- `foo(a: int) -> Bar` — does a thing",
            '- `foo(a: Literal["x", "y"]) -> Bar`',
            "- `foo(a: int, *, b: str) -> Bar`",
        ):
            assert parse_signature_lines(line), line


# ------------------------------------------------------------------------- grading


class TestGrading:
    """`grade_program_design()` classifies a section body as specific or not."""

    def test_missing_or_empty_section_is_not_specific(self) -> None:
        from little_loops.issues.program_design import grade_program_design

        for body in ("", "   \n\n  "):
            verdict = grade_program_design(body, lambda _s: True)
            assert verdict.is_specific is False
            assert verdict.reasons

    def test_prose_only_section_is_not_specific(self) -> None:
        from little_loops.issues.program_design import grade_program_design

        verdict = grade_program_design(_PROSE_SECTION, lambda _s: True)

        assert verdict.is_specific is False
        assert verdict.signatures == []

    def test_valid_section_is_specific(self) -> None:
        from little_loops.issues.program_design import grade_program_design

        verdict = grade_program_design(_VALID_SECTION, lambda s: s == "check_format_gaps")

        assert verdict.is_specific is True
        assert verdict.signatures
        assert "check_format_gaps" in verdict.resolved

    def test_unresolvable_call_path_anchors_fail(self) -> None:
        """Every anchor unresolvable means the design is not grounded in the repo."""
        from little_loops.issues.program_design import grade_program_design

        verdict = grade_program_design(_VALID_SECTION, lambda _s: False)

        assert verdict.is_specific is False
        assert verdict.resolved == []
        assert verdict.anchors

    def test_new_identifiers_need_only_be_shape_valid(self) -> None:
        """New signatures never need to resolve — only call-path anchors do."""
        from little_loops.issues.program_design import grade_program_design

        body = """
### Signatures

- `brand_new_never_defined_symbol(x: int) -> Widget`

### Call Path

`check_format_gaps` -> `brand_new_never_defined_symbol`
"""
        verdict = grade_program_design(body, lambda s: s == "check_format_gaps")

        assert verdict.is_specific is True

    def test_verdict_is_indifferent_to_new_identifier_resolution(self) -> None:
        """AC-5: a new identifier that *happens* to resolve must not flip the verdict.

        The same body is graded twice — once with a resolver that knows only the
        anchor, once with an all-resolving resolver. Specificity must not change.
        """
        from little_loops.issues.program_design import grade_program_design

        body = """
### Signatures

- `grade_program_design(body: str, resolver: Resolver) -> DesignVerdict`

### Call Path

`check_format_gaps` -> `grade_program_design`
"""
        anchor_only = grade_program_design(body, lambda s: s == "check_format_gaps")
        all_resolve = grade_program_design(body, lambda _s: True)
        none_but_anchor = grade_program_design(
            body, lambda s: s in {"check_format_gaps", "grade_program_design"}
        )

        assert anchor_only.is_specific is True
        assert all_resolve.is_specific is True
        assert none_but_anchor.is_specific is True

    def test_deviations_subsection_is_inert(self) -> None:
        """ENH-2871's appended `Deviations` note must not feed specificity either way."""
        from little_loops.issues.program_design import grade_program_design

        deviations_only = """
### Types

Nothing concrete here, just prose about the approach.

### Signatures

Prose describing what the function will roughly do.

### Call Path

Described in words with no identifiers at all.

### Deviations

- `actually_implemented(x: int) -> None` replaced the planned shape.
- `check_format_gaps` -> `actually_implemented`
"""
        verdict = grade_program_design(deviations_only, lambda _s: True)

        assert verdict.is_specific is False, "Deviations content must not rescue a prose section"

        with_deviations = _VALID_SECTION + "\n### Deviations\n\n- Widened the return type.\n"
        still_specific = grade_program_design(with_deviations, lambda s: s == "check_format_gaps")
        assert still_specific.is_specific is True, "Deviations must not break a valid section"

    def test_nonspecific_reason_names_only_accepted_headings(self) -> None:
        """BUG-3071: every heading named in the message is one `_evidence_body` retains.

        The old message hardcoded a combined `Types/Signatures` heading that
        `DESIGN_SUBSECTIONS` does not contain, so following it produced the one
        heading guaranteed to fail the gate. Assert the reason text is built from
        `DESIGN_SUBSECTIONS` itself (title-cased) plus the documented preamble
        exception, so the two can never drift apart again.
        """
        from little_loops.issues.program_design import DESIGN_SUBSECTIONS, grade_program_design

        verdict = grade_program_design("Just prose, no signatures here.", lambda _s: True)

        assert verdict.is_specific is False
        [reason] = [r for r in verdict.reasons if r.startswith("no signature-shaped line")]

        assert "Types/Signatures" not in reason
        named_headings = {
            token.strip().lower()
            for token in reason.split(" found in ", 1)[1].split(",")
            if token.strip().lower() not in ("or the section preamble", "the section preamble")
        }
        named_headings = {h.removeprefix("or ").strip() for h in named_headings}
        assert named_headings == set(DESIGN_SUBSECTIONS), (
            f"reason names headings outside DESIGN_SUBSECTIONS: "
            f"{named_headings.symmetric_difference(set(DESIGN_SUBSECTIONS))}"
        )


class TestRealRepoResolution:
    """`git_grep_resolver` resolves real symbols in a real repo."""

    def test_real_repo_anchors_resolve_via_git_grep(self, tmp_path: Path) -> None:
        from little_loops.issues.program_design import git_grep_resolver

        _init_repo(tmp_path)
        (tmp_path / "mod.py").write_text(
            "def check_format_gaps(path):\n    return None\n\n\nclass FormatGaps:\n    pass\n",
            encoding="utf-8",
        )
        _commit_all(tmp_path)

        assert git_grep_resolver("check_format_gaps", tmp_path) is True
        assert git_grep_resolver("FormatGaps", tmp_path) is True
        assert git_grep_resolver("never_defined_anywhere", tmp_path) is False


class TestFindProjectRoot:
    """`find_project_root` prefers a `.git` ancestor over the nearest `.ll` (ENH-2924)."""

    def test_stray_ll_in_subdirectory_still_resolves_to_repo_root(self, tmp_path: Path) -> None:
        """(b) A stray `.ll` below the repo root is skipped in favor of the repo root."""
        from little_loops.paths import find_project_root

        _init_repo(tmp_path)
        (tmp_path / ".ll").mkdir()
        sub = tmp_path / "scripts" / "little_loops"
        sub.mkdir(parents=True)
        (sub / ".ll").mkdir()

        assert find_project_root(sub) == tmp_path

    def test_non_git_project_keeps_nearest_ll_semantics(self, tmp_path: Path) -> None:
        """(c) With no `.git` anywhere, the nearest `.ll` ancestor still wins."""
        from little_loops.paths import find_project_root

        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        (sub / ".ll").mkdir()

        assert find_project_root(sub) == sub

    def test_worktree_git_file_wins_over_stray_ll_below_it(self, tmp_path: Path) -> None:
        """(d) A worktree's `.git` *file* still beats a stray `.ll` below it."""
        from little_loops.paths import find_project_root

        (tmp_path / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n", encoding="utf-8")
        (tmp_path / ".ll").mkdir()
        sub = tmp_path / "scripts"
        sub.mkdir()
        (sub / ".ll").mkdir()

        assert find_project_root(sub) == tmp_path

    def test_monorepo_subproject_resolves_to_ll_only_subdir(self, tmp_path: Path) -> None:
        """(e) `.git` only at the repo root, `.ll` only at a subproject, resolves there."""
        from little_loops.paths import find_project_root

        _init_repo(tmp_path)
        sub = tmp_path / "packages" / "foo"
        sub.mkdir(parents=True)
        (sub / ".ll").mkdir()

        assert find_project_root(sub) == sub

    def test_ll_above_repo_boundary_is_never_returned(self, tmp_path: Path) -> None:
        """(f) A `.ll` above the repo root (e.g. `~/.ll`) is out of bounds — returns None."""
        from little_loops.paths import find_project_root

        (tmp_path / ".ll").mkdir()
        repo = tmp_path / "project"
        repo.mkdir()
        _init_repo(repo)

        assert find_project_root(repo) is None


class TestResolveLlDir:
    """`resolve_ll_dir` (ENH-2927): sole authority for creating `.ll/` outside `ll-init`."""

    def test_pure_lookup_no_mkdir(self, tmp_path: Path) -> None:
        """create=False (the default) never creates .ll/, even when no root resolves."""
        from little_loops.paths import resolve_ll_dir

        probe = tmp_path / "probe"
        probe.mkdir()
        result = resolve_ll_dir(probe)
        assert result is None
        assert not (probe / ".ll").exists()

    def test_returns_none_when_no_root_resolves(self, tmp_path: Path) -> None:
        from little_loops.paths import resolve_ll_dir

        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        assert resolve_ll_dir(sub) is None

    def test_finds_existing_ll_dir_at_ancestor(self, tmp_path: Path) -> None:
        """When an ancestor already has .ll/, resolve_ll_dir returns it without creating anything."""
        from little_loops.paths import resolve_ll_dir

        _init_repo(tmp_path)
        (tmp_path / ".ll").mkdir()
        sub = tmp_path / "scripts" / "little_loops"
        sub.mkdir(parents=True)

        result = resolve_ll_dir(sub)
        assert result == tmp_path / ".ll"
        # Pure lookup: no stray .ll/ created at the subdirectory.
        assert not (sub / ".ll").exists()

    def test_create_true_creates_ll_dir_at_resolved_root(self, tmp_path: Path) -> None:
        """create=True materializes .ll/ at the resolved root, not at start."""
        from little_loops.paths import resolve_ll_dir

        _init_repo(tmp_path)
        (tmp_path / ".ll").mkdir()
        sub = tmp_path / "scripts"
        sub.mkdir()

        result = resolve_ll_dir(sub, create=True)
        assert result == tmp_path / ".ll"
        assert (tmp_path / ".ll").is_dir()
        assert not (sub / ".ll").exists()

    def test_create_true_is_idempotent_on_existing_ll_dir(self, tmp_path: Path) -> None:
        from little_loops.paths import resolve_ll_dir

        _init_repo(tmp_path)
        (tmp_path / ".ll").mkdir()

        result = resolve_ll_dir(tmp_path, create=True)
        assert result == tmp_path / ".ll"
        assert (tmp_path / ".ll").is_dir()

    def test_create_true_does_not_invent_a_root_when_none_resolves(self, tmp_path: Path) -> None:
        """create=True still returns None (and creates nothing) when no root resolves at all."""
        from little_loops.paths import resolve_ll_dir

        probe = tmp_path / "no-project-anywhere"
        probe.mkdir()
        result = resolve_ll_dir(probe, create=True)
        assert result is None
        assert not (probe / ".ll").exists()

    def test_default_start_is_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from little_loops.paths import resolve_ll_dir

        _init_repo(tmp_path)
        (tmp_path / ".ll").mkdir()
        monkeypatch.chdir(tmp_path)

        assert resolve_ll_dir() == tmp_path / ".ll"


# --------------------------------------------------------------------- cutover stamp


class TestCutoverStamp:
    """`.ll/program-design-cutover.json` is the single source of truth for the cutoff."""

    def test_reads_sha_and_date(self, tmp_path: Path) -> None:
        from little_loops.issues.program_design import read_cutover_stamp

        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "program-design-cutover.json").write_text(
            json.dumps({"sha": "a" * 40, "date": "2026-07-28"}), encoding="utf-8"
        )

        stamp = read_cutover_stamp(tmp_path)

        assert stamp is not None
        assert stamp.isoformat() == "2026-07-28"

    def test_absent_stamp_returns_none(self, tmp_path: Path) -> None:
        from little_loops.issues.program_design import read_cutover_stamp

        assert read_cutover_stamp(tmp_path) is None

    @pytest.mark.parametrize(
        "payload",
        ['{"sha": "abc"}', "not json at all", '{"sha": "abc", "date": "not-a-date"}', "{}"],
    )
    def test_unparseable_stamp_returns_none(self, tmp_path: Path, payload: str) -> None:
        from little_loops.issues.program_design import read_cutover_stamp

        (tmp_path / ".ll").mkdir()
        (tmp_path / ".ll" / "program-design-cutover.json").write_text(payload, encoding="utf-8")

        assert read_cutover_stamp(tmp_path) is None


class TestIssueTimestamp:
    """The refine timestamp from the Session Log takes precedence over discovered_date."""

    def test_discovered_date_used_when_no_session_log(self) -> None:
        from little_loops.issues.program_design import issue_design_timestamp

        content = "---\nid: BUG-1\ndiscovered_date: 2026-07-20\n---\n\n# BUG-1\n"

        stamp = issue_design_timestamp(content)

        assert stamp is not None and stamp.isoformat() == "2026-07-20"

    def test_refine_entry_takes_precedence(self) -> None:
        from little_loops.issues.program_design import issue_design_timestamp

        content = (
            "---\nid: BUG-1\ndiscovered_date: 2026-07-20\n---\n\n"
            "## Session Log\n"
            "- `/ll:refine-issue` - 2026-08-02T10:00:00 - `a.jsonl`\n"
            "- `/ll:refine-issue` - 2026-07-21T10:00:00 - `b.jsonl`\n"
        )

        stamp = issue_design_timestamp(content)

        assert stamp is not None and stamp.isoformat() == "2026-08-02", "latest refine wins"

    def test_unparseable_refine_entry_falls_back_to_discovered_date(self) -> None:
        from little_loops.issues.program_design import issue_design_timestamp

        content = (
            "---\nid: BUG-1\ndiscovered_date: 2026-07-20\n---\n\n"
            "## Session Log\n"
            "- `/ll:refine-issue` - whenever - `a.jsonl`\n"
        )

        stamp = issue_design_timestamp(content)

        assert stamp is not None and stamp.isoformat() == "2026-07-20"


# ----------------------------------------------------------- check_format_gaps wiring


class TestFormatGapsWiring:
    """The gate reaches every `check_format_gaps()` consumer, grandfathering included."""

    def test_unstamped_project_reports_no_program_design_gap(self, tmp_path: Path) -> None:
        """Fail open: no stamp means the gate is off for all issues (AC)."""
        from little_loops.issue_parser import check_format_gaps

        issue_file = _make_project(tmp_path, body=_clean_bug_body(program_design=None))

        gaps = check_format_gaps(issue_file)

        assert "Program Design" not in gaps.missing
        assert gaps.program_design_nonspecific == []
        assert gaps.has_gaps is False

    def test_grandfathered_issue_reports_no_program_design_gap(self, tmp_path: Path) -> None:
        """An issue strictly earlier than the stamp date is exempt (AC)."""
        from little_loops.issue_parser import check_format_gaps

        issue_file = _make_project(
            tmp_path, stamp_date="2026-07-28", body=_clean_bug_body(program_design=None)
        )

        gaps = check_format_gaps(issue_file)

        assert "Program Design" not in gaps.missing
        assert gaps.program_design_nonspecific == []
        assert gaps.has_gaps is False

    def test_same_day_issue_is_not_grandfathered(self, tmp_path: Path) -> None:
        """Boundary: exemption is strictly-earlier-than, so same-day issues are gated."""
        from little_loops.issue_parser import check_format_gaps

        issue_file = _make_project(
            tmp_path, stamp_date="2026-07-20", body=_clean_bug_body(program_design=None)
        )

        gaps = check_format_gaps(issue_file)

        assert "Program Design" in gaps.missing

    def test_post_cutover_missing_section_reports_missing(self, tmp_path: Path) -> None:
        from little_loops.issue_parser import check_format_gaps

        issue_file = _make_project(
            tmp_path, stamp_date="2026-07-01", body=_clean_bug_body(program_design=None)
        )

        gaps = check_format_gaps(issue_file)

        assert gaps.missing == ["Program Design"]
        assert gaps.program_design_nonspecific == []

    def test_post_cutover_prose_section_reports_nonspecific(self, tmp_path: Path) -> None:
        from little_loops.issue_parser import check_format_gaps

        issue_file = _make_project(
            tmp_path, stamp_date="2026-07-01", body=_clean_bug_body(program_design=_PROSE_SECTION)
        )

        gaps = check_format_gaps(issue_file)

        assert gaps.missing == []
        assert gaps.program_design_nonspecific
        assert gaps.has_gaps is True

    def test_post_cutover_valid_section_reports_no_gap(self, tmp_path: Path) -> None:
        """A real signature plus a repo-resolvable call-path anchor passes."""
        from little_loops.issue_parser import check_format_gaps

        issue_file = _make_project(
            tmp_path, stamp_date="2026-07-01", body=_clean_bug_body(program_design=_VALID_SECTION)
        )
        _init_repo(tmp_path)
        (tmp_path / "mod.py").write_text(
            "def check_format_gaps(path):\n    return None\n", encoding="utf-8"
        )
        _commit_all(tmp_path)

        gaps = check_format_gaps(issue_file)

        assert gaps.program_design_nonspecific == []
        assert gaps.has_gaps is False

    def test_stray_ll_ancestor_of_issue_does_not_disable_the_gate(self, tmp_path: Path) -> None:
        """(a) regression: a stray `.ll` under `.issues/` must not shadow the stamped root."""
        from little_loops.issue_parser import check_format_gaps
        from little_loops.issues.program_design import program_design_gate_active

        issue_file = _make_project(
            tmp_path, stamp_date="2026-07-01", body=_clean_bug_body(program_design=None)
        )
        _init_repo(tmp_path)
        _commit_all(tmp_path)
        (tmp_path / ".issues" / ".ll").mkdir()

        content = issue_file.read_text(encoding="utf-8")
        assert program_design_gate_active(issue_file, content) is True

        gaps = check_format_gaps(issue_file)
        assert gaps.missing == ["Program Design"]

    def test_escape_hatch_skips_the_gate(self, tmp_path: Path) -> None:
        """`program_design_not_applicable: true` fully skips the section (AC)."""
        from little_loops.issue_parser import check_format_gaps

        body = _clean_bug_body(program_design=None).replace(
            "status: open", "status: open\nprogram_design_not_applicable: true"
        )
        issue_file = _make_project(tmp_path, stamp_date="2026-07-01", body=body)

        gaps = check_format_gaps(issue_file)

        assert "Program Design" not in gaps.missing
        assert gaps.program_design_nonspecific == []

    def test_empty_section_is_not_double_reported(self, tmp_path: Path) -> None:
        """An empty section is an `empty` gap, not additionally a specificity gap."""
        from little_loops.issue_parser import check_format_gaps

        issue_file = _make_project(
            tmp_path, stamp_date="2026-07-01", body=_clean_bug_body(program_design="")
        )

        gaps = check_format_gaps(issue_file)

        assert gaps.empty == ["Program Design"] or gaps.missing == ["Program Design"]
        assert gaps.program_design_nonspecific == []

    def test_gap_field_is_serialized(self, tmp_path: Path) -> None:
        from little_loops.issue_parser import FormatGaps

        gaps = FormatGaps(program_design_nonspecific=["Program Design: no signature"])

        assert gaps.has_gaps is True
        assert gaps.to_dict()["program_design_nonspecific"] == ["Program Design: no signature"]


class TestFindProjectRootReexport:
    """`find_project_root` moved to `little_loops.paths`; the old import path stays live."""

    def test_reexported_from_issues_program_design(self) -> None:
        from little_loops.issues.program_design import find_project_root as old
        from little_loops.paths import find_project_root as new

        assert old is new
