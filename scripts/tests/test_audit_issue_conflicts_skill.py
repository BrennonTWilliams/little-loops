"""Structural tests for the audit-issue-conflicts skill (FEAT-1031)."""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = PROJECT_ROOT / "skills" / "audit-issue-conflicts" / "SKILL.md"

# Binaries this skill's fenced ```bash blocks are known to invoke as of
# ENH-2845. If a new interpreter/binary is introduced in a fenced block, this
# set (and the matching `allowed-tools` entry) must grow alongside it.
_KNOWN_FENCED_BINARIES = ("git", "ll-issues", "python3")


class TestAuditIssueConflictsSkillExists:
    """Verify the audit-issue-conflicts skill file is present and well-formed."""

    def test_skill_file_exists(self) -> None:
        """Skill file must be present."""
        assert SKILL_FILE.exists(), "Skill file not found"

    def test_dry_run_flag(self) -> None:
        """Skill must document --dry-run flag."""
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "--dry-run" in SKILL_FILE.read_text()

    def test_auto_flag(self) -> None:
        """Skill must document --auto flag."""
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "--auto" in SKILL_FILE.read_text()

    def test_severity_labels(self) -> None:
        """Skill must reference high, medium, and low severity labels."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        for label in ("high", "medium", "low"):
            assert label in content

    def test_conflict_types(self) -> None:
        """Skill must reference all four conflict type tokens."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        for ctype in ("requirement", "objective", "architecture", "scope"):
            assert ctype in content

    def test_no_conflicts_path(self) -> None:
        """Skill must document the no-conflicts output path."""
        assert SKILL_FILE.exists(), "Skill file not found"
        # NOTE: SKILL.md uses "No conflicts detected" (not "No conflicts found")
        assert "No conflicts detected" in SKILL_FILE.read_text()

    def test_config_issues_base_dir_glob(self) -> None:
        """Skill must reference the config.issues.base_dir glob pattern."""
        assert SKILL_FILE.exists(), "Skill file not found"
        assert "{{config.issues.base_dir}}" in SKILL_FILE.read_text()

    def test_phase1_filters_by_status(self) -> None:
        """Phase 1 must filter to open|in_progress|blocked via ll-issues list --json
        piped through python3, not awk or a bare find (BUG-1799, ENH-2845)."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "awk '/^---$/{n++; next} n==1 && /^status:/" not in content, (
            "Phase 1 must not parse frontmatter status with awk (ENH-2845)"
        )
        assert "active = {'open', 'in_progress', 'blocked'}" in content
        assert "TERMINAL_COUNT" in content
        assert "excluded $TERMINAL_COUNT terminal issues" in content

    def test_phase5_stages_only_modified_files(self) -> None:
        """Phase 5 must stage via git add -u, not a non-persistent bash array
        that cannot survive across separate Bash tool calls (BUG-1800, ENH-2845)."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "MODIFIED_FILES=()" not in content, (
            "Phase 4b/5 must not track state in a MODIFIED_FILES array — it cannot "
            "persist across separate Bash tool invocations (ENH-2845)"
        )
        assert "MODIFIED_FILES+=(" not in content
        assert 'for f in "${MODIFIED_FILES[@]}"; do' not in content
        assert "git add -u {{config.issues.base_dir}}/" in content
        assert "git add {{config.issues.base_dir}}/" not in content

    def test_phase2b_cross_theme_header_present(self) -> None:
        """Phase 2b cross-theme section must be present in the skill (ENH-1801)."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "Phase 2b" in content
        assert "--cross-theme" in content

    def test_phase2b_uses_fingerprint_subcommand(self) -> None:
        """Phase 2b must reference the ll-issues fingerprint subcommand (ENH-1801)."""
        assert SKILL_FILE.exists(), "Skill file not found"
        content = SKILL_FILE.read_text()
        assert "ll-issues fingerprint" in content

    def test_phase4b_idempotency_guard_present(self) -> None:
        """Phase 4b must document idempotency rule for Scope Boundary/Addition/Resolution (ENH-1802)."""
        content = SKILL_FILE.read_text()
        phase4b_start = content.index("## Phase 4b")
        phase5_start = content.index("## Phase 5")
        phase4b_text = content[phase4b_start:phase5_start]
        assert "idempotent" in phase4b_text.lower(), (
            "Phase 4b must document idempotency pre-check for audit-authored section appends"
        )

    def test_phase4b_write_side_guard_present(self) -> None:
        """Phase 4b must guard writes to non-active targets (BUG-2264), re-checking
        live status via ll-issues show --json's raw_status (uncased), not a bash
        array or an awk frontmatter parse that can't persist across Bash calls
        (ENH-2845)."""
        content = SKILL_FILE.read_text()
        phase4b_start = content.index("## Phase 4b")
        phase5_start = content.index("## Phase 5")
        phase4b_text = content[phase4b_start:phase5_start]
        assert "active issues collected in Phase 1" in phase4b_text, (
            "Phase 4b must reference the active-issue roster from Phase 1"
        )
        assert "ll-issues show" in phase4b_text and "raw_status" in phase4b_text, (
            "Phase 4b must re-check status via ll-issues show --json's raw_status"
        )
        assert "not in active set" in phase4b_text, "Phase 4b must log skip reason"

    def test_phase4b_supersession_uses_cancelled_not_done(self) -> None:
        """Phase 4b merge/deprecate must close via cancelled + supersedes edge, not done (BUG-2844)."""
        content = SKILL_FILE.read_text()
        phase4b_start = content.index("## Phase 4b")
        phase5_start = content.index("## Phase 5")
        phase4b_text = content[phase4b_start:phase5_start]
        assert "Closed - Superseded" not in phase4b_text, (
            "Phase 4b must not write the non-canonical 'Closed - Superseded' status prose"
        )
        assert "status: done using the Edit tool" not in phase4b_text, (
            "Phase 4b must not hand-edit frontmatter status: done for a superseded issue"
        )
        assert "set-status" in phase4b_text and "cancelled" in phase4b_text, (
            "Phase 4b must close superseded issues via ll-issues set-status ... cancelled"
        )
        assert "--reason" in phase4b_text and "superseded" in phase4b_text, (
            "Phase 4b must stamp closed_reason: superseded"
        )
        assert "supersedes:" in phase4b_text, (
            "Phase 4b must write the supersedes: edge onto the kept issue"
        )

    def test_add_dependency_uses_ll_issues_link(self) -> None:
        """add_dependency must write edges via ll-issues link, not a raw Edit
        (FEAT-2842) — the CLI is idempotent/list-aware/validating, unlike a
        free-form frontmatter Edit."""
        content = SKILL_FILE.read_text()
        section_start = content.index("### add_dependency")
        next_section = content.index("### split / update_scope")
        section_text = content[section_start:next_section]
        assert "ll-issues link" in section_text, (
            "add_dependency must reference the ll-issues link CLI"
        )
        assert "using Edit" not in section_text, (
            "add_dependency must not instruct a raw frontmatter Edit for dependency fields"
        )

    def test_allowed_tools_covers_fenced_block_binaries(self) -> None:
        """Every interpreter/binary invoked in a ```bash fenced block must have
        a matching Bash(<binary>:*) entry in the frontmatter allowed-tools
        (ENH-2845) — generalizes test_issue_size_review_skill.py's
        test_edit_in_allowed_tools single-token check into a real diff."""
        content = SKILL_FILE.read_text()
        fm_end = content.index("\n---", content.index("---") + 3)
        frontmatter = content[:fm_end]
        declared = set(re.findall(r"Bash\((\w[\w.-]*):\*\)", frontmatter))

        fenced_blocks = re.findall(r"```bash\n(.*?)```", content, re.DOTALL)
        invoked = set()
        for block in fenced_blocks:
            for binary in _KNOWN_FENCED_BINARIES:
                if re.search(rf"(^|[|(`\s]){re.escape(binary)}\b", block, re.MULTILINE):
                    invoked.add(binary)

        assert invoked, "Expected at least one known binary in a fenced bash block"
        missing = invoked - declared
        assert not missing, (
            f"allowed-tools is missing Bash(<binary>:*) entries for: {sorted(missing)}"
        )

    def test_phase4_phase6_auto_mode_low_severity_agree(self) -> None:
        """Phase 4 and Phase 6 must state the same --auto low-severity policy —
        historically Phase 4 said 'apply all' while Phase 6's example implied
        low severity is skipped in auto mode (ENH-2845)."""
        content = SKILL_FILE.read_text()
        phase4_start = content.index("## Phase 4:")
        phase4b_start = content.index("## Phase 4b")
        phase4_text = content[phase4_start:phase4b_start]
        phase6_start = content.index("## Phase 6")
        phase6_text = content[phase6_start:]

        assert "regardless of severity" in phase4_text, (
            "Phase 4 auto-mode section must state severity is not a skip condition"
        )
        assert "low severity, skipped in auto mode" not in phase6_text, (
            "Phase 6 must not contradict Phase 4's auto-mode-applies-all-severities policy"
        )
        assert "`--auto` applies every severity" in phase6_text

    def test_phase6_skipped_inactive_count_reported(self) -> None:
        """Phase 6 must report SKIPPED_INACTIVE_COUNT for write-side guard skips (BUG-2264)."""
        content = SKILL_FILE.read_text()
        phase6_start = content.index("## Phase 6")
        phase6_text = content[phase6_start:]
        assert "SKIPPED_INACTIVE_COUNT" in phase6_text, "Phase 6 must tally skipped inactive writes"
        assert "Skipped (target not active)" in phase6_text, "Phase 6 must label the skip category"


class TestAuditIssueConflictsEpicScoping:
    """Verify the optional positional EPIC-scoping argument (ENH-2634)."""

    def _phase(self, start_header: str, end_header: str) -> str:
        content = SKILL_FILE.read_text()
        return content[content.index(start_header) : content.index(end_header)]

    def test_argument_hint_documents_epic_positional(self) -> None:
        """Frontmatter argument-hint must document the optional [EPIC-NNNN] positional."""
        content = SKILL_FILE.read_text()
        # Only inspect the YAML frontmatter block (between the first two '---').
        fm_end = content.index("\n---", content.index("---") + 3)
        frontmatter = content[:fm_end]
        assert "EPIC-NNNN" in frontmatter, "argument-hint must document [EPIC-NNNN]"

    def test_phase0_parses_scope_epic_positional(self) -> None:
        """Phase 0 must parse the positional argument into SCOPE_EPIC."""
        phase0 = self._phase("## Phase 0", "## Phase 1")
        assert "SCOPE_EPIC" in phase0, "Phase 0 must bind a SCOPE_EPIC variable"

    def test_phase0_aborts_on_non_epic_argument(self) -> None:
        """Phase 0 must abort with a clear message when the positional is not a valid EPIC."""
        phase0 = self._phase("## Phase 0", "## Phase 1")
        assert "not an EPIC" in phase0 or "not a valid EPIC" in phase0, (
            "Phase 0 must abort with a clear message on a non-EPIC positional"
        )

    def test_phase1_scopes_via_parent(self) -> None:
        """Phase 1 must scope to the EPIC's transitive children via ll-issues list --parent."""
        phase1 = self._phase("## Phase 1", "## Phase 2")
        assert "SCOPE_EPIC" in phase1, "Phase 1 must branch on SCOPE_EPIC"
        assert "--parent" in phase1, "Phase 1 must use ll-issues list --parent for scoping"

    def test_phase1_unscoped_load_includes_epics(self) -> None:
        """Phase 1's unscoped load must include EPIC files (no --type filter),
        not a directory glob (ENH-2845 removed the bare bash for-loop over
        bugs/features/enhancements/epics dirs in favor of ll-issues list --json)."""
        phase1 = self._phase("## Phase 1", "## Phase 2")
        assert "ll-issues list --status all --json" in phase1
        assert "fingerprinted too (ENH-2634)" in phase1, (
            "Phase 1 must still document that epics/ is covered so EPIC files are fingerprinted"
        )
