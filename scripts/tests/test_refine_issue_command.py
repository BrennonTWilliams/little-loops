"""Structural tests for the refine-issue command (ENH-1237).

Verifies that /ll:refine-issue --auto sets `decision_needed: true` in issue
frontmatter when 2+ implementation options are deposited into Proposed Solution,
and that the flag is documented in the expected locations.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
COMMAND_FILE = PROJECT_ROOT / "commands" / "refine-issue.md"
ISSUE_TEMPLATE = PROJECT_ROOT / "docs" / "reference" / "ISSUE_TEMPLATE.md"
COMMANDS_REF = PROJECT_ROOT / "docs" / "reference" / "COMMANDS.md"


class TestOptionCountDetectionInCommand:
    """commands/refine-issue.md must document option-count detection in Step 5a."""

    def test_command_file_exists(self) -> None:
        assert COMMAND_FILE.exists(), "commands/refine-issue.md not found"

    def test_decision_needed_key_in_step_5a(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert "decision_needed" in step_5a_text, (
            "Step 5a must reference `decision_needed` for the option-count detection logic"
        )

    def test_option_count_detection_block_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "Option-Count Detection" in content, (
            "commands/refine-issue.md must contain an Option-Count Detection block in Step 5a"
        )

    def test_two_or_more_threshold_documented(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert ">= 2" in step_5a_text or "2+" in step_5a_text or "count >= 2" in step_5a_text, (
            "Step 5a must document the >= 2 threshold for setting decision_needed: true"
        )

    def test_idempotency_guard_mentioned(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert "Idempotency" in step_5a_text or "idempotent" in step_5a_text.lower(), (
            "Step 5a must document idempotency: skip write if field already has same value"
        )

    def test_dry_run_guard_mentioned(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert "--dry-run" in step_5a_text, (
            "Step 5a must document that the frontmatter write is skipped in --dry-run mode"
        )

    def test_placement_targets_proposed_solution(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert "## Proposed Solution" in step_5a_text, (
            "Step 5a must document that the Option block is placed inside "
            "`## Proposed Solution`, not just 'near the original prose' (BUG-2820)"
        )

    def test_check_decidable_verification_documented(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert "check-decidable" in step_5a_text, (
            "Step 5a must document verifying via `ll-issues check-decidable <ID>` "
            "before setting decision_needed: true (BUG-2820)"
        )

    def test_no_ask_user_question_in_step_5a(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert "AskUserQuestion" not in step_5a_text, (
            "Step 5a must not use AskUserQuestion — option-count write-back is unconditional in auto mode"
        )

    def test_decision_needed_in_file_status_section(self) -> None:
        content = COMMAND_FILE.read_text()
        file_status_start = content.index("## FILE STATUS")
        next_heading = content.find("\n##", file_status_start + 1)
        file_status_text = content[file_status_start:next_heading]
        assert "decision_needed" in file_status_text, (
            "Step 8 FILE STATUS section must surface the decision_needed flag value"
        )

    def test_decision_point_formatting_rule_documented(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5a_text = content[step_5a_start:step_5b_start]
        assert "Decision-Point Formatting" in step_5a_text, (
            "Step 5a must document the Decision-Point Formatting rule that converts "
            "prose recommendations into bold-label option blocks"
        )
        assert "**Option A**" in step_5a_text and "**Recommended**" in step_5a_text, (
            "Step 5a must show the **Option A**/**Recommended** bold-label template "
            "for formatting decision recommendations"
        )


class TestDecisionNeededDocWiring:
    """`decision_needed` must be documented in the issue template reference."""

    def test_decision_needed_in_issue_template(self) -> None:
        content = ISSUE_TEMPLATE.read_text()
        assert "`decision_needed`" in content, (
            "docs/reference/ISSUE_TEMPLATE.md Frontmatter Fields table must include "
            "a `decision_needed` row"
        )

    def test_decision_needed_row_mentions_refine_issue(self) -> None:
        content = ISSUE_TEMPLATE.read_text()
        lines = [line for line in content.splitlines() if "`decision_needed`" in line]
        assert lines, "Expected at least one line referencing `decision_needed`"
        row = next((line for line in lines if line.lstrip().startswith("|")), "")
        assert row, "Expected a table row for `decision_needed`"
        assert "refine-issue" in row or "refine" in row.lower(), (
            "`decision_needed` row must mention refine-issue as the source of this field"
        )

    def test_decision_needed_in_commands_ref(self) -> None:
        content = COMMANDS_REF.read_text()
        assert "decision_needed" in content, (
            "docs/reference/COMMANDS.md must document the `decision_needed` frontmatter "
            "write-back for /ll:refine-issue"
        )

    def test_frontmatter_write_back_note_in_commands_ref(self) -> None:
        content = COMMANDS_REF.read_text()
        refine_start = content.index("### `/ll:refine-issue`")
        next_heading = content.find("\n###", refine_start + 1)
        refine_text = content[refine_start:next_heading]
        assert "Frontmatter write-back" in refine_text, (
            "docs/reference/COMMANDS.md /ll:refine-issue entry must include a "
            "'Frontmatter write-back' note (follow issue-size-review pattern at line 249)"
        )


class TestGapAnalysisMode:
    """commands/refine-issue.md must document the --gap-analysis and --full-rewrite flags."""

    def _section_5c_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("### 5c. Gap-Analysis Mode")
        next_heading = content.find("\n### 6.", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_gap_analysis_flag_in_step_0(self) -> None:
        content = COMMAND_FILE.read_text()
        step_0_start = content.index("### 0. Parse Flags")
        step_1_start = content.index("### 1. Locate Issue File")
        step_0_text = content[step_0_start:step_1_start]
        assert "--gap-analysis" in step_0_text, (
            "Step 0 Parse Flags must detect the --gap-analysis flag"
        )

    def test_full_rewrite_flag_in_step_0(self) -> None:
        content = COMMAND_FILE.read_text()
        step_0_start = content.index("### 0. Parse Flags")
        step_1_start = content.index("### 1. Locate Issue File")
        step_0_text = content[step_0_start:step_1_start]
        assert "--full-rewrite" in step_0_text, (
            "Step 0 Parse Flags must detect the --full-rewrite flag"
        )

    def test_section_5c_exists_after_5b(self) -> None:
        content = COMMAND_FILE.read_text()
        pos_5b = content.index("### 5b. Interactive Refinement")
        pos_5c = content.index("### 5c. Gap-Analysis Mode")
        assert pos_5c > pos_5b, (
            "### 5c. Gap-Analysis Mode must appear after ### 5b. Interactive Refinement"
        )

    def test_additive_only_contract_documented(self) -> None:
        text = self._section_5c_text()
        assert "never removes" in text.lower() or "additive" in text.lower(), (
            "Section 5c must document the additive-only contract (never removes existing content)"
        )

    def test_max_refine_count_exemption_documented(self) -> None:
        text = self._section_5c_text()
        assert "max_refine_count" in text, (
            "Section 5c must document that gap-analysis runs are exempt from max_refine_count"
        )

    def test_gap_analysis_in_examples(self) -> None:
        content = COMMAND_FILE.read_text()
        examples_start = content.index("## Examples")
        examples_text = content[examples_start:]
        assert "--gap-analysis" in examples_text, (
            "Examples section must include a --gap-analysis example"
        )

    def test_full_rewrite_in_examples(self) -> None:
        content = COMMAND_FILE.read_text()
        examples_start = content.index("## Examples")
        examples_text = content[examples_start:]
        assert "--full-rewrite" in examples_text, (
            "Examples section must include a --full-rewrite example"
        )


class TestSupersededDirectiveMarker:
    """Preservation Rule must document the `> ⚠ Superseded — ...` annotation
    carve-out (ENH-2995): annotate-only, three directive sections, same-pass
    refutation, idempotent, and the bounded marker-removal right.
    """

    def _preservation_rule_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("#### Preservation Rule")
        end = content.index("### 5b. Interactive Refinement")
        return content[start:end]

    def test_superseded_marker_documented(self) -> None:
        text = self._preservation_rule_text()
        assert "⚠ Superseded" in text, (
            "Preservation Rule must document the `> ⚠ Superseded — ...` marker text"
        )

    def test_scope_limited_to_three_directive_sections(self) -> None:
        text = self._preservation_rule_text()
        for section in ("Implementation Steps", "Files to Modify", "Acceptance Criteria"):
            assert section in text, (
                f"Preservation Rule must scope the carve-out to include `{section}`"
            )

    def test_annotate_only_never_edit_documented(self) -> None:
        text = self._preservation_rule_text()
        assert "annotate" in text.lower(), (
            "Preservation Rule must state the carve-out is annotation-only, never "
            "editing the refuted line's own text"
        )

    def test_same_pass_only_documented(self) -> None:
        text = self._preservation_rule_text()
        assert "same pass" in text.lower() or "this pass" in text.lower(), (
            "Preservation Rule must restrict the carve-out to findings from the "
            "current refine pass, not prior appended blocks"
        )

    def test_idempotency_via_substring_containment_documented(self) -> None:
        text = self._preservation_rule_text()
        assert "idempotent" in text.lower(), (
            "Preservation Rule must document idempotency for the superseded marker"
        )

    def test_marker_removal_right_documented(self) -> None:
        text = self._preservation_rule_text()
        assert "remove" in text.lower() or "delet" in text.lower(), (
            "Preservation Rule must document the bounded marker-removal right "
            "(a marker is the one deletable line when its refutation no longer holds)"
        )


class TestGapAnalysisEmissionIdempotency:
    """Command must document heading-containment and lazy-emission (BUG-3245):
    a retry pass must not duplicate `### Call Path` / `### Dependent Files
    (Callers/Importers)` headings, nor emit a provenance stub with no findings.
    """

    def _enrichment_and_preservation_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("#### Enrichment Rules")
        end = content.index("### 5b. Interactive Refinement")
        return content[start:end]

    def test_call_path_and_dependent_files_headings_named(self) -> None:
        text = self._enrichment_and_preservation_text()
        assert "### Call Path" in text
        assert "### Dependent Files (Callers/Importers)" in text

    def test_containment_check_before_heading_emission_documented(self) -> None:
        text = self._enrichment_and_preservation_text()
        assert "Heading Containment Check" in text
        assert "duplicate" in text.lower(), (
            "must state that a second `### Call Path` / `### Dependent Files "
            "(Callers/Importers)` heading is never created within the same H2"
        )

    def test_append_beneath_existing_heading_documented(self) -> None:
        text = self._enrichment_and_preservation_text()
        assert "append" in text.lower(), (
            "must instruct appending under an existing heading instead of "
            "emitting a sibling"
        )

    def test_lazy_emission_rule_documented(self) -> None:
        text = self._enrichment_and_preservation_text()
        assert "Lazy emission" in text, (
            "must restate that a pass with no findings emits no heading, "
            "provenance stub, or blank placeholder"
        )

    def test_fold_findings_still_the_only_route_for_findings_blocks(self) -> None:
        text = self._enrichment_and_preservation_text()
        assert "ll-issues fold-findings" in text


class TestRefineIssueHistoryContextInjection:
    """commands/refine-issue.md must document Step 2.5 historical context query (ENH-1847)."""

    def _phase_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("### 2.5 — Query Historical Context")
        next_heading = content.find("\n### 3.", start + 1)
        end = next_heading if next_heading != -1 else len(content)
        return content[start:end]

    def test_step_2_5_heading_exists(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "### 2.5 — Query Historical Context" in content, (
            "commands/refine-issue.md must contain a '### 2.5 — Query Historical Context' section"
        )

    def test_ll_history_context_command_present(self) -> None:
        assert "ll-history-context" in self._phase_text(), (
            "Step 2.5 must include the ll-history-context command invocation"
        )

    def test_hist_variable_in_step_2_5(self) -> None:
        assert "HIST" in self._phase_text(), (
            "Step 2.5 must assign ll-history-context output to HIST variable"
        )

    def test_graceful_degradation_mentioned(self) -> None:
        text = self._phase_text()
        assert "missing" in text.lower() or "absent" in text.lower() or "DB" in text, (
            "Step 2.5 must mention graceful degradation when DB is missing or no matches"
        )


class TestResearchTriageWiring:
    """Step 3 must condition its spawn set on `ll-issues research-triage` (ENH-2971)."""

    def _step_3_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("### 3. Research Codebase")
        end = content.index("### 4. Identify Knowledge Gaps")
        return content[start:end]

    def test_triage_cli_invoked(self) -> None:
        assert "ll-issues research-triage" in self._step_3_text(), (
            "Step 3 must call `ll-issues research-triage` before spawning research agents"
        )

    def test_spawn_set_is_conditioned_on_triage(self) -> None:
        text = self._step_3_text()
        assert "covered" in text, "Step 3 must branch on the triage output's `covered` field"
        assert "Spawn exactly one Task per axis whose `covered` is `false`" in text, (
            "Step 3 must instruct spawning one agent per uncovered axis, not all three"
        )
        assert "Spawn all 3 agents in a SINGLE message" not in text, (
            "the unconditional 3-agent spawn instruction must be gone from Step 3"
        )

    def test_full_rewrite_preserves_unconditional_spawn(self) -> None:
        text = self._step_3_text()
        assert "FULL_REWRITE" in text, (
            "Step 3 must exempt --full-rewrite from triage (a full rewrite does not "
            "trust existing content)"
        )

    def test_cli_failure_falls_back_to_all_three(self) -> None:
        text = self._step_3_text().lower()
        assert "fail open" in text or "fail-open" in text, (
            "Step 3 must fail open to all three agents when the triage CLI fails"
        )

    def test_zero_unmet_axes_branch_present(self) -> None:
        text = self._step_3_text()
        assert "#### 3.1" in text, "Step 3 must contain the zero-unmet-axes branch as 3.1"
        for step in ("4", "5a", "5b"):
            assert step in text, f"the 3.1 branch must name Step {step} as skipped"
        assert "Session Log" in text, (
            "a no-op refine must still append its Session Log entry, or callers cannot "
            "distinguish it from a silent failure"
        )

    def test_program_design_gate_override_documented(self) -> None:
        """BUG-3003: a failing Program Design gate forces the analyzer axis unmet."""
        text = self._step_3_text()
        assert "Program Design gate" in text, (
            "Step 3.0 must document that a failing Program Design gate forces the "
            "analyzer axis unmet"
        )
        step_3_0, step_3_1 = text.split("#### 3.1", 1)
        assert "Program Design gate" in step_3_0, (
            "the gate-override sentence belongs in Step 3.0, where the triage output is documented"
        )
        assert "cannot be reached while the section is missing or non-specific" in step_3_1, (
            "Step 3.1's no-op branch needs a carve-out: on a gate-active project this "
            "branch cannot be reached while Program Design is missing/non-specific"
        )

    def test_step_4_guards_against_absent_findings(self) -> None:
        content = COMMAND_FILE.read_text()
        start = content.index("### 4. Identify Knowledge Gaps")
        end = content.index("### 5a.")
        assert "3.1" in content[start:end], (
            "Step 4 must skip when Step 3.1 applied — with no research findings there is "
            "nothing to identify gaps against"
        )


class TestProgramDesignGapTaxonomy:
    """Step 4's gap tables must name types/signatures/call path (BUG-3001)."""

    def _step_4_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("### 4. Identify Knowledge Gaps")
        end = content.index("### 5a.")
        return content[start:end]

    def test_all_three_gap_tables_name_types_signatures_call_path(self) -> None:
        text = self._step_4_text()
        assert text.count("Types/signatures/call path") == 3, (
            "each of the BUG/FEAT/ENH gap tables must carry a "
            "'Types/signatures/call path' row sourced from codebase-analyzer, "
            "or Program Design is never marked FILLABLE"
        )


class TestProgramDesignEnrichmentRule:
    """Step 5a must write `## Program Design` from analyzer findings (BUG-3001)."""

    def _step_5a_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("### 5a. Fill Gaps with Research Findings")
        end = content.index("### 5b. Interactive Refinement")
        return content[start:end]

    def test_program_design_enrichment_block_present(self) -> None:
        text = self._step_5a_text()
        assert "## Program Design" in text, (
            "Step 5a must document an enrichment rule that writes ## Program Design"
        )
        assert "### Types" in text and "### Signatures" in text and "### Call Path" in text, (
            "the Program Design enrichment rule must emit the template's three subheadings"
        )

    def test_not_applicable_recommendation_documented(self) -> None:
        text = self._step_5a_text()
        assert "program_design_not_applicable" in text, (
            "Step 5a must document recommending program_design_not_applicable "
            "when research cannot produce a design"
        )

    def test_refine_never_sets_the_opt_out_flag_itself(self) -> None:
        text = self._step_5a_text()
        lowered = text.lower()
        assert "never set this frontmatter field directly" in lowered or (
            "must not write it" in lowered
        ), (
            "Step 5a must explicitly state that refine recommends but never sets "
            "program_design_not_applicable — that is a human decision"
        )


class TestProgramDesignGateExtension:
    """Step 6.7 must read program_design_nonspecific (BUG-3001)."""

    def _gate_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("### 6.7. Prose Dependency & Program Design Gate")
        end = content.index("### 7.5. Extract Learning Targets")
        return content[start:end]

    def test_program_design_nonspecific_key_read(self) -> None:
        assert "program_design_nonspecific" in self._gate_text(), (
            "Step 6.7 must inspect the program_design_nonspecific key from "
            "`ll-issues format-check --format json`, alongside prose_dep_drift/stale_prose_dep"
        )

    def test_single_revision_attempt_documented(self) -> None:
        text = self._gate_text().lower()
        assert "once" in text, (
            "Step 6.7 must document a single revision attempt, not an unbounded retry loop"
        )

    def test_still_failing_gap_reported_not_opted_out(self) -> None:
        text = self._gate_text()
        assert "report the still-failing gap" in text, (
            "a still-failing Program Design gap must be reported explicitly in Step 8's output"
        )
        assert (
            "do not touch" in text.lower() or "not touch `program_design_not_applicable`" in text
        ), (
            "Step 6.7 must state that refine does not set program_design_not_applicable "
            "even when the gate still fails after the one revision attempt"
        )


class TestSoftDepHardEdgeAndContradictionGate:
    """Step 6.7 must read soft_dep_hard_edge and run the AC-vs-Design pass (ENH-3046)."""

    def _gate_text(self) -> str:
        content = COMMAND_FILE.read_text()
        start = content.index("### 6.7. Prose Dependency & Program Design Gate")
        end = content.index("### 7.5. Extract Learning Targets")
        return content[start:end]

    def test_soft_dep_hard_edge_key_read(self) -> None:
        assert "soft_dep_hard_edge" in self._gate_text(), (
            "Step 6.7 must inspect the soft_dep_hard_edge key from "
            "`ll-issues format-check --format json`"
        )

    def test_soft_dep_hard_edge_remedy_moves_to_relates_to_not_deletes_prose(self) -> None:
        text = self._gate_text()
        assert "relates_to" in text, "remedy must move the ID to relates_to"
        assert "do not delete the soft-dependency prose" in text, (
            "remedy must explicitly preserve the soft-dependency prose, not delete it"
        )

    def test_ac_vs_program_design_contradiction_pass_documented(self) -> None:
        text = self._gate_text()
        assert "Acceptance Criteria" in text and "Program Design" in text
        assert "report only" in text.lower() or "never auto-applied" in text.lower(), (
            "the AC-vs-Program-Design pass must be documented as report-only"
        )


class TestSessionLogPrecedesProgramDesignGate:
    """Session Log append must precede the gate check that reads it (BUG-3001).

    program_design_gate_active() derives arming from the most recent
    `/ll:refine-issue` Session Log entry — checking the gate first would read a
    grandfathered issue as still grandfathered and declare success without
    ever writing a design.
    """

    def test_session_log_heading_precedes_gate_heading(self) -> None:
        content = COMMAND_FILE.read_text()
        session_log_idx = content.index("### 6.5. Append Session Log")
        gate_idx = content.index("### 6.7. Prose Dependency & Program Design Gate")
        assert session_log_idx < gate_idx, (
            "the Session Log append step must appear before the Prose/Program "
            "Design Gate step in commands/refine-issue.md"
        )

    def test_gate_step_references_ordering_rationale(self) -> None:
        content = COMMAND_FILE.read_text()
        start = content.index("### 6.5. Append Session Log")
        end = content.index("### 6.7. Prose Dependency & Program Design Gate")
        text = content[start:end]
        assert "program_design_gate_active" in text, (
            "Step 6.5 must explain why the Session Log append precedes the gate check"
        )


class TestDependencyClassificationInStep5a:
    """commands/refine-issue.md must document the blocked_by-vs-relates_to
    dependency-classification/promotion rule (ENH-3284): a fresh finding that
    names another open issue as affecting *how or whether* this issue's
    mechanism works is promoted to `blocked_by` at deposit time via
    `ll-issues link`, rather than left as prose for Step 6.7's reactive
    `prose_dep_drift` gate to maybe catch.
    """

    def _step_5a_text(self) -> str:
        content = COMMAND_FILE.read_text()
        step_5a_start = content.index("### 5a. Fill Gaps with Research Findings")
        step_5b_start = content.index("### 5b. Interactive Refinement")
        return content[step_5a_start:step_5b_start]

    def _dependency_classification_text(self) -> str:
        text = self._step_5a_text()
        start = text.index("Dependency Classification")
        return text[start:]

    def test_dependency_classification_block_present(self) -> None:
        assert "Dependency Classification" in self._step_5a_text(), (
            "Step 5a must contain a Dependency Classification block"
        )

    def test_discriminator_documented(self) -> None:
        text = self._dependency_classification_text()
        assert "relates_to" in text and "blocked_by" in text, (
            "Dependency Classification block must name both `relates_to` and `blocked_by`"
        )
        assert "does not work until that issue lands" in text, (
            "Dependency Classification block must state the correctness-based "
            "blocked_by-vs-relates_to discriminator verbatim"
        )

    def test_link_promotion_call_documented(self) -> None:
        text = self._dependency_classification_text()
        assert "ll-issues link" in text and "blocked_by" in text, (
            "Dependency Classification block must document promoting via "
            "`ll-issues link [ID] blocked_by [BLOCKER-ID]`"
        )
        assert "--unlink" in text, (
            "Dependency Classification block must document the --unlink move form "
            "for a blocker ID already sitting in relates_to"
        )

    def test_cycle_refusal_branch_documented(self) -> None:
        text = self._dependency_classification_text()
        assert "cycle" in text.lower(), (
            "Dependency Classification block must document the cycle-refusal branch"
        )
        assert "--force" in text, (
            "Dependency Classification block must state that cycle refusal is not "
            "retried and --force is not used"
        )

    def test_dry_run_guard_documented(self) -> None:
        text = self._dependency_classification_text()
        assert "--dry-run" in text, (
            "Dependency Classification block must document the --dry-run skip"
        )

    def test_canonical_phrasing_companion_documented(self) -> None:
        text = self._dependency_classification_text()
        assert "companion" in text.lower(), (
            "Dependency Classification block must state canonical prose phrasing is "
            "a companion to the frontmatter write, not the promotion mechanism"
        )

    def test_ambiguous_default_to_relates_to_documented(self) -> None:
        text = self._dependency_classification_text()
        assert "Ordering check" in text, (
            "Dependency Classification block must document the ambiguous-middle "
            "default (relates_to plus an `Ordering check:` note)"
        )

    def test_reachable_from_interactive_mode(self) -> None:
        content = COMMAND_FILE.read_text()
        step_5b_start = content.index("### 5b. Interactive Refinement")
        step_5c_start = content.index("### 5c. Gap-Analysis Mode")
        step_5b_text = content[step_5b_start:step_5c_start]
        assert "Dependency Classification" in step_5b_text, (
            "Step 5b must reference the Dependency Classification rule so it is "
            "reachable from interactive mode too, not only Auto Mode's Step 5a"
        )
