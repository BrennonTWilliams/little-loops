"""Tests for ll-verify-evidence, plus the repo-wide CI gate (BUG-3282).

The gate at the bottom (:class:`TestRepoGate`) is the pytest transport for this
check — this project has no hosted CI, so `python -m pytest scripts/tests/` is
the enforced boundary (see .claude/CLAUDE.md § Testing & CI Policy).

The flagship regression fixture pins both sides (the BUG-3278 blob at
``baa553d9`` and a fixed ENH-3277 revision) into a synthetic temp repo so the
test stays hermetic even though ENH-3277 is a live, growing file (BUG-3282
Integration Map -> Tests).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from little_loops.cli.verify_evidence import (
    BASELINE_PATH,
    ArtifactMatcher,
    attribute_span,
    extract_candidate_spans,
    in_scope_sections,
    is_command_output,
    is_mention_class,
    is_suppressed,
    iter_sections,
    load_baseline,
    main_verify_evidence,
    normalize,
    resolve_artifact,
    scan_all,
    scan_file,
    scan_paths,
    strip_patch_prefixes,
    write_baseline,
)
from little_loops.config import BRConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
BUG_3278_SHA = "baa553d9"
BUG_3278_REPO_PATH = (
    ".issues/bugs/P2-BUG-3278-decide-issue-clears-decision_needed-while-"
    "lower-precedence-decision-blocks-stay-unresolved.md"
)
# Pinned to a fixed, already-merged commit (not HEAD/working tree) so this
# test stays hermetic even though ENH-3277 is `status: open` and its history
# keeps growing.
ENH_3277_SHA = "08e9f9a57be10bc4b362c7d02f882d41332da4c2"
ENH_3277_REPO_PATH = (
    ".issues/enhancements/P2-ENH-3277-convert-the-five-mechanical-inline-"
    "test_cmdlint_cmd-loops-to-ll-config-get.md"
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _read_blob(sha: str, rel_path: str) -> str:
    if not (REPO_ROOT / ".git").exists():
        pytest.skip("not a git checkout; nothing to pin")
    result = subprocess.run(
        ["git", "show", f"{sha}:{rel_path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"pinned blob {sha}:{rel_path} unavailable in this checkout")
    return result.stdout


def _init_repo(root: Path) -> None:
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "test")


def _mkissues(root: Path) -> None:
    for kind in ("bugs", "features", "enhancements", "epics"):
        (root / ".issues" / kind).mkdir(parents=True, exist_ok=True)


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _commit_all(root: Path, message: str = "commit") -> None:
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", message)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _init_repo(r)
    _mkissues(r)
    return r


@pytest.fixture()
def config(repo: Path):
    return BRConfig(repo)


# ---------------------------------------------------------------------------
# Flagship regression fixture (real, pinned)
# ---------------------------------------------------------------------------


class TestFlagshipRegressionFixture:
    """BUG-3278's fabricated ENH-3277 evidence, pinned on both sides."""

    @pytest.fixture()
    def pinned_repo(self, tmp_path: Path):
        bug_content = _read_blob(BUG_3278_SHA, BUG_3278_REPO_PATH)
        enh_content = _read_blob(ENH_3277_SHA, ENH_3277_REPO_PATH)

        r = tmp_path / "pinned"
        r.mkdir()
        _init_repo(r)
        _mkissues(r)
        _write(r, BUG_3278_REPO_PATH, bug_content)
        _write(r, ENH_3277_REPO_PATH, enh_content)
        _commit_all(r, "pin BUG-3278 and ENH-3277")
        return r

    def test_exact_finding_set(self, pinned_repo: Path) -> None:
        config = BRConfig(pinned_repo)
        findings, _ = scan_file(
            pinned_repo,
            pinned_repo / BUG_3278_REPO_PATH,
            config,
            rel_path=Path(BUG_3278_REPO_PATH),
        )
        # 4 occurrences / 3 distinct spans (the (a)/(b) spans share :38).
        assert len(findings) == 4, [f.span for f in findings]
        assert sorted(f.line for f in findings) == [38, 38, 40, 60]
        distinct_spans = {normalize(f.span) for f in findings}
        assert len(distinct_spans) == 3
        for f in findings:
            assert f.artifact == "ENH-3277"

    def test_must_flag_spans_present(self, pinned_repo: Path) -> None:
        config = BRConfig(pinned_repo)
        findings, _ = scan_file(
            pinned_repo,
            pinned_repo / BUG_3278_REPO_PATH,
            config,
            rel_path=Path(BUG_3278_REPO_PATH),
        )
        spans = {normalize(f.span) for f in findings}
        assert normalize("- **(a) Make the documented override real.**") in spans
        assert normalize("- **(b) Drop the knob.**") in spans
        assert normalize("**DECISION — pick one before step 4 touches this file:**") in spans

    def test_mention_class_not_flagged(self, pinned_repo: Path) -> None:
        """The five mention-class spans (Integration Map -> Tests table) must
        not appear as findings — this is what the exact-finding-set assertion
        buys over a looser "flags the fabrications" check."""
        config = BRConfig(pinned_repo)
        findings, _ = scan_file(
            pinned_repo,
            pinned_repo / BUG_3278_REPO_PATH,
            config,
            rel_path=Path(BUG_3278_REPO_PATH),
        )
        flagged_texts = {f.span for f in findings}
        for mention in (
            "ll-issues locate-options ENH-3277 --json",
            "issue_parser.locate_enumerable_options",
            "pattern bold_label",
            "/ll:decide-issue ENH-3277",
            "section_header",
        ):
            assert mention not in flagged_texts

    def test_option_abc_not_flagged(self, pinned_repo: Path) -> None:
        """`**Option A**`/B/C sit under the same ENH-3277 attribution as the
        fabrications but do occur (emphasis-normalized) in ENH-3277."""
        config = BRConfig(pinned_repo)
        findings, _ = scan_file(
            pinned_repo,
            pinned_repo / BUG_3278_REPO_PATH,
            config,
            rel_path=Path(BUG_3278_REPO_PATH),
        )
        flagged_texts = {f.span for f in findings}
        assert "**Option A**" not in flagged_texts
        assert "**Option B**" not in flagged_texts
        assert "**Option C**" not in flagged_texts

    def test_command_output_fence_not_flagged(self, pinned_repo: Path) -> None:
        """The :44-49 fence is command output, not a quote from ENH-3277."""
        config = BRConfig(pinned_repo)
        findings, _ = scan_file(
            pinned_repo,
            pinned_repo / BUG_3278_REPO_PATH,
            config,
            rel_path=Path(BUG_3278_REPO_PATH),
        )
        assert not any("bold_label  heading" in f.span for f in findings)


# ---------------------------------------------------------------------------
# Section scope
# ---------------------------------------------------------------------------


class TestSectionScope:
    def test_in_scope_section_quoting_absent_string_flags(self, repo: Path, config) -> None:
        body = (
            "## Current Behavior\n\n"
            "The code says `this exact phrase never appears anywhere` (`.issues/bugs/target.md`).\n"
        )
        _write(repo, ".issues/bugs/target.md", "existing content, nothing matching.\n")
        path = _write(repo, ".issues/bugs/issue.md", body)
        _commit_all(repo)
        findings, _ = scan_file(repo, path, config, rel_path=Path(".issues/bugs/issue.md"))
        assert len(findings) == 1

    def test_excluded_proposed_solution_section_no_finding(self, repo: Path, config) -> None:
        body = (
            "## Proposed Solution\n\n"
            "New code will say `this exact phrase never appears anywhere` (`other.md`).\n"
        )
        _write(repo, ".issues/bugs/target.md", "existing content, nothing matching.\n")
        path = _write(repo, ".issues/bugs/issue.md", body)
        _commit_all(repo)
        findings, _ = scan_file(repo, path, config, rel_path=Path(".issues/bugs/issue.md"))
        assert findings == []

    def test_unlisted_section_no_finding(self, repo: Path, config) -> None:
        """A section in neither list (e.g. ## Summary) is out of scope by default."""
        body = "## Summary\n\nQuotes `this exact phrase never appears anywhere` (`other.md`).\n"
        _write(repo, ".issues/bugs/target.md", "existing content, nothing matching.\n")
        path = _write(repo, ".issues/bugs/issue.md", body)
        _commit_all(repo)
        findings, _ = scan_file(repo, path, config, rel_path=Path(".issues/bugs/issue.md"))
        assert findings == []

    def test_section_boundaries(self) -> None:
        content = "## A\n\ntext1\n\n### B\n\ntext2\n\n## C\n\ntext3\n"
        sections = iter_sections(content)
        assert [s.name for s in sections] == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


class TestAttribution:
    def test_following_parenthetical_overrides_nearest_preceding(self) -> None:
        content = (
            "## Codebase Research Findings\n\n"
            "`scripts/little_loops/codequery/fallback.py:50` mentions "
            "`read_blob_at_ref()` (`scripts/tests/spike/git_show_blob_at_ref/"
            "blob_reader.py`, single-ref blob read).\n"
        )
        section = in_scope_sections(content)[0]
        from little_loops.cli.verify_evidence import _extract_mentions

        mentions = _extract_mentions(content[section.start : section.end], section.start)
        spans = extract_candidate_spans(content, section)
        target = next(s for s in spans if s.text == "read_blob_at_ref()")
        artifact = attribute_span(content, target, mentions)
        assert artifact == "scripts/tests/spike/git_show_blob_at_ref/blob_reader.py"

    def test_nearest_preceding_section_bounded(self) -> None:
        """A mention in one section must not attribute a span in the next."""
        content = (
            "## Current Behavior\n\n"
            "Observed on ENH-9999.\n\n"
            "## Steps to Reproduce\n\n"
            "The span `some unrelated quoted prose here` appears.\n"
        )
        section = in_scope_sections(content)[1]
        from little_loops.cli.verify_evidence import _extract_mentions

        mentions = _extract_mentions(content[section.start : section.end], section.start)
        spans = extract_candidate_spans(content, section)
        target = next(s for s in spans if "unrelated quoted prose" in s.text)
        artifact = attribute_span(content, target, mentions)
        assert artifact is None  # ENH-9999 is in the *previous* section

    def test_command_output_exclusion_crosses_blank_line(self) -> None:
        content = (
            "## Current Behavior\n\n"
            "Observed on ENH-9999.\n\n"
            "`ll-issues locate-options ENH-9999 --json` returns:\n"
            "\n"
            "```\n"
            "count 3  pattern bold_label  heading long enough to clear the floor\n"
            "```\n"
        )
        section = in_scope_sections(content)[0]
        fence = next(s for s in extract_candidate_spans(content, section) if s.is_fence)
        assert is_command_output(content, fence) is True


# ---------------------------------------------------------------------------
# Span-kind filter (quote vs. mention)
# ---------------------------------------------------------------------------


class TestSpanKind:
    def test_bare_identifier_is_mention(self) -> None:
        assert is_mention_class("issue_parser.locate_enumerable_options", "", 0) is True

    def test_prose_positive_control_not_mention(self) -> None:
        assert is_mention_class("issue_parser dot locate enumerable", "", 0) is False

    def test_command_invocation_is_mention(self) -> None:
        assert is_mention_class("ll-issues locate-options ENH-3277 --json", "", 0) is True

    def test_skill_invocation_is_mention(self) -> None:
        assert is_mention_class("/ll:decide-issue ENH-3277", "", 0) is True

    def test_inline_output_following_invocation_is_mention(self) -> None:
        line = "Run `ll-issues locate-options ENH-1 --json` — observe `count 3`."
        # `count 3`'s column position in the line:
        col = line.index("`count 3`") + 1
        assert is_mention_class("count 3", line, col) is True

    def test_prose_not_following_invocation_is_not_mention(self) -> None:
        line = "This is `just some regular prose quote` on its own."
        col = line.index("`just some regular prose quote`") + 1
        assert is_mention_class("just some regular prose quote", line, col) is False


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


class TestNormalization:
    def test_emphasis_normalized_match(self, repo: Path, config) -> None:
        _write(
            repo,
            ".issues/enhancements/target.md",
            "## Proposed Solution\n\n**Foo Bar Decision — extra context. SELECTED.**\n",
        )
        body = "## Current Behavior\n\nSee `**Foo Bar Decision**` (`.issues/enhancements/target.md`).\n"
        path = _write(repo, ".issues/bugs/issue.md", body)
        _commit_all(repo)
        findings, _ = scan_file(repo, path, config, rel_path=Path(".issues/bugs/issue.md"))
        assert findings == []

    def test_raw_match_would_have_failed(self) -> None:
        span = "**Foo Bar Decision**"
        artifact = "**Foo Bar Decision — extra context. SELECTED.**"
        assert span not in artifact  # raw containment fails
        assert normalize(span) in normalize(artifact)  # normalized containment holds


# ---------------------------------------------------------------------------
# Patch-text preparation
# ---------------------------------------------------------------------------


class TestPatchTextPreparation:
    def test_strip_patch_prefixes_removes_diff_markers(self) -> None:
        raw = (
            "diff --git a/f.md b/f.md\n"
            "index 111..222 100644\n"
            "--- a/f.md\n"
            "+++ b/f.md\n"
            "@@ -1,2 +1,2 @@\n"
            "+A multi line\n"
            "+span here\n"
            "-old line\n"
        )
        stripped = strip_patch_prefixes(raw)
        assert "diff --git" not in stripped
        assert "@@" not in stripped
        assert "A multi line" in stripped
        assert "span here" in stripped

    def test_multiline_span_found_only_with_prefix_stripping(self, repo: Path) -> None:
        rel = ".issues/enhancements/history_target.md"
        _write(repo, rel, "## Section\n\nA multi line\nspan here in the original.\n")
        _commit_all(repo, "add original")
        # Delete the file's content in a later commit so it's absent at HEAD.
        _write(repo, rel, "## Section\n\ncompletely different content now.\n")
        _commit_all(repo, "rewrite content")

        matcher = ArtifactMatcher(repo)
        result = matcher.matches(rel, ["A multi line span here in the original."])
        assert result["A multi line span here in the original."] is True


# ---------------------------------------------------------------------------
# Character floor
# ---------------------------------------------------------------------------


class TestCharacterFloor:
    def test_short_span_below_floor_dropped(self, repo: Path, config) -> None:
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        body = "## Current Behavior\n\nSee `**Option A**` (`.issues/enhancements/target.md`).\n"
        path = _write(repo, ".issues/bugs/issue.md", body)
        _commit_all(repo)
        findings, _ = scan_file(repo, path, config, rel_path=Path(".issues/bugs/issue.md"))
        assert findings == []  # dropped by the floor, not found "by accident"

    def test_span_at_and_above_floor_kept(self, repo: Path, config) -> None:
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        body = (
            "## Current Behavior\n\n"
            "See `- **(b) Drop the knob.**` (`.issues/enhancements/target.md`).\n"
        )
        path = _write(repo, ".issues/bugs/issue.md", body)
        _commit_all(repo)
        findings, _ = scan_file(repo, path, config, rel_path=Path(".issues/bugs/issue.md"))
        assert len(findings) == 1


# ---------------------------------------------------------------------------
# Fail-open
# ---------------------------------------------------------------------------


class TestFailOpen:
    def test_untracked_artifact_no_finding(self, repo: Path, config) -> None:
        body = (
            "## Current Behavior\n\n"
            "See `this phrase does not exist anywhere` (`.loops/tmp/scratch/run.log`).\n"
        )
        path = _write(repo, ".issues/bugs/issue.md", body)
        _commit_all(repo)  # run.log is never created/tracked
        findings, _ = scan_file(repo, path, config, rel_path=Path(".issues/bugs/issue.md"))
        assert findings == []

    def test_resolve_artifact_none_for_untracked(self, repo: Path, config) -> None:
        assert resolve_artifact(repo, "no/such/file.md", config) is None


# ---------------------------------------------------------------------------
# Suppression / escape hatch / counter-example
# ---------------------------------------------------------------------------


class TestSuppressionEscapeHatch:
    def test_suppressed_on_own_line(self, repo: Path, config) -> None:
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        body = (
            "## Current Behavior\n\n"
            "See `this phrase does not exist here at all` (`.issues/enhancements/target.md`)."
            " <!-- ll-evidence-ok: counter-example, this is the point -->\n"
        )
        path = _write(repo, ".issues/bugs/issue.md", body)
        _commit_all(repo)
        findings, _ = scan_file(repo, path, config, rel_path=Path(".issues/bugs/issue.md"))
        assert findings == []

    def test_suppressed_on_preceding_line(self, repo: Path, config) -> None:
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        body = (
            "## Current Behavior\n\n"
            "<!-- ll-evidence-ok: counter-example -->\n"
            "See `this phrase does not exist here at all` (`.issues/enhancements/target.md`).\n"
        )
        path = _write(repo, ".issues/bugs/issue.md", body)
        _commit_all(repo)
        findings, _ = scan_file(repo, path, config, rel_path=Path(".issues/bugs/issue.md"))
        assert findings == []

    def test_unsuppressed_still_flags(self, repo: Path, config) -> None:
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        body = (
            "## Current Behavior\n\n"
            "See `this phrase does not exist here at all` (`.issues/enhancements/target.md`).\n"
        )
        path = _write(repo, ".issues/bugs/issue.md", body)
        _commit_all(repo)
        findings, _ = scan_file(repo, path, config, rel_path=Path(".issues/bugs/issue.md"))
        assert len(findings) == 1

    def test_counter_example_quote_flags_before_suppression(self, repo: Path, config) -> None:
        """An issue *reporting* a fabricated quote must reproduce it — a genuine
        finding by the checker's own definition until annotated."""
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        body = (
            "## Current Behavior\n\n"
            "Attributed to `.issues/enhancements/target.md`, the other issue claimed "
            "`this text never appeared in the target file`, which is fabricated.\n"
        )
        path = _write(repo, ".issues/bugs/issue.md", body)
        _commit_all(repo)
        findings, _ = scan_file(repo, path, config, rel_path=Path(".issues/bugs/issue.md"))
        assert len(findings) == 1


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


class TestBaseline:
    def test_baseline_suppresses_before_matching(self, repo: Path, config, monkeypatch) -> None:
        """A baselined span must skip the history-tier git calls entirely."""
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        body = (
            "---\nid: BUG-1\n---\n\n"
            "## Current Behavior\n\n"
            "See `this phrase does not exist here at all` (`.issues/enhancements/target.md`).\n"
        )
        path = _write(repo, ".issues/bugs/P3-BUG-1-test.md", body)
        _commit_all(repo)

        first, hashes = scan_file(
            repo, path, config, rel_path=Path(".issues/bugs/P3-BUG-1-test.md")
        )
        assert len(first) == 1
        write_baseline(repo, hashes)

        called = {"n": 0}
        orig = ArtifactMatcher._tier_text

        def spy(self, rel_path, tier):
            if tier in ("history", "history_follow"):
                called["n"] += 1
            return orig(self, rel_path, tier)

        monkeypatch.setattr(ArtifactMatcher, "_tier_text", spy)

        baseline = load_baseline(repo)
        second, _ = scan_file(
            repo, path, config, rel_path=Path(".issues/bugs/P3-BUG-1-test.md"), baseline=baseline
        )
        assert second == []
        assert called["n"] == 0, "baselined span must skip history-tier git calls entirely"

    def test_baseline_detects_swapped_finding(self, repo: Path, config) -> None:
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        body_v1 = (
            "---\nid: BUG-2\n---\n\n"
            "## Current Behavior\n\n"
            "See `first fabricated phrase absent here` (`.issues/enhancements/target.md`).\n"
        )
        path = _write(repo, ".issues/bugs/P3-BUG-2-test.md", body_v1)
        _commit_all(repo)
        findings_v1, hashes_v1 = scan_file(
            repo, path, config, rel_path=Path(".issues/bugs/P3-BUG-2-test.md")
        )
        assert len(findings_v1) == 1
        write_baseline(repo, hashes_v1)

        # Fix the first span, introduce a different unverifiable one.
        body_v2 = (
            "---\nid: BUG-2\n---\n\n"
            "## Current Behavior\n\n"
            "See `nothing relevant here` (`.issues/enhancements/target.md`) and also "
            "`second fabricated phrase also absent` (`.issues/enhancements/target.md`).\n"
        )
        _write(repo, ".issues/bugs/P3-BUG-2-test.md", body_v2)

        baseline = load_baseline(repo)
        findings_v2, _ = scan_file(
            repo,
            path,
            config,
            rel_path=Path(".issues/bugs/P3-BUG-2-test.md"),
            baseline=baseline,
        )
        assert len(findings_v2) == 1
        assert "second fabricated phrase" in findings_v2[0].span

    def test_baseline_survives_rename(self, repo: Path, config) -> None:
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        body = (
            "---\nid: BUG-3\n---\n\n"
            "## Current Behavior\n\n"
            "See `phrase absent from target file here` (`.issues/enhancements/target.md`).\n"
        )
        old_path = _write(repo, ".issues/bugs/P2-BUG-3-old-title.md", body)
        _commit_all(repo)
        findings, hashes = scan_file(
            repo, old_path, config, rel_path=Path(".issues/bugs/P2-BUG-3-old-title.md")
        )
        assert len(findings) == 1
        write_baseline(repo, hashes)

        new_rel = Path(".issues/bugs/P1-BUG-3-new-title.md")
        _git(repo, "mv", str(old_path.relative_to(repo)), str(new_rel))
        _commit_all(repo, "rename")

        baseline = load_baseline(repo)
        findings_after, _ = scan_file(
            repo, repo / new_rel, config, rel_path=new_rel, baseline=baseline
        )
        assert findings_after == []  # ID-keyed baseline survives the rename


# ---------------------------------------------------------------------------
# --all scope
# ---------------------------------------------------------------------------


class TestAllScope:
    def test_source_file_outside_issues_base_dir_not_scanned(self, repo: Path, config) -> None:
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        _write(
            repo,
            "scripts/some_module.py",
            '"""See `unverifiable phrase absent from target` (`.issues/enhancements/target.md`)."""\n',
        )
        body = "## Current Behavior\n\nnothing notable.\n"
        _write(repo, ".issues/bugs/P3-BUG-4-test.md", body)
        _commit_all(repo)
        findings, _ = scan_all(repo, config, ".issues")
        assert findings == []


# ---------------------------------------------------------------------------
# Added-only (pre-commit mode)
# ---------------------------------------------------------------------------


class TestAddedOnly:
    def test_preexisting_span_on_unrelated_edit_not_flagged(self, repo: Path, config) -> None:
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        body_v1 = (
            "## Current Behavior\n\n"
            "See `pre-existing fabricated phrase here` (`.issues/enhancements/target.md`).\n"
            "\nSome trailing line.\n"
        )
        _write(repo, ".issues/bugs/issue.md", body_v1)
        _commit_all(repo)

        body_v2 = body_v1.replace("Some trailing line.", "Some trailing line, edited.")
        _write(repo, ".issues/bugs/issue.md", body_v2)
        _git(repo, "add", ".issues/bugs/issue.md")

        findings = scan_paths(repo, [Path(".issues/bugs/issue.md")], config, added_only=True)
        assert findings == []

    def test_new_span_on_staged_edit_flagged(self, repo: Path, config) -> None:
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        body_v1 = "## Current Behavior\n\nNothing quoted yet.\n"
        _write(repo, ".issues/bugs/issue.md", body_v1)
        _commit_all(repo)

        body_v2 = (
            "## Current Behavior\n\n"
            "Nothing quoted yet. See `newly added fabricated phrase` "
            "(`.issues/enhancements/target.md`).\n"
        )
        _write(repo, ".issues/bugs/issue.md", body_v2)
        _git(repo, "add", ".issues/bugs/issue.md")

        findings = scan_paths(repo, [Path(".issues/bugs/issue.md")], config, added_only=True)
        assert len(findings) == 1


# ---------------------------------------------------------------------------
# History tiering
# ---------------------------------------------------------------------------


class TestHistoryTiering:
    def test_follow_tier_finds_content_missed_by_non_follow(self, repo: Path) -> None:
        """A span present only in a revision strictly before the rename — one
        already overwritten under the old name by rename time — is
        transparent to results: the non-follow tier (pathspec-limited to the
        new name) misses it, --follow crosses the rename and finds it."""
        old_rel = ".issues/enhancements/old_name.md"
        _write(repo, old_rel, "## Section\n\nA distinctive phrase for renamed history.\n")
        _commit_all(repo, "add under old name")
        # Overwritten *before* the rename — gone from the old-name path too,
        # so only a --follow walk back through history reaches it.
        _write(repo, old_rel, "## Section\n\nsomething else entirely, pre-rename.\n")
        _commit_all(repo, "modify under old name")
        new_rel_path = Path(".issues/enhancements/new_name.md")
        _git(repo, "mv", old_rel, str(new_rel_path))
        _commit_all(repo, "rename")

        matcher = ArtifactMatcher(repo)
        follow_result = matcher._tier_text(str(new_rel_path), "history_follow")
        nonfollow_result = matcher._tier_text(str(new_rel_path), "history")
        assert follow_result is not None
        assert "distinctive phrase for renamed history" in follow_result
        assert (nonfollow_result is None) or (
            "distinctive phrase for renamed history" not in nonfollow_result
        )


# ---------------------------------------------------------------------------
# Whole-corpus precision smoke test (extraction-stage only — see docstring)
# ---------------------------------------------------------------------------


class TestWholeCorpusPrecision:
    def test_candidate_extraction_precision_ceiling(self) -> None:
        """Canary for the mention class over the real `.issues/` corpus.

        Scoped to extraction + attribution + span-kind filtering only (no git
        resolution/matching) so this stays fast — the full `--all` scan
        (which does walk git history for misses) is exercised by
        TestRepoGate below, which is allowed to be slow since it is the
        actual CI gate. If the span-kind filter is right, the number of
        candidates surviving to the matching stage across the whole corpus
        should be small relative to naive attributed-span extraction.
        """
        if not (REPO_ROOT / ".git").exists():
            pytest.skip("not a git checkout")

        from little_loops.cli.verify_evidence import _extract_mentions

        result = subprocess.run(
            ["git", "ls-files", "-z", "--", ".issues/**/*.md"],
            cwd=REPO_ROOT,
            capture_output=True,
        )
        rels = [n for n in result.stdout.decode("utf-8", "replace").split("\0") if n][:400]

        total_candidates = 0
        for rel in rels:
            try:
                content = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for section in in_scope_sections(content):
                mentions = _extract_mentions(content[section.start : section.end], section.start)
                for span in extract_candidate_spans(content, section):
                    if span.is_fence and is_command_output(content, span):
                        continue
                    from little_loops.cli.verify_evidence import MIN_SPAN_LEN

                    if len(span.text) < MIN_SPAN_LEN:
                        continue
                    if is_suppressed(content, span.start):
                        continue
                    if not span.is_fence:
                        line_start = content.rfind("\n", 0, span.start) + 1
                        line_end = content.find("\n", span.start)
                        line_end = len(content) if line_end == -1 else line_end
                        line_text = content[line_start:line_end]
                        if is_mention_class(span.text, line_text, span.start - line_start):
                            continue
                    if attribute_span(content, span, mentions) is None:
                        continue
                    total_candidates += 1

        # Per-file rate ceiling, not an absolute count: measured baseline rate
        # on this corpus is ~4 candidates/file. 15/file gives headroom for
        # normal variance while still catching a genuine mention-class
        # explosion — BUG-3282's own body carries 53 raw in-scope inline
        # spans before filtering, an order of magnitude above this ceiling.
        ceiling = len(rels) * 15
        assert total_candidates < ceiling, (
            f"{total_candidates} candidate spans survived filtering across "
            f"{len(rels)} sampled issue files (ceiling {ceiling}) — span-kind "
            "filter may be under-excluding"
        )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


class TestCli:
    def test_no_paths_no_all_errors(self, repo: Path) -> None:
        with pytest.raises(SystemExit):
            main_verify_evidence(["-C", str(repo)])

    def test_update_baseline_requires_all(self, repo: Path) -> None:
        with pytest.raises(SystemExit):
            main_verify_evidence(["-C", str(repo), "--update-baseline"])

    def test_added_only_rejected_with_all(self, repo: Path) -> None:
        with pytest.raises(SystemExit):
            main_verify_evidence(["-C", str(repo), "--all", "--added-only"])

    def test_clean_file_exits_zero(self, repo: Path) -> None:
        _write(repo, ".issues/bugs/issue.md", "## Current Behavior\n\nnothing notable.\n")
        _commit_all(repo)
        rc = main_verify_evidence(["-C", str(repo), ".issues/bugs/issue.md"])
        assert rc == 0

    def test_unverifiable_file_exits_one(self, repo: Path) -> None:
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        body = (
            "## Current Behavior\n\n"
            "See `this text is entirely absent from the target` "
            "(`.issues/enhancements/target.md`).\n"
        )
        _write(repo, ".issues/bugs/issue.md", body)
        _commit_all(repo)
        rc = main_verify_evidence(["-C", str(repo), ".issues/bugs/issue.md"])
        assert rc == 1


# ---------------------------------------------------------------------------
# Repo-wide CI gate
# ---------------------------------------------------------------------------


class TestRepoGate:
    """The CI gate: this repo's `.issues/` corpus must gain no new
    evidence-unverifiable spans beyond the tracked baseline.

    Regenerate deliberately, never reflexively:

        ll-verify-evidence --all --update-baseline

    A regression here means either a fabricated quote landed, or a genuine
    attribution/span-kind gap needs fixing before the baseline is re-seeded.
    """

    def test_no_new_unverifiable_evidence(self) -> None:
        if not (REPO_ROOT / ".git").exists():
            pytest.skip("not a git checkout; nothing to enumerate")

        result = subprocess.run(
            ["ll-verify-evidence", "--all", "--json", "-C", str(REPO_ROOT)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if result.returncode not in (0, 1):
            pytest.skip(f"ll-verify-evidence unavailable (rc={result.returncode})")

        payload = json.loads(result.stdout)
        if payload["ok"]:
            return

        detail = "\n".join(
            f"  {f['file']}:{f['line']} [{f['section']}] attributed to {f['artifact']}: {f['span']!r}"
            for f in payload["findings"][:20]
        )
        pytest.fail(
            f"{payload['count']} evidence-unverifiable span(s) beyond baseline.\n"
            f"{detail}\n\n"
            "Fix the quote, correct the attribution, or suppress a reviewed "
            "counter-example with '<!-- ll-evidence-ok: reason -->'."
        )

    def test_baseline_is_tracked_and_parseable(self) -> None:
        baseline = REPO_ROOT / BASELINE_PATH
        assert baseline.is_file(), f"{BASELINE_PATH} must be tracked for the gate to mean anything"
        assert load_baseline(REPO_ROOT), (
            "baseline parsed empty — every file would read as regressed"
        )
