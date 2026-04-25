---
captured_at: "2026-04-25T19:07:05Z"
discovered_date: 2026-04-25
discovered_by: capture-issue
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

## Integration Map

### Files to Modify
- `skills/issue-size-review/SKILL.md` — Phase 5 Auto Mode Behavior section

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml` — calls `run_size_review`; benefits from the guard without changes
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — may also call `issue-size-review`; same benefit

### Similar Patterns
- `confidence-check` Phase 4.6 signal phrase scan — analogous guard pattern reading frontmatter fields to make a routing decision

### Tests
- TBD — fixture: Large issue (score 6) with `score_ambiguity: 22`, `score_complexity: 20`, `outcome_confidence: 64`
- Expected: `--auto` skips decomposition, prints skip reason

### Documentation
- N/A

### Configuration
- N/A — guard uses fields already written by confidence-check

## Implementation Steps

1. In Phase 5 Auto Mode of `issue-size-review` SKILL.md, add the qualitative-guard check before emitting a decomposition action
2. Read `score_ambiguity`, `score_complexity`, and `outcome_confidence` from issue frontmatter using the same YAML parsing already used for `size` write-back
3. Apply threshold: if all three fields present and the guard condition holds, emit skip line instead of decomposition
4. Ensure guard does not affect `--check` mode (check mode only scores, doesn't decompose)
5. Test with the fixture and verify no regression on genuinely oversized issues (low `score_ambiguity` + high structural score should still decompose)

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

## Labels

`enhancement`, `issue-size-review`, `confidence-gate`, `autodev`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-25T19:07:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e47d1ef-2bc6-4299-8018-0c5ef506b76e.jsonl`

---

**Open** | Created: 2026-04-25 | Priority: P3
