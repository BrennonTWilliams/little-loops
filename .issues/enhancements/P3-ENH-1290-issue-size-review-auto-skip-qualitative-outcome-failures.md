---
captured_at: "2026-04-25T19:07:05Z"
completed_at: 2026-04-26T17:44:59Z
discovered_date: 2026-04-25
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
status: done
---

# ENH-1290: `issue-size-review --auto` should skip decomposition for qualitative outcome failures

## Summary

`issue-size-review --auto` scores issues using purely structural heuristics (file mentions, word count, section count) and decomposes Large/Very Large issues without knowing whether the issue's `outcome_confidence` is low for qualitative reasons — unresolved decisions, absent files — rather than genuine scope bigness. This causes well-scoped issues to be incorrectly fragmented.

## Current Behavior

`issue-size-review` Phase 2 scoring uses:
- File path mentions in issue text (+2)
- Proposed Solution word count >300 (+2)
- Multiple `##` subsections or "additionally" phrases (+3)
- Cross-issue dependency references (+2)
- Total word count >800 (+2)

In `--auto` mode (Phase 5), issues scoring ≥8 (Very Large) are automatically decomposed if the split is "unambiguous". Large issues (5–7) are flagged but skipped.

A well-specified Medium issue that received low `outcome_confidence` scores due to a missing file (`ExtensionSection.jsx` absent) or one unresolved disposal decision (`ScannerSection`) can structurally score Large (e.g., 6) because it has detailed sections, multiple files mentioned, and is well-written. The structural heuristics reward thoroughness, not scope.

When autodev routes such an issue to `run_size_review --auto`, the skill proposes decomposition based on structure alone. The actual problem — a qualitative bottleneck — goes unaddressed.

## Expected Behavior

In `--auto` mode, before decomposing any Large (5–7) issue, `issue-size-review` should check whether `outcome_confidence` and `score_*` fields are present in the issue frontmatter. If they are:

- If `score_ambiguity ≥ 18` (not ambiguous) AND `score_complexity ≥ 18` (not broadly complex): the issue is structurally Large but the confidence failure is qualitative. Skip decomposition and print: `[ID] skipped: structural score N but outcome_confidence low is qualitative (ambiguity: A, complexity: C) — suggest /ll:refine-issue or /ll:wire-issue`
- Otherwise: proceed with normal auto decomposition

For Very Large (≥8) issues, apply the same check but require `score_ambiguity ≥ 18` AND `score_complexity ≥ 18` before skipping (higher bar since Very Large is a stronger structural signal).

This does not affect interactive mode — the user already has the option to decline.

## Motivation

The scenario that prompted this issue: a settings-page ENH issue with `confidence_score: 98` (near-perfect readiness) and `outcome_confidence: 64` (two specific qualitative risks) was routed to size-review by autodev because it hadn't been flagged as a decision. Size-review, seeing a detailed 6-point issue, proposed decomposition. The correct action was one targeted fix (resolve ScannerSection disposal), not three child issues.

Structural scoring is a useful proxy for scope but breaks down when the issue is thorough and well-documented. The fix adds a single guard that prevents the most common false-positive case.

## Proposed Solution

In Phase 5 (Auto Mode Behavior) of `issue-size-review`, before emitting a decomposition action for a Large/Very Large issue:

```python
# Read issue frontmatter
d = read_issue_frontmatter(issue_file)
score_ambiguity = int(d.get('score_ambiguity') or 0)
score_complexity = int(d.get('score_complexity') or 0)
outcome_confidence = int(d.get('outcome_confidence') or 0)

# Guard: qualitative failure — structural decomposition is the wrong fix
if outcome_confidence > 0 and score_ambiguity >= 18 and score_complexity >= 18:
    print(f"[{issue_id}] skipped: structural score {score} but outcome_confidence "
          f"low is qualitative (ambiguity: {score_ambiguity}, complexity: {score_complexity})"
          " — suggest /ll:refine-issue or /ll:wire-issue")
    continue  # skip decomposition for this issue
```

The `score_*` fields are written by `/ll:confidence-check` (Phase 4); if absent (confidence-check was never run), skip the guard and proceed with normal behavior.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

In `SKILL.md` execution context (Claude following instructions), frontmatter is read via the Read tool on the issue file, then the `---` block is parsed inline — not via a Python `read_issue_frontmatter()` call. The established pattern (from `autodev.yaml:386-411`) reads these fields via `ll-issues show --json`, which calls `show.py:114` → `parse_frontmatter(content, coerce_types=True)` → returns integers directly. The safe-default idiom is `int(d.get('score_ambiguity') or 0)` (0 means "treat as absent/unknown").

## API/Interface

N/A — No public API changes. The guard is a conditional block added to Phase 5 of `issue-size-review` SKILL.md; no function signatures, CLI arguments, or data schemas change.

## Integration Map

### Files to Modify
- `skills/issue-size-review/SKILL.md` — Phase 5 Auto Mode Behavior section

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml:413-420` — `run_size_review` state calls `issue-size-review --auto`; benefits from the guard without changes
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:226-227` — `breakdown_issue` state calls `issue-size-review --auto` directly
- `scripts/little_loops/loops/recursive-refine.yaml` — indirect caller: runs `refine-to-ready-issue` as a sub-loop which reaches `breakdown_issue`; benefits transitively

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/sprint-build-and-validate.yaml:32-40` — `size_review` state calls `issue-size-review --auto` for sprint issues; qualitative guard will fire here too, no code change needed
- `scripts/little_loops/loops/issue-size-split.yaml:15-20` — `find_large` state calls `issue-size-review` interactively; unaffected by `--auto` guard (interactive mode unchanged)
- `scripts/little_loops/loops/backlog-flow-optimizer.yaml:99-106` — `fix_oversized` state calls `issue-size-review`; benefits from guard transitively

### Similar Patterns
- `confidence-check` Phase 4.6 signal phrase scan — analogous guard pattern reading frontmatter fields to make a routing decision

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/loops/autodev.yaml:386-411` — `triage_outcome_failure` state: direct precedent; reads `score_ambiguity` via `ll-issues show --json` using `int(d.get('score_ambiguity') or 25)` safe-default pattern (the exact same fields as the proposed guard)
- `skills/confidence-check/SKILL.md:497-515` — Phase 4.6 signal phrase scan: reads frontmatter-backed text content to conditionally set `decision_needed: true`; same guard-at-decision-point structure as the proposed skip

### Tests
- `scripts/tests/test_issue_size_review_skill.py` — add Phase 5 qualitative-guard test cases here
- Fixture pattern: use `_make_issue` from `scripts/tests/test_refine_status.py:19-68` as template — it already accepts `score_ambiguity`, `score_complexity`, and `outcome_confidence`; the version at `test_next_issues.py:19-46` is narrower and does not support score fields. The primary test pattern in `test_issue_size_review_skill.py` is structural content tests (read SKILL.md as text, slice to Phase 5 section, assert on phrases) — no `_make_issue` needed for those. See `TestIssueInfoScoreDimensions` at `scripts/tests/test_issue_parser.py:1841-2011` only if writing integration-level parser tests.
- **Positive fixture**: Large issue (score 6) with `score_ambiguity: 22`, `score_complexity: 20`, `outcome_confidence: 64` → `--auto` emits skip reason, no decomposition action
- **Regression fixture**: Large issue with `score_ambiguity: 8`, `score_complexity: 5`, `outcome_confidence: 64` → guard does NOT fire; normal decomposition path proceeds
- **Absent-fields fixture**: Large issue with no `score_*` frontmatter → guard skipped; existing behavior unchanged

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:267` — `--auto` flag description reads "auto-decomposes issues scoring ≥8 without prompting"; guard adds suppression condition — needs a note about qualitative skip
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:360` — "auto-decomposes only issues scoring >=8" — same incompleteness as COMMANDS.md
- `docs/guides/LOOPS_GUIDE.md:335` — sprint-build-and-validate state table states "Very Large issues (score ≥ 8) are decomposed"; technically inaccurate when guard fires

### Configuration
- N/A — guard uses fields already written by confidence-check

## Implementation Steps

1. In `skills/issue-size-review/SKILL.md:209-210` (Phase 5 Auto Mode Behavior), insert the qualitative-guard block immediately before the existing `AUTO_MODE` decomposition/skip logic
2. Read `score_ambiguity`, `score_complexity`, and `outcome_confidence` from issue frontmatter — in SKILL.md context, use the Read tool on the issue file and parse the `---` block; the `ll-issues show --json` pattern at `autodev.yaml:386-411` is the direct FSM-loop analog for field access
3. Apply threshold: if all three fields present and guard condition holds, emit skip line instead of decomposition
4. Ensure guard does not affect `--check` mode (`SKILL.md:212-214`): Check Mode exits before Phase 5 Auto Mode logic entirely
5. Test with fixtures in `scripts/tests/test_issue_size_review_skill.py` and verify no regression on genuinely oversized issues (low `score_ambiguity` + high structural score should still decompose)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/COMMANDS.md:267` — amend `--auto` flag description to note qualitative-skip: "when `score_ambiguity ≥ 18` and `score_complexity ≥ 18` and `outcome_confidence` is set, Large/Very Large issues are skipped rather than decomposed"
7. Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:360` — same correction to "auto-decomposes only issues scoring >=8" prose
8. Update `docs/guides/LOOPS_GUIDE.md:335` — add footnote to sprint-build-and-validate state table noting the qualitative-skip condition

## Impact

- **Priority**: P3 — secondary fix; the primary fix (ENH-1288 triage) reduces how often autodev even reaches size-review for qualitative failures; this adds a backstop in size-review itself
- **Effort**: Small — adds one conditional block to Phase 5 Auto Mode Behavior
- **Risk**: Low — additive guard; only skips issues that meet all three conditions; no change to normal path
- **Breaking Change**: No

## Scope Boundaries

- Only affects `--auto` mode in Phase 5; interactive mode is unchanged
- Does not change scoring heuristics (Phase 2) or write-back (Phase 3)
- Does not affect `--check` mode
- Does not address cases where `score_*` fields are absent (confidence-check was never run) — those fall through to existing behavior

## Success Metrics

- **False-positive decomposition rate**: 0 — issues with `score_ambiguity ≥ 18`, `score_complexity ≥ 18`, and `outcome_confidence > 0` are skipped in `--auto` mode
- **Regression check**: Issues with low `score_ambiguity` (< 18) and high structural scores still decompose as before
- **Fixture test passes**: Large issue (score 6) with `score_ambiguity: 22`, `score_complexity: 20`, `outcome_confidence: 64` → `--auto` prints skip reason, no decomposition action emitted

## Labels

`enhancement`, `issue-size-review`, `confidence-gate`, `autodev`, `captured`

## Resolution

- Added qualitative-skip guard to Phase 5 Auto Mode in `skills/issue-size-review/SKILL.md`
- Added 10 tests to `scripts/tests/test_issue_size_review_skill.py` covering guard presence, thresholds, skip message format, and mode isolation
- Updated `docs/reference/COMMANDS.md`, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`, and `docs/guides/LOOPS_GUIDE.md` with qualitative-skip documentation

## Session Log
- `/ll:ready-issue` - 2026-04-26T17:41:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/268c69b1-4803-4c7d-b68d-5fc68a4edc44.jsonl`
- `/ll:confidence-check` - 2026-04-26T18:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/473de642-9b42-4807-8fcb-2bad07f17f6a.jsonl`
- `/ll:wire-issue` - 2026-04-26T17:36:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eb4b13a6-5683-4348-b991-8d0ddd6907b6.jsonl`
- `/ll:refine-issue` - 2026-04-26T17:29:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42fabf89-9803-43b2-ae07-b91aa0889500.jsonl`
- `/ll:format-issue` - 2026-04-26T17:18:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c577867-4c4d-4b90-aa25-5065c70baa3c.jsonl`
- `/ll:manage-issue` - 2026-04-26T17:44:59Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/268c69b1-4803-4c7d-b68d-5fc68a4edc44.jsonl`
- `/ll:capture-issue` - 2026-04-25T19:07:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e47d1ef-2bc6-4299-8018-0c5ef506b76e.jsonl`

---

**Open** | Created: 2026-04-25 | Priority: P3
