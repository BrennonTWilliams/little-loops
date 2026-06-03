---
id: ENH-1888
title: Expand history.db consumer wiring to go-no-go and capture-issue
type: ENH
priority: P3
status: done
discovered_date: 2026-06-02
captured_at: '2026-06-02T00:00:00Z'
completed_at: '2026-06-03T03:37:51Z'
discovered_by: capture-issue
parent: EPIC-1707
depends_on:
- ENH-1847
- ENH-1887
blocked_by: []
labels:
- enhancement
- captured
confidence_score: 100
outcome_confidence: 85
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 22
---

# ENH-1888: Expand history.db consumer wiring to go-no-go and capture-issue

## Summary

ENH-1847 wired `history.db` reads into the initial 3 skills (`refine-issue`, `ready-issue`, `confidence-check`), satisfying EPIC-1707's minimum success metric. Two additional high-leverage consumers are untracked: `go-no-go` (where prior corrections on an issue's scope are a direct halt signal) and `capture-issue` (where recently closed or deferred issues could flag near-duplicate captures before they land in the backlog).

## Motivation

### `go-no-go`

`go-no-go` is the final gate before implementation begins. A prior `user_corrections` row saying "we decided not to do this approach for X reason" is exactly the kind of signal that should surface here — it's more decision-critical than `confidence-check`, which is advisory. Currently `go-no-go` builds its verdict purely from the issue file and codebase state.

### `capture-issue`

When a user captures a new issue, `capture-issue` has no visibility into recently closed or deferred issues. A common waste pattern: re-capturing an issue that was deferred 2 weeks ago with a "not now, low priority" note, or re-capturing a variant of something that was `done` last sprint. A `related_issue_events(issue_id)` lookup on the new issue's title keywords could surface a "similar issue was closed N days ago: <reason>" warning before the issue is written.

## Current Behavior

- `go-no-go`: reads issue file + optional codebase context; no history DB access
- `capture-issue`: writes new issue file; no duplicate/recency check against history DB

## Expected Behavior

### `go-no-go`

After loading the issue file (Phase 1), query:
```bash
ll-history-context <issue_id> 2>/dev/null || true
```
If output is non-empty, include as a `## Historical Context` section. A corrections match on this issue ID is a `-0.2` signal on the go/no-go verdict confidence. Surface any matched corrections as explicit "prior concerns" in the output.

### `capture-issue`

After the user describes the issue but before writing the file, query:
```bash
ll-session search --fts "<title_keywords>" --kind issue --limit 5 2>/dev/null || true
```
If results include closed/deferred issues with >70% title overlap, surface a "Similar closed issue found: <ID> — <reason>" warning and ask the user whether to proceed or link instead.

**Note**: `--kind issue` is the correct filter value (valid choices: `tool`, `file`, `issue`, `loop`, `correction`, `message`, `skill`, `cli`). FTS5 tokenizes hyphenated issue IDs — search by title keywords rather than a raw `ENH-NNN` string to get reliable matches. The check belongs in **Phase 2: Duplicate Detection** alongside the existing Jaccard scoring, not as a separate phase — results feed into the same Phase 3 routing logic.

## Scope Boundaries

- **In scope**: wiring `ll-history-context` into `go-no-go`; wiring FTS5 near-duplicate check into `capture-issue`; graceful degradation for missing DB; tests for both consumers
- **Out of scope**: changing `go-no-go` verdict logic beyond the additional signal; changing issue capture storage format; cross-project dedup

## Implementation Steps

1. Wire `ll-history-context` into `skills/go-no-go/SKILL.md`: add `Bash(ll-history-context:*)` to `allowed-tools`; add DB query step in **Phase 3, after Step 3a (Read the Issue File) and before Step 3a.5 (Learning Test pre-fetch)** — there is no "Phase 1 Gather Context" in this skill; the issue file load happens in Phase 3 Step 3a. Follow the `confidence-check/SKILL.md` prose pattern exactly: `HIST=$(ll-history-context {{issue_id}} 2>/dev/null || true)`; each matched correction is a −0.2 signal on the GO/NO-GO verdict confidence.
2. Wire `ll-session search --fts` into `skills/capture-issue/SKILL.md`: add `Bash(ll-session:*)` to `allowed-tools`; add near-duplicate FTS5 check as an additional step in **Phase 2: Duplicate Detection**, after the existing Jaccard scoring — results feed into the same Phase 3 routing already in place. Use `--kind issue` (not `--kind issue_event`); search on extracted title keywords rather than a raw `ENH-NNN` ID (FTS5 tokenizes hyphens).
3. **Create** bridge stubs `skills/ll-go-no-go/SKILL.md` and `skills/ll-capture-issue/SKILL.md` — neither file currently exists. Model after `skills/ll-refine-issue/SKILL.md` and `skills/ll-ready-issue/SKILL.md`: minimal frontmatter with matching `allowed-tools`, single-line body pointing to the source skill.
4. Add `TestGoNoGoHistoryContextInjection` (corrections present, no corrections, DB missing) to new file `scripts/tests/test_go_no_go_skill.py` — use `_phase_text()` helper slicing from `"### Phase 3"` (or the Step 3a heading) to the next `###`; assert `ll-history-context` present, `HIST` assigned, and `−0.2` signal documented. Follow `test_confidence_check_skill.py:TestConfidenceCheckHistoryContextInjection` exactly.
5. Add `TestCaptureIssueNearDuplicateCheck` (duplicate found closed, duplicate found deferred, no match, DB missing) to new file `scripts/tests/test_capture_issue_skill.py` — use `_phase_text()` slicing Phase 2; assert `ll-session` present, `--kind issue` flag documented, and graceful-degradation text present.
6. Create `scripts/tests/test_enh1888_doc_wiring.py` asserting `Bash(ll-history-context:*)` in go-no-go frontmatter, `Bash(ll-session:*)` in capture-issue frontmatter, and both new bridge stubs — follow `test_enh1847_doc_wiring.py:TestHistoryContextAllowedTools` and its `_frontmatter()` helper exactly.
7. Verify end-to-end: both skills proceed normally with no hard failure when `.ll/history.db` is absent

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `README.md`, `docs/ARCHITECTURE.md`, and `CONTRIBUTING.md` with the correct post-stub skill count: `ll-go-no-go` and `ll-capture-issue` bridge from `skills/`, not `commands/`, so their body text cannot use the `"Bridged from \`commands/"` phrase — they will NOT match `BRIDGE_MARKER` in `doc_counts.py` and will be counted; increment all three hardcoded counts by 2 (run `ll-verify-docs` after to confirm)
9. Bridge stub body text constraint: write `"Bridged from \`skills/go-no-go/SKILL.md\` for Codex Skills API discovery."` and `"Bridged from \`skills/capture-issue/SKILL.md\` for Codex Skills API discovery."` — do NOT copy the `"Bridged from \`commands/..."` line verbatim from `skills/ll-refine-issue/SKILL.md`; doing so would incorrectly suppress them from the verified skill count in `test_doc_counts.py`

## Integration Map

### Files to Modify
- `skills/go-no-go/SKILL.md` — add `Bash(ll-history-context:*)` to `allowed-tools`; add DB query step after **Step 3a (Read the Issue File)** in Phase 3 (no "Phase 1 Gather Context" exists in this skill); the existing `Bash(ll-learning-tests:*)` step 3a.5 immediately follows and provides a structural reference point
- `skills/capture-issue/SKILL.md` — add `Bash(ll-session:*)` to `allowed-tools`; add FTS5 near-duplicate check in **Phase 2: Duplicate Detection** after existing Jaccard scoring; use `--kind issue` filter

### Files to Create (Bridge Stubs — neither currently exists)
- `skills/ll-go-no-go/SKILL.md` — new Codex bridge stub; model after `skills/ll-refine-issue/SKILL.md`; must include `Bash(ll-history-context:*)` in `allowed-tools`
- `skills/ll-capture-issue/SKILL.md` — new Codex bridge stub; model after `skills/ll-refine-issue/SKILL.md`; must include `Bash(ll-session:*)` in `allowed-tools`

### Tests
- `scripts/tests/test_go_no_go_skill.py` — new file; add `TestGoNoGoHistoryContextInjection` covering: corrections present, no corrections, DB missing; follow `test_confidence_check_skill.py:TestConfidenceCheckHistoryContextInjection` and its `_phase_text()` helper; anchor `_phase_text()` at `"### Step 3a: Read the Issue File"` (next heading is `"### Step 3a.5"`)
- `scripts/tests/test_capture_issue_skill.py` — new file; add `TestCaptureIssueNearDuplicateCheck` covering: duplicate found (closed), duplicate found (deferred), no match, DB missing; anchor `_phase_text()` at `"### Phase 2: Duplicate Detection"`
- `scripts/tests/test_enh1888_doc_wiring.py` — new file; assert `Bash(ll-history-context:*)` in go-no-go frontmatter, `Bash(ll-session:*)` in capture-issue frontmatter, and both bridge stubs have matching `allowed-tools`; follow `test_enh1847_doc_wiring.py:TestHistoryContextAllowedTools` and its `_frontmatter()` helper

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_doc_counts.py` — asserts exact skill counts via `ll-verify-docs`; adding two non-bridge stubs will change the live count — verify this test passes after creating the stubs and updating the three doc count files above

### CLI (already exists, no changes)
- `scripts/little_loops/cli/history_context.py` — `ll-history-context` CLI (from ENH-1846)
- `scripts/little_loops/cli/session.py` — `ll-session search --fts` (already supports `--kind`)

### Dependent Files (Callers/Importers)
- N/A — skills are invoked by users directly, not imported by other modules

### Similar Patterns
- `skills/refine-issue/SKILL.md`, `skills/ready-issue/SKILL.md`, `skills/confidence-check/SKILL.md` — established the `ll-history-context` wiring pattern in ENH-1847; follow the same `allowed-tools` + Phase 1 query pattern

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — `**61 skills**` count must increment to 63 after adding `ll-go-no-go` and `ll-capture-issue` stubs; neither matches `BRIDGE_MARKER = "Bridged from \`commands/"` in `doc_counts.py` (these bridge from skills, not commands), so both count toward the verified total
- `docs/ARCHITECTURE.md` — `# 33 skill definitions` in the directory-tree ASCII diagram needs updating to the post-stub count
- `CONTRIBUTING.md` — `# 33 skill definitions` in the directory-tree listing needs updating to the post-stub count

### Configuration
- N/A — no config file changes; `.ll/history.db` is read-only in consumer skills

## Impact

- **Priority**: P3 — expands value of the consumer layer to two more decision-critical touchpoints
- **Effort**: Small — both wiring points follow the established pattern from ENH-1847; no new infrastructure
- **Risk**: Low — additive; skills degrade gracefully when DB is empty
- **Breaking Change**: No

## Success Metrics

- `go-no-go` Historical Context injection: `ll-history-context` output appears in skill output when DB has a corrections row for the issue → verified by `TestGoNoGoHistoryContextInjection.test_corrections_present`
- `capture-issue` near-duplicate warning: warning emitted for closed/deferred issues with >70% title overlap → verified by `TestCaptureIssueNearDuplicateCheck.test_duplicate_closed`
- Graceful degradation: both skills exit 0 and proceed normally when `.ll/history.db` is missing → verified by DB-missing test cases
- Test suite: 6 new tests (3 per skill), all green

## Acceptance Criteria

- `go-no-go` includes a `## Historical Context` section in its output when `ll-history-context` returns non-empty
- `capture-issue` surfaces a near-duplicate warning when FTS5 finds a closed/deferred issue with matching title keywords
- Both skills proceed normally (no hard failure) when `.ll/history.db` is missing or empty
- Test coverage: 3 cases per skill (matches present, no matches, DB missing)

---

**Open** | Created: 2026-06-02 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-06-03T03:29:00 - `fc8f4fc3-8af3-472c-a5c4-370021aafc26.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00Z - `31eb2104-5613-4954-9951-7e09d3cbd138.jsonl`
- `/ll:wire-issue` - 2026-06-03T03:25:27 - `7d1ba3ec-289d-4a27-a8f9-1a8a69965c26.jsonl`
- `/ll:refine-issue` - 2026-06-03T03:20:11 - `4101a91d-d955-4c95-960d-af231b3fb91d.jsonl`
- `/ll:format-issue` - 2026-06-03T01:14:03 - `6440d944-a7d1-441a-bc55-42e0d5f7c1f8.jsonl`
