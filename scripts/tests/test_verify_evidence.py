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
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from little_loops.cli.verify_evidence import (
    BASELINE_PATH,
    VERDICT_CACHE_PATH,
    ArtifactMatcher,
    BlobReader,
    HistoryIndex,
    ScanExecutionError,
    _read_working_tree,
    attribute_span,
    build_tracked_index,
    compute_findings_delta,
    extract_candidate_spans,
    in_scope_sections,
    is_command_output,
    is_mention_class,
    is_suppressed,
    iter_sections,
    load_baseline,
    load_verdict_cache,
    main_verify_evidence,
    normalize,
    resolve_artifact,
    scan_all,
    scan_file,
    scan_paths,
    write_baseline,
    write_verdict_cache,
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

GATE_CLI = "ll-verify-evidence"
# A full-corpus `--all` runs in ~10s (parallel seed) to ~50s (cold serial), so
# 120s is generous headroom rather than a guess. It exists because an *untimed*
# subprocess here is what wedged a whole `ll-auto` run: pytest's thread-method
# timeout killed the xdist worker without reaping this grandchild, xdist
# respawned and re-ran the test, and the cycle leaked one orphaned scan every
# ~124s until the run was killed by hand. Mirrors the sibling validator gate at
# `test_decisions_yaml_gate.py:80`.
#
# The gate test carries `@pytest.mark.timeout(GATE_TIMEOUT + 30)`: the suite-wide
# `--timeout=120` (thread method) starts before the subprocess does, so an equal
# cap would kill the xdist worker first and the labelled `TimeoutExpired`
# message would never appear. The per-test cap must stay strictly greater.
GATE_TIMEOUT = 120
GATE_FAILURE_LABEL = "ISSUE-CORPUS EVIDENCE GATE"
GATE_MAX_FINDINGS_SHOWN = 20


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


def _fail_if_shallow_checkout(repo_root: Path) -> None:
    """Fail fast when the checkout lacks the history the gate depends on (BUG-3442).

    A depth-1 clone (the ``actions/checkout`` default) has a ``.git``, so the
    plain not-a-git-checkout skip never fires — yet ``HistoryIndex``'s single
    ``git log --all --raw`` pass sees only the tip commit, so every span older
    than tip reports unverifiable (~155 structural findings) and the gate is
    always-red. Fails rather than skips: a skip would silently disarm the gate
    in exactly the state this guards against; the diagnostic names both
    remedies in one line instead of a 150-item findings dump.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout; nothing to enumerate")
    if result.stdout.strip() == "true":
        pytest.fail(
            "shallow checkout: the history-dependent evidence gate cannot run "
            "(CI: actions/checkout needs `fetch-depth: 0` — BUG-3442; local: "
            "`git fetch --unshallow`)"
        )


def _classify_gate_result(returncode: int, stdout: str, stderr: str) -> tuple[str, str]:
    """Classify a ``ll-verify-evidence --all --json`` run (ENH-3518).

    Returns ``("clean" | "findings" | "execution_failure", labelled message)``.
    Exit 1 is ambiguous (an uncaught CLI exception also exits 1), so status is
    only trusted once stdout parses as a payload consistent with the exit code.
    """

    def failure(reason: str) -> tuple[str, str]:
        tail = stderr.strip()[-2000:]
        return (
            "execution_failure",
            f"{GATE_FAILURE_LABEL}: {GATE_CLI} did not produce a usable result "
            f"({reason}; exit {returncode}). This is a verifier execution failure, "
            f"not a corpus finding.\nstderr: {tail or '<empty>'}",
        )

    try:
        payload = json.loads(stdout)
    except ValueError:
        return failure("stdout is not valid JSON")
    if not isinstance(payload, dict):
        return failure("payload is not a JSON object")

    ok, count, findings = payload.get("ok"), payload.get("count"), payload.get("findings")
    if not isinstance(ok, bool) or not isinstance(payload.get("mode"), str):
        return failure("invalid 'ok'/'mode' field types")
    if not isinstance(count, int) or isinstance(count, bool) or not isinstance(findings, list):
        return failure("invalid 'count'/'findings' field types")
    fields = {"file": str, "line": int, "section": str, "span": str, "artifact": str}
    for f in findings:
        if not isinstance(f, dict) or not all(
            isinstance(f.get(k), t) and not isinstance(f.get(k), bool) for k, t in fields.items()
        ):
            return failure("invalid finding entry")

    if returncode == 0 and ok and count == 0 and findings == []:
        return "clean", ""
    if returncode == 1 and not ok and count == len(findings) > 0:
        shown = findings[:GATE_MAX_FINDINGS_SHOWN]
        detail = "\n".join(
            f"  {f['file']}:{f['line']} [{f['section']}] attributed to {f['artifact']}: "
            f"{f['span']!r}"
            for f in shown
        )
        truncated = f" (showing {GATE_MAX_FINDINGS_SHOWN} of {count})" if count > len(shown) else ""
        return (
            "findings",
            f"{GATE_FAILURE_LABEL}: {count} evidence-unverifiable span(s) in the issue "
            f"corpus beyond baseline{truncated}.\n{detail}\n\n"
            "Fix the quote, correct the attribution, or suppress a reviewed "
            "counter-example with '<!-- ll-evidence-ok: reason -->'.",
        )
    return failure("exit status inconsistent with payload")


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
# History index / blob reader
# ---------------------------------------------------------------------------


class TestHistoryIndex:
    def test_multiline_span_found_in_superseded_revision(self, repo: Path) -> None:
        rel = ".issues/enhancements/history_target.md"
        _write(repo, rel, "## Section\n\nA multi line\nspan here in the original.\n")
        _commit_all(repo, "add original")
        # Overwrite in a later commit so it's absent at HEAD.
        _write(repo, rel, "## Section\n\ncompletely different content now.\n")
        _commit_all(repo, "rewrite content")

        with ArtifactMatcher(repo) as matcher:
            result = matcher.matches(rel, ["A multi line span here in the original."])
        assert result["A multi line span here in the original."] is True

    def test_rename_record_does_not_mis_file_blobs(self, repo: Path) -> None:
        """``--no-renames`` is load-bearing: an ``R100`` raw record carries two
        tab-separated paths, and a parse that misses this files blobs under a
        concatenated path. Renaming with content intact must leave the new path
        resolvable, not stashed under ``old\\tnew``."""
        old_rel = ".issues/enhancements/before.md"
        _write(repo, old_rel, "## Section\n\nA stable distinctive sentence here.\n")
        _commit_all(repo, "add")
        _git(repo, "mv", old_rel, ".issues/enhancements/after.md")
        _commit_all(repo, "rename")

        index = HistoryIndex(repo)
        index.ensure_full()
        assert index.blobs_for(".issues/enhancements/after.md")
        assert not any("\t" in path for path in index.as_data())

    def test_blobs_for_unknown_path_is_empty(self, repo: Path) -> None:
        """The miss case that previously cost ~250ms of ``git log`` per call."""
        index = HistoryIndex(repo)
        index.ensure_full()
        assert index.blobs_for("no/such/file/ever.py") == ()

    def test_blob_reader_returns_none_for_missing_oid(self, repo: Path) -> None:
        with BlobReader(repo) as reader:
            assert reader.read("0" * 40) is None

    def test_commit_message_text_does_not_certify_a_span(self, repo: Path) -> None:
        """Regression: ``git log -p`` interleaved commit-message text with file
        content, so a quote appearing only in a commit message was certified as
        present in the artifact. Verified on the real repo before this change:
        ``on_error: define_done`` matched the patch stream for
        ``test_builtin_loops.py`` while appearing in 0 of its 453 revisions."""
        rel = ".issues/enhancements/msg_target.md"
        _write(repo, rel, "## Section\n\nordinary content, nothing quoted.\n")
        _commit_all(repo, "a distinctive phrase that lives only in this message")

        with ArtifactMatcher(repo) as matcher:
            result = matcher.matches(rel, ["a distinctive phrase that lives only in this message"])
        assert result["a distinctive phrase that lives only in this message"] is False


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
        orig = ArtifactMatcher._blob_text

        def spy(self, oid):
            called["n"] += 1
            return orig(self, oid)

        monkeypatch.setattr(ArtifactMatcher, "_blob_text", spy)

        baseline = load_baseline(repo)
        second, _ = scan_file(
            repo, path, config, rel_path=Path(".issues/bugs/P3-BUG-1-test.md"), baseline=baseline
        )
        assert second == []
        assert called["n"] == 0, "baselined span must skip the blob walk entirely"

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


class TestVerdictCache:
    """The cache is memoization, never policy: it may change wall time and
    must never change a verdict set."""

    def _seed(self, repo: Path) -> tuple[Path, str]:
        rel = ".issues/enhancements/cache_target.md"
        _write(repo, rel, "## Section\n\nordinary content only.\n")
        _commit_all(repo, "seed")
        return repo, rel

    def test_found_verdict_is_reused(self, repo: Path) -> None:
        _, rel = self._seed(repo)
        cache = load_verdict_cache(repo, max_revisions=80)
        with ArtifactMatcher(repo, max_revisions=80, verdict_cache=cache) as m:
            assert m.matches(rel, ["ordinary content only."]) == {"ordinary content only.": True}
        write_verdict_cache(repo, cache)

        reloaded = load_verdict_cache(repo, max_revisions=80)
        with ArtifactMatcher(repo, max_revisions=80, verdict_cache=reloaded) as m:
            # No blob reads at all: the hit is served from the cache.
            m._blob_text = lambda oid: pytest.fail("cache miss: blob was re-read")  # type: ignore[assignment]
            assert m.matches(rel, ["ordinary content only."]) == {"ordinary content only.": True}

    def test_found_verdict_invalidated_by_working_tree_edit(self, repo: Path) -> None:
        """The CI-failure shape (2026-09-11): a hit recorded from the working
        tree must not survive the text being edited out. Under the old
        bare-"1" entries, stale found verdicts suppressed real findings on
        every warm-cache machine while CI's cold checkout failed. The span
        stays uncommitted so blob history cannot legitimately re-verify it."""
        _, rel = self._seed(repo)
        span = "uncommitted working-tree-only phrase."
        _write(repo, rel, f"## Section\n\n{span}\n")  # uncommitted, on top of the seed commit
        cache = load_verdict_cache(repo, max_revisions=80)
        with ArtifactMatcher(repo, max_revisions=80, verdict_cache=cache) as m:
            assert m.matches(rel, [span]) == {span: True}
        write_verdict_cache(repo, cache)

        # The artifact loses the text: the cached hit must not survive.
        _write(repo, rel, "## Section\n\nthe phrase is gone now.\n")
        reloaded = load_verdict_cache(repo, max_revisions=80)
        with ArtifactMatcher(repo, max_revisions=80, verdict_cache=reloaded) as m:
            assert m.matches(rel, [span]) == {span: False}

    def test_not_found_verdict_invalidated_by_working_tree_edit(self, repo: Path) -> None:
        _, rel = self._seed(repo)
        span = "a phrase that is not there yet"
        cache = load_verdict_cache(repo, max_revisions=80)
        with ArtifactMatcher(repo, max_revisions=80, verdict_cache=cache) as m:
            assert m.matches(rel, [span]) == {span: False}
        write_verdict_cache(repo, cache)

        # The artifact gains the text: the cached miss must not survive.
        _write(repo, rel, f"## Section\n\n{span}\n")
        reloaded = load_verdict_cache(repo, max_revisions=80)
        with ArtifactMatcher(repo, max_revisions=80, verdict_cache=reloaded) as m:
            assert m.matches(rel, [span]) == {span: True}

    def test_algorithm_change_discards_everything(self, repo: Path) -> None:
        """A narrower matcher could legitimately un-find a span, so a changed
        `max_revisions` must not inherit even the found verdicts."""
        _, rel = self._seed(repo)
        cache = load_verdict_cache(repo, max_revisions=80)
        cache.record(rel, "deadbeefdeadbeef", True, "fp", "wt")
        write_verdict_cache(repo, cache)

        assert load_verdict_cache(repo, max_revisions=80).verdicts != {}
        assert load_verdict_cache(repo, max_revisions=20).verdicts == {}

    def test_corrupt_cache_is_ignored_not_fatal(self, repo: Path) -> None:
        (repo / ".ll").mkdir(parents=True, exist_ok=True)
        (repo / VERDICT_CACHE_PATH).write_text("{ not json")
        assert load_verdict_cache(repo, max_revisions=80).verdicts == {}


class TestHistoryTiering:
    def test_content_surviving_a_rename_is_still_found(self, repo: Path) -> None:
        """The rename case that actually occurs: content present at rename time.

        ``--no-renames`` turns a rename into delete+add, and the add's
        post-image blob is the *complete* file, so text that survived the
        rename is reachable under the new path without following anything.
        """
        old_rel = ".issues/enhancements/old_name.md"
        _write(repo, old_rel, "## Section\n\nA distinctive phrase for renamed history.\n")
        _commit_all(repo, "add under old name")
        new_rel_path = Path(".issues/enhancements/new_name.md")
        _git(repo, "mv", old_rel, str(new_rel_path))
        _commit_all(repo, "rename")

        with ArtifactMatcher(repo) as matcher:
            result = matcher.matches(
                str(new_rel_path), ["A distinctive phrase for renamed history."]
            )
        assert result["A distinctive phrase for renamed history."] is True

    def test_content_overwritten_before_a_rename_is_not_followed(self, repo: Path) -> None:
        """Documents the one recall case dropping ``--follow`` gives up.

        Text overwritten under the *old* name before the rename is filed under
        the old path and is not reached from the new one. This is deliberate:
        the ``--follow`` tier cost 33.7% of total runtime and resolved **zero**
        spans across two independent samples (400 files and 120 files) of this
        repo's corpus, so it was removed rather than conditionalised. Restoring
        it means re-running the index pass with ``-M`` and chaining ``R``-status
        records — measured at +2.2s per run for a corpus recall gain of zero.
        """
        old_rel = ".issues/enhancements/old_name.md"
        _write(repo, old_rel, "## Section\n\nA distinctive phrase for renamed history.\n")
        _commit_all(repo, "add under old name")
        _write(repo, old_rel, "## Section\n\nsomething else entirely, pre-rename.\n")
        _commit_all(repo, "modify under old name")
        new_rel_path = Path(".issues/enhancements/new_name.md")
        _git(repo, "mv", old_rel, str(new_rel_path))
        _commit_all(repo, "rename")

        with ArtifactMatcher(repo) as matcher:
            result = matcher.matches(
                str(new_rel_path), ["A distinctive phrase for renamed history."]
            )
        assert result["A distinctive phrase for renamed history."] is False
        # ...but it is still reachable under the name it was written to.
        with ArtifactMatcher(repo) as matcher:
            under_old = matcher.matches(old_rel, ["A distinctive phrase for renamed history."])
        assert under_old["A distinctive phrase for renamed history."] is True


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
# Snapshot / delta (ENH-3519)
# ---------------------------------------------------------------------------

_TARGET = ".issues/enhancements/target.md"
_ISSUE = ".issues/bugs/issue.md"
_BAD1 = "this first quote is entirely absent from the target"
_BAD2 = "this second quote is also entirely absent from it"


def _issue_body(*spans: str, alias: str = _TARGET) -> str:
    quotes = "\n".join(f"See `{sp}` (`{alias}`)." for sp in spans)
    return f"## Current Behavior\n\n{quotes}\n"


@pytest.fixture
def delta_repo(repo: Path) -> Path:
    _write(repo, _TARGET, "nothing relevant here\n")
    _write(repo, _ISSUE, _issue_body(_BAD1))
    _commit_all(repo)
    return repo


def _run(repo: Path, *args: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
    rc = main_verify_evidence(["-C", str(repo), *args, "--json"])
    return rc, json.loads(capsys.readouterr().out)


def _snapshot(repo: Path, capsys: pytest.CaptureFixture[str]) -> str:
    rc, payload = _run(repo, _ISSUE, "--save-snapshot", capsys=capsys)
    assert rc == 1
    return payload["snapshot_path"]


class TestComputeFindingsDelta:
    @staticmethod
    def _f(span: str, line: int = 3, artifact: str = "A", resolved: str = "a.md") -> dict:
        return {
            "file": "i.md",
            "line": line,
            "section": "Current Behavior",
            "span": span,
            "artifact": artifact,
            "resolved_artifact": resolved,
        }

    def test_unchanged_and_line_shift_not_new(self) -> None:
        before = [self._f(_BAD1, 3)]
        assert compute_findings_delta(before, [self._f(_BAD1, 9)]) == []

    def test_new_quote_reported_with_candidates(self) -> None:
        groups = compute_findings_delta([self._f(_BAD1)], [self._f(_BAD1), self._f(_BAD2, 5)])
        assert len(groups) == 1
        assert groups[0]["added_count"] == 1
        assert groups[0]["preexisting_count"] == 0
        assert groups[0]["candidates"][0]["line"] == 5

    def test_duplicate_of_old_bad_quote_is_new(self) -> None:
        groups = compute_findings_delta(
            [self._f(_BAD1, 3)], [self._f(_BAD1, 3), self._f(_BAD1, 3), self._f(_BAD1, 9)]
        )
        assert groups[0]["added_count"] == 2
        assert groups[0]["preexisting_count"] == 1
        assert len(groups[0]["candidates"]) == 3

    def test_duplicate_inserted_before_existing(self) -> None:
        groups = compute_findings_delta([self._f(_BAD1, 5)], [self._f(_BAD1, 3), self._f(_BAD1, 6)])
        assert groups[0]["added_count"] == 1

    def test_whitespace_emphasis_punctuation_rewrite_not_new(self) -> None:
        before = [self._f("the  quoted   text is long enough")]
        after = [self._f("the *quoted* text is long enough.")]
        assert compute_findings_delta(before, after) == []

    def test_respelling_same_artifact_not_new_but_reattribution_is(self) -> None:
        before = [self._f(_BAD1, artifact="ENH-1", resolved="a.md")]
        assert compute_findings_delta(before, [self._f(_BAD1, artifact="a.md")]) == []
        moved = [self._f(_BAD1, artifact="b.md", resolved="b.md")]
        assert compute_findings_delta(before, moved)[0]["resolved_artifact"] == "b.md"

    def test_repaired_finding_not_new(self) -> None:
        assert compute_findings_delta([self._f(_BAD1)], []) == []

    def test_equal_count_replacement_cancels(self) -> None:
        # Documented net-count semantics: remove one identical span, add another.
        assert compute_findings_delta([self._f(_BAD1, 3)], [self._f(_BAD1, 8)]) == []


class TestAttributionPerOccurrence:
    def test_alias_does_not_relabel_earlier_finding(self, delta_repo: Path) -> None:
        # Two spellings (issue ID and path) resolving to one file.
        _write(delta_repo, ".issues/enhancements/P3-ENH-9-target.md", "unrelated\n")
        body = f"## Current Behavior\n\nSee `{_BAD1}` (`ENH-9`).\n\nSee `{_BAD2}` (`P3-ENH-9`).\n"
        _write(delta_repo, _ISSUE, body)
        _commit_all(delta_repo)
        config = BRConfig(delta_repo)
        findings = scan_paths(delta_repo, [Path(_ISSUE)], config)
        by_span = {f.span: f for f in findings}
        assert by_span[_BAD1].artifact == "ENH-9"
        assert by_span[_BAD2].artifact == "P3-ENH-9"
        assert by_span[_BAD1].resolved_artifact == by_span[_BAD2].resolved_artifact


class TestSnapshotCli:
    def test_allocates_unique_path(
        self, delta_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p1 = Path(_snapshot(delta_repo, capsys))
        p2 = Path(_snapshot(delta_repo, capsys))
        assert p1 != p2
        for p in (p1, p2):
            assert p.is_file()
            assert p.parent == (delta_repo / ".loops" / "tmp" / "scratch").resolve()
            assert p.name.startswith("evidence-snapshot-")
            assert p.name.endswith(f"-{os.getpid()}.json")

    def test_payload_has_resolved_artifact(
        self, delta_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc, payload = _run(delta_repo, _ISSUE, "--save-snapshot", capsys=capsys)
        assert rc == 1
        assert payload["findings"][0]["resolved_artifact"] == _TARGET
        assert Path(payload["snapshot_path"]).is_absolute()

    def test_text_output_prints_saved_path(
        self, delta_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main_verify_evidence(["-C", str(delta_repo), _ISSUE, "--save-snapshot"])
        assert rc == 1
        assert "Snapshot saved: " in capsys.readouterr().out

    def test_explicit_path_and_alias_rejected(
        self, delta_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        dest = tmp_path / "snap.json"
        rc, _ = _run(delta_repo, _ISSUE, "--save-snapshot", str(dest), capsys=capsys)
        assert rc == 1 and dest.is_file()
        rc, body = _run(
            delta_repo, _ISSUE, "--save-snapshot", str(delta_repo / _ISSUE), capsys=capsys
        )
        assert rc == 2 and body["status"] == "incomplete"
        assert "aliases" in body["error"]

    def test_write_failure_is_incomplete(
        self, delta_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        blocker = tmp_path / "file"
        blocker.write_text("x")
        rc, body = _run(
            delta_repo, _ISSUE, "--save-snapshot", str(blocker / "s.json"), capsys=capsys
        )
        assert rc == 2 and body["status"] == "incomplete"


class TestDeltaCli:
    def test_clean_delta_with_preexisting_findings(
        self, delta_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        snap = _snapshot(delta_repo, capsys)
        rc, body = _run(delta_repo, _ISSUE, "--delta-from", snap, capsys=capsys)
        assert rc == 0
        assert body["mode"] == "delta" and body["status"] == "clean" and body["ok"] is True
        assert body["new_count"] == 0 and body["count"] == len(body["findings"]) == 1

    def test_new_quote_detected(self, delta_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        snap = _snapshot(delta_repo, capsys)
        _write(delta_repo, _ISSUE, _issue_body(_BAD1, _BAD2))
        rc, body = _run(delta_repo, _ISSUE, "--delta-from", snap, capsys=capsys)
        assert rc == 1 and body["ok"] is False and body["status"] == "new_findings"
        assert body["new_count"] == sum(g["added_count"] for g in body["new_findings"]) == 1
        assert body["count"] == len(body["findings"]) == 2
        assert body["new_findings"][0]["span"] == _BAD2

    def test_text_output_distinguishes_new(
        self, delta_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        snap = _snapshot(delta_repo, capsys)
        _write(delta_repo, _ISSUE, _issue_body(_BAD1, _BAD2))
        rc = main_verify_evidence(["-C", str(delta_repo), _ISSUE, "--delta-from", snap])
        out = capsys.readouterr().out
        assert rc == 1 and "NEW FINDINGS" in out and "1 pre-existing" in out

    def test_repair_returns_clean(
        self, delta_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        snap = _snapshot(delta_repo, capsys)
        _write(delta_repo, _ISSUE, _issue_body(_BAD1, "nothing relevant here"))
        rc, body = _run(delta_repo, _ISSUE, "--delta-from", snap, capsys=capsys)
        assert rc == 0 and body["status"] == "clean"

    def test_missing_snapshot_incomplete(
        self, delta_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc, body = _run(
            delta_repo, _ISSUE, "--delta-from", str(tmp_path / "nope.json"), capsys=capsys
        )
        assert rc == 2
        assert body["status"] == "incomplete" and body["findings"] == []

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda d: d.update(schema_version=99),
            lambda d: d.update(verifier_compat=99),
            lambda d: d.update(project_root="/elsewhere"),
            lambda d: d.update(issue_path="other.md"),
            lambda d: d.update(max_revisions=1),
            lambda d: d.update(findings="nope"),
            lambda d: d["findings"][0].update(line="3"),
            lambda d: d["findings"][0].pop("resolved_artifact"),
        ],
    )
    def test_invalid_snapshot_incomplete(
        self, delta_repo: Path, capsys: pytest.CaptureFixture[str], mutate
    ) -> None:
        snap = Path(_snapshot(delta_repo, capsys))
        data = json.loads(snap.read_text())
        mutate(data)
        snap.write_text(json.dumps(data))
        rc, body = _run(delta_repo, _ISSUE, "--delta-from", str(snap), capsys=capsys)
        assert rc == 2 and body["status"] == "incomplete"

    def test_malformed_json_snapshot(
        self, delta_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        rc, body = _run(delta_repo, _ISSUE, "--delta-from", str(bad), capsys=capsys)
        assert rc == 2 and body["status"] == "incomplete"

    def test_after_scan_failure_carries_snapshot_findings(
        self,
        delta_repo: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        snap = _snapshot(delta_repo, capsys)

        def boom(*a: object, **k: object) -> None:
            raise ScanExecutionError("git ls-files exited 128")

        monkeypatch.setattr("little_loops.cli.verify_evidence.build_tracked_index", boom)
        rc, body = _run(delta_repo, _ISSUE, "--delta-from", snap, capsys=capsys)
        assert rc == 2 and body["status"] == "incomplete"
        assert body["ok"] is False and len(body["findings"]) == 1

    def test_before_scan_failure_publishes_no_snapshot(
        self, delta_repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*a: object, **k: object) -> None:
            raise ScanExecutionError("history failed")

        monkeypatch.setattr("little_loops.cli.verify_evidence.HistoryIndex._run_full", boom)
        monkeypatch.setattr("little_loops.cli.verify_evidence.HistoryIndex.ensure_paths", boom)
        rc, body = _run(delta_repo, _ISSUE, "--save-snapshot", capsys=capsys)
        assert rc == 2 and body["status"] == "incomplete"
        assert not (delta_repo / ".loops" / "tmp" / "scratch").exists()


class TestSnapshotFlagValidation:
    @pytest.mark.parametrize(
        "extra",
        [
            ["--all"],
            ["--update-baseline"],
            ["--added-only"],
        ],
    )
    def test_incompatible_flags_json(
        self, delta_repo: Path, capsys: pytest.CaptureFixture[str], extra: list[str]
    ) -> None:
        rc, body = _run(delta_repo, _ISSUE, "--save-snapshot", *extra, capsys=capsys)
        assert rc == 2 and body["status"] == "incomplete"

    def test_mutually_exclusive(self, delta_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc, body = _run(
            delta_repo, _ISSUE, "--save-snapshot", "auto", "--delta-from", "x", capsys=capsys
        )
        assert rc == 2 and body["status"] == "incomplete"

    def test_cardinality(self, delta_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc, body = _run(delta_repo, _ISSUE, _TARGET, "--save-snapshot", capsys=capsys)
        assert rc == 2 and body["status"] == "incomplete"
        rc, body = _run(delta_repo, "--save-snapshot", capsys=capsys)
        assert rc == 2 and body["status"] == "incomplete"

    def test_missing_input_file(self, delta_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc, body = _run(delta_repo, ".issues/bugs/none.md", "--save-snapshot", capsys=capsys)
        assert rc == 2 and body["status"] == "incomplete"

    def test_text_mode_reports_incomplete(
        self, delta_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main_verify_evidence(
            ["-C", str(delta_repo), ".issues/bugs/none.md", "--save-snapshot"]
        )
        assert rc == 2 and "INCOMPLETE" in capsys.readouterr().out

    def test_argparse_syntax_error_stays_stderr(self, delta_repo: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            main_verify_evidence(["-C", str(delta_repo), _ISSUE, "--delta-from"])
        assert exc.value.code == 2


class _FakeProc:
    """Minimal ``git cat-file --batch`` stand-in feeding canned bytes."""

    def __init__(self, response: bytes) -> None:
        import io

        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(response)

    def poll(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        pass


class TestStrictBlobReader:
    OID = "a" * 40

    def _reader(self, response: bytes, *, strict: bool) -> BlobReader:
        reader = BlobReader(Path("."), strict=strict)
        reader._proc = _FakeProc(response)  # type: ignore[assignment]
        return reader

    def test_well_formed(self) -> None:
        r = self._reader(f"{self.OID} blob 5\nhello\n".encode(), strict=True)
        assert r.read(self.OID) == b"hello"

    def test_missing_is_absence(self) -> None:
        r = self._reader(f"{self.OID} missing\n".encode(), strict=True)
        assert r.read(self.OID) is None

    @pytest.mark.parametrize(
        "response",
        [
            b"",  # empty header
            b"short\n",  # arbitrary short header
            b"%(oid)s blob -5\nhello\n",  # negative size
            b"%(oid)s blob abc\nhello\n",  # invalid size
            b"%(oid)s tree 5\nhello\n",  # wrong type
            b"%(other)s blob 5\nhello\n",  # wrong oid
            b"%(oid)s blob 50\nhello\n",  # truncated payload containing the quote
            b"%(oid)s blob 5\nhelloX",  # incorrect terminator
            b"%(oid)s blob 5\nhello",  # missing terminator
        ],
    )
    def test_malformed_raises(self, response: bytes) -> None:
        raw = (
            response % {b"oid": self.OID.encode(), b"other": b"b" * 40}
            if b"%(" in response
            else response
        )
        r = self._reader(raw, strict=True)
        with pytest.raises(ScanExecutionError):
            r.read(self.OID)

    def test_legacy_lenient_on_malformed(self) -> None:
        assert self._reader(b"short\n", strict=False).read(self.OID) is None


class TestStrictFailures:
    def test_tracked_index_failure(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def run(*a: object, **k: object) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(a, 128, b"", b"")

        monkeypatch.setattr(subprocess, "run", run)
        with pytest.raises(ScanExecutionError):
            build_tracked_index(repo, strict=True)
        assert build_tracked_index(repo) == frozenset()

    def test_history_failure(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def run(*a: object, **k: object) -> subprocess.CompletedProcess[bytes]:
            raise OSError("no git")

        monkeypatch.setattr(subprocess, "run", run)
        with pytest.raises(ScanExecutionError):
            HistoryIndex(repo, strict=True).ensure_full()
        with pytest.raises(ScanExecutionError):
            HistoryIndex(repo, strict=True).ensure_paths(["a.md"])
        HistoryIndex(repo).ensure_full()  # legacy: swallowed

    def test_zero_exit_empty_history_is_absence(self, repo: Path) -> None:
        _write(repo, "x.md", "x\n")
        _commit_all(repo)
        index = HistoryIndex(repo, strict=True)
        index.ensure_paths(["never-existed.md"])
        assert index.blobs_for("never-existed.md") == ()

    def test_issue_read_failure(self, repo: Path) -> None:
        config = BRConfig(repo)
        missing = repo / "gone.md"
        with pytest.raises(ScanExecutionError):
            scan_file(repo, missing, config, strict=True)
        assert scan_file(repo, missing, config) == ([], {})

    def test_worktree_read_error_vs_absence(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert _read_working_tree(repo, "absent.md", strict=True) is None

        def denied(self: Path, *a: object, **k: object) -> str:
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "read_text", denied)
        with pytest.raises(ScanExecutionError):
            _read_working_tree(repo, "x.md", strict=True)
        assert _read_working_tree(repo, "x.md") is None


# ---------------------------------------------------------------------------
# Repo-wide CI gate
# ---------------------------------------------------------------------------


class TestShallowCheckoutPrecondition:
    """BUG-3442: the repo gate must fail fast on a shallow checkout.

    A depth-1 clone has a `.git`, so the plain not-a-git-checkout skip never
    fires — but `HistoryIndex.ensure_full()`'s single `git log --all --raw`
    pass sees only the tip commit, so every span older than tip reports
    unverifiable (~155 structural findings on CI) and the gate is always-red
    with zero signal. The precondition must `pytest.fail` (not skip): a skip
    would silently disarm the gate in exactly the state this guards against.
    """

    @staticmethod
    def _two_commit_repo(root: Path) -> None:
        _init_repo(root)
        _write(root, "a.txt", "one\n")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "init")
        _write(root, "a.txt", "two\n")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "second")

    def test_shallow_checkout_fails_fast_with_remedy(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        self._two_commit_repo(src)
        shallow = tmp_path / "shallow"
        # file:// is required: a local-path clone hardlinks and ignores --depth.
        _git(
            tmp_path,
            "clone",
            "-q",
            "--depth",
            "1",
            f"file://{src}",
            str(shallow),
        )
        with pytest.raises(pytest.fail.Exception) as excinfo:
            _fail_if_shallow_checkout(shallow)
        message = str(excinfo.value)
        assert "fetch-depth" in message, "diagnostic must name the CI remedy"
        assert "--unshallow" in message, "diagnostic must name the local remedy"

    def test_full_history_checkout_passes(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        self._two_commit_repo(src)
        _fail_if_shallow_checkout(src)  # must not raise


class TestRepoGate:
    """The CI gate: this repo's `.issues/` corpus must gain no new
    evidence-unverifiable spans beyond the tracked baseline.

    Regenerate deliberately, never reflexively:

        ll-verify-evidence --all --update-baseline

    A regression here means either a fabricated quote landed, or a genuine
    attribution/span-kind gap needs fixing before the baseline is re-seeded.
    """

    @pytest.fixture(scope="module")
    def gate_cli(self) -> str:
        """Return the ``ll-verify-evidence`` path, skipping when it is missing.

        The canonical skip-when-missing idiom (``test_decisions_yaml_gate.py``
        :49-63). This replaces a ``returncode not in (0, 1)`` check, which
        could never fire for the failure that actually occurred: the call
        hanging means there is no return code to inspect.
        """
        path = shutil.which(GATE_CLI)
        if path is None:
            pytest.skip(f"{GATE_CLI} not installed; install via `pip install -e ./scripts[dev]`")
        return path

    @pytest.mark.timeout(GATE_TIMEOUT + 30)
    def test_no_new_unverifiable_evidence(self, gate_cli: str) -> None:
        if not (REPO_ROOT / ".git").exists():
            pytest.skip("not a git checkout; nothing to enumerate")
        _fail_if_shallow_checkout(REPO_ROOT)

        try:
            result = subprocess.run(
                [gate_cli, "--all", "--json", "-C", str(REPO_ROOT)],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                timeout=GATE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"{GATE_FAILURE_LABEL}: {GATE_CLI} --all exceeded {GATE_TIMEOUT}s. A full "
                "corpus scan runs in well under that; a timeout here may indicate a "
                "verifier performance regression."
            )
        except OSError as exc:
            pytest.fail(
                f"{GATE_FAILURE_LABEL}: could not launch {GATE_CLI} ({exc}). "
                "This is a verifier execution failure, not a corpus finding."
            )

        verdict, message = _classify_gate_result(result.returncode, result.stdout, result.stderr)
        if verdict != "clean":
            pytest.fail(message)

    def test_baseline_is_tracked_and_parseable(self) -> None:
        baseline = REPO_ROOT / BASELINE_PATH
        assert baseline.is_file(), f"{BASELINE_PATH} must be tracked for the gate to mean anything"
        assert load_baseline(REPO_ROOT), (
            "baseline parsed empty — every file would read as regressed"
        )

    def test_baseline_size_is_bounded(self) -> None:
        """The counterweight to ``--update-baseline``.

        A baseline is a grandfathered backlog; one that grows is a checker that
        got *worse*, not a corpus that did. It also has to stay small enough
        that a maintainer can actually read it before committing a re-seed —
        this one went unreviewed at ~3800 findings once already.
        """
        total = sum(len(v) for v in load_baseline(REPO_ROOT).values())
        assert total <= 400, (
            f"{total} baselined spans — a re-seed absorbed a precision regression. "
            "Fix the checker before re-running --update-baseline."
        )


def _gate_payload(ok: bool, findings: list, count: int | None = None) -> str:
    return json.dumps(
        {
            "ok": ok,
            "mode": "all",
            "count": len(findings) if count is None else count,
            "findings": findings,
        }
    )


class TestGateClassification:
    """Branches of the ENH-3518 gate classifier, without patching subprocess."""

    @staticmethod
    def _finding(n: int = 0) -> dict:
        return {"file": f"f{n}.md", "line": 1, "section": "S", "span": "x", "artifact": "a.md"}

    def test_clean(self) -> None:
        assert _classify_gate_result(0, _gate_payload(True, []), "") == ("clean", "")

    def test_findings_labelled_with_remedies(self) -> None:
        verdict, msg = _classify_gate_result(1, _gate_payload(False, [self._finding()]), "")
        assert verdict == "findings"
        assert msg.startswith(GATE_FAILURE_LABEL)
        assert "ll-evidence-ok" in msg and "correct the attribution" in msg

    def test_truncation_is_reported(self) -> None:
        many = [self._finding(i) for i in range(25)]
        _, msg = _classify_gate_result(1, _gate_payload(False, many), "")
        assert "showing 20 of 25" in msg
        assert "f19.md" in msg and "f20.md" not in msg

    def test_uncaught_exception_exit_1_is_execution_failure_not_findings(self) -> None:
        verdict, msg = _classify_gate_result(1, "", "Traceback (most recent call last):\nboom")
        assert verdict == "execution_failure"
        assert msg.startswith(GATE_FAILURE_LABEL)
        assert "boom" in msg

    @pytest.mark.parametrize(
        ("rc", "stdout"),
        [
            (2, _gate_payload(True, [])),
            (0, "not json"),
            (0, "[]"),
            (0, json.dumps({"ok": "yes", "mode": "all", "count": 0, "findings": []})),
            (0, json.dumps({"ok": True, "mode": "all", "count": "0", "findings": []})),
            (0, json.dumps({"ok": True, "mode": "all", "count": 1, "findings": []})),
            (1, _gate_payload(True, [])),
            (1, _gate_payload(False, [])),
            (0, _gate_payload(False, [{"file": "f.md"}])),
            (1, _gate_payload(False, [{"file": "f.md"}])),
            (
                1,
                _gate_payload(
                    False,
                    [{"file": "f.md", "line": "1", "section": "S", "span": "x", "artifact": "a"}],
                ),
            ),  # noqa: E501
            (
                1,
                _gate_payload(
                    False,
                    [{"file": "f.md", "line": 1, "section": "S", "span": "x", "artifact": "a"}],
                    count=3,
                ),
            ),  # noqa: E501
        ],
    )
    def test_malformed_or_inconsistent_is_execution_failure(self, rc: int, stdout: str) -> None:
        verdict, msg = _classify_gate_result(rc, stdout, "err text")
        assert verdict == "execution_failure"
        assert msg.startswith(GATE_FAILURE_LABEL)
        assert "err text" in msg

    def test_timeout_and_launch_failure_are_labelled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        real_run = subprocess.run

        def make(exc: Exception):  # type: ignore[no-untyped-def]
            def fake(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
                if cmd and cmd[0] == "gate-cli-stub":
                    raise exc
                return real_run(cmd, *args, **kwargs)

            return fake

        gate_test = TestRepoGate().test_no_new_unverifiable_evidence
        for exc, needle in (
            (subprocess.TimeoutExpired("gate-cli-stub", GATE_TIMEOUT), "exceeded"),
            (OSError("no exec"), "could not launch"),
        ):
            monkeypatch.setattr(subprocess, "run", make(exc))
            with pytest.raises(pytest.fail.Exception) as excinfo:
                gate_test("gate-cli-stub")
            assert str(excinfo.value).startswith(GATE_FAILURE_LABEL)
            assert needle in str(excinfo.value)

    def test_gate_test_timeout_exceeds_gate_timeout(self) -> None:
        marks = [
            m
            for m in TestRepoGate.test_no_new_unverifiable_evidence.pytestmark  # type: ignore[attr-defined]
            if m.name == "timeout"
        ]
        assert marks and marks[0].args[0] > GATE_TIMEOUT


class TestBaselineKeying:
    def test_id_resolves_from_filename_when_frontmatter_has_none(self, repo: Path) -> None:
        """34% of this repo's issue files carry no ``id:`` line; keying on
        frontmatter alone left their findings permanently unbaselineable."""
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        body = (
            "## Current Behavior\n\n"
            "See `this phrase does not exist there` (`.issues/enhancements/target.md`).\n"
        )
        rel = Path(".issues/bugs/P2-BUG-4242-no-frontmatter-id.md")
        path = _write(repo, str(rel), body)
        _commit_all(repo)

        config = BRConfig(repo)
        findings, hashes = scan_file(repo, path, config, rel_path=rel)
        assert len(findings) == 1
        assert "4242" in hashes, "filename-anchored numeric ID must key the baseline"

    def test_reseed_does_not_drop_existing_baseline_entries(self, repo: Path, config) -> None:
        """``--update-baseline`` scanned *with* the old baseline and then
        replaced the file. Baselined spans are dropped before matching, so they
        never reached the new hashes and were silently un-grandfathered."""
        _write(repo, ".issues/enhancements/target.md", "nothing relevant here\n")
        body = (
            "---\nid: BUG-7\n---\n\n"
            "## Current Behavior\n\n"
            "See `an absent phrase used as evidence` (`.issues/enhancements/target.md`).\n"
        )
        rel = Path(".issues/bugs/P3-BUG-7-test.md")
        path = _write(repo, str(rel), body)
        _commit_all(repo)

        _, hashes = scan_file(repo, path, config, rel_path=rel)
        write_baseline(repo, hashes)
        first = load_baseline(repo)
        assert first.get("7")

        # A re-seed must reproduce the same grandfathering, not empty it.
        _, reseeded = scan_all(repo, config, ".issues", use_baseline=False)
        assert reseeded.get("7") == first["7"]
