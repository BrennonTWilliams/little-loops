---
id: ENH-1859
type: ENH
priority: P3
status: done
captured_at: '2026-06-01T17:35:32Z'
completed_at: '2026-06-01T20:22:38Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
relates_to:
- FEAT-1737
- FEAT-1855
- FEAT-1856
parent: EPIC-1864
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1859: `/ll:review-sprint` EPIC awareness — flag sprints that bypass EPIC critical path

## Summary

Extend `/ll:review-sprint` to detect when a sprint includes children of one or more EPICs and audit the sprint against the EPIC's critical path. Flag sprints that touch EPIC-X children but skip its known blockers, or that include children of competing EPICs without coordination.

## Current Behavior

`/ll:review-sprint` audits a sprint as a flat issue list. It identifies stale issues, dependency conflicts inside the sprint, and rough sizing concerns. It has no EPIC awareness — a sprint that contains 3 children of EPIC-1773 but skips the critical-path blocker is rated identically to a sprint that includes the blocker.

`ll-sprint <EPIC-ID>` (FEAT-1737, done) resolves an entire EPIC as a sprint, but explicitly-curated sprints can include EPIC children without surfacing the relationship.

## Expected Behavior

When auditing a sprint, the skill also produces an EPIC-context section:

```
## EPIC context

This sprint touches 2 EPICs:

### EPIC-1773 (Audit & simplify FSM loops)
- Sprint includes: ENH-1820, ENH-1774
- EPIC blocker not in sprint: ENH-1641 (24d stalled, blocks ENH-1820)
  Recommendation: add ENH-1641 to the sprint or defer ENH-1820

### EPIC-1713 (Codex CLI parity)
- Sprint includes: FEAT-1737
- All EPIC critical-path children included or done
```

## Motivation

Sprints derived from EPICs (via FEAT-1737) inherit the EPIC's dependency structure automatically. Manually curated sprints often don't — users pick the "interesting" children and skip the blocker, causing waves to stall mid-sprint. Surfacing this at review time prevents the mid-sprint surprise.

## Proposed Solution

In `commands/review-sprint.md`, add a new audit sub-phase **3f: EPIC Context** within Phase 3 Analysis (after the existing `3e: Wave Optimization`), and add corresponding output to Phase 4 Recommendations.

1. **Identify EPIC touchpoints** — for each sprint member, read its frontmatter `parent:` field; filter for IDs matching `EPIC-\d+`; group sprint members by EPIC.
2. **For each touched EPIC**, resolve the full active-children set using `ll-sprint show EPIC-NNN` (which calls `SprintManager.load_or_resolve()` internally and returns dependency-ordered children).
3. **Compute the delta** — EPIC children NOT in the sprint. For each delta member, check if any sprint member is `blocked_by` it (either via `ll-deps tree EPIC-NNN --json` edges, or by reading the issue file's `blocked_by:` frontmatter).
4. **Render EPIC-context section** in the Phase 4 output with per-EPIC findings.
5. **Add recommendations** — concrete edit commands (`ll-sprint edit <name> --add ENH-1641`).

The implementation is entirely within the command prompt file (`commands/review-sprint.md`) using existing CLI tools — no Python changes required.

## Integration Map

### Files to Modify
- `commands/review-sprint.md` — primary file; add Phase 3f and Phase 4 EPIC-context output block
- `skills/ll-review-sprint/SKILL.md` — Codex bridge (note `ll-` prefix); defers to the command file but the description may need updating

### Files That Do NOT Need Modification
- `scripts/little_loops/sprint.py` — `SprintManager.load_or_resolve()` already handles EPIC→Sprint resolution (FEAT-1737); no changes needed
- `scripts/little_loops/issue_progress.py` — `compute_epic_progress()` already exists (FEAT-1855); no changes needed

### Shell Tools Used in the New Phase
- `ll-sprint show EPIC-NNN` — resolves EPIC to its full active-children set (ordered by dependency waves); existing FEAT-1737 functionality
- `ll-issues epic-progress EPIC-NNN` — returns per-EPIC progress including blocked children and their `blocked_by` IDs (text format best for this use case)
- `ll-deps tree EPIC-NNN --json` — returns `{root, nodes[], edges[]}` for the full child set with blocking edges; enables set-intersection with sprint members

### Dependent Files (Callers/Importers)
- `commands/review-sprint.md` calls `ll-sprint show $SPRINT_NAME` (Phase 1) — EPIC detection is additive on top of this
- `skills/issue-size-review/SKILL.md` — precedent for sprint-scoped issue audit in a command file (reads sprint YAML then loops over member IDs)

### Similar Patterns
- `commands/review-sprint.md:Phase 3e` — existing wave-optimization sub-phase; same structural shape as the new 3f
- `commands/review-sprint.md:Phase 4 / Category 3: Warnings` — existing warnings output block; EPIC-context findings slot into Warnings or a new Category 4
- `scripts/little_loops/cli/sprint/_helpers.py:_render_dependency_analysis()` — Python-layer pattern for "warning + fix suggestion" with `ll-sprint edit` fix command
- `scripts/little_loops/issue_progress.py:compute_epic_progress()` — canonical EPIC-child resolution via forward (`relates_to:`) + backward (`parent:`) union

### Tests
- `scripts/tests/test_sprint.py` — existing sprint unit tests (not directly affected; no Python changes)
- `scripts/tests/test_issues_cli.py` — existing epic-progress CLI tests (not directly affected)
- New: scenario test or snapshot test for `commands/review-sprint.md` EPIC-context output format (same type as any existing command file tests)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1859_doc_wiring.py` — new test file (does not exist yet); follow Pattern A from `scripts/tests/test_issue_size_review_skill.py` (`TestIssueSizeReviewSkillWriteBack`) — assert Phase 3f section present in `commands/review-sprint.md`, `ll-sprint show EPIC` call present, `ll-deps tree` present, `## EPIC context` output block present, `ll-sprint edit --add` fix command present; also assert `docs/guides/SPRINT_GUIDE.md` mentions EPIC awareness [Agent 3 finding]

### Documentation
- `docs/guides/SPRINT_GUIDE.md` — note EPIC awareness in the review section

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — update `/ll:review-sprint` **Output** description to mention EPIC critical-path gap flags; current prose only describes stale/dependency/contention output [Agent 2 finding]
- `docs/reference/CLI.md` — update `ll-sprint show <sprint>` argument to `<sprint|EPIC-NNN>` (matching the `ll-sprint run` entry pattern); Phase 3f instructs `ll-sprint show EPIC-NNN` but the CLI reference doesn't document this as valid for `show` [Agent 2 finding]

### Configuration
- N/A (always on; cheap structural check, no new config keys)

## Implementation Steps

1. **Read sprint YAML** — already done in Phase 1 via `ll-sprint show $SPRINT_NAME` and direct YAML read at `.sprints/$SPRINT_NAME.yaml`. Sprint `issues:` list is available.

2. **Detect EPIC touchpoints (new Phase 3f)** — for each issue ID in the sprint, read the issue file frontmatter (or use `ll-issues show $ID --json`) and extract the `parent:` field. Collect IDs matching `EPIC-\d+` pattern; group sprint members by EPIC ID.

3. **For each touched EPIC, resolve full child set** — call `ll-sprint show EPIC-NNN` (or `ll-deps tree EPIC-NNN --json` for structured edge data). The `ll-sprint show` output lists all active children in dependency wave order.

4. **Compute delta and blocker check** — `delta = epic_children_set - sprint_members_set`. For each delta member, check if any sprint member lists it in `blocked_by:` frontmatter. A positive match means the sprint includes a blocked issue but not its blocker.

5. **Render EPIC-context section** in Phase 4 output (new Category 4 or appended to Warnings):
   ```
   ### EPIC Context (N EPICs touched)
   
   #### EPIC-NNN (Title)
   - Sprint includes: ID-1, ID-2
   - Blocker not in sprint: ID-3 (Xd stalled, blocks ID-2)
     → Run: ll-sprint edit $SPRINT_NAME --add ID-3
   ```

6. **Update Phase 5 / Interactive Approval** — if blocker gaps are found, add an `AskUserQuestion` pass (5d) offering to add the missing blocker to the sprint. Option label: `"Add ID-3 (blocker)"`, description: `"Add via ll-sprint edit --add"`.

7. **Tests** — add a scenario/snapshot test verifying the EPIC-context section renders correctly for a sprint that touches an EPIC but skips a critical-path member.

8. **Docs** — update `docs/guides/SPRINT_GUIDE.md` to mention EPIC-awareness in the review section.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `commands/review-sprint.md` `allowed-tools` frontmatter — add `Bash(ll-issues:*)` and `Bash(ll-deps:*)` entries; Phase 3f calls `ll-issues epic-progress` and `ll-deps tree`, neither of which is covered by the existing `Bash(ll-sprint:*)` gate
10. Update `docs/reference/COMMANDS.md` — extend the `/ll:review-sprint` **Output** description to mention the EPIC critical-path gap section
11. Update `docs/reference/CLI.md` — change `ll-sprint show <sprint>` to `ll-sprint show <sprint|EPIC-NNN>` to reflect that `SprintManager.load_or_resolve()` accepts EPIC IDs (Phase 3f relies on this)
12. Write `scripts/tests/test_enh1859_doc_wiring.py` — structural assertions against `commands/review-sprint.md` (Phase 3f present, tools called, output block present, fix command present) and against `docs/guides/SPRINT_GUIDE.md` (EPIC awareness mentioned)

## Impact

- **Priority**: P3 — Quality-of-life for sprint planning; depends on FEAT-1737 (already done) and is more useful with FEAT-1855 / FEAT-1856 landed.
- **Effort**: Small — Pure extension to existing command file; no new Python dependencies.
- **Risk**: Low — Audit-only; never edits sprint files unless user accepts the 5d interactive prompt.
- **Breaking Change**: No

## Success Metrics

- Sprints touching ≥1 EPIC get an EPIC-context section in every review.
- Sprints that skip critical-path blockers are flagged with a concrete fix-up command.

## Scope Boundaries

- No automatic sprint editing — recommendations only (interactive approval in Phase 5d).
- No new EPIC scoring or progress logic here (defer to FEAT-1855).
- No changes to `/ll:create-sprint` (that's covered by EPIC-aware planning if separately captured).
- No Python changes needed — all new behavior lives in `commands/review-sprint.md`.

## API/Interface

No new flags. Behavior change only:

```
/ll:review-sprint <sprint-name>
# now includes "## EPIC context" section when applicable
```

## Related Key Documentation

- `docs/guides/SPRINT_GUIDE.md` — Sprint user guide covering waves, blocked_by vs depends_on

## Labels

`enhancement`, `epics`, `sprint`, `skill`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-06-01T20:17:57 - `21fc4d51-9f05-467d-9e9a-9dfbe2765d14.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `e874e443-0b3b-43eb-88ed-57be305c96d0.jsonl`
- `/ll:wire-issue` - 2026-06-01T20:12:29 - `30a028ae-141d-4e0f-b13f-1be393a6ebb5.jsonl`
- `/ll:refine-issue` - 2026-06-01T20:05:28 - `b04cf320-86fa-45f9-bd06-8d0f92e9c407.jsonl`
- `/ll:refine-issue` - 2026-06-01T00:00:00 - `unknown`
- `/ll:format-issue` - 2026-06-01T17:45:10 - `ac3a8d0e-1e74-47b1-9d58-b8dbb8f453b4.jsonl`
- `/ll:capture-issue` - 2026-06-01T17:35:32Z - `277dd3c5-ffef-46cb-bcc6-124409ce1225.jsonl`
- `/ll:manage-issue` - 2026-06-01T20:22:38Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P3
