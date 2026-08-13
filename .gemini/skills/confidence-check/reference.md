# Confidence Check — Output, Integration & Examples

Companion to `SKILL.md` (extracted per the ENH-494 500-line companion pattern).

## Output Format

Emit the single-issue report (`CONFIDENCE CHECK: [ISSUE-ID]` banner, READINESS
SCORES table, OUTCOME CONFIDENCE SCORES table, SUMMARY, RECOMMENDATION, and the
conditional Concerns / Gaps to Address / Escalation / Outcome Risk Factors
subsections). See [rubric.md](rubric.md) for the exact output-format template.

## Batch Output Format (--all mode)

When processing all issues, output a summary table after all individual
evaluations (`CONFIDENCE CHECK BATCH REPORT` banner, READINESS SUMMARY, OUTCOME
CONFIDENCE SUMMARY, RESULTS table, FRONTMATTER UPDATES). See
[rubric.md](rubric.md) for the exact batch output-format template.

## Integration with /ll:manage-issue

This skill is referenced in `/ll:manage-issue` Phase 2 as a recommended pre-planning step. When invoked within manage-issue:

- Uses research findings from Phase 1.5 (no redundant searching)
- Readiness score >=70: proceed to plan creation
- Readiness score <70: stop and report gaps (manage-issue marks as INCOMPLETE)
- Non-blocking by default — can be skipped if user prefers
- The manage-issue Phase 2.5 confidence gate reads `confidence_score` (readiness) from frontmatter — the `outcome_confidence` field is informational and does not affect the gate

## Examples

See [rubric.md](rubric.md) for worked examples: the single-issue scenario table,
the Criterion D Pattern A vs Pattern B walkthroughs, the Criterion A
Breadth × Depth walkthroughs, and the CLI usage patterns.

## Additional Resources

- [rubric.md](rubric.md) — full scoring rubric tables (Phase 2 readiness
  criteria, Phase 2b outcome criteria, Phase 3 score-to-recommendation tables),
  the single-issue and `--all` output-format templates, and worked examples.
